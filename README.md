# Opportunity Scout

A weekly system that finds grants, industry funding, scholarships and awards, and jobs a doctoral student is actually eligible for, and keeps them in one tracker.

It has three parts:

| Folder | What it is |
|---|---|
| `grow_lite/` | A no-AWS copy of the grant matcher from GROW2 (Grant Research Opportunity Wizard, built by AWS with a UNC researcher). Searches Grants.gov and scores each grant with GROW's own code. |
| `agents/` | Instructions for a scheduled Claude task: eight search agents, an independent verifier pass, and a retry loop, all checked against an explicit eligibility checklist. |
| `tracker/` | The tracker page that stores verified opportunities, the ruled-out list, and a run log. |

## How a weekly run works

1. **GROW match.** `grow_lite/find_grants.py` searches Grants.gov and scores every grant against `profile.json` using GROW's Bayesian matcher. Most results are faculty-level grants; only student-eligible ones go on to verification.
2. **Search agents.** Eight agents search in parallel: NIH and federal, foundations, societies and conferences, university and state, national scholarships, industry funding, competitions and prizes, and jobs. Each runs at least 15 searches and returns 10 to 20 candidates.
3. **Email leads.** Recent funding and job emails are read for more candidates.
4. **Independent verification.** A separate verifier agent, which never sees the searchers' reasoning, opens each official page and checks nine eligibility rules: career stage, place, field, timing, award overlap, personal criteria, values, job rules, and proof on the official page.
5. **Retry loop.** Any agent with fewer than 4 passing finds searches again on new source types, and a fresh verifier checks the new batch.
6. **Tracker and report.** Passing items go to the tracker as Eligible, or Confirm with the one fact to check. Rejections go to a ruled-out list so they never come back.

## Run the grant matcher by itself

```
cd grow_lite
python find_grants.py                        # 8 searches, top 25
python find_grants.py --queries 3 --top 2    # GROW's own defaults
```

It needs only Python, with no packages to install. Edit `grow_lite/profile.json` to change what it searches for. See `grow_lite/README.md` for details and known limits.

## Set up the weekly agents

1. Publish `tracker/opportunity-scout.html` as a Claude artifact with the `db` capability, and add the three `grow_lite` files to it under `code/`.
2. Fill in every `{{...}}` field in `agents/weekly_scout_prompt.md`.
3. Create a weekly scheduled task in Claude with that prompt.

The tracker page only works inside Claude, because it saves to the artifact's database.

## Credit and license

The grant matching code comes from GROW2, [aws-samples/sample-grants-genai-assistant](https://github.com/aws-samples/sample-grants-genai-assistant) (commit 473650f, October 2026), released under the MIT No Attribution license. The scoring math in `grow_lite/matcher.py` is unchanged; only its AWS database calls were replaced with a local profile file. The search agents, verifier loop, eligibility checklist, and tracker are new. Everything here is released under the same MIT No Attribution license (see `LICENSE`).
