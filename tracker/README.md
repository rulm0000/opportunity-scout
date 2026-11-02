# The dashboard

`opportunity-scout.html` is one page with five tabs. It is published as a Claude artifact with the `db` capability, and scheduled Claude tasks keep its database current.

| Tab | What it shows | Who fills it |
|---|---|---|
| Overview | What needs you next: meetings, application steps and deadlines in date order, plus when each agent last ran | Built from the other tabs |
| Opportunities | Verified grants, scholarships, internships and jobs you are eligible for, programs to watch, swept areas, and a ruled-out list | Weekly opportunity scout, internship scout |
| Applications | Everything you applied to or are preparing, with its stage, next step, closing date and the folder that holds your materials | You (stage), the scouts (from employer emails) |
| Network | People at those employers, who can introduce you, and where each conversation stands | Network tools in `network/`, a reply-check task |
| Meetings | Each call or interview with a prep brief: who they are, what their group does, a diagram of how their work connects to yours, ranked questions, your notes | Meeting prep task (`agents/meeting_prep_prompt.md`) |

Every employer name links to an employer page that gathers its applications, people, meetings, open roles and watch items in one place. Your own choices (an opportunity's status, an application's stage, which questions you asked, meeting notes) save to the database, and the agents are told to leave them alone.

## Publish it

1. In Claude, publish `opportunity-scout.html` as an artifact with `capabilities: {"db": {}}`.
2. Optional: save `settings.example.json`, edited, as the document `settings/dashboard`. It groups the names an employer goes by under one key, sets the order employers are listed in, and sets the pay floor used on watch rows.
3. Give the artifact's link to each scheduled task (the `{{TRACKER_URL}}` field in `agents/`).

The page only works inside Claude, because it reads and writes the artifact's database. It renders a designed empty state until the first agent run fills it.

## Data model

All collections live in the artifact's database. Dates are `YYYY-MM-DD`; meeting times are ISO 8601 with an offset.

### opps
One document per opportunity or application. Written by the scouts; `status` and `stage` belong to you.

| Field | Meaning |
|---|---|
| `category` | `grant`, `industry`, `scholarship`, `internship` or `job` |
| `name`, `org`, `number`, `link` | What it is, who offers it, requisition or opportunity number, official page |
| `amount`, `deadline` | Pay or award text; a date, `rolling`, or short text such as `Expected Mar 2027` |
| `eligibility`, `confirmNote` | `eligible` or `confirm`, and the one fact to confirm |
| `whyFit`, `eligibilityCheck`, `source` | One-line fit, how eligibility was checked, which agent found it |
| `status` | Yours: `new`, `interested`, `applied`, `dismissed` |
| `appliedDate`, `outcome`, `closed` | Application date, latest employer update, deadline passed |
| `stage` | Yours (agents move it forward on employer evidence only): `preparing`, `submitted`, `in_review`, `interview`, `offer`, `not_selected`, `withdrawn` |
| `nextStep`, `nextDue` | What you need to do next, and by when |
| `folder`, `materials` | Path to your application folder; optional list of `{label, path}` |

An opportunity shows on the Applications tab once its status is `applied` or it has a `stage`. Without a stage, the page infers one from `outcome`.

### watch
Programs that have not posted yet or pay below your floor: `org`, `name`, `status` (`watching`, `not_started`, `window_open`), `checkBy`, `deadline`, `payHr`, `floor` (`at`, `below`, `unknown`), `link`, `contact`, `nextAction`, `updates` (list of `{date, note}`).

### contacts
People at employers: `employer`, `employerKey`, `person`, `title`, `connector` (who would introduce you), `intro`, `status` (`not_asked`, `draft`, `asked`, `agreed`, `introduced`, `replied`, `met`), `statusNote`, `action`, `email` (only from an official page or a corresponding-author line), `priority`, `source`. `network/linkedin_import.py` and the sweeps in `network/` produce records in this shape.

### meetings
One document per meeting; `doc_id` is the contact's id when there is one.

| Group | Fields |
|---|---|
| Identity | `person`, `credentials`, `title`, `employer`, `employerKey`, `contactId`, `connector` |
| Logistics | `kind`, `format`, `start`, `tz`, `durationMin`, `status` (`requested`, `scheduled`, `done`, `followed_up`, `cancelled`), `nextStep`, `relatedOpps` |
| Brief | `prepStatus` (`needed`, `ready`, `updated`), `prepUpdated`, `prepDoc`, `headline`, `summary`, `timeline` [`{when, role}`], `work` [`{year, title, venue, note, link}`], `groupIntro`, `group` [text], `groupLinks` [`{label, url}`], `news` [`{date, text, link}`] |
| Connections | `bridgeHeaders` (three column labels), `bridgeSummary`, `bridges` [`{theirs, theirsDetail, shared, mine, mineDetail}`] |
| Questions | `questionTip`, `questions` [`{topic, text}`], `backupQuestion`, `mention`, `emailDraft` {`context`, `body`} |
| Yours | `asked` (indexes of questions you ticked), `notes`, `notesUpdated`, `status` |
| Wrap-up | `followUp`, `sources` [`{label, url}`], `unverified`, `source` |

The page draws the `bridges` as a three-column diagram (their work, the shared idea, your work), so no image is needed.

### Run logs
Each agent writes one document per run, and the Overview tab shows the latest of each: `runs` (weekly opportunity scout), `internship_runs`, `replycheck_runs`, `meeting_runs`. Each has at least a `date` field.

### Other collections
`ruledout` (everything screened out, never resurfaced), `coverage` (areas the scouts have swept), `boards` (extra job boards found by runs), `settings/dashboard` (above).
