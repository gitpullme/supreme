# SAT-SA — Brutal God-Tier Execution Plan

> Goal: win SIH 26157. Strategy: be the only team that detects **gaming** and
> **absence**, proves it against manual review, and explains every flag.
> Prototype (v0) is included in this plan and already built under `prototype/`.

## Phase 0 — Foundations (Day 1) ✅ DONE in prototype

- [x] Lock `SOLUTION_CONTEXT.md` (thesis, detectors E1–E6/C1–C5, EIS/CAS, stack).
- [x] Repo layout: `prototype/` = runnable v0; `docs/` = SIH deliverables (next).
- [x] Deterministic synthetic data generator (seed=42) with 5 CSEs, each with a
  distinct injected pathology + 1 clean control. Ground-truth labels emitted
  for validation harness.
- [x] DuckDB ingestion (`satsa_store.py`): CSV/JSON → normalised tables
  `alerts, cases, assets, escalations`; ingestion SHA-256 logged to ledger.
- [x] Hash-chain ledger (`satsa_ledger.py`): append-only JSONL, SHA-256 chained,
  verify command.
- [x] 9 detectors (`satsa_detectors.py`), EIS/CAS scorer (`satsa_scoring.py`),
  validation harness (`satsa_validate.py`), FastAPI JSON API (`api.py`),
  offline server-rendered dashboard (`dashboard.py`), one-command runner (`run.py`).

**Definition of done:** `python run.py` generates data → runs engines → prints
EIS/CAS table + precision/recall → serves dashboard at :8000. No internet, no GPU.

## Phase 1 — Execution-gap engine hardening (Days 2–3)

1. **E1 SLA-cliff:** histogram of (SLA_deadline − closed_at) in last-10% bucket +
   KS test vs uniform; report cliff-ratio + p-value. Visual: cliff histogram per entity.
2. **E2/E3/E6 rule pack:** YAML-driven rules (`rules/escalation.yaml`) with IDs
   `SAT-E2-…`; every hit stores alert_ids + asset + technique + handling-minutes.
3. **E4 NLP upgrade path:** v0 TF-IDF cosine ≥0.85 across different cases.
   Swap to `all-MiniLM-L6-v2` ONNX (offline, CPU) behind identical
   `flag_duplicate_notes()` signature; keep TF-IDF as fallback + benchmark both.
4. **E5 repeat-asset:** group (asset, technique) windows; flag ≥3 re-fires with
   zero remediation/escalation; link to case IDs.
5. Add per-flag evidence bundles: `{rule_id, record_ids, observed, expected, technique}`.

## Phase 2 — Negative-space engine hardening (Days 3–4) — the differentiator

1. **C1 coverage map:** `attck/expected_map.yaml` (asset_role → expected
   techniques, e.g. `internet-facing → [T1190,T1133]`, `mail-gateway → [T1566]`,
   `ad-server → [T1003,T1078]`, `edr-covered → [T1059,T1486]`). Zero-hit expected
   technique = gap with citation. Steal DeTT&CT's scoring idea, supervisor flavour.
2. **C2 silent assets:** Tier-1 assets with 0 alerts over window; weight by
   criticality × days-silent.
3. **C3 blind spots:** per-entity daily counts → rolling mean/σ z-score;
   drop < −2.5σ for ≥3 days = blind-spot flag. Upgrade to STL/Prophet later;
   keep z-score as explainable baseline judges can read.
4. **C4 peer baselines:** cluster by (sector, size_bin, asset_mix); per-cluster
   median/IQR bands for volume + category mix; flag outside 1.5×IQR with peer table.
5. Negative-space flags ALWAYS show "expected vs observed" — absence is only
   convincing next to an explicit expectation.

## Phase 3 — Scoring + explainability (Day 4)

- **EIS** = 100 × noisy-OR over normalised E-signals
  (esc-violation, fast-close, SLA-cliff, dup-notes, repeat-groups):
  `EIS = 100·(1−Π(1−sᵢ))`. A mean would let one screaming signal hide behind
  four quiet ones; disjunctive accumulation is the honest risk semantic.
  Marginal contributions in fixed order sum EXACTLY to the score — the
  dashboard prints "esc +38, fast-close +21 …" with zero residual.
- **CAS** = same noisy-OR over C-signals (coverage-gap, silent-Tier-1,
  blind-spot→0.6, peer-outlier→0.5; binary signals capped below 1 so no single
  binary flag alone maxes the score).
- Priority = transparent max/mean shown WITH both components (never a hidden blend).
- SHAP: train XGBoost entity-risk classifier on E/C features → SHAP waterfall per
  entity in dashboard ("why flagged" panel). Rules path stays SHAP-free (rule ID
  + records IS the explanation).
- Optional Ollama narrative: template → Phi-3-mini draft → displayed as
  "draft rationale (unedited)" with detector citations; disabled by default offline.

## Phase 4 — API + UI (Days 5–6)

- FastAPI contracts (frozen — React builds against these):
  `GET /entities`, `GET /entities/{id}`, `GET /flags?entity=`, `GET /audit`,
  `GET /validate`, `POST /ingest` (CSV/JSON upload → DuckDB + ledger entry).
- v0 dashboard (`dashboard.py`): EIS×CAS scatter, per-entity drill-down
  (flags → evidence record IDs), cliff histogram, peer band chart, coverage-gap
  matrix, ledger tail. Server-rendered matplotlib → base64 PNG (zero CDN = air-gap safe).
- React upgrade (identical contracts): Vite+TS, Recharts, entity table, EIS/CAS
  scatter, evidence drawer, audit view. Serve built bundle from FastAPI `/`.
- Trend view: EIS/CAS across submission windows (REQ 16).

## Phase 5 — Validation harness (Day 6) — wins criterion 1 + PS §8

- Synthetic ground truth: generator labels every injected pattern
  (`ground_truth.json`); `satsa_validate.py` reports per-detector
  precision/recall + top-N entity overlap vs "manual review" priority list.
- Target for demo: precision 1.0 / recall 1.0 on the seeded 5-CSE suite, every
  injected pattern's detector PASSes, clean control CLEAR and ranked last
  (`risky_above_clean=true`). Top-3 overlap reported honestly (2/3 — the tool
  ranks by severity, the simulated manual list by entity order; the gap is
  ordering, not a miss). Print table in `run.py` output AND `/validate` AND
  dashboard footer — judges see numbers everywhere.
- Real-data path: document adapter for NCIIPC past-manual-finding exports
  (CSV of finding→entity→alert_ids) → same harness, no code change.
- Feedback loop: supervisor confirm/dismiss endpoint → ledger event →
  scheduled retrain runbook (`docs/RETRAIN.md`).

## Phase 6 — Air-gap + scale proof (Day 7)

- `Dockerfile` + `docker-compose.yml`: `api` + `dashboard` services, no
  outbound network (`network_mode: none` test passes), DuckDB file volume.
  Document Postgres swap path (SQL is portable; one env var).
- Hardware sheet: CPU-only, 4 vCPU / 8 GB RAM reference; MiniLM-ONNX ~90 MB,
  Prophet/statsmodels CPU; no GPU. Model-update = file drop + ledger hash.
- Perf test: 1M-alert synthetic ingest timed in README (DuckDB columnar proof).

## Phase 7 — SIH deliverables (Days 7–8)

- `README.md` + setup (offline wheel mirror instructions).
- `docs/ARCHITECTURE.md` (max 2 pages — diagram from prompt + EIS/CAS + ledger).
- 5-slide deck: problem → dual-score → detectors → explainability/ledger → validation.
- 2-min demo script: upload → scatter (clean vs gamed) → drill into SLA-cliff +
  silent-asset → show evidence + ledger → validation numbers. No live coding.
- GitHub link + demo video.

## Prototype v0 — what was built NOW (in `prototype/`)

```
prototype/
  requirements.txt      pandas numpy scikit-learn duckdb fastapi uvicorn matplotlib
  satsa/
    __init__.py
    generator.py        5 CSEs × seeded pathologies + ground truth
    store.py            CSV/JSON → DuckDB (alerts/cases/assets) + ingestion hash
    detectors.py        E1–E5 + C1–C4 (E6 folded into E3+technique tag)
    scoring.py          EIS/CAS 0–100, transparent weights
    ledger.py           SHA-256 hash chain (JSONL)
    validate.py         precision/recall + top-N overlap vs ground truth
  api.py                JSON API (frozen contracts for React)
  dashboard.py          offline HTML dashboard (matplotlib base64, no CDN)
  run.py                one command: generate → ingest → detect → score → validate → serve
  README.md
```

Entity pathologies (seeded, labelled):
CSE-001 clean control · CSE-002 SLA-gamer (closures in last 5% of SLA) ·
CSE-003 copy-paste investigator (duplicate notes) + fast-close ·
CSE-004 silent critical assets + missing ATT&CK coverage ·
CSE-005 critical-no-escalation + repeat-asset-no-remediation.

## Brutal truths (why this wins)

1. Judges score 6 criteria — dual EIS/CAS maps to 2 of them by construction.
2. Negative space (C1–C4) is what most teams skip — it's the moat.
3. Every flag carries evidence or it doesn't ship. No black boxes.
4. Air-gap compliance isn't a slide — v0 already runs with networking disabled.
5. Validation numbers (precision/recall + top-N overlap) answer PS §8 on screen,
   not in prose.
```

