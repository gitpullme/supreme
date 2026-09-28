# SAT-SA — hardware, offline training/inference, model updates

Reference box (what the prototype was built and timed on): 4 vCPU / 8 GB RAM,
CPU-only, Windows 11. No GPU anywhere in the design. Anything at or above a
standard NCIIPC analyst workstation qualifies.

## Offline training & inference

| Component | Train | Infer | Size | Notes |
|---|---|---|---|---|
| Rules E1–E5/C1–C4 | n/a (config) | pandas/DuckDB | KBs | `rules/detectors.yaml`, hashed |
| TF-IDF E4 | fit per window | cosine | KBs | no pretraining, no downloads |
| XGBoost explainer | ~seconds on 1.5k alerts | ms/alert | ~100 KB | retrained per window, params ledger-logged |
| MiniLM E4 upgrade | none (frozen) | CPU | ~92 MB vendored (`models/minilm`) | cosine-threshold formulation REJECTED by validation gate 2026-09 (dup_rate 1.00 on clean control at 0.90–0.97); TF-IDF retained as default |
| Ollama narrative (optional) | none (frozen) | CPU, quantized 3B | ~2 GB | prose drafts only, never detection |

## Model update mechanism (air-gap)

1. New model/config file arrives via approved offline media.
2. Operator drops it into `models/` or `rules/` and reruns `python run.py`.
3. New SHA-256 is written to the ledger `rule_pack` / `explanation_model` event.
4. Old findings remain verifiable against the old hash — history is never rewritten.

## Scale-up path

DuckDB (embedded, zero-config) → PostgreSQL by changing the store layer only;
all detector SQL is portable. Container image is CPU-only `python:3.12-slim`.
Multi-node future: same ledger event schema ports to Hyperledger Fabric.

## Measured performance (this box, CPU-only, single process)

`perf_bench.py` (30,320 alerts / 100 entities, ingestion path):
- Ingest (DuckDB): 0.5 s — 58,420 alerts/s
- Hash-seal (SHA-256 over all 5 tables): 0.21 s for 14,782 alerts — ~70,000 alerts/s

Full 22-engine detection on the 14,782-alert demo package (6 banks):
- Total ~28 s (~530 alerts/s). Per-engine: E4 TF-IDF 23.5 s (84% — pairwise
  cosine per entity), E11 handoffs 3.2 s, E1 row-loop 0.8 s, E7 0.2 s,
  everything else <0.05 s each.
- End-to-end upload (parse → seal → 22 engines → SHAP → write): ~40 s.
- 1M-alert extrapolation, single process: ~30 min. Every per-entity engine is
  independent, so 8-way parallelism → ~4–5 min. E4 is the parallelization
  priority (see below).
