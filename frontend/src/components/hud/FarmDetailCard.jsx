import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchRealSensorByLatLon, fetchRealSensorHistoryByLatLon, provenanceLabel } from '../../data/realSensor';
import { STAGE_LABEL } from '../../data/v13Predictions';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function useCountUp(target, duration = 850, delay = 180) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    setVal(0);
    let raf;
    const t0 = performance.now() + delay;
    const tick = (now) => {
      if (now < t0) { raf = requestAnimationFrame(tick); return; }
      const t = Math.min((now - t0) / duration, 1);
      setVal((1 - Math.pow(1 - t, 3)) * target);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setVal(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return val;
}

function scoreColor(s) {
  if (s > 0.8) return '#FF4D4F';
  if (s > 0.6) return '#FF8A3D';
  if (s > 0.4) return '#FFD700';
  return '#00FF88';
}
function scoreSev(s) {
  if (s > 0.8) return 'DANGER';
  if (s > 0.6) return 'WARNING';
  if (s > 0.4) return 'CAUTION';
  return 'NORMAL';
}

// 황백화 지표 색상 (단위: μg/L)
function dinColor(v)  { return v < 70  ? '#FF4D4F' : v < 100 ? '#FF8A3D' : '#00FF88'; }
function dipColor(v)  { return v < 6   ? '#FF4D4F' : v < 16  ? '#FF8A3D' : '#00FF88'; }
function npColor(v)   { return v < 6   ? '#FF4D4F' : v < 16  ? '#FF8A3D' : '#00FF88'; }
function riskLabel(v, danger, caution) {
  return v < danger ? 'DANGER' : v < caution ? 'CAUTION' : 'NORMAL';
}

// mock 센서 데이터 (din/dip: μg/L, np: 몰비)
const SENSORS = {
  A1: { temp: 24.8, do: 4.9, sal: 33.1, turb: 12.4, din:  55.2, dip:  5.1, np:  5.9 },
  A2: { temp: 24.3, do: 5.1, sal: 32.8, turb: 10.8, din:  62.1, dip:  8.3, np:  8.2 },
  A3: { temp: 23.9, do: 5.8, sal: 33.4, turb:  8.2, din:  88.4, dip: 12.5, np:  7.7 },
  N1: { temp: 19.2, do: 8.1, sal: 32.2, turb:  2.1, din: 142.3, dip: 28.1, np: 27.8 },
  N2: { temp: 20.1, do: 7.8, sal: 32.5, turb:  3.4, din: 118.6, dip: 22.4, np: 29.1 },
  N3: { temp: 21.5, do: 7.2, sal: 32.9, turb:  4.7, din: 105.2, dip: 19.8, np: 23.2 },
  N4: { temp: 18.9, do: 8.4, sal: 32.0, turb:  1.9, din: 156.7, dip: 31.2, np: 27.6 },
};

// 실측 이력 스파크라인 — series는 실제 관측값 배열(과거→최신). 2점 미만이면 그리지 않는다(가짜 곡선 금지).
function Sparkline({ color, series }) {
  const vals = (series ?? []).filter(Number.isFinite);
  if (vals.length < 2) return null;
  const min = Math.min(...vals), max = Math.max(...vals);
  // 변화 없는 시계열은 최하단이 아니라 중앙에 — 아니면 '최저치'처럼 오독됨
  const norm = max - min < 1e-9
    ? vals.map(() => 22)
    : vals.map(v => 36 - ((v - min) / (max - min)) * 28);
  const step = 70 / (vals.length - 1);
  const path = norm.map((y, i) => `${i === 0 ? 'M' : 'L'}${i * step} ${y}`).join(' ');
  return (
    <svg width={70} height={28} viewBox="0 0 70 40" style={{ opacity: 0.75 }}>
      <defs>
        <linearGradient id={`sg-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <path d={path + ` L${70} 40 L0 40 Z`} fill={`url(#sg-${color.replace('#','')})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx={70} cy={norm[norm.length - 1]} r="2.5" fill={color}/>
    </svg>
  );
}

// stage 라벨 SSOT = data/v13Predictions.js STAGE_LABEL (지도·XAI와 공유).
// 2026-07-17: 여기 따로 정의돼 있던 V7_LABELS를 제거하고 공용 상수로 통일했다(라벨 3중 불일치 해소).
const V7_COLORS = { 0: '#00FF88', 1: '#FFD700', 2: '#FF8A3D', 3: '#FF4D4F' };
const V7_LABELS = STAGE_LABEL;

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, color: 'rgba(255,255,255,0.5)', fontFamily: 'Courier New',
      letterSpacing: 2, marginBottom: 8, marginTop: 4,
      display: 'flex', alignItems: 'center', gap: 6,
    }}>
      <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }}/>
      {children}
      <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }}/>
    </div>
  );
}

export default function FarmDetailCard({ site, onClose, maxH, onDragHandle, onGoXai }) {
  if (!site) return null;

  const col = scoreColor(site.score);
  const sev = scoreSev(site.score);

  // 실측(Bronze) 센서 — 최근접 관측소. 실패 시 기존 mock 폴백.
  const [realSensor, setRealSensor] = useState(null);
  // 관측 이력(분기 n회) — 스파크라인용. 없으면 스파크라인 숨김.
  const [sensorHist, setSensorHist] = useState(null);
  useEffect(() => {
    let alive = true;
    setRealSensor(null);
    setSensorHist(null);
    (async () => {
      const [r, h] = await Promise.all([
        fetchRealSensorByLatLon(site.lat, site.lon),
        fetchRealSensorHistoryByLatLon(site.lat, site.lon),
      ]);
      if (alive) { setRealSensor(r); setSensorHist(h); }
    })();
    return () => { alive = false; };
  }, [site.id]);

  // 더미 폴백 어장은 스파크라인도 숨긴다 — 더미 숫자 옆에 실측 곡선을 두면 출처가 섞여 오도됨
  const histSeries = (key) => (realSensor && sensorHist) ? sensorHist.series.map(p => p[key]) : null;

  const mock = SENSORS[site.id] ?? { temp: 22.0, do: 6.5, sal: 32.5, turb: 5.0, din: 100.0, dip: 20.0, np: 26.0 };
  // HUD 카드의 DIN/DIP 임계는 μg/L 체계 → 실측도 raw_ugl(μg/L)을 쓴다 (μmol/L 혼용 금지)
  const s = realSensor ? {
    temp: realSensor.sensor_vals.water_temp,
    do:   realSensor.sensor_vals.dissolved_oxygen,
    sal:  realSensor.sensor_vals.salinity,
    turb: realSensor.sensor_vals.turbidity ?? 0,
    din:  realSensor.raw_ugl?.din ?? 0,
    dip:  realSensor.raw_ugl?.dip ?? 0,
    np:   realSensor.sensor_vals.np_ratio,
  } : mock;
  // 비양식기/예측없음이면 site.score === null → 점수를 지어내지 않고 '예측 없음'으로 표시
  const hasScore  = typeof site.score === 'number' && Number.isFinite(site.score);
  const isAnomaly = hasScore && site.score > 0.5;
  const animScore = useCountUp(hasScore ? site.score : 0);

  const [scanning, setScanning] = useState(true);
  useEffect(() => {
    setScanning(true);
    const t = setTimeout(() => setScanning(false), 720);
    return () => clearTimeout(t);
  }, [site.id]);

  // v13 예측 fetch — 이제 1194개 전 어장이 gid 키로 팩에 있으므로 **직접 조회**
  // (기존의 '최근접 F어장 매핑' 임시방편은 제거됨 — 근사 없이 이 어장의 실제 예측)
  const [v7Series, setV7Series] = useState(null);
  const [v7Loading, setV7Loading] = useState(false);
  useEffect(() => {
    setV7Series(null);
    setV7Loading(true);
    const ctrl = new AbortController();
    fetch(`${API_BASE}/predict/v7/${site.id}?start=2025-10-01&end=2026-01-31`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : null)
      .then(d => { setV7Series(d?.series ?? null); setV7Loading(false); })
      .catch(() => { if (!ctrl.signal.aborted) setV7Loading(false); });
    return () => ctrl.abort();
  }, [site.id]);

  const latest = v7Series?.[v7Series.length - 1];
  const lc     = V7_COLORS[latest?.stage] ?? '#888';
  const recent = v7Series?.slice(-60) ?? [];

  return (
    <motion.div
      key={site.id}
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1,  y: 0 }}
      exit={{    opacity: 0,  y: -8 }}
      transition={{ type: 'spring', stiffness: 280, damping: 24 }}
      style={{
        background: 'rgb(8,15,32)',
        border: `1px solid ${col}44`,
        borderRadius: 10,
        overflow: 'hidden',
        boxShadow: `0 4px 40px rgba(0,0,0,0.7), 0 0 20px ${col}18`,
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        maxHeight: maxH ? `${maxH}px` : '82vh',
      }}
    >
      {/* 스캐닝 오버레이 */}
      <AnimatePresence>
        {scanning && (
          <motion.div
            key="scan-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{
              position: 'absolute', inset: 0, zIndex: 20,
              background: 'rgba(8,15,32,0.96)',
              borderRadius: 10,
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 14,
            }}
          >
            <motion.div
              animate={{ opacity: [0.25, 1, 0.25] }}
              transition={{ duration: 0.52, repeat: Infinity }}
              style={{ fontSize: 9, color: '#00E5FF', fontFamily: 'Courier New,monospace', letterSpacing: 4, fontWeight: 700 }}
            >SCANNING PARAMETERS</motion.div>
            <div style={{ width: 130, height: 2, background: 'rgba(0,229,255,0.1)', borderRadius: 2, overflow: 'hidden' }}>
              <motion.div
                initial={{ width: 0 }} animate={{ width: '100%' }}
                transition={{ duration: 0.62 }}
                style={{ height: '100%', background: '#00E5FF', boxShadow: '0 0 8px #00E5FF' }}
              />
            </div>
            <div style={{ fontSize: 10, color: `${col}cc`, fontFamily: 'Courier New,monospace', letterSpacing: 2 }}>
              {site.name}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 상단 액센트 */}
      <motion.div
        initial={{ scaleX: 0 }} animate={{ scaleX: 1 }}
        transition={{ duration: 0.45, ease: 'easeOut' }}
        style={{ height: 2, flexShrink: 0, transformOrigin: 'left', background: `linear-gradient(90deg, ${col}, ${col}44, transparent)` }}
      />

      {/* 헤더 (고정 · 드래그 핸들) */}
      <div
        onPointerDown={onDragHandle}
        style={{ padding: '16px 18px 12px', flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
          cursor: onDragHandle ? 'grab' : 'default', touchAction: 'none', userSelect: 'none' }}
      >
        <div>
          <div style={{ fontSize: 10, color: `${col}dd`, fontFamily: 'Courier New', letterSpacing: 3, marginBottom: 5, display: 'flex', alignItems: 'center', gap: 6 }}>
            {onDragHandle && <span style={{ color: `${col}99`, fontSize: 12, letterSpacing: 0 }}>⠿</span>}
            SELECTED FARM
          </div>
          <div style={{ fontSize: 19, fontWeight: 800, color: '#fff', lineHeight: 1.2 }}>
            {site.name}
          </div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', fontFamily: 'Courier New', marginTop: 4 }}>
            {site.lat.toFixed(4)}°N · {site.lon.toFixed(4)}°E
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          <button
            onClick={onClose}
            onPointerDown={(e) => e.stopPropagation()}
            style={{
              background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.5)',
              color: 'rgba(255,255,255,0.7)', width: 26, height: 26, borderRadius: 5,
              cursor: 'pointer', fontSize: 12, padding: 0, lineHeight: '26px',
            }}
          >✕</button>
          <motion.div
            animate={isAnomaly ? { opacity: [0.65, 1, 0.65] } : {}}
            transition={{ duration: 1.6, repeat: Infinity }}
            style={{
              padding: '3px 10px', borderRadius: 4, fontSize: 10, fontWeight: 700,
              letterSpacing: 2, fontFamily: 'Courier New',
              background: `${col}18`, border: `1px solid ${col}55`, color: col,
            }}
          >{sev}</motion.div>
        </div>
      </div>

      {/* ─── 스크롤 영역 ─── */}
      <div style={{
        flex: 1, overflowY: 'auto', overflowX: 'hidden',
        padding: '0 18px',
        scrollbarWidth: 'thin',
        scrollbarColor: `${col}33 transparent`,
      }}>

        {/* ① 위험도 — 예측이 없으면(비양식기 등) 점수를 만들어내지 않는다 */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.58)', fontFamily: 'Courier New', letterSpacing: 2 }}>
              위험도
            </span>
            {hasScore ? (
              <span style={{ fontSize: 30, fontWeight: 900, color: col, fontFamily: 'Courier New', lineHeight: 1 }}>
                {animScore.toFixed(2)}
              </span>
            ) : (
              <span style={{ fontSize: 13, fontWeight: 700, color: 'rgba(190,205,225,0.85)' }}>
                예측 없음 (비양식기)
              </span>
            )}
          </div>
          {hasScore && (
            <div style={{ height: 10, borderRadius: 4, overflow: 'hidden', position: 'relative', background: 'rgba(255,255,255,0.05)' }}>
              {[[0,0.4,'#00FF8830'],[0.4,0.6,'#FFD70030'],[0.6,0.8,'#FF8A3D30'],[0.8,1.0,'#FF4D4F30']].map(([f,t,bg]) => (
                <div key={f} style={{ position:'absolute', top:0, bottom:0, left:`${f*100}%`, width:`${(t-f)*100}%`, background:bg }}/>
              ))}
              <motion.div
                initial={{ width: 0 }} animate={{ width: `${site.score * 100}%` }}
                transition={{ duration: 0.9, delay: 0.1, ease: [0.25, 0.46, 0.45, 0.94] }}
                style={{
                  position: 'absolute', top: 0, left: 0, height: '100%',
                  background: `linear-gradient(90deg, ${col}60, ${col})`,
                  boxShadow: `0 0 10px ${col}`, borderRadius: 4,
                }}
              />
            </div>
          )}
        </div>

        {/* ② STMMT v13 예측 — 이 어장의 실제 예측 (근사 아님) */}
        <SectionLabel>STMMT v13 황백화 예측</SectionLabel>
        <div style={{
          background: 'rgba(0,229,255,0.04)',
          border: '1px solid rgba(0,229,255,0.15)', borderRadius: 8, padding: '14px 14px', marginBottom: 14,
        }}>
          {v7Loading && (
            <div style={{ textAlign: 'center', fontSize: 11, color: 'rgba(0,229,255,0.5)', fontFamily: 'Courier New', letterSpacing: 2, padding: '10px 0' }}>
              LOADING...
            </div>
          )}
          {!v7Loading && !v7Series && (
            <div style={{ textAlign: 'center', fontSize: 11, color: 'rgba(255,100,100,0.5)', fontFamily: 'Courier New', padding: '8px 0' }}>
              서버 미연결 — 예측 데이터 없음
            </div>
          )}
          {!v7Loading && v7Series && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div>
                  <div style={{ fontSize: 10, color: 'rgba(0,229,255,0.5)', fontFamily: 'Courier New', letterSpacing: 2, marginBottom: 4 }}>
                    최신 예측 · {latest?.date}
                  </div>
                  <div style={{ fontSize: 26, fontWeight: 900, color: lc, fontFamily: 'Courier New' }}>
                    {V7_LABELS[latest?.stage]}
                    <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.58)', marginLeft: 8, fontWeight: 400 }}>
                      stage {latest?.stage}
                    </span>
                  </div>
                </div>
                <div style={{
                  padding: '4px 10px', borderRadius: 4, fontSize: 10,
                  background: `${lc}18`, border: `1px solid ${lc}55`, color: lc,
                  fontFamily: 'Courier New', letterSpacing: 1,
                }}>STMMT v7</div>
              </div>
              <div style={{ marginBottom: 6 }}>
                <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.5)', fontFamily: 'Courier New', letterSpacing: 2, marginBottom: 6 }}>
                  최근 60일 stage 추이
                </div>
                <div style={{ display: 'flex', gap: 1.5, height: 28, alignItems: 'flex-end' }}>
                  {recent.map((p, i) => {
                    const c = V7_COLORS[p.stage] ?? '#888';
                    const h = [8, 13, 19, 28][p.stage] ?? 8;
                    return (
                      <div key={i} title={`${p.date}: ${V7_LABELS[p.stage]}`}
                        style={{
                          flex: 1, height: h, borderRadius: 2, background: c,
                          opacity: i === recent.length - 1 ? 1 : 0.6,
                          boxShadow: i === recent.length - 1 ? `0 0 6px ${c}` : 'none',
                        }}
                      />
                    );
                  })}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                  <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.5)', fontFamily: 'Courier New' }}>{recent[0]?.date?.slice(5)}</span>
                  <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.5)', fontFamily: 'Courier New' }}>{recent[recent.length-1]?.date?.slice(5)}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
                {[0,1,2,3].map(st => (
                  <div key={st} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 2, background: V7_COLORS[st] }}/>
                    <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.58)', fontFamily: 'Courier New' }}>{V7_LABELS[st]}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* ③ 황백화 핵심 지표 (DIN / DIP / N:P) */}
        <SectionLabel>영양염 · 황백화 임계치</SectionLabel>
        <div style={{
          fontSize: 9, fontFamily: 'Courier New', marginBottom: 6, letterSpacing: 0.5,
          color: realSensor ? 'rgba(0,255,136,0.75)' : 'rgba(255,211,0,0.7)',
        }}>
          {realSensor
            ? `● 실측 — ${provenanceLabel(realSensor.provenance)}`
            : '● 더미 데이터 (실측 미연결) — 아래 센서값 전체'}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
          {[
            { key: 'din', label: 'DIN',  val: s.din, unit: 'μg/L', color: dinColor(s.din), label2: riskLabel(s.din, 70, 100),  bar: Math.min(s.din / 150, 1) },
            { key: 'dip', label: 'DIP',  val: s.dip, unit: 'μg/L', color: dipColor(s.dip), label2: riskLabel(s.dip, 6, 16),    bar: Math.min(s.dip / 40, 1)  },
            { key: 'np',  label: 'N:P',  val: s.np,  unit: '몰비', color: npColor(s.np),   label2: riskLabel(s.np,  6, 16),    bar: Math.min(s.np  / 32, 1)  },
          ].map(({ key, label, val, unit, color, label2, bar }) => (
            <div key={key} style={{
              background: `${color}08`,
              border: `1px solid ${color}30`,
              borderRadius: 7, padding: '10px 10px 9px',
            }}>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.58)', fontFamily: 'Courier New', letterSpacing: 1, marginBottom: 5 }}>
                {label}
              </div>
              <div style={{ fontSize: 18, fontWeight: 900, color, fontFamily: 'Courier New', lineHeight: 1, marginBottom: 4 }}>
                {Number.isFinite(val) ? val.toFixed(1) : '—'}
              </div>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.5)', marginBottom: 6 }}>{unit}</div>
              <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.07)', overflow: 'hidden', marginBottom: 5 }}>
                <div style={{ width: `${bar * 100}%`, height: '100%', background: color, borderRadius: 2 }}/>
              </div>
              <div style={{ fontSize: 9, color, fontFamily: 'Courier New', letterSpacing: 1, fontWeight: 700 }}>
                {label2}
              </div>
            </div>
          ))}
        </div>

        {/* ④ 수온 / DO (황백화 직접 연관) */}
        <SectionLabel>수온 · 용존산소{!realSensor && ' (더미)'}</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 14 }}>
          {[
            { label: '수온',  val: `${s.temp}`, unit: '℃',    col: '#FF8A3D', hk: 'water_temp'       },
            { label: 'DO',   val: `${s.do}`,   unit: 'mg/L', col: '#00E5FF', hk: 'dissolved_oxygen' },
          ].map(({ label, val, unit, col: c, hk }) => (
            <div key={label} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              background: 'rgba(255,255,255,0.02)', borderRadius: 6, padding: '8px 12px',
              border: `1px solid ${c}14`,
            }}>
              <div>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 17, fontWeight: 700, fontFamily: 'Courier New', color: c }}>
                  {val} <span style={{ fontSize: 12, opacity: 0.55 }}>{unit}</span>
                </div>
              </div>
              <Sparkline color={c} series={histSeries(hk)} />
            </div>
          ))}
        </div>

        {/* ⑤ 일반 환경 지표 (스크롤 내려서 확인) */}
        <SectionLabel>환경 지표{!realSensor && ' (더미)'}</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 4 }}>
          {[
            { label: '염분', val: `${s.sal}`,  unit: 'PSU', col: '#8B5CF6', hk: 'salinity'  },
            { label: '탁도', val: `${s.turb}`, unit: 'NTU', col: '#FFD700', hk: 'turbidity' },
          ].map(({ label, val, unit, col: c, hk }) => (
            <div key={label} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              background: 'rgba(255,255,255,0.02)', borderRadius: 6, padding: '8px 12px',
              border: `1px solid ${c}14`,
            }}>
              <div>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 17, fontWeight: 700, fontFamily: 'Courier New', color: c }}>
                  {val} <span style={{ fontSize: 12, opacity: 0.55 }}>{unit}</span>
                </div>
              </div>
              <Sparkline color={c} series={histSeries(hk)} />
            </div>
          ))}
        </div>

        {/* 스파크라인 출처 — KOEM은 분기·반기 관측이라 '최근 며칠'처럼 보이면 오도.
            횟수 대신 기간 표기(지표별 결측으로 점 수가 다를 수 있음) + 관측소 거리 병기 */}
        {realSensor && sensorHist && (
          <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.45)', fontFamily: 'Courier New', marginBottom: 4, letterSpacing: 0.5 }}>
            그래프: {sensorHist.station} ({sensorHist.distance_km}km) 실측
            {' '}{sensorHist.series[0].date.slice(0, 7)} ~ {sensorHist.series[sensorHist.series.length - 1].date.slice(0, 7)} (정기 관측)
          </div>
        )}

        {/* 스크롤 여백 */}
        <div style={{ height: 8 }} />
      </div>

      {/* 하단 액션 버튼 (고정) */}
      <div style={{
        padding: '12px 18px 15px', flexShrink: 0,
        borderTop: '1px solid rgba(255,255,255,0.05)',
        background: 'rgb(8,15,32)',
        display: 'flex', gap: 8,
      }}>
        <button
          onClick={() => onGoXai?.()}
          onPointerDown={(e) => e.stopPropagation()}
          style={{
            flex: 1, padding: '10px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
            letterSpacing: 1.5, cursor: 'pointer', fontFamily: 'Courier New',
            background: `${col}18`, border: `1px solid ${col}50`, color: col,
            transition: 'background 0.2s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = `${col}30`; }}
          onMouseLeave={e => { e.currentTarget.style.background = `${col}18`; }}
        >
          XAI 분석 →
        </button>
        <button style={{
          flex: 1, padding: '10px 0', borderRadius: 6, fontSize: 11, fontWeight: 700,
          letterSpacing: 1.5, cursor: 'pointer', fontFamily: 'Courier New',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
          color: 'rgba(255,255,255,0.6)',
        }}>
          알림 설정
        </button>
      </div>
    </motion.div>
  );
}
