"""Deep dive on one employer: everyone with that employer's affiliation on a recent paper who once listed one of your schools or programs.

    python employer_alumni.py --employer "Eli Lilly" --employers employers.json --circles circles.json --since 2022 --out alumni.json

circles.json maps a label to a regex, for example {"UNC": "University of North Carolina|Chapel Hill"}; a PubMed query term for each goes in
"pubmed" (see circles.example.json). Name collisions are common: check each result's past affiliations and topics before using it.
"""
import argparse, json, re
from pubmed import esearch, efetch, key, full_name_query, Employers

ap = argparse.ArgumentParser()
ap.add_argument("--employer", required=True); ap.add_argument("--employers", required=True); ap.add_argument("--circles", required=True)
ap.add_argument("--since", type=int, default=2022); ap.add_argument("--out", default="alumni.json")
a = ap.parse_args()
cfg = json.load(open(a.employers)); one = Employers({a.employer: cfg[a.employer]})
circles = json.load(open(a.circles)); rx = {k: re.compile(v["pattern"], re.I) for k, v in circles.items()}
cq = "(" + " OR ".join(f'"{t}"[ad]' for v in circles.values() for t in v["pubmed"]) + ")"

people = {}
for art in efetch(esearch(f"{one.query} AND {a.since}:3000[dp]", 20000)):
    for au in art["authors"]:
        k = key(au)
        if len(k[1]) >= 2 and one.match(au["aff"]):
            p = people.setdefault(k, dict(name=f'{au["fore"]} {au["last"]}', last=au["last"], fore=au["fore"], latest=0))
            if art["year"] >= p["latest"]:
                p.update(latest=art["year"], pmid=art["pmid"], affiliation=au["aff"][:250])
print(len(people), "people with a", a.employer, "affiliation since", a.since, flush=True)

found, keys = {}, list(people)
for i in range(0, len(keys), 25):
    chunk = keys[i:i + 25]
    for art in efetch(esearch("(" + " OR ".join(full_name_query(people[k]) for k in chunk) + f") AND {cq}", 3000)):
        for au in art["authors"]:
            k = key(au)
            if k in chunk and au["aff"] and not one.match(au["aff"]):
                for label, r in rx.items():
                    if r.search(au["aff"]):
                        found.setdefault(k, dict(person=people[k], past=[]))["past"].append(
                            dict(circle=label, year=art["year"], pmid=art["pmid"], affiliation=au["aff"][:220], title=art["title"][:150]))
                        break
json.dump(list(found.values()), open(a.out, "w"), indent=1)
print(len(found), "with a past affiliation in your circles, written to", a.out)
