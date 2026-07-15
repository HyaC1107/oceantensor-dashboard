/**
 * FarmPicker — 실제 어장 1194개를 지역 필터 + 구역/이름 검색으로 고르는 선택기.
 *
 * 어장 등록부가 1194개라 단일 <select> 로는 못 찾는다.
 *   ① 지역(시군구) 필터  ② 구역코드(A-01)·어장명 검색  ③ 필터된 목록에서 선택
 * 어장 체계는 realFarms(SSOT) — 지도·예측팩·실측 관측소가 같은 id(gid)를 공유한다.
 */
import { useState, useMemo, useRef, useEffect } from 'react';
import { ALL_FARMS, REGION_GROUPS, farmLabel, getFarm } from '../data/realFarms';

// 어장 수 많은 지역부터
const REGIONS = Object.entries(REGION_GROUPS)
  .map(([name, ids]) => ({ name, n: ids.length }))
  .sort((a, b) => b.n - a.n);

export default function FarmPicker({ farmId, onChange, region: regionProp, onRegionChange, hideRegions }) {
  const selected = getFarm(farmId);
  // 지역: controlled(맵 툴바가 관리) / uncontrolled(탭 단독) 둘 다 지원
  const controlled = regionProp !== undefined;
  const [regionState, setRegionState] = useState(selected?.region ?? '');
  const region = controlled ? (regionProp ?? '') : regionState;
  const setRegion = controlled ? (onRegionChange ?? (() => {})) : setRegionState;
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  // 외부 클릭 시 닫기
  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const results = useMemo(() => {
    const kw = q.trim().toLowerCase();
    let list = region ? ALL_FARMS.filter(f => f.region === region) : ALL_FARMS;
    if (kw) {
      // 토큰 AND 매칭 — "고흥 a-01" 처럼 지역+구역 조합 검색 지원
      const tokens = kw.split(/\s+/).filter(Boolean);
      list = list.filter(f => {
        const hay = `${f.region} ${f.zone} ${farmLabel(f)} ${f.id}`.toLowerCase();
        return tokens.every(t => hay.includes(t));
      });
    }
    return list.slice(0, 300);            // 렌더 폭주 방지
  }, [region, q]);

  const totalInScope = region ? REGION_GROUPS[region].length : ALL_FARMS.length;

  return (
    <div ref={boxRef} style={st.wrap}>
      {/* 현재 선택 — 클릭하면 검색 패널 */}
      <button onClick={() => setOpen(o => !o)} style={st.trigger}>
        <span style={st.triggerRegion}>{selected ? (selected.zone || selected.region) : '검색'}</span>
        <span style={st.triggerName}>
          {selected ? `${selected.region} · ${farmLabel(selected)}` : '지역·구역·어장 검색'}
        </span>
        <span style={st.caret}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={st.panel}>
          {/* 지역 칩 — 단독 사용(탭) 시만. 맵에선 상단 툴바가 지역을 관리하므로 숨김 */}
          {!hideRegions ? (
            <div style={st.chipRow}>
              <button onClick={() => setRegion('')} style={{ ...st.chip, ...(region === '' ? st.chipOn : {}) }}>
                전체 <span style={st.chipN}>{ALL_FARMS.length}</span>
              </button>
              {REGIONS.map(r => (
                <button key={r.name} onClick={() => setRegion(r.name)}
                        style={{ ...st.chip, ...(region === r.name ? st.chipOn : {}) }}>
                  {r.name} <span style={st.chipN}>{r.n}</span>
                </button>
              ))}
            </div>
          ) : (
            <div style={st.scope}>
              📍 <b style={{ color: '#00E5FF' }}>{region || '전국'}</b> 내 어장 검색 · 지역 변경은 상단 툴바에서
            </div>
          )}

          {/* 검색 */}
          <input
            autoFocus
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder={hideRegions ? '어장·구역 검색 (예: A-01, 삽시도)' : '지역·구역·어장 검색 (예: 고흥 A-01)'}
            style={st.search}
          />

          <div style={st.count}>
            {results.length}개 표시
            {results.length >= 300 && ' (상위 300개 — 검색어를 좁혀주세요)'}
            <span style={{ color: 'rgba(255,255,255,0.3)' }}> / 범위 {totalInScope}개</span>
          </div>

          {/* 결과 목록 */}
          <div style={st.list}>
            {results.length === 0 && <div style={st.empty}>검색 결과 없음</div>}
            {results.map(f => (
              <button
                key={f.id}
                onClick={() => { onChange(f.id); setOpen(false); setQ(''); }}
                style={{ ...st.item, ...(f.id === farmId ? st.itemOn : {}) }}
              >
                <span style={st.itemRegion}>{f.region}</span>
                <span style={st.itemZone}>{f.zone}</span>
                <span style={st.itemName}>{farmLabel(f)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const st = {
  wrap: { position: 'relative' },
  trigger: {
    display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
    background: 'rgba(5,11,24,0.85)', border: '1px solid rgba(0,229,255,0.25)',
    borderRadius: 6, padding: '7px 12px', minWidth: 260,
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
  },
  triggerRegion: {
    fontSize: 10, fontWeight: 800, color: '#00E5FF', background: 'rgba(0,229,255,0.12)',
    border: '1px solid rgba(0,229,255,0.3)', borderRadius: 4, padding: '2px 7px', flexShrink: 0,
  },
  triggerName: { fontSize: 12.5, color: 'rgba(255,255,255,0.9)', flex: 1, textAlign: 'left', fontWeight: 600 },
  caret: { fontSize: 9, color: 'rgba(0,229,255,0.6)' },

  panel: {
    position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 1000,
    width: 380, padding: 12, borderRadius: 8,
    background: 'rgba(8,16,32,0.98)', border: '1px solid rgba(0,229,255,0.3)',
    boxShadow: '0 12px 40px rgba(0,0,0,0.6)', backdropFilter: 'blur(12px)',
  },
  chipRow: { display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 9, maxHeight: 82, overflowY: 'auto' },
  chip: {
    cursor: 'pointer', fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 5,
    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)',
    color: 'rgba(255,255,255,0.7)', whiteSpace: 'nowrap',
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
  },
  chipOn: { background: 'rgba(0,229,255,0.18)', borderColor: 'rgba(0,229,255,0.55)', color: '#00E5FF' },
  chipN: { opacity: 0.5, fontSize: 9, marginLeft: 2 },

  scope: {
    fontSize: 11, color: 'rgba(255,255,255,0.72)', margin: '2px 2px 9px', padding: '6px 9px',
    background: 'rgba(0,229,255,0.06)', border: '1px solid rgba(0,229,255,0.18)', borderRadius: 6,
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
  },

  search: {
    width: '100%', boxSizing: 'border-box', padding: '8px 11px', borderRadius: 6,
    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(0,229,255,0.25)',
    color: '#fff', fontSize: 12.5, outline: 'none',
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
  },
  count: { fontSize: 10, color: 'rgba(0,229,255,0.6)', margin: '7px 2px 5px', fontFamily: 'Courier New,monospace' },

  list: { maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 },
  item: {
    display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', textAlign: 'left',
    background: 'none', border: '1px solid transparent', borderRadius: 5, padding: '6px 8px',
    fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
  },
  itemOn: { background: 'rgba(0,229,255,0.12)', borderColor: 'rgba(0,229,255,0.35)' },
  itemRegion: {
    fontSize: 9.5, fontWeight: 700, color: 'rgba(0,229,255,0.75)', minWidth: 34, flexShrink: 0,
  },
  itemZone: {
    fontSize: 9.5, fontWeight: 800, color: '#00E5FF', background: 'rgba(0,229,255,0.1)',
    border: '1px solid rgba(0,229,255,0.25)', borderRadius: 4, padding: '1px 5px',
    fontFamily: 'Courier New,monospace', flexShrink: 0, letterSpacing: 0.5,
  },
  itemName: { fontSize: 12, color: 'rgba(255,255,255,0.82)' },
  empty: { fontSize: 11.5, color: 'rgba(255,255,255,0.35)', padding: '16px 0', textAlign: 'center' },
};
