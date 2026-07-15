import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, GeoJSON, useMap } from 'react-leaflet';
import L from 'leaflet';
import { motion, AnimatePresence, useDragControls } from 'framer-motion';
import kimAllPolygons from '../../data/kimFarmPolygons2025.json';
import { fetchRealSensorByLatLon, provenanceLabel } from '../../data/realSensor';
import 'leaflet/dist/leaflet.css';
import FarmDetailCard from './FarmDetailCard';
import FarmPicker from '../FarmPicker';
import { loadPredictions, resetPredictionsCache, RISK } from '../../data/v13Predictions';

const NO_DATA_COLOR = 'rgba(150,165,190,0.55)';   // 예측 없음/비양식기 — 중립 회색

// ── 색상 헬퍼 — onset(전이) 기반 위험등급 ─────────────────────
// score(0~1)는 강조 강도로만 쓴다. 색은 risk 등급이 결정.
const RISK_WEIGHT = { onset: 0.95, sustained: 0.7, watch: 0.45, normal: 0.15 };

// 등급별 폴리곤 스타일 — '급등'만 도드라지게, '지속'은 배경 맥락으로 낮춘다.
// (지속은 persistence로도 알 수 있는 정보라 시각적 경보 가치가 낮음. 40% 어장이 여기 해당)
const RISK_STYLE = {
  onset:     { weight: 2.6, fillOpacity: 0.38, dashArray: null },   // ★ AI가 새로 포착
  sustained: { weight: 1.0, fillOpacity: 0.10, dashArray: null },   // 이미 높음 — 은은하게
  watch:     { weight: 0.9, fillOpacity: 0.08, dashArray: null },
  normal:    { weight: 0.6, fillOpacity: 0.05, dashArray: '4 3' },
};
const NO_DATA_STYLE = { weight: 0.7, fillOpacity: 0.04, dashArray: '3 4' };

function riskStyle(risk) {
  const col = risk && RISK[risk] ? RISK[risk].color : NO_DATA_COLOR;
  const s   = (risk && RISK_STYLE[risk]) || NO_DATA_STYLE;
  return { color: col, fillColor: col, ...s };
}

function scoreColor(score, risk) {
  if (risk && RISK[risk]) return RISK[risk].color;
  if (score == null) return NO_DATA_COLOR;
  return '#00FF88';
}
function scoreSev(score, risk) {
  if (risk && RISK[risk]) return RISK[risk].label;
  return score == null ? 'NO DATA' : '정상';
}

// ── 파티클 캔버스 ─────────────────────────────────────────────
function ParticleCanvas() {
  const canvasRef = useRef(null);
  const rafRef    = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener('resize', resize);
    const N = 50;
    const pts = Array.from({ length: N }, () => ({
      x: Math.random() * canvas.width, y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.32, vy: (Math.random() - 0.5) * 0.32,
      r: Math.random() * 1.3 + 0.4, a: Math.random() * 0.4 + 0.1,
    }));
    const tick = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      pts.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = canvas.width;  if (p.x > canvas.width)  p.x = 0;
        if (p.y < 0) p.y = canvas.height; if (p.y > canvas.height) p.y = 0;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0,229,255,${p.a})`; ctx.fill();
      });
      for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < 85) {
          ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y);
          ctx.strokeStyle = `rgba(0,229,255,${0.1*(1-d/85)})`; ctx.lineWidth = 0.5; ctx.stroke();
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(rafRef.current); window.removeEventListener('resize', resize); };
  }, []);

  return <canvas ref={canvasRef} style={{
    position: 'absolute', inset: 0, width: '100%', height: '100%',
    pointerEvents: 'none', zIndex: 500,
  }} />;
}

// ── 나침반 ────────────────────────────────────────────────────
function CompassRose() {
  const dirs = ['N','NE','E','SE','S','SW','W','NW'];
  return (
    <div style={{ position: 'absolute', right: 14, bottom: 14, zIndex: 600, pointerEvents: 'none' }}>
      <svg width={60} height={60} viewBox="0 0 64 64">
        <circle cx="32" cy="32" r="30" fill="rgba(5,11,24,0.78)" stroke="rgba(0,229,255,0.2)" strokeWidth="1"/>
        {dirs.map((d, i) => {
          const a = (i/8)*Math.PI*2 - Math.PI/2, card = i%2===0;
          return (
            <g key={d}>
              <line x1={32+(card?20:23)*Math.cos(a)} y1={32+(card?20:23)*Math.sin(a)}
                    x2={32+(card?28:26)*Math.cos(a)} y2={32+(card?28:26)*Math.sin(a)}
                stroke={card?'rgba(0,229,255,0.6)':'rgba(0,229,255,0.2)'} strokeWidth={card?1.5:1}/>
              {card && <text x={32+14*Math.cos(a)} y={32+14*Math.sin(a)+3} textAnchor="middle"
                fontSize="7" fill={d==='N'?'#FF4D4F':'rgba(0,229,255,0.7)'}
                fontFamily="'Courier New',monospace" fontWeight="bold">{d}</text>}
            </g>
          );
        })}
        <circle cx="32" cy="32" r="2" fill="rgba(0,229,255,0.6)"/>
      </svg>
    </div>
  );
}

// ── 이상 마커 아이콘 ──────────────────────────────────────────
function makeAnomalyIcon(color, isSelected) {
  return L.divIcon({
    className: '',
    html: `<div class="anomaly-marker-wrap" style="--mc:${color};${isSelected ? 'transform:scale(1.5);' : ''}">
             <div class="anomaly-marker-ring1"></div>
             <div class="anomaly-marker-ring2"></div>
             <div class="anomaly-marker-core"></div>
           </div>`,
    iconSize: [36, 36], iconAnchor: [18, 18],
  });
}

// ── FlyTo 컨트롤러 (MapContainer 내부) ───────────────────────
function MapController({ selectedSite, onMapReady }) {
  const map = useMap();

  useEffect(() => { onMapReady(map); }, [map]); // eslint-disable-line

  useEffect(() => {
    if (!selectedSite) return;
    map.flyTo(
      [selectedSite.lat, selectedSite.lon], 13,
      { animate: true, duration: 0.75, easeLinearity: 0.25 }
    );
  }, [selectedSite?.id]); // eslint-disable-line

  return null;
}

// ── 스캔 링 캔버스 ────────────────────────────────────────────
function ScanRingCanvas({ selectedSite, mapRef }) {
  const canvasRef = useRef(null);
  const rafRef    = useRef(null);

  useEffect(() => {
    if (!selectedSite || !mapRef.current || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const map    = mapRef.current;
    const ctx    = canvas.getContext('2d');

    canvas.width  = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    const RINGS        = 3;
    const RING_DELAY   = 230;   // ms 간격
    const RING_DUR     = 1100;  // ms per ring
    const MAX_RADIUS   = 90;
    const startTime    = performance.now();

    const tick = (now) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // lat/lon → 캔버스 픽셀 (flyTo 중에도 정확)
      const pt = map.latLngToContainerPoint([selectedSite.lat, selectedSite.lon]);
      const cx = pt.x, cy = pt.y;

      // 확산 링 × RINGS개
      for (let i = 0; i < RINGS; i++) {
        const elapsed = now - startTime - i * RING_DELAY;
        if (elapsed <= 0) continue;
        const t     = Math.min(elapsed / RING_DUR, 1);
        const eased = 1 - Math.pow(1 - t, 2.5);
        const r     = eased * MAX_RADIUS;
        const a     = Math.pow(1 - t, 1.8) * 0.88;
        if (a < 0.01) continue;

        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0,229,255,${a})`;
        ctx.lineWidth   = 1.8 * (1 - t * 0.3);
        ctx.stroke();

        // 첫 번째 링에만 코너 틱 추가
        if (i === 0 && t < 0.65) {
          const tickA = a * 0.7;
          ctx.strokeStyle = `rgba(0,229,255,${tickA})`;
          ctx.lineWidth   = 1;
          const tickLen   = 10 * (1 - t / 0.65);
          [0, 90, 180, 270].forEach(deg => {
            const rad = (deg - 90) * Math.PI / 180;
            const ox  = Math.cos(rad), oy = Math.sin(rad);
            ctx.beginPath();
            ctx.moveTo(cx + ox * (r - tickLen), cy + oy * (r - tickLen));
            ctx.lineTo(cx + ox * (r + tickLen * 0.4), cy + oy * (r + tickLen * 0.4));
            ctx.stroke();
          });
        }
      }

      // 크로스헤어 (300ms fade-in → 1500ms 유지 → fade-out)
      const total  = now - startTime;
      const cAlpha = Math.min(total / 280, 1) * Math.max(0, 1 - (total - 1500) / 450);
      if (cAlpha > 0.01) {
        ctx.strokeStyle = `rgba(0,229,255,${cAlpha * 0.62})`;
        ctx.lineWidth   = 1;
        [[-28,0,-8,0],[8,0,28,0],[0,-28,0,-8],[0,8,0,28]].forEach(([x1,y1,x2,y2]) => {
          ctx.beginPath(); ctx.moveTo(cx+x1, cy+y1); ctx.lineTo(cx+x2, cy+y2); ctx.stroke();
        });
        ctx.beginPath();
        ctx.arc(cx, cy, 3, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0,229,255,${cAlpha})`;
        ctx.fill();
      }

      const maxTime = RING_DELAY * (RINGS - 1) + RING_DUR + 700;
      if (total < maxTime) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafRef.current);
      const c = canvasRef.current;
      if (c) c.getContext('2d').clearRect(0, 0, c.width, c.height);
    };
  }, [selectedSite?.id]); // eslint-disable-line

  return (
    <canvas ref={canvasRef} style={{
      position: 'absolute', inset: 0, width: '100%', height: '100%',
      pointerEvents: 'none', zIndex: 620,
    }} />
  );
}

// ── Lock-On HUD 오버레이 ──────────────────────────────────────
function LockOnOverlay({ isAnalyzing, selectedSite }) {
  const corners = [
    { top: 14,    left: 14,  borderTop: '2px solid rgba(0,229,255,0.7)', borderLeft:   '2px solid rgba(0,229,255,0.7)' },
    { top: 14,    right: 14, borderTop: '2px solid rgba(0,229,255,0.7)', borderRight:  '2px solid rgba(0,229,255,0.7)' },
    { bottom: 14, left: 14,  borderBottom: '2px solid rgba(0,229,255,0.7)', borderLeft:  '2px solid rgba(0,229,255,0.7)' },
    { bottom: 14, right: 14, borderBottom: '2px solid rgba(0,229,255,0.7)', borderRight: '2px solid rgba(0,229,255,0.7)' },
  ];

  return (
    <AnimatePresence>
      {isAnalyzing && selectedSite && (
        <motion.div
          key="lockon"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          style={{ position: 'absolute', inset: 0, zIndex: 700, pointerEvents: 'none' }}
        >
          {/* 코너 브라켓 */}
          {corners.map((c, i) => (
            <motion.div key={i}
              initial={{ width: 0, height: 0 }}
              animate={{ width: 20, height: 20 }}
              exit={{ width: 0, height: 0 }}
              transition={{ duration: 0.22, delay: i * 0.04 }}
              style={{ position: 'absolute', ...c }}
            />
          ))}

          {/* LOCK ON 배너 */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ delay: 0.12 }}
            style={{
              position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
              background: 'rgba(5,11,24,0.92)',
              border: '1px solid rgba(0,229,255,0.4)',
              padding: '5px 18px', borderRadius: 4,
              display: 'flex', alignItems: 'center', gap: 9,
              whiteSpace: 'nowrap',
            }}
          >
            <motion.div
              animate={{ opacity: [1, 0.1, 1] }}
              transition={{ duration: 0.5, repeat: Infinity }}
              style={{ width: 6, height: 6, borderRadius: '50%', background: '#00E5FF', boxShadow: '0 0 8px #00E5FF', flexShrink: 0 }}
            />
            <span style={{
              fontSize: 10, color: '#00E5FF',
              fontFamily: 'Courier New,monospace', letterSpacing: 3, fontWeight: 700,
            }}>
              LOCK ON · ANALYZING
            </span>
            <motion.span
              animate={{ opacity: [0, 1, 0] }}
              transition={{ duration: 0.65, repeat: Infinity }}
              style={{ color: '#00E5FF', fontFamily: 'Courier New,monospace', fontSize: 12 }}
            >▋</motion.span>
          </motion.div>

          {/* 타겟 이름 */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ delay: 0.2 }}
            style={{
              position: 'absolute', bottom: 52, left: '50%', transform: 'translateX(-50%)',
              fontSize: 8, color: 'rgba(0,229,255,0.52)',
              fontFamily: 'Courier New,monospace', letterSpacing: 3,
              background: 'rgba(5,11,24,0.75)', padding: '3px 12px',
              border: '1px solid rgba(0,229,255,0.14)',
              whiteSpace: 'nowrap',
            }}
          >
            TARGET: {selectedSite?.name}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ── 맵 위 플로팅 팜 카드 (드래그 이동 + 높이 자동 맞춤) ──────────
function FloatingFarmCard({ selectedSite, mapRef, onClose, onGoXai }) {
  const [pos, setPos] = useState(null);
  const [cardH, setCardH] = useState(540);
  const [dragged, setDragged] = useState(false);   // 사용자가 옮기면 마커 추적 중단
  const cardRef = useRef(null);
  const dragControls = useDragControls();

  useEffect(() => {
    setDragged(false);   // 어장 바뀌면 자동 배치로 리셋
    if (!selectedSite || !mapRef.current) { setPos(null); return; }

    const updatePos = () => {
      const map = mapRef.current;
      if (!map) return;
      const pt = map.latLngToContainerPoint([selectedSite.lat, selectedSite.lon]);
      setPos({ x: Math.round(pt.x), y: Math.round(pt.y) });
    };

    updatePos();
    const map = mapRef.current;
    map.on('move', updatePos);
    map.on('zoom', updatePos);

    return () => {
      map.off('move', updatePos);
      map.off('zoom', updatePos);
    };
  }, [selectedSite?.id]); // eslint-disable-line

  // 실제 렌더 높이 측정 (v7 로드 등으로 내용 길이 변해도 잘림 없이 클램프)
  useEffect(() => {
    if (!cardRef.current) return;
    const ro = new ResizeObserver(([e]) => setCardH(e.contentRect.height));
    ro.observe(cardRef.current);
    return () => ro.disconnect();
  }, [selectedSite?.id]);

  if (!pos || !selectedSite) return null;

  const CARD_W = 380;
  const mapEl  = mapRef.current?.getContainer();
  const mW     = mapEl?.offsetWidth  ?? 900;
  const mH     = mapEl?.offsetHeight ?? 600;

  const TOP_MIN = 8, MARGIN = 12;
  const maxH = mH - TOP_MIN - MARGIN;          // 카드가 맵 패널을 넘지 않도록 (내부 스크롤)
  const h = Math.min(cardH, maxH);

  // 오른쪽 우선, 공간 없으면 왼쪽으로
  const toRight = pos.x + 36 + CARD_W < mW - MARGIN;
  let left = toRight ? pos.x + 36 : pos.x - CARD_W - 36;
  left = Math.max(TOP_MIN, Math.min(left, mW - CARD_W - TOP_MIN));
  let top  = pos.y - h / 2;
  if (top < TOP_MIN)          top = TOP_MIN;
  if (top + h > mH - MARGIN)  top = mH - h - MARGIN;

  // 드래그 범위: 카드가 맵 밖으로 못 나가게 (left/top 기준 상대 오프셋)
  const dragConstraints = {
    left:  -(left - TOP_MIN),
    right:  (mW - CARD_W - TOP_MIN) - left,
    top:   -(top - TOP_MIN),
    bottom: (mH - h - MARGIN) - top,
  };

  // 연결선: 카드의 가까운 변 중앙으로 (드래그 전에만 표시)
  const lineEndX = toRight ? left : left + CARD_W;
  const lineEndY = top + h / 2;

  return (
    <>
      {/* 점선 연결선 (옮기기 전) */}
      {!dragged && (
        <svg style={{
          position: 'absolute', inset: 0, zIndex: 641,
          pointerEvents: 'none', width: '100%', height: '100%',
        }}>
          <line
            x1={pos.x} y1={pos.y} x2={lineEndX} y2={lineEndY}
            stroke="rgba(0,229,255,0.22)" strokeWidth="1" strokeDasharray="5 4"
          />
          <circle cx={pos.x} cy={pos.y} r="3.5" fill="rgba(0,229,255,0.5)" />
        </svg>
      )}

      {/* 카드 */}
      <AnimatePresence mode="wait">
        <motion.div
          key={selectedSite.id}
          ref={cardRef}
          drag
          dragListener={false}
          dragControls={dragControls}
          dragMomentum={false}
          dragElastic={0}
          dragConstraints={dragConstraints}
          onDragStart={() => setDragged(true)}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{    opacity: 0, scale: 0.9 }}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          style={{
            position: 'absolute', left, top, width: CARD_W, zIndex: 650,
            transitionProperty: dragged ? 'none' : 'left, top',
            transitionDuration: '80ms',
            transitionTimingFunction: 'linear',
          }}
        >
          <FarmDetailCard
            site={selectedSite}
            onClose={onClose}
            maxH={maxH}
            onDragHandle={(e) => dragControls.start(e)}
            onGoXai={onGoXai}
          />
        </motion.div>
      </AnimatePresence>
    </>
  );
}

// ⚠️ 구 demoScore(gid 해시 기반 가짜 점수)는 제거됨 — 이제 v13 실예측을 쓴다.
// 예측이 없는 어장은 null → '데이터 없음'(중립 회색)으로 그린다. 가짜로 채우지 않는다.
function farmEntry(preds, gid) {
  return preds?.farms?.[String(gid)] ?? null;
}
function realScore(preds, gid) {
  const e = farmEntry(preds, gid);
  if (!e?.risk) return null;
  return RISK_WEIGHT[e.risk] ?? null;
}
function farmRisk(preds, gid) {
  return farmEntry(preds, gid)?.risk ?? null;
}

// 지역 선택 칩 스타일
function regionChip(active) {
  return {
    flexShrink: 0, cursor: 'pointer', whiteSpace: 'nowrap',
    fontSize: 10.5, fontWeight: 700, padding: '3px 8px', borderRadius: 6,
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
    background: active ? 'rgba(0,229,255,0.18)' : 'rgba(255,255,255,0.05)',
    border: `1px solid ${active ? 'rgba(0,229,255,0.55)' : 'rgba(255,255,255,0.12)'}`,
    color: active ? '#00E5FF' : 'rgba(255,255,255,0.7)',
    transition: 'background .15s, border-color .15s',
  };
}

// 지역 툴바 좌우 이동 화살표 버튼 스타일
const arrowBtnStyle = {
  flexShrink: 0, cursor: 'pointer', width: 22, height: 24, borderRadius: 5, padding: 0,
  display: 'grid', placeItems: 'center', fontSize: 15, fontWeight: 800, lineHeight: 1,
  color: '#00E5FF', background: 'rgba(0,229,255,0.08)', border: '1px solid rgba(0,229,255,0.25)',
  fontFamily: 'monospace',
};

// ── 시군구 지역 그룹 (라벨 + 포커싱용) — 정적 1회 계산 ──────────
const REGIONS = (() => {
  const g = {};
  for (const f of kimAllPolygons.features) {
    const p = f.properties;
    if (!p.lat || !p.lon || !p.sgg_nm) continue;
    const key = p.sgg_nm.split(' ').pop().replace(/(시|군|구)$/, '');  // "전라남도 고흥군" → "고흥"
    if (!g[key]) g[key] = { name: key, latSum: 0, lonSum: 0, n: 0, minLat: 90, maxLat: -90, minLon: 180, maxLon: -180 };
    const r = g[key];
    r.latSum += p.lat; r.lonSum += p.lon; r.n++;
    r.minLat = Math.min(r.minLat, p.lat); r.maxLat = Math.max(r.maxLat, p.lat);
    r.minLon = Math.min(r.minLon, p.lon); r.maxLon = Math.max(r.maxLon, p.lon);
  }
  return Object.values(g)
    .filter(r => r.n >= 8)                       // 라벨/버튼 낼 만한 규모만
    .map(r => ({
      name: r.name, n: r.n,
      lat: r.latSum / r.n, lon: r.lonSum / r.n,
      bounds: [[r.minLat, r.minLon], [r.maxLat, r.maxLon]],
    }))
    .sort((a, b) => b.n - a.n);
})();

// 전 지역 bounds (검색창에서 고른 소규모 지역(n<8)도 flyTo 가능하게 — 전체 지역 포함)
//  ⚠️ 멀리 떨어진 섬 몇 개(이상치)가 min/max bounds를 부풀려 flyTo 중심이 지역과 크게 어긋난다
//     (예: 신안은 full-bounds 중심이 실제 군집에서 84km 벗어남).
//     → 10~90 백분위로 핵심 군집만 프레이밍 (n<10이면 전체 사용).
const ALL_REGION_BOUNDS = (() => {
  const g = {};
  for (const f of kimAllPolygons.features) {
    const p = f.properties;
    if (!p.lat || !p.lon || !p.sgg_nm) continue;
    const key = p.sgg_nm.split(' ').pop().replace(/(시|군|구)$/, '');
    (g[key] ??= { lats: [], lons: [] });
    g[key].lats.push(p.lat); g[key].lons.push(p.lon);
  }
  const pct = (arr, q) => {
    const a = arr.slice().sort((x, y) => x - y);
    const i = (a.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
    return a[lo] + (a[hi] - a[lo]) * (i - lo);
  };
  const out = {};
  for (const k in g) {
    const { lats, lons } = g[k];
    const q = lats.length >= 10 ? 0.1 : 0;
    out[k] = [[pct(lats, q), pct(lons, q)], [pct(lats, 1 - q), pct(lons, 1 - q)]];
  }
  return out;
})();

// ── 줌 기반 지역명 라벨 (줌아웃=희미하게 크게, 줌인하면 사라짐) ──
function RegionLabels() {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom());
    map.on('zoomend', onZoom);
    return () => { map.off('zoomend', onZoom); };
  }, [map]);

  if (zoom >= 12) return null;                    // 개별 어장 볼 땐 방해 안 되게 숨김
  const opacity  = zoom >= 10 ? 0.24 : 0.4;
  const fontSize = zoom >= 10 ? 13   : 19;

  return REGIONS.map(r => (
    <Marker
      key={r.name}
      position={[r.lat, r.lon]}
      interactive={false}
      icon={L.divIcon({
        className: 'region-label',
        iconSize: [0, 0],
        html: `<div style="transform:translate(-50%,-50%);white-space:nowrap;`
            + `font-family:'Pretendard','Noto Sans KR',sans-serif;font-weight:800;`
            + `font-size:${fontSize}px;color:rgba(220,235,255,${opacity});`
            + `text-shadow:0 1px 7px rgba(0,0,0,0.95);letter-spacing:3px;pointer-events:none;">`
            + `${r.name}</div>`,
      })}
    />
  ));
}

// ── 실측 센서 오버레이(좌상단) — 선택 어장(없으면 완도 대표) 최근접 관측소 실측값 ──
// 풍속/조류는 실측 엔드포인트에 없어, 실측 가능한 수온·염분·DIN·강수로 구성 + provenance 노출.
function RealSensorOverlay({ site }) {
  const lat = site?.lat ?? 34.31;
  const lon = site?.lon ?? 126.76;
  const [d, setD] = useState(null);
  useEffect(() => {
    let alive = true; setD(null);
    fetchRealSensorByLatLon(lat, lon).then(r => { if (alive) setD(r); });
    return () => { alive = false; };
  }, [lat, lon]);

  const sv = d?.sensor_vals ?? {};
  const fmt = (v) => (Number.isFinite(v) ? (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)) : '—');
  const fields = [
    { label: '수온', val: sv.water_temp,    unit: '℃',    col: '#FF8A3D' },
    { label: '염분', val: sv.salinity,      unit: 'PSU',  col: '#8B5CF6' },
    { label: 'DIN',  val: d?.raw_ugl?.din,  unit: 'μg/L', col: '#00E5FF' },
    { label: '강수', val: sv.precipitation, unit: 'mm',   col: '#00E5FF' },
  ];

  return (
    <div style={{
      background: 'rgba(5,11,24,0.85)', border: '1px solid rgba(0,229,255,0.22)',
      borderRadius: 6, padding: '10px 16px', backdropFilter: 'blur(12px)',
    }}>
      <div style={{ fontSize: 11, color: 'rgba(0,229,255,0.5)', letterSpacing: 1.5, marginBottom: 6, fontWeight: 700 }}>
        실측 센서 · {site?.name ?? '완도 대표'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 24px' }}>
        {fields.map(({ label, val, unit, col }) => (
          <div key={label}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)', fontWeight: 500 }}>{label}</div>
            <div style={{ fontSize: 13, fontFamily: 'Courier New', fontWeight: 700, color: col }}>
              {fmt(val)} <span style={{ fontSize: 10, opacity: 0.55 }}>{unit}</span>
            </div>
          </div>
        ))}
      </div>
      <div style={{
        fontSize: 8.5, marginTop: 7, fontFamily: 'Courier New', letterSpacing: 0.3, lineHeight: 1.4,
        color: d ? 'rgba(0,255,136,0.7)' : 'rgba(255,211,0,0.65)',
      }}>
        {d ? `● 실측 · ${provenanceLabel(d.provenance)}` : '● 실측 미연결 (최근접 관측소 없음)'}
      </div>
    </div>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
export default function MapPanel({ onSiteSelect, selectedSite, isAnalyzing, onClearSite, onGoXai }) {
  const mapRef     = useRef(null);
  const geoJsonRef = useRef(null);
  const onMapReady = useCallback(map => { mapRef.current = map; }, []);

  // 지역 선택(단일 소스) — 툴바 칩 · 검색창 지역칩이 공유.
  // 어느 쪽에서 눌러도 하이라이트(activeRegion) + flyTo가 함께 동기화된다.
  const [activeRegion, setActiveRegion] = useState(null);
  const selectRegion = useCallback((name) => {
    const map = mapRef.current;
    if (!name) { setActiveRegion(null); if (map) map.flyTo([34.6, 126.5], 9, { duration: 0.8 }); return; }
    setActiveRegion(name);
    const bounds = ALL_REGION_BOUNDS[name];
    if (map && bounds) map.flyToBounds(bounds, { padding: [70, 70], maxZoom: 12, duration: 0.9 });
  }, []);

  // v13 실예측 로드 — 지도 색상의 진짜 소스.
  // 기본은 "오늘" 기준. 오늘이 비양식기면 예측을 켜지 않는다(전부 중립).
  const [preds, setPreds] = useState(null);
  const [predsLoaded, setPredsLoaded] = useState(false);
  const [viewDate, setViewDate] = useState(null);   // null=오늘 / 값=지난 시즌 열람
  useEffect(() => {
    let alive = true;
    setPredsLoaded(false);
    resetPredictionsCache();
    loadPredictions(viewDate).then(p => {
      if (!alive) return;
      setPreds(p);
      setPredsLoaded(true);
    });
    return () => { alive = false; };
  }, [viewDate]);

  // 1194개 전체 어장 → farm 객체 배열 (score = v13 실예측, 없으면 null)
  const farms = useMemo(() => kimAllPolygons.features
    .filter(f => f.properties.lat && f.properties.lon)
    .map(f => {
      const p = f.properties;
      const score = realScore(preds, p.gid);
      const risk  = farmRisk(preds, p.gid);
      return {
        id:      String(p.gid),
        name:    p.loc || p.sgg_nm || '김양식장',
        lat:     p.lat,
        lon:     p.lon,
        species: p.species,
        sido:    p.sido_nm,
        score,
        stage:   preds?.farms[String(p.gid)]?.stage ?? null,
        outOfGrid: preds?.outOfGrid.has(String(p.gid)) ?? false,
        risk,
        severity: scoreSev(score, risk),
        polygon: f.geometry.coordinates[0].map(([lon, lat]) => [lat, lon]),
      };
    }), [preds]);

  // gid → farm 빠른 조회 (클릭 핸들러용)
  const farmMap = useMemo(
    () => Object.fromEntries(farms.map(f => [f.id, f])),
    [farms]
  );

  // 검색 피커에서 어장 선택 → 폴리곤 클릭과 동일하게 선택(→ MapController flyTo)
  const handlePick = useCallback((gid) => {
    const farm = farmMap[String(gid)];
    if (farm) onSiteSelect(farm);
  }, [farmMap, onSiteSelect]);

  // 선택된 양식장 강조 비콘(타겟 리티클) — 선택 중 계속 표시돼 어디 골랐는지 한눈에
  const selIcon = useMemo(() => L.divIcon({
    className: '',
    html: '<div class="sel-beacon"><div class="p"></div><div class="retic"></div><div class="ring"></div><div class="dot"></div></div>',
    iconSize: [46, 46], iconAnchor: [23, 23],
  }), []);

  // 지역 툴바 좌우 화살표 스크롤 (스크롤바 대신)
  const chipScrollRef = useRef(null);
  const scrollChips = useCallback((dir) => {
    chipScrollRef.current?.scrollBy({ left: dir * 160, behavior: 'smooth' });
  }, []);

  // 펄스 마커 = '급등 경보'(onset)만. AI가 새로 잡아낸 위험만 눈에 띄게 한다.
  const anomalyFarms = useMemo(() => farms.filter(f => f.risk === 'onset'), [farms]);
  const riskCount = useMemo(() => {
    const c = { onset: 0, sustained: 0, watch: 0, normal: 0 };
    farms.forEach(f => { if (f.risk) c[f.risk]++; });
    return c;
  }, [farms]);
  const hasSelection = !!selectedSite;

  // 선택/dimming 시 GeoJSON 레이어 스타일 직접 업데이트 (전체 리렌더 없이)
  useEffect(() => {
    const layer = geoJsonRef.current;
    if (!layer) return;
    layer.eachLayer(sub => {
      const p          = sub.feature.properties;
      const isSelected = selectedSite?.id === String(p.gid);
      const dimmed     = hasSelection && !isSelected;
      const score      = realScore(preds, p.gid);
      const risk       = farmRisk(preds, p.gid);
      const col        = scoreColor(score, risk);

      if (isSelected) {
        sub.setStyle({ color: '#00E5FF', weight: 4, fillColor: col, fillOpacity: 0.5, dashArray: null });
      } else if (dimmed) {
        sub.setStyle({ color: 'rgba(0,200,255,0.08)', weight: 0.5, fillColor: 'rgba(0,180,255,1)', fillOpacity: 0.02, dashArray: null });
      } else {
        sub.setStyle(riskStyle(risk));
      }
    });
  }, [selectedSite?.id, hasSelection, preds]); // eslint-disable-line

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <MapContainer
        center={[34.6, 126.5]} zoom={9}
        style={{ width: '100%', height: '100%', background: '#050B18' }}
        zoomControl={false} attributionControl={false}
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          maxZoom={18}
        />

        {/* FlyTo 컨트롤러 */}
        <MapController selectedSite={selectedSite} onMapReady={onMapReady} />

        {/* 줌 기반 지역명 라벨 */}
        <RegionLabels />

        {/* 전국 김 양식장 폴리곤 — 클릭 가능, score 반영 색상 */}
        <GeoJSON
          key={preds ? `v13-${preds.date}` : 'nodata'}   // 예측 도착 시 재렌더(스타일 재적용)
          ref={geoJsonRef}
          data={kimAllPolygons}
          style={feature => riskStyle(farmRisk(preds, feature.properties.gid))}
          onEachFeature={(feature, layer) => {
            const p     = feature.properties;
            const score = realScore(preds, p.gid);
            const risk  = farmRisk(preds, p.gid);
            const col   = scoreColor(score, risk);
            const sev   = scoreSev(score, risk);
            const entry = preds?.farms[String(p.gid)];
            const oog   = preds?.outOfGrid.has(String(p.gid));

            const detail = entry
              ? `${sev} · 7일내 발생확률 ${(entry.warn * 100).toFixed(0)}%`
                + (entry.onset != null && entry.onset >= 0.15
                    ? ` <span style="color:#FF4D4F">(전일 대비 +${(entry.onset * 100).toFixed(0)}%p 급등)</span>` : '')
                + (oog ? ' <span style="color:#FFD700">(격자밖·신뢰도↓)</span>' : '')
              : '예측 데이터 없음';

            layer.bindTooltip(
              `<span style="font-family:Courier New;font-size:11px;color:${col}">
                ${p.loc || p.sgg_nm}
                <br/><span style="color:rgba(255,255,255,0.6);font-size:10px">${detail}</span>
              </span>`,
              { sticky: true, className: 'hud-tooltip' }
            );

            layer.on('click', () => {
              const farm = farmMap[String(p.gid)];
              if (farm) onSiteSelect(farm);
            });
          }}
        />

        {/* 이상 마커 (score > 0.6 — pulse 아이콘) */}
        {anomalyFarms.map(farm => {
          const col        = scoreColor(farm.score, farm.risk);
          const isSelected = selectedSite?.id === farm.id;
          const dimmed     = hasSelection && !isSelected;
          if (dimmed) return null;
          return (
            <Marker
              key={farm.id}
              position={[farm.lat, farm.lon]}
              icon={makeAnomalyIcon(col, isSelected)}
              eventHandlers={{ click: () => onSiteSelect(farm) }}
            />
          );
        })}

        {/* 선택된 양식장 강조 비콘 — 위치에 항상 떠 있어 눈에 띔 */}
        {selectedSite && (
          <Marker
            position={[selectedSite.lat, selectedSite.lon]}
            icon={selIcon}
            interactive={false}
            zIndexOffset={2000}
          />
        )}
      </MapContainer>

      {/* 예측 기준일 · 시즌 상태 배너 */}
      {predsLoaded && (
        <div style={{
          position: 'absolute', top: 52, left: '50%', transform: 'translateX(-50%)',
          zIndex: 639, padding: '6px 14px', borderRadius: 6,
          fontSize: 11.5, fontFamily: "'Pretendard','Noto Sans KR',sans-serif", fontWeight: 600,
          background: 'rgba(5,11,24,0.9)', backdropFilter: 'blur(8px)',
          border: `1px solid ${preds?.inSeason ? 'rgba(0,229,255,0.25)' : 'rgba(150,165,190,0.4)'}`,
          color: preds?.inSeason ? 'rgba(255,255,255,0.85)' : 'rgba(200,215,235,0.95)',
          whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 10,
        }}>
          {!preds && <>⚠️ 예측 데이터를 불러오지 못했습니다</>}

          {/* 오늘이 비양식기 → 예측 비활성 */}
          {preds && !preds.inSeason && preds.isToday && (
            <>
              <span>🚫 <b>비양식기</b> ({preds.date}) — 김 양식 기간이 아니라 위험 예측을 표시하지 않습니다</span>
              {preds.lastSeasonDate && (
                <button
                  onClick={() => setViewDate(preds.lastSeasonDate)}
                  style={{
                    background: 'rgba(0,229,255,0.12)', border: '1px solid rgba(0,229,255,0.4)',
                    color: '#00E5FF', borderRadius: 5, padding: '3px 9px',
                    fontSize: 10.5, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                  }}>
                  지난 시즌 보기 →
                </button>
              )}
            </>
          )}

          {/* 지난 시즌 열람 모드 */}
          {preds?.inSeason && preds.isArchive && (
            <>
              <span>📅 <b>지난 시즌 열람</b> — <b style={{ color: '#00E5FF' }}>{preds.date}</b> 기준 (현재는 비양식기)</span>
              <button
                onClick={() => setViewDate(null)}
                style={{
                  background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.2)',
                  color: 'rgba(255,255,255,0.7)', borderRadius: 5, padding: '3px 9px',
                  fontSize: 10.5, fontWeight: 700, cursor: 'pointer',
                }}>
                오늘로 ↩
              </button>
            </>
          )}

          {/* 오늘이 양식기 */}
          {preds?.inSeason && !preds.isArchive && (
            <span>예측 기준일 <b style={{ color: '#00E5FF' }}>{preds.date}</b> · 김 양식기(11~5월)</span>
          )}
        </div>
      )}

      {/* 상단: 어장·구역 검색(왼) + 지역 포커싱 툴바(오) — 역할 분리, 지역칩은 툴바에만 */}
      <div style={{
        position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)',
        zIndex: 640, display: 'flex', gap: 8, alignItems: 'flex-start', maxWidth: '94%',
      }}>
        {/* 어장·구역 검색 (지역은 툴바가 관리 → hideRegions, 툴바 선택 지역으로 필터) */}
        <FarmPicker
          farmId={selectedSite?.id}
          onChange={handlePick}
          region={activeRegion || ''}
          hideRegions
        />

        {/* 지역 툴바 — 스크롤바 대신 좌우 화살표로 이동. 클릭 시 하이라이트 + flyTo + 검색창 필터 동기화 */}
        <div style={{
          display: 'flex', gap: 4, alignItems: 'center', padding: '6px 8px',
          background: 'rgba(5,11,24,0.85)', border: '1px solid rgba(0,229,255,0.2)',
          borderRadius: 9, backdropFilter: 'blur(10px)',
        }}>
          <span style={{ fontSize: 9, color: 'rgba(0,229,255,0.55)', fontFamily: 'Courier New', letterSpacing: 1, flexShrink: 0, paddingLeft: 2 }}>
            지역
          </span>
          <button onClick={() => scrollChips(-1)} aria-label="지역 왼쪽 이동" style={arrowBtnStyle}>‹</button>
          <div ref={chipScrollRef} style={{
            display: 'flex', gap: 5, alignItems: 'center', overflow: 'hidden',
            maxWidth: 'min(38vw, 330px)', scrollBehavior: 'smooth',
          }}>
            <button onClick={() => selectRegion('')} style={regionChip(activeRegion === null)}>전체</button>
            {REGIONS.map(r => (
              <button key={r.name} onClick={() => selectRegion(r.name)} style={regionChip(activeRegion === r.name)}>
                {r.name}
                <span style={{ opacity: 0.5, marginLeft: 4, fontSize: 9 }}>{r.n}</span>
              </button>
            ))}
          </div>
          <button onClick={() => scrollChips(1)} aria-label="지역 오른쪽 이동" style={arrowBtnStyle}>›</button>
        </div>
      </div>

      {/* 파티클 레이어 */}
      <ParticleCanvas />

      {/* 스캔 링 캔버스 */}
      <ScanRingCanvas selectedSite={selectedSite} mapRef={mapRef} />

      {/* 나침반 */}
      <CompassRose />

      {/* Lock-On HUD */}
      <LockOnOverlay isAnalyzing={isAnalyzing} selectedSite={selectedSite} />

      {/* 맵 위 플로팅 팜 카드 */}
      <FloatingFarmCard selectedSite={selectedSite} mapRef={mapRef} onClose={onClearSite} onGoXai={onGoXai} />

      {/* 센서 오버레이 — 상단 검색/툴바 아래로 내려 겹치지 않게 */}
      <div style={{
        position: 'absolute', left: 12, top: 62, zIndex: 600, pointerEvents: 'none',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}>
        <RealSensorOverlay site={selectedSite} />

        {/* 위험 등급 범례 — onset(전이) 기반 */}
        <div style={{
          background: 'rgba(5,11,24,0.82)', border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 5, padding: '8px 12px', backdropFilter: 'blur(8px)',
        }}>
          <div style={{ fontSize: 9, color: 'rgba(0,229,255,0.6)', fontFamily: 'Courier New', letterSpacing: 1, marginBottom: 6 }}>
            위험 등급 (전일 대비 전이 기준)
          </div>
          {['onset', 'sustained', 'watch', 'normal'].map(k => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: RISK[k].color, boxShadow: `0 0 5px ${RISK[k].color}`, flexShrink: 0 }}/>
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.75)', fontWeight: 700, minWidth: 62 }}>{RISK[k].label}</span>
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', fontFamily: 'Courier New' }}>{riskCount[k]}</span>
            </div>
          ))}
          <div style={{ fontSize: 8.5, color: 'rgba(255,255,255,0.38)', marginTop: 5, lineHeight: 1.4, maxWidth: 190 }}>
            🔴 급등 = AI가 새로 포착한 위험 전이<br/>
            🟠 지속 = 이미 높은 상태(관성)
          </div>
        </div>

        <div style={{
          background: 'rgba(5,11,24,0.75)', border: '1px solid rgba(0,229,255,0.12)',
          borderRadius: 5, padding: '6px 12px', backdropFilter: 'blur(8px)',
        }}>
          <span style={{ fontSize: 11, color: 'rgba(0,229,255,0.5)', fontFamily: 'Courier New', letterSpacing: 1.5, fontWeight: 600 }}>
            모니터링 {farms.length} · 전국 김양식장 {kimAllPolygons.features.length}
          </span>
        </div>
      </div>

      {/* 스캔라인 */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 510, pointerEvents: 'none',
        background: 'repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,0.01) 3px,rgba(0,229,255,0.01) 4px)',
      }} />

      {/* 경보 테두리 */}
      <motion.div
        style={{ position: 'absolute', inset: 0, zIndex: 520, pointerEvents: 'none', border: '2px solid #FF4D4F' }}
        animate={{ opacity: [0.1, 0.38, 0.1] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  );
}
