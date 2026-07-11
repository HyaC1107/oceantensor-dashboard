import { motion } from 'framer-motion';

const STATUS_CFG = {
  connected:    { dot: '#00FF88', label: 'ONLINE'  },
  connecting:   { dot: '#FFD700', label: 'SYNC...' },
  disconnected: { dot: '#FF4D4F', label: 'OFFLINE' },
  error:        { dot: '#FF4D4F', label: 'ERROR'   },
};

export default function TopBar({ status, lastUpdate, farmId }) {
  const { dot, label } = STATUS_CFG[status] ?? STATUS_CFG.disconnected;
  const isLive = status === 'connected';
  const timeStr = lastUpdate
    ? new Date(lastUpdate).toLocaleTimeString('ko-KR', { hour12: false })
    : '--:--:--';

  return (
    <header style={st.bar}>
      <div style={st.scanline} />

      {/* 좌 */}
      <div style={st.left}>
        <svg width={18} height={18} viewBox="0 0 18 18" style={{ flexShrink: 0 }}>
          <polygon points="9,1 17,14 1,14" fill="none" stroke="#00E5FF" strokeWidth="1.5"
            style={{ filter: 'drop-shadow(0 0 4px #00E5FF)' }}/>
          <circle cx="9" cy="10" r="2" fill="#00E5FF"/>
        </svg>
        <div>
          <div style={st.sysId}>TTORI OCEAN WATCH · SEAWEED DETECTION SYSTEM</div>
          <div style={st.title}>김 양식장 황백화 이상 징후 분석 대시보드</div>
        </div>
        <div style={st.farmBadge}>
          <span style={st.farmLabel}>FARM</span>
          <span style={st.farmId}>{farmId}</span>
        </div>
      </div>

      {/* 우 */}
      <div style={st.right}>
        <div style={st.statusChip}>
          <motion.div
            style={{ ...st.dot, background: dot, boxShadow: `0 0 8px ${dot}` }}
            animate={isLive ? { opacity: [0.4, 1, 0.4] } : {}}
            transition={{ duration: 1.4, repeat: Infinity }}
          />
          <span style={{ ...st.statusText, color: dot }}>{label}</span>
        </div>
        <div style={st.timeChip}>
          <span style={st.timeLabel}>LAST UPDATE</span>
          <span style={st.timeVal}>{timeStr}</span>
        </div>
        <div style={st.sep} />
        <a href="#admin" style={st.adminLink}>ADMIN</a>
      </div>
    </header>
  );
}

const st = {
  bar: {
    position: 'relative', flexShrink: 0,
    height: 46, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 18px',
    background: 'rgba(5,11,24,0.98)',
    borderBottom: '1px solid rgba(0,229,255,0.15)',
    overflow: 'hidden',
  },
  scanline: {
    position: 'absolute', inset: 0, pointerEvents: 'none',
    background: 'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,255,0.012) 2px,rgba(0,229,255,0.012) 3px)',
  },
  left:  { display: 'flex', alignItems: 'center', gap: 12, position: 'relative' },
  right: { display: 'flex', alignItems: 'center', gap: 14, position: 'relative' },
  sysId: {
    fontSize: 7, color: 'rgba(0,229,255,0.4)', letterSpacing: 3,
    fontFamily: 'Courier New,monospace', marginBottom: 2,
  },
  title: {
    fontSize: 13, fontWeight: 800, color: '#00E5FF', letterSpacing: 0.3,
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
    textShadow: '0 0 16px rgba(0,229,255,0.5)',
  },
  farmBadge: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    background: 'rgba(0,229,255,0.07)', border: '1px solid rgba(0,229,255,0.22)',
    borderRadius: 4, padding: '2px 10px',
  },
  farmLabel: { fontSize: 7, color: 'rgba(0,229,255,0.45)', letterSpacing: 3, fontFamily: 'Courier New,monospace' },
  farmId:    { fontSize: 11, color: '#00E5FF', fontWeight: 700, fontFamily: 'Courier New,monospace' },
  statusChip: { display: 'flex', alignItems: 'center', gap: 6 },
  dot: { width: 7, height: 7, borderRadius: '50%', flexShrink: 0 },
  statusText: { fontSize: 10, fontFamily: 'Courier New,monospace', fontWeight: 700, letterSpacing: 1 },
  timeChip: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' },
  timeLabel: { fontSize: 7, color: 'rgba(255,255,255,0.2)', letterSpacing: 2, fontFamily: 'Courier New,monospace' },
  timeVal:   { fontSize: 10, color: 'rgba(0,229,255,0.6)', fontFamily: 'Courier New,monospace' },
  sep: { width: 1, height: 22, background: 'rgba(255,255,255,0.1)' },
  adminLink: {
    color: 'rgba(255,255,255,0.2)', fontSize: 9, textDecoration: 'none',
    fontFamily: 'Courier New,monospace', letterSpacing: 2,
    border: '1px solid rgba(255,255,255,0.1)', padding: '3px 10px', borderRadius: 3,
  },
};
