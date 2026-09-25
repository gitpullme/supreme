"""Validation harness (PS section 8 stand-in).

Compares tool output against ground-truth labels from the generator
(which play the role of NCIIPC past-manual-review findings):
  1. entity-level precision/recall (risky = EIS>=50 or CAS>=50 or any high+ flag)
  2. top-N overlap: do the tool's riskiest entities match manual-review priority?
  3. per-pattern expectation checks (did the right detector fire per entity?)
"""
from __future__ import annotations


def validate(scores: dict, flags: dict, ground_truth: dict, top_n: int = 3) -> dict:
    entities = sorted(ground_truth)
    pred_risky, true_risky = {}, {}
    for ent in entities:
        sc = scores.get(ent, {})
        fl = flags.get(ent, [])
        hot = any(f["severity"] in ("high", "critical") for f in fl)
        pred_risky[ent] = bool((sc.get("priority", 0) >= 50) or hot)
        true_risky[ent] = bool(ground_truth[ent]["risky"])

    tp = sum(1 for e in entities if pred_risky[e] and true_risky[e])
    fp = sum(1 for e in entities if pred_risky[e] and not true_risky[e])
    fn = sum(1 for e in entities if not pred_risky[e] and true_risky[e])
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)

    ranked = sorted(entities, key=lambda e: scores.get(e, {}).get("priority", 0),
                    reverse=True)
    # "manual priority" = risky entities first (simulating expert triage)
    manual_top = [e for e in entities if true_risky[e]][:top_n]
    tool_top = ranked[:top_n]
    overlap = len(set(manual_top) & set(tool_top))
    # Honest separation check: every risky entity must rank above the clean control.
    clean = [e for e in entities if not true_risky[e]]
    risky_above_clean = all(ranked.index(e) < min(ranked.index(c) for c in clean)
                            for e in entities if true_risky[e]) if clean else True

    # pattern -> detector expectations (lists: every listed rule must fire).
    # Cross-window findings (E12/C5/C6/C7) are merged into flags by run.py.
    # Seeded-suite expectations apply only when those entities exist; any OTHER
    # ground-truth entity (e.g. inspector uploads) gets a generic check:
    # risky ⇒ at least one high/critical flag, clean ⇒ none.
    rule_ids = {e: {f["rule_id"] for f in flags.get(e, [])} for e in entities}
    expectations = {
        "CSE-002": ["SAT-E1", "SAT-E9", "SAT-X1", "SAT-E12"],
        "CSE-003": ["SAT-E4", "SAT-E6", "SAT-E7", "SAT-E11"],
        "CSE-004": ["SAT-C2", "SAT-C6", "SAT-C7"],
        "CSE-005": ["SAT-E2", "SAT-E8", "SAT-E10"],
        "CSE-001": None,  # clean: expect no high/critical flags
    }
    pattern_checks = {}
    for ent in entities:
        wants = expectations.get(ent, "GENERIC")
        hot = [f for f in flags.get(ent, [])
               if f["severity"] in ("high", "critical")]
        if wants is None or (wants == "GENERIC" and not true_risky[ent]):
            pattern_checks[ent] = {"expected": "no high/critical flags",
                                   "pass": len(hot) == 0,
                                   "fired": sorted(rule_ids.get(ent, set()))}
        elif wants == "GENERIC":
            pattern_checks[ent] = {"expected": ">=1 high/critical flag (risky entity)",
                                   "pass": len(hot) > 0,
                                   "fired": sorted(rule_ids.get(ent, set()))}
        else:
            fired = rule_ids.get(ent, set())
            missing = [w for w in wants if not any(w in r for r in fired)]
            pattern_checks[ent] = {"expected": wants,
                                   "pass": len(missing) == 0,
                                   "missing": missing,
                                   "fired": sorted(fired)}

    return {"precision": round(precision, 3), "recall": round(recall, 3),
            "tp": tp, "fp": fp, "fn": fn,
            "ranked": ranked, "tool_top3": tool_top, "manual_top3": manual_top,
            "top3_overlap": f"{overlap}/{top_n}",
            "risky_above_clean": risky_above_clean,
            "pred_risky": pred_risky, "pattern_checks": pattern_checks}
