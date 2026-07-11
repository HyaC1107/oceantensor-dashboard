/**
 * XaiAnalysisTab — 어장 선택형 풀사이즈 XAI 분석 페이지
 *
 * 양식장 맵의 인포패널(좁음)과 달리, 한 어장을 깊게 파는 전용 탭.
 * 재활용: farmDummy(어장별 결정론 더미) → /predict(Attention 기여도)
 *         → /explain/llm(Gemini 자연어) + XaiHeatmapOverlay(엽체 히트맵).
 *
 * 기존 AttentionMap 탭이 mock에서 pred_id=null로 비어있던 문제를
 * pred_id 의존 제거(더미 sensor_vals 직접 전달)로 해결.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { ALL_FARMS, getFarm } from '../data/realFarms';
import FarmPicker from './FarmPicker';
import { farmDummy } from '../data/farmDummy';
import { fetchRealSensorByLatLon, provenanceLabel } from '../data/realSensor';
import { XAI_EXPLANATIONS, statusToKey, SEVERITY_COLOR } from '../data/xaiExplanations';
import XaiHeatmapOverlay from './XaiHeatmapOverlay';
import ForecastChart from './ForecastChart';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const BAR_COLORS = ['#FF4D4F', '#FF8A3D', '#FFD700', '#00E5FF', '#8B5CF6', '#00FF88', '#FF6B9D', '#64DFDF'];

function severityLabel(wbi) {
  if (wbi == null) return { t: '데이터 없음', c: 'rgba(255,255,255,0.3)' };
  if (wbi < 0.3)   return { t: '정상',        c: '#00FF88' };
  if (wbi < 0.6)   return { t: '주의',        c: '#FFD700' };
  if (wbi < 0.8)   return { t: '경고',        c: '#FF8A3D' };
  return             { t: '위험',             c: '#FF4D4F' };
}

export default function XaiAnalysisTab() {
  // 기본 선택 = 등록부 첫 어장. (구: 더미 위험도로 1194개를 정렬 — 가짜 점수 기준이라 무의미했음)
  const [farmId, setFarmId] = useState(ALL_FARMS[0].id);
  const farm = useMemo(() => getFarm(farmId), [farmId]);
  const dummy = useMemo(() => farmDummy(farm), [farm]);

  // 실측(Bronze) 우선 — 실패 시 더미 폴백
  const [real, setReal] = useState(null);
  const snapshot = real ?? dummy;
  const wbi = snapshot.wbi;
  const sev = severityLabel(wbi);

  const [causes, setCauses] = useState([]);
  const [llm, setLlm] = useState(null);
  const [loading, setLoading] = useState(false);
  const [llmLoading, setLlmLoading] = useState(false);

  const analyze = useCallback(async (farm, dummy) => {
    setLoading(true); setLlmLoading(true); setCauses([]); setLlm(null);
    let tc = [], score = dummy.wbi, stage = dummy.stage;
    try {
      const pr = await fetch(`${API_BASE}/predict/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ farm_id: farm.id, sensor_vals: dummy.sensor_vals }),
      });
      const p = await pr.json();
      tc = p.top_causes ?? [];
      if (typeof p.anomaly_score === 'number') score = p.anomaly_score;
      if (typeof p.stage === 'number') stage = p.stage;
      setCauses(tc);
    } catch (e) { setCauses([]); } finally { setLoading(false); }

    try {
      const lr = await fetch(`${API_BASE}/explain/llm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          farm_id: farm.id, farm_name: farm.name, region: farm.city,
          stage, anomaly_score: score, sensor_vals: dummy.sensor_vals, top_causes: tc,
        }),
      });
      setLlm(await lr.json());
    } catch (e) {
      setLlm({ summary: 'LLM 분석 서버에 연결할 수 없습니다.', used_llm: false, cause_analysis: [], recommendations: [] });
    } finally { setLlmLoading(false); }
  }, []);

  // 어장 변경 → 실측 조회 후, 얻은 스냅샷(실측 or 더미)으로 분석
  useEffect(() => {
    let alive = true;
    const centroid = farm.centroid;   // [lon, lat]
    setReal(null);
    (async () => {
      const r = centroid ? await fetchRealSensorByLatLon(centroid[1], centroid[0]) : null;
      if (!alive) return;
      setReal(r);
      analyze(farm, r ?? dummy);
    })();
    return () => { alive = false; };
  }, [farmId]);   // eslint-disable-line

  const chartData = useMemo(() => {
    const sorted = [...causes].sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0));
    return sorted.map((c, i) => ({
      name: XAI_EXPLANATIONS[c.feature]?.label?.split(' ')[0] ?? c.feature,
      pct: Math.round((c.importance ?? 0) * 100),
      color: BAR_COLORS[i % BAR_COLORS.length],
      feature: c.feature, value: c.value, status: c.status,
    }));
  }, [causes]);

  return (
    <div style={st.wrap}>
      {/* 헤더: 어장 선택 + WBI */}
      <div style={st.header}>
        <div style={st.headLeft}>
          <span style={st.headTitle}>🧠 어장별 XAI 심층 분석</span>
          <FarmPicker farmId={farmId} onChange={setFarmId} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* 데이터 출처 — 실측/더미 명시 (실시간 오해 방지) */}
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2,
            fontSize: 10, fontFamily: 'Courier New,monospace',
          }}>
            <span style={{
              padding: '2px 8px', borderRadius: 3, fontWeight: 700, letterSpacing: 0.5,
              background: real ? 'rgba(0,255,136,0.12)' : 'rgba(255,211,0,0.12)',
              color: real ? '#00FF88' : '#FFD700',
              border: `1px solid ${real ? 'rgba(0,255,136,0.3)' : 'rgba(255,211,0,0.3)'}`,
            }}>
              {real ? '실측 데이터' : '더미 데이터'}
            </span>
            {real?.provenance && (
              <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 9 }}>
                {provenanceLabel(real.provenance)}
              </span>
            )}
          </div>
          <div style={{ ...st.wbiBadge, borderColor: sev.c, background: sev.c + '18' }}>
            <span style={st.wbiLabel}>황백화 위험도</span>
            <span style={{ ...st.wbiVal, color: sev.c }}>{(wbi * 100).toFixed(1)}%</span>
            <span style={{ ...st.wbiTag, background: sev.c }}>{sev.t}</span>
          </div>
        </div>
      </div>

      {/* 상단: Attention 바차트 + 센서 스냅샷 */}
      <div style={st.row}>
        <div style={{ ...st.card, flex: 2 }}>
          <div style={st.cardTitle}>
            Attention 기여도 — 모델이 주목한 변수
            {loading && <span style={st.loading}> 분석 중...</span>}
          </div>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 60, right: 30, top: 6, bottom: 6 }}>
                <XAxis type="number" domain={[0, 45]} tick={{ fill: '#64748b', fontSize: 11 }}
                       tickFormatter={v => `${v}%`} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#cbd5e1', fontSize: 12 }} width={60} />
                <Tooltip
                  contentStyle={{ background: 'rgba(5,11,24,0.95)', border: '1px solid rgba(0,229,255,0.2)', borderRadius: 6, fontSize: 11, fontFamily: 'Courier New,monospace' }}
                  formatter={(v, _n, p) => [`기여도 ${v}%  (측정 ${p.payload.value ?? '—'})`, '']}
                  labelStyle={{ color: '#00E5FF' }} />
                <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                  {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div style={st.empty}>{loading ? '분석 중...' : '데이터 없음'}</div>}
        </div>

        <div style={{ ...st.card, flex: 1 }}>
          <div style={st.cardTitle}>센서 스냅샷</div>
          <div style={st.sensorGrid}>
            {[
              ['수온', snapshot.sensor_vals.water_temp, '℃'],
              ['DO', snapshot.sensor_vals.dissolved_oxygen, 'mg/L'],
              ['DIN', snapshot.sensor_vals.din, 'μmol/L'],
              ['DIP', snapshot.sensor_vals.dip, 'μmol/L'],
              ['N:P', snapshot.sensor_vals.np_ratio, ''],
              ['염분', snapshot.sensor_vals.salinity, 'PSU'],
            ].map(([k, v, u]) => (
              <div key={k} style={st.sensorCard}>
                <div style={st.sensorLabel}>{k}</div>
                <div style={st.sensorVal}>{v != null ? Number(v).toFixed(2) : '—'}</div>
                <div style={st.sensorUnit}>{u}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 중단: 7일 예측 */}
      <div style={st.row}>
        <div style={{ ...st.card, flex: 1 }}>
          <ForecastChart farm={farm} snapshot={snapshot} />
        </div>
      </div>

      {/* 하단: 엽체 히트맵 + LLM 종합 */}
      <div style={st.row}>
        <div style={{ ...st.card, flex: 1 }}>
          <div style={st.cardTitle}>🔬 엽체 황백화 진단맵 (XAI 오버레이)</div>
          <XaiHeatmapOverlay farm={farm} snapshot={snapshot} />
        </div>

        <div style={{ ...st.card, flex: 1.4 }}>
          <div style={st.cardTitle}>
            🤖 LLM 종합 분석
            {llm && (
              <span style={{
                marginLeft: 8, fontSize: 8, padding: '1px 8px', borderRadius: 3,
                background: llm.used_llm ? 'rgba(0,255,136,0.1)' : 'rgba(255,211,0,0.1)',
                color: llm.used_llm ? '#00FF88' : '#FFD700',
                border: `1px solid ${llm.used_llm ? 'rgba(0,255,136,0.25)' : 'rgba(255,211,0,0.25)'}`,
                fontFamily: 'Courier New,monospace', letterSpacing: 1,
              }}>{llm.used_llm ? `Gemini ${llm.model ?? ''}` : '템플릿(키 없음)'}</span>
            )}
          </div>
          {llmLoading && <div style={st.loading}>🤖 Gemini 분석 생성 중...</div>}
          {!llmLoading && llm && (
            <div>
              <div style={st.llmSummary}>{llm.summary}</div>
              {llm.cause_analysis?.length > 0 && (
                <div style={st.llmCauses}>
                  {llm.cause_analysis.map((c, i) => (
                    <div key={i} style={st.llmCauseRow}>
                      <span>{XAI_EXPLANATIONS[c.feature]?.icon ?? '•'}</span>
                      <span style={st.llmCauseText}>{c.text}</span>
                    </div>
                  ))}
                </div>
              )}
              {llm.recommendations?.length > 0 && (
                <div style={st.recBox}>
                  <div style={st.recTitle}>권장 조치</div>
                  {llm.recommendations.map((r, i) => <div key={i} style={st.recRow}>✓ {r}</div>)}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const st = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 14 },

  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12,
    background: 'rgba(8,20,37,0.72)', backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0,229,255,0.14)', borderRadius: 8, padding: '12px 18px',
    position: 'relative', overflow: 'hidden',
  },
  headLeft: { display: 'flex', alignItems: 'center', gap: 12 },
  headTitle: {
    color: '#00E5FF', fontSize: 14, fontWeight: 800, letterSpacing: 0.4,
    textShadow: '0 0 12px rgba(0,229,255,0.4)',
  },
  select: {
    background: 'rgba(5,11,24,0.85)', border: '1px solid rgba(0,229,255,0.22)',
    color: 'rgba(255,255,255,0.8)', borderRadius: 6, padding: '6px 12px',
    fontSize: 12, minWidth: 200, fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
    outline: 'none',
  },
  wbiBadge: {
    display: 'flex', alignItems: 'center', gap: 10, border: '1px solid',
    borderRadius: 6, padding: '8px 16px', backdropFilter: 'blur(8px)',
  },
  wbiLabel: { color: 'rgba(255,255,255,0.35)', fontSize: 10, fontFamily: 'Courier New,monospace', letterSpacing: 2 },
  wbiVal:   { fontSize: 24, fontWeight: 900, fontFamily: 'Courier New,monospace' },
  wbiTag:   { color: '#050B18', fontSize: 10, fontWeight: 800, padding: '2px 10px', borderRadius: 4, letterSpacing: 1 },

  row: { display: 'flex', gap: 14, alignItems: 'stretch', flexWrap: 'wrap' },
  card: {
    background: 'rgba(8,20,37,0.72)', backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0,229,255,0.1)', borderRadius: 10,
    padding: '14px 16px', minWidth: 260,
  },
  cardTitle: {
    color: 'rgba(0,229,255,0.7)', fontSize: 11, fontWeight: 700, marginBottom: 12,
    letterSpacing: 1, fontFamily: 'Courier New,monospace', display: 'flex', alignItems: 'center', gap: 6,
  },
  loading: { color: '#FFD700', fontSize: 10, fontFamily: 'Courier New,monospace' },
  empty:   { color: 'rgba(255,255,255,0.18)', fontSize: 12, textAlign: 'center', padding: 40 },

  sensorGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 7 },
  sensorCard: {
    background: 'rgba(5,11,24,0.7)', border: '1px solid rgba(0,229,255,0.08)',
    borderRadius: 7, padding: '9px 8px', textAlign: 'center',
  },
  sensorLabel: { color: 'rgba(255,255,255,0.25)', fontSize: 9, marginBottom: 4, fontFamily: 'Courier New,monospace', letterSpacing: 1 },
  sensorVal:   { color: '#FF8A3D', fontSize: 16, fontWeight: 700, fontFamily: 'Courier New,monospace' },
  sensorUnit:  { color: 'rgba(255,255,255,0.18)', fontSize: 8 },

  llmSummary:  { color: 'rgba(255,255,255,0.78)', fontSize: 13, lineHeight: 1.85, marginBottom: 14 },
  llmCauses:   { display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 12 },
  llmCauseRow: { display: 'flex', gap: 8, alignItems: 'flex-start' },
  llmCauseText:{ color: 'rgba(255,255,255,0.5)', fontSize: 12, lineHeight: 1.65 },
  recBox:   { borderTop: '1px solid rgba(0,229,255,0.1)', paddingTop: 10 },
  recTitle: {
    color: 'rgba(0,229,255,0.4)', fontSize: 9, fontWeight: 700,
    textTransform: 'uppercase', letterSpacing: 2, marginBottom: 7,
    fontFamily: 'Courier New,monospace',
  },
  recRow: { color: '#00FF88', fontSize: 12, lineHeight: 1.85 },
};
