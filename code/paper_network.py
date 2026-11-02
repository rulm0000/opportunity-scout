#!/usr/bin/env python3
"""Paper-network employer finder.

Mines author affiliations on recent PubMed papers to find NON-ACADEMIC
organizations (consultancies, CROs, data firms, pharma teams, modeling firms,
digital health) that publish in a topic area. Those organizations are then
candidate employers for internships and jobs.

Standard library only. Uses NCBI E-utilities (no key needed; set NCBI_API_KEY
to go faster).

Usage:
  python3 paper_network.py --config topics.json --out <dir> [--since 2024] [--max 200]

Outputs in <dir>:
  orgs.json   one row per organization: name, type, papers, pmids, topics, sample titles
  orgs.csv    same, flat
  papers.json every screened paper with its non-academic affiliations
"""
import argparse, csv, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
KEY = os.environ.get("NCBI_API_KEY", "")
PAUSE = 0.12 if KEY else 0.4

# Company suffix filter used inside PubMed queries (keeps queries under the
# 20-operator limit when combined with a topic block).
SUFFIX_AD = '(Inc[ad] OR LLC[ad] OR Ltd[ad] OR GmbH[ad] OR "A/S"[ad] OR Corporation[ad] OR Company[ad])'

ACADEMIC = re.compile(
    r"\b(universit|college|school of|faculty of|hospital|medical cent|health system|"
    r"clinic\b|institute of technology|academy|national institutes? of health|\bNIH\b|"
    r"centers? for disease control|\bCDC\b|ministry|department of health|veterans affairs|"
    r"\bVA\b|research council|inserm|cnrs|max planck|karolinska|kaiser permanente|helmholtz|"
    r"research cent(er|re) for|medical corporation)",
    re.I)
COMPANY = re.compile(
    r"\b(inc\.?|llc|l\.l\.c\.|ltd\.?|limited|gmbh|a/s|corp\.?|corporation|company|co\.|plc|"
    r"\bag\b|s\.a\.|s\.r\.l\.|b\.v\.|pty|consulting|analytics|consultancy|partners)\b",
    re.I)

# Canonical names. Key = regex on the affiliation string, value = (name, type).
# Extend freely; unknown companies still come through via the suffix rule.
KNOWN = [
    (r"analysis group", ("Analysis Group", "consultancy")),
    (r"genesis research", ("Genesis Research Group", "consultancy")),
    (r"ossian", ("Ossian Health Economics & Communications", "consultancy")),
    (r"rti health solutions", ("RTI Health Solutions", "consultancy")),
    (r"costello medical", ("Costello Medical", "consultancy")),
    (r"evidera|ppd\b|thermo fisher", ("PPD Evidera", "CRO/consultancy")),
    (r"iqvia", ("IQVIA", "CRO/data")),
    (r"haapacs", ("HaaPACS", "modeling consultancy")),
    (r"lane clark|\blcp\b", ("Lane Clark & Peacock", "consultancy")),
    (r"curta", ("Curta", "consultancy")),
    (r"adelphi", ("Adelphi Real World", "RWE/survey")),
    (r"qualitymetric", ("QualityMetric", "PRO firm")),
    (r"cencora|pharmalex", ("Cencora", "consultancy")),
    (r"aetion", ("Aetion", "RWE tech")),
    (r"trinetx", ("TriNetX", "data firm")),
    (r"truveta", ("Truveta", "data firm")),
    (r"veradigm", ("Veradigm", "data firm")),
    (r"merative", ("Merative", "data firm")),
    (r"nference", ("nference", "AI/RWD")),
    (r"komodo", ("Komodo Health", "data firm")),
    (r"epic research|epic systems", ("Epic Research", "data firm")),
    (r"optum|unitedhealth", ("Optum/UnitedHealth", "payer")),
    (r"carelon|elevance", ("Carelon Research", "payer")),
    (r"evernorth|cigna|express scripts", ("Evernorth", "payer/PBM")),
    (r"humana", ("Humana", "payer")),
    (r"prime therapeutics", ("Prime Therapeutics", "PBM")),
    (r"cvs|aetna", ("CVS Health", "payer/PBM")),
    (r"novo nordisk", ("Novo Nordisk", "pharma")),
    (r"eli lilly|lilly research", ("Eli Lilly", "pharma")),
    (r"janssen|johnson & johnson|johnson and johnson", ("Johnson & Johnson", "pharma")),
    (r"regeneron", ("Regeneron", "pharma")),
    (r"merck|\bmsd\b", ("Merck", "pharma")),
    (r"astrazeneca", ("AstraZeneca", "pharma")),
    (r"boehringer", ("Boehringer Ingelheim", "pharma")),
    (r"bayer", ("Bayer", "pharma")),
    (r"pfizer", ("Pfizer", "pharma")),
    (r"sanofi", ("Sanofi", "pharma")),
    (r"takeda", ("Takeda", "pharma")),
    (r"biogen", ("Biogen", "pharma")),
    (r"simulations plus", ("Simulations Plus", "QSP/modeling")),
    (r"certara", ("Certara", "QSP/modeling")),
    (r"vantage research", ("Vantage Research", "QSP/modeling")),
    (r"metrum", ("Metrum Research Group", "QSP/modeling")),
    (r"applied biomath", ("Applied BioMath", "QSP/modeling")),
    (r"weightwatchers|ww international", ("WW International", "digital health")),
    (r"virta", ("Virta Health", "digital health")),
    (r"noom", ("Noom", "digital health")),
    (r"westat", ("Westat", "research org")),
    (r"mathematica", ("Mathematica", "research org")),
    (r"\bnorc\b", ("NORC", "research org")),
    (r"rti international", ("RTI International", "research org")),
    (r"rand corporation", ("RAND", "research org")),
    (r"institute for clinical and economic review|\bicer\b", ("ICER", "nonprofit HTA")),
]
KNOWN = [(re.compile(p, re.I), v) for p, v in KNOWN]


def get(url, params, tries=4):
    if KEY:
        params = dict(params, api_key=KEY)
    full = url + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(full, timeout=60) as r:
                data = r.read()
            time.sleep(PAUSE)
            return data
        except Exception as e:  # rate limit or transient
            time.sleep(1.5 * (i + 1))
            err = e
    raise RuntimeError(f"E-utilities failed: {err}")


def esearch(term, since, retmax):
    data = json.loads(get(EUTILS + "esearch.fcgi", {
        "db": "pubmed", "term": term, "retmode": "json", "retmax": retmax,
        "datetype": "pdat", "mindate": str(since), "maxdate": "3000", "sort": "pub_date"}))
    r = data["esearchresult"]
    return int(r.get("count", 0)), r.get("idlist", [])


def efetch(pmids):
    out = []
    for i in range(0, len(pmids), 100):
        xml = get(EUTILS + "efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids[i:i + 100]), "retmode": "xml"})
        root = ET.fromstring(xml)
        for art in root.iter("PubmedArticle"):
            pmid = art.findtext(".//PMID")
            title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
            year = art.findtext(".//PubDate/Year") or art.findtext(".//ArticleDate/Year") or ""
            journal = art.findtext(".//Journal/ISOAbbreviation") or ""
            affs = []
            for a in art.iter("Author"):
                for af in a.iter("AffiliationInfo"):
                    t = af.findtext("Affiliation")
                    if t:
                        affs.append(t.strip())
            out.append({"pmid": pmid, "title": title, "year": year, "journal": journal, "affs": affs})
    return out


def classify(aff):
    """Return list of (name, type) for non-academic orgs in one affiliation string."""
    hits = []
    for rx, v in KNOWN:
        if rx.search(aff):
            hits.append(v)
    if hits:
        return hits
    # Unknown org: split on ';' (multiple affiliations) and ',' segments
    for part in re.split(r";", aff):
        segs = [s.strip() for s in part.split(",") if s.strip()]
        # Re-attach bare suffixes ("Acme, Inc.") to the name before them
        merged = []
        for s in segs:
            if merged and re.fullmatch(r"(inc|llc|ltd|limited|gmbh|a/s|corp|plc|ag|co)\.?", s, re.I):
                merged[-1] = merged[-1] + " " + s
            else:
                merged.append(s)
        for s in merged:
            if COMPANY.search(s) and not ACADEMIC.search(s) and len(s) < 80:
                name = re.sub(r"\s+", " ", s).strip(" .")
                hits.append((name, "other company"))
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="topics.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", type=int, default=2024)
    ap.add_argument("--max", type=int, default=200, help="max PMIDs per query")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cfg = json.load(open(a.config))

    papers = {}
    log = []
    for topic in cfg["topics"]:
        tname = topic["name"]
        for q in topic["queries"]:
            term = q.replace("{SUFFIX_AD}", SUFFIX_AD)
            n, ids = esearch(term, a.since, a.max)
            log.append({"topic": tname, "query": term, "hits": n, "fetched": len(ids)})
            print(f"[{tname}] {n} hits, fetching {len(ids)}: {term[:110]}", file=sys.stderr)
            new = [i for i in ids if i not in papers]
            for p in efetch(new):
                p["topics"] = set()
                papers[p["pmid"]] = p
            for i in ids:
                if i in papers:
                    papers[i]["topics"].add(tname)

    orgs = defaultdict(lambda: {"type": "", "pmids": set(), "topics": set(), "titles": []})
    exclude = [re.compile(x, re.I) for x in cfg.get("exclude_orgs", [])]
    screened = []
    for p in papers.values():
        found = {}
        for aff in p["affs"]:
            for name, typ in classify(aff):
                if any(rx.search(name) for rx in exclude):
                    continue
                found[name] = typ
        p["orgs"] = sorted(found)
        screened.append({k: (sorted(v) if isinstance(v, set) else v) for k, v in p.items() if k != "affs"})
        for name, typ in found.items():
            o = orgs[name]
            o["type"] = typ
            o["pmids"].add(p["pmid"])
            o["topics"] |= p["topics"]
            if len(o["titles"]) < 3:
                o["titles"].append(f'{p["title"][:140]} ({p["journal"]} {p["year"]}, PMID {p["pmid"]})')

    rows = sorted(({"name": k, "type": v["type"], "papers": len(v["pmids"]),
                    "pmids": sorted(v["pmids"]), "topics": sorted(v["topics"]),
                    "sampleTitles": v["titles"]} for k, v in orgs.items()),
                  key=lambda r: (-r["papers"], r["name"]))
    min_papers = cfg.get("min_papers", 1)
    rows = [r for r in rows if r["papers"] >= min_papers or r["type"] != "other company"]

    json.dump(rows, open(os.path.join(a.out, "orgs.json"), "w"), indent=1)
    json.dump(screened, open(os.path.join(a.out, "papers.json"), "w"), indent=1)
    json.dump(log, open(os.path.join(a.out, "queries.json"), "w"), indent=1)
    with open(os.path.join(a.out, "orgs.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "type", "papers", "topics", "pmids"])
        for r in rows:
            w.writerow([r["name"], r["type"], r["papers"], "; ".join(r["topics"]), " ".join(r["pmids"][:10])])
    print(json.dumps({"papers": len(papers), "orgs": len(rows),
                      "top": [(r["name"], r["papers"]) for r in rows[:25]]}, indent=1))


if __name__ == "__main__":
    main()
