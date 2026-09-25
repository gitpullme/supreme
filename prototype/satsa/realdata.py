"""Real-data adapter (PS section 8 path).

Two jobs:
1. Map arbitrary CSE export columns -> canonical schema (alerts/cases/assets).
   Operators describe THEIR columns once in a small YAML; everything downstream
   (detectors, scoring, ledger, validation) is untouched.
2. Load past-manual-review findings (finding -> entity -> alert_ids, CSV) as
   ground truth so validate.py runs unchanged against REAL expert labels
   instead of the synthetic stand-in.
"""
from __future__ import annotations

import pandas as pd

ALERT_COLS = ["alert_id", "entity_id", "orig_severity", "severity", "asset_id",
              "technique_id", "created_at", "closed_at", "sla_hours",
              "escalated", "status", "handling_minutes", "analyst",
              "reported_minutes", "criticality", "role"]
CASE_COLS = ["case_id", "entity_id", "alert_id", "note", "investigator", "closed_at"]
ASSET_COLS = ["asset_id", "entity_id", "criticality", "role", "status"]
HANDOFF_COLS = ["handoff_id", "alert_id", "entity_id", "analyst", "ts"]
ESC_COLS = ["esc_id", "alert_id", "entity_id", "actor",
            "opened_at", "closed_at", "outcome"]


def map_columns(df: pd.DataFrame, mapping: dict, required: list) -> pd.DataFrame:
    """mapping: {canonical_name: source_column}. Fills documented defaults
    for fields a CSE cannot provide (logged by the caller into the ledger)."""
    out = pd.DataFrame()
    for canon in required:
        if canon in mapping:
            out[canon] = df[mapping[canon]]
        else:
            out[canon] = _default(canon, len(df))
    if "handling_minutes" in required and "handling_minutes" not in mapping:
        out["handling_minutes"] = (
            pd.to_datetime(out["closed_at"], format="mixed")
            - pd.to_datetime(out["created_at"], format="mixed")
        ).dt.total_seconds() / 60.0
    if "orig_severity" in required and "orig_severity" not in mapping:
        out["orig_severity"] = out["severity"]  # no downgrade history: assume as-seen
    if "reported_minutes" in required and "reported_minutes" not in mapping:
        out["reported_minutes"] = out["handling_minutes"]
    out["escalated"] = out["escalated"].astype(bool)
    return out


def _default(col: str, n: int):
    import numpy as np
    return {
        "technique_id": "UNKNOWN", "criticality": "Tier-3", "role": "workstation",
        "sla_hours": 24, "escalated": False, "status": "closed",
        "investigator": "unknown", "analyst": "unknown", "note": "",
        "outcome": "genuine",
    }.get(col, np.nan)


def attach_assets(alerts: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    """Join inventory criticality/role onto alerts (detectors read them there)."""
    a = alerts.drop(columns=[c for c in ("criticality", "role") if c in alerts.columns])
    return a.merge(assets[["asset_id", "entity_id", "criticality", "role"]].drop_duplicates(),
                   on=["asset_id", "entity_id"], how="left")


def load_manual_findings(path: str) -> dict:
    """CSV with columns: entity_id, pattern, alert_ids (semicolon-separated, optional).
    Returns the same ground_truth shape the generator emits:
    {entity: {"risky": bool, "patterns": [...]}}."""
    df = pd.read_csv(path)
    gt: dict = {}
    for _, r in df.iterrows():
        ent = str(r["entity_id"])
        g = gt.setdefault(ent, {"risky": True, "patterns": []})
        if str(r.get("pattern", "")).strip().lower() not in ("", "clean", "none"):
            g["patterns"].append(str(r["pattern"]))
        else:
            g["risky"] = False
    return gt


def validate_against_manual(scores: dict, flags: dict, findings_path: str,
                            top_n: int = 3) -> dict:
    """Drop-in for the synthetic harness: same metrics, real labels."""
    from .validate import validate
    return validate(scores, flags, load_manual_findings(findings_path), top_n)
