"""Synthetic CSE data generator with INJECTED, LABELLED gaming patterns.

Deterministic (seeded). Produces alert/case/asset tables shaped like the
periodic CSE submissions described in PS section 2, plus a ground-truth
manifest used by the validation harness as a stand-in for NCIIPC
past-manual-review findings (PS section 8).

Entities:
  CSE-001  clean control (healthy SOC)
  CSE-002  SLA-gamer (closures cluster just before SLA deadline)
  CSE-003  copy-paste investigator + fast-closer
  CSE-004  silent Tier-1 assets + ATT&CK coverage gaps + volume drop
  CSE-005  critical-no-escalation + repeat-asset-no-remediation
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

TECHNIQUES = ["T1190", "T1566", "T1003", "T1059", "T1486", "T1078", "T1133", "T1021"]
SEVERITIES = ["low", "medium", "high", "critical"]
SEV_W = [0.45, 0.30, 0.17, 0.08]

# Asset role -> ATT&CK techniques that SHOULD be detectable there (C1 map).
EXPECTED_MAP = {
    "internet-facing": ["T1190", "T1133"],
    "mail-gateway": ["T1566"],
    "ad-server": ["T1003", "T1078"],
    "edr-covered": ["T1059", "T1486"],
    "db-server": ["T1021"],
    "workstation": ["T1059"],
}

NOTE_POOL = [
    "Reviewed alert, checked process tree and network connections, no malicious indicators found. Closed as benign.",
    "Correlated with threat intel feeds and EDR telemetry. Isolated host for 30 minutes, confirmed false positive.",
    "Escalated to Tier-2 after finding suspicious PowerShell encoded command. Containment initiated.",
    "Checked firewall and proxy logs for the source IP. No lateral movement observed. Documented findings.",
    "Verified with asset owner, patch applied, vulnerability confirmed remediated. Case closed with evidence.",
    "Performed timeline analysis across 6 hours of logs. Found benign admin activity. Closed with notes.",
    "Cross-checked user behaviour baseline, anomaly explained by approved change request CHG-2211.",
    "Ran AV rescan and memory dump review. No persistence found. Recommended monitoring for 7 days.",
]

COPY_PASTE_TEMPLATES = [
    "Checked logs, found nothing suspicious. Closing as false positive.",
    "Checked logs, found nothing suspicious. Closing as false positive.",
    "Reviewed and closed. No further action required.",
]

ENTITIES = ["CSE-001", "CSE-002", "CSE-003", "CSE-004", "CSE-005"]


def _assets_for(entity: str, rng: random.Random) -> pd.DataFrame:
    roles = (["internet-facing", "mail-gateway", "ad-server", "edr-covered",
              "db-server"] + ["workstation"] * 6 + ["edr-covered"] * 4)
    rows = []
    for i, role in enumerate(roles):
        aid = f"{entity}-A{i:02d}"
        if role in ("ad-server", "internet-facing", "db-server"):
            crit = "Tier-1"
        elif role in ("mail-gateway", "edr-covered"):
            crit = "Tier-2" if rng.random() < 0.5 else "Tier-1"
        else:
            crit = "Tier-3" if rng.random() < 0.7 else "Tier-2"
        rows.append({"asset_id": aid, "entity_id": entity,
                     "criticality": crit, "role": role})
    return pd.DataFrame(rows)


def generate(seed: int = 42, days: int = 60, base_date: str = "2026-06-01",
             gaming_level: float = 1.0):
    """gaming_level scales injection probabilities (0.5 = mild quarter,
    1.0 = canonical, 1.4 = deteriorating). g=1.0 reproduces the blessed
    baseline bit-for-bit (x*1.0 == x), so trend windows never disturb it."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    t0 = datetime.fromisoformat(base_date)
    sla_map = {"low": 72, "medium": 48, "high": 24, "critical": 8}  # hours

    all_alerts, all_cases, all_assets = [], [], []
    ground_truth = {}
    alert_seq = 0

    for ent in ENTITIES:
        assets = _assets_for(ent, rng)
        # CSE-004: designate silent Tier-1 assets (never emit alerts)
        silent_ids = set()
        if ent == "CSE-004":
            t1 = assets[assets.criticality == "Tier-1"]["asset_id"].tolist()
            silent_ids = set(t1[:3])
        live_assets = assets[~assets.asset_id.isin(silent_ids)]

        n = 320 if ent != "CSE-001" else 300
        # CSE-004 volume drop: log source goes DARK in the final week (blackout)
        # plus mild thinning before that — the classic dead-feed slope.
        for i in range(n):
            day_off = int(np_rng.integers(0, days))
            if ent == "CSE-004" and day_off >= days - 7:
                continue  # total blackout: no telemetry at all
            if ent == "CSE-004" and day_off >= days - 21:
                if rng.random() < min(0.70, 0.30 * gaming_level):
                    continue
            # spread intraday
            created = t0 + timedelta(days=day_off,
                                     hours=int(np_rng.integers(0, 24)),
                                     minutes=int(np_rng.integers(0, 60)))
            sev = rng.choices(SEVERITIES, weights=SEV_W)[0]
            # CSE-004 coverage gap: never emit T1566/T1003 even though it has the roles
            tech_pool = TECHNIQUES
            if ent == "CSE-004":
                tech_pool = [t for t in TECHNIQUES if t not in ("T1566", "T1003")]
            tech = rng.choice(tech_pool)
            arow = live_assets.iloc[rng.randrange(len(live_assets))]
            aid = arow["asset_id"]
            sla_h = sla_map[sev]
            deadline = created + timedelta(hours=sla_h)

            # ---- handling time + escalation per pathology ----
            esc = False
            if ent == "CSE-002":  # SLA gamer: close just inside deadline
                if rng.random() < min(0.95, 0.60 * gaming_level):
                    # close within last 5% of SLA window
                    late = deadline - timedelta(minutes=int(rng.randint(1, max(1, int(sla_h * 60 * 0.05)))))
                    closed = late
                else:
                    closed = created + timedelta(hours=float(np_rng.lognormal(1.6, 0.7)))
                    if closed > deadline:
                        closed = deadline - timedelta(minutes=rng.randint(5, 60))
                esc = rng.random() < (0.85 if sev in ("critical", "high") else 0.2)
            elif ent == "CSE-003":  # fast closer
                if sev in ("high", "critical") and rng.random() < min(0.90, 0.35 * gaming_level):
                    closed = created + timedelta(minutes=rng.randint(2, 14))
                    esc = False
                else:
                    closed = created + timedelta(hours=float(np_rng.lognormal(1.2, 0.8)))
                    esc = rng.random() < 0.5
            elif ent == "CSE-005":  # (almost) never escalates criticals
                closed = created + timedelta(hours=float(np_rng.lognormal(1.5, 0.7)))
                esc = rng.random() < (0.05 if sev in ("critical", "high") else 0.1)
            else:  # clean control / CSE-004 baseline handling
                closed = created + timedelta(hours=float(np_rng.lognormal(1.7, 0.6)))
                if closed > deadline + timedelta(hours=2):
                    closed = deadline - timedelta(hours=rng.randint(1, 4))
                if ent == "CSE-001":  # healthy SOC: escalates (almost) everything hot
                    esc = rng.random() < (0.97 if sev == "critical"
                                          else 0.90 if sev == "high" else 0.15)
                else:
                    esc = rng.random() < (0.90 if sev == "critical"
                                          else 0.6 if sev == "high" else 0.15)

            # CSE-005 repeat-asset: force a hot asset+technique cluster
            if ent == "CSE-005" and rng.random() < min(0.60, 0.18 * gaming_level):
                aid = f"{ent}-A00"
                tech = "T1059"
                esc = False

            alert_seq += 1
            alert_id = f"{ent}-AL{alert_seq:05d}"
            handling_min = (closed - created).total_seconds() / 60.0
            all_alerts.append({
                "alert_id": alert_id, "entity_id": ent, "severity": sev,
                "asset_id": aid, "technique_id": tech,
                "created_at": created.isoformat(), "closed_at": closed.isoformat(),
                "sla_hours": sla_h, "escalated": bool(esc), "status": "closed",
                "handling_minutes": round(handling_min, 1),
            })
            # ---- case note ----
            # Healthy investigators write case-specific notes (unique detail per
            # alert keeps TF-IDF similarity low); CSE-003 pastes bare templates.
            if ent == "CSE-003" and rng.random() < min(0.90, 0.45 * gaming_level):
                note = rng.choice(COPY_PASTE_TEMPLATES)
            else:
                note = (rng.choice(NOTE_POOL)
                        + f" Ref {alert_id} on {aid} [{tech}/{sev}].")
            all_cases.append({
                "case_id": f"{alert_id}-C", "entity_id": ent, "alert_id": alert_id,
                "note": note, "investigator": f"an-{rng.randint(1, 6)}",
                "closed_at": closed.isoformat(),
            })
        all_assets.append(assets)

        # ground-truth labels (stand-in for manual-review findings)
        gt = {"risky": ent != "CSE-001", "patterns": []}
        if ent == "CSE-002":
            gt["patterns"] = ["SLA-cliff-gaming"]
        elif ent == "CSE-003":
            gt["patterns"] = ["copy-paste-investigation", "fast-close"]
        elif ent == "CSE-004":
            gt["patterns"] = ["silent-tier1-assets", "attck-coverage-gap", "volume-drop"]
        elif ent == "CSE-005":
            gt["patterns"] = ["critical-no-escalation", "repeat-asset-no-remediation"]
        ground_truth[ent] = gt

    alerts = pd.DataFrame(all_alerts)
    cases = pd.DataFrame(all_cases)
    assets = pd.concat(all_assets, ignore_index=True)
    # join asset criticality/role onto alerts for convenience
    alerts = alerts.merge(assets, on=["asset_id", "entity_id"], how="left")
    return alerts, cases, assets, ground_truth, EXPECTED_MAP


def dataset_hash(alerts: pd.DataFrame, cases: pd.DataFrame, assets: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for df in (alerts, cases, assets):
        h.update(df.to_csv(index=False).encode())
    return h.hexdigest()


if __name__ == "__main__":
    a, c, ass, gt, _ = generate()
    print(a.groupby("entity_id").size())
    print(json.dumps(gt, indent=1))
