/**
 * ForecastChart — 7일 ADI(황백화 강도) 예측 궤적 + 밴드
 *
 * `/predict/forecast` 는 **sensor_vals 를 보내지 않으면 v13 실제 7일 ADI 궤적**을 서빙하고
 * (method="stmmt-v13"), 보내면 WBI 공식 통계추정으로 빠진다(predict.py:385).
 * 🔴 2026-07-17: 과거엔 snapshot.sensor_vals 를 보내 공식 경로를 타고 있었다
 *   (같은 어장이 v13 0.995 ↔ 공식 0.168 = 6배 차이 → 지도와 어긋난 원인 중 하나).
 *   이제 farm 만 받아 v13 경로를 탄다. **snapshot prop 을 되살리지 말 것.**
 *
 * ⚠️ 이 차트의 y = ADI/10(**강도**)이고, XAI 헤더 배지 = warn(**7일내 발생확률**)이다.
 *    서로 다른 물리량이라 임계도 다르다 → 색은 ADI 등급 SSOT(1/5/8)를 따른다.
 */
import { useState, useEffect } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { STAGE_LABEL } from '../data/v13Predictions';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ADI 등급 경계(학습 SSOT `channel_builder` = 1/5/8) → wbi 스케일(=adi/10) 0.1/0.5/0.8.
// 2026-07-17: 구 WBI 임계(0.3/0.6/0.8)에서 교체 — 그 값은 XAI에서 제거한 severityLabel의 것이라
//             차트만 다른 기준으로 색칠하고 있었다(리뷰어 지적).
const ADI_STAGE_TH = [0.1, 0.5, 0.8];
const STAGE_COLOR  = ['#22c55e', '#f59e0b', '#f97316', '#ef4444'];

function stageOf(wbi) {
  if (wbi == null) return 0;
  if (wbi >= ADI_STAGE_TH[2]) return 3;
  if (wbi >= ADI_STAGE_TH[1]) return 2;
  if (wbi >= ADI_STAGE_TH[0]) return 1;
  return 0;
}
const sevColor = (wbi) => STAGE_COLOR[stageOf(wbi)];

export default function ForecastChart({ farm }) {
  const [data, setData] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!farm) return;
    setLoading(true); setData(null);
    fetch(`${API_BASE}/predict/forecast`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      // sensor_vals 를 넣지 않는다 = v13 경로(위 주석 참조)
      body: JSON.stringify({ farm_id: farm.id }),
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
        {/* 헤더 배지(warn=발생확률)와 다른 물리량임을 제목에서 구분 — 둘 다 '%'로 보이면 오독된다 */}
        <span style={st.title}>7일 황백화 강도(ADI) 예측</span>
        {meta && (
          <span style={st.peak}>
            정점 <b style={{ color: lineColor }}>
              +{meta.peak_day}일 ADI {(meta.peak_wbi * 10).toFixed(1)}
            </b>
            <span style={{ color: 'rgba(255,255,255,0.4)', marginLeft: 6, fontSize: 10 }}>
              ({STAGE_LABEL[stageOf(meta.peak_wbi)]}{meta.method ? ` · ${meta.method}` : ''}
              {meta.source_date ? ` · ${meta.source_date} 기준` : ''})
            </span>
          </span>
        )}
      </div>

      {loading && <div style={st.loading}>예측 계산 중...</div>}
      {data && data.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 4 }}>
            {/* v13 경로는 day가 1부터 시작한다(predict.py: enumerate(adi7, start=1)) → '오늘' 분기 없음 */}
            <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 10 }}
                   tickFormatter={d => (d === 0 ? '오늘' : `+${d}일`)} />
            <YAxis domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 10 }}
                   tickFormatter={v => `${(v * 10).toFixed(0)}`} width={28} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6, fontSize: 11 }}
              labelFormatter={d => d === 0 ? '오늘' : `${d}일 후`}
              formatter={(v, name) => {
                if (name === 'band') return [`ADI ${(v[0] * 10).toFixed(1)}~${(v[1] * 10).toFixed(1)}`, '신뢰구간'];
                return [`ADI ${(v * 10).toFixed(1)} (${STAGE_LABEL[stageOf(v)]})`, '예측 강도'];
              }} />
            {/* 발생 임계 = ADI 5 (warn 헤드의 정의 P(7일 max ADI≥5)와 동일 기준) */}
            <ReferenceLine y={0.5} stroke="#f97316" strokeDasharray="4 3"
                           label={{ value: '발생 임계 ADI 5', fill: '#f97316', fontSize: 9, position: 'insideTopRight' }} />
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
