#!/usr/bin/env python3
"""
Read the NIH Guide and NSF funding feeds directly and keep student-relevant notices.

Most NIH and NSF opportunities also appear in the Grants.gov database
(federal_db.py), but these feeds catch new notices early, including NIH notices
(NOT-...) that announce supplements or reissued fellowships.

Usage:
  python feeds.py --out feeds
"""

import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

FEEDS = {
    "NIH Guide": "https://grants.nih.gov/grants/guide/newsfeed/fundingopps.xml",
    "NSF": "https://www.nsf.gov/rss/rss_www_funding_pgm_annc_inf.xml",
}
STUDENT = re.compile(
    r"pre-?doctoral|dissertation|graduate|doctoral|fellowship|trainee|training|student"
    r"|\b(F30|F31|F99|R36|K00|T32|R25)\b|diversity supplement|re-?entry", re.I)


def read(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    for it in root.iter("item"):
        yield {"title": (it.findtext("title") or "").strip(),
               "link": (it.findtext("link") or "").strip(),
               "date": (it.findtext("pubDate") or "").strip()}


def main():
    ap = argparse.ArgumentParser(description="Read NIH and NSF funding feeds.")
    ap.add_argument("--out", default="feeds")
    a = ap.parse_args()
    rows, errors = [], {}
    for name, url in FEEDS.items():
        try:
            for item in read(url):
                if STUDENT.search(item["title"]):
                    rows.append({"feed": name, **item})
        except Exception as ex:
            errors[name] = str(ex)[:80]
    with open(f"{a.out}.json", "w", encoding="utf-8") as f:
        json.dump({"runAt": datetime.now().isoformat(timespec="minutes"),
                   "errors": errors, "items": rows}, f, indent=2)
    print(f"{len(rows)} student-relevant feed items; wrote {a.out}.json")


if __name__ == "__main__":
    main()
