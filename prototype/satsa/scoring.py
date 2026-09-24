"""EIS / CAS scoring. No black box: noisy-OR aggregation over normalised signals.

EIS (Execution Integrity, higher = worse): is work real or ticket-closing?
CAS (Coverage Assurance, higher = worse): is anything missing?

Why noisy-OR instead of a weighted mean: a mean lets one screaming signal
(e.g. 95% of criticals never escalated) hide behind four quiet ones. Risk
accumulates disjunctively — ANY strong gaming/absence signal tanks the score,
and further signals push it higher. Formula (fully visible):

    EIS = 100 * (1 - PROD_i (1 - s_i))      over the 5 E-signals, each in [0,1]
    CAS = 100 * (1 - PROD_j (1 - c_j))      over the 4 C-signals

Explainability bonus: marginal contributions computed in a fixed, documented
order sum EXACTLY to the score, so the dashboard can say
"esc-violations +38, fast-close +21, ..." with no residual to hand-wave about.
Priority shown WITH both components, never as a hidden blend.
"""
from __future__ import annotations

E_ORDER = ["esc_violation_rate", "fast_close_rate", "cliff_frac",
           "dup_rate", "repeat_groups"]
C_ORDER = ["coverage_gap_frac", "silent_tier1_frac", "blind_spot",
           "peer_outlier"]


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _esignals(s: dict) -> dict:
    return {
        "esc_violation_rate": _clip01(s.get("esc_violation_rate", 0)),
        "fast_close_rate": _clip01(s.get("fast_close_rate", 0)),
        "cliff_frac": _clip01(s.get("cliff_frac", 0)),
        "dup_rate": _clip01(s.get("dup_rate", 0)),
        "repeat_groups": _clip01(s.get("repeat_groups", 0) / 5.0),
    }


def _csignals(s: dict) -> dict:
    # Binary absence signals map to fixed strengths (< 1 so no single
    # binary flag alone can max the score; documented, tunable).
    return {
        "coverage_gap_frac": _clip01(s.get("coverage_gap_frac", 0)),
        "silent_tier1_frac": _clip01(s.get("silent_tier1_frac", 0)),
        "blind_spot": 0.60 if s.get("blind_spot") else 0.0,
        "peer_outlier": 0.50 if abs(s.get("peer_z", 0)) > 1.5 else 0.0,
    }


def _noisy_or(parts: dict, order: list) -> tuple[float, dict]:
    remaining, total, contrib = 1.0, 0.0, {}
    for k in order:
        c = parts[k] * remaining
        contrib[k] = round(100 * c, 1)
        total += c
        remaining *= (1 - parts[k])
    return round(100 * total, 1), contrib


def score_entities(signals: dict) -> dict:
    out = {}
    for ent, s in signals.items():
        e = _esignals(s)
        c = _csignals(s)
        eis, e_contrib = _noisy_or(e, E_ORDER)
        cas, c_contrib = _noisy_or(c, C_ORDER)
        priority = round(max(eis, cas), 1)  # transparent: worst axis drives attention
        band = ("CLEAR" if priority < 25 else "WATCH" if priority < 50
                else "ELEVATED" if priority < 70 else "PRIORITY")
        out[ent] = {"EIS": eis, "CAS": cas, "priority": priority, "band": band,
                    "e_parts": e, "e_contrib": e_contrib,
                    "c_parts": c, "c_contrib": c_contrib}
    return out
