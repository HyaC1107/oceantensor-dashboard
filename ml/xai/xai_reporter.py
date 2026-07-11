"""XAI Reporter — 황백화 원인 분석 자동 보고서 생성.

TinyTransformer의 Attention Map + 센서값을 받아
어가(양식 농가)가 이해할 수 있는 자연어 보고서 + JSON 구조체를 생성.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ml.xai.attention_viz import (
    extract_attention_map,
    build_top_causes,
    render_attention_heatmap_base64,
    STAGE_NAMES,
)


STAGE_DESCRIPTIONS = {
    0: "현재 양식장은 정상 상태입니다. 황백화 위험이 낮습니다.",
    1: "황백화 초기 징후가 감지되었습니다. 주의 관찰이 필요합니다.",
    2: "황백화 경계 단계입니다. 조기 대응 조치를 검토하세요.",
    3: "황백화가 진행 중입니다. 즉각적인 대응이 필요합니다.",
    4: "황백화 심각 단계입니다. 긴급 조치를 취하십시오.",
}

FEATURE_DISPLAY = {
    "water_temp":       "수온",
    "dissolved_oxygen": "용존산소(DO)",
    "din":              "용존무기질소(DIN)",
    "dip":              "용존무기인(DIP)",
    "np_ratio":         "N:P 비율",
    "salinity":         "염분",
    "precipitation":    "강수량(3일)",
    "chlorophyll_a":    "클로로필-a",
}

UNIT_MAP = {
    "water_temp": "℃",
    "dissolved_oxygen": "mg/L",
    "din": "μmol/L",
    "dip": "μmol/L",
    "np_ratio": "",
    "salinity": "PSU",
    "precipitation": "mm",
    "chlorophyll_a": "μg/L",
}

CAUSE_ADVICE = {
    "din": {
        "BELOW_THRESHOLD": "DIN(용존무기질소)이 임계치 이하입니다. 질소 부족으로 황백화가 악화될 수 있습니다.",
        "ABOVE_THRESHOLD": "DIN이 높습니다. 육상 오염원 유입 가능성을 확인하세요.",
    },
    "water_temp": {
        "ABOVE_THRESHOLD": "수온이 임계치를 초과했습니다. 고온 스트레스로 인한 황백화 위험이 높습니다.",
        "BELOW_THRESHOLD": "수온은 정상 범위입니다.",
    },
    "np_ratio": {
        "BELOW_THRESHOLD": "N:P 비가 낮습니다(질소 상대적 부족). 황백화 유발 가능성이 있습니다.",
        "ABOVE_THRESHOLD": "N:P 비가 높습니다. 인산염 부족 상태를 모니터링하세요.",
    },
    "dissolved_oxygen": {
        "BELOW_THRESHOLD": "DO가 낮습니다. 산소 부족으로 생리 장애가 발생할 수 있습니다.",
        "ABOVE_THRESHOLD": "DO는 정상 이상입니다.",
    },
    "salinity": {
        "BELOW_THRESHOLD": "염분이 낮습니다. 강우 유출수 유입 가능성이 있습니다.",
        "ABOVE_THRESHOLD": "염분이 높습니다. 증발·환류 영향을 확인하세요.",
    },
    "precipitation": {
        "ABOVE_THRESHOLD": "최근 3일 강수량이 많습니다. 육상 오염 유입 및 영양염 변동을 주시하세요.",
        "BELOW_THRESHOLD": "강수량 영향은 낮습니다.",
    },
    "chlorophyll_a": {
        "ABOVE_THRESHOLD": "클로로필-a 농도가 높습니다. 식물플랑크톤 번성으로 DIN 고갈 가능성이 있습니다.",
        "BELOW_THRESHOLD": "클로로필-a는 정상 범위입니다.",
    },
    "dip": {
        "BELOW_THRESHOLD": "DIP(인산염)이 낮습니다. 인 부족 상태입니다.",
        "ABOVE_THRESHOLD": "DIP가 높습니다.",
    },
}


def generate_report(
    model_output: dict,
    farm_id: str,
    sensor_values: dict | None = None,
    include_heatmap: bool = False,
) -> dict:
    """황백화 원인 분석 보고서 생성.

    Args:
        model_output:    TinyTransformer.forward() 반환값
        farm_id:         양식장 ID
        sensor_values:   최신 센서 측정값 dict
        include_heatmap: True면 base64 PNG 히트맵 포함

    Returns:
        완전한 보고서 dict (API 응답으로 바로 직렬화 가능)
    """
    attn_map = extract_attention_map(model_output)
    top_causes = build_top_causes(attn_map, sensor_values)

    stage = attn_map["stage"]
    anomaly_score = attn_map["anomaly_score"]

    # 자연어 요약
    summary = _build_summary(stage, anomaly_score, top_causes)
    recommendations = _build_recommendations(stage, top_causes)

    report = {
        "report_id": f"{farm_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "farm_id": farm_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "stage_name": STAGE_NAMES[min(stage, 4)],
        "anomaly_score": anomaly_score,
        "summary": summary,
        "attention_map": {
            "tokens": attn_map["tokens"],
            "weights": attn_map["weights"],
            "top_feature": attn_map["top_feature"],
        },
        "top_causes": top_causes,
        "recommendations": recommendations,
        "sensor_snapshot": sensor_values or {},
    }

    if include_heatmap:
        report["heatmap_base64"] = render_attention_heatmap_base64(attn_map)

    return report


def _build_summary(stage: int, score: float, causes: list[dict]) -> str:
    base = STAGE_DESCRIPTIONS.get(stage, "상태를 확인하세요.")
    pct = round(score * 100, 1)
    top = causes[0]["feature"] if causes else None
    top_display = FEATURE_DISPLAY.get(top, top) if top else "알 수 없음"
    return (
        f"{base} "
        f"황백화 지수: {pct}%. "
        f"주요 원인 변수는 '{top_display}'입니다."
    )


def _build_recommendations(stage: int, causes: list[dict]) -> list[str]:
    recs = []

    if stage >= 2:
        recs.append("즉시 양식장 현장 육안 점검을 실시하세요.")
    if stage >= 3:
        recs.append("지역 어업기술센터 또는 국립수산과학원에 연락하세요.")
    if stage >= 4:
        recs.append("수확 시기 조정 및 추가 피해 확산 방지 조치를 취하세요.")

    for cause in causes[:3]:
        feat = cause["feature"]
        status = cause["status"]
        advice = CAUSE_ADVICE.get(feat, {}).get(status)
        if advice:
            recs.append(advice)

    if not recs:
        recs.append("현재 상태를 유지하며 정기 모니터링을 계속하세요.")

    return recs
