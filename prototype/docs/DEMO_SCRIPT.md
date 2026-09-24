# Demo video script — 2 minutes, no live coding (pre-run everything)

**0:00–0:15 — Problem.** "Every compliance dashboard shows what SOCs self-report.
Manual NCIIPC reviews keep finding the gap between paperwork and reality — gaming
and silence. SAT-SA automates that review instinct, offline."

**0:15–0:40 — Triage.** Open `/app`. EIS×CAS scatter: four entities top-right,
one clean bottom-left. "Two scores, not one black box: is investigation real,
and what's missing?" Click CSE-002.

**0:40–1:05 — Execution gap.** CSE-002 drill-down: SAT-E1 flag, cliff chart,
"66% of closures in the final 10% of SLA, KS rejects uniformity — deadline-driven
ticket-closing." Show evidence record count + SHAP drivers.

**1:05–1:30 — Negative space.** Switch to CSE-004: silent Tier-1 assets, ATT&CK
coverage gaps (phishing expected, never seen), 7-day blackout chart. "The tool
notices what's quietly missing — no SIEM shows you this."

**1:30–1:50 — Trust.** Audit view: hash-chained ledger, verify OK. Confirm one
flag via feedback button. Validation view: precision 1.0, recall 1.0, clean
ranked last. "Validated like NCIIPC validates: against manual-review findings."

**1:50–2:00 — Deploy.** "One CPU-only container, zero network, DuckDB today,
Postgres tomorrow. Rules detect, models explain, supervisors decide."
