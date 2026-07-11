/**
 * XaiHeatmapOverlay — 김 엽체 위 황백화 Attention 히트맵 오버레이 (XAI)
 *
 * 비전 모델(엽체 이미지 → 황백화 영역) 학습 전까지의 **데모 시각화**.
 *  - 합성 김 엽체(blade)를 Canvas로 그리고, WBI 심각도에 비례해
 *    황백화(노랑→흰색) 의심 영역을 가우시안 블롭으로 오버레이.
 *  - farm.id seed → 어장마다 안정적(클릭마다 동일) 패턴.
 *  - imageSrc 를 주면 합성 엽체 대신 실제 현미경/엽체 사진 위에 오버레이.
 *
 * 실제 비전 모델 도입 시: 블롭 생성부를 모델의 spatial attention map으로 교체.
 */
import { useRef, useEffect, useState, useMemo } from 'react';

// 결정론적 seed (farmDummy 와 동일 방식)
function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const W = 280, H = 156;
const BLADES = [
  { x: 56,  w: 30 },
  { x: 112, w: 34 },
  { x: 170, w: 30 },
  { x: 222, w: 28 },
];
const TOP = 16, BOT = 142;  // 엽체 세로 범위

function severityLabel(wbi) {
  if (wbi < 0.3)  return { t: '정상', c: '#22c55e' };
  if (wbi < 0.6)  return { t: '주의', c: '#f59e0b' };
  if (wbi < 0.8)  return { t: '경고', c: '#f97316' };
  return            { t: '위험', c: '#ef4444' };
}

export default function XaiHeatmapOverlay({ farm, snapshot, imageSrc }) {
  const canvasRef = useRef(null);
  const [showHeat, setShowHeat] = useState(true);
  const wbi = snapshot?.wbi ?? 0;
  const sev = severityLabel(wbi);

  // 어장+심각도 기반 블롭 생성 (결정론적)
  const blobs = useMemo(() => {
    if (!farm) return [];
    const rng = mulberry32(hashStr(farm.id + '|heat'));
    const n = Math.round(wbi * 9);              // 0~9개
    const out = [];
    for (let i = 0; i < n; i++) {
      const blade = BLADES[Math.floor(rng() * BLADES.length)];
      out.push({
        x: blade.x + (rng() - 0.5) * blade.w * 0.9,
        y: TOP + rng() * (BOT - TOP),
        r: 14 + rng() * 16,
        a: 0.30 + wbi * 0.55 * (0.6 + rng() * 0.4),  // 알파 ∝ 심각도
      });
    }
    return out;
  }, [farm, wbi]);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr;
    const ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    // 배경(해수)
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#06141f'); bg.addColorStop(1, '#0a1c2b');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

    const drawScene = () => {
      // 히트맵 (엽체 위에 가산 합성)
      if (showHeat && blobs.length) {
        ctx.globalCompositeOperation = 'lighter';
        for (const b of blobs) {
          const g = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r);
          // 황백화: 안쪽 흰빛 → 노랑 → 투명
          g.addColorStop(0,   `rgba(254,252,232,${b.a})`);
          g.addColorStop(0.4, `rgba(250,204,21,${b.a * 0.7})`);
          g.addColorStop(1,   'rgba(250,204,21,0)');
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalCompositeOperation = 'source-over';
      }
      // 외곽선
      ctx.strokeStyle = 'rgba(30,58,95,0.9)'; ctx.lineWidth = 1;
      ctx.strokeRect(0.5, 0.5, W - 1, H - 1);
    };

    if (imageSrc) {
      const img = new Image();
      img.onload = () => {
        // cover 맞춤
        const r = Math.max(W / img.width, H / img.height);
        const iw = img.width * r, ih = img.height * r;
        ctx.drawImage(img, (W - iw) / 2, (H - ih) / 2, iw, ih);
        drawScene();
      };
      img.onerror = () => { drawBlades(ctx); drawScene(); };
      img.src = imageSrc;
    } else {
      drawBlades(ctx);
      drawScene();
    }
  }, [farm, wbi, showHeat, imageSrc, blobs]);

  return (
    <div>
      <div style={st.head}>
        <span style={{ ...st.sevDot, background: sev.c }} />
        <span style={st.sevText}>
          엽체 황백화 분포 · <b style={{ color: sev.c }}>{sev.t}</b>
          <span style={st.count}> ({blobs.length}개 의심영역)</span>
        </span>
        <button style={st.toggle} onClick={() => setShowHeat(v => !v)}>
          {showHeat ? '원본' : '히트맵'}
        </button>
      </div>

      <canvas ref={canvasRef}
        style={{ width: W, height: H, borderRadius: 8, display: 'block', maxWidth: '100%' }} />

      {/* 컬러바 범례 */}
      <div style={st.legendRow}>
        <span style={st.legLabel}>정상</span>
        <div style={st.legBar} />
        <span style={st.legLabel}>황백화</span>
      </div>
      <div style={st.note}>
        ※ 비전모델 학습 전 데모 — WBI {(wbi * 100).toFixed(0)}% 기반 합성 attention.
        실제 엽체 영상 도입 시 모델 spatial attention으로 교체.
      </div>
    </div>
  );
}

// 합성 김 엽체(blade) 그리기
function drawBlades(ctx) {
  for (const b of BLADES) {
    const g = ctx.createLinearGradient(0, TOP, 0, BOT);
    g.addColorStop(0,   '#14532d');
    g.addColorStop(0.5, '#166534');
    g.addColorStop(1,   '#3f2d12');   // 끝부분 갈변
    ctx.fillStyle = g;
    ctx.beginPath();
    const cx = b.x, hw = b.w / 2;
    ctx.moveTo(cx, TOP);
    ctx.bezierCurveTo(cx + hw, TOP + 18, cx + hw * 0.7, BOT - 24, cx, BOT);
    ctx.bezierCurveTo(cx - hw * 0.7, BOT - 24, cx - hw, TOP + 18, cx, TOP);
    ctx.fill();
    // 중심맥
    ctx.strokeStyle = 'rgba(20,83,45,0.6)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, TOP + 6); ctx.lineTo(cx, BOT - 6); ctx.stroke();
  }
}

const st = {
  head:    { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 },
  sevDot:  { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  sevText: { color: '#cbd5e1', fontSize: 11, flex: 1 },
  count:   { color: '#64748b', fontSize: 10 },
  toggle:  { background: '#0f172a', border: '1px solid #1e3a5f', color: '#93c5fd',
             borderRadius: 6, padding: '2px 9px', cursor: 'pointer', fontSize: 10 },
  legendRow: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 },
  legLabel:  { color: '#64748b', fontSize: 9 },
  legBar:    { flex: 1, height: 8, borderRadius: 4,
               background: 'linear-gradient(90deg, #14532d 0%, #166534 35%, #facc15 75%, #fefce8 100%)' },
  note:    { color: '#475569', fontSize: 9, lineHeight: 1.5, marginTop: 6 },
};
