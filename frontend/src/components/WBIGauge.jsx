import { PieChart, Pie, Cell } from 'recharts';

const SEVERITY_CONFIG = {
  NORMAL:  { color: '#22c55e', label: '정상',   bg: '#052e16' },
  CAUTION: { color: '#f59e0b', label: '주의',   bg: '#1c1400' },
  WARNING: { color: '#f97316', label: '경고',   bg: '#1c0a00' },
  DANGER:  { color: '#ef4444', label: '위험',   bg: '#1c0000' },
};

export default function WBIGauge({ wbiScore, severity }) {
  const score = wbiScore ?? 0;
  const cfg = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.NORMAL;

  // 반원 게이지용 데이터
  const filled = score;
  const empty  = 1 - score;
  const data   = [{ value: filled }, { value: empty }];

  return (
    <div style={{ ...styles.card, background: cfg.bg, borderColor: cfg.color }}>
      <div style={styles.title}>황백화 지수 (WBI)</div>

      <div style={styles.gaugeWrap}>
        <PieChart width={200} height={110}>
          <Pie
            data={data}
            cx={100} cy={100}
            startAngle={180} endAngle={0}
            innerRadius={60} outerRadius={85}
            dataKey="value"
            stroke="none"
          >
            <Cell fill={cfg.color} />
            <Cell fill="#1e293b" />
          </Pie>
        </PieChart>
        <div style={styles.scoreOverlay}>
          <span style={{ ...styles.scoreNum, color: cfg.color }}>
            {(score * 100).toFixed(1)}
          </span>
          <span style={styles.scoreUnit}>%</span>
        </div>
      </div>

      <div style={{ ...styles.badge, background: cfg.color }}>
        {cfg.label}
      </div>

      <div style={styles.thresholds}>
        <span style={{ color: '#22c55e' }}>● 정상 &lt;30</span>
        <span style={{ color: '#f59e0b' }}>● 주의 30~60</span>
        <span style={{ color: '#f97316' }}>● 경고 60~80</span>
        <span style={{ color: '#ef4444' }}>● 위험 ≥80</span>
      </div>
    </div>
  );
}

const styles = {
  card: {
    borderRadius: 12, padding: '20px 24px', border: '1px solid',
    textAlign: 'center', minWidth: 220,
  },
  title:       { color: '#94a3b8', fontSize: 13, marginBottom: 8 },
  gaugeWrap:   { position: 'relative', display: 'inline-block' },
  scoreOverlay:{
    position: 'absolute', bottom: 8, left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex', alignItems: 'baseline', gap: 2,
  },
  scoreNum:    { fontSize: 32, fontWeight: 800 },
  scoreUnit:   { color: '#94a3b8', fontSize: 14 },
  badge: {
    display: 'inline-block', padding: '4px 16px', borderRadius: 20,
    fontWeight: 700, fontSize: 14, color: '#fff', marginTop: 8,
  },
  thresholds: {
    display: 'flex', gap: 8, justifyContent: 'center',
    fontSize: 10, color: '#64748b', marginTop: 12, flexWrap: 'wrap',
  },
};
