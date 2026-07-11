"""XAI 해석 라우터 — Attention Map + 황백화 원인 보고서."""
import random
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models.prediction import PredictionResult
from app.schemas.prediction import ExplainResponse, LLMReportRequest
from app.config import settings

router = APIRouter()


def _score_to_stage(score: float) -> int:
    if score < 0.2:  return 0
    if score < 0.4:  return 1
    if score < 0.6:  return 2
    if score < 0.8:  return 3
    return 4


@router.post("/llm")
async def explain_llm(req: LLMReportRequest):
    """Gemini(Google AI Studio) 기반 황백화 자연어 XAI 보고서.

    프론트가 클릭한 어장의 stage/score/top_causes/sensor_vals 를 그대로 받아
    어가용 자연어 분석을 생성한다. 키 없으면 템플릿 폴백.
    """
    from ml.xai.llm_reporter import generate_llm_report

    stage = req.stage
    if stage is None and req.anomaly_score is not None:
        stage = _score_to_stage(req.anomaly_score)

    return generate_llm_report(
        farm_id=req.farm_id,
        farm_name=req.farm_name,
        region=req.region,
        stage=stage,
        anomaly_score=req.anomaly_score,
        sensor_vals=req.sensor_vals,
        top_causes=req.top_causes,
    )

SENSOR_FEATURES = ["din", "water_temp", "np_ratio", "dissolved_oxygen",
                   "salinity", "dip", "precipitation", "chlorophyll_a"]


def _build_mock_explain(pred_id: int, include_heatmap: bool = False) -> dict:
    """다양한 패턴의 mock attention map 생성 (단순 고정값 탈피)."""
    weights_raw = [random.uniform(0.05, 0.45) for _ in SENSOR_FEATURES]
    total = sum(weights_raw)
    weights = [round(w / total, 4) for w in weights_raw]

    top_idx = weights.index(max(weights))
    top_feat = SENSOR_FEATURES[top_idx]

    mock_vals = {
        "din": round(random.uniform(1.0, 12.0), 2),
        "water_temp": round(random.uniform(18.0, 30.0), 2),
        "np_ratio": round(random.uniform(5.0, 25.0), 2),
        "dissolved_oxygen": round(random.uniform(4.5, 10.0), 2),
        "salinity": round(random.uniform(29.0, 35.0), 2),
        "dip": round(random.uniform(0.15, 1.0), 3),
        "precipitation": round(random.uniform(0, 20.0), 1),
        "chlorophyll_a": round(random.uniform(1.0, 8.0), 2),
    }
    thresh = {
        "din": 5.0, "water_temp": 25.0, "np_ratio": 10.0,
        "dissolved_oxygen": 5.0, "salinity": 30.0,
        "dip": 0.3, "precipitation": 15.0, "chlorophyll_a": 5.0,
    }

    top_causes = []
    for feat, w in sorted(zip(SENSOR_FEATURES, weights), key=lambda x: -x[1])[:5]:
        val = mock_vals[feat]
        thr = thresh[feat]
        if feat in ("din", "dissolved_oxygen", "salinity", "dip"):
            status = "BELOW_THRESHOLD" if val < thr else "ABOVE_THRESHOLD"
        else:
            status = "ABOVE_THRESHOLD" if val > thr else "BELOW_THRESHOLD"
        top_causes.append({
            "feature": feat, "importance": w,
            "value": val, "threshold": thr, "status": status,
        })

    result = {
        "pred_id": pred_id,
        "attention_map_json": {
            "tokens": SENSOR_FEATURES,
            "weights": weights,
            "top_feature": top_feat,
            "top_weight": max(weights),
        },
        "top_causes": top_causes,
    }

    if include_heatmap:
        try:
            from ml.xai.attention_viz import render_attention_heatmap_base64
            result["heatmap_base64"] = render_attention_heatmap_base64(
                {"tokens": SENSOR_FEATURES, "weights": weights}
            )
        except Exception:
            result["heatmap_base64"] = ""

    return result


@router.get("/{pred_id}", response_model=ExplainResponse)
async def get_explain(
    pred_id: int,
    include_heatmap: bool = Query(False, description="base64 PNG 히트맵 포함 여부"),
    db: AsyncSession = Depends(get_db),
):
    if settings.use_mock_data:
        return _build_mock_explain(pred_id, include_heatmap)

    result = await db.execute(
        select(PredictionResult).where(PredictionResult.pred_id == pred_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="예측 결과를 찾을 수 없습니다.")

    explain = ExplainResponse(
        pred_id=row.pred_id,
        attention_map_json=row.attention_map_json,
        top_causes=row.top_causes,
    )

    # 히트맵 생성 (DB에 attention_map 있을 때)
    if include_heatmap and row.attention_map_json:
        try:
            from ml.xai.attention_viz import render_attention_heatmap_base64
            explain.heatmap_base64 = render_attention_heatmap_base64(
                row.attention_map_json
            )
        except Exception:
            pass

    return explain


@router.get("/report/{pred_id}")
async def get_xai_report(
    pred_id: int,
    farm_id: str = Query("A7"),
    db: AsyncSession = Depends(get_db),
):
    """자연어 황백화 원인 분석 보고서."""
    from ml.xai.xai_reporter import generate_report

    if settings.use_mock_data:
        mock_explain = _build_mock_explain(pred_id)
        # mock model_output 형태로 래핑
        mock_out = {
            "anomaly_score": [random.uniform(0.2, 0.9)],
            "stage": [random.randint(0, 4)],
            "token_scores": None,
            "attn_weights": None,
        }
        sensor_vals = {
            tc["feature"]: tc["value"]
            for tc in mock_explain["top_causes"]
        }
        return generate_report(mock_out, farm_id, sensor_vals, include_heatmap=False)

    result = await db.execute(
        select(PredictionResult).where(PredictionResult.pred_id == pred_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="예측 결과를 찾을 수 없습니다.")

    mock_out = {
        "anomaly_score": [row.anomaly_score or 0.0],
        "stage": [3 if (row.anomaly_score or 0) >= 0.8 else
                  2 if (row.anomaly_score or 0) >= 0.6 else
                  1 if (row.anomaly_score or 0) >= 0.4 else 0],
        "token_scores": None,
        "attn_weights": None,
    }
    return generate_report(mock_out, farm_id, {}, include_heatmap=False)
