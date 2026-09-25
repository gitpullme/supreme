"""Synthetic CSE data generator with INJECTED, LABELLED gaming patterns.

Deterministic (seeded). Produces alert/case/asset/handoff/escalation tables
shaped like the periodic CSE submissions described in PS section 2, plus a
ground-truth manifest used by the validation harness as a stand-in for NCIIPC
past-manual-review findings (PS section 8).

Entities (canonical window):
  CSE-001  clean control (healthy SOC)
  CSE-002  SLA-gamer + bulk-bursts + rounded reported-times + audit-theatre
  CSE-003  copy-paste + fast-close + speed-demon analyst + hollow notes + hot-potato
  CSE-004  silent Tier-1 + coverage gaps + blackout + inventory drift + red-team miss
  CSE-005  critical-no-escalation + repeat-no-remediation + theatre + downgrades

Draw discipline: the MAIN rng streams reproduce the blessed baseline bit-for-bit
when new injections are off. Every NEW random choice consumes the SECONDARY
stream (nrng / np_rng2), so enabling a new pathology never perturbs the draws
of the old ones. Canonical call generate(seed=42, gaming_level=1.0) with all
injection flags at their defaults is the validated baseline.
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

# Techniques so rarely benign that downgrading them is itself a signal (E10).
RARELY_BENIGN = ["T1486", "T1003", "T1190"]

# Supervisory sectors for X2 meta-analysis.
SECTORS = {"CSE-001": "banking", "CSE-002": "banking", "CSE-005": "banking",
           "CSE-003": "energy", "CSE-004": "energy"}

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
ANALYSTS = [f"an-{i}" for i in range(1, 7)]


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
                     "criticality": crit, "role": role, "status": "active"})
    return pd.DataFrame(rows)


def _artifact_suffix(nrng: random.Random, alert_id: str, aid: str) -> str:
    ip = f"10.{nrng.randrange(256)}.{nrng.randrange(256)}.{nrng.randrange(1, 255)}"
    host = f"{aid.lower()}.corp"
    h = f"{nrng.getrandbits(32):08x}"
    return f" Ref {alert_id} src {ip} host {host} hash {h}."


def generate(seed: int = 42, days: int = 60, base_date: str = "2026-06-01",
             gaming_level: float = 1.0, assessment_date=None,
             inventory_drift: bool = False):
    """gaming_level scales injection probabilities (g=1.0 = canonical baseline).
    assessment_date: datetime|None — CSE-002 behaves near it (E12 theatre).
    inventory_drift: CSE-004 silently drops/adds assets (C6 drift).
    Returns (alerts, cases, assets, ground_truth, EXPECTED_MAP, extra) where
    extra = {"handoffs": df, "escalations": df}."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    # Secondary streams: new pathologies consume ONLY these (baseline preserved).
    nrng = random.Random(seed * 7919 + 13)
    np_rng2 = np.random.default_rng(seed * 104729 + 7)
    t0 = datetime.fromisoformat(base_date)
    assess = datetime.fromisoformat(assessment_date) if assessment_date else None
    sla_map = {"low": 72, "medium": 48, "high": 24, "critical": 8}  # hours

    all_alerts, all_cases, all_assets = [], [], []
    all_handoffs, all_escalations = [], []
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
        ent_alert_rows = []  # per-alert dicts for post-loop injections
        for i in range(n):
            day_off = int(np_rng.integers(0, days))
            if ent == "CSE-004" and day_off >= days - 7:
                continue  # total blackout: no telemetry at all
            if ent == "CSE-004" and day_off >= days - 21:
                if rng.random() < min(0.70, 0.30 * gaming_level):
                    continue
            created = t0 + timedelta(days=day_off,
                                     hours=int(np_rng.integers(0, 24)),
                                     minutes=int(np_rng.integers(0, 60)))
            sev = rng.choices(SEVERITIES, weights=SEV_W)[0]
            orig_sev = sev
            tech_pool = TECHNIQUES
            if ent == "CSE-004":
                tech_pool = [t for t in TECHNIQUES if t not in ("T1566", "T1003")]
            tech = rng.choice(tech_pool)
            arow = live_assets.iloc[rng.randrange(len(live_assets))]
            aid = arow["asset_id"]
            sla_h = sla_map[sev]
            deadline = created + timedelta(hours=sla_h)

            # ---- handling time + escalation per pathology (MAIN stream only) ----
            esc = False
            if ent == "CSE-002":  # SLA gamer: close just inside deadline
                late_p = min(0.95, 0.60 * gaming_level)
                if assess is not None:  # E12: behave during assessment, revert after
                    d = (created - assess).days
                    if abs(d) <= 3:
                        late_p *= 0.25
                    elif 3 < d <= 14:
                        late_p = min(0.97, late_p * 1.3)
                if rng.random() < late_p:
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
                if ent == "CSE-001":
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

            # ---- case note (draws in ORIGINAL order: note-random, note-choice) ----
            if ent == "CSE-003" and rng.random() < min(0.90, 0.45 * gaming_level):
                note = rng.choice(COPY_PASTE_TEMPLATES)
                hollow = True
            else:
                note = rng.choice(NOTE_POOL)
                hollow = False

            # Investigator draw: ORIGINAL position (after note draws) so the
            # main-rng sequence reproduces the blessed baseline bit-for-bit.
            # Alert analyst mirrors the investigator; post-loop injections
            # (speed-demon) override via the secondary stream only.
            investigator = f"an-{rng.randint(1, 6)}"
            ent_alert_rows.append({
                "alert_id": alert_id, "entity_id": ent, "orig_severity": orig_sev,
                "severity": sev, "asset_id": aid, "technique_id": tech,
                "created_at": created.isoformat(), "closed_at": closed.isoformat(),
                "sla_hours": sla_h, "escalated": bool(esc), "status": "closed",
                "handling_minutes": round(handling_min, 1),
                "analyst": investigator, "note": note, "hollow": hollow,
                "investigator": investigator, "created_dt": created,
                "closed_dt": closed,
            })

        # ================= post-loop injections (SECONDARY stream only) =================
        rows = ent_alert_rows
        by_id = {r["alert_id"]: r for r in rows}

        # -- E10 severity downgrades (CSE-005): orig critical -> final low
        if ent == "CSE-005":
            for r in rows:
                if r["orig_severity"] == "critical" and nrng.random() < 0.60:
                    r["severity"] = "low"

        # -- healthy reported_minutes; CSE-002 rounds them (X1 fabrication)
        # Both scale with gaming_level so trend windows show a real slope.
        for r in rows:
            actual = max(1.0, r["handling_minutes"])
            if ent == "CSE-002" and nrng.random() < min(0.90, 0.40 * gaming_level):
                r["reported_minutes"] = float(nrng.choice([30, 60, 90, 120, 240, 480]))
            else:
                r["reported_minutes"] = round(actual * nrng.uniform(0.9, 1.1), 1)

        # -- E7 artifacts: healthy notes cite concrete evidence; templates cite nothing
        for r in rows:
            if not r["hollow"]:
                r["note"] = r["note"] + _artifact_suffix(nrng, r["alert_id"], r["asset_id"])
                r["note"] += f" Ref {r['alert_id']} on {r['asset_id']} [{r['technique_id']}/{r['severity']}]."

        # -- E9 bulk burst (CSE-002): low/medium alerts closed inside 60 seconds.
        # Size scales with gaming_level: mild quarters stay under the flag line.
        if ent == "CSE-002":
            cands = [r for r in rows if r["orig_severity"] in ("low", "medium")]
            burst_n = int(30 * gaming_level)
            burst = nrng.sample(cands, min(burst_n, len(cands)))
            t_burst = t0 + timedelta(days=int(np_rng2.integers(5, days - 5)),
                                     hours=int(np_rng2.integers(0, 24)),
                                     minutes=int(np_rng2.integers(0, 60)),
                                     seconds=int(np_rng2.integers(0, 60)))
            for r in burst:
                r["closed_dt"] = t_burst + timedelta(seconds=int(np_rng2.integers(0, 60)))
                r["closed_at"] = r["closed_dt"].isoformat()
                r["handling_minutes"] = round((r["closed_dt"] - r["created_dt"]).total_seconds() / 60.0, 1)
                if nrng.random() < min(0.90, 0.40 * gaming_level):
                    r["reported_minutes"] = float(nrng.choice([30, 60, 90, 120, 240, 480]))

        # -- E6 speed-demon analyst (CSE-003): an-9 "investigates" a shift-load
        # of hot alerts. Load scales with gaming_level (mild quarter: under ceiling).
        # Sampled ONLY from alerts created before the shift, so all N land in ONE
        # analyst-shift cell deterministically (no created>closed spillover).
        if ent == "CSE-003":
            # Fixed late-window shift: nearly all hot alerts predate it, so the
            # full demon load always lands in ONE analyst-shift cell.
            shift_start = t0 + timedelta(days=days - 10, hours=8)
            eligible = [r for r in rows
                        if r["orig_severity"] in ("high", "critical")
                        and r["created_dt"] <= shift_start]
            demon = nrng.sample(eligible, min(int(45 * gaming_level), len(eligible)))
            for r in demon:
                r["analyst"] = "an-9"
                r["investigator"] = "an-9"
                r["closed_dt"] = shift_start + timedelta(minutes=int(np_rng2.integers(0, 480)))
                r["closed_at"] = r["closed_dt"].isoformat()
                r["handling_minutes"] = round((r["closed_dt"] - r["created_dt"]).total_seconds() / 60.0, 1)

        # -- E11 hot-potato handoffs (CSE-003): 12 alerts bounced across 4-5 analysts
        hot_potatoes = set()
        if ent == "CSE-003":
            hot_potatoes = {r["alert_id"] for r in nrng.sample(rows, min(12, len(rows)))}
        for r in rows:
            if r["alert_id"] in hot_potatoes:
                others = nrng.sample([a for a in ANALYSTS + ["an-9"] if a != r["analyst"]],
                                     nrng.randint(3, 4))
                chain = [r["analyst"]] + others
                base = r["closed_dt"] - timedelta(minutes=20)
                for k, a in enumerate(chain):
                    all_handoffs.append({
                        "handoff_id": f"{r['alert_id']}-H{k}", "alert_id": r["alert_id"],
                        "entity_id": ent, "analyst": a,
                        "ts": (base + timedelta(minutes=k * 5)).isoformat()})
            else:
                all_handoffs.append({
                    "handoff_id": f"{r['alert_id']}-H0", "alert_id": r["alert_id"],
                    "entity_id": ent, "analyst": r["analyst"],
                    "ts": r["created_at"]})
                if nrng.random() < 0.20:  # occasional genuine collaboration
                    all_handoffs.append({
                        "handoff_id": f"{r['alert_id']}-H1", "alert_id": r["alert_id"],
                        "entity_id": ent,
                        "analyst": nrng.choice([a for a in ANALYSTS if a != r["analyst"]]),
                        "ts": r["created_at"]})

        # -- escalations table: genuine rows + E8 theatre (CSE-005 self-reversals)
        theatre_ids = set()
        if ent == "CSE-005":
            cands = [r for r in rows
                     if r["orig_severity"] in ("high", "critical") and not r["escalated"]]
            for r in nrng.sample(cands, min(8, len(cands))):
                theatre_ids.add(r["alert_id"])
                opened = r["closed_dt"] - timedelta(seconds=nrng.randint(30, 90))
                all_escalations.append({
                    "esc_id": f"{r['alert_id']}-T", "alert_id": r["alert_id"],
                    "entity_id": ent, "actor": r["analyst"],
                    "opened_at": opened.isoformat(), "closed_at": r["closed_at"],
                    "outcome": "reversed"})
        for r in rows:
            if r["escalated"] and nrng.random() < 0.30 and r["alert_id"] not in theatre_ids:
                opened = r["closed_dt"] - timedelta(hours=nrng.randint(1, 72))
                all_escalations.append({
                    "esc_id": f"{r['alert_id']}-E", "alert_id": r["alert_id"],
                    "entity_id": ent, "actor": r["analyst"],
                    "opened_at": opened.isoformat(), "closed_at": r["closed_at"],
                    "outcome": "genuine"})

        # -- emit alerts/cases
        for r in rows:
            all_alerts.append({k: r[k] for k in (
                "alert_id", "entity_id", "orig_severity", "severity", "asset_id",
                "technique_id", "created_at", "closed_at", "sla_hours",
                "escalated", "status", "handling_minutes", "analyst",
                "reported_minutes")})
            all_cases.append({
                "case_id": f"{r['alert_id']}-C", "entity_id": ent,
                "alert_id": r["alert_id"], "note": r["note"],
                "investigator": r["investigator"], "closed_at": r["closed_at"]})

        # -- C6 inventory drift (CSE-004, later windows only)
        if inventory_drift and ent == "CSE-004":
            assets = assets[~assets["asset_id"].isin([f"{ent}-A02", f"{ent}-A04"])]
            assets = pd.concat([assets, pd.DataFrame([{
                "asset_id": f"{ent}-A15", "entity_id": ent,
                "criticality": "Tier-2", "role": "workstation",
                "status": "active"}])], ignore_index=True)
        all_assets.append(assets)

        # ground-truth labels (stand-in for manual-review findings)
        gt = {"risky": ent != "CSE-001", "patterns": []}
        if ent == "CSE-002":
            gt["patterns"] = ["SLA-cliff-gaming", "bulk-closure-burst",
                              "reported-time-rounding", "audit-calendar-theatre"]
        elif ent == "CSE-003":
            gt["patterns"] = ["copy-paste-investigation", "fast-close",
                              "throughput-abuse", "hollow-notes", "hot-potato"]
        elif ent == "CSE-004":
            gt["patterns"] = ["silent-tier1-assets", "attck-coverage-gap",
                              "volume-drop", "inventory-drift", "redteam-miss"]
        elif ent == "CSE-005":
            gt["patterns"] = ["critical-no-escalation", "repeat-asset-no-remediation",
                              "escalation-theatre", "severity-downgrade"]
        ground_truth[ent] = gt

    alerts = pd.DataFrame(all_alerts)
    cases = pd.DataFrame(all_cases)
    assets = pd.concat(all_assets, ignore_index=True)
    handoffs = pd.DataFrame(all_handoffs)
    escalations = pd.DataFrame(all_escalations)
    # join asset criticality/role onto alerts (status lives only on inventory)
    alerts = alerts.merge(assets[["asset_id", "entity_id", "criticality", "role"]],
                          on=["asset_id", "entity_id"], how="left")
    extra = {"handoffs": handoffs, "escalations": escalations}
    return alerts, cases, assets, ground_truth, EXPECTED_MAP, extra


def dataset_hash(alerts: pd.DataFrame, cases: pd.DataFrame, assets: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for df in (alerts, cases, assets):
        h.update(df.to_csv(index=False).encode())
    return h.hexdigest()


if __name__ == "__main__":
    a, c, ass, gt, _, extra = generate()
    print(a.groupby("entity_id").size())
    print(json.dumps(gt, indent=1))
    print({k: len(v) for k, v in extra.items()})
