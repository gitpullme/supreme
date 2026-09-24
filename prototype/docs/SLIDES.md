# Technical presentation — 5 slides

1. **The gap manual review catches** — paperwork vs reality; execution gaps +
   negative space; why SIEM/GRC/compliance can't see it. Out-of-scope guardrails.
2. **Dual scores, not a black box** — EIS×CAS scatter screenshot; noisy-OR +
   exact-sum contributions; priority always shows both axes.
3. **Detectors that cite their evidence** — 9 engines table (E1–E5/C1–C4);
   SLA-cliff + KS, copy-paste NLP, ATT&CK coverage gaps, silent assets;
   every flag = rule_id + records. Rules detect, XGBoost+SHAP explains.
4. **Trust & audit** — hash-chain ledger diagram; confirm/dismiss feedback loop;
   validation vs manual-review stand-in: precision 1.0 / recall 1.0 / clean last;
   trend windows showing a deteriorating gamer.
5. **Deployable & scalable** — air-gap container, CPU-only, offline model updates
   via file drop + ledger hash; measured 58k alerts/s ingest, 0.12 s/entity;
   DuckDB → Postgres; React SPA + API already split for NCIIPC intranet hosting.
