"""Honest perf benchmark: replicate the canonical window K times with distinct
entity IDs, time DuckDB ingest + full detection + scoring. No mocks.

Usage: python perf_bench.py [copies=20]
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DB = os.path.join(HERE, "perf.duckdb")


def main():
    import pandas as pd
    from satsa.generator import generate, EXPECTED_MAP
    from satsa.store import init_and_ingest
    from satsa.detectors import run_all_detectors
    from satsa.scoring import score_entities
    from satsa.config import load as load_config

    k = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    alerts, cases, assets, _, _ = generate(seed=42)
    n0 = len(alerts)

    A, C, S = [], [], []
    for i in range(k):
        a, c, s = alerts.copy(), cases.copy(), assets.copy()
        tag = f"-R{i:02d}"
        for df in (a, c, s):
            df["entity_id"] = df["entity_id"] + tag
        a["alert_id"] = a["alert_id"] + tag
        a["asset_id"] = a["asset_id"] + tag
        c["case_id"] = c["case_id"] + tag
        c["alert_id"] = c["alert_id"] + tag
        s["asset_id"] = s["asset_id"] + tag
        A.append(a)
        C.append(c)
        S.append(s)
    A = pd.concat(A, ignore_index=True)
    C = pd.concat(C, ignore_index=True)
    S = pd.concat(S, ignore_index=True)
    print(f"rows: alerts={len(A)} (base window {n0} x {k}), "
          f"cases={len(C)}, assets={len(S)}")

    cfg, _ = load_config()
    t = time.perf_counter()
    init_and_ingest(DB, A, C, S)
    t_ing = time.perf_counter() - t
    t = time.perf_counter()
    flags, signals = run_all_detectors(A, C, S, EXPECTED_MAP, cfg)
    scores = score_entities(signals)
    t_det = time.perf_counter() - t
    n_ent = len(scores)
    print(f"ingest : {t_ing:.1f}s  ({len(A) / t_ing:,.0f} alerts/s)")
    print(f"detect : {t_det:.1f}s over {n_ent} entities "
          f"({len(A) / t_det:,.0f} alerts/s, {t_det / n_ent:.2f}s/entity)")
    print(f"flags  : {sum(len(v) for v in flags.values())}")
    one_m = 1_000_000 / (len(A) / t_det)
    print(f"extrapolated full-pipeline time for 1M alerts on THIS box: ~{one_m:,.0f}s "
          f"(single process, no tuning)")
    os.remove(DB)


if __name__ == "__main__":
    main()
