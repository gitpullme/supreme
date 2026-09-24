# SAT-SA — Solution Architecture (2 pages)

## 1. Problem → design bet

NCIIPC manual reviews catch what paperwork misses: **execution gaps** (ticket-closing
masquerading as investigation) and **negative space** (expected evidence absent).
SAT-SA is a **batch supervisory analytics tool**: periodic CSE submissions in,
prioritised entities + evidence-backed flags out. Explicitly NOT a SIEM, SOC, or
real-time monitor. Fully offline: no internet, cloud, SaaS, or external AI.

Core bet: **two separate scores, never one black box** — EIS (is work real?) and
CAS (what's missing?), each 0–100 (higher = worse) with exact-sum contribution
breakdowns. Priority = max(EIS, CAS), always displayed with both components.

## 2. Data flow

```
CSE submissions (CSV/JSON/DB: alerts, cases, assets, escalations)
        │  satsa/store.py → DuckDB (Postgres-compatible SQL later)
        ▼  SHA-256 logged to hash-chain ledger
┌──────────────────────┐  ┌──────────────────────┐
│ EXECUTION-GAP ENGINE │  │ NEGATIVE-SPACE ENGINE│
│ E1 SLA-cliff (+KS)   │  │ C1 ATT&CK cover-gap  │
│ E2 escalation logic  │  │ C2 silent Tier-1     │
│ E3 fast-close (+E6)  │  │ C3 volume-drop (z)   │
│ E4 dup-note NLP      │  │ C4 peer outlier      │
│ E5 repeat-no-remedy  │  │                      │
└──────────┬───────────┘  └──────────┬───────────┘
           ▼                         ▼
   EIS (noisy-OR)              CAS (noisy-OR)   ← satsa/scoring.py
           └─────────┬─────────┘
                     ▼
   XGBoost+SHAP explainer (explains, never detects) + optional local LLM prose
                     ▼
   Supervisor UI (React /app + legacy /) ← GET /api/*, POST /api/feedback
                     ▼
   Hash-chain ledger: ingestion → rule-pack → detection → scoring →
   explanation → validation → supervisor decisions (dispute-grade audit)
```

## 3. Key decisions

- **Rules detect, models explain.** Every flag = rule_id + evidence + record IDs.
  XGBoost+SHAP answers "why does the statistics agree", never "guilty because AI".
- **Absence needs an expectation.** C1 derives expected techniques from asset roles
  (`attck/expected_map.yaml`); silent assets/volume drops are measured against
  baselines — never bare "zero means bad".
- **Noisy-OR scoring**, not weighted means: one screaming signal can't hide behind
  quiet ones; marginal contributions sum exactly to the score.
- **Thresholds are config, not code** (`rules/detectors.yaml`, hashed per run).
- **Validation = contract.** Seeded synthetic suite with labelled gaming patterns
  stands in for past manual findings: precision/recall + top-N overlap + clean-last,
  printed on every run. Real NCIIPC finding exports plug into the same harness
  (`satsa/realdata.py`).

## 4. Deployment & scale

Single CPU-only container (`python:3.12-slim`), built once, shipped via offline
media. DuckDB embedded → Postgres path. Measured: 58k alerts/s ingest, 0.12 s/entity
detection, ~400 s per 1M-alert window single-process. TF-IDF E4 → vendored MiniLM
drop-in; STL/Prophet later with z-score retained as explainable baseline.
