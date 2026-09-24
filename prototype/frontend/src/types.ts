// Frozen JSON contracts (FastAPI, same-origin). All fields beyond the
// documented contracts are optional — the UI renders defensively.

export interface EntitySummary {
  entity_id: string;
  EIS: number;
  CAS: number;
  priority: number;
  band: string;
  n_flags: number;
}

export interface EntitiesResponse {
  entities: EntitySummary[];
}

export interface Flag {
  rule_id: string;
  entity_id?: string;
  title: string;
  severity: string;
  evidence: string;
  observed: string | number;
  expected: string | number;
  records: string[];
  n_records: number;
}

export interface ScoreBlock {
  EIS: number;
  CAS: number;
  priority: number;
  band: string;
  e_parts?: Record<string, number>;
  e_contrib?: Record<string, number>;
  c_parts?: Record<string, number>;
  c_contrib?: Record<string, number>;
  // SHAP may or may not be present depending on backend version.
  shap_drivers?: ShapDriver[];
  shap?: ShapDriver[];
  shap_values?: Record<string, number>;
  [k: string]: unknown;
}

export interface ShapDriver {
  feature?: string;
  name?: string;
  value?: number;
  contribution?: number;
  [k: string]: unknown;
}

export interface EntityDetail {
  entity_id: string;
  scores: ScoreBlock;
  signals: Record<string, unknown>;
  flags: Flag[];
  ground_truth?: unknown;
}

export interface FlagsResponseAll {
  count: number;
  flags: Flag[];
}

export interface FlagsResponseEntity {
  entity_id: string;
  flags: Flag[];
}

export interface AuditEvent {
  seq: number;
  ts: string;
  event: string;
  payload: unknown;
  prev_hash: string;
  hash: string;
}

export interface AuditResponse {
  verified: boolean;
  message: string;
  events: AuditEvent[];
}

export interface PatternCheck {
  expected: string;
  pass: boolean;
  fired: string[];
}

export interface ValidateResponse {
  precision: number;
  recall: number;
  ranked: string[];
  tool_top3: string[];
  manual_top3: string[];
  top3_overlap: string;
  risky_above_clean?: boolean;
  tp?: number;
  fp?: number;
  fn?: number;
  pattern_checks: Record<string, PatternCheck>;
}

export interface TrendsResponse {
  windows: string[];
  series: Record<string, { EIS: number[]; CAS: number[] }>;
}

export interface FeedbackResponse {
  status: string;
  ledger?: unknown;
}

export type View = 'triage' | 'entity' | 'trends' | 'audit' | 'validate';
