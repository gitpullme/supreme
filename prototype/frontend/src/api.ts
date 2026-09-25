// Same-origin fetch helpers. No CORS, no absolute host, no CDN.
import type {
  AuditResponse,
  EntitiesResponse,
  EntityDetail,
  FeedbackResponse,
  FlagsResponseAll,
  FlagsResponseEntity,
  IngestResponse,
  TrendsResponse,
  ValidateResponse,
} from './types';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status} for ${url}`);
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  return (await res.json()) as T;
}

export function getEntities(): Promise<EntitiesResponse> {
  return fetchJson<EntitiesResponse>('/api/entities');
}

export function getEntity(id: string): Promise<EntityDetail> {
  return fetchJson<EntityDetail>(`/api/entities/${encodeURIComponent(id)}`);
}

export function getFlagsAll(): Promise<FlagsResponseAll> {
  return fetchJson<FlagsResponseAll>('/api/flags');
}

export function getFlagsForEntity(
  entity: string,
): Promise<FlagsResponseEntity> {
  return fetchJson<FlagsResponseEntity>(
    `/api/flags?entity=${encodeURIComponent(entity)}`,
  );
}

export function getAudit(): Promise<AuditResponse> {
  return fetchJson<AuditResponse>('/api/audit');
}

export function getValidate(): Promise<ValidateResponse> {
  return fetchJson<ValidateResponse>('/api/validate');
}

// /api/trends does NOT exist yet on the backend. Return null on 404 (or any
// failure) so the caller hides the trends view instead of crashing.
export async function getTrends(): Promise<TrendsResponse | null> {
  try {
    return await fetchJson<TrendsResponse>('/api/trends');
  } catch {
    return null;
  }
}

export async function postFeedback(body: {
  entity_id: string;
  rule_id: string;
  decision: 'confirm' | 'dismiss';
  note?: string;
}): Promise<FeedbackResponse> {
  const res = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = '';
    try {
      detail = await res.text();
    } catch {
      /* ignore */
    }
    throw new Error(
      `Feedback endpoint unavailable (HTTP ${res.status})${detail ? `: ${detail.slice(0, 200)}` : ''}`,
    );
  }
  return (await res.json()) as FeedbackResponse;
}

export async function postIngest(form: FormData): Promise<IngestResponse> {
  const res = await fetch('/api/ingest', { method: 'POST', body: form });
  if (!res.ok) {
    let detail = '';
    try {
      detail = await res.text();
    } catch {
      /* ignore */
    }
    throw new Error(
      `Ingest failed (HTTP ${res.status})${detail ? `: ${detail.slice(0, 300)}` : ''}`,
    );
  }
  return (await res.json()) as IngestResponse;
}

export function httpStatus(e: unknown): number | undefined {
  return (e as { status?: number })?.status;
}
