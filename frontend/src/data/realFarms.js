/**
 * 실제 어장 SSOT — 지도·XAI·시뮬레이터가 **모두 같은 어장 체계**를 쓰게 한다.
 *
 * 이전에는 화면마다 어장 데이터가 갈라져 있었다:
 *   - 지도(HUD)      : kimFarmPolygons2025.json (1194개, 실제 등록 어장, gid)
 *   - XAI/시뮬레이터 : farmGeoData.js (46개 **가짜 데모 어장** — "완도 금일 1구역" 등)
 * 그래서 XAI에서 고른 어장이 지도에 없고, 이름도 서로 안 맞았다.
 *
 * 이 모듈은 **지도와 동일한 실제 어장 등록부**를 단일 소스로 제공한다.
 * id = gid (예측팩 키와 동일) → 예측/실측/지도가 한 어장을 가리킨다.
 */
import kimAllPolygons from './kimFarmPolygons2025.json';

function shortRegion(sggNm) {
  const last = String(sggNm || '').split(' ').pop();
  return last.replace(/(시|군|구)$/, '') || last;
}

/** 실제 어장 1194개 — {id(gid), name, region, lat, lon, centroid[lon,lat]} */
export const ALL_FARMS = kimAllPolygons.features
  .filter(f => f.properties?.lat && f.properties?.lon)
  .map(f => {
    const p = f.properties;
    const region = shortRegion(p.sgg_nm);
    return {
      id:       String(p.gid),
      gid:      p.gid,
      name:     p.loc || p.sgg_nm || '김양식장',
      region,
      city:     region,                    // 기존 컴포넌트 호환(farm.city)
      sido:     p.sido_nm,
      species:  p.species,
      lat:      p.lat,
      lon:      p.lon,
      centroid: [p.lon, p.lat],            // 기존 컴포넌트 호환([lon, lat])
    };
  })
  .sort((a, b) => a.region.localeCompare(b.region, 'ko') || a.name.localeCompare(b.name, 'ko'));

/** 지역(시군구) → 어장 id 목록. 드롭다운 optgroup 용. */
export const REGION_GROUPS = ALL_FARMS.reduce((acc, f) => {
  (acc[f.region] ??= []).push(f.id);
  return acc;
}, {});

/** id(gid) → 어장 */
const _byId = new Map(ALL_FARMS.map(f => [f.id, f]));
export function getFarm(id) {
  return _byId.get(String(id)) ?? null;
}

/** 같은 이름이 여러 어장에 붙는 경우가 많아(등록부 특성) 표시용 라벨에 번호를 붙인다. */
const _seen = new Map();
export const FARM_LABEL = new Map(
  ALL_FARMS.map(f => {
    const n = (_seen.get(f.name) ?? 0) + 1;
    _seen.set(f.name, n);
    const dupTotal = ALL_FARMS.filter(x => x.name === f.name).length;
    return [f.id, dupTotal > 1 ? `${f.name} #${n}` : f.name];
  })
);
export function farmLabel(f) {
  return FARM_LABEL.get(f.id) ?? f.name;
}
