"""Find people you could be introduced to: recent co-authors of the people you would ask (introducers) who now list an employer you applied to.

    python coauthor_sweep.py --introducers introducers.json --employers employers.json --years 2019:2026 --out leads.json

Steps: (1) pull each introducer's papers in the year range (team papers with more than --max-authors authors are skipped, since a large
consortium is not a real tie); (2) check every co-author for a paper since --since-year that lists one of the employers; (3) check each hit's
latest affiliation, so people who have since left are flagged. Common names collide, so confirm every lead on LinkedIn or a staff page.
"""
import argparse, json
from pubmed import esearch, efetch, key, full_name_query, Employers

ap = argparse.ArgumentParser()
ap.add_argument("--introducers", required=True); ap.add_argument("--employers", required=True)
ap.add_argument("--years", default="2019:2026"); ap.add_argument("--since-year", type=int, default=2022)
ap.add_argument("--max-authors", type=int, default=25); ap.add_argument("--out", default="leads.json")
a = ap.parse_args()
intro = json.load(open(a.introducers)); emp = Employers(json.load(open(a.employers)))

coauthors = {}
for p in intro:  # each: {"name", "query" (PubMed author query), "self_last": [...], "self_first": optional}
    papers = efetch(esearch(f'{p["query"]} AND {a.years}[dp]'))
    for art in papers:
        if len(art["authors"]) > a.max_authors:
            continue
        for au in art["authors"]:
            k = key(au)
            if len(k[1]) < 2 or (k[0] in [s.lower() for s in p["self_last"]] and k[1].startswith(p.get("self_first", "")[:3].lower())):
                continue
            d = coauthors.setdefault(k, dict(name=f'{au["fore"]} {au["last"]}', last=au["last"], fore=au["fore"], papers=[]))
            d["papers"].append(dict(introducer=p["name"], pmid=art["pmid"], year=art["year"], title=art["title"], journal=art["journal"], n_authors=len(art["authors"])))
    print(f'{p["name"]}: {len(papers)} papers; {len(coauthors)} co-authors so far', flush=True)

keys, hits = list(coauthors), {}
for i in range(0, len(keys), 20):
    chunk = keys[i:i + 20]
    q = "(" + " OR ".join(full_name_query(coauthors[k]) for k in chunk) + f") AND {emp.query} AND {a.since_year}:3000[dp]"
    for art in efetch(esearch(q, 5000)):
        for au in art["authors"]:
            k = key(au); e = emp.match(au["aff"])
            if k in chunk and e and art["year"] >= a.since_year:
                h = hits.setdefault(k, {})
                if e not in h or art["year"] > h[e]["year"]:
                    h[e] = dict(year=art["year"], pmid=art["pmid"], affiliation=au["aff"][:300])

leads = []
for k, emps in hits.items():
    latest = None
    for art in efetch(esearch(f'{full_name_query(coauthors[k])} AND {a.since_year}:3000[dp]', 60)[:60]):
        for au in art["authors"]:
            if key(au) == k and au["aff"] and (not latest or art["year"] > latest["year"]):
                latest = dict(year=art["year"], pmid=art["pmid"], affiliation=au["aff"][:300], employer=emp.match(au["aff"]))
    for e, h in emps.items():
        left = bool(latest and latest["year"] > h["year"] and latest["employer"] != e)
        leads.append(dict(person=coauthors[k]["name"], employer=e, employer_evidence=h, latest_affiliation=latest,
                          may_have_left=left, shared_papers=sorted(coauthors[k]["papers"], key=lambda x: -x["year"])))
json.dump(leads, open(a.out, "w"), indent=1)
print(f"{len(leads)} leads written to {a.out} (confirm each one before reaching out)")
