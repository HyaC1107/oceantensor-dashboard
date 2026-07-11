import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { CAUSATION_DATA } from '../../data/dashboardDummy';

export default function CausationChart({ data = CAUSATION_DATA }) {
  const [animated, setAnimated] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 300);
    return () => clearTimeout(t);
  }, []);

  const total = data.reduce((s, d) => s + d.value, 0) || 1;

  return (
    <div className="flex flex-col gap-2.5">
      {/* 섹션 레이블 */}
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-orange-400" style={{ boxShadow: '0 0 8px #FF8A3D' }} />
        <span className="text-[10px] font-bold tracking-[3px] text-orange-400 uppercase">
          Causal Contribution
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {data.map((item, i) => {
          const pct = Math.round((item.value / total) * 100);
          return (
            <motion.div key={item.label}
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.1 + 0.2 }}>
              {/* 라벨 + 퍼센트 */}
              <div className="flex justify-between items-center mb-1">
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ background: item.color, boxShadow: `0 0 5px ${item.color}` }} />
                  <span className="text-[10px] text-white/70">{item.label}</span>
                </div>
                <span className="text-[10px] font-bold font-mono" style={{ color: item.color }}>{pct}%</span>
              </div>

              {/* 바 */}
              <div className="relative h-2 rounded-full overflow-hidden"
                style={{ background: `${item.color}14` }}>
                {/* 배경 그리드 라인 */}
                {[25, 50, 75].map(p => (
                  <div key={p} className="absolute top-0 bottom-0 w-px"
                    style={{ left: `${p}%`, background: 'rgba(255,255,255,0.06)' }} />
                ))}

                {/* 채워진 바 */}
                <motion.div
                  className="absolute top-0 left-0 h-full rounded-full"
                  style={{
                    background: `linear-gradient(90deg, ${item.color}80, ${item.color})`,
                    boxShadow: `0 0 8px ${item.color}88`,
                  }}
                  initial={{ width: 0 }}
                  animate={{ width: animated ? `${pct}%` : 0 }}
                  transition={{ duration: 1.2, delay: i * 0.12 + 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
                />

                {/* 끝단 발광점 */}
                <motion.div
                  className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full"
                  style={{ background: item.color, boxShadow: `0 0 6px ${item.color}` }}
                  initial={{ left: 0 }}
                  animate={{ left: animated ? `calc(${pct}% - 4px)` : 0 }}
                  transition={{ duration: 1.2, delay: i * 0.12 + 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
                />
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
