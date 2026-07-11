import { motion } from 'framer-motion';
import { FLOW_STEPS } from '../../data/dashboardDummy';

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.18, delayChildren: 0.1 } },
};
const nodeVar = {
  hidden:  { opacity: 0, scale: 0.7, y: 10 },
  visible: { opacity: 1, scale: 1,   y: 0, transition: { type: 'spring', stiffness: 260, damping: 20 } },
};
const arrowVar = {
  hidden:  { opacity: 0, scaleX: 0 },
  visible: { opacity: 1, scaleX: 1, transition: { duration: 0.25 } },
};

function StreamDots({ color }) {
  return (
    <div className="flex flex-col gap-0.5 items-center justify-center overflow-hidden h-5">
      {[0, 1, 2].map(i => (
        <motion.div key={i}
          className="w-0.5 h-0.5 rounded-full"
          style={{ background: color }}
          animate={{ opacity: [0, 1, 0], y: [-4, 0, 4] }}
          transition={{ duration: 0.8, delay: i * 0.2, repeat: Infinity, ease: 'easeInOut' }}
        />
      ))}
    </div>
  );
}

export default function TransformerFlow() {
  // 센서 + 이미지 → 융합 → 모델 → 출력
  const top = FLOW_STEPS.slice(0, 2);       // 센서, 이미지
  const rest = FLOW_STEPS.slice(2);          // 융합, 모델, 출력

  return (
    <div className="flex flex-col gap-3">
      {/* 섹션 레이블 */}
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-purple-500" style={{ boxShadow: '0 0 8px #8B5CF6' }} />
        <span className="text-[10px] font-bold tracking-[3px] text-purple-400 uppercase">
          Transformer 분석 흐름
        </span>
      </div>

      <motion.div
        className="flex items-center gap-0"
        variants={container} initial="hidden" animate="visible"
      >
        {/* 입력 2개 (세로 스택) */}
        <div className="flex flex-col gap-2">
          {top.map(step => (
            <motion.div key={step.id} variants={nodeVar}
              className="hud-corner glass rounded px-2.5 py-1.5 flex items-center gap-2 min-w-[110px]"
              style={{ borderColor: `${step.color}33`, boxShadow: `0 0 10px ${step.color}18` }}
              whileHover={{ boxShadow: `0 0 18px ${step.color}44`, scale: 1.02 }}>
              <span className="text-sm">{step.icon}</span>
              <div>
                <div className="text-[10px] font-bold" style={{ color: step.color }}>{step.label}</div>
                <div className="text-[8px] text-white/30 mt-0.5">{step.desc}</div>
              </div>
            </motion.div>
          ))}
        </div>

        {/* 수렴 화살표 */}
        <div className="flex flex-col items-center justify-center gap-4 mx-1">
          {top.map((s, i) => (
            <motion.div key={i} variants={arrowVar} className="flex items-center" style={{ originX: 0 }}>
              <StreamDots color={s.color} />
              <svg width="20" height="10" viewBox="0 0 20 10">
                <path d="M0 5 L16 5 L12 1 M16 5 L12 9"
                  stroke={s.color} strokeWidth="1.2" fill="none" strokeLinecap="round" opacity="0.7"/>
              </svg>
            </motion.div>
          ))}
        </div>

        {/* 나머지 노드 (융합→모델→출력) */}
        {rest.map((step, i) => (
          <div key={step.id} className="flex items-center">
            {/* 화살표 */}
            {i > 0 && (
              <motion.div variants={arrowVar} className="flex items-center mx-1" style={{ originX: 0 }}>
                <StreamDots color={step.color} />
                <svg width="18" height="10" viewBox="0 0 18 10">
                  <path d="M0 5 L14 5 L10 1 M14 5 L10 9"
                    stroke={step.color} strokeWidth="1.2" fill="none" strokeLinecap="round" opacity="0.7"/>
                </svg>
              </motion.div>
            )}

            <motion.div variants={nodeVar}
              className="hud-corner glass rounded px-2.5 py-1.5 flex flex-col items-center gap-0.5 min-w-[68px]"
              style={{ borderColor: `${step.color}33`, boxShadow: `0 0 10px ${step.color}18` }}
              whileHover={{ boxShadow: `0 0 20px ${step.color}55`, scale: 1.03 }}>
              {/* 중앙 아이콘에 pulse */}
              <motion.span className="text-base"
                animate={step.id === 'model' ? { scale: [1, 1.15, 1] } : {}}
                transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}>
                {step.icon}
              </motion.span>
              <div className="text-[9px] font-bold text-center leading-tight" style={{ color: step.color }}>
                {step.label}
              </div>
              <div className="text-[7px] text-white/25 text-center">{step.desc}</div>
            </motion.div>
          </div>
        ))}
      </motion.div>

      {/* 하단 실시간 처리 수치 */}
      <div className="flex gap-3">
        {[
          { label: 'Latency', val: '18 ms',  col: '#00E5FF' },
          { label: 'FPS',     val: '0.8 Hz', col: '#8B5CF6' },
          { label: 'Stage',   val: 'Lv.2',   col: '#FF8A3D' },
        ].map(({ label, val, col }) => (
          <div key={label} className="glass rounded px-2 py-1 flex-1 text-center"
            style={{ borderColor: `${col}22` }}>
            <div className="text-[8px] text-white/30 mb-0.5">{label}</div>
            <div className="text-[11px] font-bold font-mono" style={{ color: col }}>{val}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
