import { useEffect, useRef } from 'react';

const SEVERITY_STYLE = {
  NORMAL:  { color: '#22c55e', icon: '✅' },
  CAUTION: { color: '#f59e0b', icon: '⚠️' },
  WARNING: { color: '#f97316', icon: '🔶' },
  DANGER:  { color: '#ef4444', icon: '🚨' },
};

function buildAlerts(history) {
  return history
    .filter((d) => d.severity !== 'NORMAL')
    .slice(-20)
    .reverse()
    .map((d, i) => ({
      id: i,
      time: new Date(d.ts).toLocaleTimeString('ko-KR'),
      severity: d.severity,
      msg: buildMessage(d),
    }));
}

function buildMessage(d) {
  const parts = [];
  if (d.din < 5)  parts.push(`DIN ${d.din.toFixed(1)} μmol/L (임계값 이하)`);
  if (d.water_temp > 25) parts.push(`수온 ${d.water_temp.toFixed(1)}℃ (25℃ 초과)`);
  if (d.wbi_score > 0.6) parts.push(`WBI ${(d.wbi_score * 100).toFixed(0)}%`);
  return parts.length ? parts.join(' | ') : `황백화 ${d.severity}`;
}

export default function AlertFeed({ history }) {
  const alerts = buildAlerts(history);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [alerts.length]);

  return (
    <div style={styles.card}>
      <div style={styles.title}>경보 로그 <span style={styles.count}>{alerts.length}건</span></div>
      <div style={styles.feed}>
        {alerts.length === 0 ? (
          <div style={styles.empty}>정상 범위 운영 중</div>
        ) : (
          alerts.map((a) => {
            const cfg = SEVERITY_STYLE[a.severity] ?? SEVERITY_STYLE.CAUTION;
            return (
              <div key={a.id} style={styles.item}>
                <span style={styles.time}>{a.time}</span>
                <span style={{ ...styles.badge, background: cfg.color }}>
                  {cfg.icon} {a.severity}
                </span>
                <span style={styles.msg}>{a.msg}</span>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}

const styles = {
  card:  { background: '#1e293b', borderRadius: 12, padding: '20px 24px', border: '1px solid #334155' },
  title: { color: '#e2e8f0', fontSize: 14, fontWeight: 600, marginBottom: 12 },
  count: { color: '#64748b', fontSize: 12, fontWeight: 400, marginLeft: 6 },
  feed:  { maxHeight: 180, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 },
  item:  { display: 'flex', alignItems: 'center', gap: 8 },
  time:  { color: '#64748b', fontSize: 11, minWidth: 64 },
  badge: { fontSize: 10, fontWeight: 700, color: '#fff', padding: '2px 8px', borderRadius: 10 },
  msg:   { color: '#cbd5e1', fontSize: 12 },
  empty: { color: '#22c55e', fontSize: 13, textAlign: 'center', padding: '20px 0' },
};
