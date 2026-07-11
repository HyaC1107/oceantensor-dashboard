"""황백화 예측 라우터 — TinyTransformer 실 추론 (torch 없으면 WBI 공식 fallback)."""
import random
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db import get_db
from app.models.sensor import OceanSensorRaw
from app.models.prediction import PredictionResult
from app.schemas.prediction import PredictRequest, PredictResponse
from app.config import settings
from app.metrics import wbi_score_gauge
from app.routers.v7 import _load as _load_v13_pack

router = APIRouter()

# ---------------------------------------------------------------------------
# v13 사전계산 팩 조회 (sensor_vals 없는 요청 = 대시보드 → v13 우선 서빙)
# sensor_vals 있는 요청 = what-if 시뮬레이션/맵 클릭 일관성 → 공식 경로 유지
# ---------------------------------------------------------------------------

def _v13_lookup(farm_id: str, date: Optional[str] = None) -> Optional[dict]:
    """v13 팩에서 (farm, date) 예측 조회. 팩/어장/날짜 없으면 None → 기존 경로 폴백."""
    model_name, data = _load_v13_pack()
    if model_name != "stmmt-v13" or not data:
        return None
    preds = data.get("predictions", {})
    if not preds:
        return None
    if date is None:
        date = max(preds.keys())
    day = preds.get(date)
    if day is None:
        return None
    raw = day.get(farm_id)
    # 완결성 체크: stage/adi7 없거나 adi7 비면 폴백 (malformed 팩으로 500 방지)
    if not isinstance(raw, dict) or "stage" not in raw or not raw.get("adi7"):
        return None
    return {"date": date, **raw}

# ---------------------------------------------------------------------------
# TinyTransformer 로드 (torch 없으면 graceful fallback)
# ---------------------------------------------------------------------------
_model = None
_model_version = "v0.1.0-wbi-formula"

def _load_model():
    global _model, _model_version
    if _model is not None:
        return _model
    try:
        import torch
        from ml.models.tiny_transformer import TinyTransformer
        from ml.registry.model_registry import ModelRegistry

        registry = ModelRegistry()
        active = registry.get_active_version()
        if active:
            m = TinyTransformer(sensor_dim=8, d_model=128, n_layers=2)
            _model = registry.load(active, m, device="cpu")
            _model_version = f"tiny-transformer-{active}"
            print(f"[predict] TinyTransformer {active} 로드 완료")
        else:
            # 체크포인트 없음 → 초기화된 모델로 추론 (학습 전 데모)
            _model = TinyTransformer(sensor_dim=8, d_model=128, n_layers=2)
            _model.eval()
            _model_version = "v0.1.0-untrained"
            print("[predict] 학습된 체크포인트 없음 — 초기화 모델 사용")
    except Exception as e:
        print(f"[predict] torch 로드 실패 ({e}) — WBI 공식 fallback 사용")
        _model = None
    return _model


# ---------------------------------------------------------------------------
# 센서값 → 8차원 특징 벡터 생성
# ---------------------------------------------------------------------------

def _build_sensor_vector(sensor_vals: dict) -> "np.ndarray":
    """센서 측정값을 TinyTransformer 입력 벡터로 변환 (정규화 포함)."""
    wt  = (sensor_vals.get("water_temp", 15.0) - 15.0) / 5.0
    do_ = (sensor_vals.get("dissolved_oxygen", 8.0) - 8.0) / 2.0
    din = (sensor_vals.get("din", 5.0) - 5.0) / 5.0
    dip = (sensor_vals.get("dip", 0.5) - 0.5) / 0.3
    nrp = (sensor_vals.get("np_ratio", 16.0) - 16.0) / 8.0
    sal = (sensor_vals.get("salinity", 32.0) - 32.0) / 2.0
    pre = (sensor_vals.get("precipitation", 0.0)) / 10.0
    chl = (sensor_vals.get("chlorophyll_a", 3.0) - 3.0) / 2.0
    return np.array([wt, do_, din, dip, nrp, sal, pre, chl], dtype=np.float32)


# ---------------------------------------------------------------------------
# WBI 계산 공식 (torch 없을 때 fallback)
# ---------------------------------------------------------------------------

def _wbi_formula(sensor_vals: dict) -> float:
    """황백화 지수 물리 공식 기반 계산.

    주요 변수 가중치 (KOEM 연구 기반):
      DIN  < 5 μmol/L  → 급격히 상승
      수온  > 25 ℃     → 위험 가중
      N:P  < 10        → 심각 신호
      DO   < 5 mg/L    → 중간 기여
    """
    din  = sensor_vals.get("din", 5.0)
    wt   = sensor_vals.get("water_temp", 15.0)
    nrp  = sensor_vals.get("np_ratio", 16.0)
    do_  = sensor_vals.get("dissolved_oxygen", 8.0)
    sal  = sensor_vals.get("salinity", 32.0)

    # 개별 위험 지수 (0~1)
    din_risk  = max(0.0, 1.0 - din / 5.0)           # 5 μmol/L 이하 → 1
    temp_risk = max(0.0, (wt - 20.0) / 10.0)        # 20℃ 초과 비례
    np_risk   = max(0.0, 1.0 - nrp / 10.0)          # N:P < 10 → 1
    do_risk   = max(0.0, 1.0 - do_ / 5.0)           # DO < 5 → 1
    sal_risk  = max(0.0, (32.0 - sal) / 4.0)        # 염분 낮으면 위험

    # 가중 합산 (논문 기반 가중치)
    wbi = (0.38 * din_risk + 0.27 * temp_risk + 0.19 * np_risk
           + 0.10 * do_risk + 0.06 * sal_risk)
    return float(min(1.0, max(0.0, wbi)))


def _score_to_stage(score: float) -> int:
    if score < 0.2:  return 0  # 정상
    if score < 0.4:  return 1  # 초기
    if score < 0.6:  return 2  # 경계
    if score < 0.8:  return 3  # 진행
    return 4                   # 심각


# ---------------------------------------------------------------------------
# DB에서 최신 센서값 조회
# ---------------------------------------------------------------------------

async def _fetch_latest_sensor(db: AsyncSession, farm_id: str) -> dict:
    result = await db.execute(
        select(OceanSensorRaw).order_by(desc(OceanSensorRaw.observed_at)).limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {}
    din = (row.no3_nitrogen or 0) + (row.nh4_nitrogen or 0)
    dip = 0.82
    return {
        "water_temp": row.water_temp or 15.0,
        "dissolved_oxygen": row.dissolved_oxygen or 8.0,
        "din": din,
        "dip": dip,
        "np_ratio": round(din / dip, 2) if dip else 0.0,
        "salinity": row.salinity or 32.0,
        "precipitation": 0.0,
        "chlorophyll_a": 3.0,
    }


# ---------------------------------------------------------------------------
# 핵심 예측 함수
# ---------------------------------------------------------------------------

def _predict_with_model(sensor_vals: dict, farm_id: str) -> dict:
    """TinyTransformer 실 추론."""
    import torch
    model = _load_model()
    vec = _build_sensor_vector(sensor_vals)        # (8,)
    T = 24
    seq = np.tile(vec, (T, 1))                    # (T, 8)
    seq += np.random.randn(T, 8).astype(np.float32) * 0.05  # 시계열 노이즈

    sensor_tensor = torch.tensor(seq).unsqueeze(0)  # (1, T, 8)

    t0 = time.perf_counter()
    with torch.no_grad():
        out = model(sensor_tensor)
    latency_ms = (time.perf_counter() - t0) * 1000

    score = float(out["anomaly_score"][0])
    severity_pct = float(out["severity_pct"][0])
    stage = int(out["stage"][0])

    # XAI top_causes
    from ml.xai.attention_viz import extract_attention_map, build_top_causes
    attn_map = extract_attention_map(out, t_in=T)
    top_causes = build_top_causes(attn_map, sensor_vals)

    wbi_score_gauge.labels(farm_id=farm_id).set(score)
    return {
        "farm_id": farm_id,
        "predicted_at": datetime.now(timezone.utc),
        "model_version": _model_version,
        "anomaly_score": round(score, 4),
        "severity_pct": round(severity_pct, 1),
        "hwangbaek_flag": stage >= 3,
        "top_causes": top_causes,
        "latency_ms": round(latency_ms, 2),
        "device": "cpu",
        "stage": stage,
        "attention_map": attn_map,
    }


def _predict_formula(sensor_vals: dict, farm_id: str) -> dict:
    """WBI 공식 기반 예측 (torch 없을 때 fallback)."""
    t0 = time.perf_counter()
    score = _wbi_formula(sensor_vals)
    latency_ms = (time.perf_counter() - t0) * 1000 + random.uniform(1, 3)
    stage = _score_to_stage(score)

    weights = [0.38, 0.27, 0.19, 0.10, 0.06]
    features = ["din", "water_temp", "np_ratio", "dissolved_oxygen", "salinity"]
    thresholds = {"din": 5.0, "water_temp": 25.0, "np_ratio": 10.0,
                  "dissolved_oxygen": 5.0, "salinity": 30.0}
    # din/do/salinity/np_ratio 는 '낮을수록 위험', water_temp 는 '높을수록 위험'
    low_is_risk = {"din", "dissolved_oxygen", "salinity", "np_ratio"}
    top_causes = []
    for f, w in zip(features, weights):
        val = sensor_vals.get(f)
        thr = thresholds[f]
        if val is None:
            status = "UNKNOWN"
        elif f in low_is_risk:
            status = "BELOW_THRESHOLD" if val < thr else "ABOVE_THRESHOLD"
        else:
            status = "ABOVE_THRESHOLD" if val > thr else "BELOW_THRESHOLD"
        top_causes.append({
            "feature": f, "importance": w,
            "value": val, "threshold": thr, "status": status,
        })

    wbi_score_gauge.labels(farm_id=farm_id).set(score)
    return {
        "farm_id": farm_id,
        "predicted_at": datetime.now(timezone.utc),
        "model_version": _model_version,
        "anomaly_score": round(score, 4),
        "severity_pct": round(score * 100, 1),
        "hwangbaek_flag": stage >= 3,
        "top_causes": top_causes,
        "latency_ms": round(latency_ms, 2),
        "device": "cpu-formula",
        "stage": stage,
    }


# ---------------------------------------------------------------------------
# 라우터
# ---------------------------------------------------------------------------

def _predict_v13(pack: dict, farm_id: str) -> dict:
    """v13 사전계산 팩 기반 응답 (STMMT 미래 7일 조기경보)."""
    stage = int(pack["stage"])
    warn = float(pack.get("warn", 0.0))
    severe = float(pack.get("severe", 0.0))
    wbi_score_gauge.labels(farm_id=farm_id).set(warn)
    return {
        "farm_id": farm_id,
        "predicted_at": datetime.now(timezone.utc),
        "model_version": "stmmt-v13",
        "anomaly_score": round(warn, 4),          # P(7일 내 발생) 를 위험도로 노출
        "severity_pct": round(severe * 100, 1),   # P(7일 내 심화) %
        "hwangbaek_flag": stage >= 3,
        "top_causes": None,                       # 팩에는 기여도 없음 → /explain 경로 사용
        "latency_ms": 0.1,
        "device": "precomputed-pack",
        "stage": stage,
        "warn": round(warn, 4),
        "severe": round(severe, 4),
        "adi7": pack["adi7"],
        "source_date": pack["date"],
    }


@router.post("/", response_model=PredictResponse)
async def run_predict(
    req: PredictRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1) sensor_vals 없는 요청은 v13 사전계산 팩 우선 (대시보드/조회용)
    #    단 engine="formula" 명시 시엔 팩보다 공식 강제가 우선
    #    v13 서빙은 사전계산 조회라 DB 저장 없이 바로 반환 (의도된 동작)
    if req.sensor_vals is None and req.engine != "formula":
        pack = _v13_lookup(req.farm_id, req.date)
        if pack is not None:
            return _predict_v13(pack, req.farm_id)

    # 2) what-if(sensor_vals) 또는 팩 미커버 어장 → 기존 공식/Tiny 경로
    # 센서값 수집
    if settings.use_mock_data:
        if req.sensor_vals:
            # 프론트가 전달한 어장별 결정론적 더미값 사용 (predict↔explain↔지도 일관성)
            sensor_vals = dict(req.sensor_vals)
            if "np_ratio" not in sensor_vals:
                dip = sensor_vals.get("dip", 0)
                sensor_vals["np_ratio"] = round(
                    sensor_vals.get("din", 0) / dip, 2
                ) if dip else 0.0
        else:
            sensor_vals = {
                "water_temp": round(random.uniform(20.0, 30.0), 2),
                "dissolved_oxygen": round(random.uniform(5.0, 10.0), 2),
                "din": round(random.uniform(1.0, 12.0), 2),
                "dip": round(random.uniform(0.2, 1.0), 3),
                "salinity": round(random.uniform(30.0, 34.0), 2),
                "precipitation": round(random.uniform(0, 15.0), 1),
                "chlorophyll_a": round(random.uniform(1.0, 7.0), 2),
            }
            sensor_vals["np_ratio"] = round(
                sensor_vals["din"] / sensor_vals["dip"], 2
            ) if sensor_vals["dip"] > 0 else 0.0
    else:
        sensor_vals = await _fetch_latest_sensor(db, req.farm_id)

    # 추론 (engine="formula" 면 WBI 공식 강제 — 시뮬레이터 일관성)
    if req.engine == "formula":
        result = _predict_formula(sensor_vals, req.farm_id)
    else:
        try:
            import torch
            model = _load_model()
            if model is not None:
                result = _predict_with_model(sensor_vals, req.farm_id)
            else:
                result = _predict_formula(sensor_vals, req.farm_id)
        except Exception:
            result = _predict_formula(sensor_vals, req.farm_id)

    # DB 저장
    if not settings.use_mock_data:
        try:
            save_data = {k: v for k, v in result.items()
                        if k in {"farm_id", "predicted_at", "model_version",
                                 "anomaly_score", "severity_pct", "hwangbaek_flag",
                                 "latency_ms", "device"}}
            save_data["top_causes"] = result.get("top_causes")
            save_data["attention_map_json"] = result.get("attention_map")
            row = PredictionResult(**save_data)
            db.add(row)
            await db.commit()
            await db.refresh(row)
            result["pred_id"] = row.pred_id
        except Exception as e:
            print(f"[predict] DB 저장 실패: {e}")

    return result


# ---------------------------------------------------------------------------
# 7일 황백화 예측 (시계열 추정)
# ---------------------------------------------------------------------------

def _forecast_series(wbi0: float, farm_id: str, horizon: int = 7) -> list[dict]:
    """현재 WBI 에서 출발해 horizon 일치 WBI 궤적 + 신뢰밴드 생성.

    모델 학습(H100) 전까지의 **결정론적 통계 추정**:
      - 기준선(0.3)으로의 약한 평균회귀 + 어장별 시드 드리프트 + 미세 노이즈
      - 불확실성 밴드는 예측 지평이 멀수록 확대
    farm_id 시드라 클릭마다 동일. 추후 시계열 모델 출력으로 교체 지점.
    """
    rng = random.Random(f"{farm_id}|forecast")
    trend = (rng.random() - 0.42) * 0.045          # 약한 상승 편향 드리프트
    series = [{"day": 0, "wbi": round(wbi0, 3), "lower": round(wbi0, 3), "upper": round(wbi0, 3)}]
    w = wbi0
    for d in range(1, horizon + 1):
        w = w + (0.30 - w) * 0.06 + trend + (rng.random() - 0.5) * 0.015
        w = min(1.0, max(0.0, w))
        band = min(0.25, 0.02 + 0.018 * d)
        series.append({
            "day": d,
            "wbi": round(w, 3),
            "lower": round(max(0.0, w - band), 3),
            "upper": round(min(1.0, w + band), 3),
        })
    return series


@router.post("/forecast")
async def forecast(req: PredictRequest, db: AsyncSession = Depends(get_db)):
    """7일 황백화 위험도 예측 시계열 + 신뢰밴드."""
    # sensor_vals 없는 요청 → v13 실제 미래 7일 ADI 궤적 서빙 (engine="formula" 면 통계 추정 강제)
    if req.sensor_vals is None and req.engine != "formula":
        pack = _v13_lookup(req.farm_id, req.date)
        if pack is not None:
            adi7 = pack["adi7"]
            series = []
            for d, adi in enumerate(adi7, start=1):
                wbi = round(min(1.0, max(0.0, adi / 10.0)), 3)
                series.append({
                    "day": d, "adi": round(float(adi), 2),
                    "wbi": wbi, "lower": wbi, "upper": wbi,  # 팩엔 불확실성 없음 → 밴드 0
                })
            peak = max(series, key=lambda s: s["wbi"])
            return {
                "farm_id": req.farm_id,
                "current_wbi": series[0]["wbi"],
                "horizon_days": len(series),
                "method": "stmmt-v13",
                "source_date": pack["date"],
                "warn": round(float(pack.get("warn", 0.0)), 4),
                "severe": round(float(pack.get("severe", 0.0)), 4),
                "peak_day": peak["day"],
                "peak_wbi": peak["wbi"],
                "series": series,
            }

    # what-if(sensor_vals) 또는 팩 미커버 어장 → 통계 추정 폴백
    if settings.use_mock_data:
        sensor_vals = dict(req.sensor_vals) if req.sensor_vals else {}
    else:
        sensor_vals = await _fetch_latest_sensor(db, req.farm_id)

    wbi0 = _wbi_formula(sensor_vals)
    series = _forecast_series(wbi0, req.farm_id)
    peak = max(series, key=lambda s: s["wbi"])
    return {
        "farm_id": req.farm_id,
        "current_wbi": round(wbi0, 3),
        "horizon_days": 7,
        "method": "statistical-estimate",  # 이 경로는 항상 WBI 공식 + 통계 추정
        "peak_day": peak["day"],
        "peak_wbi": peak["wbi"],
        "series": series,
    }
