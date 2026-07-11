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
        onsetThreshold: j.onset_threshold,
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

/** 김 양식(수확) 시즌 여부 — SSOT: channel_builder._is_harvest_season (11~5월) */
export function isHarvestSeason(date) {
  const m = Number(String(date).slice(5, 7));
  return ![6, 7, 8, 9, 10].includes(m);
}

/** stage(0~3) → 위험도 스코어(0~1). (구 방식 — 지도 색상엔 더 이상 쓰지 않음) */
export function stageToScore(stage) {
  return { 0: 0.15, 1: 0.45, 2: 0.7, 3: 0.9 }[stage] ?? null;
}

export const STAGE_LABEL = { 0: '정상', 1: '초기', 2: '경계', 3: '진행' };

/**
 * ★ 지도 색상 SSOT — onset(전이) 기반 위험 등급.
 *
 * stage(ADI 회귀헤드 파생)로 칠하면 1년 내내 ~40% 어장이 빨갛게 나온다.
 * 그 회귀헤드는 모든 평가에서 persistence에 열세였던 **모델의 약점**이기 때문이다.
 * 모델의 검증된 강점은 warn **onset**(전이 탐지, 무누수 홀드아웃 +3.3pt vs persistence)이므로,
 * "전일 대비 발생확률 급등"을 경보로 쓰고, 이미 높은 상태의 지속은 별도 등급으로 분리한다.
 */
export const RISK = {
  onset:     { color: '#FF4D4F', label: '급등 경보',    desc: '전일 대비 7일내 발생확률 급등 — AI 조기경보' },
  sustained: { color: '#FF8A3D', label: '고위험 지속',  desc: '이미 높은 위험이 유지됨 (관성 — 규칙기반으로도 포착)' },
  watch:     { color: '#FFD700', label: '주의',        desc: '발생확률 중간' },
  normal:    { color: '#00FF88', label: '정상',        desc: '발생확률 낮음' },
};

/** 어장 엔트리 → 색상 (예측 없으면 null) */
export function riskColor(entry) {
  if (!entry?.risk) return null;
  return RISK[entry.risk]?.color ?? null;
}
