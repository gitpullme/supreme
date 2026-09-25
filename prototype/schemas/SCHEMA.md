# SAT-SA submission schema — what the inspector uploads

One assessment = one folder (USB handover or browser upload) with these CSVs.
`alerts.csv`, `cases.csv`, `assets.csv` are REQUIRED; the rest are optional and
unlock deeper engines. Column names must match; extra columns are ignored.
Missing optional *columns* fall back to documented defaults (logged in the ledger).

## alerts.csv (one row per SOC alert)

| column | meaning | example |
|---|---|---|
| alert_id | unique ticket ID | ALT-90214 |
| entity_id | which CSE | DEMO-BANK-02 |
| orig_severity | severity assigned by detection | critical |
| severity | final disposition severity (may equal orig) | critical |
| asset_id | target host, must exist in assets.csv | DB-01 |
| technique_id | ATT&CK ID if known, else UNKNOWN | T1003 |
| created_at / closed_at | ISO timestamps | 2026-08-01T09:02:00 |
| sla_hours | closure target for this severity | 8 |
| escalated | was it escalated (true/false) | false |
| status | closed/open | closed |
| handling_minutes | closed−created in minutes | 6.0 |
| analyst | badge ID who closed it | an-3 |
| reported_minutes | what the analyst *typed* as effort (X1 fabrication check) | 6.0 |

Optional columns: `orig_severity` (default = severity), `analyst` (default unknown),
`reported_minutes` (default = handling_minutes — X1 then sees nothing).

## cases.csv — `case_id, entity_id, alert_id, note, investigator, closed_at`

`note` is the free-text investigation write-up (E4/E7 read this).

## assets.csv — `asset_id, entity_id, criticality, role, status`

`criticality`: Tier-1/2/3. `role`: internet-facing, mail-gateway, ad-server,
edr-covered, db-server, workstation. `status`: active/decommissioned.

## handoffs.csv (optional — E11) — `handoff_id, alert_id, entity_id, analyst, ts`

One row per analyst touch. Without it, hot-potato analysis is skipped.

## escalations.csv (optional — E8) — `esc_id, alert_id, entity_id, actor, opened_at, closed_at, outcome`

`outcome`: genuine/reversed. Without it, escalation-theatre analysis is skipped.

## exercises.csv (optional — C7) — `id, entity_id, technique_id, start, end`

NCIIPC-known red-team windows. A confirmed exercise with zero matching alerts
is a *proven* blind spot (critical).

## findings.csv (optional — validation) — `entity_id, pattern, alert_ids`

Past manual-review findings (`clean`/`none` = compliant entity). With it, the
tool reports precision/recall against YOUR experts; without it, triage still
runs fully and validation shows "no ground truth".

## Different column names?

Map yours once via `satsa/realdata.py::map_columns`:
`{"alert_id": "Ticket No", "severity": "Final Sev", ...}` — everything downstream
(detectors, scoring, ledger) is untouched.
