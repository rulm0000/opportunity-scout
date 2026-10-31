"""Small PubMed (NCBI E-utilities) helpers. Standard library only."""
import json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

E = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL = "opportunity_scout_network"
PAUSE = 0.36  # NCBI allows about 3 requests a second without an API key


def _post(endpoint, params, tries=5):
    data = urllib.parse.urlencode({**params, "tool": TOOL}).encode()
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(E + endpoint, data=data), timeout=90) as r:
                time.sleep(PAUSE)
                return r.read().decode("utf-8")
        except Exception:
            time.sleep(2 + 3 * t)
    raise RuntimeError(f"PubMed request failed: {endpoint}")


def esearch(term, retmax=2000):
    j = json.loads(_post("esearch.fcgi", dict(db="pubmed", term=term, retmax=retmax, retmode="json")))
    return j["esearchresult"].get("idlist", [])


def efetch(pmids, batch=150):
    """Return one dict per paper: pmid, title, journal, year, authors [{last, fore, aff}]."""
    out = []
    for i in range(0, len(pmids), batch):
        root = ET.fromstring(_post("efetch.fcgi", dict(db="pubmed", id=",".join(pmids[i:i + batch]), retmode="xml")))
        for a in root.findall(".//PubmedArticle"):
            t = a.find(".//ArticleTitle")
            y = a.findtext(".//JournalIssue/PubDate/Year") or (a.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4] or ""
            authors = []
            for au in a.findall(".//AuthorList/Author"):
                if au.findtext("LastName"):
                    authors.append(dict(last=au.findtext("LastName"), fore=au.findtext("ForeName") or "",
                                        aff=" | ".join(" ".join(x.itertext()) for x in au.findall(".//AffiliationInfo/Affiliation"))))
            out.append(dict(pmid=a.findtext(".//MedlineCitation/PMID"), title="".join(t.itertext()) if t is not None else "",
                            journal=a.findtext(".//Journal/Title") or "", year=int(y) if y.isdigit() else 0, authors=authors))
    return out


def key(author):
    """Match people by last name plus first given name (initials-only names are skipped by callers)."""
    return (author["last"].lower(), (author["fore"].split() or [""])[0].lower().strip("."))


def full_name_query(author):
    return f'"{author["last"]}, {author["fore"].split()[0]}"[FAU]'


class Employers:
    """Employer affiliation rules from a config file: {name: {"pattern": regex, "exclude": regex, "pubmed": [terms]}}."""

    def __init__(self, cfg):
        self.rules = [(n, re.compile(r["pattern"]), re.compile(r["exclude"], re.I) if r.get("exclude") else None) for n, r in cfg.items()]
        terms = [t for r in cfg.values() for t in r.get("pubmed", [])]
        self.query = "(" + " OR ".join(f'"{t}"[ad]' for t in terms) + ")"

    def match(self, aff):
        for name, rx, bad in self.rules:
            if aff and rx.search(aff) and not (bad and bad.search(aff)):
                return name
        return None
