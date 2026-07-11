import { motion, AnimatePresence } from 'framer-motion';

function scoreColor(s) {
  if (s > 0.8) return '#FF4D4F';
  if (s > 0.6) return '#FF8A3D';
  if (s > 0.4) return '#FFD700';
  return '#00FF88';
}
function scoreSev(s) {
  if (s > 0.8) return 'DANGER';
  if (s > 0.6) return 'WARNING';
  if (s > 0.4) return 'CAUTION';
  return 'NORMAL';
}

// 사이트별 더미 센서 데이터
const SENSORS = {
  A1: { temp: 24.8, do: 4.9, sal: 33.1 },
  A2: { temp: 24.3, do: 5.1, sal: 32.8 },
  A3: { temp: 23.9, do: 5.8, sal: 33.4 },
  N1: { temp: 19.2, do: 8.1, sal: 32.2 },
  N2: { temp: 20.1, do: 7.8, sal: 32.5 },
  N3: { temp: 21.5, do: 7.2, sal: 32.9 },
  N4: { temp: 18.9, do: 8.4, sal: 32.0 },
};

// 미니 스파크라인 (7포인트 SVG)
function Sparkline({ color, inverted = false }) {
  const pts = Array.from({ length: 8 }, (_, i) => {
    const trend = inverted ? -i * 0.5 : i * 0.5;
    return 40 - (trend + (Math.random() - 0.5) * 6);
  });
  const path = pts.map((y, x) => `${x === 0 ? 'M' : 'L'}${x * 10} ${Math.max(4, Math.min(44, y))}`).join(' ');
  return (
    <svg width={70} height={28} viewBox="0 0 70 48" style={{ opacity: 0.7 }}>
      <path d={path} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={70} cy={Math.max(4, Math.min(44, pts[pts.length - 1]))} r="2.5" fill={color} />
    </svg>
  );
}

export default function FarmCard({ site, onClose }) {
  if (!site) return null;

  const col = scoreColor(site.score);
  const sev = scoreSev(site.score);
  const s   = SENSORS[site.id] ?? { temp: 22.0, do: 6.5, sal: 32.5 };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={site.id}
        initial={{ opacity: 0, y: 24, scale: 0.93 }}
        animate={{ opacity: 1, y: 0,  scale: 1 }}
        exit={{    opacity: 0, y: 16, scale: 0.95 }}
        transition={{ type: 'spring', stiffness: 300, damping: 26 }}
        style={{
          position: 'absolute', bottom: 96, left: 16, width: 270, zIndex: 700,
          background: 'rgba(5,11,24,0.93)',
          backdropFilter: 'blur(22px)',
          border: `1px solid ${col}44`,
          borderRadius: 12,
          boxShadow: `0 0 40px ${col}1a, 0 12px 40px rgba(0,0,0,0.7)`,
          overflow: 'hidden',
          pointerEvents: 'all',
        }}>

        {/* 상단 액센트 라인 */}
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          style={{
            height: 2, transformOrigin: 'left',
            background: `linear-gradient(90deg, ${col}, ${col}55, transparent)`,
          }}
        />

        {/* 헤더 */}
        <div style={{ padding: '11px 14px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 8, color: `${col}88`, fontFamily: 'Courier New', letterSpacing: 3, marginBottom: 3 }}>
              FARM ANALYSIS
            </div>
            <div style={{ fontSize: 14, fontWeight: 800, color: '#fff', lineHeight: 1.2 }}>
              {site.name}
            </div>
            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.52)', fontFamily: 'Courier New', marginTop: 3 }}>
              {site.lat.toFixed(4)}°N · {site.lon.toFixed(4)}°E
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
            <button onClick={onClose} style={{
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.4)', width: 22, height: 22, borderRadius: 5,
              cursor: 'pointer', fontSize: 10, lineHeight: '22px', textAlign: 'center',
              padding: 0,
            }}>✕</button>
            <motion.div
              animate={{ opacity: [0.7, 1, 0.7] }}
              transition={{ duration: 1.8, repeat: Infinity }}
              style={{
                padding: '2px 8px', borderRadius: 4, fontSize: 8, fontWeight: 700,
                letterSpacing: 2, fontFamily: 'Courier New',
                background: `${col}18`, border: `1px solid ${col}55`, color: col,
              }}>{sev}</motion.div>
          </div>
        </div>

        {/* 이상 점수 바 */}
        <div style={{ padding: '10px 14px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
            <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.55)', fontFamily: 'Courier New', letterSpacing: 2 }}>
              ANOMALY SCORE
            </span>
            <span style={{ fontSize: 20, fontWeight: 900, color: col, fontFamily: 'Courier New', lineHeight: 1 }}>
              {site.score.toFixed(2)}
            </span>
          </div>

          {/* 구간 바 */}
          <div style={{ height: 7, borderRadius: 4, overflow: 'hidden', position: 'relative',
            background: 'rgba(255,255,255,0.05)' }}>
            {[
              [0, 0.4, '#00FF8830'],
              [0.4, 0.6, '#FFD70030'],
              [0.6, 0.8, '#FF8A3D30'],
              [0.8, 1.0, '#FF4D4F30'],
            ].map(([from, to, bg]) => (
              <div key={from} style={{
                position: 'absolute', top: 0, bottom: 0,
                left: `${from * 100}%`, width: `${(to - from) * 100}%`, background: bg,
              }} />
            ))}
            <motion.div
              initial={{ width: 0 }} animate={{ width: `${site.score * 100}%` }}
              transition={{ duration: 0.9, delay: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
              style={{
                position: 'absolute', top: 0, left: 0, height: '100%',
                background: `linear-gradient(90deg, ${col}70, ${col})`,
                boxShadow: `0 0 10px ${col}`,
                borderRadius: 4,
              }}
            />
          </div>
        </div>

        {/* 센서 3개 + 스파크라인 */}
        <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {[
            { label: '수온',  val: `${s.temp}`,  unit: '℃',    col: '#FF8A3D', inverted: false },
            { label: 'DO',   val: `${s.do}`,   unit: 'mg/L', col: '#00E5FF', inverted: true  },
            { label: '염분', val: `${s.sal}`,  unit: 'PSU',  col: '#8B5CF6', inverted: false },
          ].map(({ label, val, unit, col: c, inverted }) => (
            <div key={label} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              background: 'rgba(255,255,255,0.03)', borderRadius: 6, padding: '4px 10px',
              border: `1px solid ${c}12`,
            }}>
              <div>
                <div style={{ fontSize: 8, color: 'rgba(255,255,255,0.5)', marginBottom: 1 }}>{label}</div>
                <div style={{ fontSize: 13, fontWeight: 700, fontFamily: 'Courier New', color: c }}>
                  {val} <span style={{ fontSize: 9, opacity: 0.6 }}>{unit}</span>
                </div>
              </div>
              <Sparkline color={c} inverted={inverted} />
            </div>
          ))}
        </div>

        {/* 버튼 */}
        <div style={{ padding: '0 14px 12px', display: 'flex', gap: 6 }}>
          <button
            style={{
              flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 9, fontWeight: 700,
              letterSpacing: 1.5, cursor: 'pointer', fontFamily: 'Courier New',
              background: `${col}18`, border: `1px solid ${col}50`, color: col,
            }}
            onMouseEnter={e => { e.currentTarget.style.background = `${col}30`; }}
            onMouseLeave={e => { e.currentTarget.style.background = `${col}18`; }}
          >상세 분석 →</button>
          <button style={{
            flex: 1, padding: '7px 0', borderRadius: 6, fontSize: 9, fontWeight: 700,
            letterSpacing: 1.5, cursor: 'pointer', fontFamily: 'Courier New',
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
            color: 'rgba(255,255,255,0.6)',
          }}>알림 설정</button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
