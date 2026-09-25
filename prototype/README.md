# SAT-SA prototype v0.3 — Supervisory Analytics Tool for SOC Assessment

Working end-to-end prototype of the plan in `../PLAN.md`. Detects **execution gaps**
(metric gaming, fake investigations) and **negative space** (what's quietly missing),
scores every entity on two separate axes (**EIS** + **CAS**), explains every flag
with rule ID + evidence + SHAP drivers, and chains everything into a tamper-evident ledger.

## 60-second run

```powershell
C:\Users\azmut\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
C:\Users\azmut\AppData\Local\Programs\Python\Python312\python.exe run.py
# legacy dashboard -> dashboard.html · React SPA -> python run.py --serve -> :8000/app
```

No internet, no GPU, no API keys at runtime. Deterministic seed — same numbers every run.

## What it proves (maps to PS requirements)

| Demo beat | Requirement |
|---|---|
| EIS×CAS scatter: CSE-001 clean corner vs 4 gamed entities | REQ 9 entity risk indicators |
| SLA-cliff + KS test (CSE-002), duplicate notes (CSE-003) | REQ 5, use cases i/vii/viii |
| Silent Tier-1 + coverage gaps + blackout + peer outlier (CSE-004) | REQ 6, use cases iv/vi |
| Critical-no-escalation + repeat-asset (CSE-005) | REQ 4, use cases ii/iii |
| Trend windows: gamer deteriorates 39 → 65 → 88 EIS | REQ 16 trend analysis |
| Per-flag rule_id + evidence + SHAP drivers (AUC 1.0) | REQ 11–14 explainability |
| Ledger panel + `/api/audit` verification + confirm/dismiss feedback | REQ 13 auditability |
| Precision 1.0 / recall 1.0, clean ranked last | PS §8 validation |
| DuckDB + CSV adapter (`satsa/realdata.py`) + 58k alerts/s ingest | REQ 1–3 ingestion/scale |
| CPU-only container, zero runtime network | PS §5 air-gap |

## API (frozen — React builds against these)

`GET /api/entities`, `/api/entities/{id}`, `/api/flags`, `/api/audit`,
`/api/validate`, `/api/trends`, `GET+POST /api/feedback`, `POST /api/ingest`.

## Layout

- `satsa/generator.py` — seeded synthetic CSE submissions + ground truth (`gaming_level` for trends)
- `satsa/store.py` — CSV/JSON → DuckDB + ingestion SHA-256
- `satsa/realdata.py` — real CSE column-mapping + manual-finding ground-truth loader
- `satsa/detectors.py` — engines E1–E12 / C1–C7 / X1–X2 (rule_id on every flag)
- `satsa/config.py` + `rules/detectors.yaml` — audited, hashed rule pack
- `satsa/scoring.py` — EIS/CAS noisy-OR with exact-sum contributions
- `satsa/explain.py` — XGBoost + SHAP (explains, never detects)
- `satsa/embeddings.py` — E4 adapter (TF-IDF default, vendored MiniLM drop-in)
- `satsa/ledger.py` — SHA-256 hash chain (JSONL)
- `satsa/validate.py` — precision/recall + top-N overlap harness
- `attck/expected_map.yaml` — asset-role → expected ATT&CK techniques
- `api.py` — JSON API + legacy dashboard + React static serving
- `frontend/` — React+TS+Recharts SPA (`dist/` served at `/app`)
- `run.py` / `perf_bench.py` / `Dockerfile` / `docker-compose.yml`
- `docs/` — ARCHITECTURE, HARDWARE, DEMO_SCRIPT, SLIDES
