/**
 * v13 실예측 로더 — 지도 폴리곤(gid) 색상의 진짜 소스.
 *
 * 이전에는 MapPanel 의 `demoScore(gid)` 라는 **해시 기반 가짜 점수**로 1194개 폴리곤을
 * 색칠하고 있었다. 이 모듈은 그걸 백엔드의 **실제 v13 예측**으로 대체한다.
 *
 * 백엔드: GET /predict/v7?date=YYYY-MM-DD
 *   → { date, model, farms: { <gid>: { stage, stage_label, adi7, warn, severe } }, out_of_grid_farms }
 *
 * ⚠️ 격자 밖(out_of_grid) 어장은 모델 격자(lat 34.0~36.8 / lon 125.3~128.0) 경계 픽셀로
 *    클램프된 값이라 신뢰도가 낮다 → 별도 표시하고 위험도로 쓰지 않는다.
 * ⚠️ 예측을 못 받으면 폴리곤은 '데이터 없음'(중립 회색)으로 그린다. 가짜 점수로 되돌리지 않는다.
 */
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

let _cache = null;      // { date, farms, outOfGrid:Set }
let _inflight = null;

/** 팩 메타(서빙 가능한 최신 날짜) 조회 */
async function fetchMeta() {
  const r = await fetch(`${API_BASE}/predict/v7-meta`);
  if (!r.ok) throw new Error('meta 없음');
  return r.json();
}

/**
 * 특정 날짜(미지정 시 팩의 최신일)의 전체 어장 예측을 로드.
 * @returns {Promise<{date:string, farms:Object, outOfGrid:Set}|null>}
 */
export async function loadPredictions(date) {
  if (_cache && (!date || _cache.date === date)) return _cache;
  if (_inflight) return _inflight;

  _inflight = (async () => {
    try {
      const season = await fetch(`${API_BASE}/predict/v7-season`).then(r => (r.ok ? r.json() : null));

      // ★ 날짜 미지정 = "지금" 을 보여주는 상태.
      //   오늘이 비양식기면 예측을 아예 켜지 않는다(지도 전체 비활성).
      //   지난 시즌 데이터를 보려면 date 를 명시적으로 넘겨야 한다(archive 모드).
      if (!date) {
        if (season && season.today_in_season === false) {
          _cache = {
            date: season.today,
            inSeason: false,
            isToday: true,
            seasonNote: season.today_note,
            lastSeasonDate: season.latest_in_season_date,
            farms: {},                       // 예측 없음 → 지도 전부 중립
            outOfGrid: new Set(),
          };
          return _cache;
        }
      }

      const d = date || season?.latest_in_season_date;
      const r = await fetch(`${API_BASE}/predict/v7?date=${d}`);
      if (!r.ok) throw new Error(`predict/v7 ${r.status}`);
      const j = await r.json();
      _cache = {
        date: j.date,
        inSeason: j.in_season !== false,
        isToday: !date,
        isArchive: Boolean(date),            // 지난 시즌 열람 모드
        seasonNote: j.season_note ?? null,
        riskCounts: j.risk_counts ?? {},
        // onsetThreshold 제거(2026-07-17) — Δwarn 판정 폐기로 백엔드가 항상 null을 준다.
        riskThresholds: j.risk_thresholds ?? null,   // 등급 임계 SSOT(백엔드 v7.py) — 범례 표시에 사용
        farms: j.farms ?? {},
        outOfGrid: new Set(j.out_of_grid_farms ?? []),
      };
      return _cache;
    } catch {
      return null;                          // 폴백은 '데이터 없음' — 가짜 점수 금지
    } finally {
      _inflight = null;
    }
  })();
  return _inflight;
}

/** 캐시 무효화 (날짜 전환 시) */
export function resetPredictionsCache() { _cache = null; }

/** 시퀀스 코드(문자) → risk 등급. 백엔드 /predict/v7-sequence 와 계약.
 *  '3'(구 onset)은 2026-07-17 판정 폐기로 더 이상 생성되지 않는다. 다만 구버전 캐시 응답이
 *  섞여 들어와도 색이 사라지지 않도록 최고 등급(sustained)으로 흡수한다. */
export const SEQ_CODE_RISK = { '3': 'sustained', '2': 'sustained', '1': 'watch', '0': 'normal', '.': null };

let _seqCache = null;
/**
 * 양식기(11~5월) **일단위 위험등급 시퀀스** — 타임랩스 자동재생용.
 * fetch 1회로 시즌 전체를 받아 캐시한다(≈0.5MB). 재생 중엔 이 캐시에서 프레임을 읽어
 * 네트워크 없이 폴리곤 색만 갈아끼운다.
 * @returns {Promise<{dates:string[], codes:Object<string,string>}|null>}
 *   codes[gid] = 날짜순 등급 문자열 (각 문자 = SEQ_CODE_RISK 키).
 */
export async function fetchSequence() {
  if (_seqCache) return _seqCache;
  try {
    const r = await fetch(`${API_BASE}/predict/v7-sequence`);
    if (!r.ok) throw new Error(`v7-sequence ${r.status}`);
    const j = await r.json();
    if (!Array.isArray(j.dates) || !j.codes) return null;
    _seqCache = { dates: j.dates, codes: j.codes };
    return _seqCache;
  } catch { return null; }
}

/**
 * 예측팩 범위(meta.date_range) 내 **김 양식기(11~5월)** 월 목록 — 연도+월 타임라인용.
 * 비수기(6~10월)는 제외. 각 월의 대표일(15일)을 date 로 준다.
 * @returns {Promise<Array<{key,year,month,label,date}>>}
 */
export async function fetchSeasonMonths() {
  try {
    const meta = await fetchMeta();
    const [s, e] = meta.date_range || [];
    if (!s || !e) return [];
    const months = [];
    let y = Number(s.slice(0, 4)), m = Number(s.slice(5, 7));
    const ey = Number(e.slice(0, 4)), em = Number(e.slice(5, 7));
    while (y < ey || (y === ey && m <= em)) {
      if ([11, 12, 1, 2, 3, 4, 5].includes(m)) {
        const key = `${y}-${String(m).padStart(2, '0')}`;
        months.push({ key, year: y, month: m, label: `${y}.${String(m).padStart(2, '0')}`, date: `${key}-15` });
      }
      m++; if (m > 12) { m = 1; y++; }
    }
    return months;
  } catch { return []; }
}

/** 김 양식(수확) 시즌 여부 — SSOT: channel_builder._is_harvest_season (11~5월) */
export function isHarvestSeason(date) {
  const m = Number(String(date).slice(5, 7));
  return ![6, 7, 8, 9, 10].includes(m);
}

/** stage(0~3) → 위험도 스코어(0~1). (구 방식 — 지도 색상엔 더 이상 쓰지 않음) */
export function stageToScore(stage) {
  return { 0: 0.15, 1: 0.45, 2: 0.7, 3: 0.9 }[stage] ?? null;
}

export const STAGE_LABEL = { 0: '정상', 1: '초기', 2: '경계', 3: '심각' };

/**
 * ★ 지도 색상 SSOT — warn(7일내 발생확률) **절대값** 기반. 백엔드 `v7.py:_risk_class`와 계약.
 *
 * 🔴 2026-07-17: Δwarn(전일 대비 급등) 기반 `onset` 등급을 **제거**했다.
 *   실측(analysis/onset_eval6_delta.py, 안 본 25-26시즌 1.3억 픽셀):
 *   Δwarn 의 onset 예측 AUC = 0.3852(warn)/0.4696(severe) → **무작위(0.5)보다 나쁨**.
 *   같은 표본에서 warn 절대값은 AUC 0.9772/0.9877 로 유효 → 절대값 기준으로 전환.
 *   (기존에 Δwarn을 쓴 근거였던 "+3.3pt"는 사실 **warn 절대값**의 성적이었다. 논리 비약이었음.)
 *
 * ⚠️ 남은 한계: 모델 출력이 이진 포화(median 0 / p75 0.989)라 상시 ~29%가 '고위험'으로 표시된다.
 *   임계값으로 조정 불가(0.5→0.96 올려도 29%→26%) — 재학습(focal_gamma) 영역.
 */
export const RISK = {
  // onset: 2026-07-17 제거. 백엔드가 더 이상 이 값을 반환하지 않는다. (아래 normalizeRisk가 흡수)
  // desc에 임계 수치를 박지 않는다 — 수치 SSOT는 백엔드 risk_thresholds(범례가 그걸 받아 표시)
  sustained: { color: '#FF4D4F', label: '고위험',  desc: '7일내 발생확률 높음' },
  watch:     { color: '#FFD700', label: '주의',    desc: '발생확률 중간' },
  normal:    { color: '#00FF88', label: '정상',    desc: '발생확률 낮음' },
};

/**
 * 구버전 등급명 흡수. 구 HTTP 캐시가 `risk:"onset"`을 뱉을 수 있는데, 그대로 두면
 * RISK에 키가 없어 **회색('예측 없음')으로 그려진다 — 위험이 안전해 보이는 잘못된 fail-safe**.
 * 구 onset은 경보 등급이었으므로 최고 등급으로 올려서 흡수한다(시퀀스 SEQ_CODE_RISK와 동일 정책).
 */
export function normalizeRisk(risk) {
  if (!risk) return null;
  if (RISK[risk]) return risk;
  return 'sustained';   // 미지 등급(구 onset 등) → 안전한 쪽(경보)으로
}

/** 어장 엔트리 → 색상 (예측 없으면 null) */
export function riskColor(entry) {
  const r = normalizeRisk(entry?.risk);
  return r ? RISK[r].color : null;
}
