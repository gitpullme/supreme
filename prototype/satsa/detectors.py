"""Detection engines. Every flag carries rule_id + evidence record IDs.

Execution-gap engine (E1-E5, +E6 folded into E3 technique tag):
  E1 SLA-cliff clustering        [SAT-E1]
  E2 escalation-logic violation  [SAT-E2]
  E3 fast-close high/critical    [SAT-E3] (+ technique tag = E6 [SAT-E6])
  E4 copy-paste notes (TF-IDF cosine; MiniLM drop-in later) [SAT-E4]
  E5 repeat asset+technique, no remediation [SAT-E5]
Negative-space engine (C1-C4):
  C1 ATT&CK coverage gap         [SAT-C1]
  C2 silent Tier-1 assets        [SAT-C2]
  C3 volume-drop blind spot      [SAT-C3]
  C4 peer-baseline outlier       [SAT-C4]
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kstest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import load as _load_config

# Rule pack: thresholds come from rules/detectors.yaml (audited, hashed).
# Module-level load keeps detector signatures stable; run.py logs the hash.
CFG, CFG_HASH = _load_config()

FAST_CLOSE_MIN = 15
DUP_SIM_THRESHOLD = 0.85
REPEAT_MIN = 3


def _flag(rule_id, entity, title, severity, evidence, observed, expected, records):
    return {"rule_id": rule_id, "entity_id": entity, "title": title,
            "severity": severity, "evidence": evidence,
            "observed": observed, "expected": expected,
            "records": records[:25], "n_records": len(records)}


def e1_sla_cliff(alerts: pd.DataFrame, cfg: dict | None = None):
    """Closures landing in the final 10% of the SLA window, with a
    Kolmogorov-Smirnov test of closure positions vs uniform handling.
    A deadline-driven SOC shows mass near the deadline AND rejects uniformity.
    """
    c = (cfg or CFG)["E1_sla_cliff"]
    out, signals = [], {}
    for ent, g in alerts.groupby("entity_id"):
        fracs, positions = [], []
        for _, r in g.iterrows():
            try:
                cr = pd.Timestamp(r["created_at"]); cl = pd.Timestamp(r["closed_at"])
            except Exception:
                continue
            window = float(r["sla_hours"]) * 60.0
            if window <= 0:
                continue
            remain = (cr + pd.Timedelta(hours=float(r["sla_hours"])) - cl).total_seconds() / 60.0
            fracs.append(remain / window)  # 0 = exactly at deadline
            positions.append(1.0 - remain / window)  # 1 = closed at deadline
        fracs = np.array(fracs)
        cliff_frac = float(np.mean(fracs <= c["last_window_frac"])) if len(fracs) else 0.0
        try:
            ks_d, ks_p = (float(v) for v in
                          kstest(np.clip(positions, 0, 1), "uniform")[:2]) \
                if len(positions) >= 20 else (0.0, 1.0)
        except Exception:
            ks_d, ks_p = 0.0, 1.0
        signals[ent] = {"cliff_frac": cliff_frac, "n": len(fracs),
                        "ks_D": round(ks_d, 3), "ks_p": ks_p}
        if cliff_frac > c["flag_threshold"]:
            gaming = ks_p < c["ks_alpha"]
            out.append(_flag(c["rule_id"], ent, "SLA-cliff clustering: closures pile up just before deadline",
                             "high" if cliff_frac > c["high_threshold"] else "medium",
                             f"{cliff_frac:.0%} of closures fall in the final {c['last_window_frac']:.0%} of the SLA window "
                             f"(honest handling would be ~{c['last_window_frac']:.0%}). "
                             f"KS vs uniform: D={ks_d:.2f}, p={ks_p:.2g} "
                             f"({'rejects uniformity — deadline-driven' if gaming else 'supporting view only'}). "
                             "Classic metric-gaming signature.",
                             f"{cliff_frac:.1%} in last-{c['last_window_frac']:.0%} window; KS p={ks_p:.2g}",
                             f"~{c['last_window_frac']:.0%} expected",
                             g["alert_id"].tolist()))
    return out, signals


def e2_escalation_violation(alerts: pd.DataFrame, cfg: dict | None = None):
    c = (cfg or CFG)["E2_escalation_violation"]
    out, signals = [], {}
    for ent, g in alerts.groupby("entity_id"):
        crit = g[(g.severity.isin(c["severities"])) &
                 (g.criticality == c["tier"]) & (~g.escalated.astype(bool))]
        denom = max(1, len(g[(g.severity.isin(c["severities"])) & (g.criticality == c["tier"])]))
        rate = len(crit) / denom
        signals[ent] = {"esc_violation_rate": rate, "esc_violations": len(crit)}
        # Isolated one-offs happen; a *pattern* of un-escalated criticals is the signal.
        if len(crit) >= c["min_violations"] and rate > c["min_rate"]:
            sev = "critical" if (crit.severity == "critical").any() and rate > 0.3 else "high"
            out.append(_flag(c["rule_id"], ent, "Critical/High on Tier-1 closed without escalation",
                             sev,
                             f"{len(crit)} critical/high alerts on Tier-1 assets have no escalation record.",
                             f"{rate:.0%} un-escalated ({len(crit)}/{denom})",
                             "critical on Tier-1 must be escalated",
                             crit["alert_id"].tolist()))
    return out, signals


def e3_fast_close(alerts: pd.DataFrame, cfg: dict | None = None):
    c = (cfg or CFG)["E3_fast_close"]
    out, signals = [], {}
    for ent, g in alerts.groupby("entity_id"):
        hc = g[g.severity.isin(["high", "critical"])]
        fast = hc[hc.handling_minutes <= c["fast_close_min"]]
        rate = len(fast) / max(1, len(hc))
        signals[ent] = {"fast_close_rate": rate, "fast_close_n": len(fast)}
        if len(fast):
            tags = ", ".join(sorted(fast.technique_id.unique())[:4])
            out.append(_flag(c["rule_id"], ent, f"High-severity alerts closed in <= {c['fast_close_min']} min",
                             "high" if rate > c["high_rate_threshold"] else "medium",
                             f"{len(fast)} high/critical alerts closed within {c['fast_close_min']} minutes with no meaningful investigation window. ATT&CK tags: {tags}.",
                             f"{rate:.0%} fast-closed ({len(fast)}/{len(hc)})",
                             "high-severity investigation normally takes hours",
                             fast["alert_id"].tolist()))
    return out, signals


def e4_duplicate_notes(cases: pd.DataFrame, cfg: dict | None = None):
    c = (cfg or CFG)["E4_duplicate_notes"]
    from .embeddings import similarity_matrix  # local-embedding adapter (TF-IDF default)
    out, signals = [], {}
    for ent, g in cases.groupby("entity_id"):
        notes = g[["case_id", "note"]].drop_duplicates("case_id")
        if len(notes) < 5:
            signals[ent] = {"dup_rate": 0.0, "dup_pairs": 0}
            continue
        try:
            sim = similarity_matrix(notes.note.tolist(), method=c["method"],
                                    threshold=c["sim_threshold"])
            np.fill_diagonal(sim, 0.0)
            iu = np.triu_indices(len(notes), 1)
            dup_pairs = int(np.sum(sim[iu] >= c["sim_threshold"]))
            hit_rows = set()
            for i, j in zip(*np.where(np.triu(sim >= c["sim_threshold"], 1))):
                hit_rows.add(notes.iloc[i].case_id)
                hit_rows.add(notes.iloc[j].case_id)
            rate = len(hit_rows) / len(notes)
        except ValueError:
            dup_pairs, rate, hit_rows = 0, 0.0, set()
        signals[ent] = {"dup_rate": float(rate), "dup_pairs": dup_pairs}
        if dup_pairs and rate > c["min_rate"]:
            out.append(_flag(c["rule_id"], ent, "Template-driven investigations: near-duplicate case notes",
                             "high" if rate > 0.3 else "medium",
                             f"{dup_pairs} near-duplicate note pairs (cosine >= {c['sim_threshold']}, {c['method']}) across different cases — copy-paste investigation signature.",
                             f"{rate:.0%} of cases share near-identical notes",
                             "independent investigations should read differently",
                             sorted(hit_rows)))
    return out, signals


def e5_repeat_asset(alerts: pd.DataFrame, cfg: dict | None = None):
    c = (cfg or CFG)["E5_repeat_asset"]
    out, signals = [], {}
    for ent, g in alerts.groupby("entity_id"):
        grp = g.groupby(["asset_id", "technique_id"])
        hits_hot, hits_vol = [], []
        for k, v in grp:
            n_hot = int(v.severity.isin(["high", "critical"]).sum())
            if len(v) < c["repeat_min"] or v.escalated.astype(bool).any():
                continue
            # Hot pattern = recurring failure on the SAME weakness with no learning.
            if n_hot >= c["min_hot"]:
                hits_hot.append(k)
            elif len(v) >= c["vol_min"]:
                hits_vol.append(k)  # all-low volume recurrence: hygiene note only
        signals[ent] = {"repeat_groups": len(hits_hot)}
        if hits_hot:
            recs = g.set_index(["asset_id", "technique_id"]).loc[
                pd.MultiIndex.from_tuples(hits_hot)].reset_index()["alert_id"].tolist()
            out.append(_flag(c["rule_id"], ent, "Repeat alerts, same asset+technique, no remediation",
                             "high" if len(hits_hot) >= c["high_groups_threshold"] else "medium",
                             f"{len(hits_hot)} hot (asset, technique) pairs re-fired >= {c['repeat_min']}x "
                             f"with >= {c['min_hot']} high/critical and zero escalation/remediation — root cause never addressed."
                             + (f" (+{len(hits_vol)} low-severity volume recurrences)" if hits_vol else ""),
                             f"{len(hits_hot)} unremediated hot repeat clusters", "0 expected",
                             recs))
    return out, signals


def c1_coverage_gap(alerts: pd.DataFrame, assets: pd.DataFrame, expected_map: dict):
    out, signals = [], {}
    obs = alerts.groupby("entity_id").technique_id.apply(set).to_dict()
    for ent, ag in assets.groupby("entity_id"):
        roles = set(ag.role.unique())
        expected = set()
        for r in roles:
            expected.update(expected_map.get(r, []))
        seen = obs.get(ent, set())
        gaps = sorted(expected - seen)
        signals[ent] = {"coverage_gaps": gaps, "coverage_gap_frac":
                        (len(gaps) / max(1, len(expected)))}
        if gaps:
            out.append(_flag("SAT-C1", ent, "ATT&CK coverage gap: expected technique never observed",
                             "high" if len(gaps) >= 2 else "medium",
                             f"Asset inventory implies detectability of {sorted(expected)}, but {gaps} never fired once — monitoring blind spot (DeTT&CT-style reasoning, supervisory use).",
                             f"never observed: {gaps}", f"expected: {sorted(expected)}", []))
    return out, signals


def c2_silent_assets(alerts: pd.DataFrame, assets: pd.DataFrame):
    out, signals = [], {}
    counts = alerts.groupby(["entity_id", "asset_id"]).size().to_dict()
    for ent, ag in assets.groupby("entity_id"):
        t1 = ag[ag.criticality == "Tier-1"]
        silent = [r.asset_id for _, r in t1.iterrows()
                  if (ent, r.asset_id) not in counts]
        frac = len(silent) / max(1, len(t1))
        signals[ent] = {"silent_tier1": silent, "silent_tier1_frac": frac}
        if silent:
            out.append(_flag("SAT-C2", ent, "Silent critical assets: Tier-1 with zero telemetry",
                             "critical" if len(silent) >= 2 else "high",
                             f"{len(silent)} Tier-1 assets generated ZERO alerts over the full window: {silent}.",
                             f"{len(silent)} silent Tier-1 / {len(t1)}", "0 silent Tier-1 expected",
                             []))
    return out, signals


def c3_volume_drop(alerts: pd.DataFrame):
    out, signals = [], {}
    a = alerts.copy()
    a["day"] = pd.to_datetime(a["created_at"]).dt.date
    full_idx = pd.date_range(pd.to_datetime(a["created_at"]).min().date(),
                             pd.to_datetime(a["created_at"]).max().date(), freq="D").date
    for ent, g in a.groupby("entity_id"):
        # Reindex over the FULL calendar window: blackout days count as zeros
        # (groupby alone would silently drop them — exactly the wrong thing here).
        daily = g.groupby("day").size().reindex(full_idx, fill_value=0).sort_index()
        if len(daily) < 20:
            signals[ent] = {"drop_z": 0.0, "blind_spot": False}
            continue
        base, recent = daily.iloc[:-7], daily.iloc[-7:]
        mu, sd = float(base.mean()), float(base.std() or 1.0)
        z = (float(recent.mean()) - mu) / sd
        blind = bool(z < -1.75)
        signals[ent] = {"drop_z": round(z, 2), "blind_spot": blind}
        if blind:
            out.append(_flag("SAT-C3", ent, "Time-series blind spot: unexplained volume drop",
                             "high",
                             f"Alert volume in the last 7 days is {z:.1f} sigma below baseline (often a dead log source).",
                             f"z = {z:.2f} vs trailing baseline", "z within ±1.75",
                             []))
    return out, signals


def c4_peer_outlier(alerts: pd.DataFrame):
    out, signals = [], {}
    vol = alerts.groupby("entity_id").size()
    mu, sd = float(vol.mean()), float(vol.std() or 1.0)
    for ent, v in vol.items():
        z = (v - mu) / sd
        signals[ent] = {"peer_z": round(float(z), 2), "volume": int(v),
                        "peer_mean": round(mu, 1)}
        if abs(z) > 1.5:
            out.append(_flag("SAT-C4", ent, "Peer-baseline outlier: activity outside peer norms",
                             "medium",
                             f"Entity volume {v} vs peer mean {mu:.0f} (z = {z:+.2f}). "
                             "Suspiciously low OR high vs comparable entities.",
                             f"volume {v}, z = {z:+.2f}", f"peer mean {mu:.0f}",
                             []))
    return out, signals


def run_all_detectors(alerts, cases, assets, expected_map, cfg=None):
    """Returns (flags_by_entity, signals_by_entity). cfg = rule pack (YAML-loaded)."""
    cfg = cfg or CFG
    collectors = [
        e1_sla_cliff(alerts, cfg), e2_escalation_violation(alerts, cfg),
        e3_fast_close(alerts, cfg), e4_duplicate_notes(cases, cfg),
        e5_repeat_asset(alerts, cfg), c1_coverage_gap(alerts, assets, expected_map),
        c2_silent_assets(alerts, assets), c3_volume_drop(alerts),
        c4_peer_outlier(alerts),
    ]
    flags, signals = {}, {}
    for flist, slist in collectors:
        for f in flist:
            flags.setdefault(f["entity_id"], []).append(f)
        for ent, s in slist.items():
            signals.setdefault(ent, {}).update(s)
    return flags, signals
