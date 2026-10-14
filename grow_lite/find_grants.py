#!/usr/bin/env python3
"""
GROW grant finder, local copy (no AWS account needed).

Reproduces GROW2's US grant discovery from aws-samples/sample-grants-genai-assistant
(commit 473650f, 2026-10-12, MIT No Attribution license):

  1. Pick search terms from the profile keywords      (agent-discovery-search/handler.py)
  2. Search Grants.gov for each term, posted only     (grants-search-agent-v2/agent.py)
  3. Fetch each grant's full record from Grants.gov   (grants-search-agent-v2/agent.py)
  4. Score each grant against the profile             (matcher.py, GROW's Bayesian matcher)
  5. De-duplicate, drop scores under 20%, rank by score with sooner deadlines first
                                                      (agent-discovery-search/handler.py)

What was removed: the AWS pieces (DynamoDB tables, AppSync events, the AgentCore
runtime, the website). What was swapped: httpx -> Python's built-in urllib, so the
script runs with a plain Python install. GROW's EU grant search is not included.

Additions that are NOT in GROW (clearly separate from its scoring):
  - --queries and --top settings (GROW hardcodes 3 searches and shows 2 results)
  - a "mechanism" column (e.g. R01, F31) read from the grant title
  - a "students can lead" flag for mechanisms built for predoctoral students
  - a link to each grant's Grants.gov page, and a CSV + JSON output

Usage:
  python find_grants.py                       (uses profile.json next to this file)
  python find_grants.py --profile my.json --queries 8 --top 25 --out results
"""

import argparse
import csv
import html
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from matcher import apply_dual_scoring  # noqa: E402  (GROW's scoring code)

logger = logging.getLogger("grow_lite")

SEARCH_URL = "https://api.grants.gov/v1/api/search2"
DETAILS_URL = "https://api.grants.gov/v1/api/fetchOpportunity"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; GrantsAgentV2/1.0)",  # same as GROW
}
MIN_PROFILE_MATCH_SCORE = 0.20  # GROW's surfacing floor


# ---------------------------------------------------------------------------
# HTTP helper (replaces GROW's httpx.Client)
# ---------------------------------------------------------------------------
def _post_json(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Copied from GROW: grants-search-agent-v2/agent.py
# ---------------------------------------------------------------------------
def parse_search_filters(user_input):
    """Convert natural language to API filters using simple keyword matching"""
    return {
        "keyword": user_input.strip(),
        "agencies": "",
        "fundingCategories": "",
        "eligibilities": "",
        "oppStatuses": "posted",
        "fundingInstruments": "",
        "aln": "",
        "oppNum": "",
        "dateRange": "",
    }


def call_grants_api(payload):
    """Call grants.gov API"""
    result = _post_json(SEARCH_URL, payload, timeout=30.0)
    if result.get("errorcode", 0) != 0:
        raise Exception(f"API Error: {result.get('msg', 'Unknown error')}")
    data = result.get("data", {})
    logger.info(f"Grants.gov returned {len(data.get('oppHits', []))} grants "
                f"(total: {data.get('hitCount', 0)})")
    return data


def fetch_grant_details(opp_id: str) -> dict:
    """Fetch detailed grant information"""
    try:
        result = _post_json(DETAILS_URL, {"opportunityId": int(opp_id)}, timeout=10.0)
        if result.get("errorcode", 0) != 0:
            return {"error": f"API Error: {result.get('msg', 'Unknown error')}"}
        return result.get("data", {})
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def extract_cfda_titles(details_data: Dict[str, Any]) -> List[str]:
    """CFDA / Assistance Listing entries as "<number> <programTitle>" strings."""
    out = []
    try:
        for c in (details_data.get('cfdas') or []):
            number = str(c.get('cfdaNumber') or '').strip()
            title = str(c.get('programTitle') or '').strip()
            if title:
                out.append(f"{number} {title}".strip())
    except Exception as e:
        logger.warning(f"Could not extract CFDA titles: {e}")
    return out


def convert_grant_to_ui_format(grant_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert agent grant format to UI format (same as GROW V1/V2)"""
    search_data = grant_data.get('searchData', {})
    details_data = grant_data.get('detailsData') or {}

    synopsis = details_data.get('synopsis', {}) or {}
    description = synopsis.get('synopsisDesc', 'No description available')

    amount = 0
    amount_str = synopsis.get('awardCeiling', '0')
    if amount_str and str(amount_str).lower() != 'none':
        try:
            clean_amount = str(amount_str).replace('$', '').replace(',', '').strip()
            if clean_amount:
                amount = float(clean_amount)
        except Exception:
            amount = 0

    return {
        'grantId': search_data.get('id', ''),
        'title': search_data.get('title', 'No title'),
        'agency': search_data.get('agency', 'Unknown agency'),
        'amount': amount,
        'deadline': search_data.get('closeDate', ''),
        'description': description,
        'eligibility': synopsis.get('applicantEligibilityDesc', 'See grant details'),
        'applicationProcess': f"Contact: {synopsis.get('agencyContactEmail', '')}",
        'matchedKeywords': [],
        'tags': extract_cfda_titles(details_data),
        'contactEmail': synopsis.get('agencyContactEmail', ''),
        'contactPhone': synopsis.get('agencyContactPhone', ''),
        'openDate': search_data.get('openDate', ''),
        'opportunityNumber': search_data.get('number', ''),
        'source': 'GRANTS_GOV',
    }


def search_grants_sync(keyword: str, delay: float = 0.15) -> List[Dict[str, Any]]:
    """Search Grants.gov for one term and return grants in GROW's format."""
    parsed = parse_search_filters(keyword)
    payload = {
        "rows": 25,
        "startRecordNum": 0,
        "resultType": "json",
        "searchOnly": False,
        "keyword": parsed["keyword"],
        "oppStatuses": parsed["oppStatuses"],
    }
    raw_grants = call_grants_api(payload).get("oppHits", [])

    grants = []
    for grant in raw_grants[:25]:
        grant_data = {
            "searchData": {
                "id": grant.get("id", ""),
                "number": grant.get("number", ""),
                "title": grant.get("title", ""),
                "agencyCode": grant.get("agencyCode", ""),
                "agency": grant.get("agency", ""),
                "openDate": grant.get("openDate", ""),
                "closeDate": grant.get("closeDate", ""),
                "oppStatus": grant.get("oppStatus", ""),
                "docType": grant.get("docType", ""),
                "cfdaList": grant.get("cfdaList", []),
            },
            "detailsData": None,
            "error": None,
        }
        opp_id = grant.get("id")
        if opp_id:
            details = fetch_grant_details(opp_id)
            if details and not details.get("error"):
                grant_data["detailsData"] = details
            else:
                grant_data["error"] = details.get("error", "Failed to fetch details")
            time.sleep(delay)  # be polite to the public API
        grants.append(convert_grant_to_ui_format(grant_data))
    return grants


# ---------------------------------------------------------------------------
# Copied from GROW: agent-discovery-search/handler.py
# ---------------------------------------------------------------------------
def extract_broad_keywords(profile_keywords: List[str], max_queries: int = 3) -> List[str]:
    """Keep phrases up to 3 words (truncate longer ones), dedupe, take the first N."""
    broad_terms = []
    for keyword in profile_keywords:
        words = keyword.strip().split()
        broad_terms.append(keyword.strip() if len(words) <= 3 else ' '.join(words[:3]))
    return list(dict.fromkeys(broad_terms))[:max_queries]


def deduplicate_grants(grants: List[dict]) -> List[dict]:
    """Deduplicate by grantId, keeping the copy with the highest profileMatchScore."""
    seen = {}
    for grant in grants:
        grant_id = grant.get('grantId') or grant.get('id')
        if not grant_id:
            continue
        if grant_id not in seen or float(grant.get('profileMatchScore', 0)) > \
                float(seen[grant_id].get('profileMatchScore', 0)):
            seen[grant_id] = grant
    return list(seen.values())


def deadline_sort_key(grant: dict) -> float:
    """Days until deadline; unknown or past deadlines sort last."""
    raw = str(grant.get('deadline') or '').strip()
    if not raw:
        return float('inf')
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try:
            days = (datetime.strptime(raw, fmt) - datetime.now()).days
            return days if days >= 0 else float('inf')
        except ValueError:
            continue
    return float('inf')


def rank_grants(grants: List[dict]) -> None:
    """Sort in place: best match first, sooner deadline breaking ties."""
    grants.sort(key=lambda g: (-float(g.get('profileMatchScore', 0)), deadline_sort_key(g)))


# ---------------------------------------------------------------------------
# Additions (not in GROW): mechanism label and student flag
# ---------------------------------------------------------------------------
STUDENT_MECHANISMS = {"F30", "F31", "F99", "R36", "D43"}
STUDENT_WORDS = ("predoctoral", "pre-doctoral", "dissertation", "graduate student",
                 "doctoral student")
_MECH_RE = re.compile(r'\b([A-Z]{1,2}\d{2})\b')


def mechanism_of(title: str) -> str:
    m = _MECH_RE.search(title or '')
    return m.group(1) if m else ''


def students_can_lead(grant: dict) -> bool:
    text = f"{grant.get('title', '')}".lower()
    return mechanism_of(grant.get('title', '')) in STUDENT_MECHANISMS or \
        any(w in text for w in STUDENT_WORDS)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def run(profile_path: str, max_queries: int, top: int, out_prefix: str) -> List[dict]:
    with open(profile_path, 'r', encoding='utf-8') as f:
        profile = json.load(f)

    all_keywords = (profile.get('keywords') or []) + (profile.get('optimized_keywords') or [])
    queries = extract_broad_keywords(all_keywords, max_queries=max_queries) or ['research']
    print(f"Searching Grants.gov for: {', '.join(queries)}")

    scored: List[dict] = []
    for q in queries:
        try:
            grants = search_grants_sync(q)
        except Exception as e:
            print(f"  '{q}': search failed ({e})")
            continue
        grants = apply_dual_scoring(grants, profile_path, q)  # GROW's scorer
        for g in grants:
            g['foundBy'] = q
        print(f"  '{q}': {len(grants)} grants")
        scored.extend(grants)

    unique = deduplicate_grants(scored)
    kept = [g for g in unique if float(g.get('profileMatchScore', 0)) >= MIN_PROFILE_MATCH_SCORE]
    rank_grants(kept)
    surfaced = kept[:top]
    print(f"{len(scored)} results, {len(unique)} unique, {len(kept)} at or above "
          f"{MIN_PROFILE_MATCH_SCORE:.0%}, showing top {len(surfaced)}")

    rows = []
    for rank, g in enumerate(surfaced, 1):
        rows.append({
            'rank': rank,
            'score': round(float(g.get('profileMatchScore', 0)) * 100, 1),
            'title': html.unescape(g.get('title', '')).replace('\xa0', ' '),
            'opportunityNumber': g.get('opportunityNumber', ''),
            'mechanism': mechanism_of(g.get('title', '')),
            'studentsCanLead': 'yes' if students_can_lead(g) else 'no',
            'agency': g.get('agency', ''),
            'awardCeiling': int(g['amount']) if g.get('amount') else '',
            # Grants.gov "close date". For NIH PAs/PARs this is when the notice
            # expires, not the next submission due date.
            'closes': g.get('deadline', ''),
            'whyItMatched': '; '.join(g.get('matchedKeywords') or []),
            'foundBy': g.get('foundBy', ''),
            'fundingPrograms': '; '.join(g.get('tags') or []),
            'link': f"https://www.grants.gov/search-results-detail/{g.get('grantId')}",
        })

    with open(f"{out_prefix}.csv", 'w', newline='', encoding='utf-8') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    with open(f"{out_prefix}.json", 'w', encoding='utf-8') as f:
        json.dump({
            'runAt': datetime.now().isoformat(timespec='minutes'),
            'queries': queries,
            'totals': {'results': len(scored), 'unique': len(unique),
                       'aboveFloor': len(kept), 'shown': len(surfaced)},
            'grants': rows,
        }, f, indent=2)
    print(f"Wrote {out_prefix}.csv and {out_prefix}.json")
    return rows


def main():
    ap = argparse.ArgumentParser(description="GROW grant finder, local copy (no AWS).")
    ap.add_argument('--profile', default=os.path.join(HERE, 'profile.json'))
    ap.add_argument('--queries', type=int, default=8,
                    help='how many profile keywords to search (GROW uses 3)')
    ap.add_argument('--top', type=int, default=25,
                    help='how many matches to keep (GROW shows 2)')
    ap.add_argument('--out', default='grant_matches', help='output file prefix')
    ap.add_argument('--verbose', action='store_true', help="show GROW's scoring log")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format='%(message)s')
    run(args.profile, args.queries, args.top, args.out)


if __name__ == '__main__':
    main()
