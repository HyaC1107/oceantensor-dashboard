"""Feature Store — 전처리 완료 피처를 버전 관리하며 DB에 저장.

역할:
  1. 공공API 수집 원시 데이터를 Feature Schema로 변환
  2. WBI(황백화 지수) 계산 포함
  3. OutlierDetector로 품질 플래그 부여
  4. feature_store 테이블에 upsert
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.feature import FeatureStore
from data_pipeline.processors.outlier_detector import OutlierDetector

# 싱글턴 OutlierDetector (프로세스 생애주기 유지)
_detector = OutlierDetector(window_size=100)

FEATURE_VERSION = "v1.0"


def _compute_wbi(features: dict) -> float:
    """황백화 지수(WBI) 계산.

    가중 합산:
      DIN  낮을수록 위험 (0.38) — 기준: 70 μg/L (= 0.07 mg/L), 출처: NIFS/JKOSMEE 2018
      수온  높을수록 위험 (0.27)
      N:P  낮을수록 위험 (0.19) — 기준: 몰비 6:1, 출처: JKOSMEE 2023
      DO   낮을수록 위험 (0.10)
      염분  낮을수록 위험 (0.06)

    DIN, DIP 단위: μg/L
    """
    din  = features.get("din") or 100.0   # μg/L, 기본값=정상 범위
    wt   = features.get("water_temp_surface") or 15.0
    nrp  = features.get("din_dip_ratio") or 26.0  # 몰비, 기본값=김 최적 성장 비율
    do_  = features.get("do_surface") or 8.0
    sal  = features.get("salinity") or 32.0

    # DIN < 70 μg/L → 위험, 0에 가까울수록 risk=1.0
    din_risk  = max(0.0, 1.0 - din / 70.0)
    temp_risk = max(0.0, (wt - 20.0) / 10.0)
    # N:P 몰비 < 6 → 위험
    np_risk   = max(0.0, 1.0 - nrp / 6.0)
    do_risk   = max(0.0, 1.0 - do_ / 5.0)
    sal_risk  = max(0.0, (32.0 - sal) / 4.0)

    wbi = (0.38 * din_risk + 0.27 * temp_risk + 0.19 * np_risk
           + 0.10 * do_risk + 0.06 * sal_risk)
    return round(min(1.0, max(0.0, wbi)), 4)


def build_feature_row(
    farm_id: str,
    feature_ts: datetime,
    raw: dict,
) -> dict:
    """원시 센서 dict → feature_store 레코드 dict.

    Args:
        farm_id:    양식장 ID
        feature_ts: 피처 기준 시각
        raw:        수집된 원시 데이터 dict

    Returns:
        feature_store 컬럼 매핑 dict
    """
    din  = raw.get("din") or (
        (raw.get("no3_nitrogen") or 0) + (raw.get("nh4_nitrogen") or 0)
    )
    dip  = raw.get("dip") or raw.get("dip_surface") or 20.0  # μg/L, 기본값=정상 범위
    nrp  = round(din / dip, 4) if dip > 0 else 0.0
    chl  = raw.get("chlorophyll_a") or raw.get("chl_a") or raw.get("chlorophyll")
    prec = raw.get("precipitation") or raw.get("precipitation_3d") or 0.0

    features = {
        "water_temp_surface": raw.get("water_temp") or raw.get("water_temp_surface"),
        "water_temp_bottom":  raw.get("water_temp_bottom"),
        "do_surface":         raw.get("dissolved_oxygen") or raw.get("do_surface"),
        "din":                din,
        "dip":                dip,
        "din_dip_ratio":      nrp,
        "chlorophyll_a":      chl,
        "salinity":           raw.get("salinity"),
        "turbidity":          raw.get("turbidity"),
        "wind_speed":         raw.get("wind_speed"),
        "precipitation_3d":   prec,
        "sst_anomaly":        raw.get("sst_anomaly"),
        "chl_satellite":      raw.get("chl_satellite"),
    }

    # 이상값 탐지 & 품질 플래그
    detect_input = {k: v for k, v in features.items() if v is not None}
    report = _detector.detect(detect_input, record_id=f"{farm_id}@{feature_ts}")
    quality_flag = 1
    if report.max_severity == "critical":
        quality_flag = -1
    elif report.max_severity == "warning":
        quality_flag = 0

    # WBI 계산
    # (feature_store에 직접 저장하지 않고 predict.py에서 계산하지만 디버깅용 포함)
    _ = _compute_wbi(features)

    return {
        "farm_id":            farm_id,
        "feature_ts":         feature_ts,
        "feature_version":    FEATURE_VERSION,
        "quality_flag":       quality_flag,
        **{k: v for k, v in features.items() if v is not None},
    }


async def upsert_features(
    db: AsyncSession,
    farm_id: str,
    feature_ts: datetime,
    raw: dict,
) -> dict:
    """feature_store 테이블에 upsert.

    기존 (farm_id, feature_ts) 레코드가 있으면 업데이트, 없으면 삽입.
    Returns: 저장된 feature row dict
    """
    row = build_feature_row(farm_id, feature_ts, raw)

    stmt = insert(FeatureStore).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["farm_id", "feature_ts"],
        set_={k: v for k, v in row.items() if k not in ("farm_id", "feature_ts")},
    )

    try:
        await db.execute(stmt)
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"[FeatureStore] upsert 실패: {e}")

    return row


def compute_wbi(raw_or_features: dict) -> float:
    """외부에서 호출 가능한 WBI 계산 함수 (단순 래퍼)."""
    return _compute_wbi(raw_or_features)
