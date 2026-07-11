/**
 * FarmMap — react-leaflet 위성맵 기반 김 양식장 GIS + XAI 인포윈도우
 *
 * 문서 참조: 연안 양식지도 구현하기.MD / 양식 김 어장 공간정보시스템(GIS).MD
 *
 * 레이어 구조 (OpenLayers 권장 문서 기반):
 *   ① 위성영상 (ESRI World Imagery)
 *   ② 양식장 Polygon (WBI 등급별 색상)
 *   ③ 관측 부이 마커 (파란 원)
 *   ④ 조위관측소 마커 (주황 마름모)
 *
 * 클릭 시 인포윈도우:
 *   - 어장 GIS 속성 (어장명, 품종, 면적, 허가번호 등)
 *   - 실시간 센서값
 *   - XAI Attention Map (황백화 원인별 기여도 바차트)
 *   - 7일 예측 황백화 확률
 */
import { useState, useCallback, useMemo } from 'react';
import {
  MapContainer, TileLayer, Polygon, Tooltip,
  CircleMarker, LayersControl, useMap,
} from 'react-leaflet';
import { BarChart, Bar, XAxis, YAxis, Cell, Tooltip as RTooltip, ResponsiveContainer } from 'recharts';
import { ALL_FARMS, OBSERVATION_STATIONS, REGION_GROUPS } from '../data/farmGeoData';
import { XAI_EXPLANATIONS, statusToKey, SEVERITY_COLOR, FIELD_PHOTOS } from '../data/xaiExplanations';
import { farmDummy, farmWbi } from '../data/farmDummy';
import XaiHeatmapOverlay from './XaiHeatmapOverlay';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── 타일 레이어 정의 ──────────────────────────────────────
const TILES = {
  satellite: {
    label: '위성',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri, Maxar, Earthstar Geographics',
    maxZoom: 19,
  },
  vworld: {
    label: '브이월드',
    url: 'http://api.vworld.kr/req/wmts/1.0.0/D1CE0ECC-8E9C-3B36-A3CA-E2C2C2C2C2C2/Satellite/{z}/{y}/{x}.jpeg',
    attribution: '© VWorld Korea',
    maxZoom: 18,
  },
  osm: {
    label: '일반지도',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19,
  },
};

// ── WBI 등급 색상 ──────────────────────────────────────────
function wbiColor(wbi) {
  if (wbi === null || wbi === undefined) return { color: '#94a3b8', fill: '#94a3b8', opacity: 0.18 };
  if (wbi < 0.3)  return { color: '#22c55e', fill: '#22c55e', opacity: 0.25 };
  if (wbi < 0.6)  return { color: '#f59e0b', fill: '#f59e0b', opacity: 0.30 };
  if (wbi < 0.8)  return { color: '#f97316', fill: '#f97316', opacity: 0.38 };
  return           { color: '#ef4444', fill: '#ef4444', opacity: 0.45 };
}

function severityLabel(wbi) {
  if (wbi === null || wbi === undefined) return { text: '데이터 없음', color: '#64748b' };
  if (wbi < 0.3)  return { text: '정상',  color: '#22c55e' };
  if (wbi < 0.6)  return { text: '주의',  color: '#f59e0b' };
  if (wbi < 0.8)  return { text: '경고',  color: '#f97316' };
  return           { text: '위험',  color: '#ef4444' };
}

// ── 지도 중심 이동 헬퍼 ───────────────────────────────────
function FlyTo({ center, zoom }) {
  const map = useMap();
  if (center) map.flyTo(center, zoom ?? 11, { duration: 0.8 });
  return null;
}

// ── XAI 통합 패널 (바 차트 + 자연어 설명 + 현장 사진) ──
const XAI_COLORS = ['#ef4444','#f97316','#f59e0b','#22c55e','#06b6d4','#6366f1','#a855f7','#84cc16'];

function XAIPanel({ causes, loading }) {
  const [activeIdx, setActiveIdx] = useState(0);

  if (loading) return <div style={xaiSt.loading}>🔍 AI 원인 분석 중...</div>;
  if (!causes?.length) return <div style={xaiSt.empty}>예측 데이터를 불러오는 중입니다</div>;

  const sorted = [...causes].sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0));
  const active = sorted[activeIdx];
  const meta = XAI_EXPLANATIONS[active?.feature];
  const stKey = statusToKey(active?.status);
  const explanation = meta && stKey ? meta[stKey] : null;
  const sevColor = explanation ? SEVERITY_COLOR[explanation.severity] : '#64748b';

  const chartData = sorted.map((c, i) => ({
    name: XAI_EXPLANATIONS[c.feature]?.label?.split(' ')[0] ?? c.feature,
    pct: Math.round((c.importance ?? 0) * 100),
    color: XAI_COLORS[i % XAI_COLORS.length],
  }));

  return (
    <div>
      {/* 바 차트 */}
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={chartData} layout="vertical"
                  margin={{ left: 52, right: 20, top: 2, bottom: 0 }}
                  onClick={e => e?.activeTooltipIndex != null && setActiveIdx(e.activeTooltipIndex)}>
          <XAxis type="number" domain={[0, 45]} tick={{ fill: '#475569', fontSize: 9 }}
                 tickFormatter={v => `${v}%`} />
          <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} width={52} />
          <RTooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6, fontSize: 11 }}
            formatter={(v) => [`기여도 ${v}%`, '']}
            labelStyle={{ color: '#e2e8f0' }}
          />
          <Bar dataKey="pct" radius={[0, 3, 3, 0]} cursor="pointer">
            {chartData.map((d, i) => (
              <Cell key={i} fill={d.color}
                    opacity={i === activeIdx ? 1 : 0.55}
                    strokeWidth={i === activeIdx ? 1.5 : 0}
                    stroke={i === activeIdx ? '#fff' : 'none'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div style={xaiSt.hint}>↑ 막대를 클릭하면 원인 설명을 볼 수 있습니다</div>

      {/* 선택된 원인 자연어 설명 */}
      {active && (
        <div style={{ ...xaiSt.explainBox, borderColor: sevColor, background: sevColor + '12' }}>
          <div style={xaiSt.explainHeader}>
            <span style={xaiSt.explainIcon}>{meta?.icon ?? '📊'}</span>
            <div>
              <div style={{ ...xaiSt.explainTitle, color: sevColor }}>
                {meta?.label ?? active.feature}
              </div>
              <div style={xaiSt.explainMeta}>
                측정값 {active.value != null ? `${active.value} ${meta?.unit ?? ''}` : 'N/A'}
                {' / '}기준 {meta?.threshold ?? '—'} {meta?.unit ?? ''}
                {' · '}기여도 {Math.round((active.importance ?? 0) * 100)}%
              </div>
            </div>
          </div>

          {explanation ? (
            <>
              <div style={xaiSt.explainText}>{explanation.explain}</div>
              <div style={{ ...xaiSt.actionBox, borderColor: sevColor }}>
                <span style={{ ...xaiSt.actionIcon, color: sevColor }}>💡</span>
                <span style={xaiSt.actionText}>{explanation.action}</span>
              </div>
            </>
          ) : (
            <div style={xaiSt.explainText}>정상 범위 내에 있습니다.</div>
          )}
        </div>
      )}

      {/* 변수 선택 탭 */}
      <div style={xaiSt.tabs}>
        {sorted.slice(0, 5).map((c, i) => (
          <button key={i}
            style={{ ...xaiSt.tab, ...(i === activeIdx ? { background: XAI_COLORS[i] + '30', borderColor: XAI_COLORS[i], color: '#e2e8f0' } : {}) }}
            onClick={() => setActiveIdx(i)}
          >
            {XAI_EXPLANATIONS[c.feature]?.icon ?? '📊'} {Math.round((c.importance ?? 0) * 100)}%
          </button>
        ))}
      </div>
    </div>
  );
}

const xaiSt = {
  loading: { color: '#f59e0b', fontSize: 12, textAlign: 'center', padding: '12px 0', animation: 'pulse 1.5s infinite' },
  empty:   { color: '#475569', fontSize: 12, textAlign: 'center', padding: 16 },
  hint:    { color: '#334155', fontSize: 10, textAlign: 'center', marginBottom: 8, marginTop: 2 },
  explainBox: {
    border: '1px solid', borderRadius: 8, padding: '10px 12px',
    marginBottom: 8,
  },
  explainHeader: { display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 8 },
  explainIcon:   { fontSize: 18, flexShrink: 0 },
  explainTitle:  { fontWeight: 700, fontSize: 13, lineHeight: 1.2 },
  explainMeta:   { color: '#64748b', fontSize: 10, marginTop: 2 },
  explainText:   { color: '#cbd5e1', fontSize: 12, lineHeight: 1.7, marginBottom: 8 },
  actionBox: {
    display: 'flex', alignItems: 'flex-start', gap: 6,
    background: 'rgba(255,255,255,0.04)', borderLeft: '2px solid',
    borderRadius: '0 4px 4px 0', padding: '6px 8px',
  },
  actionIcon: { fontSize: 13, flexShrink: 0, marginTop: 1 },
  actionText: { color: '#94a3b8', fontSize: 11, lineHeight: 1.6 },
  tabs: { display: 'flex', gap: 4, flexWrap: 'wrap' },
  tab: {
    background: '#0f172a', border: '1px solid #1e293b', color: '#64748b',
    borderRadius: 6, padding: '3px 8px', cursor: 'pointer', fontSize: 11,
  },
};

const llmSt = {
  box:      { background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 8, padding: '10px 12px' },
  summary:  { color: '#e2e8f0', fontSize: 12, lineHeight: 1.7, marginBottom: 8 },
  causes:   { display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 8 },
  causeRow: { display: 'flex', gap: 6, alignItems: 'flex-start' },
  causeIcon:{ fontSize: 12, flexShrink: 0, marginTop: 1 },
  causeText:{ color: '#94a3b8', fontSize: 11, lineHeight: 1.6 },
  recBox:   { borderTop: '1px solid #1e293b', paddingTop: 7, marginTop: 2 },
  recTitle: { color: '#475569', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 },
  recRow:   { color: '#6ee7b7', fontSize: 11, lineHeight: 1.7 },
  err:      { color: '#64748b', fontSize: 9, marginTop: 6, fontStyle: 'italic' },
};

// ── 현장 사진 슬라이더 ────────────────────────────────────
function FieldPhotoSlider({ photos }) {
  const [idx, setIdx] = useState(0);
  if (!photos?.length) return null;
  const photo = photos[idx];
  return (
    <div style={photoSt.wrap}>
      <img src={photo.src} alt={photo.caption}
           style={photoSt.img}
           onError={e => { e.target.style.display = 'none'; }} />
      <div style={photoSt.caption}>{photo.caption}</div>
      {photos.length > 1 && (
        <div style={photoSt.dots}>
          {photos.map((_, i) => (
            <button key={i} style={{ ...photoSt.dot, ...(i === idx ? photoSt.dotOn : {}) }}
                    onClick={() => setIdx(i)} />
          ))}
        </div>
      )}
    </div>
  );
}
const photoSt = {
  wrap:    { borderRadius: 8, overflow: 'hidden', border: '1px solid #1e3a5f', marginBottom: 4, position: 'relative', background: '#0a1628' },
  img:     { width: '100%', height: 110, objectFit: 'cover', display: 'block' },
  caption: { color: '#64748b', fontSize: 10, padding: '4px 8px', textAlign: 'center', background: '#0a1628' },
  dots:    { display: 'flex', justifyContent: 'center', gap: 4, padding: '4px 0', background: '#0a1628' },
  dot:     { width: 5, height: 5, borderRadius: '50%', border: 'none', background: '#334155', cursor: 'pointer', padding: 0 },
  dotOn:   { background: '#60a5fa' },
};

// ── 모델 입력 8차원 정규화 벡터 (백엔드 _build_sensor_vector 미러) ──
const FEATURE_ORDER = ['수온', 'DO', 'DIN', 'DIP', 'N:P', '염분', '강수', '클로로필'];
function buildFeatureVector(sv = {}) {
  const n = (v) => Math.round(v * 100) / 100;
  return [
    n(((sv.water_temp ?? 15) - 15) / 5),
    n(((sv.dissolved_oxygen ?? 8) - 8) / 2),
    n(((sv.din ?? 5) - 5) / 5),
    n(((sv.dip ?? 0.5) - 0.5) / 0.3),
    n(((sv.np_ratio ?? 16) - 16) / 8),
    n(((sv.salinity ?? 32) - 32) / 2),
    n((sv.precipitation ?? 0) / 10),
    n(((sv.chlorophyll_a ?? 3) - 3) / 2),
  ];
}

// ── 메인 인포 패널 ────────────────────────────────────────
function InfoPanel({ farm, liveData, snapshot, xaiData, xaiLoading, llmReport, llmLoading, forecast7d, onClose }) {
  const wbi = liveData?.wbi_score ?? null;
  const sev = severityLabel(wbi);
  // 7일 후 예측: forecast 엔드포인트 값 우선, 로딩 전엔 근사식 fallback
  const predict7d = forecast7d != null ? forecast7d
    : (wbi != null ? Math.min(1, wbi * 1.18 + 0.03) : null);

  // 어장 유형별 현장 사진 선택
  const photos = farm.rack_type === '부류식' ? FIELD_PHOTOS.buoy : FIELD_PHOTOS.farm;

  return (
    <div style={infoSt.panel}>
      {/* 헤더 */}
      <div style={infoSt.header}>
        <div>
          <div style={infoSt.title}>{farm.name}</div>
          <div style={infoSt.sub}>{farm.city} · {farm.species} · {farm.rack_type}</div>
        </div>
        <button style={infoSt.close} onClick={onClose}>✕</button>
      </div>

      {/* 현장 사진 슬라이더 */}
      <FieldPhotoSlider photos={photos} />

      {/* WBI + 7일 예측 */}
      <div style={infoSt.wbiRow}>
        <div style={{ ...infoSt.wbiBox, borderColor: sev.color, background: sev.color + '18' }}>
          <div style={infoSt.wbiLabel}>현재 황백화 위험도</div>
          <div style={{ ...infoSt.wbiVal, color: sev.color }}>
            {wbi != null ? `${(wbi * 100).toFixed(1)}%` : '—'}
          </div>
          <div style={{ ...infoSt.wbiBadge, background: sev.color }}>{sev.text}</div>
        </div>
        <div style={{ ...infoSt.wbiBox, borderColor: '#6366f1', background: '#6366f118' }}>
          <div style={infoSt.wbiLabel}>7일 후 예측</div>
          <div style={{ ...infoSt.wbiVal, color: '#818cf8' }}>
            {predict7d != null ? `${(predict7d * 100).toFixed(1)}%` : '—'}
          </div>
          <div style={{ ...infoSt.wbiBadge, background: '#6366f1' }}>AI 예측</div>
        </div>
      </div>

      {/* 실시간 센서 */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>실시간 센서값 (WebSocket)</div>
        <div style={infoSt.sensorGrid}>
          {[
            ['수온', liveData?.water_temp, '℃'],
            ['DO', liveData?.dissolved_oxygen, 'mg/L'],
            ['DIN', liveData?.din, 'μmol/L'],
            ['N:P', liveData?.np_ratio, ''],
            ['염분', liveData?.salinity, 'PSU'],
          ].map(([label, val, unit]) => (
            <div key={label} style={infoSt.sensorCard}>
              <div style={infoSt.sensorLabel}>{label}</div>
              <div style={infoSt.sensorVal}>
                {val != null ? parseFloat(val).toFixed(2) : '—'}
              </div>
              {unit && <div style={infoSt.sensorUnit}>{unit}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* XAI 원인 분석 + 자연어 설명 */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>
          🧠 AI 황백화 원인 분석
          {xaiLoading && <span style={{ color: '#f59e0b', fontSize: 10, marginLeft: 6 }}>분석 중...</span>}
        </div>
        <XAIPanel causes={xaiData?.top_causes} loading={xaiLoading} />
      </div>

      {/* 엽체 황백화 Attention 히트맵 오버레이 */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>🔬 엽체 황백화 진단맵 (XAI 오버레이)</div>
        <XaiHeatmapOverlay farm={farm} snapshot={snapshot} />
      </div>

      {/* LLM 자연어 분석 (Gemini) */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>
          🤖 LLM 종합 분석
          {llmReport && (
            <span style={{
              marginLeft: 6, fontSize: 9, padding: '1px 6px', borderRadius: 8,
              background: llmReport.used_llm ? '#064e3b' : '#3f3f00',
              color: llmReport.used_llm ? '#6ee7b7' : '#fde68a',
            }}>
              {llmReport.used_llm ? `Gemini ${llmReport.model ?? ''}` : '템플릿(키 없음)'}
            </span>
          )}
        </div>
        {llmLoading && <div style={xaiSt.loading}>🤖 Gemini 분석 생성 중...</div>}
        {!llmLoading && llmReport && (
          <div style={llmSt.box}>
            <div style={llmSt.summary}>{llmReport.summary}</div>
            {llmReport.cause_analysis?.length > 0 && (
              <div style={llmSt.causes}>
                {llmReport.cause_analysis.map((c, i) => (
                  <div key={i} style={llmSt.causeRow}>
                    <span style={llmSt.causeIcon}>{XAI_EXPLANATIONS[c.feature]?.icon ?? '•'}</span>
                    <span style={llmSt.causeText}>{c.text}</span>
                  </div>
                ))}
              </div>
            )}
            {llmReport.recommendations?.length > 0 && (
              <div style={llmSt.recBox}>
                <div style={llmSt.recTitle}>권장 조치</div>
                {llmReport.recommendations.map((r, i) => (
                  <div key={i} style={llmSt.recRow}>✓ {r}</div>
                ))}
              </div>
            )}
            {llmReport.llm_error && (
              <div style={llmSt.err}>⚠ LLM 폴백 사유: {llmReport.llm_error}</div>
            )}
          </div>
        )}
      </div>

      {/* 관측 네트워크 + 현장 사진 */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>최근접 관측 네트워크</div>
        <div style={infoSt.obsRow}>
          <span style={{ ...infoSt.obsTag, background: '#1e3a5f', color: '#93c5fd' }}>
            🔵 {farm.nearest_buoy}
          </span>
          <span style={{ ...infoSt.obsTag, background: '#1c1400', color: '#fde68a' }}>
            🟠 {farm.nearest_tide}
          </span>
        </div>
        <FieldPhotoSlider photos={FIELD_PHOTOS.tide} />
        <div style={infoSt.idwNote}>
          IDW 거리가중 보간: w<sub>i</sub> = (1/d<sub>i</sub>) / Σ(1/d<sub>j</sub>)
        </div>
      </div>

      {/* 어장 GIS 속성 */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>어장 GIS 속성</div>
        {[
          ['면허번호', farm.permit_id],
          ['관할해역', farm.sea_area],
          ['면적', `${(farm.area_m2 / 10000).toFixed(2)} ha`],
          ['수심', `${farm.depth} m`],
          ['조차', `${farm.tidal_range} m`],
          ['유속', `${farm.current_speed} m/s`],
          ['염분(기준)', `${farm.salinity} PSU`],
          ['운영상태', farm.status],
        ].map(([k, v]) => (
          <div key={k} style={infoSt.row}>
            <span style={infoSt.key}>{k}</span>
            <span style={infoSt.val}>{v}</span>
          </div>
        ))}
      </div>

      {/* Spatial Token — 모델 입력 (정규화 8차원 벡터) */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>Spatial Token · 모델 입력</div>
        <pre style={infoSt.json}>{JSON.stringify({
          polygon_id: farm.id,
          centroid: farm.centroid,
          area_m2: farm.area_m2,
          feature_vector: buildFeatureVector(snapshot?.sensor_vals),
        }, null, 2)}</pre>
        <div style={infoSt.tokenHint}>
          feature_vector = [{FEATURE_ORDER.join(', ')}] · 평균 0 기준 정규화
          (TinyTransformer 입력 8채널)
        </div>
      </div>

      {/* Model Output — 모델 출력 (입력과 분리) */}
      <div style={infoSt.section}>
        <div style={infoSt.secTitle}>Model Output · 모델 출력</div>
        <pre style={{ ...infoSt.json, color: '#fca5a5', borderColor: '#7f1d1d' }}>{JSON.stringify({
          wbi_score: wbi != null ? +wbi.toFixed(3) : null,
          stage: snapshot?.stage ?? null,
          label: wbi != null && wbi >= 0.6 ? '황백화 발생' : '정상',
        }, null, 2)}</pre>
        <div style={infoSt.tokenHint}>
          wbi_score: 황백화 지수(0~1) · stage: 0정상~4심각 · label: 0.6 이상이면 발생
        </div>
      </div>
    </div>
  );
}

const infoSt = {
  panel: {
    position: 'absolute', top: 0, right: 0, bottom: 0, width: 310,
    background: '#0d1b2e', borderLeft: '1px solid #1e3a5f',
    overflowY: 'auto', zIndex: 1000, padding: '14px 14px',
    boxSizing: 'border-box',
    fontFamily: "'Pretendard', 'Noto Sans KR', system-ui, sans-serif",
  },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  title:  { color: '#e2e8f0', fontWeight: 700, fontSize: 14, lineHeight: 1.3 },
  sub:    { color: '#475569', fontSize: 11, marginTop: 2 },
  close:  { background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 16 },

  wbiRow: { display: 'flex', gap: 8, marginBottom: 14 },
  wbiBox: { flex: 1, borderRadius: 8, border: '1px solid', padding: '10px 8px', textAlign: 'center' },
  wbiLabel: { color: '#64748b', fontSize: 10, marginBottom: 4 },
  wbiVal:   { fontSize: 20, fontWeight: 800, marginBottom: 4 },
  wbiBadge: { display: 'inline-block', color: '#fff', fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 10 },

  section:  { marginBottom: 14 },
  secTitle: { color: '#475569', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 },
  loading:  { color: '#f59e0b', fontSize: 10, fontWeight: 400 },

  sensorGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 },
  sensorCard: { background: '#0f172a', borderRadius: 6, padding: '7px 6px', textAlign: 'center', border: '1px solid #1e293b' },
  sensorLabel: { color: '#64748b', fontSize: 9, marginBottom: 2 },
  sensorVal:   { color: '#f59e0b', fontSize: 14, fontWeight: 700 },
  sensorUnit:  { color: '#334155', fontSize: 9 },

  row:  { display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid #0f172a' },
  key:  { color: '#64748b', fontSize: 11 },
  val:  { color: '#cbd5e1', fontSize: 11 },

  obsRow: { display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 },
  obsTag: { fontSize: 11, padding: '3px 8px', borderRadius: 6, fontWeight: 600 },
  idwNote: { color: '#334155', fontSize: 10, fontStyle: 'italic' },

  json: {
    background: '#0f172a', borderRadius: 6, padding: 8, fontSize: 10,
    color: '#a3e635', overflowX: 'auto', border: '1px solid #1e293b',
    margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.5,
  },
  tokenHint: { color: '#475569', fontSize: 9, lineHeight: 1.5, marginTop: 5 },
};

// ── 범례 ──────────────────────────────────────────────────
function Legend() {
  return (
    <div style={legSt.box}>
      <div style={legSt.title}>황백화 위험도</div>
      {[
        ['#94a3b8', '데이터 없음'],
        ['#22c55e', '정상 < 30%'],
        ['#f59e0b', '주의 30~60%'],
        ['#f97316', '경고 60~80%'],
        ['#ef4444', '위험 ≥ 80%'],
      ].map(([c, l]) => (
        <div key={l} style={legSt.row}>
          <div style={{ ...legSt.dot, background: c }} />
          <span style={legSt.label}>{l}</span>
        </div>
      ))}
      <div style={{ borderTop: '1px solid #1e3a5f', marginTop: 7, paddingTop: 7 }}>
        <div style={legSt.row}><span style={legSt.icon}>🔵</span><span style={legSt.label}>관측 부이</span></div>
        <div style={legSt.row}><span style={legSt.icon}>🟠</span><span style={legSt.label}>조위관측소</span></div>
      </div>
    </div>
  );
}
const legSt = {
  box:   { position: 'absolute', bottom: 54, left: 10, zIndex: 999, background: 'rgba(10,22,40,0.93)', borderRadius: 8, padding: '10px 14px', border: '1px solid #1e3a5f', minWidth: 155, pointerEvents: 'none' },
  title: { color: '#64748b', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 7 },
  row:   { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 },
  dot:   { width: 12, height: 9, borderRadius: 2, opacity: 0.85, border: '1px solid rgba(255,255,255,0.2)' },
  label: { color: '#cbd5e1', fontSize: 11 },
  icon:  { fontSize: 12, width: 14, textAlign: 'center' },
};

// ── 메인 컴포넌트 ─────────────────────────────────────────
export default function FarmMap({ liveData }) {
  const [selected, setSelected]       = useState(null);
  const [flyTarget, setFlyTarget]     = useState(null);
  const [tileKey, setTileKey]         = useState('satellite');
  const [showBuoy, setShowBuoy]       = useState(true);
  const [showTide, setShowTide]       = useState(true);
  const [regionFilter, setRegionFilter] = useState('전체');
  const [xaiData, setXaiData]         = useState(null);
  const [xaiLoading, setXaiLoading]   = useState(false);
  const [snapshot, setSnapshot]       = useState(null);   // 클릭 어장 더미 스냅샷
  const [llmReport, setLlmReport]     = useState(null);   // Gemini XAI 보고서
  const [llmLoading, setLlmLoading]   = useState(false);
  const [forecast7d, setForecast7d]   = useState(null);   // 7일 후 예측 WBI (forecast 엔드포인트)

  // 클릭 어장의 더미 sensor_vals 로 predict → /explain/llm 까지 일관 호출
  const fetchAnalysis = useCallback(async (farm, dummy) => {
    setXaiLoading(true); setLlmLoading(true);
    setXaiData(null); setLlmReport(null); setForecast7d(null);

    // 7일 예측 (fire-and-forget — 패널 7일 후 값 일관화)
    fetch(`${API_BASE}/predict/forecast`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ farm_id: farm.id, sensor_vals: dummy.sensor_vals }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j?.series?.length) setForecast7d(j.series[j.series.length - 1].wbi); })
      .catch(() => {});

    let predTopCauses = [];
    let anomalyScore = dummy.wbi;
    let stage = dummy.stage;

    // 1) predict — 어장별 더미 센서값 전달 (수치 일관)
    try {
      const pr = await fetch(`${API_BASE}/predict/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ farm_id: farm.id, sensor_vals: dummy.sensor_vals }),
      });
      const pred = await pr.json();
      predTopCauses = pred.top_causes ?? [];
      if (typeof pred.anomaly_score === 'number') anomalyScore = pred.anomaly_score;
      if (typeof pred.stage === 'number') stage = pred.stage;
      setXaiData({ top_causes: predTopCauses });
    } catch (e) {
      setXaiData({ top_causes: [] });
    } finally {
      setXaiLoading(false);
    }

    // 2) explain/llm — 같은 컨텍스트로 Gemini 자연어 보고서
    try {
      const lr = await fetch(`${API_BASE}/explain/llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          farm_id: farm.id,
          farm_name: farm.name,
          region: farm.city,
          stage,
          anomaly_score: anomalyScore,
          sensor_vals: dummy.sensor_vals,
          top_causes: predTopCauses,
        }),
      });
      setLlmReport(await lr.json());
    } catch (e) {
      setLlmReport({ summary: 'LLM 분석 서버에 연결할 수 없습니다.', used_llm: false, cause_analysis: [], recommendations: [] });
    } finally {
      setLlmLoading(false);
    }
  }, []);

  const handleFarmClick = useCallback(async (farm) => {
    setSelected(farm);
    const [lon, lat] = farm.centroid;
    setFlyTarget([lat, lon]);

    // 실데이터 시도 → 실패 시 더미 fallback
    let snapshot;
    try {
      const res = await fetch(`${API_BASE}/sensor/by-latlon?lat=${lat}&lon=${lon}`);
      if (res.ok) {
        const real = await res.json();
        snapshot = {
          ...farmDummy(farm),           // stage/wbi/label 등 기존 필드 유지
          sensor_vals: real.sensor_vals,
          pred_label: real.pred_label,
          pred_label_name: real.pred_label_name,
          class_probs: real.class_probs,
          anomaly_score: real.anomaly_score,
          cube_date: real.cube_date,
          wbi: real.anomaly_score,
          stage: real.pred_label,
          data_source: 'cube_v5_real',
        };
      } else {
        snapshot = farmDummy(farm);
      }
    } catch {
      snapshot = farmDummy(farm);
    }

    setSnapshot(snapshot);
    fetchAnalysis(farm, snapshot);
  }, [fetchAnalysis]);

  const filteredFarms = useMemo(() =>
    regionFilter === '전체'
      ? ALL_FARMS
      : ALL_FARMS.filter(f => f.city.startsWith(regionFilter.slice(0, 2))),
    [regionFilter]
  );

  const tile = TILES[tileKey];
  const regions = ['전체', ...Object.keys(REGION_GROUPS)];

  return (
    <div style={mapSt.wrapper}>
      {/* 툴바 */}
      <div style={mapSt.toolbar}>
        <div style={mapSt.tbLeft}>
          <span style={mapSt.tbTitle}>🗺️ 김 양식장 GIS 현황맵</span>
          <span style={mapSt.tbCount}>{ALL_FARMS.length}개 어장 · {OBSERVATION_STATIONS.length}개 관측소</span>
        </div>
        <div style={mapSt.tbRight}>
          <select style={mapSt.select} value={regionFilter} onChange={e => setRegionFilter(e.target.value)}>
            {regions.map(r => <option key={r}>{r}</option>)}
          </select>
          {Object.entries(TILES).map(([k, t]) => (
            <button key={k}
              style={{ ...mapSt.btn, ...(tileKey === k ? mapSt.btnOn : {}) }}
              onClick={() => setTileKey(k)}>{t.label}</button>
          ))}
          <button style={{ ...mapSt.btn, ...(showBuoy ? mapSt.btnOn : {}) }}
            onClick={() => setShowBuoy(p => !p)}>부이</button>
          <button style={{ ...mapSt.btn, ...(showTide ? mapSt.btnOn : {}) }}
            onClick={() => setShowTide(p => !p)}>조위소</button>
        </div>
      </div>

      {/* 지도 + 패널 */}
      <div style={mapSt.body}>
        <MapContainer
          center={[34.4, 126.7]} zoom={9}
          style={mapSt.map}
          zoomControl={true}
          attributionControl={true}
        >
          {/* 타일 레이어 */}
          <TileLayer
            key={tileKey}
            url={tile.url}
            attribution={tile.attribution}
            maxZoom={tile.maxZoom}
          />

          {/* 중심 이동 트리거 */}
          {flyTarget && <FlyTo center={flyTarget} zoom={12} />}

          {/* 양식장 Polygon */}
          {filteredFarms.map(farm => {
            const isSelected = selected?.id === farm.id;
            const c = wbiColor(farmWbi(farm));
            return (
              <Polygon
                key={farm.id}
                positions={farm.coordinates[0].map(([lon, lat]) => [lat, lon])}
                pathOptions={{
                  color:       isSelected ? '#60a5fa' : c.color,
                  fillColor:   isSelected ? '#60a5fa' : c.fill,
                  fillOpacity: isSelected ? 0.55      : c.opacity,
                  weight:      isSelected ? 2.5       : 1.5,
                  dashArray:   isSelected ? null      : '5 3',
                }}
                eventHandlers={{ click: () => handleFarmClick(farm) }}
              >
                <Tooltip direction="top" sticky>
                  <b>{farm.name}</b><br />
                  {farm.species} · {farm.rack_type}<br />
                  {(farm.area_m2 / 10000).toFixed(1)} ha
                </Tooltip>
              </Polygon>
            );
          })}

          {/* 관측 부이 */}
          {showBuoy && OBSERVATION_STATIONS
            .filter(s => s.type === 'buoy')
            .map(s => (
              <CircleMarker key={s.id}
                center={[s.lat, s.lon]}
                radius={6}
                pathOptions={{ color: '#93c5fd', fillColor: '#3b82f6', fillOpacity: 0.85, weight: 1.5 }}
              >
                <Tooltip direction="top">
                  <b>{s.name}</b><br />관측 부이
                </Tooltip>
              </CircleMarker>
            ))
          }

          {/* 조위관측소 */}
          {showTide && OBSERVATION_STATIONS
            .filter(s => s.type === 'tide')
            .map(s => (
              <CircleMarker key={s.id}
                center={[s.lat, s.lon]}
                radius={6}
                pathOptions={{ color: '#fed7aa', fillColor: '#f97316', fillOpacity: 0.85, weight: 1.5 }}
              >
                <Tooltip direction="top">
                  <b>{s.name}</b><br />조위관측소
                </Tooltip>
              </CircleMarker>
            ))
          }
        </MapContainer>

        {/* 좌측 범례 (지도 위) */}
        <Legend />

        {/* 우측 인포 패널 */}
        {selected && (
          <InfoPanel
            farm={selected}
            liveData={snapshot ? {
              farm_id: selected.id,
              water_temp: snapshot.sensor_vals.water_temp,
              dissolved_oxygen: snapshot.sensor_vals.dissolved_oxygen,
              din: snapshot.sensor_vals.din,
              np_ratio: snapshot.sensor_vals.np_ratio,
              salinity: snapshot.sensor_vals.salinity,
              wbi_score: snapshot.wbi,
            } : null}
            snapshot={snapshot}
            xaiData={xaiData}
            xaiLoading={xaiLoading}
            llmReport={llmReport}
            llmLoading={llmLoading}
            forecast7d={forecast7d}
            onClose={() => {
              setSelected(null); setXaiData(null); setFlyTarget(null);
              setSnapshot(null); setLlmReport(null); setForecast7d(null);
            }}
          />
        )}

        {/* 미선택 안내 */}
        {!selected && (
          <div style={mapSt.hint}>
            양식장 구역을 클릭하면 XAI 황백화 분석을 볼 수 있습니다
          </div>
        )}
      </div>

      {/* 하단 지역 요약 탭 */}
      <div style={mapSt.regionBar}>
        {regions.map(r => (
          <div key={r}
            style={{ ...mapSt.regionItem, ...(regionFilter === r ? mapSt.regionOn : {}) }}
            onClick={() => setRegionFilter(r)}
          >
            <div style={mapSt.regionName}>{r}</div>
            <div style={mapSt.regionCount}>
              {r === '전체' ? `${ALL_FARMS.length}개소` : `${(REGION_GROUPS[r] ?? []).length}개소`}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const mapSt = {
  wrapper: {
    background: '#0d1b2e', border: '1px solid #1e3a5f',
    overflow: 'hidden', display: 'flex', flexDirection: 'column',
    fontFamily: "'Pretendard', 'Noto Sans KR', system-ui, sans-serif",
    flex: 1, minHeight: 0,
  },
  toolbar: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '9px 16px', background: '#0a1628', borderBottom: '1px solid #1e3a5f', flexShrink: 0,
  },
  tbLeft:  { display: 'flex', alignItems: 'center', gap: 12 },
  tbTitle: { color: '#e2e8f0', fontWeight: 700, fontSize: 14 },
  tbCount: { color: '#475569', fontSize: 11 },
  tbRight: { display: 'flex', gap: 6, alignItems: 'center' },
  select: {
    background: '#0f172a', border: '1px solid #334155',
    color: '#94a3b8', borderRadius: 6, padding: '3px 8px', fontSize: 11,
  },
  btn: {
    background: '#0f172a', border: '1px solid #1e3a5f', color: '#64748b',
    borderRadius: 6, padding: '3px 10px', cursor: 'pointer', fontSize: 11,
  },
  btnOn: { background: '#1e3a5f', color: '#93c5fd', borderColor: '#3b82f6' },

  body: { position: 'relative', flex: 1, minHeight: 480 },
  map:  { width: '100%', height: '100%' },

  hint: {
    position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)',
    background: 'rgba(10,22,40,0.88)', color: '#64748b', fontSize: 12,
    padding: '6px 16px', borderRadius: 20, border: '1px solid #1e3a5f',
    pointerEvents: 'none', whiteSpace: 'nowrap', zIndex: 999,
  },

  regionBar: {
    display: 'flex', borderTop: '1px solid #1e3a5f',
    background: '#0a1628', flexShrink: 0,
  },
  regionItem: {
    flex: 1, padding: '9px 8px', textAlign: 'center',
    borderRight: '1px solid #1e3a5f', cursor: 'pointer', transition: 'background .15s',
  },
  regionOn:    { background: '#1e3a5f' },
  regionName:  { color: '#94a3b8', fontSize: 11, marginBottom: 2 },
  regionCount: { color: '#60a5fa', fontSize: 13, fontWeight: 700 },
};
