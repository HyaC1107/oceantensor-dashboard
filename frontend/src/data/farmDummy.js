/**
 * 어장별 결정론적 더미 스냅샷
 *
 * 각 양식장 id 를 seed 로 안정적인(클릭마다 동일) 센서값을 생성한다.
 * WBI 공식은 백엔드 app/routers/predict.py 의 _wbi_formula 와 동일하게 미러링 →
 * 지도 폴리곤 색(프론트 계산)과 /predict 응답(백엔드 계산)이 일치한다.
 *
 * 용도:
 *   - 지도 폴리곤 색상 (모든 어장)
 *   - InfoPanel WBI/센서/7일예측 (모든 어장)
 *   - /predict, /explain/llm 요청 body 의 sensor_vals (일관성)
 */

// 문자열 → 32bit 정수 해시
function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// seed 기반 결정론적 난수 (mulberry32)
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const r2 = (v) => Math.round(v * 100) / 100;
const r3 = (v) => Math.round(v * 1000) / 1000;

// 백엔드 _wbi_formula 미러
export function wbiFormula({ din, water_temp, np_ratio, dissolved_oxygen, salinity }) {
  const dinRisk  = Math.max(0, 1 - din / 5);
  const tempRisk = Math.max(0, (water_temp - 20) / 10);
  const npRisk   = Math.max(0, 1 - np_ratio / 10);
  const doRisk   = Math.max(0, 1 - dissolved_oxygen / 5);
  const salRisk  = Math.max(0, (32 - salinity) / 4);
  const wbi = 0.38 * dinRisk + 0.27 * tempRisk + 0.19 * npRisk
            + 0.10 * doRisk + 0.06 * salRisk;
  return Math.min(1, Math.max(0, wbi));
}

export function scoreToStage(s) {
  if (s < 0.2) return 0;
  if (s < 0.4) return 1;
  if (s < 0.6) return 2;
  if (s < 0.8) return 3;
  return 4;
}

const _cache = new Map();

/**
 * @param {{id:string}} farm
 * @returns {{ sensor_vals:object, wbi:number, stage:number }}
 */
export function farmDummy(farm) {
  if (_cache.has(farm.id)) return _cache.get(farm.id);

  const rng = mulberry32(hashStr(farm.id));
  const rand = (min, max) => min + rng() * (max - min);

  const water_temp        = r2(rand(18.0, 29.0));
  const dissolved_oxygen  = r2(rand(4.5, 10.0));
  const din               = r2(rand(1.0, 12.0));
  const dip               = r3(rand(0.15, 1.0));
  const salinity          = r2(rand(29.0, 34.0));
  const precipitation     = r2(rand(0, 20.0));
  const chlorophyll_a     = r2(rand(1.0, 8.0));
  const np_ratio          = dip > 0 ? r2(din / dip) : 0;

  const sensor_vals = {
    water_temp, dissolved_oxygen, din, dip,
    salinity, precipitation, chlorophyll_a, np_ratio,
  };
  const wbi = r3(wbiFormula(sensor_vals));
  const snap = { sensor_vals, wbi, stage: scoreToStage(wbi) };
  _cache.set(farm.id, snap);
  return snap;
}

// 지도 폴리곤 색상용 — wbi 만 빠르게
export function farmWbi(farm) {
  return farmDummy(farm).wbi;
}
