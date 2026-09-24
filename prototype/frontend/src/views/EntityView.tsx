import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getEntity, postFeedback } from '../api';
import type { EntityDetail, Flag, ScoreBlock, ShapDriver } from '../types';

function severityClass(s: string): string {
  const v = (s || '').toLowerCase();
  if (v === 'critical') return 'critical';
  if (v === 'high') return 'high';
  if (v === 'medium') return 'medium';
  return 'low';
}

// SHAP shape is backend-version dependent — accept every known spelling,
// render if found, hide the section entirely if absent.
function extractShap(scores: ScoreBlock): ShapDriver[] | null {
  if (Array.isArray(scores.shap_drivers) && scores.shap_drivers.length > 0)
    return scores.shap_drivers;
  if (Array.isArray(scores.shap) && scores.shap.length > 0) return scores.shap;
  if (
    scores.shap_values &&
    typeof scores.shap_values === 'object' &&
    Object.keys(scores.shap_values).length > 0
  ) {
    return Object.entries(scores.shap_values).map(([feature, value]) => ({
      feature,
      value: typeof value === 'number' ? value : Number(value) || 0,
    }));
  }
  return null;
}

function ContribBars({
  title,
  contrib,
  kind,
}: {
  title: string;
  contrib?: Record<string, number>;
  kind: 'e' | 'c';
}) {
  const entries = Object.entries(contrib ?? {}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  const max = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));
  const data = entries.map(([k, v]) => ({ name: k, value: v }));
  return (
    <div>
      <h3>{title}</h3>
      {/* Recharts horizontal bars */}
      <div style={{ width: '100%', height: Math.max(120, entries.length * 36) }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 48 }}>
            <CartesianGrid stroke="#222224" strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fill: '#96927f', fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="name"
              width={160}
              tick={{ fill: '#e9e5d6', fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{
                background: '#101011',
                border: '1px solid #333336',
                borderRadius: 0,
                color: '#e9e5d6',
              }}
            />
            <Bar dataKey="value" radius={[0, 0, 0, 0]}>
              {data.map((d) => (
                <Cell
                  key={d.name}
                  fill={kind === 'e' ? '#ffb000' : '#7d93ad'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* Exact numeric readout (plain CSS, keeps values readable) */}
      {entries.map(([k, v]) => (
        <div className="contrib-row" key={k}>
          <span className="mono">{k}</span>
          <span className="bar">
            <span
              className={kind === 'e' ? 'fill-e' : 'fill-c'}
              style={{
                display: 'block',
                width: `${(Math.abs(v) / max) * 100}%`,
              }}
            />
          </span>
          <span className="mono">{v.toFixed(1)}</span>
        </div>
      ))}
    </div>
  );
}

function FlagCard({ flag }: { flag: Flag }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function decide(decision: 'confirm' | 'dismiss') {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const res = await postFeedback({
        entity_id: flag.entity_id ?? '',
        rule_id: flag.rule_id,
        decision,
        note: note || undefined,
      });
      setOk(`Recorded: ${res.status}`);
    } catch (e) {
      // /api/feedback may not exist yet — tolerate with an error message.
      setErr(e instanceof Error ? e.message : 'Feedback failed');
    } finally {
      setBusy(false);
    }
  }

  const firstRecords = (flag.records ?? []).slice(0, 5);
  return (
    <div className="flag">
      <div className="flag-head">
        <span className="badge mono">{flag.rule_id}</span>
        <span className={`badge ${severityClass(flag.severity)}`}>
          {String(flag.severity).toUpperCase()}
        </span>
        <span className="flag-title">{flag.title}</span>
      </div>
      <div className="muted" style={{ fontSize: 12.5 }}>
        {flag.evidence}
      </div>
      <dl className="ev-grid">
        <dt>Observed</dt>
        <dd className="mono">{String(flag.observed)}</dd>
        <dt>Expected</dt>
        <dd className="mono">{String(flag.expected)}</dd>
        <dt>Records</dt>
        <dd>
          <b>{flag.n_records}</b>{' '}
          {firstRecords.length > 0 && (
            <span className="record-ids">
              — first {firstRecords.length}: {firstRecords.join(', ')}
              {(flag.records ?? []).length > firstRecords.length ? ' …' : ''}
            </span>
          )}
        </dd>
      </dl>
      <div className="feedback-row">
        <button
          className="btn small"
          disabled={busy}
          onClick={() => void decide('confirm')}
        >
          Confirm
        </button>
        <button
          className="btn small"
          disabled={busy}
          onClick={() => void decide('dismiss')}
        >
          Dismiss
        </button>
        <input
          type="text"
          placeholder="note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      {err && <div className="err">{err}</div>}
      {ok && <div className="okmsg">{ok}</div>}
    </div>
  );
}

export default function EntityView({
  entityId,
  onBack,
}: {
  entityId: string;
  onBack: () => void;
}) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    getEntity(entityId)
      .then((d) => {
        if (alive) setDetail(d);
      })
      .catch((e) => {
        if (alive)
          setError(e instanceof Error ? e.message : 'Failed to load entity');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [entityId]);

  if (loading) return <div className="loading">Loading {entityId}…</div>;
  if (error) return <div className="err">{error}</div>;
  if (!detail) return <div className="err">No data for {entityId}</div>;

  const s = detail.scores;
  const shap = extractShap(s);

  return (
    <div>
      <button className="btn" onClick={onBack} style={{ marginBottom: 12 }}>
        ← Back to triage
      </button>
      <div className="card">
        <h2 className="mono">{detail.entity_id}</h2>
        <div>
          <span className={`band ${s.band}`}>{s.band}</span>{' '}
          <span className="muted">priority {Number(s.priority).toFixed(1)}</span>
        </div>
        <div className="score-cards">
          <div className="score-card">
            <div className="k">EIS</div>
            <div className="v">{Number(s.EIS).toFixed(1)}</div>
          </div>
          <div className="score-card">
            <div className="k">CAS</div>
            <div className="v">{Number(s.CAS).toFixed(1)}</div>
          </div>
          <div className="score-card">
            <div className="k">Priority</div>
            <div className="v">{Number(s.priority).toFixed(1)}</div>
          </div>
          <div className="score-card">
            <div className="k">Flags</div>
            <div className="v">{detail.flags.length}</div>
          </div>
        </div>
        <div className="grid2">
          <ContribBars
            title="Execution contributions (e_contrib)"
            contrib={s.e_contrib}
            kind="e"
          />
          <ContribBars
            title="Coverage contributions (c_contrib)"
            contrib={s.c_contrib}
            kind="c"
          />
        </div>
        {shap && (
          <div>
            <h3>SHAP drivers</h3>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Value / Contribution</th>
                </tr>
              </thead>
              <tbody>
                {shap.map((d, i) => (
                  <tr key={i}>
                    <td className="mono">
                      {String(d.feature ?? d.name ?? `driver_${i}`)}
                    </td>
                    <td className="mono">
                      {String(
                        d.contribution ?? d.value ?? JSON.stringify(d),
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Flags ({detail.flags.length})</h2>
        {detail.flags.length === 0 && (
          <div className="muted">No flags for this entity.</div>
        )}
        {detail.flags.map((f) => (
          <FlagCard key={f.rule_id} flag={{ ...f, entity_id: detail.entity_id }} />
        ))}
      </div>

      <div className="card">
        <h2>Signals</h2>
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <tbody>
              {Object.entries(detail.signals ?? {}).map(([k, v]) => (
                <tr key={k}>
                  <td className="mono muted">{k}</td>
                  <td className="mono">
                    {Array.isArray(v)
                      ? v.length > 0
                        ? v.slice(0, 8).join(', ') +
                          (v.length > 8 ? ` … (${v.length})` : '')
                        : '—'
                      : typeof v === 'object'
                        ? JSON.stringify(v)
                        : String(v)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {detail.ground_truth !== undefined && detail.ground_truth !== null && (
          <div style={{ marginTop: 8 }}>
            <h3>Ground truth (supervisory reference)</h3>
            <div className="mono muted" style={{ fontSize: 12 }}>
              {JSON.stringify(detail.ground_truth)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
