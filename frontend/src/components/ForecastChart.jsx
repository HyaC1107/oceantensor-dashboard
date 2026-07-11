/**
 * ForecastChart — 7일 황백화 위험도 예측 + 신뢰밴드
 *
 * /predict/forecast 로 7일 WBI 궤적(밴드 포함)을 받아 ComposedChart로 표시.
 * 현재는 통계적 추정(method=statistical-estimate). 시계열 모델 도입 시 동일 슬롯 사용.
 */
import { useState, useEffect } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function sevColor(wbi) {
  if (wbi < 0.3) return '#22c55e';
  if (wbi < 0.6) return '#f59e0b';
  if (wbi < 0.8) return '#f97316';
  return '#ef4444';
}

export default function ForecastChart({ farm, snapshot }) {
  const [data, setData] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!farm) return;
    setLoading(true); setData(null);
    fetch(`${API_BASE}/predict/forecast`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ farm_id: farm.id, sensor_vals: snapshot?.sensor_vals }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(j => {
        setMeta(j);
        setData(j.series.map(s => ({ day: s.day, wbi: s.wbi, band: [s.lower, s.upper] })));
      })
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [farm?.id]);   // eslint-disable-line

  const lineColor = meta ? sevColor(meta.peak_wbi) : '#818cf8';

  return (
    <div>
      <div style={st.head}>
        <span style={st.title}>7일 황백화 위험도 예측</span>
        {meta && (
          <span style={st.peak}>
            정점 <b style={{ color: lineColor }}>+{meta.peak_day}일 {(meta.peak_wbi * 100).toFixed(0)}%</b>
          </span>
        )}
      </div>

      {loading && <div style={st.loading}>예측 계산 중...</div>}
      {data && data.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 4 }}>
            <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 10 }}
                   tickFormatter={d => d === 0 ? '오늘' : `+${d}일`} />
            <YAxis domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 10 }}
                   tickFormatter={v => `${Math.round(v * 100)}%`} width={36} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6, fontSize: 11 }}
              labelFormatter={d => d === 0 ? '오늘' : `${d}일 후`}
              formatter={(v, name) => {
                if (name === 'band') return [`${Math.round(v[0] * 100)}~${Math.round(v[1] * 100)}%`, '신뢰구간'];
                return [`${Math.round(v * 100)}%`, '예측 위험도'];
              }} />
            <ReferenceLine y={0.6} stroke="#f97316" strokeDasharray="4 3"
                           label={{ value: '경고선 60%', fill: '#f97316', fontSize: 9, position: 'insideTopRight' }} />
            <Area dataKey="band" stroke="none" fill={lineColor} fillOpacity={0.14} />
            <Line dataKey="wbi" stroke={lineColor} strokeWidth={2}
                  dot={{ r: 3, fill: lineColor }} activeDot={{ r: 5 }} />
          </ComposedChart>
        </ResponsiveContainer>
      )}
      <div style={st.note}>
        ※ {meta?.method === 'statistical-estimate'
          ? '모델 학습 전 통계적 추정(평균회귀+드리프트)'
          : `모델 예측 (${meta?.method ?? '-'})`} · 밴드 = 불확실성 구간
      </div>
    </div>
  );
}

const st = {
  head:    { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  title:   { color: '#94a3b8', fontSize: 13, fontWeight: 600 },
  peak:    { color: '#64748b', fontSize: 11 },
  loading: { color: '#f59e0b', fontSize: 12, textAlign: 'center', padding: 30 },
  note:    { color: '#475569', fontSize: 9, lineHeight: 1.5, marginTop: 6 },
};
