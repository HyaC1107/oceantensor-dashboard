/**
 * XaiAnalysisTab — 어장 선택형 풀사이즈 XAI 분석 페이지
 *
 * 🔴 2026-07-17 개편 — 지도와 XAI가 서로 다른 지표를 보여주던 문제 수정.
 *   [이전] 헤더 '황백화 위험도' = WBI 물리공식(현재 스냅샷, 실측 실패 시 더미).
 *          지도는 v13 딥러닝의 7일 발생확률 → **같은 어장이 지도 '고위험'인데 XAI '주의'**로 갈렸다.
 *          (실증: gid 83003이 지도 warn 0.999/심각인데 완도 실측 WBI는 0.469/주의)
 *   [현재] **주 지표 = v13 예측**(`/predict/v7/{gid}` — 지도와 동일 SSOT, risk_label까지 서버가 준다).
 *          WBI 공식은 "물리 요인 해석(참고)"으로 강등. v13은 시공간 큐브 입력이라
 *          단일 어장 라이브 추론이 불가능해 기여도 분석은 여전히 공식 기반이다.
 *
 * 재활용: /predict(WBI 기여도) → /explain/llm(Gemini 자연어) + XaiHeatmapOverlay(엽체 히트맵).
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { ALL_FARMS, getFarm } from '../data/realFarms';
import FarmPicker from './FarmPicker';
import { farmDummy } from '../data/farmDummy';
import { fetchRealSensorByLatLon, provenanceLabel } from '../data/realSensor';
import { RISK, STAGE_LABEL, normalizeRisk, loadPredictions } from '../data/v13Predictions';
import { XAI_EXPLANATIONS, statusToKey, SEVERITY_COLOR } from '../data/xaiExplanations';
import XaiHeatmapOverlay from './XaiHeatmapOverlay';
import ForecastChart from './ForecastChart';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const BAR_COLORS = ['#FF4D4F', '#FF8A3D', '#FFD700', '#00E5FF', '#8B5CF6', '#00FF88', '#FF6B9D', '#64DFDF'];

// 등급 라벨 SSOT = data/v13Predictions.js (지도·상세카드와 공유).
// 구 severityLabel(WBI 기준 정상/주의/경고/위험)은 2026-07-17 제거 — 지도와 라벨 체계가 갈렸던 원인.

export default function XaiAnalysisTab({ initialFarmId = null }) {
  // 🔴 2026-07-17: 지도에서 넘어온 어장을 우선 선택한다.
  //   이전엔 무조건 ALL_FARMS[0](gid 70018 보령 삽시도리)로 시작해서,
  //   지도에서 '주의' 어장을 클릭하고 "XAI 분석 →"을 눌러도 **전혀 다른 어장의 '정상'**이 떴다.
  //   (PM이 지적한 "지도 색은 주의인데 XAI는 정상"의 진짜 원인 — 값이 아니라 대상이 달랐다)
  const [farmId, setFarmId] = useState(
    () => (initialFarmId && getFarm(initialFarmId) ? String(initialFarmId) : ALL_FARMS[0].id)
  );
  // 탭이 유지된 채 지도에서 다른 어장으로 다시 들어오는 경우도 반영
  useEffect(() => {
    if (initialFarmId && getFarm(initialFarmId)) setFarmId(String(initialFarmId));
  }, [initialFarmId]);
  const farm = useMemo(() => getFarm(farmId), [farmId]);
  const dummy = useMemo(() => farmDummy(farm), [farm]);

  // 실측(Bronze) 우선 — 실패 시 더미 폴백. (센서 스냅샷 표시 + WBI 기여도 분석용 — 주 지표 아님)
  const [real, setReal] = useState(null);
  const snapshot = real ?? dummy;

  // ★ 주 지표 = v13 예측 (지도와 동일 SSOT). 서버가 risk/risk_label/stage까지 계산해 준다.
  const [v13, setV13] = useState(null);
  const [v13Loading, setV13Loading] = useState(false);
  const [seasonNote, setSeasonNote] = useState(null);   // 비양식기 안내(지도와 동일 규칙)
  const risk = normalizeRisk(v13?.risk);
  const riskStyle = risk ? RISK[risk] : null;

  const [causes, setCauses] = useState([]);
  const [llm, setLlm] = useState(null);
  const [loading, setLoading] = useState(false);
  const [llmLoading, setLlmLoading] = useState(false);

  // signal: 어장을 빠르게 바꿀 때 이전 어장 결과가 늦게 착지하는 것 방지(리뷰어 지적)
  const analyze = useCallback(async (farm, snap, v13entry, signal) => {
    setLoading(true); setLlmLoading(true); setCauses([]); setLlm(null);
    let tc = [], score = snap.wbi, stage = snap.stage;
    try {
      // WBI 공식 기여도 — v13은 시공간 큐브 입력이라 단일 어장 라이브 추론이 불가해 공식으로 분해한다.
      const pr = await fetch(`${API_BASE}/predict/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
        body: JSON.stringify({ farm_id: farm.id, sensor_vals: snap.sensor_vals, engine: 'formula' }),
      });
      const p = await pr.json();
      tc = p.top_causes ?? [];
      if (typeof p.anomaly_score === 'number') score = p.anomaly_score;
      if (typeof p.stage === 'number') stage = p.stage;
      if (!signal?.aborted) setCauses(tc);
    } catch (e) {
      if (!signal?.aborted) setCauses([]);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }

    try {
      // LLM에는 **v13 예측을 우선** 전달한다(화면 주 지표와 설명이 어긋나지 않도록).
      // v13이 없으면(비양식기·격자밖) 공식값으로 폴백.
      const lr = await fetch(`${API_BASE}/explain/llm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
        body: JSON.stringify({
          farm_id: farm.id, farm_name: farm.name, region: farm.city,
          stage: v13entry?.stage ?? stage,
          anomaly_score: v13entry?.warn ?? score,
          sensor_vals: snap.sensor_vals, top_causes: tc,
        }),
      });
      const j = await lr.json();
      if (!signal?.aborted) setLlm(j);
    } catch (e) {
      if (!signal?.aborted) {
        setLlm({ summary: 'LLM 분석 서버에 연결할 수 없습니다.', used_llm: false, cause_analysis: [], recommendations: [] });
      }
    } finally {
      if (!signal?.aborted) setLlmLoading(false);
    }
  }, []);

  // 어장 변경 → v13 예측 + 실측을 함께 조회 → 분석
  //
  // 🔴 v13은 반드시 **지도와 같은 `loadPredictions()`** 로 읽는다(캐시 공유라 네트워크 비용 0).
  //   `/predict/v7/{gid}` series의 마지막(=팩 절대 최신)을 쓰면 **지도와 날짜 규칙이 갈린다**:
  //   지도는 `latest_in_season_date` 기준이고 오늘이 비양식기면 `farms:{}`로 전체를 중립 처리하는데,
  //   XAI만 팩 최신(예: 2026-05-20)을 띄우면 **"지도는 예측없음인데 XAI는 99.9% 고위험"**이 된다.
  //   (이게 애초에 PM이 지적한 불일치와 같은 종류다 — 리뷰어 지적으로 배포 전 차단)
  useEffect(() => {
    let alive = true;
    const centroid = farm.centroid;   // [lon, lat]
    setReal(null); setV13(null); setV13Loading(true);
    const ctrl = new AbortController();
    (async () => {
      const [r, preds] = await Promise.all([
        centroid ? fetchRealSensorByLatLon(centroid[1], centroid[0]) : null,
        loadPredictions().catch(() => null),
      ]);
      if (!alive) return;
      const entry = preds?.farms?.[String(farm.id)] ?? null;
      const v = entry ? { ...entry, date: preds.date, inSeason: preds.inSeason !== false } : null;
      setReal(r); setV13(v); setV13Loading(false);
      setSeasonNote(preds && preds.inSeason === false ? (preds.seasonNote ?? '비양식기') : null);
      analyze(farm, r ?? dummy, v, ctrl.signal);
    })();
    return () => { alive = false; ctrl.abort(); };
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
          {/* 기여도 분석용 센서 출처 — 실측/더미 + 관측일 명시 (실시간 오해 방지) */}
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
              {real ? '요인분석 = 실측' : '요인분석 = 더미'}
            </span>
            {real?.provenance && (
              <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 9 }}>
                {provenanceLabel(real.provenance)}
              </span>
            )}
          </div>
          {/* ★ 주 지표 = v13 예측 (지도와 동일 값·동일 등급) */}
          {v13Loading ? (
            <div style={{ ...st.wbiBadge, borderColor: 'rgba(0,229,255,0.3)' }}>
              <span style={st.wbiLabel}>STMMT v13</span>
              <span style={{ ...st.wbiVal, color: 'rgba(0,229,255,0.6)', fontSize: 16 }}>LOADING</span>
            </div>
          ) : riskStyle ? (
            <div style={{ ...st.wbiBadge, borderColor: riskStyle.color, background: riskStyle.color + '18' }}>
              {/* 팩의 최신 예측일 — 오늘이 비양식기면 지난 시즌 마지막 날이다. '현재'로 오해되지 않게 날짜 명시 */}
              <span style={st.wbiLabel}>STMMT v13 · 7일내 발생확률</span>
              <span style={{ ...st.wbiVal, color: riskStyle.color }}>{(v13.warn * 100).toFixed(1)}%</span>
              <span style={{ ...st.wbiTag, background: riskStyle.color }}>{riskStyle.label}</span>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.5)', fontFamily: 'Courier New,monospace', marginLeft: 6 }}>
                {v13.date} 기준 · stage {v13.stage}({STAGE_LABEL[v13.stage] ?? '?'})
              </span>
            </div>
          ) : (
            <div style={{ ...st.wbiBadge, borderColor: 'rgba(255,255,255,0.2)' }}>
              <span style={st.wbiLabel}>STMMT v13 예측</span>
              <span style={{ ...st.wbiVal, color: 'rgba(190,205,225,0.8)', fontSize: 13 }}>예측 없음</span>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.45)', maxWidth: 210, lineHeight: 1.3 }}>
                {seasonNote ?? '해당 어장 예측 없음 (격자밖 등)'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 상단: Attention 바차트 + 센서 스냅샷 */}
      <div style={st.row}>
        <div style={{ ...st.card, flex: 2 }}>
          {/* 🔴 2026-07-17: 제목이 "Attention 기여도 — 모델이 주목한 변수"였으나 **사실이 아니었다**.
              이 차트는 v13(딥러닝)의 attention이 아니라 **WBI 물리공식의 인자별 기여도**다.
              v13은 시공간 큐브 입력이라 단일 어장 라이브 추론이 불가해 공식으로 분해한다. */}
          <div style={st.cardTitle}>
            황백화 요인 기여도 — WBI 물리공식 기반
            <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', fontWeight: 400, marginLeft: 6 }}>
              (위 v13 예측과 별개인 참고 분석 · 현재 관측 기준)
            </span>
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
          {/* 🔴 2026-07-17: snapshot(=WBI 센서값)을 넘기지 않는다.
              백엔드 /predict/forecast 는 sensor_vals 가 없으면 **v13 실제 7일 ADI 궤적**을 서빙하고,
              있으면 공식 통계추정으로 빠진다(predict.py:385). 지도·헤더와 축을 맞추려면 v13 경로여야 한다. */}
          <ForecastChart farm={farm} />
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
    // overflow:hidden 제거 + zIndex 상향 — FarmPicker 드롭다운이 아래 차트 카드(backdropFilter=새 stacking) 뒤로 깔리던 문제
    position: 'relative', zIndex: 20,
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
