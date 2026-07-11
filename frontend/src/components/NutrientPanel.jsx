import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from 'recharts';

export default function NutrientPanel({ data }) {
  const din = data?.din ?? 0;
  const dip = data?.dip ?? 0;
  const np  = data?.np_ratio ?? 0;

  const barData = [
    { name: 'DIN', value: +din.toFixed(2), threshold: 5,   unit: 'μmol/L', danger: din < 5 },
    { name: 'DIP', value: +dip.toFixed(3), threshold: 0.3, unit: 'μmol/L', danger: dip < 0.3 },
  ];

  return (
    <div style={styles.card}>
      <div style={styles.title}>영양염 패널</div>

      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={barData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8 }}
            formatter={(v, n, props) => [`${v} ${props.payload.unit}`, n]}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {barData.map((entry, i) => (
              <Cell key={i} fill={entry.danger ? '#ef4444' : '#38bdf8'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div style={styles.npRow}>
        <span style={styles.npLabel}>N:P 비율</span>
        <span style={{ ...styles.npValue, color: np <= 16 ? '#ef4444' : '#22c55e' }}>
          {np.toFixed(1)}
        </span>
        <span style={styles.npHint}>임계값 ≤16 → 질소 제한 (황백화 위험)</span>
      </div>

      <div style={styles.thresholds}>
        <div style={styles.thItem}>
          <span style={{ color: din < 5 ? '#ef4444' : '#22c55e' }}>● DIN</span>
          <span style={styles.thDesc}>임계값 5 μmol/L — {din < 5 ? '⚠ 이하' : '정상'}</span>
        </div>
        <div style={styles.thItem}>
          <span style={{ color: dip < 0.3 ? '#ef4444' : '#22c55e' }}>● DIP</span>
          <span style={styles.thDesc}>임계값 0.3 μmol/L — {dip < 0.3 ? '⚠ 이하' : '정상'}</span>
        </div>
      </div>
    </div>
  );
}

const styles = {
  card:       { background: '#1e293b', borderRadius: 12, padding: '20px 24px', border: '1px solid #334155' },
  title:      { color: '#e2e8f0', fontSize: 14, fontWeight: 600, marginBottom: 12 },
  npRow:      { display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 12 },
  npLabel:    { color: '#94a3b8', fontSize: 12 },
  npValue:    { fontSize: 22, fontWeight: 700 },
  npHint:     { color: '#64748b', fontSize: 11 },
  thresholds: { marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4 },
  thItem:     { display: 'flex', gap: 8, alignItems: 'center' },
  thDesc:     { color: '#64748b', fontSize: 11 },
};
