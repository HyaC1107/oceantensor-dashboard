import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import MapPanel from './MapPanel';

// ── HUD TopBar ────────────────────────────────────────────────
function HudTopBar({ selectedSite }) {
  const timeStr = new Date().toLocaleTimeString('ko-KR', { hour12: false });

  return (
    <div style={{
      height: 46, flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px',
      background: 'rgba(5,11,24,0.95)',
      borderBottom: '1px solid rgba(0,229,255,0.14)',
    }}>
      {/* 좌 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <motion.div
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity }}
          style={{ width: 8, height: 8, borderRadius: '50%', background: '#FF4D4F', boxShadow: '0 0 8px #FF4D4F' }}
        />
        <div>
          <div style={{ fontSize: 8, color: 'rgba(0,229,255,0.45)', letterSpacing: 3, fontFamily: 'Courier New' }}>
            TTORI OCEAN WATCH · SEAWEED ANOMALY DETECTION SYSTEM
          </div>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#00E5FF', letterSpacing: 0.5 }}>
            해양 양식장 황백화 이상 징후 AI 관제센터
          </div>
        </div>
      </div>

      {/* 중앙 경보 */}
      <AnimatePresence>
        {selectedSite && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
            style={{
              position: 'absolute', left: '50%', transform: 'translateX(-50%)',
              display: 'flex', alignItems: 'center', gap: 7,
              background: 'rgba(255,77,79,0.12)', border: '1px solid rgba(255,77,79,0.45)',
              borderRadius: 4, padding: '4px 14px',
            }}>
            <motion.div
              animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 0.8, repeat: Infinity }}
              style={{ width: 6, height: 6, borderRadius: '50%', background: '#FF4D4F' }}
            />
            <span style={{ fontSize: 11, color: '#FF4D4F', fontWeight: 700, letterSpacing: 1, fontFamily: 'Courier New' }}>
              ALERT — {selectedSite.name}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 우 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        {[
          { label: 'SAT LINK',  val: '4/4',       col: '#00FF88' },
          { label: 'EDGE NODE', val: '12 ONLINE',  col: '#00E5FF' },
        ].map(({ label, val, col }) => (
          <div key={label} style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 7, color: 'rgba(255,255,255,0.5)', letterSpacing: 2, fontFamily: 'Courier New' }}>{label}</div>
            <div style={{ fontSize: 10, color: col, fontWeight: 700, fontFamily: 'Courier New' }}>{val}</div>
          </div>
        ))}
        <div style={{ borderLeft: '1px solid rgba(0,229,255,0.14)', paddingLeft: 16 }}>
          <div style={{ fontSize: 7, color: 'rgba(255,255,255,0.5)', letterSpacing: 2, fontFamily: 'Courier New' }}>KST</div>
          <div style={{ fontSize: 13, color: '#00E5FF', fontWeight: 700, fontFamily: 'Courier New' }}>{timeStr}</div>
        </div>
      </div>
    </div>
  );
}


// ── HUD 코너 장식 ─────────────────────────────────────────────
function HudCorners() {
  return (
    <>
      {[
        { top: 0, left: 0,     style: { borderTop: '1.5px solid rgba(0,229,255,0.5)', borderLeft: '1.5px solid rgba(0,229,255,0.5)' } },
        { top: 0, right: 0,    style: { borderTop: '1.5px solid rgba(0,229,255,0.5)', borderRight: '1.5px solid rgba(0,229,255,0.5)' } },
        { bottom: 0, left: 0,  style: { borderBottom: '1.5px solid rgba(0,229,255,0.5)', borderLeft: '1.5px solid rgba(0,229,255,0.5)' } },
        { bottom: 0, right: 0, style: { borderBottom: '1.5px solid rgba(0,229,255,0.5)', borderRight: '1.5px solid rgba(0,229,255,0.5)' } },
      ].map((c, i) => (
        <div key={i} style={{
          position: 'absolute', width: 16, height: 16,
          top: c.top, bottom: c.bottom, left: c.left, right: c.right,
          ...c.style, pointerEvents: 'none', zIndex: 900,
        }} />
      ))}
    </>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
export default function Dashboard({ onGoXai }) {
  const [selectedSite, setSelectedSite] = useState(null);
  const [isAnalyzing,  setIsAnalyzing]  = useState(false);

  const handleSiteSelect = useCallback((site) => {
    setSelectedSite(site);
    setIsAnalyzing(true);
    setTimeout(() => setIsAnalyzing(false), 1800);
  }, []);

  return (
    <div style={{
      flex: 1, minHeight: 0,
      display: 'flex', flexDirection: 'column',
      background: '#050B18',
      position: 'relative',
      overflow: 'hidden',
      fontFamily: "'Pretendard','Noto Sans KR','Courier New',monospace",
    }}>
      <HudCorners />

      {/* TopBar */}
      <HudTopBar selectedSite={selectedSite} />

      {/* 맵 풀스크린 */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <MapPanel
          onSiteSelect={handleSiteSelect}
          selectedSite={selectedSite}
          isAnalyzing={isAnalyzing}
          onClearSite={() => setSelectedSite(null)}
          onGoXai={onGoXai}
        />
      </div>
    </div>
  );
}
