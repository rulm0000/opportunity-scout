#!/usr/bin/env python3
"""
Read job boards directly (no web search) for the employers in employers.json.

Supports the public JSON feeds behind most company career sites:
  Greenhouse  GET  https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true
  Ashby       GET  https://api.ashbyhq.com/posting-api/job-board/<board>
  Lever       GET  https://api.lever.co/v0/postings/<board>?mode=json
  Workday     POST https://<tenant>.<wd>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs

Keeps research roles (epidemiology, biostatistics, outcomes research, real-world
evidence, health economics, behavioral science, data science, research scientist,
postdoctoral programs) in the United States or remote. Drops leadership titles,
internships (a separate internship tracker covers those), wet-lab roles, and
machine-learning roles. Flags part-time, contract, temporary, and remote postings.
Pay and hours are checked afterwards on each posting page.

Usage:
  python jobs_feeds.py --out jobs
  python jobs_feeds.py --mode internships --out interns     (keep intern, co-op and fellowship titles instead)
  python jobs_feeds.py --extra boards.json --out jobs        (also read boards listed in another file:
                                                              a list of employer objects, or {"employers": [...]})
  python jobs_feeds.py --only "Eli Lilly,Regeneron" --out t  (read just these employers, for testing)
"""

import argparse
import concurrent.futures as cf
import html
import json
import os
import re
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
      "Content-Type": "application/json"}

KEEP = re.compile(
    r"epidemiolog|biostatist|statistic|outcomes research|\bheor\b|health econom|real[- ]world"
    r"|\brwe\b|behavio|data scien|research scien|research associate|population health"
    r"|evidence|evaluation|post-?doc|quantitative|observational|health services|\bscientist\b", re.I)
DROP = re.compile(
    r"\b(director|head|vice president|\bvp\b|chief|principal|lead|manager|senior manager"
    r"|intern|internship|co-?op|sales|account|marketing|engineer)\b", re.I)
BENCH = re.compile(  # wet-lab and deep-learning roles, dropped by default (edit to suit your field)
    r"assay|in[- ]?vivo|in[- ]?vitro|histolog|immunohisto|chemi|cell|tissue|pharmacolog"
    r"|bioinformatic|machine learning|\bml\b|\bai\b|algorithm|imaging|genomic|protein|design control", re.I)
NON_US = re.compile(
    r"canada|poland|china|philippines|india|england|united kingdom|\buk\b|london|germany"
    r"|basel|switzerland|japan|spain|france|ireland|belgium|netherlands|singapore|australia"
    r"|brazil|mexico|italy|denmark|sweden|israel|korea|taiwan|argentina|costa rica|hungary"
    r"|czech|romania|portugal|south africa|egypt|serbia|bulgaria|greece|turkey|malaysia"
    r"|iceland|norway|finland|austria|scotland|wales|vietnam|colombia|peru|chile|ukraine"
    r"|slovakia|lithuania|estonia|croatia|new zealand|thailand|indonesia|saudi|dubai|qatar"
    r"|geneva|toronto|montreal|vancouver|ontario|quebec|zurich|munich|paris|tokyo|shanghai|beijing"
    r"|bangalore|bengaluru|hyderabad|\bcork\b|madrid|milan|copenhagen|stockholm|amsterdam|brussels"
    r"|vienna|prague|warsaw|budapest|bucharest|seoul|sydney|melbourne|sao paulo|^ca: ", re.I)
INTERN = re.compile(r"\bintern(s|ship|ships)?\b|\bco-?op\b|\bfellow(s|ship)?\b|summer 20\d\d|\bdoctoral\b|\bph\.?d\b|\bstudent\b|\btrainee\b|\bresidency\b", re.I)
INTERN_DROP = re.compile(r"\b(undergrad|undergraduate|bachelor|high school|mba|sales|marketing|finance|accounting|human resources|\bhr\b"
                         r"|supply chain|manufacturing|mechanical|electrical|facilities|it intern|software engineer)\b", re.I)
FLAGS = {"part-time": re.compile(r"part[- ]time", re.I),
         "contract": re.compile(r"\bcontract|contractor|temporary|\btemp\b|fixed[- ]term", re.I),
         "remote": re.compile(r"\bremote\b", re.I)}


def _req(url, data=None, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers=UA, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def greenhouse(e):
    d = _req(f"https://boards-api.greenhouse.io/v1/boards/{e['board']}/jobs?content=true")
    for j in d.get("jobs", []):
        yield dict(title=j.get("title", ""), location=(j.get("location") or {}).get("name", ""),
                   link=j.get("absolute_url", ""), posted=j.get("updated_at", "")[:10],
                   text=html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(j.get("content", ""))))[:4000])


def ashby(e):
    d = _req(f"https://api.ashbyhq.com/posting-api/job-board/{e['board']}")
    for j in d.get("jobs", []):
        yield dict(title=j.get("title", ""), location=j.get("location", ""),
                   link=j.get("jobUrl", ""), posted=(j.get("publishedAt") or "")[:10],
                   text=(j.get("employmentType") or "") + " " + (j.get("descriptionPlain") or "")[:4000])


def lever(e):
    d = _req(f"https://api.lever.co/v0/postings/{e['board']}?mode=json")
    for j in d:
        cat = j.get("categories") or {}
        yield dict(title=j.get("text", ""), location=cat.get("location", ""),
                   link=j.get("hostedUrl", ""), posted="",
                   text=(cat.get("commitment") or "") + " " + (j.get("descriptionPlain") or "")[:4000])


def workday(e, searches):
    base = f"https://{e['tenant']}.{e['wd']}.myworkdayjobs.com"
    seen = set()
    for q in searches:
        d = _req(f"{base}/wday/cxs/{e['tenant']}/{e['site']}/jobs",
                 {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q})
        for j in d.get("jobPostings", []):
            path = j.get("externalPath", "")
            if path in seen:
                continue
            seen.add(path)
            yield dict(title=j.get("title", ""), location=j.get("locationsText", ""),
                       link=f"{base}/en-US/{e['site']}{path}", posted=j.get("postedOn", ""),
                       text=" ".join(j.get("bulletFields") or []))


def read_employer(e, searches):
    try:
        if e["type"] == "greenhouse":
            jobs = list(greenhouse(e))
        elif e["type"] == "ashby":
            jobs = list(ashby(e))
        elif e["type"] == "lever":
            jobs = list(lever(e))
        elif e["type"] == "workday":
            jobs = list(workday(e, searches))
        else:
            return e["name"], [], f"unknown type {e['type']}"
    except Exception as ex:
        return e["name"], [], str(ex)[:80]
    return e["name"], jobs, None


def main():
    ap = argparse.ArgumentParser(description="Read employer job boards directly.")
    ap.add_argument("--employers", default=os.path.join(HERE, "employers.json"))
    ap.add_argument("--out", default="jobs")
    ap.add_argument("--mode", choices=["jobs", "internships"], default="jobs")
    ap.add_argument("--extra", help="JSON file with more employer boards (list, or {'employers': [...]})")
    ap.add_argument("--only", help="comma-separated employer names to read (testing)")
    a = ap.parse_args()
    cfg = json.load(open(a.employers, encoding="utf-8"))
    if a.extra:
        x = json.load(open(a.extra, encoding="utf-8"))
        x = x.get("employers", []) if isinstance(x, dict) else x
        names = {e["name"].lower() for e in cfg["employers"]}
        cfg["employers"] += [e for e in x if e.get("name", "").lower() not in names and e.get("type")]
    if a.only:
        want = {w.strip().lower() for w in a.only.split(",")}
        cfg["employers"] = [e for e in cfg["employers"] if e["name"].lower() in want]
    interns = a.mode == "internships"
    searches = cfg.get("internshipSearches" if interns else "workdaySearches", ["epidemiology"])
    rows, errors, total = [], {}, 0
    with cf.ThreadPoolExecutor(8) as ex:
        for name, jobs, err in ex.map(lambda e: read_employer(e, searches), cfg["employers"]):
            if err:
                errors[name] = err
                continue
            total += len(jobs)
            for j in jobs:
                t = j["title"]
                if interns:
                    if not INTERN.search(t) or INTERN_DROP.search(t):
                        continue
                elif not KEEP.search(t) or DROP.search(t) or BENCH.search(t):
                    continue
                if NON_US.search(j["location"] or "") and "united states" not in (j["location"] or "").lower():
                    continue
                blob = f"{t} {j['location']} {j['text']}"
                rows.append({"employer": name, "title": t, "location": j["location"],
                             "posted": j["posted"], "link": j["link"],
                             "flags": [k for k, rx in FLAGS.items() if rx.search(blob)]})
    rows.sort(key=lambda r: (-len(r["flags"]), r["employer"], r["title"]))
    with open(f"{a.out}.json", "w", encoding="utf-8") as f:
        json.dump({"runAt": datetime.now().isoformat(timespec="minutes"),
                   "mode": a.mode,
                   "totals": {"employers": len(cfg["employers"]), "postingsRead": total,
                              "researchRoles": len(rows)},
                   "errors": errors, "jobs": rows}, f, indent=2)
    print(f"{len(cfg['employers'])} employers, {total} postings read, {len(rows)} "
          f"{'internship' if interns else 'research'} roles kept; {len(errors)} boards failed. Wrote {a.out}.json")
    for n, err in errors.items():
        print(f"  failed: {n}: {err}")


if __name__ == "__main__":
    main()
