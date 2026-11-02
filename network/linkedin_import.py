#!/usr/bin/env python3
"""
Import a LinkedIn "Connections.csv" export and find first-degree connections at target employers.

How to get the file (LinkedIn, desktop):
  Me > Settings & Privacy > Data privacy > Get a copy of your data >
  "Want something in particular?" > tick Connections > Request archive.
  LinkedIn emails a download link (usually within about 10 minutes for Connections only).
  Unzip it; the file is Connections.csv.

The export starts with a few "Notes:" lines before the real header:
  First Name,Last Name,URL,Email Address,Company,Position,Connected On
Email Address is blank unless the connection allows it to be shared.

Usage:
  python3 linkedin_import.py Connections.csv --targets targets.json --contacts contacts.json --out out_dir
    targets.json   {"employers": [{"key": "acme", "name": "Acme Pharma", "match": ["acme pharma", "acme"]}, ...]}
    contacts.json  optional: a list of existing contact records with "person" and "employer" (to flag who is new)
Writes:
  out_dir/linkedin_connections.json   every connection, normalized, with the employer key it matched (or null)
  out_dir/linkedin_by_employer.json   matched connections grouped by employer key, newest connection first
  out_dir/linkedin_contact_ops.json   database ops (set) for NEW matched people, ready for a contacts collection
Standard library only. Nothing is sent anywhere.
"""
import argparse, csv, io, json, os, re, sys, unicodedata
from datetime import datetime

HEADER = ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"]


def read_connections(path):
    raw = open(path, encoding="utf-8-sig", errors="replace").read()
    lines = raw.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("First Name,")), None)
    if start is None:
        raise SystemExit("No 'First Name,...' header found; is this LinkedIn's Connections.csv?")
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
    out = []
    for r in rows:
        first, last = (r.get("First Name") or "").strip(), (r.get("Last Name") or "").strip()
        if not (first or last):
            continue
        out.append({
            "person": f"{first} {last}".strip(),
            "company": (r.get("Company") or "").strip(),
            "position": (r.get("Position") or "").strip(),
            "url": (r.get("URL") or "").strip(),
            "linkedinEmail": (r.get("Email Address") or "").strip(),
            "connectedOn": parse_date(r.get("Connected On")),
        })
    return out


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def norm(s):
    return re.sub(r"[^a-z0-9&]+", " ", (s or "").lower()).strip()


def employer_key(company, targets):
    c = " " + norm(company) + " "
    for t in targets:
        for m in t["match"]:
            if " " + norm(m) + " " in c:
                return t["key"]
    return None


def ascii_fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def name_key(s):
    """First and last name only, so "Jane A. Example", "Jane Example" and "Dr. Jane Example, MD" match."""
    s = ascii_fold(s)
    s = re.sub(r"\([^)]*\)", " ", s or "")
    s = re.sub(r",.*$", "", s)
    toks = [t for t in re.sub(r"[^a-z\- ]+", " ", s.lower()).split() if len(t) > 1 and t not in ("dr", "mr", "ms", "mrs", "prof")]
    return (toks[0], toks[-1]) if len(toks) >= 2 else tuple(toks)


def slug(s, n=40):
    return re.sub(r"[^a-z0-9]+", "-", ascii_fold(s).lower()).strip("-")[:n].strip("-")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("csv")
    ap.add_argument("--targets", required=True)
    ap.add_argument("--contacts")
    ap.add_argument("--out", default="linkedin_out")
    a = ap.parse_args()
    targets = json.load(open(a.targets, encoding="utf-8"))["employers"]
    tname = {t["key"]: t["name"] for t in targets}
    known = set()
    if a.contacts and os.path.exists(a.contacts):
        for c in json.load(open(a.contacts, encoding="utf-8")):
            known.add(name_key(c.get("person")))
    conns = read_connections(a.csv)
    for c in conns:
        c["employerKey"] = employer_key(c["company"], targets)
    os.makedirs(a.out, exist_ok=True)
    json.dump(conns, open(os.path.join(a.out, "linkedin_connections.json"), "w"), indent=1, ensure_ascii=False)
    by = {}
    for c in conns:
        if c["employerKey"]:
            by.setdefault(c["employerKey"], []).append(c)
    for v in by.values():
        v.sort(key=lambda c: c["connectedOn"], reverse=True)
    json.dump(by, open(os.path.join(a.out, "linkedin_by_employer.json"), "w"), indent=1, ensure_ascii=False)
    today = datetime.now().strftime("%Y-%m-%d")
    ops, used = [], set()
    for k, people in by.items():
        for c in people:
            if name_key(c["person"]) in known:
                continue
            path = f"contacts/{k}-{slug(c['person'])}"
            if path in used:  # two people with the same name at one employer
                path += "-" + slug(c["url"].rstrip("/").rsplit("/", 1)[-1], 20)
            used.add(path)
            ops.append({"op": "set", "path": path, "data": {
                "employer": tname[k], "employerKey": k, "person": c["person"], "title": c["position"],
                "connector": "", "intro": "direct", "status": "not_asked", "priority": 5,
                "statusNote": f"First-degree LinkedIn connection since {c['connectedOn']}.",
                "action": "You can message them directly on LinkedIn; mention the role you applied to on their team.",
                "linkedinUrl": c["url"], "linkedinEmail": c["linkedinEmail"], "email": "",
                "source": f"LinkedIn export {today}"}})
    json.dump(ops, open(os.path.join(a.out, "linkedin_contact_ops.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(conns)} connections read; {sum(len(v) for v in by.values())} at target employers "
          f"({', '.join(f'{tname[k]} {len(v)}' for k, v in sorted(by.items()))}); {len(ops)} new contact records.")


if __name__ == "__main__":
    main()
