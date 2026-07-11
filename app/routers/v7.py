"""v7/v13 STMMT 사전 계산 예측 서빙 — 날짜별 어장 예측 반환.

- v13 팩(app/data/v13_predictions.json)이 있으면 우선 서빙:
  어장별 {adi7(회귀 7일궤적 0~10), warn=P(7일 max ADI>=5), severe=P(>=8), stage}
- 없으면 구 v7 팩(v7_predictions.json, stage int만) 폴백.
- 응답 스키마는 구버전 필드(stage/stage_label)를 항상 포함 → 프론트 하위호환.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

DATA_DIR = Path(__file__).parents[1] / "data"
# 전체 어장 팩(gid 키, 1194개 — 지도 폴리곤과 직접 매칭)이 주(主).
# 79어장 팩(F01~F79 키)은 키 공간이 달라 함께 병합해 서빙한다(하위호환).
PACK_ALL = DATA_DIR / "v13_predictions_all.json"   # gid  키
PACK_79  = DATA_DIR / "v13_predictions.json"       # Fxx  키
PACK_V7  = DATA_DIR / "v7_predictions.json"        # 구 폴백
STAGE_LABELS = {0: "정상", 1: "초기", 2: "경계", 3: "진행"}

# ── 김 양식(수확) 시즌 — SSOT: ml/data/channel_builder.py `_is_harvest_season`
#    "수확기 여부. 11~5월=True, 6~10월=False(IGNORE)."
#    6~10월은 학습 시 라벨이 IGNORE(-1)로 마스킹됐다 → 그 구간 예측은 무의미한 외삽이므로
#    서빙 시 '비양식기'로 비활성화한다(빨갛게 칠하지 않는다).
OFF_SEASON_MONTHS = {6, 7, 8, 9, 10}


def _in_season(date: str) -> bool:
    try:
        return int(date[5:7]) not in OFF_SEASON_MONTHS
    except (ValueError, IndexError):
        return True


@lru_cache(maxsize=1)
def _load() -> tuple[str, dict]:
    """전체 팩 + 79어장 팩을 날짜별로 병합. 키 공간(gid vs Fxx)이 달라 충돌 없음."""
    packs = []
    for path in (PACK_ALL, PACK_79):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                packs.append(json.load(f))
    if not packs:
        if PACK_V7.exists():
            with open(PACK_V7, encoding="utf-8") as f:
                return "stmmt-v7", json.load(f)
        return "", {}

    base = packs[0]
    if len(packs) > 1:
        merged_preds = base.get("predictions", {})
        for extra in packs[1:]:
            for date, day in extra.get("predictions", {}).items():
                merged_preds.setdefault(date, {}).update(day)
        base["predictions"] = merged_preds
        # 격자 밖 목록도 합침
        oog = set(base["meta"].get("out_of_grid_farms", []))
        for extra in packs[1:]:
            oog |= set(extra.get("meta", {}).get("out_of_grid_farms", []))
        base["meta"]["out_of_grid_farms"] = sorted(oog)
        base["meta"]["n_farms"] = len(next(iter(base["predictions"].values()), {}))
    return "stmmt-v13", base


# ── 위험 등급: onset(전이) 기반 ────────────────────────────────────────────
# 왜 stage(ADI 회귀헤드 파생)를 안 쓰나:
#   회귀헤드는 v12·v13·v14 전 평가에서 persistence에 열세였고, 그걸로 칠하면
#   1년 내내 ~40% 어장이 "진행"으로 빨갛게 나온다(실제 사건은 11~1월 집중).
# 모델의 검증된 강점은 **warn onset**(전이 탐지, 무누수 홀드아웃 +3.3pt vs persistence)이다.
#   → "전일 대비 발생확률 급등(Δwarn)"을 경보로 쓰고,
#     이미 높은 상태의 지속은 persistence 영역이라 별도 등급으로 분리한다.
ONSET_TH     = 0.15   # Δwarn ≥ 0.15 → 급등 경보 (실측 분포상 상위 ~1%, 하루 평균 12개 어장)
SUSTAINED_TH = 0.50   # warn ≥ 0.5 이면서 급등은 아님 → 고위험 지속(관성)
WATCH_TH     = 0.20   # 주의

RISK_LABELS = {
    "onset":     "급등 경보",
    "sustained": "고위험 지속",
    "watch":     "주의",
    "normal":    "정상",
}


def _risk_class(warn: float, onset: Optional[float]) -> str:
    if onset is not None and onset >= ONSET_TH:
        return "onset"                     # ★ AI의 검증된 강점 — 새 위험의 시작
    if warn >= SUSTAINED_TH:
        return "sustained"                 # 이미 높음 (persistence로도 알 수 있는 정보)
    if warn >= WATCH_TH:
        return "watch"
    return "normal"


def _farm_entry(raw, prev=None) -> dict:
    """구 팩(int stage) / 신 팩(dict) → 공통 스키마 + onset 위험등급."""
    if not isinstance(raw, dict):
        return {"stage": raw, "stage_label": STAGE_LABELS.get(raw, "??")}

    entry = {"stage": raw["stage"], "stage_label": STAGE_LABELS.get(raw["stage"], "??")}
    for k in ("adi7", "warn", "severe"):
        if k in raw:
            entry[k] = raw[k]

    warn = float(raw.get("warn", 0.0))
    onset = None
    if isinstance(prev, dict) and "warn" in prev:
        onset = round(warn - float(prev["warn"]), 4)

    entry["warn_prev"] = None if not isinstance(prev, dict) else prev.get("warn")
    entry["onset"] = onset
    entry["risk"] = _risk_class(warn, onset)
    entry["risk_label"] = RISK_LABELS[entry["risk"]]
    return entry


def _prev_date(preds: dict, date: str) -> Optional[str]:
    """직전 관측일. 시즌 공백(6~10월)을 건너뛴 경우는 onset 계산이 무의미하므로 제외."""
    from datetime import date as _d, timedelta
    try:
        y, m, dd = (int(x) for x in date.split("-"))
        cand = _d(y, m, dd) - timedelta(days=1)
    except Exception:
        return None
    for _ in range(3):                       # 최대 3일 전까지만 허용 (긴 공백은 onset 무효)
        s = cand.isoformat()
        if s in preds:
            return s
        cand -= timedelta(days=1)
    return None


@router.get("/v7")
def get_v7_by_date(date: str = Query(..., description="YYYY-MM-DD")):
    """특정 날짜 전체 어장 예측 반환."""
    model_name, data = _load()
    if not data:
        raise HTTPException(503, "사전 계산 예측 데이터 없음")
    preds = data.get("predictions", {})
    if date not in preds:
        available = sorted(preds.keys())
        raise HTTPException(
            404,
            f"날짜 없음: {date}. 범위: {available[0]} ~ {available[-1]}",
        )
    day = preds[date]
    in_season = _in_season(date)
    pdate = _prev_date(preds, date)
    prev_day = preds.get(pdate, {}) if pdate else {}

    farms = {} if not in_season else {
        fid: _farm_entry(raw, prev_day.get(fid)) for fid, raw in day.items()
    }
    counts: dict[str, int] = {}
    for e in farms.values():
        counts[e["risk"]] = counts.get(e["risk"], 0) + 1

    return {
        "date": date,
        "model": model_name,
        "in_season": in_season,
        # 비양식기(6~10월)는 학습 시 IGNORE 구간이라 예측을 비활성화한다.
        "season_note": None if in_season
                       else "비양식기(6~10월) — 김 양식 기간이 아니며, 학습 시 IGNORE 구간이라 예측을 표시하지 않음",
        "prev_date": pdate,
        "onset_threshold": ONSET_TH,
        "risk_counts": counts,
        "farms": farms,
        "out_of_grid_farms": data["meta"].get("out_of_grid_farms", []),
    }


@router.get("/v7-season")
def get_season_info():
    """양식 시즌 정보 — **오늘** 기준 양식기 여부 + 팩의 참고용 날짜들."""
    from datetime import date as _d
    _, data = _load()
    preds = data.get("predictions", {}) if data else {}
    in_season_dates = sorted(d for d in preds if _in_season(d))

    today = _d.today().isoformat()
    today_in_season = _in_season(today)

    return {
        "today": today,
        # ★ 오늘이 양식기인가 — 대시보드는 이걸 기준으로 예측을 켜고 끈다.
        "today_in_season": today_in_season,
        "today_note": None if today_in_season else (
            f"현재 비양식기({int(today[5:7])}월) — 김 양식 기간이 아니므로 위험 예측을 표시하지 않습니다"
        ),
        "harvest_months": sorted(set(range(1, 13)) - OFF_SEASON_MONTHS),
        "off_season_months": sorted(OFF_SEASON_MONTHS),
        "source": "ml/data/channel_builder.py::_is_harvest_season (SSOT)",
        # 데모/검토용 — 지난 시즌 데이터를 볼 때 쓰는 날짜들
        "latest_in_season_date": in_season_dates[-1] if in_season_dates else None,
        "in_season_dates": in_season_dates,
        "n_in_season_dates": len(in_season_dates),
    }


@router.get("/v7/{farm_id}")
def get_v7_farm_series(
    farm_id: str,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """특정 어장의 예측 시계열 반환."""
    model_name, data = _load()
    if not data:
        raise HTTPException(503, "사전 계산 예측 데이터 없음")
    preds = data.get("predictions", {})
    series = []
    for date in sorted(preds.keys()):
        if start and date < start:
            continue
        if end and date > end:
            break
        raw = preds[date].get(farm_id)
        if raw is None:
            continue
        series.append({"date": date, **_farm_entry(raw)})
    if not series:
        raise HTTPException(404, f"어장 없음 또는 해당 기간 데이터 없음: {farm_id}")
    return {
        "farm_id": farm_id,
        "model": model_name,
        "date_range": [series[0]["date"], series[-1]["date"]],
        "series": series,
    }


@router.get("/v7-meta")
def get_v7_meta():
    """사전 계산 예측 메타 정보."""
    model_name, data = _load()
    if not data:
        raise HTTPException(503, "사전 계산 예측 데이터 없음")
    return data.get("meta", {})
