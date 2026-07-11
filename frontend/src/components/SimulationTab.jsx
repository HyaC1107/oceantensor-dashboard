/**
 * SimulationTab — 황백화 What-if 시뮬레이터
 *
 * 핵심 수질 지표(수온·DIN·DIP·염분·DO)를 슬라이더로 조정하면
 * WBI(황백화 위험도)가 실시간 반응 → 지표↔황백화 연관성을 체감하는 페이지.
 *
 * 계산 구조:
 *   - 즉시 반응   : 프론트 wbiFormula 미러 (farmDummy.js 와 동일 공식)
 *   - 백엔드 확정 : debounce 후 POST /predict/ (sensor_vals what-if 경로)
 *   - 7일 궤적    : debounce 후 POST /predict/forecast (통계 추정 what-if)
 *
 * ⚠️ v13(STMMT)은 시공간 큐브 입력이라 슬라이더 라이브 추론 불가 →
 *    이 페이지는 WBI 물리 공식 기반 민감도 시뮬레이션이다. (v13 궤적은 대시보드 서빙)
 * ⚠️ Chl-a 는 라벨(결과) 지표라 입력에서 의도적으로 제외 (v13 학습도 누수 방지 위해 대체).
 */
import { useState, useEffect, useMemo, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceDot, ComposedChart, Area, CartesianGrid,
} from 'recharts';
import { ALL_FARMS, getFarm } from '../data/realFarms';
import FarmPicker from './FarmPicker';
import { farmDummy } from '../data/farmDummy';
import { fetchRealSensorByLatLon, provenanceLabel } from '../data/realSensor';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── 백엔드 _wbi_formula 미러 (farmDummy.js 와 동일) ──────────────────────
function riskParts({ din, water_temp, np_ratio, dissolved_oxygen, salinity }) {
  return {
    din:              Math.max(0, 1 - din / 5),
    water_temp:       Math.max(0, (water_temp - 20) / 10),
    np_ratio:         Math.max(0, 1 - np_ratio / 10),
    dissolved_oxygen: Math.max(0, 1 - dissolved_oxygen / 5),
    salinity:         Math.max(0, (32 - salinity) / 4),
  };
}
const WEIGHTS = { din: 0.38, water_temp: 0.27, np_ratio: 0.19, dissolved_oxygen: 0.10, salinity: 0.06 };

function wbiOf(vals) {
  // 백엔드 _wbi_formula 와 동일: 개별 클램프 없이 최종값만 [0,1] (미러 일치 필수)
  const p = riskParts(vals);
  const w = Object.keys(WEIGHTS).reduce((s, k) => s + WEIGHTS[k] * p[k], 0);
  return Math.min(1, Math.max(0, w));
}

function severity(wbi) {
  if (wbi < 0.3) return { t: '정상', c: '#00FF88' };
  if (wbi < 0.6) return { t: '주의', c: '#FFD700' };
  if (wbi < 0.8) return { t: '경고', c: '#FF8A3D' };
  return           { t: '위험', c: '#FF4D4F' };
}

// ── 슬라이더 정의 ────────────────────────────────────────────────────────
const FACTORS = [
  { key: 'water_temp',       label: '수온',        unit: '℃',      min: 5,   max: 32,  step: 0.1,  hint: '20℃ 초과부터 위험 가중 (가중치 27%)' },
  { key: 'din',              label: 'DIN 용존무기질소', unit: 'μmol/L', min: 0,   max: 15,  step: 0.1,  hint: '5 μmol/L 이하 → 급격 상승 (가중치 38%, 최대)' },
  { key: 'dip',              label: 'DIP 용존무기인',  unit: 'μmol/L', min: 0.1, max: 1.5, step: 0.01, hint: 'N:P 비율(DIN÷DIP) 결정 — N:P<10 심각 신호 (19%)' },
  { key: 'salinity',         label: '염분',        unit: 'psu',    min: 26,  max: 35,  step: 0.1,  hint: '32 psu 미만부터 위험 (강수/담수 유입 시 하락, 6%)' },
  { key: 'dissolved_oxygen', label: '용존산소 DO', unit: 'mg/L',   min: 2,   max: 12,  step: 0.1,  hint: '5 mg/L 미만부터 위험 (10%)' },
];

const PRESETS = [
  { name: '정상', c: '#00FF88', vals: { water_temp: 18,  din: 9,   dip: 0.6,  salinity: 33,   dissolved_oxygen: 9 } },
  { name: '주의', c: '#FFD700', vals: { water_temp: 23,  din: 4.5, dip: 0.5,  salinity: 32,   dissolved_oxygen: 7 } },
  { name: '경고', c: '#FF8A3D', vals: { water_temp: 26,  din: 2.5, dip: 0.5,  salinity: 30.5, dissolved_oxygen: 5.5 } },
  { name: '위험', c: '#FF4D4F', vals: { water_temp: 29.5, din: 0.8, dip: 0.45, salinity: 28.5, dissolved_oxygen: 3.5 } },
];

const FACTOR_LABEL = Object.fromEntries(FACTORS.map(f => [f.key, f.label]));

function fromSensorVals(sensor_vals) {
  const v = {};
  FACTORS.forEach(f => { v[f.key] = sensor_vals[f.key]; });
  return v;
}

function fromFarm(farm) {
  return fromSensorVals(farmDummy(farm).sensor_vals);
}

function fullSensorVals(vals) {
  // 백엔드 8차원 벡터 호환: 공식 외 입력은 중립 기본값
  const np_ratio = vals.dip > 0 ? Math.round((vals.din / vals.dip) * 100) / 100 : 0;
  return { ...vals, np_ratio, precipitation: 0.0, chlorophyll_a: 3.0 };
}

export default function SimulationTab() {
  const [farmId, setFarmId] = useState(ALL_FARMS[0].id);
  const farm = useMemo(() => getFarm(farmId), [farmId]);
  const [vals, setVals] = useState(() => fromFarm(ALL_FARMS[0]));
  const [sweepKey, setSweepKey] = useState('din');
  const [backend, setBackend] = useState(null);   // /predict 확정치
  const [forecastData, setForecastData] = useState(null);
  const debRef = useRef(null);

  const npRatio = vals.dip > 0 ? vals.din / vals.dip : 0;
  const simVals = { ...vals, np_ratio: npRatio };
  const wbi = wbiOf(simVals);
  const sev = severity(wbi);
  const parts = riskParts(simVals);

  // 어장 변경 → 실측 현재값으로 리셋 (실패 시 더미)
  const [real, setReal] = useState(null);
  useEffect(() => {
    let alive = true;
    setReal(null);
    setVals(fromFarm(farm));           // 우선 더미로 즉시 표시
    const c = farm.centroid;           // [lon, lat]
    if (!c) return;
    (async () => {
      const r = await fetchRealSensorByLatLon(c[1], c[0]);
      if (!alive || !r) return;
      setReal(r);
      setVals(fromSensorVals(r.sensor_vals));   // 실측 도착하면 교체
    })();
    return () => { alive = false; };
  }, [farmId]);  // eslint-disable-line

  const resetToFarm = () => setVals(real ? fromSensorVals(real.sensor_vals) : fromFarm(farm));

  // 슬라이더 변경 → 500ms debounce 후 백엔드 확정치 + 7일 궤적
  // AbortController 로 stale 응답 race 차단 (이전 어장/설정 응답이 늦게 와 덮어쓰는 문제)
  useEffect(() => {
    const ctrl = new AbortController();
    clearTimeout(debRef.current);
    debRef.current = setTimeout(async () => {
      const body = JSON.stringify({ farm_id: farmId, sensor_vals: fullSensorVals(vals), engine: 'formula' });
      const opt = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: ctrl.signal };
      try {
        const [pr, fr] = await Promise.all([
          fetch(`${API_BASE}/predict/`, opt),
          fetch(`${API_BASE}/predict/forecast`, opt),
        ]);
        const [p, f] = [await pr.json(), await fr.json()];
        if (!ctrl.signal.aborted) { setBackend(p); setForecastData(f); }
      } catch {
        if (!ctrl.signal.aborted) { setBackend(null); setForecastData(null); }
      }
    }, 500);
    return () => { clearTimeout(debRef.current); ctrl.abort(); };
  }, [vals, farmId]);

  // 민감도 스윕: 선택 인자를 범위 전체로 훑으며 WBI 곡선
  const sweep = useMemo(() => {
    const f = FACTORS.find(x => x.key === sweepKey);
    const N = 60;
    const out = [];
    for (let i = 0; i <= N; i++) {
      const x = f.min + (i / N) * (f.max - f.min);
      const v = { ...vals, [f.key]: x };
      const np = v.dip > 0 ? v.din / v.dip : 0;
      out.push({ x: Math.round(x * 100) / 100, wbi: Math.round(wbiOf({ ...v, np_ratio: np }) * 1000) / 10 });
    }
    return { factor: f, data: out };
  }, [sweepKey, vals]);

  const contrib = FACTORS.map(f => {
    const key = f.key === 'dip' ? 'np_ratio' : f.key;   // DIP 는 N:P 경유로 기여
    return {
      key, label: f.key === 'dip' ? 'N:P 비율' : f.label,
      pct: Math.round(WEIGHTS[key] * parts[key] * 1000) / 10,  // 공식과 동일 (미클램프)
      max: WEIGHTS[key] * 100,
    };
  }).filter((c, i, arr) => arr.findIndex(x => x.key === c.key) === i)  // 방어용 dedup (현재 키 조합에선 no-op)
    .sort((a, b) => b.pct - a.pct);

  const matched = backend && Math.abs((backend.anomaly_score ?? -1) - wbi) < 0.005;

  // ForecastChart.jsx 검증 패턴: range Area 는 band 배열 필드로 사전 매핑
  const forecastSeries = useMemo(
    () => forecastData?.series?.map(s => ({ ...s, band: [s.lower, s.upper] })) ?? null,
    [forecastData]
  );

  // 민감도 곡선 현재값 최근접점 (ReferenceDot)
  const sweepDot = useMemo(() => {
    if (!sweep.data.length) return null;
    return sweep.data.reduce((best, d) =>
      Math.abs(d.x - vals[sweepKey]) < Math.abs(best.x - vals[sweepKey]) ? d : best);
  }, [sweep, vals, sweepKey]);

  return (
    <div style={st.wrap}>
      {/* 헤더 */}
      <div style={st.header}>
        <div style={st.headLeft}>
          <span style={st.headTitle}>🧪 황백화 What-if 시뮬레이터</span>
          <FarmPicker farmId={farmId} onChange={setFarmId} />
          <div style={st.presetRow}>
            {PRESETS.map(p => (
              <button key={p.name} style={{ ...st.presetBtn, borderColor: p.c + '55', color: p.c }}
                      onClick={() => setVals(v => ({ ...v, ...p.vals }))}>
                {p.name}
              </button>
            ))}
            <button style={st.resetBtn} onClick={resetToFarm}>
              ↺ 어장 현재값{real ? ' (실측)' : ''}
            </button>
          </div>
          {real?.provenance && (
            <span style={{ fontSize: 9, color: 'rgba(0,255,136,0.6)', fontFamily: 'Courier New,monospace' }}>
              실측: {provenanceLabel(real.provenance)}
            </span>
          )}
        </div>
        <div style={{ ...st.wbiBadge, borderColor: sev.c, background: sev.c + '18' }}>
          <span style={st.wbiLabel}>시뮬레이션 위험도</span>
          <span style={{ ...st.wbiVal, color: sev.c }}>{(wbi * 100).toFixed(1)}%</span>
          <span style={{ ...st.wbiTag, background: sev.c }}>{sev.t}</span>
        </div>
      </div>

      <div style={st.row}>
        {/* 좌: 슬라이더 패널 */}
        <div style={{ ...st.card, flex: 1.1, minWidth: 320 }}>
          <div style={st.cardTitle}>핵심 지표 조정</div>
          {FACTORS.map(f => (
            <div key={f.key} style={st.sliderBlock}>
              <div style={st.sliderHead}>
                <span style={st.sliderLabel}>{f.label}</span>
                <span style={st.sliderVal}>{Number(vals[f.key]).toFixed(f.step < 0.1 ? 2 : 1)} {f.unit}</span>
              </div>
              <input
                type="range" min={f.min} max={f.max} step={f.step} value={vals[f.key]}
                onChange={e => setVals(v => ({ ...v, [f.key]: Number(e.target.value) }))}
                style={st.slider}
              />
              <div style={st.sliderHint}>{f.hint}</div>
            </div>
          ))}
          <div style={st.npBox}>
            N:P 비율 (DIN ÷ DIP) = <b style={{ color: npRatio < 10 ? '#FF4D4F' : '#00E5FF' }}>{npRatio.toFixed(1)}</b>
            <span style={st.npHint}> {npRatio < 10 ? '— 10 미만: 질소 고갈 심각 신호' : '— 10 이상: 양호'}</span>
          </div>
          <div style={st.note}>
            ⚠️ Chl-a(엽록소)는 황백화 판정 결과 지표라 입력에서 제외 (v13 학습에서도 누수 방지 위해 대체).
            시뮬레이터는 WBI 물리 공식 기반 — v13(STMMT) 실궤적은 대시보드에 서빙.
          </div>
        </div>

        {/* 우: 기여도 + 민감도 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1.6, minWidth: 380 }}>
          <div style={st.card}>
            <div style={st.cardTitle}>
              인자별 위험 기여도 (현재 설정 기준)
              {backend && (
                <span style={{ ...st.verify, color: matched ? '#00FF88' : '#FFD700' }}>
                  서버 {backend.model_version}: {(backend.anomaly_score * 100).toFixed(1)}% {matched ? '✓ 일치' : ''}
                </span>
              )}
            </div>
            {contrib.map(c => (
              <div key={c.key} style={st.contribRow}>
                <span style={st.contribLabel}>{c.label}</span>
                <div style={st.contribTrack}>
                  <div style={{ ...st.contribMax, width: `${c.max}%` }} />
                  <div style={{ ...st.contribBar, width: `${Math.min(c.pct, 100)}%`, background: c.pct > c.max * 0.66 ? '#FF4D4F' : c.pct > c.max * 0.33 ? '#FFD700' : '#00E5FF' }} />
                </div>
                <span style={st.contribPct}>{c.pct.toFixed(1)}%p</span>
              </div>
            ))}
            <div style={st.sliderHint}>연한 배경 = 해당 인자의 최대 기여 한도(가중치), 채워진 바 = 현재 기여분</div>
          </div>

          <div style={st.card}>
            <div style={st.cardTitle}>민감도 곡선 — 이 지표가 움직이면 위험도가 어떻게 변하나</div>
            <div style={st.chipRow}>
              {FACTORS.map(f => (
                <button key={f.key}
                        style={{ ...st.chip, ...(sweepKey === f.key ? st.chipOn : {}) }}
                        onClick={() => setSweepKey(f.key)}>
                  {f.label}
                </button>
              ))}
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={sweep.data} margin={{ top: 8, right: 16, bottom: 4, left: -18 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="x" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.45)' }}
                       label={{ value: `${sweep.factor.label} (${sweep.factor.unit})`, position: 'insideBottom', dy: 8, fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.45)' }} unit="%" />
                <Tooltip contentStyle={st.tooltip} formatter={v => [`${v}%`, '위험도']} />
                <Line type="monotone" dataKey="wbi" stroke="#00E5FF" strokeWidth={2} dot={false} />
                {sweepDot && (
                  <ReferenceDot x={sweepDot.x} y={sweepDot.wbi}
                                r={5} fill={sev.c} stroke="#fff" strokeWidth={1.5} />
                )}
              </LineChart>
            </ResponsiveContainer>
            <div style={st.sliderHint}>점 = 현재 슬라이더 값 · 다른 지표는 현재 설정으로 고정한 채 이 지표만 스윕</div>
          </div>

          <div style={st.card}>
            <div style={st.cardTitle}>
              7일 위험도 궤적 (what-if 통계 추정)
              {forecastData?.method && <span style={st.verify}>method: {forecastData.method}</span>}
            </div>
            {forecastSeries ? (
              <ResponsiveContainer width="100%" height={180}>
                <ComposedChart data={forecastSeries} margin={{ top: 8, right: 16, bottom: 0, left: -18 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.45)' }} tickFormatter={d => `+${d}일`} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.45)' }} tickFormatter={v => `${Math.round(v * 100)}%`} />
                  <Tooltip contentStyle={st.tooltip} formatter={(v, n) => [Array.isArray(v) ? `${Math.round(v[0]*100)}~${Math.round(v[1]*100)}%` : `${Math.round(v * 100)}%`, n === 'wbi' ? '위험도' : '신뢰밴드']} />
                  <Area dataKey="band" stroke="none" fill="rgba(0,229,255,0.12)" />
                  <Line type="monotone" dataKey="wbi" stroke="#00E5FF" strokeWidth={2} dot={{ r: 2.5 }} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div style={st.empty}>백엔드(:8000) 연결 시 7일 궤적이 표시됩니다.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const st = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 16 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' },
  headLeft: { display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' },
  headTitle: { fontSize: 15, fontWeight: 800, color: '#00E5FF', letterSpacing: 0.5 },
  select: {
    background: 'rgba(0,229,255,0.06)', color: '#fff', border: '1px solid rgba(0,229,255,0.25)',
    borderRadius: 6, padding: '7px 10px', fontSize: 12, outline: 'none',
  },
  presetRow: { display: 'flex', gap: 6, alignItems: 'center' },
  presetBtn: {
    background: 'none', border: '1px solid', borderRadius: 5, padding: '5px 10px',
    fontSize: 11, fontWeight: 700, cursor: 'pointer',
  },
  resetBtn: {
    background: 'none', border: '1px solid rgba(255,255,255,0.2)', borderRadius: 5,
    padding: '5px 10px', fontSize: 11, color: 'rgba(255,255,255,0.6)', cursor: 'pointer',
  },
  wbiBadge: {
    display: 'flex', alignItems: 'center', gap: 10, border: '1px solid',
    borderRadius: 8, padding: '8px 14px',
  },
  wbiLabel: { fontSize: 11, color: 'rgba(255,255,255,0.55)' },
  wbiVal: { fontSize: 22, fontWeight: 900, fontFamily: 'Courier New,monospace' },
  wbiTag: { fontSize: 11, fontWeight: 800, color: '#041018', borderRadius: 4, padding: '2px 8px' },
  row: { display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' },
  card: {
    background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(0,229,255,0.12)',
    borderRadius: 10, padding: '14px 16px',
  },
  cardTitle: {
    fontSize: 12, fontWeight: 700, color: 'rgba(255,255,255,0.75)', marginBottom: 12,
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap',
  },
  verify: { fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.45)', fontFamily: 'Courier New,monospace' },
  sliderBlock: { marginBottom: 14 },
  sliderHead: { display: 'flex', justifyContent: 'space-between', marginBottom: 4 },
  sliderLabel: { fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.8)' },
  sliderVal: { fontSize: 12, fontWeight: 800, color: '#00E5FF', fontFamily: 'Courier New,monospace' },
  slider: { width: '100%', accentColor: '#00E5FF', cursor: 'pointer' },
  sliderHint: { fontSize: 10, color: 'rgba(255,255,255,0.35)', marginTop: 3 },
  npBox: {
    marginTop: 4, padding: '9px 12px', borderRadius: 6, fontSize: 12,
    background: 'rgba(0,229,255,0.05)', border: '1px solid rgba(0,229,255,0.15)', color: 'rgba(255,255,255,0.8)',
  },
  npHint: { fontSize: 10, color: 'rgba(255,255,255,0.4)' },
  note: {
    marginTop: 10, fontSize: 10, lineHeight: 1.6, color: 'rgba(255,215,0,0.55)',
    borderTop: '1px dashed rgba(255,255,255,0.1)', paddingTop: 8,
  },
  contribRow: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 },
  contribLabel: { fontSize: 11, color: 'rgba(255,255,255,0.7)', width: 110, flexShrink: 0 },
  contribTrack: { flex: 1, height: 14, position: 'relative', background: 'rgba(255,255,255,0.04)', borderRadius: 3, overflow: 'hidden' },
  contribMax: { position: 'absolute', top: 0, left: 0, height: '100%', background: 'rgba(0,229,255,0.08)' },
  contribBar: { position: 'absolute', top: 0, left: 0, height: '100%', borderRadius: 3, transition: 'width .25s' },
  contribPct: { fontSize: 11, fontWeight: 800, color: 'rgba(255,255,255,0.85)', width: 48, textAlign: 'right', fontFamily: 'Courier New,monospace' },
  chipRow: { display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' },
  chip: {
    background: 'none', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 20,
    padding: '4px 12px', fontSize: 11, color: 'rgba(255,255,255,0.5)', cursor: 'pointer',
  },
  chipOn: { borderColor: '#00E5FF', color: '#00E5FF', background: 'rgba(0,229,255,0.08)' },
  tooltip: {
    background: 'rgba(5,11,24,0.95)', border: '1px solid rgba(0,229,255,0.3)',
    borderRadius: 6, fontSize: 11,
  },
  empty: { fontSize: 11, color: 'rgba(255,255,255,0.35)', padding: '24px 0', textAlign: 'center' },
};
