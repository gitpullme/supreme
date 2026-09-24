import { useEffect, useState } from 'react';
import { getAudit } from '../api';
import type { AuditResponse } from '../types';

function shortHash(h: unknown): string {
  const s = String(h ?? '');
  return s.length > 16 ? `${s.slice(0, 12)}…` : s;
}

export default function AuditView() {
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAudit()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : 'Audit load failed');
      });
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <div className="err">{error}</div>;
  if (!data) return <div className="loading">Loading audit ledger…</div>;

  return (
    <div>
      <div className="card">
        <h2>Audit ledger</h2>
        {data.verified ? (
          <div className="okmsg">
            ✓ VERIFIED — {data.message || 'hash chain intact'}
          </div>
        ) : (
          <div className="err">
            ✗ VERIFICATION FAILED — {data.message || 'hash chain mismatch'}
          </div>
        )}
        <div className="muted">{data.events.length} chained events.</div>
      </div>
      <div className="card">
        <h2>Events</h2>
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Seq</th>
                <th>TS</th>
                <th>Event</th>
                <th>Payload</th>
                <th>Prev hash</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <tr key={e.seq ?? i}>
                  <td className="mono">{e.seq}</td>
                  <td className="mono">{String(e.ts)}</td>
                  <td className="mono">{e.event}</td>
                  <td
                    className="mono muted"
                    style={{ maxWidth: 320, wordBreak: 'break-word' }}
                  >
                    {typeof e.payload === 'string'
                      ? e.payload.slice(0, 200)
                      : JSON.stringify(e.payload)?.slice(0, 200)}
                  </td>
                  <td className="mono muted">{shortHash(e.prev_hash)}</td>
                  <td className="mono muted">{shortHash(e.hash)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
