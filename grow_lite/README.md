# GROW grant finder, local copy (no AWS)

A copy of the grant-matching part of GROW2 (AWS and UNC's Grant Research
Opportunity Wizard) that runs on any computer with Python. No AWS account,
no logins, no website, no monthly bill.

Source: github.com/aws-samples/sample-grants-genai-assistant, commit 473650f
(Oct 12, 2026). License: MIT No Attribution, so copying and changing it is allowed.

## What it does

1. Takes the first few keywords from `profile.json` as search terms.
2. Searches Grants.gov for each one (posted opportunities, 25 per search).
3. Pulls each grant's full record from Grants.gov.
4. Scores every grant against your profile with GROW's own scoring code
   (`matcher.py`). Tested against GROW's original file: identical scores.
5. Drops anything under 20%, removes duplicates, and ranks the rest
   (sooner closing dates break ties).

Results go to `grant_matches.csv` (opens in Excel) and `grant_matches.json`.

## Files

- `find_grants.py`: the search and ranking steps, copied from GROW.
- `matcher.py`: GROW's scoring code. Only the AWS database lines were replaced.
- `profile.json`: your research profile. Edit this to change what it looks for.

Keep all three in the same folder.

## How to run it on Windows

1. If you don't have Python, install it from python.org. Tick
   "Add python.exe to PATH" during install.
2. Put the three files in one folder, for example `Documents\grant-finder`.
3. Open PowerShell in that folder (Shift + right-click the folder, then
   "Open PowerShell window here").
4. Run:

   ```
   python find_grants.py
   ```

   It takes about a minute and a half.

Optional settings:

```
python find_grants.py --queries 3 --top 2     # GROW's own defaults
python find_grants.py --queries 10 --top 50   # wider search
python find_grants.py --verbose               # show GROW's scoring steps
```

## Editing your profile

`keywords` and `optimized_keywords` are searched in order, so put the most
important ones first. GROW's docs note that fewer, broader keywords score
better than many narrow ones. `agencies` gives a small boost to grants from
those agencies.

## Known limits (from GROW itself)

- Grants.gov only. It never sees foundations, societies, or UNC internal awards.
- Matching is by keyword, not meaning. Different wording means no match.
- It does not check whether you are eligible. Most Grants.gov listings are
  for faculty-led projects.
- Forecasted opportunities are skipped; only posted ones are searched.
- The closing date for NIH program announcements is when the notice expires,
  not the next submission deadline.
- GROW's EU grant search and its proposal-writing features are not included.

## Additions not in GROW

The `--queries` and `--top` settings, the mechanism column (R01, F31, and so on),
the "students can lead" flag, and the Grants.gov link column. None of these
change GROW's scores.
