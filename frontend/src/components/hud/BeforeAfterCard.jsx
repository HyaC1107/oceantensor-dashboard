import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const CARDS = [
  {
    type: 'before',
    label: '정상',
    en: 'NORMAL STATE',
    color: '#00FF88',
    bg: 'linear-gradient(135deg, #003322 0%, #004433 40%, #002211 100%)',
    overlay: 'rgba(0,255,136,0.06)',
    icon: '🌿',
    stats: [
      { label: 'DO',    val: '8.4 mg/L' },
      { label: '수온',  val: '18.2 ℃'  },
      { label: '색상',  val: '암적갈색' },
    ],
    desc: '정상 엽체 · 광합성 활발',
  },
  {
    type: 'after',
    label: '황백화 발생',
    en: 'ANOMALY DETECTED',
    color: '#FF4D4F',
    bg: 'linear-gradient(135deg, #2a1500 0%, #3d1f00 40%, #1a0d00 100%)',
    overlay: 'rgba(255,77,79,0.08)',
    icon: '⚠️',
    stats: [
      { label: 'DO',    val: '5.1 mg/L' },
      { label: '수온',  val: '24.3 ℃'  },
      { label: '색상',  val: '황백·탈색' },
    ],
    desc: 'WBI 0.76 · 영양염류 결핍',
  },
];

function FieldViz({ card }) {
  // CSS로 구현한 시각화 (이미지 대체)
  return (
    <div className="relative w-full h-full overflow-hidden rounded-t"
      style={{ background: card.bg }}>
      {/* 격자 패턴 (양식장 구조) */}
      <div className="absolute inset-0"
        style={{
          backgroundImage: `
            linear-gradient(${card.color}18 1px, transparent 1px),
            linear-gradient(90deg, ${card.color}18 1px, transparent 1px)
          `,
          backgroundSize: '18px 18px',
        }}
      />
      {/* 물결 효과 */}
      <motion.div className="absolute bottom-0 left-0 right-0 h-8 opacity-30"
        style={{ background: `linear-gradient(180deg, transparent, ${card.color}40)` }}
        animate={{ opacity: [0.2, 0.4, 0.2] }}
        transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* 중앙 아이콘 */}
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1">
        <motion.div className="text-3xl"
          animate={card.type === 'after' ? { scale: [1, 1.1, 1] } : {}}
          transition={{ duration: 2, repeat: Infinity }}>
          {card.icon}
        </motion.div>
        {/* 상태 표시 도트들 */}
        <div className="flex gap-1.5 mt-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <motion.div key={i} className="w-1.5 h-1.5 rounded-full"
              style={{ background: card.color }}
              animate={{ opacity: card.type === 'after' ? [0.3, 1, 0.3] : 1 }}
              transition={{ duration: 1.2, delay: i * 0.2, repeat: card.type === 'after' ? Infinity : 0 }}
            />
          ))}
        </div>
      </div>
      {/* 오버레이 */}
      <div className="absolute inset-0 rounded-t" style={{ background: card.overlay }} />
    </div>
  );
}

export default function BeforeAfterCard() {
  const [hovered, setHovered] = useState(null);

  return (
    <div className="flex flex-col gap-2">
      {/* 섹션 레이블 */}
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-white/30" style={{ boxShadow: '0 0 6px rgba(255,255,255,0.4)' }} />
        <span className="text-[10px] font-bold tracking-[3px] text-white/50 uppercase">
          현장 비교 — Before / After
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {CARDS.map(card => (
          <motion.div key={card.type}
            className="hud-corner glass rounded overflow-hidden cursor-pointer"
            style={{
              borderColor: `${card.color}28`,
              boxShadow: hovered === card.type ? `0 0 24px ${card.color}44` : `0 0 8px ${card.color}12`,
            }}
            onHoverStart={() => setHovered(card.type)}
            onHoverEnd={() => setHovered(null)}
            whileHover={{ scale: 1.025, y: -2 }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}>

            {/* 비주얼 영역 */}
            <div className="h-[80px]">
              <FieldViz card={card} />
            </div>

            {/* 정보 영역 */}
            <div className="p-2">
              {/* 상태 헤더 */}
              <div className="flex items-center justify-between mb-1.5">
                <div>
                  <div className="text-[9px] font-mono tracking-widest"
                    style={{ color: `${card.color}88` }}>{card.en}</div>
                  <div className="text-[11px] font-bold" style={{ color: card.color }}>{card.label}</div>
                </div>
                {/* 상태 LED */}
                <motion.div className="w-2 h-2 rounded-full"
                  style={{ background: card.color, boxShadow: `0 0 6px ${card.color}` }}
                  animate={{ opacity: card.type === 'after' ? [0.4, 1, 0.4] : 1 }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
              </div>

              {/* 수치 */}
              <div className="flex flex-col gap-0.5">
                {card.stats.map(s => (
                  <div key={s.label} className="flex justify-between items-center">
                    <span className="text-[8px] text-white/30">{s.label}</span>
                    <span className="text-[9px] font-mono font-bold" style={{ color: card.color }}>{s.val}</span>
                  </div>
                ))}
              </div>

              {/* 설명 */}
              <div className="mt-1.5 text-[8px] text-white/25 border-t pt-1"
                style={{ borderColor: `${card.color}20` }}>
                {card.desc}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
