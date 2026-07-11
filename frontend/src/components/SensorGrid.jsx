function SensorCard({ label, value, unit, warn, danger, icon }) {
  const num = value ?? null;
  let color = '#22c55e';
  if (num !== null && danger !== undefined && num >= danger) color = '#ef4444';
  else if (num !== null && warn !== undefined && num >= warn) color = '#f59e0b';

  return (
    <div style={styles.card}>
      <div style={styles.iconRow}>{icon}</div>
      <div style={styles.label}>{label}</div>
      <div style={{ ...styles.value, color }}>
        {num !== null ? num.toFixed(2) : '—'}
      </div>
      <div style={styles.unit}>{unit}</div>
    </div>
  );
}

export default function SensorGrid({ data }) {
  const np = data?.np_ratio ?? null;

  return (
    <div style={styles.grid}>
      <SensorCard
        icon="🌡️" label="수온" unit="℃"
        value={data?.water_temp}
        warn={22} danger={25}
      />
      <SensorCard
        icon="💧" label="용존산소 (DO)" unit="mg/L"
        value={data?.dissolved_oxygen}
        warn={6} danger={4}
      />
      <SensorCard
        icon="🧪" label="DIN (용존무기질소)" unit="μmol/L"
        value={data?.din}
        /* 낮을수록 위험 — 5 이하 경고 */
        warn={null} danger={null}
      />
      <SensorCard
        icon="⚖️" label="N:P 비율" unit=""
        value={np}
        warn={null} danger={null}
      />
    </div>
  );
}

const styles = {
  grid: {
    display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16,
    padding: '0 24px',
  },
  card: {
    background: '#1e293b', borderRadius: 12, padding: '20px 16px',
    textAlign: 'center', border: '1px solid #334155',
  },
  iconRow: { fontSize: 24, marginBottom: 8 },
  label:  { color: '#94a3b8', fontSize: 12, marginBottom: 4 },
  value:  { fontSize: 28, fontWeight: 700, marginBottom: 4 },
  unit:   { color: '#64748b', fontSize: 11 },
};
