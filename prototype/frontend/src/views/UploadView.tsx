import { useEffect, useRef, useState } from 'react';
import { getJob, uploadWithProgress } from '../api';
import type { JobStatus } from '../types';

const DOCS: Array<[string, string, boolean]> = [
  ['alerts', 'alerts.csv — one row per SOC alert (REQUIRED)', true],
  ['cases', 'cases.csv — investigation notes (REQUIRED)', true],
  ['assets', 'assets.csv — inventory: criticality, role, status (REQUIRED)', true],
  ['handoffs', 'handoffs.csv — analyst touches (optional, unlocks E11)', false],
  ['escalations', 'escalations.csv — open/reverse records (optional, unlocks E8)', false],
  ['exercises', 'exercises.csv — red-team windows (optional, unlocks C7)', false],
  ['findings', 'findings.csv — past manual findings (optional, unlocks validation)', false],
];

export default function UploadView({ onDone }: { onDone: () => void }) {
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Phase 1 (bytes on the wire, from the browser itself) + phase 2 (server stages).
  const [upPct, setUpPct] = useState<number | null>(null);
  const [upBytes, setUpBytes] = useState('');
  const [job, setJob] = useState<JobStatus | null>(null);
  const poller = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (poller.current) window.clearInterval(poller.current);
    },
    [],
  );

  function pick(key: string, f: File | null) {
    setFiles((p) => ({ ...p, [key]: f }));
  }

  async function submit() {
    setError(null);
    setJob(null);
    setUpPct(null);
    for (const [key, , required] of DOCS) {
      if (required && !files[key]) {
        setError(`Missing required file: ${key}.csv`);
        return;
      }
    }
    const form = new FormData();
    for (const [key] of DOCS) {
      if (files[key]) form.append(key, files[key] as File);
    }
    setBusy(true);
    try {
      const started = await uploadWithProgress(form, (loaded, total) => {
        setUpPct(Math.round((loaded / Math.max(total, 1)) * 100));
        setUpBytes(
          `${(loaded / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB`,
        );
      });
      // Transfer complete (202 accepted). Now poll the server's own milestones.
      poller.current = window.setInterval(async () => {
        try {
          const s = await getJob(started.job_id);
          setJob(s);
          if (s.state === 'done' || s.state === 'error') {
            if (poller.current) window.clearInterval(poller.current);
            poller.current = null;
            setBusy(false);
            if (s.state === 'error') setError(s.error ?? 'Assessment failed');
          }
        } catch (e) {
          if (poller.current) window.clearInterval(poller.current);
          poller.current = null;
          setBusy(false);
          setError(e instanceof Error ? e.message : 'Status poll failed');
        }
      }, 400);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : 'Upload failed');
    }
  }

  const result = job?.state === 'done' ? job.result : null;
  // Overall bar: transfer occupies 0–10%, server pipeline 10–100%.
  const overall =
    job != null
      ? Math.min(100, 10 + job.pct * 0.9)
      : upPct != null
        ? (upPct / 100) * 10
        : 0;

  return (
    <div>
      <div className="card">
        <h2>Inspector submission upload</h2>
        <div className="muted">
          Drop the CSE's assessment package (USB handover → this form). Files are
          validated against <span className="mono">schemas/SCHEMA.md</span>,
          hash-sealed into the audit ledger, then run through the exact same
          pipeline as the synthetic suite. Uploading <b>replaces</b> the current
          assessment — re-run <span className="mono">run.py</span> to restore the demo.
        </div>
        <div style={{ marginTop: 10 }}>
          {DOCS.map(([key, label, required]) => (
            <div className="checkline" key={key} style={{ marginBottom: 8 }}>
              <span className="mono" style={{ minWidth: 120 }}>
                {key}.csv{required ? ' *' : ''}
              </span>
              <input
                type="file"
                accept=".csv"
                disabled={busy}
                onChange={(e) => pick(key, e.target.files?.[0] ?? null)}
              />
              <span className="muted">{label}</span>
            </div>
          ))}
        </div>
        <div className="feedback-row">
          <button className="btn" onClick={submit} disabled={busy}>
            {busy ? 'WORKING…' : 'SEAL + ASSESS'}
          </button>
          {result && (
            <button className="btn" onClick={onDone}>
              OPEN TRIAGE →
            </button>
          )}
        </div>

        {(busy || job) && (
          <div style={{ marginTop: 12 }}>
            <div className="checkline">
              <span className="mono">
                {upPct != null && job == null
                  ? `UPLOADING ${upPct}% (${upBytes})`
                  : `${(job?.stage ?? 'starting').toUpperCase()} — ${job?.detail ?? ''}`}
              </span>
              <span className="mono" style={{ marginLeft: 'auto' }}>
                {overall.toFixed(0)}%
              </span>
            </div>
            <div className="bar" style={{ marginTop: 6 }}>
              <span
                className="fill-e"
                style={{ display: 'block', width: `${overall}%` }}
              />
            </div>
            {(job?.log ?? []).length > 0 && (
              <div
                className="mono muted"
                style={{
                  marginTop: 8,
                  maxHeight: 180,
                  overflowY: 'auto',
                  fontSize: 11.5,
                  lineHeight: 1.7,
                }}
              >
                {(job?.log ?? []).map((l, i) => (
                  <div key={i}>
                    [{l.t}] {l.stage} ({l.pct}%) — {l.detail}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {error && <div className="err">{error}</div>}
      </div>

      {result && (
        <div className="card">
          <h2>Assessment complete</h2>
          <div className="score-cards">
            <div className="score-card">
              <div className="k">Entities</div>
              <div className="v">{result.entities}</div>
            </div>
            <div className="score-card">
              <div className="k">Flags</div>
              <div className="v">{result.n_flags}</div>
            </div>
            <div className="score-card">
              <div className="k">Top entity</div>
              <div className="v" style={{ fontSize: 16 }}>
                {result.ranked[0] ?? '—'}
              </div>
            </div>
            <div className="score-card">
              <div className="k">Precision / Recall</div>
              <div className="v" style={{ fontSize: 16 }}>
                {result.metrics?.precision ?? '—'} / {result.metrics?.recall ?? '—'}
              </div>
            </div>
          </div>
          <div className="muted">
            Ranking: <span className="mono">{result.ranked.join(' → ')}</span>
          </div>
        </div>
      )}
    </div>
  );
}
