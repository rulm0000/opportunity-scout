# Network search: who can get you in the door

Tools for the second half of a job search: once you have applied, find people at those employers you can reach, and through whom.
Standard library Python only, like the rest of this repo.

## Files

| File | What it does |
|---|---|
| `coauthor_sweep.py` | Takes the people you would ask for an introduction and pulls their papers in a year range (PubMed). Every co-author is checked for a recent paper that lists an employer you applied to, then for their latest affiliation, so people who have left are flagged. Large team papers (over 25 authors) are skipped. |
| `employer_alumni.py` | Deep dive on one employer: everyone with that employer's affiliation since a given year who once listed one of your schools or programs. |
| `build_map.py`, `map_template.html` | Turns your contact list into a one-page map: you, then the person or program you would go through, then the person, then the employer. Introductions people have agreed to are starred; contacts you are not ready to ask are greyed out. |
| `pubmed.py` | Shared PubMed helpers and the employer-matching rules. |
| `outreach/Build-OutreachDrafts.ps1` | Builds Outlook drafts (new messages or replies on the same thread) with your own signature. It only saves drafts and never sends. |
| `*.example.json` | Fill-in examples of every input file. |

## Use it

1. Copy each `*.example.json` to the same name without `.example` and fill it in: `introducers.json` (who you would ask, with a PubMed author query for each), `employers.json` (how each employer appears in affiliations), `circles.json` (your schools and programs), `network_config.json` (employer order and who counts as an introducer), `status.json` (who has agreed).
2. Run the sweeps:

```
python coauthor_sweep.py --introducers introducers.json --employers employers.json --years 2019:2026 --out leads.json
python coauthor_sweep.py --introducers introducers.json --employers employers.json --years 2008:2018 --out leads_older.json
python employer_alumni.py --employer "Eli Lilly" --employers employers.json --circles circles.json --since 2022 --out alumni.json
```

3. Confirm every lead before using it. Common names collide (two different people named Wei Zhang), and pharma papers often list an academic author's consulting ties. Check that the person's topic and past affiliations match, and confirm the current employer on LinkedIn or a staff page.
4. Put the confirmed people in `contacts.json` (see `contacts.example.json`) and build the map:

```
python build_map.py --contacts contacts.json --config network_config.json --status status.json --out job-network-map.html
```

## What worked in practice

- Co-authors of the people you would actually ask beat broad alumni lists. A collaborator's word carries weight; a shared school rarely does.
- Ask one introducer about one or two people, and list each person's email so they can forward it in one step.
- Get emails only from company or university pages or corresponding-author lines, never by guessing a pattern.
- LinkedIn's second-degree results show which of your contacts link to an employer. Someone you met who already works there can often point you to many colleagues.

## Privacy

Your filled-in files, sweep results and map hold real names and emails, so `.gitignore` keeps them out of the repo. Only the code and the made-up examples are shared.
