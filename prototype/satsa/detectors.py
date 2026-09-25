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
    # ORIGINAL severity: quietly downgrading a critical (E10) must not hide it here.
    for ent, g in alerts.groupby("entity_id"):
        sev = g["orig_severity"] if "orig_severity" in g else g["severity"]
        is_hot = sev.isin(c["severities"])
        crit = g[is_hot & (g.criticality == c["tier"]) & (~g.escalated.astype(bool))]
        denom = max(1, int((is_hot & (g.criticality == c["tier"])).sum()))
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
            if len(v) < c["repeat_min"]:
                continue
            # Remediation means the pair STOPS: <10% ever escalated counts as
            # unremediated (a lone escalation among dozens of repeat firings
            # is not a fix — same doctrine as C5 decay).
            if v.escalated.astype(bool).mean() >= 0.10:
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
                             f"with >= {c['min_hot']} high/critical and <10% ever escalated — root cause never addressed."
                             + (f" (+{len(hits_vol)} low-severity volume recurrences)" if hits_vol else ""),
                             f"{len(hits_hot)} unremediated hot repeat clusters", "0 expected",
                             recs))
    return out, signals


def _sector_dark_spots(alerts: pd.DataFrame, assets: pd.DataFrame,
                       expected_map: dict, sectors: dict | None,
                       min_expecting: int = 2) -> dict:
    """Techniques expected by >=min_expecting entities' roles but observed by
    NONE of them. These are sector dark spots (X2), NOT entity gaps (C1) —
    flagging one entity for what nobody can see would be a false positive."""
    if not sectors:
        return {}
    obs = alerts.groupby("entity_id").technique_id.apply(set).to_dict()
    ent_roles = assets.groupby("entity_id").role.apply(set).to_dict()
    ent_expected = {e: {t for r in roles for t in expected_map.get(r, [])}
                    for e, roles in ent_roles.items()}
    dark: dict = {}  # (sector, technique) -> [expecting entities]
    sec_ents: dict = {}
    for e, s in sectors.items():
        sec_ents.setdefault(s, []).append(e)
    for s, ents in sec_ents.items():
        for t in sorted({t for e in ents for t in ent_expected.get(e, set())}):
            expecting = [e for e in ents if t in ent_expected.get(e, set())]
            if len(expecting) >= min_expecting and not any(
                    t in obs.get(e, set()) for e in ents):
                dark[(s, t)] = expecting
    return dark


def c1_coverage_gap(alerts: pd.DataFrame, assets: pd.DataFrame, expected_map: dict,
                    cfg: dict | None = None, sectors: dict | None = None):
    out, signals = [], {}
    dark = _sector_dark_spots(alerts, assets, expected_map, sectors)
    dark_by_ent = {}
    for (s, t), ents in dark.items():
        for e in ents:
            dark_by_ent.setdefault(e, set()).add(t)
    obs = alerts.groupby("entity_id").technique_id.apply(set).to_dict()
    for ent, ag in assets.groupby("entity_id"):
        roles = set(ag.role.unique())
        expected = set()
        for r in roles:
            expected.update(expected_map.get(r, []))
        seen = obs.get(ent, set())
        # Only ACTIONABLE gaps count: the technique must be observed by >=1 peer
        # (proves detectability in this cohort). Sector-wide darkness is X2.
        peers_seen = set()
        for e2, s2 in obs.items():
            if e2 != ent:
                peers_seen |= s2
        gaps = sorted((expected - seen - dark_by_ent.get(ent, set())) & peers_seen)
        actionable = (expected - dark_by_ent.get(ent, set()))
        signals[ent] = {"coverage_gaps": gaps, "coverage_gap_frac":
                        (len(gaps) / max(1, len(actionable)))}
        if gaps:
            out.append(_flag("SAT-C1", ent, "ATT&CK coverage gap: expected technique never observed",
                             "high" if len(gaps) >= 2 else "medium",
                             f"Asset inventory implies detectability of {sorted(expected)}, but {gaps} never fired once — while peers DO observe them (detectability proven). Sector-dark techniques are reported as X2, not here.",
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


def _orig(a: pd.DataFrame) -> pd.Series:
    return a["orig_severity"] if "orig_severity" in a else a["severity"]


# ================= extended execution-gap forensics (SAT-E6..E12) =================

def e6_throughput(alerts: pd.DataFrame, cfg: dict | None = None):
    """Throughput Implausibility: hot closures per analyst-shift vs ceiling."""
    c = (cfg or CFG)["E6_throughput"]
    out, signals = [], {}
    a = alerts.copy()
    a["closed"] = pd.to_datetime(a["closed_at"], format="mixed")
    a["shift"] = (a["closed"].dt.date.astype(str) + "-S"
                  + (a["closed"].dt.hour // c["shift_hours"]).astype(str))
    hot = a[_orig(a).isin(["high", "critical"])]
    cell = hot.groupby(["entity_id", "analyst", "shift"]).size()
    worst: dict = {}
    for (ent, analyst, shift), n in cell.items():
        r = n / c["max_hot_per_shift"]
        if r > worst.get(ent, (0,))[0]:
            worst[ent] = (r, analyst, shift, int(n))
    for ent in a.entity_id.unique():
        ratio = worst.get(ent, (0.0, "", "", 0))[0]
        signals[ent] = {"throughput_ratio": round(float(ratio), 2)}
        if ratio > 1.0:
            _, analyst, shift, n = worst[ent]
            recs = hot[(hot.entity_id == ent) & (hot.analyst == analyst)
                       & (hot.shift == shift)]["alert_id"].tolist()
            out.append(_flag(c["rule_id"], ent, "Throughput implausibility: superhuman closure volume",
                             "high",
                             f"Analyst {analyst} closed {n} high/critical alerts in one {c['shift_hours']}h shift "
                             f"(ceiling {c['max_hot_per_shift']}) — no human investigates at that rate.",
                             f"{n} hot closures/shift (ratio {ratio:.1f}x)", f"<= {c['max_hot_per_shift']}/shift",
                             recs))
    return out, signals


_ARTIFACT_RES = []
def _artifact_res():
    import re
    global _ARTIFACT_RES
    if not _ARTIFACT_RES:
        _ARTIFACT_RES = [
            re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),          # IPv4
            re.compile(r"\b[0-9a-f]{16,64}\b", re.I),            # hash
            re.compile(r"\bCVE-\d{4}-\d+\b", re.I),              # CVE
            re.compile(r"\bT\d{4}\b"),                           # ATT&CK ID
            re.compile(r"\b(?:AL\d{4,}|ALT-\d+)\b"),             # alert ref
            re.compile(r"\b[a-z0-9][a-z0-9\-]*\.corp\b", re.I),  # hostname
            re.compile(r"\bCHG-\d+\b", re.I),                    # change record
        ]
    return _ARTIFACT_RES


def count_artifacts(note: str) -> int:
    return sum(1 for rx in _artifact_res() if rx.search(note or ""))


def e7_evidentiary_density(alerts: pd.DataFrame, cases: pd.DataFrame,
                           cfg: dict | None = None):
    """Evidentiary Density: orig-hot notes with zero technical artifacts = hollow."""
    c = (cfg or CFG)["E7_evidentiary_density"]
    out, signals = [], {}
    hot_ids = set(alerts[_orig(alerts).isin(["high", "critical"])]["alert_id"])
    for ent, g in cases.groupby("entity_id"):
        hot = g[g.alert_id.isin(hot_ids)]
        hollow = [r.case_id for _, r in hot.iterrows()
                  if count_artifacts(r["note"]) < c["min_artifacts"]]
        rate = len(hollow) / max(1, len(hot))
        signals[ent] = {"hollow_rate": round(rate, 3), "hollow_n": len(hollow)}
        if len(hot) >= c["min_hot_notes"] and rate > c["hollow_rate_threshold"]:
            out.append(_flag(c["rule_id"], ent, "Evidentiarily hollow investigations",
                             "high" if rate > 0.4 else "medium",
                             f"{len(hollow)}/{len(hot)} high-severity notes cite ZERO technical artifacts "
                             "(no IP, hash, hostname, CVE, alert ref) — polished prose referencing nothing concrete.",
                             f"{rate:.0%} hollow hot notes", "concrete evidence per hot note",
                             hollow))
    return out, signals


def e8_escalation_theatre(escalations: pd.DataFrame | None, cfg: dict | None = None):
    """Escalation Theatre: same-actor open->reverse inside the 2-minute window."""
    c = (cfg or CFG)["E8_escalation_theatre"]
    out, signals = [], {}
    if escalations is None or len(escalations) == 0:
        return out, signals
    e = escalations.copy()
    e["dur_s"] = (pd.to_datetime(e["closed_at"], format="mixed")
                  - pd.to_datetime(e["opened_at"], format="mixed")).dt.total_seconds()
    for ent, g in e.groupby("entity_id"):
        theat = g[(g.outcome == "reversed") & (g.dur_s <= c["reverse_window_sec"])]
        rate = len(theat) / max(1, len(g))
        signals[ent] = {"theatre_rate": round(rate, 3), "theatre_n": len(theat)}
        if len(theat) >= c["min_events"]:
            out.append(_flag(c["rule_id"], ent, "Escalation theatre: performative self-reversals",
                             "high",
                             f"{len(theat)} escalations opened and reversed by the same actor within "
                             f"{c['reverse_window_sec']}s — compliance checkbox, not incident response.",
                             f"{len(theat)} reversed <={c['reverse_window_sec']}s", "escalations trigger response",
                             theat["esc_id"].tolist()))
    return out, signals


def e9_bulk_burst(alerts: pd.DataFrame, cfg: dict | None = None):
    """Bulk-Closure Burst: sliding 60s window over closure timestamps."""
    c = (cfg or CFG)["E9_bulk_burst"]
    out, signals = [], {}
    a = alerts.copy()
    # Resolution-proof epoch seconds: pandas may return datetime64[us/ms/s]
    # (NOT ns) for mixed ISO strings, where .astype(int64) is NOT nanoseconds.
    # Timedelta floor-division is exact at every resolution.
    a["cts"] = ((pd.to_datetime(a["closed_at"], format="mixed")
                 - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy()
    W = c["window_sec"]
    for ent, g in a.groupby("entity_id"):
        t = np.sort(g["cts"].to_numpy())
        best, best_j = 0, 0
        j = 0
        for i in range(len(t)):
            j = max(j, i)
            while j + 1 < len(t) and t[j + 1] - t[i] <= W:
                j += 1
            if j - i + 1 > best:
                best, best_j = j - i + 1, j
        signals[ent] = {"burst_max": int(best)}
        if best >= c["min_closures"]:
            win = g[(g.cts >= t[best_j] - W) & (g.cts <= t[best_j])]
            if win.asset_id.nunique() >= c["min_assets"] and win.technique_id.nunique() >= c["min_techniques"]:
                out.append(_flag(c["rule_id"], ent, "Bulk-closure burst: mass rubber-stamping event",
                                 "high",
                                 f"{len(win)} unrelated alerts ({win.asset_id.nunique()} assets, "
                                 f"{win.technique_id.nunique()} techniques) closed inside {W}s — "
                                 "statistically impossible as genuine triage (baseline ~0.003/60s).",
                                 f"{len(win)} closures/{W}s", "isolated individual triage",
                                 win["alert_id"].tolist()))
    return out, signals


def e10_downgrade(alerts: pd.DataFrame, cfg: dict | None = None):
    """Severity Downgrade: orig-hot rarely-benign alerts closed as cold."""
    c = (cfg or CFG)["E10_downgrade"]
    out, signals = [], {}
    for ent, g in alerts.groupby("entity_id"):
        o = _orig(g)
        pool = g[o.isin(["high", "critical"]) & g.technique_id.isin(c["rarely_benign"])]
        down = pool[~pool.severity.isin(["high", "critical"])]
        rate = len(down) / max(1, len(pool))
        signals[ent] = {"downgrade_rate": round(rate, 3), "downgrades": len(down)}
        if len(down) >= c["min_downgrades"] and rate > c["min_rate"]:
            out.append(_flag(c["rule_id"], ent, "Severity downgrades deflating incident counts",
                             "high",
                             f"{len(down)}/{len(pool)} rarely-benign hot alerts ({sorted(pool.technique_id.unique())}) "
                             "were relabelled cold before closure — quietly shrinking the incident count.",
                             f"{rate:.0%} downgraded ({len(down)}/{len(pool)})",
                             "rarely-benign techniques stay hot",
                             down["alert_id"].tolist()))
    return out, signals


def e11_hot_potato(handoffs: pd.DataFrame | None, cfg: dict | None = None):
    """Hot-Potato: alerts bounced across >=4 analysts inside 90 minutes."""
    c = (cfg or CFG)["E11_hot_potato"]
    out, signals = [], {}
    if handoffs is None or len(handoffs) == 0:
        return out, signals
    h = handoffs.copy()
    h["ts"] = pd.to_datetime(h["ts"], format="mixed")
    flagged = []
    for (ent, aid), g in h.groupby(["entity_id", "alert_id"]):
        n_an = g.analyst.nunique()
        span = (g.ts.max() - g.ts.min()).total_seconds() / 60.0
        if n_an >= c["min_analysts"] and span <= c["max_span_min"]:
            flagged.append((ent, aid, n_an, round(span, 1)))
    by_ent: dict = {}
    for ent, aid, n_an, span in flagged:
        by_ent.setdefault(ent, []).append((aid, n_an, span))
    for ent in h.entity_id.unique():
        fl = by_ent.get(ent, [])
        n_alerts = h[h.entity_id == ent].alert_id.nunique()
        signals[ent] = {"hotpotato_rate": round(len(fl) / max(1, n_alerts), 3),
                        "hotpotato_cases": len(fl)}
        if len(fl) >= c["min_cases"]:
            detail = ", ".join(f"{a} ({n} analysts, {s}m)" for a, n, s in fl[:8])
            out.append(_flag(c["rule_id"], ent, "Hot-potato reassignment: ownership avoidance",
                             "medium",
                             f"{len(fl)} alerts bounced between >= {c['min_analysts']} analysts within "
                             f"{c['max_span_min']} min — passed around, not investigated: {detail}.",
                             f"{len(fl)} bounced alerts", "stable ownership",
                             [a for a, _, _ in fl]))
    return out, signals


def e12_audit_theatre(alerts: pd.DataFrame, assessment_date, cfg: dict | None = None):
    """Audit-Calendar Correlation: better during assessment week, revert after."""
    c = (cfg or CFG)["E12_audit_theatre"]
    out, signals = [], {}
    if assessment_date is None:
        for ent in alerts.entity_id.unique():
            signals[ent] = {"audit_theatre": False}
        return out, signals
    A = pd.Timestamp(assessment_date)
    W = c["window_days"]
    a = alerts.copy()
    created = pd.to_datetime(a["created_at"], format="mixed")
    closed = pd.to_datetime(a["closed_at"], format="mixed")
    window_min = a["sla_hours"].astype(float) * 60.0
    deadline = created + pd.to_timedelta(a["sla_hours"].astype(float), unit="h")
    a["late"] = (((deadline - closed).dt.total_seconds() / 60.0) / window_min) <= 0.10
    a["created"] = created
    for ent, g in a.groupby("entity_id"):
        pre = g[(g.created >= A - pd.Timedelta(days=W)) & (g.created < A - pd.Timedelta(days=3))]
        dur = g[(g.created >= A - pd.Timedelta(days=3)) & (g.created <= A + pd.Timedelta(days=3))]
        post = g[(g.created > A + pd.Timedelta(days=3)) & (g.created <= A + pd.Timedelta(days=W))]
        signals[ent] = {"audit_theatre": False}
        if min(len(pre), len(dur), len(post)) < c["min_cases"]:
            continue
        r_pre, r_dur, r_post = pre.late.mean(), dur.late.mean(), post.late.mean()
        # Relative improvement AND absolute teeth: near-zero baselines must not
        # trigger on noise (a 3% -> 0% wobble is not audit theatre).
        improved = (r_pre - r_dur) / max(r_pre, 1e-6) >= c["improvement_margin"]
        reverted = (r_post - r_dur) / max(r_post, 1e-6) >= c["improvement_margin"]
        hit = bool(improved and reverted and r_dur < r_pre
                   and r_pre >= 0.15 and (r_pre - r_dur) >= 0.10)
        signals[ent] = {"audit_theatre": hit, "audit_rates": [round(float(x), 3) for x in (r_pre, r_dur, r_post)]}
        if hit:
            out.append(_flag(c["rule_id"], ent, "Audit theatre: staged behaviour around assessment",
                             "medium",
                             f"Late-closure rate {r_pre:.0%} pre-assessment -> {r_dur:.0%} during -> {r_post:.0%} after. "
                             "Good behaviour that exists only while inspectors watch is staged, not real.",
                             f"pre {r_pre:.0%} / during {r_dur:.0%} / post {r_post:.0%}",
                             "stable behaviour across the calendar",
                             dur["alert_id"].tolist()))
    return out, signals


# ================= extended negative space (SAT-C5..C7) =================

def c5_decay(window_alerts: list, cfg: dict | None = None):
    """Remediation Decay: pair fires flat/rising across >=3 windows, never fixed."""
    c = (cfg or CFG)["C5_remediation_decay"]
    out, signals = [], {}
    if len(window_alerts) < c["min_windows"]:
        return out, signals
    counts: dict = {}
    esc_n: dict = {}
    for _, df in window_alerts:
        w = df.groupby(["entity_id", "asset_id", "technique_id"]).size()
        e = df.groupby(["entity_id", "asset_id", "technique_id"])["escalated"].sum()
        for k, n in w.items():
            counts.setdefault(k, []).append(int(n))
            esc_n[k] = esc_n.get(k, 0) + int(e[k])
    by_ent: dict = {}
    for (ent, aid, tech), series in counts.items():
        if len(series) < c["min_windows"] or sum(series) < c["min_total"]:
            continue
        slope = float(np.polyfit(range(len(series)), series, 1)[0])
        # A lone escalation among dozens of repeat firings is not remediation;
        # remediation means the pair STOPS. Threshold: <10% ever escalated.
        esc_rate = esc_n[(ent, aid, tech)] / max(1, sum(series))
        if slope >= 0 and esc_rate < 0.10:
            by_ent.setdefault(ent, []).append((aid, tech, series, round(slope, 2)))
    ents = {e for lab, df in window_alerts for e in df.entity_id.unique()}
    for ent in ents:
        hits = by_ent.get(ent, [])
        signals[ent] = {"decay_pairs": len(hits)}
        if hits:
            detail = ", ".join(f"{a}/{t} counts={s}" for a, t, s, _ in hits[:6])
            recs = []
            for _, df in window_alerts:
                recs += df[(df.entity_id == ent)
                           & df.apply(lambda r: (r.asset_id, r.technique_id) in {(a, t) for a, t, _, _ in hits},
                                      axis=1)]["alert_id"].tolist()
            out.append(_flag(c["rule_id"], ent, "Remediation decay: acknowledged, never fixed",
                             "high",
                             f"{len(hits)} alert-asset pairs keep firing flat/rising across {len(window_alerts)} windows "
                             f"with zero remediation — the fix never happened: {detail}.",
                             f"{len(hits)} undecayed pairs", "post-fix decline",
                             recs))
    return out, signals


def c6_drift(window_assets: list, window_alerts: list, cfg: dict | None = None):
    """Inventory Drift: vanished-without-paperwork + unmonitored-new assets."""
    c = (cfg or CFG)["C6_inventory_drift"]
    out, signals = [], {}
    if len(window_assets) < 2:
        return out, signals
    by_ent: dict = {}
    for (lab0, prev), (lab1, cur) in zip(window_assets[:-1], window_assets[1:]):
        _, cur_alerts = window_alerts[[l for l, _ in window_alerts].index(lab1)]
        cur_seen = set(cur_alerts.asset_id.unique())
        for ent in set(prev.entity_id.unique()) | set(cur.entity_id.unique()):
            p = prev[prev.entity_id == ent]
            q = cur[cur.entity_id == ent]
            p_ids = set(p[p.status != "decommissioned"]["asset_id"])
            q_ids = set(q["asset_id"])
            vanished = sorted(p_ids - q_ids)
            new = sorted((q_ids - p_ids) - cur_seen)
            if vanished or new:
                by_ent.setdefault(ent, {"vanished": set(), "new": set()})
                by_ent[ent]["vanished"].update(vanished)
                by_ent[ent]["new"].update(new)
    ents = {e for _, df in window_assets for e in df.entity_id.unique()}
    for ent in ents:
        v = sorted(by_ent.get(ent, {}).get("vanished", set()))
        n = sorted(by_ent.get(ent, {}).get("new", set()))
        signals[ent] = {"drift_vanished": v, "drift_new": n,
                        "drift_n": len(v) + len(n)}
        if v or n:
            parts = []
            if v:
                parts.append(f"vanished without decommission record: {v}")
            if n:
                parts.append(f"new with zero monitoring: {n}")
            out.append(_flag(c["rule_id"], ent, "Asset inventory drift: scope evasion or monitoring lag",
                             "high" if v else "medium",
                             "; ".join(parts) + ".",
                             f"{len(v)} vanished + {len(n)} unmonitored-new", "stable, papered inventory",
                             []))
    return out, signals


def c7_redteam(alerts: pd.DataFrame, exercises: list, cfg: dict | None = None):
    """Red-Team Reconciliation: known attack, zero alerts = proven blind spot."""
    c = (cfg or CFG)["C7_redteam"]
    out, signals = [], {}
    misses: dict = {}
    for ex in exercises or []:
        g = alerts[(alerts.entity_id == ex["entity_id"])
                   & (alerts.technique_id == ex["technique_id"])
                   & (pd.to_datetime(alerts["created_at"], format="mixed") >= pd.Timestamp(ex["start"]))
                   & (pd.to_datetime(alerts["created_at"], format="mixed") < pd.Timestamp(ex["end"]))]
        if len(g) == 0:
            misses.setdefault(ex["entity_id"], []).append(ex)
    for ent in alerts.entity_id.unique():
        m = misses.get(ent, [])
        signals[ent] = {"redteam_miss": bool(m)}
        for ex in m:
            out.append(_flag(c["rule_id"], ent, "Red-team miss: confirmed attack, zero alerts",
                             "critical",
                             f"NCIIPC exercise {ex['id']} ran {ex['technique_id']} against this entity "
                             f"({ex['start']}..{ex['end']}) and the submission shows NOTHING — "
                             "ground-truth-validated detection gap, not inference.",
                             "0 alerts for a confirmed attack", ">=1 alert expected",
                             []))
    return out, signals


# ================= meta-level forensics (SAT-X1, X2) =================

def x1_digit_forensics(alerts: pd.DataFrame, cfg: dict | None = None):
    """Digit Forensics: round-number clustering + Benford chi-square on
    reported_minutes. Catches smoothed/fabricated submissions."""
    from scipy.stats import chisquare
    c = (cfg or CFG)["X1_digit_forensics"]
    out, signals = [], {}
    benford = np.array([np.log10(1 + 1 / d) for d in range(1, 10)])
    for ent, g in alerts.groupby("entity_id"):
        rep = pd.to_numeric(g.get("reported_minutes", g["handling_minutes"]),
                            errors="coerce").dropna()
        rep = rep[rep > 0]
        if len(rep) < 30:
            signals[ent] = {"round_share": 0.0, "benford_p": 1.0}
            continue
        first = rep.astype(int).astype(str).str[0].astype(int)
        obs = np.array([(first == d).sum() for d in range(1, 10)], dtype=float)
        try:
            _, p = chisquare(obs, benford * obs.sum())
            p = float(p)
        except Exception:
            p = 1.0
        round_share = float(((rep % 10) == 0).mean())
        signals[ent] = {"round_share": round(round_share, 3), "benford_p": p}
        if round_share > c["round_share_threshold"]:
            out.append(_flag(c["rule_id"], ent, "Fabricated-numbers signature in reported times",
                             "medium",
                             f"{round_share:.0%} of reported handling times land exactly on 10-minute marks "
                             f"(natural ~10%; Benford chi-square p={p:.2g}) — the submission's numbers look "
                             "smoothed or hand-filled, the way cooked ledgers do.",
                             f"{round_share:.0%} round reported times", "~10% expected naturally",
                             []))
    return out, signals


def x2_sector(alerts: pd.DataFrame, assets: pd.DataFrame, expected_map: dict,
              sectors: dict | None, cfg: dict | None = None):
    """Sector Dark Spots: technique expected across a sector, seen by none."""
    c = (cfg or CFG)["X2_sector_darkspot"]
    findings = []
    if not sectors:
        return findings
    dark = _sector_dark_spots(alerts, assets, expected_map, sectors,
                              c["min_expecting_entities"])
    sec_ents: dict = {}
    for e, s in sectors.items():
        sec_ents.setdefault(s, []).append(e)
    for (s, t), expecting in sorted(dark.items()):
        if len(sec_ents.get(s, [])) >= c["min_sector_size"]:
            findings.append({
                "rule_id": c["rule_id"], "level": "sector", "sector": s,
                "technique_id": t, "expecting": expecting,
                "title": f"Sector dark spot: {t} unseen across {s}",
                "evidence": f"{t} is expected by {expecting} ({s} sector) but ZERO "
                            "entities there observed it — a systemic blind spot no "
                            "single-entity audit could surface."})
    return findings


def run_all_detectors(alerts, cases, assets, expected_map, cfg=None,
                      handoffs=None, escalations=None, sectors=None,
                      assessment_date=None, exercises=None):
    """Single-window engines. Returns (flags_by_entity, signals_by_entity,
    sector_findings). Cross-window engines (C5, C6) run separately in run.py
    and merge their flags; E12 needs an assessment_date (None = skipped)."""
    cfg = cfg or CFG
    collectors = [
        e1_sla_cliff(alerts, cfg), e2_escalation_violation(alerts, cfg),
        e3_fast_close(alerts, cfg), e4_duplicate_notes(cases, cfg),
        e5_repeat_asset(alerts, cfg),
        e6_throughput(alerts, cfg),
        e7_evidentiary_density(alerts, cases, cfg),
        e8_escalation_theatre(escalations, cfg),
        e9_bulk_burst(alerts, cfg),
        e10_downgrade(alerts, cfg),
        e11_hot_potato(handoffs, cfg),
        e12_audit_theatre(alerts, assessment_date, cfg),
        c1_coverage_gap(alerts, assets, expected_map, cfg, sectors),
        c2_silent_assets(alerts, assets), c3_volume_drop(alerts),
        c4_peer_outlier(alerts),
        c7_redteam(alerts, exercises, cfg),
        x1_digit_forensics(alerts, cfg),
    ]
    flags, signals = {}, {}
    for flist, slist in collectors:
        for f in flist:
            flags.setdefault(f["entity_id"], []).append(f)
        for ent, s in slist.items():
            signals.setdefault(ent, {}).update(s)
    sector = x2_sector(alerts, assets, expected_map, sectors, cfg)
    return flags, signals, sector
