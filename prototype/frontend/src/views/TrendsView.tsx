import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getTrends } from '../api';
import type { TrendsResponse } from '../types';

// Monochrome series: shade per entity, EIS solid / CAS dashed.
// Urgency is carried by line STYLE, never by hue.
const SHADES = ['#ffb000', '#d6d6d6', '#8f8f8f', '#7a5200', '#5a5a5a'];
const DASHES = ['', '6 3', '2 3', '10 3', '1 2'];

export default function TrendsView() {
  const [data, setData] = useState<TrendsResponse | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    getTrends()
      .then((t) => {
        if (!alive) return;
        if (!t) {
          setMissing(true);
        } else {
          setData(t);
          setSelected(Object.keys(t.series));
        }
      })
      .catch((e) => {
        if (alive)
          setError(e instanceof Error ? e.message : 'Failed to load trends');
      });
    return () => {
      alive = false;
    };
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.windows.map((w, i) => {
      const row: Record<string, string | number> = { window: w };
      for (const [eid, s] of Object.entries(data.series)) {
        row[`${eid} · EIS`] = s.EIS[i] ?? null as unknown as number;
        row[`${eid} · CAS`] = s.CAS[i] ?? null as unknown as number;
      }
      return row;
    });
  }, [data]);

  // /api/trends does not exist yet — hide gracefully, never crash.
  if (missing) {
    return (
      <div className="card">
        <h2>Trends</h2>
        <div className="muted">
          Trend history is not available on this backend (<span className="mono">/api/trends</span> returned
          404). This view is hidden until the endpoint ships — all other views
          work normally.
        </div>
      </div>
    );
  }
  if (error) return <div className="err">{error}</div>;
  if (!data) return <div className="loading">Loading trends…</div>;

  const ids = Object.keys(data.series);
  if (ids.length === 0) {
    return (
      <div className="card">
        <h2>Trends</h2>
        <div className="muted">No trend series returned by the backend.</div>
      </div>
    );
  }

  function toggle(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function chart(metric: 'EIS' | 'CAS') {
    return (
      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#222224" strokeDasharray="3 3" />
            <XAxis
              dataKey="window"
              tick={{ fill: '#96927f', fontSize: 11 }}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: '#96927f', fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{
                background: '#101011',
                border: '1px solid #333336',
                borderRadius: 0,
                color: '#e9e5d6',
              }}
            />
            <Legend />
            {selected.map((eid, i) => (
              <Line
                key={eid}
                type="monotone"
                dataKey={`${eid} · ${metric}`}
                stroke={SHADES[i % SHADES.length]}
                strokeWidth={metric === 'EIS' ? 2 : 1.5}
                strokeDasharray={
                  metric === 'EIS'
                    ? undefined
                    : DASHES[i % DASHES.length] || '5 3'
                }
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <h2>Trends — EIS / CAS per window</h2>
        <div>
          {ids.map((id) => (
            <label className="checkline" key={id}>
              <input
                type="checkbox"
                checked={selected.includes(id)}
                onChange={() => toggle(id)}
              />
              <span className="mono">{id}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>EIS across windows</h2>
        {chart('EIS')}
      </div>
      <div className="card">
        <h2>CAS across windows</h2>
        {chart('CAS')}
      </div>
    </div>
  );
}
