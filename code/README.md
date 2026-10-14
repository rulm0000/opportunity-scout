# Code: database readers and the GROW grant matcher

Everything here runs on any computer with Python 3. No packages to install, no AWS account, no logins.

## Files

| File | What it does | Typical run |
|---|---|---|
| `federal_db.py` | Downloads the full daily Grants.gov database (about 80 MB), keeps open and forecasted opportunities a doctoral student could lead, and scores them with GROW's matcher. | About 25 seconds |
| `feeds.py` | Reads the NIH Guide and NSF funding feeds and keeps student-relevant notices. These catch new notices before they reach the database. | A few seconds |
| `jobs_feeds.py` | Reads the public job boards (Greenhouse, Ashby, Lever, Workday) of the employers in `employers.json` and keeps U.S. research roles. | About 20 seconds |
| `employers.json` | The employer list for `jobs_feeds.py`. Add or remove employers here. | |
| `find_grants.py` | GROW's original search: keyword searches on Grants.gov, then scoring and ranking. Kept for comparison. | About 90 seconds |
| `matcher.py` | GROW's scoring code. Only its AWS database calls were replaced with a local profile file. Tested against GROW's original: identical scores. | |
| `profile.json` | The research profile used for scoring. Edit this to change what counts as a match. | |

Keep all the files in the same folder.

## How to run it

1. If you don't have Python, install it from python.org. On Windows, tick "Add python.exe to PATH" during install.
2. Open a terminal in this folder.
3. Run any of these:

```
python federal_db.py --out federal     # writes federal.json
python feeds.py --out feeds            # writes feeds.json
python jobs_feeds.py --out jobs        # writes jobs.json
python find_grants.py                  # writes grant_matches.csv and .json
```

Useful options:

```
python federal_db.py --extract GrantsDBExtract.zip   # reuse a file you already downloaded
python federal_db.py --no-enrich                     # skip per-grant detail lookups (faster)
python find_grants.py --queries 3 --top 2            # GROW's own defaults
python find_grants.py --verbose                      # show GROW's scoring steps
```

## What the database reader keeps

`federal_db.py` reads every record in the Grants.gov file, then keeps those that are:

- open now, or forecasted to open, with a closing date in the future, and
- something a student can apply for: a predoctoral or dissertation mechanism (F30, F31, F99, R36, K00), a title or description aimed at graduate students or dissertations, or an "Individuals" applicant type. Postdoc-only titles are dropped.

Every kept item is scored with GROW's matcher and flagged `topicalMatch` when it fits the profile, so broad fellowships open to any field are not lost. On October 14, 2026 the file held 83,562 records, 1,199 open, and 36 a doctoral student could lead.

## Editing the profile and employers

In `profile.json`, `keywords` and `optimized_keywords` drive the scoring, so put the most important ones first. GROW's docs note that fewer, broader keywords score better than many narrow ones. `agencies` gives a small boost to grants from those agencies.

In `employers.json`, each employer needs its job-board type and board name (for Workday: tenant, server, and site, which appear in the employer's careers page address).

## Known limits

- None of these scripts check full eligibility. They narrow the field; the verifier agent in `agents/` checks each item on its official page.
- The NIH closing date in the database is when a notice expires, not the next submission deadline.
- Foundations, societies, and university awards have no shared database, so these scripts never see them. The search agents cover those.
- Some employers block their job-board feeds (Lilly, Novo Nordisk, and Takeda returned errors in testing).
- GROW's EU grant search and its proposal-writing features are not included.

## Additions not in GROW

`federal_db.py`, `feeds.py`, `jobs_feeds.py`, and `employers.json` are new. In `find_grants.py`, the `--queries` and `--top` settings, the mechanism column (R01, F31, and so on), the "students can lead" flag, and the Grants.gov link column are new. None of these change GROW's scores.
