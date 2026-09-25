"""Massive demo submission package for schemas/ (inspector-upload demo).

6 DEMO entities x ~2,500 alerts (60 days) with distinct, labelled pathologies:
  DEMO-BANK-01  clean control (escalates hots, cited notes, full coverage)
  DEMO-BANK-02  fast-close + critical-no-escalation + hollow notes
  DEMO-BANK-03  SLA-cliff gaming + rounded reported times
  DEMO-BANK-04  silent Tier-1 vaults + missing T1566/T1003 + log drop-off
  DEMO-BANK-05  copy-paste notes (50%) + hollow triage
  DEMO-BANK-06  repeat-asset cluster + severity downgrades

Deterministic (seed=7). Writes all 7 CSVs + findings + exercises.
Usage: python schemas/make_demo.py   (run from prototype/)
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
TECHS = ["T1190", "T1566", "T1003", "T1059", "T1486", "T1078", "T1133", "T1021"]
SEVS = ["low", "medium", "high", "critical"]
SEV_W = [0.45, 0.30, 0.17, 0.08]
SLA = {"low": 72, "medium": 48, "high": 24, "critical": 8}
NOTES = [
    "Isolated host, captured source {ip} host {host} hash {h}. Containment done.",
    "WAF logs reviewed for {ip}, exploit blocked at edge, rule tuned.",
    "Phishing lure quarantined, attachment hash {h}, user warned.",
    "Timeline analysis across 6h on {host}, benign admin activity confirmed.",
    "Credential rotation forced after anomalous logins from {ip}. Escalated.",
]
TERSE = ["Closed. No issue found.", "Checked. All clear.", "Reviewed and closed."]
COPY = ["Checked logs, found nothing suspicious. Closing as false positive.",
        "Verified benign, user confirmed."]


def main(n_per=2500, seed=7):
    rng = random.Random(seed)
    t0 = datetime(2026, 8, 1)
    alerts, cases, assets, hands, escs = [], [], [], [], []
    seq = 0

    def asset_rows(ent, silent_vault):
        rows = [(f"DB-01", "Tier-1", "db-server"), ("APP-01", "Tier-2", "edr-covered"),
                ("MAIL-01", "Tier-2", "mail-gateway"), ("WS-02", "Tier-3", "workstation"),
                ("WS-03", "Tier-3", "workstation"), ("VAULT-01", "Tier-1", "db-server")]
        return [{"asset_id": a, "entity_id": ent, "criticality": c,
                 "role": r, "status": "active"} for a, c, r in rows]

    def pick_asset(ent, pool, vault_live):
        a = rng.choice(pool)
        if a == "VAULT-01" and not vault_live:
            a = "DB-01"
        return a

    for ent, profile in (("DEMO-BANK-01", "clean"), ("DEMO-BANK-02", "fast"),
                         ("DEMO-BANK-03", "sla"), ("DEMO-BANK-04", "silent"),
                         ("DEMO-BANK-05", "copy"), ("DEMO-BANK-06", "repeat")):
        pool = ["DB-01", "APP-01", "MAIL-01", "WS-02", "WS-03", "VAULT-01"]
        vault_live = profile != "silent"
        assets.extend(asset_rows(ent, vault_live))
        techs = [t for t in TECHS
                 if not (profile == "silent" and t in ("T1566", "T1003"))]
        for _ in range(n_per):
            day = rng.randrange(60)
            if profile == "silent" and day >= 53 and rng.random() < 0.80:
                continue  # log drop-off in final week
            created = t0 + timedelta(days=day, hours=rng.randrange(24),
                                     minutes=rng.randrange(60))
            sev = rng.choices(SEVS, weights=SEV_W)[0]
            tech = rng.choice(techs)
            aid = pick_asset(ent, pool, vault_live)
            sla_h = SLA[sev]
            analyst = f"an-{rng.randint(1, 6)}"
            esc, note, hollow = False, "", False

            if profile == "fast" and sev in ("high", "critical") and rng.random() < 0.40:
                closed = created + timedelta(minutes=rng.randint(3, 12))
                note = rng.choice(TERSE)
                hollow = True
            elif profile == "sla" and rng.random() < 0.55:
                closed = created + timedelta(hours=sla_h) - timedelta(minutes=rng.randint(1, 20))
                esc = rng.random() < 0.8
                note = rng.choice(NOTES).format(ip=f"10.9.{rng.randrange(256)}.{rng.randrange(1, 254)}",
                                                host=f"{aid.lower()}.corp", h=f"{rng.getrandbits(32):08x}")
            elif profile == "copy" and rng.random() < 0.50:
                closed = created + timedelta(hours=rng.uniform(1, 30))
                esc = rng.random() < 0.4
                note = rng.choice(COPY)
                hollow = True
            elif profile == "repeat" and rng.random() < 0.16:
                aid, tech = "DB-01", "T1059"
                closed = created + timedelta(hours=rng.uniform(2, 20))
                note = rng.choice(NOTES).format(ip="10.9.9.9", host="db-01.corp",
                                                h=f"{rng.getrandbits(32):08x}")
            else:
                closed = created + timedelta(hours=rng.uniform(1, 40))
                if profile == "clean":
                    esc = rng.random() < (0.95 if sev in ("critical", "high") else 0.15)
                elif profile == "fast":
                    esc = rng.random() < (0.05 if sev in ("critical", "high") else 0.1)
                else:
                    esc = rng.random() < (0.7 if sev in ("critical", "high") else 0.15)
                if not hollow:
                    note = rng.choice(NOTES).format(ip=f"10.9.{rng.randrange(256)}.{rng.randrange(1, 254)}",
                                                    host=f"{aid.lower()}.corp", h=f"{rng.getrandbits(32):08x}")

            orig = sev
            if profile == "repeat" and sev in ("critical", "high") and rng.random() < 0.50:
                sev = "low"  # quiet step-down deflates the incident count
            hmin = round((closed - created).total_seconds() / 60.0, 1)
            if profile == "sla" and rng.random() < 0.45:
                reported = float(rng.choice([30, 60, 90, 120, 240, 480]))
            else:
                reported = round(hmin * rng.uniform(0.9, 1.1), 1)
            seq += 1
            aid_ = f"{ent}-A{seq:06d}"
            note_full = note if hollow else f"{note} Ref {aid_} on {aid} [{tech}/{sev}]."
            alerts.append({"alert_id": aid_, "entity_id": ent, "orig_severity": orig,
                           "severity": sev, "asset_id": aid, "technique_id": tech,
                           "created_at": created.isoformat(), "closed_at": closed.isoformat(),
                           "sla_hours": sla_h, "escalated": esc, "status": "closed",
                           "handling_minutes": hmin, "analyst": analyst,
                           "reported_minutes": reported})
            cases.append({"case_id": f"{aid_}-C", "entity_id": ent, "alert_id": aid_,
                          "note": note_full, "investigator": analyst,
                          "closed_at": closed.isoformat()})
            hands.append({"handoff_id": f"{aid_}-H0", "alert_id": aid_,
                          "entity_id": ent, "analyst": analyst,
                          "ts": created.isoformat()})
            if esc and rng.random() < 0.25:
                escs.append({"esc_id": f"{aid_}-E", "alert_id": aid_, "entity_id": ent,
                             "actor": analyst,
                             "opened_at": (closed - timedelta(hours=rng.randint(1, 48))).isoformat(),
                             "closed_at": closed.isoformat(), "outcome": "genuine"})

    import csv
    def dump(name, rows):
        with open(os.path.join(HERE, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")

    dump("alerts.csv", alerts)
    dump("cases.csv", cases)
    dump("assets.csv", assets)
    dump("handoffs.csv", hands)
    dump("escalations.csv", escs)
    with open(os.path.join(HERE, "exercises.csv"), "w") as f:
        f.write("id,entity_id,technique_id,start,end\n"
                "RT-D1,DEMO-BANK-01,T1059,2026-08-01T00:00:00,2026-09-30T00:00:00\n"
                "RT-D2,DEMO-BANK-02,T1059,2026-08-01T00:00:00,2026-09-30T00:00:00\n"
                "RT-D3,DEMO-BANK-03,T1190,2026-08-01T00:00:00,2026-09-30T00:00:00\n"
                "RT-D4,DEMO-BANK-04,T1566,2026-08-01T00:00:00,2026-09-30T00:00:00\n"
                "RT-D5,DEMO-BANK-05,T1059,2026-08-01T00:00:00,2026-09-30T00:00:00\n"
                "RT-D6,DEMO-BANK-06,T1486,2026-08-01T00:00:00,2026-09-30T00:00:00\n")
    with open(os.path.join(HERE, "findings.csv"), "w") as f:
        f.write("entity_id,pattern,alert_ids\n"
                "DEMO-BANK-01,clean,\n"
                "DEMO-BANK-02,critical-no-escalation,\n"
                "DEMO-BANK-02,fast-close,\n"
                "DEMO-BANK-03,SLA-cliff-gaming,\n"
                "DEMO-BANK-04,silent-tier1-assets,\n"
                "DEMO-BANK-05,copy-paste-investigation,\n"
                "DEMO-BANK-06,repeat-asset-no-remediation,\n")
    print("exercises.csv + findings.csv written")


if __name__ == "__main__":
    main()
