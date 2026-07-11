import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

export default function TimeSeriesChart({ history }) {
  const chartData = history.map((d) => ({
    time: new Date(d.ts).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    수온: d.water_temp,
    DO: d.dissolved_oxygen,
    WBI: +(d.wbi_score * 10).toFixed(2), // 0~1 → 0~10 스케일 맞춤
  }));

  return (
    <div style={styles.card}>
      <div style={styles.title}>실시간 시계열 <span style={styles.hint}>(WBI×10 스케일)</span></div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8 }}
            labelStyle={{ color: '#94a3b8' }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
          <Line type="monotone" dataKey="수온" stroke="#38bdf8" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="DO"   stroke="#22c55e" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="WBI"  stroke="#f97316" dot={false} strokeWidth={2} strokeDasharray="4 2" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const styles = {
  card:  { background: '#1e293b', borderRadius: 12, padding: '20px 24px', border: '1px solid #334155' },
  title: { color: '#e2e8f0', fontSize: 14, fontWeight: 600, marginBottom: 16 },
  hint:  { color: '#64748b', fontSize: 11, fontWeight: 400 },
};
