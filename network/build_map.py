"""Build the network map page from your contacts and settings.

    python build_map.py --contacts contacts.json --config network_config.json --status status.json --out job-network-map.html

contacts.json: a list of people, each with employer, person, title, closeness (1 to 5), how, connector, connector_exchanges, path,
evidence, evidence_quote, confidence (high, medium or low), fact_check, fact_note, action and, for closeness 1 to 2, program.
network_config.json: employer order, who you would ask (trusted, insider, maybe), programs to leave out. status.json: outreach status by person.
Priority: worked with you 10, introduction agreed 9, emailed or met 8, through someone you'd ask 7, through an insider 6, through a maybe 5,
same program 3, through someone you're not ready to ask 2.5, same school 1.5; one point off when confidence is low.
"""
import argparse, json, os
ap = argparse.ArgumentParser()
ap.add_argument("--contacts", required=True); ap.add_argument("--config", required=True); ap.add_argument("--status")
ap.add_argument("--out", default="job-network-map.html")
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(a.contacts)); cfg = json.load(open(a.config))
status = json.load(open(a.status)) if a.status and os.path.exists(a.status) else {}
EMP = cfg["employers_in_order"]; I = cfg["introducers"]; cut = set(cfg.get("leave_out_programs", []))
BASE = {"trusted": 7, "insider": 6, "maybe": 5, "later": 2.5}
out = []
for r in rows:
    c = dict(r)
    if c["closeness"] <= 2 and c.get("program") in cut:
        continue
    if c["closeness"] >= 5: c["priority"] = 10
    elif c["closeness"] == 4: c["priority"] = 8
    elif c["closeness"] == 3:
        conn = c.get("connector", "")
        c["intro"] = next((k for k in ("trusted", "insider", "maybe") if conn in I.get(k, [])), "later")
        c["priority"] = BASE[c["intro"]]
    else: c["priority"] = 3 if c["closeness"] == 2 else 1.5
    if c.get("confidence") == "low" and c["closeness"] <= 3: c["priority"] -= 1
    st = status.get(c["person"])
    if st:
        c["status"], c["status_note"] = st["status"], st.get("note", "")
        if st["status"] == "agreed": c["priority"] = max(c["priority"], 9)
    out.append(c)
out.sort(key=lambda c: (-c["priority"], EMP.index(c["employer"]) if c["employer"] in EMP else 99))
emps = [{"name": e, "count": sum(1 for c in out if c["employer"] == e)} for e in EMP]
data = {"contacts": out, "employers": emps, "n_apps": cfg.get("applications", 0), "insider_label": cfg.get("insider_label", "works there and knows you")}
html = open(os.path.join(here, "map_template.html")).read().replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
open(a.out, "w").write(html)
print(f"{a.out}: {len(out)} people")
