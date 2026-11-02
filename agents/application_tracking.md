# Application tracking: rules to add to any scout prompt

The Applications tab reads its data from the `opps` collection. Any scheduled task that reads your email for employer updates (the weekly scout in `weekly_scout_prompt.md`, or an internship scout of your own) should carry the block below so stages move on their own and nothing you set gets overwritten.

Paste it into the agent's prompt next to its other database rules. Replace `{{TIME_ZONE}}` with your IANA time zone.

```
APPLICATIONS (the dashboard's Applications tab reads these fields on opps documents):
- stage: "preparing" | "submitted" | "in_review" | "interview" | "offer" | "not_selected" | "withdrawn"; stageChanged (YYYY-MM-DD); nextStep (one line: what the user must do next); nextDue (YYYY-MM-DD); folder (path to the user's application folder; never change it).
- status belongs to the user. The one exception: when a confirmation email proves they applied, set status "applied" and appliedDate, if the status is "new" or "interested".
- stage belongs to the user too. Move it only on employer evidence and only forward: a confirmation email sets "submitted" (when stage is empty or "preparing"); an "under review" notice sets "in_review"; an interview or assessment invitation sets "interview" with nextStep and nextDue; an offer sets "offer"; a rejection sets "not_selected" and outcome. Never change "withdrawn", "offer" or "not_selected", never move a stage backward, and set stageChanged whenever you change stage. Clear nextStep (set it to "") once an email shows that step is done.
- If no opps document matches an application found in email, create one with status "applied", appliedDate, stage from the same evidence, link, and source "Email <date>". Joining a talent network or registering for an event is not an application.

MEETINGS: when an email invites the user to an interview, assessment or recruiter call, or confirms a time with someone in contacts, and no meetings document exists for that person and date, create meetings/<contact doc id, or "<employer slug>-<person slug>"> with person, title, employer, employerKey, contactId, kind, format, start (ISO 8601 with offset, or null), tz "{{TIME_ZONE}}", durationMin, status ("scheduled" with a confirmed time, else "requested"), prepStatus "needed", relatedOpps and source. The meeting prep task writes the brief.
```
