#!/usr/bin/env python3
"""
Federal grant database pull: the whole Grants.gov database instead of keyword search.

GROW (and find_grants.py) searches Grants.gov one keyword at a time and keeps 25
results per keyword. Grants.gov also publishes its ENTIRE opportunity database as
a daily XML extract (https://www.grants.gov/xml-extract). This script:

  1. Downloads the latest daily extract (about 80 MB zipped) or reads a local copy.
  2. Keeps opportunities that are open now (posted, close date today or later) or
     forecasted (expected to post or close in the future).
  3. Keeps only those a doctoral student could plausibly lead: fellowship,
     predoctoral, dissertation, or graduate-student terms in the title or
     eligibility text, a student mechanism (F30, F31, F99, R36, K00), or
     "Individuals" listed as an eligible applicant. Postdoc-only notices are dropped.
  4. Pulls each survivor's full Grants.gov record (for the funding-program titles
     GROW's scorer uses) and scores it with GROW's unchanged matcher (matcher.py).
  5. Ranks them by GROW score, sooner deadlines first on ties, and flags whether
     each one names a profile keyword or research area (topicalMatch). Open-field
     fellowships that never name a topic are kept, not dropped.

Steps 2, 3, and the topic flag in 5 are additions, not GROW logic.
Final eligibility is still checked by a person or the verifier agents.

Usage:
  python federal_db.py                         (downloads today's extract)
  python federal_db.py --extract GrantsDBExtract20261014v2.zip --out federal
"""

import argparse
import html
import io
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, date
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from matcher import apply_dual_scoring          # noqa: E402  GROW's scorer
from find_grants import (fetch_grant_details,   # noqa: E402  GROW's Grants.gov calls
                         extract_cfda_titles, mechanism_of,
                         deduplicate_grants, rank_grants)

EXTRACT_PAGE = "https://www.grants.gov/xml-extract"
NS = "{http://apply.grants.gov/system/OpportunityDetail-V1.0}"

STUDENT_TERMS = re.compile(
    r"\b(pre-?doctoral|predoc|dissertation|graduate students?|doctoral (students?|candidates?)"
    r"|ph\.?d\.? (students?|candidates?)|fellowships?|trainees?|student research)\b", re.I)
STUDENT_MECHS = {"F30", "F31", "F99", "R36", "K00"}
POSTDOC_ONLY = re.compile(r"\bpost-?doctoral\b", re.I)
# Grants.gov eligible-applicant codes
INDIVIDUALS = {"21"}
UNRESTRICTED = {"99"}


def latest_extract_url() -> str:
    with urllib.request.urlopen(EXTRACT_PAGE, timeout=30) as r:
        page = r.read().decode("utf-8", "replace")
    links = sorted(set(re.findall(r'https?://[^"\']*GrantsDBExtract\d{8}v\d\.zip', page)))
    if not links:
        raise RuntimeError("No extract link found on " + EXTRACT_PAGE)
    return links[-1]


def open_extract(path: Optional[str]) -> io.BufferedReader:
    if path and os.path.exists(path):
        data = open(path, "rb").read()
    else:
        url = latest_extract_url()
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=600) as r:
            data = r.read()
        if path:
            open(path, "wb").write(data)
    z = zipfile.ZipFile(io.BytesIO(data))
    name = [n for n in z.namelist() if n.lower().endswith(".xml")][0]
    return z.open(name)


def parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%m%d%Y").date()
    except ValueError:
        return None


def clean(s: str) -> str:
    s = html.unescape(html.unescape(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def records(fh):
    """Yield one dict per opportunity (synopsis or forecast) from the extract."""
    for _, el in ET.iterparse(fh, events=("end",)):
        tag = el.tag.replace(NS, "")
        if tag not in ("OpportunitySynopsisDetail_1_0", "OpportunityForecastDetail_1_0"):
            continue
        rec = {"kind": "forecasted" if "Forecast" in tag else "posted",
               "EligibleApplicants": [], "CFDANumbers": []}
        for child in el:
            k = child.tag.replace(NS, "")
            v = child.text or ""
            if k in ("EligibleApplicants", "CFDANumbers"):
                rec[k].append(v.strip())
            else:
                rec[k] = v
        el.clear()
        yield rec


def is_open(rec: dict, today: date) -> Optional[str]:
    """Return the relevant MM/DD/YYYY deadline (or 'rolling') if open/forecasted."""
    archive = parse_date(rec.get("ArchiveDate"))
    if archive and archive < today:
        return None
    if rec["kind"] == "posted":
        close = parse_date(rec.get("CloseDate"))
        if close:
            return close.strftime("%m/%d/%Y") if close >= today else None
        return "rolling" if (archive is None or archive >= today) else None
    close = parse_date(rec.get("EstimatedSynopsisCloseDate"))
    post = parse_date(rec.get("EstimatedSynopsisPostDate"))
    if close and close >= today:
        return close.strftime("%m/%d/%Y")
    if post and post >= today:
        return "forecast: posts " + post.strftime("%m/%d/%Y")
    return None


def student_signal(rec: dict) -> Optional[str]:
    title = clean(rec.get("OpportunityTitle"))
    elig = clean(rec.get("AdditionalInformationOnEligibility"))
    mech = mechanism_of(title)
    if mech in STUDENT_MECHS:
        return f"{mech} mechanism"
    m = STUDENT_TERMS.search(title) or STUDENT_TERMS.search(elig)
    if m:
        if POSTDOC_ONLY.search(title) and not re.search(r"pre-?doctoral", title, re.I):
            return None
        return f'"{m.group(0).lower()}"'
    codes = set(rec["EligibleApplicants"])
    if codes & INDIVIDUALS:
        return "Individuals eligible"
    return None


def to_grow_format(rec: dict, deadline: str) -> dict:
    """Shape a database record like GROW's grant dict so its scorer can read it."""
    amount = 0.0
    try:
        amount = float(rec.get("AwardCeiling") or 0)
    except ValueError:
        pass
    return {
        "grantId": rec.get("OpportunityID", ""),
        "title": clean(rec.get("OpportunityTitle")),
        "agency": clean(rec.get("AgencyName")),
        "amount": amount,
        "deadline": deadline if re.match(r"\d{2}/\d{2}/\d{4}$", deadline) else "",
        "description": clean(rec.get("Description")),
        "eligibility": clean(rec.get("AdditionalInformationOnEligibility")),
        "matchedKeywords": [],
        "tags": [],
        "opportunityNumber": rec.get("OpportunityNumber", ""),
        "source": "GRANTS_GOV_EXTRACT",
    }


def run(extract: Optional[str], profile_path: str, out_prefix: str, enrich: bool) -> List[dict]:
    today = date.today()
    seen = kept = 0
    candidates: List[dict] = []
    signals: Dict[str, str] = {}
    for rec in records(open_extract(extract)):
        seen += 1
        deadline = is_open(rec, today)
        if not deadline:
            continue
        sig = student_signal(rec)
        if not sig:
            continue
        g = to_grow_format(rec, deadline)
        g["_status"] = rec["kind"]
        g["_deadlineText"] = deadline
        g["_eligibleCodes"] = rec["EligibleApplicants"]
        signals[g["grantId"]] = sig
        candidates.append(g)
    print(f"{seen} opportunities in the database; {len(candidates)} open or forecasted "
          f"with a student signal")

    if enrich:  # funding-program titles for GROW's CFDA signal (one call per survivor)
        for g in candidates:
            d = fetch_grant_details(g["grantId"])
            if d and not d.get("error"):
                g["tags"] = extract_cfda_titles(d)

    scored = apply_dual_scoring(candidates, profile_path, "")
    rows = deduplicate_grants(scored)
    for g in rows:
        reasons = g.get("matchedKeywords") or []
        g["_topical"] = any(r.endswith("(in title)") or r.endswith("(in description)")
                            for r in reasons)
    # Open-field fellowships (F99/K00, NSF dissertation grants) often never name a
    # topic, so they are kept and flagged rather than dropped; the verifier judges fit.
    rank_grants(rows)
    kept = sum(1 for g in rows if g["_topical"])

    out = []
    for i, g in enumerate(rows, 1):
        out.append({
            "rank": i,
            "score": round(float(g.get("profileMatchScore", 0)) * 100, 1),
            "title": g["title"],
            "opportunityNumber": g["opportunityNumber"],
            "mechanism": mechanism_of(g["title"]),
            "status": g["_status"],
            "agency": g["agency"],
            "awardCeiling": int(g["amount"]) if g.get("amount") else "",
            "closes": g["_deadlineText"],
            "studentSignal": signals.get(g["grantId"], ""),
            "individualsEligible": bool(set(g["_eligibleCodes"]) & (INDIVIDUALS | UNRESTRICTED)),
            "topicalMatch": g["_topical"],
            "whyItMatched": "; ".join(g.get("matchedKeywords") or []),
            "link": f"https://www.grants.gov/search-results-detail/{g['grantId']}",
        })
    with open(f"{out_prefix}.json", "w", encoding="utf-8") as f:
        json.dump({"runAt": datetime.now().isoformat(timespec="minutes"),
                   "totals": {"database": seen, "studentSignal": len(candidates),
                              "topicalMatches": kept},
                   "grants": out}, f, indent=2)
    print(f"{len(out)} kept ({kept} name a profile topic); wrote {out_prefix}.json")
    return out


def main():
    ap = argparse.ArgumentParser(description="Score the full Grants.gov database with GROW.")
    ap.add_argument("--extract", help="local extract .zip (downloaded and saved here if missing)")
    ap.add_argument("--profile", default=os.path.join(HERE, "profile.json"))
    ap.add_argument("--out", default="federal_matches")
    ap.add_argument("--no-enrich", action="store_true",
                    help="skip per-grant Grants.gov lookups (faster, weaker scoring)")
    a = ap.parse_args()
    run(a.extract, a.profile, a.out, enrich=not a.no_enrich)


if __name__ == "__main__":
    main()
