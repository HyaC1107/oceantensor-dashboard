/**
 * 실데이터(Bronze) 센서 — 백엔드 /real/* 조회 + 더미 폴백
 *
 * 대시보드가 더미(farmDummy)로 채우던 어장 센서값을,
 * 네이버클라우드 oceantensor_db 의 **실측 관측**(KOEM 해양환경측정망 + KMA 강수)으로 대체한다.
 * 백엔드가 어장 좌표 최근접 관측소를 찾아 최신 관측을 반환한다.
 *
 * ⚠️ 실패(DB 미연결/관측 없음) 시 null 을 반환한다 → 호출부가 더미로 폴백해 화면이 죽지 않게 한다.
 * ⚠️ provenance(관측소·거리·관측일)를 반드시 화면에 노출할 것.
 *    영양염은 기관 QC 지연으로 최신값이 수개월 전이라, '실시간'처럼 보이면 오도가 된다.
 */
import { wbiFormula, scoreToStage } from './farmDummy';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const _cache = new Map();

async function _get(url) {
  if (_cache.has(url)) return _cache.get(url);
  try {
    const r = await fetch(`${API_BASE}${url}`);
    if (!r.ok) { _cache.set(url, null); return null; }
    const d = await r.json();
    const snap = toSnapshot(d);
    _cache.set(url, snap);
    return snap;
  } catch {
    _cache.set(url, null);
    return null;
  }
}

/** 백엔드 응답 → farmDummy 와 동일한 스냅샷 형태 { sensor_vals, wbi, stage, provenance, raw_ugl } */
function toSnapshot(d) {
  const sv = d.sensor_vals ?? {};
  // 공식에 필요한 값이 하나라도 비면 위험도 계산 불가 → 폴백시킴
  const need = ['din', 'water_temp', 'np_ratio', 'dissolved_oxygen', 'salinity'];
  if (need.some(k => sv[k] == null)) return null;

  const wbi = wbiFormula(sv);
  return {
    sensor_vals: sv,
    raw_ugl: d.raw_ugl ?? null,
    wbi: Math.round(wbi * 1000) / 1000,
    stage: scoreToStage(wbi),
    provenance: d.provenance ?? null,
    isReal: true,
  };
}

/** 어장 ID(F01~F79) 기준 실측 */
export function fetchRealSensor(farmId) {
  return _get(`/real/sensor/${farmId}`);
}

/** 임의 좌표(지도 폴리곤 gid 등) 기준 최근접 실측 */
export function fetchRealSensorByLatLon(lat, lon) {
  return _get(`/real/sensor?lat=${lat}&lon=${lon}`);
}

/**
 * 최근접 관측소 관측 이력(최근 n회) — 상세카드 스파크라인용.
 * ⚠️ KOEM 분기 관측이라 n=8 ≈ 약 2년. 화면에 관측 기간을 반드시 병기할 것.
 * 실패/이력 2회 미만이면 null → 호출부는 스파크라인을 숨긴다 (가짜 곡선 금지).
 */
export async function fetchRealSensorHistoryByLatLon(lat, lon, n = 8) {
  const url = `/real/sensor/history?lat=${lat}&lon=${lon}&n=${n}`;
  if (_cache.has(url)) return _cache.get(url);
  let out = null;
  try {
    const r = await fetch(`${API_BASE}${url}`);
    if (r.ok) {
      const d = await r.json();
      if ((d?.series?.length ?? 0) >= 2) out = d;
    }
  } catch { /* 폴백: null */ }
  _cache.set(url, out);
  return out;
}

/** 출처 한 줄 요약 — 화면 배지용 */
export function provenanceLabel(p) {
  if (!p) return '';
  return `${p.station} 관측소 · ${p.distance_km}km · ${p.observed_on} 관측`;
}
