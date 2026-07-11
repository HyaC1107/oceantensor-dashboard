import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const SEV = {
  NORMAL:  { color: '#00FF88', label: '정상',   en: 'NORMAL'  },
  CAUTION: { color: '#FFD700', label: '주의',   en: 'CAUTION' },
  WARNING: { color: '#FF8A3D', label: '경고',   en: 'WARNING' },
  DANGER:  { color: '#FF4D4F', label: '위험',   en: 'DANGER'  },
};

function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

export default function AnomalyGauge({ score = 0.76, severity = 'WARNING' }) {
  const cfg = SEV[severity] ?? SEV.WARNING;
  const [display, setDisplay] = useState(0);
  const rafRef = useRef(null);

  // 카운트업 애니메이션
  useEffect(() => {
    const duration = 2000;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min((now - start) / duration, 1);
      setDisplay(easeOutCubic(t) * score);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [score]);

  // SVG 반원 게이지 파라미터
  const R = 82;
  const cx = 120, cy = 115;
  const sw = 13;
  const circum = Math.PI * R;
  const filled = display * circum;
  const gap    = circum - filled;

  // arc path (왼쪽→오른쪽 반원)
  const arcPath = `M ${cx - R} ${cy} A ${R} ${R} 0 0 1 ${cx + R} ${cy}`;

  // 눈금 위치
  const ticks = [0, 0.25, 0.5, 0.75, 1.0];

  return (
    <div className="flex flex-col items-center select-none">
      {/* 섹션 레이블 */}
      <div className="flex items-center gap-2 mb-2 self-start">
        <div className="w-1 h-4 rounded-full" style={{ background: cfg.color, boxShadow: `0 0 8px ${cfg.color}` }} />
        <span className="text-[10px] font-bold tracking-[3px] uppercase" style={{ color: cfg.color }}>
          AI ANOMALY SCORE
        </span>
      </div>

      <div className="relative">
        <svg width={240} height={148} viewBox="0 0 240 148">
          <defs>
            <filter id="gauge-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <linearGradient id="arc-grad" gradientUnits="userSpaceOnUse"
              x1={cx - R} y1={cy} x2={cx + R} y2={cy}>
              <stop offset="0%"   stopColor={cfg.color} stopOpacity="0.5" />
              <stop offset="60%"  stopColor={cfg.color} stopOpacity="0.9" />
              <stop offset="100%" stopColor={cfg.color} stopOpacity="1.0" />
            </linearGradient>
          </defs>

          {/* 눈금 */}
          {ticks.map((t, i) => {
            const angle = Math.PI - t * Math.PI;
            const x1 = cx + (R + 8)  * Math.cos(angle);
            const y1 = cy - (R + 8)  * Math.sin(angle);
            const x2 = cx + (R + 15) * Math.cos(angle);
            const y2 = cy - (R + 15) * Math.sin(angle);
            return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round"/>;
          })}

          {/* 눈금 라벨 */}
          {[['0', cx - R - 4, cy + 18], ['0.5', cx, cy - R - 16], ['1.0', cx + R + 4, cy + 18]].map(([lbl, x, y]) => (
            <text key={lbl} x={x} y={y} textAnchor="middle" fill="rgba(255,255,255,0.25)"
              fontSize="9" fontFamily="'Courier New', monospace">{lbl}</text>
          ))}

          {/* 배경 구간 색상 */}
          {[
            { from: 0,    to: 0.3,  col: '#00FF8820' },
            { from: 0.3,  to: 0.6,  col: '#FFD70020' },
            { from: 0.6,  to: 0.8,  col: '#FF8A3D20' },
            { from: 0.8,  to: 1.0,  col: '#FF4D4F20' },
          ].map(({ from, to, col }, i) => {
            const aStart = Math.PI - from * Math.PI;
            const aEnd   = Math.PI - to   * Math.PI;
            const x1 = cx + R * Math.cos(aStart), y1 = cy - R * Math.sin(aStart);
            const x2 = cx + R * Math.cos(aEnd),   y2 = cy - R * Math.sin(aEnd);
            return <path key={i}
              d={`M ${x1} ${y1} A ${R} ${R} 0 0 1 ${x2} ${y2}`}
              fill="none" stroke={col} strokeWidth={sw + 2} strokeLinecap="butt" />;
          })}

          {/* 배경 반원 */}
          <path d={arcPath} fill="none"
            stroke="rgba(30,58,95,0.8)" strokeWidth={sw} strokeLinecap="round" />

          {/* 채워진 반원 */}
          <path d={arcPath} fill="none"
            stroke="url(#arc-grad)" strokeWidth={sw} strokeLinecap="round"
            strokeDasharray={`${filled} ${gap}`}
            filter="url(#gauge-glow)" />

          {/* 중앙 점수 숫자 */}
          <text x={cx} y={cy - 22} textAnchor="middle"
            fill={cfg.color} fontSize="48" fontWeight="900"
            fontFamily="'Courier New', monospace"
            filter="url(#gauge-glow)">
            {display.toFixed(2)}
          </text>

          {/* 상태 영문 */}
          <text x={cx} y={cy - 3} textAnchor="middle"
            fill={cfg.color} fontSize="11" fontWeight="700" letterSpacing="5"
            opacity="0.95">
            {cfg.en}
          </text>

          {/* 상태 한국어 */}
          <text x={cx} y={cy + 13} textAnchor="middle"
            fill="rgba(255,255,255,0.35)" fontSize="10" letterSpacing="3">
            {cfg.label}
          </text>

          {/* 양 끝 장식 점 */}
          <circle cx={cx - R} cy={cy} r="4" fill={cfg.color} opacity="0.5" />
          <circle cx={cx + R} cy={cy} r="4" fill={cfg.color} opacity="0.5" />
        </svg>
      </div>

      {/* 등급 바 */}
      <div className="flex gap-1.5 mt-1">
        {Object.entries(SEV).map(([k, v]) => (
          <div key={k}
            className="px-2.5 py-0.5 rounded text-[9px] font-bold tracking-[2px] transition-all"
            style={{
              background: severity === k ? v.color : 'transparent',
              border: `1px solid ${v.color}${severity === k ? 'ff' : '44'}`,
              color:  severity === k ? '#000' : `${v.color}66`,
              boxShadow: severity === k ? `0 0 10px ${v.color}80` : 'none',
            }}>
            {k}
          </div>
        ))}
      </div>
    </div>
  );
}
