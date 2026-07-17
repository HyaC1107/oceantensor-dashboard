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
STAGE_LABELS = {0: "정상", 1: "초기", 2: "경계", 3: "심각"}

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


# ── 위험 등급: warn 절대값 기반 ────────────────────────────────────────────
# 🔴 2026-07-17: Δwarn(전일 대비 급등) 기반 "급등 경보" 판정을 **제거**했다.
#
# 제거 이유 — 실측(`analysis/onset_eval6_delta.py`, val=안 본 25-26시즌 1.3억 픽셀):
#   Δwarn 의 onset 예측 AUC = **0.3852(warn) / 0.4696(severe)** → 무작위(0.5)보다 나쁜 음의 상관.
#   (warn이 이미 높은 곳은 포화되어 Δ≈0인데 거기가 정작 양성이고,
#    warn 낮은 곳에서 노이즈로 Δ가 양수로 튄다 → Δ가 클수록 음성)
#   반면 같은 표본에서 **warn 절대값 AUC = 0.9772 / 0.9877** 로 유효하다.
#
# 왜 애초에 Δwarn을 썼었나 (재발 방지용 기록):
#   "warn onset 탐지가 검증된 강점(+3.3pt vs persistence)"이라는 근거로 Δwarn을 채택했으나,
#   그 +3.3pt는 **warn 절대값**의 성적이었다. "onset 탐지가 강하다"에서 "Δ로 칠하자"로 건너뛴
#   논리 비약이었고, Δwarn 자체는 2026-07-17까지 한 번도 평가된 적이 없었다.
#
# ⚠️ 남은 한계 (임계값으로 못 고침 — 모델 재학습 영역):
#   warn/severe/adi7 출력이 전부 **이진 포화**(median 0.000 / p75 0.989 / p90 1.000)라
#   임계값을 0.5→0.9567로 올려도 28.98%→26.41%로 2.5%p밖에 안 줄어든다.
#   즉 "상시 ~29% 위험 표시"는 여기서 조정할 수 없다. 원인 추정 = 학습의 focal_gamma=3.0.
SUSTAINED_TH = 0.50   # warn ≥ 0.5 → 고위험
WATCH_TH     = 0.20   # 주의

RISK_LABELS = {
    "sustained": "고위험",
    "watch":     "주의",
    "normal":    "정상",
}


def _risk_class(warn: float) -> str:
    """warn(7일내 발생확률) 절대값 → 위험 등급. (모듈 내부 전용)"""
    if warn >= SUSTAINED_TH:
        return "sustained"
    if warn >= WATCH_TH:
        return "watch"
    return "normal"


def _farm_entry(raw, prev=None) -> dict:
    """구 팩(int stage) / 신 팩(dict) → 공통 스키마 + warn 절대값 기반 위험등급.

    `onset`(Δwarn)은 참고 지표로 응답에 실어주되 **등급 판정에는 쓰지 않는다**(AUC 0.385).
    """
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
    entry["onset"] = onset          # 참고용 노출 — 판정에는 미사용
    entry["risk"] = _risk_class(warn)
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
        # onset_threshold 제거(2026-07-17) — Δwarn 판정 폐기. 하위호환 위해 키는 남기되 null.
        "onset_threshold": None,
        "risk_thresholds": {"sustained": SUSTAINED_TH, "watch": WATCH_TH},
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


@lru_cache(maxsize=1)
def _build_sequence() -> Optional[dict]:
    """양식기(11~5월) 일단위 어장별 위험등급 시퀀스 (무거운 전량 계산 — 팩당 1회 캐시).

    지도 색상 SSOT(`_risk_class`, warn 절대값 기준)를 그대로 재사용해 **전 어장 × 양식기 전 날짜**의
    risk 등급만 뽑아 열지향 문자열로 압축한다. `_load`(lru_cache)와 함께 캐시되므로
    팩 교체 후 백엔드 재시작 시 함께 무효화된다.
    """
    _, data = _load()
    if not data:
        return None
    preds = data.get("predictions", {})
    dates = sorted(d for d in preds if _in_season(d))
    if not dates:
        return None

    # 코드 "3"(구 onset)은 2026-07-17 Δwarn 판정 폐기로 더 이상 생성되지 않는다.
    CODE = {"sustained": "2", "watch": "1", "normal": "0"}
    gids = sorted({g for d in dates for g in preds[d].keys()})
    codes: dict[str, list[str]] = {g: [] for g in gids}

    # 등급이 warn 절대값만으로 결정되므로 전일 프레임 조회(_prev_date)가 불필요해졌다.
    for d in dates:
        frame = preds[d]
        for g in gids:
            raw = frame.get(g)
            if not isinstance(raw, dict):
                codes[g].append(".")          # 그날 그 어장 예측 없음
                continue
            codes[g].append(CODE[_risk_class(float(raw.get("warn", 0.0)))])

    return {
        "dates": dates,
        "codes": {g: "".join(v) for g, v in codes.items()},
        # legend는 **현재 계약만** 선언한다. 구 "3"(onset)은 2026-07-17 폐기 후 생성되지 않으므로 뺐다.
        "code_legend": {"2": "sustained", "1": "watch", "0": "normal", ".": "none"},
        "out_of_grid_farms": data["meta"].get("out_of_grid_farms", []),
    }


@router.get("/v7-sequence")
def get_v7_sequence():
    """양식기 일단위 위험등급 시퀀스 — 프론트 타임랩스 자동재생용(fetch 1회로 시즌 통째).

    codes[gid] = 날짜순 등급 문자열. 문자: 2=sustained / 1=watch / 0=normal / .=예측없음.
    색 판정은 `/predict/v7`와 동일한 `_risk_class`(warn 절대값 기준)를 쓴다.
    ※ 구 "3"(onset, Δwarn 기반)은 2026-07-17 폐기 — 더 이상 생성되지 않는다.
    """
    model_name, _ = _load()
    seq = _build_sequence()
    if seq is None:
        raise HTTPException(503, "양식기 예측 데이터 없음")
    return {"model": model_name, **seq}


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
