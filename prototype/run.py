"""One command: generate -> ingest (DuckDB) -> detect -> score -> explain ->
validate -> trends -> dashboard.

Usage:
  python run.py            build everything, print triage table + validation
  python run.py --serve    also serve dashboard + API at http://127.0.0.1:8000
                           (legacy HTML at /, React SPA at /app, JSON at /api/*)

Windows: W18 is the blessed canonical baseline (seed 42, g=1.0, no assessment,
no drift). W14/W22 add assessment dates (E12), drift (C6) and trend slope.
Cross-window findings (E12/C5/C6/C7) merge into entity flags for display and
validation; sector findings (X2) are reported globally.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DB = os.path.join(HERE, "satsa.duckdb")
LEDGER_PATH = os.path.join(HERE, "ledger.jsonl")
RESULTS = os.path.join(HERE, "results.json")
TRENDS = os.path.join(HERE, "trends.json")
DASH = os.path.join(HERE, "dashboard.html")
MODEL_VERSION = "satsa-v0.4.0 E1-E12/C1-C7/X1-X2 rules-yaml+KS TFIDF xgb-shap"

WINDOWS = [
    {"label": "2026-W14", "seed": 142, "g": 0.5, "base": "2026-02-02",
     "assess": "2026-03-10", "drift": False},
    {"label": "2026-W18", "seed": 42, "g": 1.0, "base": "2026-06-01",
     "assess": None, "drift": False},  # canonical: keep pristine
    {"label": "2026-W22", "seed": 242, "g": 1.4, "base": "2026-09-21",
     "assess": "2026-11-04", "drift": True},
]
CANONICAL = "2026-W18"

# Red-team exercises (NCIIPC-provided in production; seeded here). Window mid ±3d.
EXERCISE_PLAN = [
    {"id": "RT-01", "entity_id": "CSE-001", "technique_id": "T1059"},
    {"id": "RT-02", "entity_id": "CSE-002", "technique_id": "T1190"},
    {"id": "RT-03", "entity_id": "CSE-003", "technique_id": "T1003"},
    {"id": "RT-04", "entity_id": "CSE-004", "technique_id": "T1566"},
    {"id": "RT-05", "entity_id": "CSE-005", "technique_id": "T1486"},
]


def _load_expected_map() -> dict:
    """ATT&CK expected-detectability map: YAML file wins, generator inline is fallback."""
    import yaml
    p = os.path.join(HERE, "attck", "expected_map.yaml")
    if os.path.exists(p):
        with open(p) as f:
            return yaml.safe_load(f)
    from satsa.generator import EXPECTED_MAP
    return dict(EXPECTED_MAP)


def _exercises_for(base: str) -> list:
    mid = datetime.fromisoformat(base) + timedelta(days=30)
    out = []
    for ex in EXERCISE_PLAN:
        out.append({**ex,
                    "start": (mid - timedelta(days=3)).isoformat(),
                    "end": (mid + timedelta(days=3)).isoformat()})
    return out


def main():
    from satsa.generator import generate, SECTORS
    from satsa.store import init_and_ingest
    from satsa.detectors import run_all_detectors, c5_decay, c6_drift
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

    # ---- per-window single-window engines
    frames = {}  # label -> dict(alerts, cases, assets, handoffs, escalations, flags, signals, sector)
    for w in WINDOWS:
        alerts, cases, assets, gt, _, extra = generate(
            seed=w["seed"], gaming_level=w["g"], base_date=w["base"],
            assessment_date=w["assess"], inventory_drift=w["drift"])
        flags, signals, sector = run_all_detectors(
            alerts, cases, assets, expected_map, cfg,
            handoffs=extra["handoffs"], escalations=extra["escalations"],
            sectors=SECTORS, assessment_date=w["assess"],
            exercises=_exercises_for(w["base"]))
        frames[w["label"]] = {"alerts": alerts, "cases": cases, "assets": assets,
                              "handoffs": extra["handoffs"],
                              "escalations": extra["escalations"], "gt": gt,
                              "flags": flags, "signals": signals, "sector": sector}
    led.append("trend_windows", {"windows": [w["label"] for w in WINDOWS]})

    # ---- cross-window engines (C5 decay, C6 drift)
    wlabels = [w["label"] for w in WINDOWS]
    _c5, c5_signals = c5_decay([(l, frames[l]["alerts"]) for l in wlabels], cfg)
    _c6, c6_signals = c6_drift([(l, frames[l]["assets"]) for l in wlabels],
                               [(l, frames[l]["alerts"]) for l in wlabels], cfg)

    def _by_entity(flag_list):
        d: dict = {}
        for f in flag_list:
            d.setdefault(f["entity_id"], []).append(f)
        return d

    c5_flags, c6_flags = _by_entity(_c5), _by_entity(_c6)
    led.append("cross_window_detection",
               {"C5_flags": sum(len(v) for v in c5_flags.values()),
                "C6_flags": sum(len(v) for v in c6_flags.values())})

    # ---- canonical window drives DB, scores, validation
    F = frames[CANONICAL]
    alerts, cases, assets = F["alerts"], F["cases"], F["assets"]
    gt, flags, signals = F["gt"], {e: list(fl) for e, fl in F["flags"].items()}, F["signals"]

    # Pristine per-window signals for trends (BEFORE cross-window merge below,
    # which mutates the canonical dict — trends must stay single-window pure).
    import copy as _copy
    pristine_signals = {lab: _copy.deepcopy(frames[lab]["signals"]) for lab in wlabels}

    # merge cross-window + other-window E12/C7 findings into entity flags
    for lab in wlabels:
        for ent, fl in frames[lab]["flags"].items():
            for f in fl:
                if f["rule_id"] in ("SAT-E12", "SAT-C7") and lab != CANONICAL:
                    g = dict(f)
                    g["window"] = lab
                    flags.setdefault(ent, []).append(g)
    for src in (c5_flags, c6_flags):
        for ent, fl in src.items():
            for f in fl:
                g = dict(f)
                g["window"] = "cross-window"
                flags.setdefault(ent, []).append(g)
    # merge cross-window SIGNALS into canonical signals before scoring
    for ent, s in c5_signals.items():
        signals.setdefault(ent, {}).update(s)
    for ent, s in c6_signals.items():
        signals.setdefault(ent, {}).update(s)

    ing_hash = init_and_ingest(DB, alerts, cases, assets,
                               F["handoffs"], F["escalations"])
    led.append("ingestion", {"rows": {"alerts": len(alerts), "cases": len(cases),
                                      "assets": len(assets),
                                      "handoffs": len(F["handoffs"]),
                                      "escalations": len(F["escalations"])},
                             "sha256": ing_hash, "source": "synthetic-seed-42"})
    led.append("model_version", {"version": MODEL_VERSION})
    led.append("detection", {"n_flags": sum(len(v) for v in flags.values()),
                             "engines": ["E1-E12", "C1-C7", "X1-X2"],
                             "rule_pack_sha": cfg_hash})
    scores = score_entities(signals)
    led.append("scoring", {"scores": scores})

    explanations = train_explain(alerts)
    led.append("explanation_model", explanations["model"])

    metrics = validate(scores, flags, gt)
    led.append("validation", metrics)

    # sector findings (X2): dedupe across windows by (sector, technique)
    seen, sector_findings = set(), []
    for lab in wlabels:
        for f in frames[lab]["sector"]:
            k = (f["sector"], f["technique_id"])
            if k not in seen:
                seen.add(k)
                sector_findings.append({**f, "window": lab})
    led.append("sector_findings", {"count": len(sector_findings)})
    ok, msg = led.verify()

    # trends for REQ 16 (pristine single-window signals — no cross-window merge)
    trend_series: dict = {}
    for lab in wlabels:
        wscores = score_entities({e: dict(s) for e, s in pristine_signals[lab].items()})
        for ent, s in wscores.items():
            trend_series.setdefault(ent, {"EIS": [], "CAS": []})
            trend_series[ent]["EIS"].append(s["EIS"])
            trend_series[ent]["CAS"].append(s["CAS"])
    trends = {"windows": wlabels, "series": trend_series}
    with open(TRENDS, "w") as f:
        json.dump(trends, f, indent=1)

    with open(RESULTS, "w") as f:
        json.dump({"scores": scores, "signals": signals, "flags": flags,
                   "metrics": metrics, "ground_truth": gt,
                   "explanations": explanations,
                   "sector_findings": sector_findings,
                   "model_version": MODEL_VERSION}, f, indent=1, default=str)
    html = build_dashboard_html(scores, flags, signals, metrics,
                                led.read_all(), trends, explanations,
                                sector_findings)
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
        status = "PASS" if c["pass"] else "FAIL"
        print(f"  {ent}: expects {c['expected']} {status}")
        if not c["pass"]:
            print(f"         missing={c.get('missing')} fired={c['fired']}")
        else:
            print(f"         fired={c['fired']}")
    m = explanations["model"]
    print(f"\nexplainer: trained={m.get('trained')} "
          f"auc={m.get('auc_train')} n_viol={m.get('n_violations')}")
    print("sector findings (X2):")
    for f in sector_findings:
        print(f"  {f['sector']}: {f['technique_id']} unseen (expecting {f['expecting']})")
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
