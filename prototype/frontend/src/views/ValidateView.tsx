import { useEffect, useState } from 'react';
import { getValidate } from '../api';
import type { ValidateResponse } from '../types';

export default function ValidateView() {
  const [data, setData] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getValidate()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive)
          setError(e instanceof Error ? e.message : 'Validate load failed');
      });
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <div className="err">{error}</div>;
  if (!data) return <div className="loading">Loading validation…</div>;

  const checks = Object.entries(data.pattern_checks ?? {});
  const novalidation = data.precision == null;

  const fmt = (v: number | null) =>
    v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(2);

  return (
    <div>
      {novalidation && (
        <div className="card">
          <h2>No ground truth for this assessment</h2>
          <div className="muted">
            {data.note ??
              'Upload findings.csv with the submission to validate against manual review.'}{' '}
            Triage, flags and audit are unaffected.
          </div>
        </div>
      )}
      <div className="card">
        <h2>Validation vs manual review</h2>
        <div className="score-cards">
          <div className="score-card">
            <div className="k">Precision</div>
            <div className="v">{fmt(data.precision)}</div>
          </div>
          <div className="score-card">
            <div className="k">Recall</div>
            <div className="v">{fmt(data.recall)}</div>
          </div>
          <div className="score-card">
            <div className="k">Top-3 overlap</div>
            <div className="v">{data.top3_overlap ?? '—'}</div>
          </div>
          {data.tp !== undefined && (
            <div className="score-card">
              <div className="k">TP / FP / FN</div>
              <div className="v" style={{ fontSize: 16 }}>
                {data.tp} / {data.fp} / {data.fn}
              </div>
            </div>
          )}
          {data.risky_above_clean !== undefined && (
            <div className="score-card">
              <div className="k">Risky above clean</div>
              <div className="v" style={{ fontSize: 16 }}>
                {data.risky_above_clean ? (
                  <span className="pass">YES</span>
                ) : (
                  <span className="fail">NO</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="grid2">
        <div className="card">
          <h2>Ranked (tool)</h2>
          <ol className="mono">
            {(data.ranked ?? []).map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ol>
          <div className="muted">
            Tool top-3:{' '}
            <span className="mono">{(data.tool_top3 ?? []).join(', ') || '—'}</span>
          </div>
        </div>
        <div className="card">
          <h2>Manual review top-3</h2>
          <ol className="mono">
            {(data.manual_top3 ?? []).map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ol>
          <div className="muted">
            Overlap with tool: <b>{data.top3_overlap ?? '—'}</b> (ordering gap, not a
            miss — tool ranks by severity, manual list by review order).
          </div>
        </div>
      </div>

      {(data.sector_findings ?? []).length > 0 && (
        <div className="card">
          <h2>Sector dark spots (X2)</h2>
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Sector</th>
                  <th>Technique</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {(data.sector_findings ?? []).map((f, i) => (
                  <tr key={`${f.sector}-${f.technique_id}-${i}`}>
                    <td className="mono">{f.sector}</td>
                    <td>
                      <span className="badge high">{f.technique_id}</span>
                    </td>
                    <td>{f.evidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Pattern checks</h2>
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Entity</th>
                <th>Expected</th>
                <th>Fired</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {checks.map(([entity, c]) => (
                <tr key={entity}>
                  <td className="mono">{entity}</td>
                  <td className="mono">
                    {Array.isArray(c.expected) ? c.expected.join(' + ') : c.expected}
                    {c.missing && c.missing.length > 0 && (
                      <span className="fail"> missing: {c.missing.join(', ')}</span>
                    )}
                  </td>
                  <td className="mono">{(c.fired ?? []).join(', ') || '—'}</td>
                  <td>
                    {c.pass ? (
                      <span className="pass">PASS</span>
                    ) : (
                      <span className="fail">FAIL</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
