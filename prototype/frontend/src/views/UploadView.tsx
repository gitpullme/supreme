import { useState } from 'react';
import { postIngest } from '../api';
import type { IngestResponse } from '../types';

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
  const [result, setResult] = useState<IngestResponse | null>(null);

  function pick(key: string, f: File | null) {
    setFiles((p) => ({ ...p, [key]: f }));
  }

  async function submit() {
    setError(null);
    setResult(null);
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
      const r = await postIngest(form);
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

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
                onChange={(e) => pick(key, e.target.files?.[0] ?? null)}
              />
              <span className="muted">{label}</span>
            </div>
          ))}
        </div>
        <div className="feedback-row">
          <button className="btn" onClick={submit} disabled={busy}>
            {busy ? 'ASSESSING…' : 'SEAL + ASSESS'}
          </button>
          {result && (
            <button className="btn" onClick={onDone}>
              OPEN TRIAGE →
            </button>
          )}
        </div>
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
