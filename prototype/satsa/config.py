"""Central rule-pack loader. Code NEVER hardcodes a threshold twice:
defaults live here (identical to rules/detectors.yaml) so the pipeline runs
even if the YAML is missing; when present, the YAML wins and its hash is
ledger-logged for dispute-grade auditability.
"""
from __future__ import annotations

import hashlib
import os

DEFAULTS = {
    "version": "v0.2.0-rules",
    "E1_sla_cliff": {"rule_id": "SAT-E1", "last_window_frac": 0.10,
                     "flag_threshold": 0.30, "high_threshold": 0.45,
                     "ks_alpha": 0.05},
    "E2_escalation_violation": {"rule_id": "SAT-E2",
                                "severities": ["critical", "high"],
                                "tier": "Tier-1", "min_violations": 3,
                                "min_rate": 0.15},
    "E3_fast_close": {"rule_id": "SAT-E3/E6", "fast_close_min": 15,
                      "high_rate_threshold": 0.15},
    "E4_duplicate_notes": {"rule_id": "SAT-E4", "method": "tfidf-cosine",
                           "sim_threshold": 0.85, "min_rate": 0.10},
    "E5_repeat_asset": {"rule_id": "SAT-E5", "repeat_min": 3, "min_hot": 2,
                        "vol_min": 6, "high_groups_threshold": 3},
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
