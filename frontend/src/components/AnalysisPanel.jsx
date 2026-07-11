import { useState, useEffect, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { ALL_FARMS } from '../data/farmGeoData';
import { farmDummy } from '../data/farmDummy';
import farmGisImg from '../assets/farm-gis.png';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const SEV_CFG = {
  NORMAL:  { label: 'NORMAL',  color: '#22c55e', dim: '#03150b' },
  CAUTION: { label: 'CAUTION', color: '#f59e0b', dim: '#120d00' },
  WARNING: { label: 'WARNING', color: '#f97316', dim: '#120800' },
  DANGER:  { label: 'DANGER',  color: '#ef4444', dim: '#120000' },
};

function sevFromWbi(wbi) {
  if (wbi == null || wbi < 0.3) return SEV_CFG.NORMAL;
  if (wbi < 0.6) return SEV_CFG.CAUTION;
  if (wbi < 0.8) return SEV_CFG.WARNING;
  return SEV_CFG.DANGER;
}

const BAR_COLORS = ['#ef4444', '#f97316', '#f59e0b', '#22c55e', '#06b6d4', '#6366f1'];

const FEAT_LABEL = {
  water_temp: '수온', din: 'DIN', salinity: '염분',
  dissolved_oxygen: 'DO', np_ratio: 'N:P',
  precipitation: '강수', chlorophyll_a: '클로로필',
};

const FALLBACK_CAUSES = [
  { feature: 'water_temp',       importance: 0.38 },
  { feature: 'din',              importance: 0.26 },
  { feature: 'salinity',         importance: 0.16 },
  { feature: 'dissolved_oxygen', importance: 0.11 },
  { feature: 'np_ratio',         importance: 0.06 },
  { feature: 'chlorophyll_a',    importance: 0.03 },
];

export default function AnalysisPanel({ data }) {
  const wbi = data?.wbi_score ?? 0.76;
  const sev = sevFromWbi(wbi);
  const [causes, setCauses] = useState(FALLBACK_CAUSES);

  const defaultFarm = useMemo(
    () => [...ALL_FARMS].sort((a, b) => farmDummy(b).wbi - farmDummy(a).wbi)[0],
    []
  );
  const dummy = useMemo(() => farmDummy(defaultFarm), [defaultFarm]);

  useEffect(() => {
    fetch(`${API_BASE}/predict/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ farm_id: defaultFarm.id, sensor_vals: dummy.sensor_vals }),
    })
      .then(r => r.json())
      .then(p => { if (p.top_causes?.length) setCauses(p.top_causes); })
      .catch(() => {});
  }, []); // eslint-disable-line

  const chartData = useMemo(() =>
    [...causes]
      .sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0))
      .slice(0, 6)
      .map((c, i) => ({
        name: FEAT_LABEL[c.feature] ?? c.feature,
        pct: Math.round((c.importance ?? 0) * 100),
        color: BAR_COLORS[i],
      })),
    [causes]
  );

  const sensors = [
    { label: '수온',  val: data?.water_temp          ?? dummy.sensor_vals.water_temp,         unit: '℃'      },
    { label: 'DO',    val: data?.dissolved_oxygen     ?? dummy.sensor_vals.dissolved_oxygen,    unit: 'mg/L'   },
    { label: 'DIN',   val: data?.din                  ?? dummy.sensor_vals.din,                 unit: 'μmol/L' },
    { label: 'N:P',   val: data?.np_ratio             ?? dummy.sensor_vals.np_ratio,            unit: ''       },
  ];

  return (
    <div style={st.panel}>
      {/* 패널 헤더 */}
      <div style={st.header}>
        <span style={st.headerDot} />
        <span style={st.headerText}>TBY TRANSFORMER ANALYSIS PANEL</span>
      </div>

      {/* 상단: WBI 큰 숫자 + 미니 센서 카드 4개 */}
      <div style={st.topSection}>
        <div style={{ ...st.wbiBox, background: sev.dim }}>
          <div style={st.wbiTitle}>황백화 지수 (WBI)</div>
          <div style={{ ...st.wbiScore, color: sev.color }}>
            {wbi.toFixed(2)}
          </div>
          <div style={{ ...st.wbiUnderline, background: sev.color + '55' }} />
          <div style={{ ...st.wbiBadge, background: sev.color, color: sev.color === '#f59e0b' ? '#000' : '#fff' }}>
            {sev.label}
          </div>
        </div>

        <div style={st.sensorGrid}>
          {sensors.map(s => (
            <div key={s.label} style={st.sensorCard}>
              <div style={st.sensorLabel}>{s.label}</div>
              <div style={st.sensorVal}>
                {s.val != null ? Number(s.val).toFixed(1) : '—'}
              </div>
              {s.unit && <div style={st.sensorUnit}>{s.unit}</div>}
            </div>
          ))}
        </div>
      </div>

      <div style={st.divider} />

      {/* 하단: 기여 인자 바 차트 + GIS 사진 */}
      <div style={st.bottomSection}>
        <div style={st.chartBox}>
          <div style={st.chartTitle}>
            황백화 발생 기여 인자
            <span style={st.chartSub}> (Causal Contribution)</span>
          </div>
          <ResponsiveContainer width="100%" height={170}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 52, right: 20, top: 4, bottom: 4 }}
            >
              <XAxis
                type="number" domain={[0, 45]}
                tick={{ fill: '#475569', fontSize: 9 }}
                tickFormatter={v => `${v}%`}
              />
              <YAxis
                type="category" dataKey="name"
                tick={{ fill: '#94a3b8', fontSize: 11 }} width={52}
              />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6, fontSize: 11 }}
                formatter={v => [`${v}%`, '기여도']}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={st.photoBox}>
          <img
            src={farmGisImg}
            alt="김 양식장 GIS 현황"
            style={st.photo}
            onError={e => { e.currentTarget.parentElement.style.background = '#0d1b2e'; e.currentTarget.style.display = 'none'; }}
          />
        </div>
      </div>
    </div>
  );
}

const st = {
  panel: {
    width: 430, flexShrink: 0,
    display: 'flex', flexDirection: 'column',
    background: '#0a1628', borderLeft: '1px solid #1e3a5f',
    fontFamily: "'Pretendard', 'Noto Sans KR', system-ui, sans-serif",
    overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '10px 16px', borderBottom: '1px solid #1e3a5f',
    background: '#060f1c', flexShrink: 0,
  },
  headerDot:  { width: 7, height: 7, borderRadius: '50%', background: '#22c55e', flexShrink: 0 },
  headerText: { color: '#334155', fontSize: 10, fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase' },

  topSection: {
    display: 'flex', gap: 12, padding: '16px 16px 12px',
    alignItems: 'stretch', flexShrink: 0,
  },
  wbiBox: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    borderRadius: 10, padding: '14px 18px', border: '1px solid #1e3a5f', minWidth: 132,
  },
  wbiTitle:     { color: '#475569', fontSize: 9, letterSpacing: 0.5, marginBottom: 4 },
  wbiScore:     { fontSize: 62, fontWeight: 900, lineHeight: 1, letterSpacing: -3 },
  wbiUnderline: { width: 56, height: 2, margin: '8px auto 6px', borderRadius: 1 },
  wbiBadge: {
    fontSize: 10, fontWeight: 900, letterSpacing: 2,
    padding: '3px 14px', borderRadius: 20,
  },

  sensorGrid: {
    flex: 1, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8,
  },
  sensorCard: {
    background: '#0d1b2e', border: '1px solid #1e3a5f', borderRadius: 8,
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: '10px 6px', textAlign: 'center',
  },
  sensorLabel: { color: '#475569', fontSize: 9, marginBottom: 3, letterSpacing: 0.3 },
  sensorVal:   { color: '#e2e8f0', fontSize: 22, fontWeight: 700, lineHeight: 1 },
  sensorUnit:  { color: '#334155', fontSize: 9, marginTop: 3 },

  divider: { borderTop: '1px solid #1e3a5f', margin: '0 16px', flexShrink: 0 },

  bottomSection: {
    display: 'flex', flex: 1, gap: 10, padding: '12px 16px 16px',
    minHeight: 0,
  },
  chartBox:  { flex: 1.5, display: 'flex', flexDirection: 'column', minWidth: 0 },
  chartTitle: { color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 6, flexShrink: 0 },
  chartSub:   { color: '#334155', fontSize: 10 },

  photoBox: {
    flex: 1, borderRadius: 8, overflow: 'hidden',
    border: '1px solid #1e3a5f', minWidth: 0,
  },
  photo: { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
};
