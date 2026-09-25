# SAT-SA — Solution Context (locked in)

> Problem: SIH 26157 — Supervisory Analytics Tool for SOC Assessment, NCIIPC / NTRO.
> Source of truth: `PS.txt`. This file locks the design principles so every later
> decision can be traced back to the RFP. Read this before writing any code.

## 1. The one-sentence thesis

**Every SIEM, GRC tool and compliance checklist already shows CSEs what they
self-report. NCIIPC needs what manual review currently catches: the gap between
paperwork and reality.**

That single sentence kills 90% of bad designs (SOC dashboards, SIEM clones,
real-time monitoring, national cyber-monitoring platforms — all explicitly
out of scope, PS §1).

## 2. What the PS actually demands (PS.txt distilled)

- **Supervisory, not operational.** Batch analysis of *periodic submissions*
  (alert metadata, case records, workflow, escalation, disposition/closure,
  asset inventory). No live log collection, no packet captures, no PII unless
  justified. Minimise raw-log dependence (PS §2).
- **Two gap families, both mandatory (PS §3):**
  - **A. Execution Gaps** — paperwork says "effective", evidence says otherwise:
    acked-but-not-investigated, closed-unusually-quickly, critical-closed-without-
    escalation, template-driven investigations, controls-not-monitored,
    metric-gaming behaviour.
  - **B. Negative Space** — expected evidence is *absent*: silent critical
    systems, missing alert categories, missing investigations/escalations,
    suspiciously low activity, blind spots, peer-divergent absence.
  - Tool must catch **known AND previously-unknown** indicators of both.
- **Functional shall-list (PS §4, REQ 1–17):** multi-CSE ingestion
  (CSV/JSON/DB/API), large multi-entity/time-range analysis, detection /
  investigation / escalation weakness indicators, execution-gap + negative-space
  detection, anomaly/outlier detection, **peer benchmarking**, **entity-level
  risk indicators**, **review prioritisation** (entities, controls, processes,
  *individual alert samples*), rationale + evidence + traceability/auditability,
  dashboards + trend analysis + drill-down to evidence.
- **9 illustrative use cases** (§4.i–ix) — every one must be demonstrably covered:
  fast-closed high-sev, repeat-asset-no-remediation, critical-no-escalation,
  silent critical systems, peer deviation, missing coverage, repetitive-investigation,
  metric-gaming, workload-inconsistency.
- **Air-gap is non-negotiable (PS §5):** fully offline, no internet, no cloud,
  no SaaS, no externally-hosted AI/API. Any ML proposal must specify
  architecture, hardware, offline train/infer, update mechanism, explainability
  + auditability controls.
- **Judging (PS §7, 6 criteria):** (1) supervisory assessment support,
  (2) execution-gap detection, (3) negative-space detection,
  (4) explainability & auditability, (5) scalability & performance,
  (6) innovation & additional insights.
- **Validation (PS §8):** prove effectiveness **comparable to or better than
  manual sampling**, validated against expert-manual-review findings.
- **SIH deliverables:** source link, README+setup, 2-page architecture doc,
  2-min demo video, 5-slide technical presentation.

## 3. The core design bet (user's solution, preserved)

**Two separate, explainable scores — never one black-box risk score.**

| Axis | Name | Question it answers | RFP anchor |
|------|------|---------------------|------------|
| EIS | Execution Integrity Score (0–100, higher = worse) | Is investigation actually happening, or just ticket-closing? | Gap family A |
| CAS | Coverage Assurance Score (0–100, higher = worse) | Is anything missing that should be there? | Gap family B |

Keeping them separate is itself a differentiator: a supervisor (and a judge)
instantly sees *why* an entity was flagged, and it maps 1:1 onto two judging
criteria. Any "overall priority" shown is always a transparent combination
with both components still visible — never a hidden blend.

## 4. Detector inventory (locked — every detector cites PS use cases)

### Execution-gap engine (is work real?)
| ID | Detector | Signal | PS use case |
|----|----------|--------|-------------|
| E1 | SLA-cliff clustering (+KS vs uniform) | closures statistically pile up just before SLA deadline (histogram + KS test vs uniform) — classic metric-gaming signature | viii, REQ 7 |
| E2 | Escalation-logic violation | severity=critical/high AND asset criticality=Tier-1 AND escalation=NULL → explicit rule violation. Uses ORIGINAL severity so quiet downgrades (E10) can't hide emergencies | iii, REQ 4 |
| E3 | Fast-close | high/critical severity closed in < N min (e.g. ≤15 min) with no escalation | i, REQ 4 |
| E4 | Copy-paste investigation NLP | near-duplicate case notes across *different* cases via embedding cosine similarity (prod: MiniLM; prototype: TF-IDF — same interface, offline) | vii, REQ 7 |
| E5 | Repeat-asset no-remediation | same asset + same ATT&CK technique re-fires ≥K times with no remediation/escalation record | ii, REQ 4 |
| E6 | Throughput implausibility | hot closures per analyst-shift vs human-plausible ceiling (e.g. 45 hot in one 8h shift) — volume no individual ticket betrays | viii, REQ 7 |
| E7 | Evidentiary density | NER-style scan for IPs/hashes/hostnames/CVEs/alert-refs; hot notes with zero artifacts = hollow prose | iv, REQ 4 |
| E8 | Escalation theatre | same-actor escalation open→reverse inside 120s — performative compliance | iii, REQ 4 |
| E9 | Bulk-closure burst | sliding 60s window: ≥20 unrelated closures (baseline ~0.003) = mass rubber-stamp | viii, REQ 7 |
| E10 | Severity downgrade audit | orig-hot rarely-benign techniques (T1486/T1003/T1190) relabelled cold pre-closure | viii, REQ 7 |
| E11 | Hot-potato reassignment | alert bounced across ≥4 analysts inside 90 min — ownership avoidance | vii, REQ 7 |
| E12 | Audit-calendar correlation | metrics improve during assessment week and revert after (pre/during/post windows) | viii, REQ 7, 16 |

> ID note: the narrative workflow doc (PSwithSOL §Step-4) describes E2–E5 with
> different prose aliases (copy-paste, rubber-stamp, emergencies, triage). The
> normative IDs are §2.4's: code E1–E5 are the ORIGINAL five (unchanged since v0),
> E6–E12 are the forensic layer. Step-4's E2–E5 labels are descriptive, not IDs.

### Negative-space engine (what's quietly missing?)
| ID | Detector | Signal | PS use case |
|----|----------|--------|-------------|
| C1 | ATT&CK coverage gap (peer-conditioned) | expected-but-never-observed technique where ≥1 PEER observes it (proves detectability); sector-wide darkness routes to X2 instead — never flag one entity for what nobody sees | vi, REQ 6 |
| C2 | Silent-asset detection | critical asset (Tier-1) with zero alerts over full window, risk-weighted by criticality × days-silent | iv, REQ 6 |
| C3 | Volume-drop blind spot | per-entity daily counts vs trailing baseline (z-score; STL/Prophet later) | iv, viii, REQ 7 |
| C4 | Peer-baseline outlier | cluster entities; expected volume/category bands; flag outside norms | v, ix, REQ 8 |
| C5 | Remediation decay curve | recurring pair fires flat/rising across ≥3 windows with <10% ever escalated — acknowledged, never fixed | ii, REQ 6, 16 |
| C6 | Inventory drift | assets vanished without decommission record; new assets with zero monitoring | iv, REQ 6, 16 |
| C7 | Red-team reconciliation | NCIIPC-known exercise technique+window with zero alerts = PROVEN gap (critical) | vi, REQ 6 |

### Meta-level forensics
| ID | Detector | Signal |
|----|----------|--------|
| X1 | Digit-distribution forensics | round-number clustering in reported times + Benford chi-square — catches smoothed/fabricated submissions (data-integrity, not SOC failure) |
| X2 | Sector dark-spot meta-analysis | technique expected across a sector, seen by none → portfolio-level finding no single-entity audit could surface |

## 5. Stack (locked — 100% free, 100% offline-capable)

- Frontend: React + TypeScript + Recharts (browser UI served on NCIIPC intranet;
  "web" = browser-based, NOT internet-hosted). Prototype shortcut: FastAPI-served
  server-rendered dashboard (matplotlib PNGs, zero CDN) so the v0 demo works
  fully offline with no `npm` build step; React is the Phase-6 upgrade with
  identical API contracts.
- Backend: Python + FastAPI (deepest free ML/stats ecosystem).
- Store: DuckDB (embedded, zero-config, columnar — fast at exactly these
  analytical queries); PostgreSQL as the documented multi-user scale-up path.
- Analytics: scikit-learn, XGBoost + SHAP, statsmodels/Prophet,
  sentence-transformers (all-MiniLM, ONNX-quantised, CPU-only). Prototype uses
  sklearn TF-IDF + z-scores behind the same function signatures so the upgrade
  is a drop-in.
- Optional local LLM (Ollama: Phi-3-mini / Llama-3.2-3B quantised) **only** for
  drafting narrative rationale + rubric-scoring a *sample* of flagged notes —
  never for detection, so explainability never depends on an opaque model.
- Deploy: Docker Compose, images built once, moved via approved offline media
  (standard air-gap pattern). Paid cloud AI APIs are categorically incompatible
  with the air-gap mandate — free/offline is the *only* compliant path.

## 6. Explainability + auditability (judging criterion 4 — where most teams die)

- Every flag ships with **either** a SHAP attribution **or** an explicit rule ID
  plus the exact record IDs that triggered it. No "model says so".
- **Tamper-evident hash-chain ledger** (SHA-256, Merkle-style): every ingestion
  hash, model version, detector config, finding, and supervisor confirm/dismiss
  decision is chained. One air-gapped node = local hash chain; multi-node future
  = same event schema ports to Hyperledger Fabric (permissioned, no mining, free).
  This matters when a CSE disputes a finding.
- Supervisor feedback loop (confirm/dismiss) is logged in the same chain and
  drives retraining cadence.

## 7. Validation (PS §8 — non-negotiable)

- Run tool against the same alert/case data behind NCIIPC's past manual findings
  (ground truth) → report **precision/recall on flags** + **overlap of tool's
  top-N riskiest entities vs manual-review priority list**.
- Prototype stand-in (no NCIIPC data yet): seeded synthetic data generator with
  *injected, labelled* gaming patterns → identical precision/recall + top-N
  overlap harness (`satsa_validate.py`). Deterministic seed = reproducible demo.
- Models retrain on a fixed cadence from confirm/dismiss feedback; every
  retrain is a ledger event with old→new model hash.

## 8. Anti-patterns (explicitly forbidden by this design)

1. No real-time monitoring / SIEM / central-SOC features. Batch supervisory only.
2. No cloud, no external API, no CDN JS in the final UI.
3. No single opaque risk score. EIS and CAS stay separate end-to-end.
4. No LLM-based detection. LLM drafts prose only, behind a flag.
5. No raw-log dependence. Metadata + case records + inventory only.
6. No finding without evidence pointers + rule/model version.

## 9. Traceability matrix (detector → REQ → use case → score)

E1→{REQ7,REQ9,REQ10}→{viii}→EIS · E2→{REQ4,REQ9,REQ10}→{iii}→EIS ·
E3→{REQ4,REQ9,REQ10}→{i}→EIS · E4→{REQ7,REQ9,REQ10}→{vii}→EIS ·
E5→{REQ4,REQ9,REQ10}→{ii}→EIS · E6→{REQ7,REQ9}→{viii}→EIS ·
E7→{REQ4,REQ9}→{iv}→EIS · E8→{REQ4,REQ9}→{iii}→EIS ·
E9→{REQ7,REQ9}→{viii}→EIS · E10→{REQ7,REQ9}→{viii}→EIS ·
E11→{REQ7,REQ9}→{vii}→EIS · E12→{REQ7,REQ16}→{viii}→EIS ·
C1→{REQ6,REQ9,REQ10}→{vi}→CAS · C2→{REQ6,REQ9,REQ10}→{iv}→CAS ·
C3→{REQ6,REQ7,REQ16}→{iv,viii}→CAS · C4→{REQ8,REQ9}→{v,ix}→CAS ·
C5→{REQ6,REQ16}→{ii}→CAS · C6→{REQ6,REQ16}→{iv}→CAS ·
C7→{REQ6,REQ9}→{vi}→CAS · X1→{REQ7,REQ11}→{viii}→EIS ·
X2→{REQ8,REQ16}→{vi}→sector-level.
Dashboards+drill-down→{REQ11–17}. Ledger→{REQ11,12,13,14}.
