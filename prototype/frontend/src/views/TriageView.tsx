import {
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { EntitySummary } from '../types';

function bandColor(band: string): string {
  // Severity/status encoding — the one place charts use color.
  switch ((band || '').toUpperCase()) {
    case 'PRIORITY':
      return '#b0454d';
    case 'ELEVATED':
      return '#c08a3e';
    case 'WATCH':
      return '#6e6e6e';
    case 'CLEAR':
      return '#3d7a5c';
    default:
      return '#6e6e6e';
  }
}

interface Props {
  entities: EntitySummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function TriageView({ entities, selectedId, onSelect }: Props) {
  const sorted = [...entities].sort((a, b) => b.priority - a.priority);
  const points = sorted.map((e) => ({
    x: e.CAS,
    y: e.EIS,
    entity_id: e.entity_id,
    priority: e.priority,
    band: e.band,
  }));

  return (
    <div>
      <div className="card">
        <h2>Triage — EIS × CAS</h2>
        <div className="muted">
          X = CAS (coverage absence), Y = EIS (execution integrity). Upper-right
          = worst on both axes. Click a row to drill down.
        </div>
        <div style={{ width: '100%', height: 380, marginTop: 8 }}>
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 0 }}>
              <CartesianGrid stroke="#222224" strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="x"
                name="CAS"
                domain={[0, 100]}
                tick={{ fill: '#96927f', fontSize: 12 }}
                label={{
                  value: 'CAS',
                  position: 'insideBottomRight',
                  offset: -10,
                  fill: '#96927f',
                }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="EIS"
                domain={[0, 100]}
                tick={{ fill: '#96927f', fontSize: 12 }}
                label={{
                  value: 'EIS',
                  angle: -90,
                  position: 'insideLeft',
                  fill: '#96927f',
                }}
              />
              <Tooltip
                contentStyle={{
                  background: '#101011',
                  border: '1px solid #333336',
                  borderRadius: 0,
                  color: '#e9e5d6',
                }}
                formatter={(value, name) => [String(value), String(name)]}
              />
              {/* Supervisory thresholds on both axes */}
              {[25, 50, 70].map((v) => (
                <ReferenceLine
                  key={`y${v}`}
                  y={v}
                  stroke="#7a5200"
                  strokeDasharray="4 4"
                  strokeOpacity={0.7}
                />
              ))}
              {[25, 50, 70].map((v) => (
                <ReferenceLine
                  key={`x${v}`}
                  x={v}
                  stroke="#7a5200"
                  strokeDasharray="4 4"
                  strokeOpacity={0.5}
                />
              ))}
              <Scatter name="entities" data={points} fill="#ffb000">
                {points.map((p) => (
                  <Cell key={p.entity_id} fill={bandColor(p.band)} />
                ))}
                <LabelList
                  dataKey="entity_id"
                  position="top"
                  style={{ fill: '#e9e5d6', fontSize: 11 }}
                />
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h2>Entities (sorted by priority desc)</h2>
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Entity</th>
                <th>EIS</th>
                <th>CAS</th>
                <th>Priority</th>
                <th>Band</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((e) => (
                <tr
                  key={e.entity_id}
                  className={`clickable${selectedId === e.entity_id ? ' selected' : ''}`}
                  onClick={() => onSelect(e.entity_id)}
                >
                  <td className="mono">{e.entity_id}</td>
                  <td>{e.EIS.toFixed(1)}</td>
                  <td>{e.CAS.toFixed(1)}</td>
                  <td>
                    <b>{e.priority.toFixed(1)}</b>
                  </td>
                  <td>
                    <span className={`band ${e.band}`}>{e.band}</span>
                  </td>
                  <td>{e.n_flags}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
