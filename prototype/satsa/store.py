"""DuckDB ingestion: CSV/JSON/DB-export -> normalised analytical tables.

Tables: alerts, cases, assets, handoffs, escalations. Every ingestion event
returns a SHA-256 hash of the canonical payload for the audit ledger
(PS REQ 11-14).
"""
from __future__ import annotations

import hashlib
import os

import pandas as pd

SCHEMA = {
    "alerts": ["alert_id", "entity_id", "orig_severity", "severity", "asset_id",
               "technique_id", "created_at", "closed_at", "sla_hours",
               "escalated", "status", "handling_minutes", "analyst",
               "reported_minutes", "criticality", "role"],
    "cases": ["case_id", "entity_id", "alert_id", "note", "investigator", "closed_at"],
    "assets": ["asset_id", "entity_id", "criticality", "role", "status"],
    "handoffs": ["handoff_id", "alert_id", "entity_id", "analyst", "ts"],
    "escalations": ["esc_id", "alert_id", "entity_id", "actor",
                    "opened_at", "closed_at", "outcome"],
}


def canonical_hash(alerts: pd.DataFrame, cases: pd.DataFrame,
                    assets: pd.DataFrame, handoffs=None,
                    escalations=None) -> str:
    h = hashlib.sha256()
    frames = [("alerts", alerts), ("cases", cases), ("assets", assets)]
    if handoffs is not None:
        frames.append(("handoffs", handoffs))
    if escalations is not None:
        frames.append(("escalations", escalations))
    for name, df in frames:
        canon = df.sort_index(axis=1).sort_values(
            by=list(df.columns), kind="mergesort").to_csv(index=False)
        h.update(name.encode() + canon.encode())
    return h.hexdigest()


def init_and_ingest(db_path: str, alerts: pd.DataFrame, cases: pd.DataFrame,
                    assets: pd.DataFrame, handoffs=None,
                    escalations=None) -> str:
    """Write DataFrames into DuckDB (overwrite). Returns ingestion hash."""
    import duckdb
    if os.path.exists(db_path):
        os.remove(db_path)
    con = duckdb.connect(db_path)
    try:
        frames = [("alerts", alerts), ("cases", cases), ("assets", assets)]
        if handoffs is not None:
            frames.append(("handoffs", handoffs))
        if escalations is not None:
            frames.append(("escalations", escalations))
        for name, df in frames:
            con.execute(f"DROP TABLE IF EXISTS {name}")
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM df")
    finally:
        con.close()
    return canonical_hash(alerts, cases, assets, handoffs, escalations)


def load_frames(db_path: str):
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    try:
        alerts = con.execute("SELECT * FROM alerts").df()
        cases = con.execute("SELECT * FROM cases").df()
        assets = con.execute("SELECT * FROM assets").df()
    finally:
        con.close()
    return alerts, cases, assets


def load_csv_dir(directory: str):
    """REQ 2 path: ingest CSV exports (alerts.csv, cases.csv, assets.csv)."""
    alerts = pd.read_csv(os.path.join(directory, "alerts.csv"))
    cases = pd.read_csv(os.path.join(directory, "cases.csv"))
    assets = pd.read_csv(os.path.join(directory, "assets.csv"))
    return alerts, cases, assets
