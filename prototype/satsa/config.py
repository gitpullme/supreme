"""Central rule-pack loader. Code NEVER hardcodes a threshold twice:
defaults live here (identical to rules/detectors.yaml) so the pipeline runs
even if the YAML is missing; when present, the YAML wins and its hash is
ledger-logged for dispute-grade auditability.
"""
from __future__ import annotations

import hashlib
import os

DEFAULTS = {
    "version": "v0.4.0-rules",
    "E1_sla_cliff": {"rule_id": "SAT-E1", "last_window_frac": 0.10,
                     "flag_threshold": 0.30, "high_threshold": 0.45,
                     "ks_alpha": 0.05},
    "E2_escalation_violation": {"rule_id": "SAT-E2",
                                "severities": ["critical", "high"],
                                "tier": "Tier-1", "min_violations": 3,
                                "min_rate": 0.15},
    "E3_fast_close": {"rule_id": "SAT-E3", "fast_close_min": 15,
                      "high_rate_threshold": 0.15},
    "E4_duplicate_notes": {"rule_id": "SAT-E4", "method": "tfidf-cosine",
                           "sim_threshold": 0.85, "min_rate": 0.10},
    "E5_repeat_asset": {"rule_id": "SAT-E5", "repeat_min": 3, "min_hot": 2,
                        "vol_min": 6, "high_groups_threshold": 3},
    "E6_throughput": {"rule_id": "SAT-E6", "max_hot_per_shift": 25,
                      "shift_hours": 8},
    "E7_evidentiary_density": {"rule_id": "SAT-E7", "min_artifacts": 1,
                               "hollow_rate_threshold": 0.20, "min_hot_notes": 5},
    "E8_escalation_theatre": {"rule_id": "SAT-E8", "reverse_window_sec": 120,
                              "min_events": 2},
    "E9_bulk_burst": {"rule_id": "SAT-E9", "window_sec": 60, "min_closures": 20,
                      "min_assets": 10, "min_techniques": 3},
    "E10_downgrade": {"rule_id": "SAT-E10", "min_downgrades": 5, "min_rate": 0.25,
                      "rarely_benign": ["T1486", "T1003", "T1190"]},
    "E11_hot_potato": {"rule_id": "SAT-E11", "min_analysts": 4,
                       "max_span_min": 90, "min_cases": 2},
    "E12_audit_theatre": {"rule_id": "SAT-E12", "window_days": 14,
                          "improvement_margin": 0.25, "min_cases": 10},
    "C5_remediation_decay": {"rule_id": "SAT-C5", "min_windows": 3, "min_total": 12},
    "C6_inventory_drift": {"rule_id": "SAT-C6"},
    "C7_redteam": {"rule_id": "SAT-C7"},
    "X1_digit_forensics": {"rule_id": "SAT-X1", "round_share_threshold": 0.30,
                           "chi2_alpha": 0.05},
    "X2_sector_darkspot": {"rule_id": "SAT-X2", "min_sector_size": 2,
                           "min_expecting_entities": 2},
}

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_PATH = os.path.join(os.path.dirname(HERE), "rules", "detectors.yaml")


def load(pack_path: str = PACK_PATH) -> tuple[dict, str]:
    """Returns (config, sha256). Falls back to DEFAULTS if YAML absent."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v)
           for k, v in DEFAULTS.items()}
    raw = "".encode()
    if os.path.exists(pack_path):
        import yaml
        with open(pack_path, "rb") as f:
            raw = f.read()
        user = yaml.safe_load(raw.decode()) or {}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    h = hashlib.sha256(raw if raw else str(sorted(DEFAULTS.items())).encode())
    return cfg, h.hexdigest()
