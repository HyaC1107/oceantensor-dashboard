import { useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { motion } from 'framer-motion';
import { TIMELINE_DATA } from '../../data/dashboardDummy';

const SERIES = [
  { key: 'temp',     label: '수온',  unit: '℃',      color: '#FF8A3D', domain: [18, 28] },
  { key: 'do',       label: 'DO',    unit: 'mg/L',   color: '#00E5FF', domain: [4, 10]  },
  { key: 'salinity', label: '염분',  unit: 'PSU',    color: '#8B5CF6', domain: [30, 35] },
];

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass rounded px-3 py-2 text-[10px]" style={{ border: '1px solid rgba(0,229,255,0.25)' }}>
      <div className="text-white/40 mb-1 font-mono">{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} className="flex gap-2 items-center">
          <div className="w-2 h-0.5 rounded" style={{ background: p.color }} />
          <span className="text-white/60">{p.name}</span>
          <span className="font-bold font-mono ml-auto" style={{ color: p.color }}>
            {typeof p.value === 'number' ? p.value.toFixed(2) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function HudTimeline() {
  const [active, setActive] = useState('all');
  const data = TIMELINE_DATA.filter((_, i) => i % 2 === 0); // 12h 단위로 축소

  const visible = active === 'all' ? SERIES : SERIES.filter(s => s.key === active);

  return (
    <div className="flex flex-col gap-2">
      {/* 섹션 레이블 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full" style={{ background: '#00E5FF', boxShadow: '0 0 8px #00E5FF' }} />
          <span className="text-[10px] font-bold tracking-[3px] text-cyan-400 uppercase">
            시계열 — 최근 7일
          </span>
        </div>

        {/* 시리즈 토글 */}
        <div className="flex gap-1">
          <button onClick={() => setActive('all')}
            className="text-[8px] px-2 py-0.5 rounded font-bold tracking-wider transition-all"
            style={{
              background: active === 'all' ? 'rgba(0,229,255,0.15)' : 'transparent',
              border: `1px solid ${active === 'all' ? '#00E5FF' : 'rgba(255,255,255,0.1)'}`,
              color: active === 'all' ? '#00E5FF' : 'rgba(255,255,255,0.3)',
            }}>ALL</button>
          {SERIES.map(s => (
            <button key={s.key} onClick={() => setActive(s.key)}
              className="text-[8px] px-2 py-0.5 rounded font-bold tracking-wider transition-all"
              style={{
                background: active === s.key ? `${s.color}22` : 'transparent',
                border: `1px solid ${active === s.key ? s.color : 'rgba(255,255,255,0.1)'}`,
                color: active === s.key ? s.color : 'rgba(255,255,255,0.25)',
              }}>{s.label}</button>
          ))}
        </div>
      </div>

      {/* 차트 */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
        <ResponsiveContainer width="100%" height={110}>
          <LineChart data={data} margin={{ top: 4, right: 6, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="rgba(0,229,255,0.05)" />
            <XAxis dataKey="time"
              tick={{ fill: 'rgba(255,255,255,0.2)', fontSize: 7, fontFamily: 'Courier New' }}
              tickLine={false} axisLine={{ stroke: 'rgba(0,229,255,0.1)' }}
              interval={3}
            />
            <YAxis
              tick={{ fill: 'rgba(255,255,255,0.2)', fontSize: 8, fontFamily: 'Courier New' }}
              tickLine={false} axisLine={false} width={28}
            />
            <Tooltip content={<CustomTooltip />} />
            {/* 황백화 임계선 */}
            <ReferenceLine y={25} stroke="#FF4D4F" strokeDasharray="4 3" strokeWidth={0.8} opacity={0.6}
              label={{ value: '임계', position: 'insideTopRight', fill: '#FF4D4F', fontSize: 8 }} />

            {visible.map(s => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label}
                stroke={s.color} strokeWidth={1.5} dot={false}
                activeDot={{ r: 3, fill: s.color, stroke: s.color }}
                style={{ filter: `drop-shadow(0 0 4px ${s.color}88)` }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </motion.div>

      {/* 범례 */}
      <div className="flex gap-4 justify-center">
        {SERIES.map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="w-4 h-0.5 rounded" style={{ background: s.color, boxShadow: `0 0 4px ${s.color}` }} />
            <span className="text-[9px] text-white/40">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
