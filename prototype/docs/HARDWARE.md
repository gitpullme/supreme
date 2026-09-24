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

## Measured performance (`python perf_bench.py 20`, this box, 30,320 alerts / 100 entities)

- Ingest (DuckDB): 0.5 s — 58,420 alerts/s
- Full detection + EIS/CAS: 12.1 s — 2,515 alerts/s, 0.12 s/entity
- Extrapolated 1M-alert window, single process, no tuning: ~400 s
- Bottleneck is per-entity TF-IDF (E4); embarrassingly parallel across entities.
