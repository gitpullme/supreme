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
                   engines_label="E1-E12/C1-C7/X1-X2"):
    """Full single-assessment pass. gt=None -> metrics None (triage still runs).
    extra_flags: {entity: [flag,...]} merged in (cross-window findings).
    extra_signals: {entity: {...}} merged before scoring."""
    from .detectors import run_all_detectors
    from .scoring import score_entities
    from .explain import train_explain
    from .validate import validate

    flags, signals, sector = run_all_detectors(
        alerts, cases, assets, expected_map, cfg, handoffs=handoffs,
        escalations=escalations, sectors=sectors,
        assessment_date=assessment_date, exercises=exercises)
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
    scores = score_entities(signals)
    if ledger is not None:
        ledger.append("scoring", {"scores": scores})
    explanations = train_explain(alerts)
    if ledger is not None:
        ledger.append("explanation_model", explanations["model"])
    metrics = validate(scores, flags, gt) if gt is not None else None
    if ledger is not None and metrics is not None:
        ledger.append("validation", metrics)
    return {"scores": scores, "signals": signals, "flags": flags,
            "sector": sector, "explanations": explanations, "metrics": metrics}
