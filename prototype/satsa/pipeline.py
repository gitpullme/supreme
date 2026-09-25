"""Shared assessment pipeline: ONE code path for synthetic runs AND inspector
uploads. run.py (demo/validation) and POST /api/ingest (real submissions) both
call run_assessment(), so uploaded data gets exactly the validated behaviour —
no parallel implementation to drift.
"""
from __future__ import annotations


def run_assessment(alerts, cases, assets, handoffs=None, escalations=None,
                   cfg=None, expected_map=None, sectors=None,
                   assessment_date=None, exercises=None, gt=None,
                   extra_flags=None, extra_signals=None, ledger=None,
                   source="synthetic",
                   engines_label="E1-E12/C1-C7/X1-X2",
                   progress=None):
    """Full single-assessment pass. gt=None -> metrics None (triage still runs).
    extra_flags: {entity: [flag,...]} merged in (cross-window findings).
    extra_signals: {entity: {...}} merged before scoring.
    progress: optional callable(stage, pct, detail) — honest milestones with
    real counts; the UI polls these, nothing is simulated."""
    """Full single-assessment pass. gt=None -> metrics None (triage still runs).
    extra_flags: {entity: [flag,...]} merged in (cross-window findings).
    extra_signals: {entity: {...}} merged before scoring."""
    from .detectors import run_all_detectors
    from .scoring import score_entities
    from .explain import train_explain
    from .validate import validate
    import time as _t

    def emit(stage, pct, detail=""):
        if progress is not None:
            progress(stage, pct, detail)

    n_alerts, n_entities = len(alerts), alerts.entity_id.nunique()
    t0 = _t.perf_counter()
    emit("detect_execution", 5, f"E1–E12 over {n_alerts:,} alerts / {n_entities} entities")
    flags, signals, sector = run_all_detectors(
        alerts, cases, assets, expected_map, cfg, handoffs=handoffs,
        escalations=escalations, sectors=sectors,
        assessment_date=assessment_date, exercises=exercises)
    n_flags = sum(len(v) for v in flags.values())
    emit("detect_execution", 45,
         f"engines done in {_t.perf_counter() - t0:.1f}s — {n_flags} flags")
    if extra_flags:
        for ent, fl in extra_flags.items():
            flags.setdefault(ent, []).extend(fl)
    if extra_signals:
        for ent, s in extra_signals.items():
            signals.setdefault(ent, {}).update(s)

    if ledger is not None:
        ledger.append("detection",
                      {"n_flags": sum(len(v) for v in flags.values()),
                       "engines": [engines_label], "source": source})
    t1 = _t.perf_counter()
    emit("scoring", 55, "EIS/CAS noisy-OR + exact-sum contributions")
    scores = score_entities(signals)
    emit("scoring", 65, f"scored {len(scores)} entities in {_t.perf_counter() - t1:.1f}s")
    if ledger is not None:
        ledger.append("scoring", {"scores": scores})
    t2 = _t.perf_counter()
    emit("explaining", 72, "XGBoost + SHAP training on this window")
    explanations = train_explain(alerts)
    m = explanations.get("model", {})
    emit("explaining", 85,
         f"explainer AUC {m.get('auc_train')} over {m.get('n_violations')} violations "
         f"({_t.perf_counter() - t2:.1f}s)")
    if ledger is not None:
        ledger.append("explanation_model", m)
    metrics = validate(scores, flags, gt) if gt is not None else None
    if metrics is not None:
        emit("validating", 92,
             f"vs manual review: precision {metrics['precision']}, "
             f"recall {metrics['recall']}")
    else:
        emit("validating", 92, "no ground truth — triage only")
    if ledger is not None and metrics is not None:
        ledger.append("validation", metrics)
    emit("assessed", 100, f"{len(scores)} entities, {sum(len(v) for v in flags.values())} flags, "
                         f"{len(sector)} sector findings, total {_t.perf_counter() - t0:.1f}s")
    return {"scores": scores, "signals": signals, "flags": flags,
            "sector": sector, "explanations": explanations, "metrics": metrics}
