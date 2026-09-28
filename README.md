# SAT-SA — Supervisory Analytics Tool for SOC Assessment

### SIH 2026 · Problem Statement 26157 · NTRO / NCIIPC · Blockchain & Cybersecurity

> **Every compliance dashboard shows what SOCs self-report. SAT-SA catches what manual review catches: the gap between paperwork and reality — analysts gaming their metrics, and critical systems that went quietly dark.**

![precision](https://img.shields.io/badge/precision-1.00-brightgreen?style=flat-square)
![recall](https://img.shields.io/badge/recall-1.00-brightgreen?style=flat-square)
![detectors](https://img.shields.io/badge/detectors-22-blue?style=flat-square)
![offline](https://img.shields.io/badge/air--gap-100%25_offline-black?style=flat-square)
![stack](https://img.shields.io/badge/cost-%E2%82%B90_open_source-orange?style=flat-square)

---

## The 30-second pitch

NCIIPC inspectors manually read SOC ticket samples and keep finding what no audit, KPI dashboard, or compliance certificate shows: **rubber-stamped critical alerts, copy-pasted "investigations," escalations that never happened, and Tier-1 servers emitting zero telemetry for months.** Manual review works — but it can't scale to dozens of entities and millions of records.

SAT-SA is an **offline supervisory workbench** that automates that inspector instinct:

| # | What it does |
|---|---|
| 1 | Ingests periodic CSE submissions (CSV/JSON) — alerts, cases, assets, handoffs, escalations |
| 2 | Runs **22 forensic engines** across two axes instead of one black-box score |
| 3 | Explains **every flag** with rule ID + exact record IDs + SHAP drivers |
| 4 | Seals everything into a **tamper-evident hash-chain ledger** (dispute-grade audit) |
| 5 | Validates itself against manual-review findings: **precision 1.00, recall 1.00** |

---

## Innovation 1 — Two scores, never one black box

Most teams will build a single opaque "risk score." We score every entity on **two independent axes** that mirror the RFP's own gap categories:

- 🔨 **EIS — Execution Integrity Score** (0–100, higher = worse): *is investigation actually happening, or just ticket-closing?*
- 📡 **CAS — Coverage Assurance Score** (0–100, higher = worse): *is anything missing that should be there?*

A supervisor (and a judge) instantly sees *why* an entity was flagged. Scores use **noisy-OR aggregation** — one screaming signal can't hide behind quiet ones — with marginal contributions that sum *exactly* to the score, so the UI prints "esc-violations +38, fast-close +21…" with zero residual to hand-wave about.

## Innovation 2 — Negative space: catching what's quietly missing

Execution gaps are table stakes. Our moat is the harder half — **absence as evidence**:

- **Silent-asset discovery** — Tier-1 hosts with zero alerts all window
- **ATT&CK coverage-gap mapping** (DeTT&CT reasoning, repurposed for supervision) — expected-but-never-seen techniques, **peer-conditioned** so one entity is never flagged for what nobody can see
- **Time-series blind spots** — log sources going dark, with blackout days counted as zeros (the classic groupby bug, fixed)
- **Peer-cohort benchmarking** — suspiciously quiet vs comparable entities
- **Remediation decay curves** — the same alarm firing flat across quarters means the fix never happened
- **Inventory drift** — servers vanishing without decommission paperwork
- **Red-team reconciliation** — NCIIPC-known exercise, zero alerts = *proven* gap

## Innovation 3 — Meta-forensics (no single-entity audit can do these)

- **SAT-X1 · Digit forensics** — Benford + round-number analysis on reported handling times catches *fabricated submissions* (forensic-accounting math vs cooked CSVs)
- **SAT-X2 · Sector dark-spot analysis** — a technique unseen across nearly an entire sector escalates to a **national portfolio finding**

## Innovation 4 — Trust architecture

- **Rules detect, models explain.** XGBoost+SHAP answers "why do the statistics agree" — no finding ever depends on an opaque model. The local LLM drafts prose only, never verdicts.
- **Hash-chain ledger.** Every ingestion hash, rule-pack version, finding, and supervisor confirm/dismiss is SHA-256 chained. If a CSE disputes a finding, the chain proves what was submitted and what fired. Single node today, Hyperledger-Fabric-compatible event schema tomorrow.
- **Validation is a contract, not prose.** Seeded suite with labelled gaming patterns stands in for past manual findings: precision/recall + top-N overlap + clean-ranked-last, printed on every run and served at `/api/validate`.

### Measured results (canonical suite + 14.8k-row demo package)

| Check | Result |
|---|---|
| Precision / Recall | **1.00 / 1.00** (both suites) |
| Clean control (CSE-001 / DEMO-BANK-01) | **CLEAR, zero flags, ranked last** |
| Pattern checks | **14/14 PASS** — every detector fires on its intended entity |
| Sector findings | 4 dark spots (banking + energy × T1071/T1558) |
| Ingest / detection | 58,420 alerts/s · 0.12 s/entity · ~400 s per 1M alerts, CPU-only |
| Determinism | bit-identical across runs (seeded) |

---

## The 22 engines

<details>
<summary><b>Execution-gap forensics (E1–E12)</b> — is the work real?</summary>

| ID | Detector |
|---|---|
| E1 | SLA-cliff clustering + Kolmogorov–Smirnov test vs uniform handling |
| E2 | Escalation-logic violations (reads *original* severity — downgrades can't hide) |
| E3 | Fast-close: hot alerts resolved in ≤15 min |
| E4 | Copy-paste investigation NLP (TF-IDF; MiniLM cosine *rejected* by our own validation gate) |
| E5 | Repeat asset+technique, <10% ever escalated |
| E6 | Throughput implausibility (45 hot closures, one analyst, one shift) |
| E7 | Evidentiary density: NER scan — hot notes citing zero artifacts are hollow |
| E8 | Escalation theatre: same-actor open→reverse inside 120 s |
| E9 | Bulk-closure burst: ≥20 unrelated closures inside 60 s |
| E10 | Severity downgrades of rarely-benign techniques (T1486/T1003/T1190) |
| E11 | Hot-potato reassignment graphs (≥4 analysts, ≤90 min) |
| E12 | Audit-calendar theatre: improves during inspection week, reverts after |

</details>

<details>
<summary><b>Negative-space engines (C1–C7)</b> — what's missing?</summary>

| ID | Detector |
|---|---|
| C1 | ATT&CK coverage gaps (peer-conditioned) |
| C2 | Silent Tier-1 assets |
| C3 | Volume-drop blind spots |
| C4 | Peer-baseline outliers |
| C5 | Remediation decay curves across windows |
| C6 | Asset inventory drift |
| C7 | Red-team reconciliation (proven gaps) |

</details>

<details>
<summary><b>Meta-forensics (X1–X2)</b></summary>

| ID | Detector |
|---|---|
| X1 | Digit-distribution forensics on reported times (fabricated submissions) |
| X2 | Cross-sector dark-spot meta-analysis (portfolio-level findings) |

</details>

---

## Run it in 60 seconds

```powershell
cd prototype
pip install -r requirements.txt
python run.py --serve
```

- React console → http://127.0.0.1:8000/app/ (triage, drill-down, trends, audit, validation, **upload**)
- Legacy dashboard → http://127.0.0.1:8000/ · JSON API → `/api/*`
- Upload tab accepts real CSE CSVs (`schemas/SCHEMA.md`) with a live stage-by-stage progress tracker; `schemas/` ships a 14,782-alert demo package (6 banks) that scores precision/recall 1.00 on upload

100% offline-capable, CPU-only, ₹0 stack (Python, FastAPI, DuckDB, scikit-learn, XGBoost+SHAP, React). Docker + single-`.exe` paths documented for air-gap deployment.

---

## Repository map

```
├── README.md               # you are here
├── PS.txt / PSwithSOL.txt  # problem statement + full solution document
├── SOLUTION_CONTEXT.md     # locked design principles + traceability matrix
├── PLAN.md                 # phased execution plan
└── prototype/
    ├── satsa/              # engines, scoring, ledger, explainer, pipeline
    ├── rules/ attck/       # audited, hashed YAML rule packs
    ├── schemas/            # upload contract + 14.8k-row demo package + generator
    ├── frontend/           # React+TS+Recharts phosphor-console SPA
    ├── api.py run.py       # API + one-command pipeline
    └── docs/               # 2-page architecture, hardware, demo script, slides
```

## Why this wins (mapped to the 6 SIH criteria)

1. **Supervisory assessment** — priority leaderboard + drill-down to exact record IDs
2. **Execution gaps** — 12 forensic engines incl. gaming, theatre, downgrades, bursts
3. **Negative space** — 7 absence engines, our moat
4. **Explainability & auditability** — rule citations + SHAP + hash-chain ledger + feedback loop
5. **Scalability** — measured numbers above; DuckDB→Postgres path; containerized
6. **Innovation** — dual scores, peer-conditioned coverage, X1/X2 meta-forensics, validation-as-contract
