"""One command: generate -> ingest (DuckDB) -> detect -> score -> explain ->
validate -> trends -> dashboard.

Usage:
  python run.py            build everything, print triage table + validation
  python run.py --serve    also serve dashboard + API at http://127.0.0.1:8000
                           (legacy HTML at /, React SPA at /app, JSON at /api/*)
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DB = os.path.join(HERE, "satsa.duckdb")
LEDGER_PATH = os.path.join(HERE, "ledger.jsonl")
RESULTS = os.path.join(HERE, "results.json")
TRENDS = os.path.join(HERE, "trends.json")
DASH = os.path.join(HERE, "dashboard.html")
MODEL_VERSION = "satsa-v0.3.0 rules-yaml+KS TFIDF-cos0.85 zscore xgb-shap"

# Submission windows: (label, seed, gaming_level). The middle window is the
# blessed canonical baseline (seed 42, g=1.0 reproduces v0 bit-for-bit).
WINDOWS = [("2026-W14", 142, 0.5), ("2026-W18", 42, 1.0), ("2026-W22", 242, 1.4)]
CANONICAL = "2026-W18"


def _load_expected_map() -> dict:
    """ATT&CK expected-detectability map: YAML file wins, generator inline is fallback."""
    import yaml
    p = os.path.join(HERE, "attck", "expected_map.yaml")
    if os.path.exists(p):
        with open(p) as f:
            return yaml.safe_load(f)
    from satsa.generator import EXPECTED_MAP
    return dict(EXPECTED_MAP)


def run_window(label: str, seed: int, g: float, mods) -> tuple:
    alerts, cases, assets, gt, _ = mods["generate"](
        seed=seed, gaming_level=g)
    flags, signals = mods["detect"](alerts, cases, assets,
                                    mods["expected_map"], mods["cfg"])
    scores = mods["score"](signals)
    return alerts, cases, assets, gt, flags, signals, scores


def main():
    from satsa.generator import generate
    from satsa.store import init_and_ingest
    from satsa.detectors import run_all_detectors
    from satsa.scoring import score_entities
    from satsa.validate import validate
    from satsa.explain import train_explain
    from satsa.ledger import Ledger
    from satsa.config import load as load_config
    from dashboard import build_dashboard_html

    if os.path.exists(LEDGER_PATH):
        os.remove(LEDGER_PATH)
    led = Ledger(LEDGER_PATH)

    cfg, cfg_hash = load_config()
    led.append("rule_pack", {"version": cfg.get("version"), "sha256": cfg_hash})
    expected_map = _load_expected_map()
    mods = {"generate": generate, "detect": run_all_detectors,
            "score": score_entities, "expected_map": expected_map, "cfg": cfg}

    # ---- multi-window trends (REQ 16); canonical window drives everything else
    trend_series: dict = {}
    trend_windows = [w[0] for w in WINDOWS]
    for label, seed, g in WINDOWS:
        _, _, _, _, _, _, wscores = run_window(label, seed, g, mods)
        for ent, s in wscores.items():
            trend_series.setdefault(ent, {"EIS": [], "CAS": []})
            trend_series[ent]["EIS"].append(s["EIS"])
            trend_series[ent]["CAS"].append(s["CAS"])
    trends = {"windows": trend_windows, "series": trend_series}
    with open(TRENDS, "w") as f:
        json.dump(trends, f, indent=1)
    led.append("trend_windows", {"windows": trend_windows})

    alerts, cases, assets, gt, flags, signals, scores = run_window(
        CANONICAL, 42, 1.0, mods)
    ing_hash = init_and_ingest(DB, alerts, cases, assets)
    led.append("ingestion", {"rows": {"alerts": len(alerts), "cases": len(cases),
                                      "assets": len(assets)},
                             "sha256": ing_hash, "source": "synthetic-seed-42"})
    led.append("model_version", {"version": MODEL_VERSION})

    led.append("detection", {"n_flags": sum(len(v) for v in flags.values()),
                             "engines": ["E1-E5", "C1-C4"],
                             "rule_pack_sha": cfg_hash})
    led.append("scoring", {"scores": scores})

    explanations = train_explain(alerts)
    led.append("explanation_model", explanations["model"])

    metrics = validate(scores, flags, gt)
    led.append("validation", metrics)
    ok, msg = led.verify()

    with open(RESULTS, "w") as f:
        json.dump({"scores": scores, "signals": signals, "flags": flags,
                   "metrics": metrics, "ground_truth": gt,
                   "explanations": explanations,
                   "model_version": MODEL_VERSION}, f, indent=1, default=str)
    html = build_dashboard_html(scores, flags, signals, metrics,
                                led.read_all(), trends, explanations)
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(html)

    print("\n=== SAT-SA triage (higher = worse) ===")
    print(f"{'entity':9} {'EIS':>6} {'CAS':>6} {'PRIO':>6}  band       flags")
    for ent in sorted(scores, key=lambda e: scores[e]["priority"], reverse=True):
        s = scores[ent]
        print(f"{ent:9} {s['EIS']:6.1f} {s['CAS']:6.1f} {s['priority']:6.1f}  "
              f"{s['band']:10} {len(flags.get(ent, []))}")
    print(f"\nvalidation: precision={metrics['precision']} recall={metrics['recall']} "
          f"top3_overlap={metrics['top3_overlap']} "
          f"risky_above_clean={metrics['risky_above_clean']}")
    print(f"ranking: {' > '.join(metrics['ranked'])}")
    print("pattern checks:")
    for ent, c in metrics["pattern_checks"].items():
        print(f"  {ent}: expects {c['expected']:28} "
              f"{'PASS' if c['pass'] else 'FAIL'}  fired={c['fired']}")
    m = explanations["model"]
    print(f"\nexplainer: trained={m.get('trained')} "
          f"auc={m.get('auc_train')} n_viol={m.get('n_violations')}")
    print("trends:")
    for ent in sorted(trend_series):
        e, c_ = trend_series[ent]["EIS"], trend_series[ent]["CAS"]
        print(f"  {ent}: EIS {e}  CAS {c_}")
    print(f"\nledger: {msg}\nresults -> {RESULTS}\ntrends -> {TRENDS}\n"
          f"dashboard -> {DASH}\ndb -> {DB}")

    if "--serve" in sys.argv:
        import uvicorn
        print("serving at http://127.0.0.1:8000  (legacy / · React /app · API /api)")
        uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
