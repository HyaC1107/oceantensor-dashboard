"""Context Filter — LLM 프롬프트 주입 전 민감정보 제거 & 익명화."""
from __future__ import annotations

import re
from typing import Any

from app.mcp.policy_engine import MCPPolicyEngine, PolicyAction, policy_engine


# 정규식 기반 PII 탐지 패턴
_PHONE_RE = re.compile(r"010[-\s]?\d{4}[-\s]?\d{4}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_COORD_RE = re.compile(r"\d{2,3}\.\d{5,}")  # 정밀 GPS 좌표


def filter_context(
    data: dict,
    request_type: str = "llm_context",
) -> dict:
    """데이터 dict를 MCP 정책 엔진으로 필터링.

    Args:
        data:         LLM에 전달할 원본 데이터
        request_type: 요청 유형

    Returns:
        정책 통과한 데이터 dict (차단이면 빈 dict)
    """
    result = policy_engine.evaluate(request_type, data)
    if result.action == PolicyAction.BLOCK:
        return {}
    return result.payload or {}


def scrub_pii_from_text(text: str) -> str:
    """자유 텍스트에서 PII 패턴을 마스킹.

    전화번호 → [PHONE], 이메일 → [EMAIL], 정밀좌표 → [COORD]
    """
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _COORD_RE.sub("[COORD]", text)
    return text


def build_llm_context(
    sensor_data: dict,
    prediction: dict | None = None,
    farm_id: str = "unknown",
) -> dict:
    """LLM RAG 컨텍스트 구성 — 필터링 후 구조화.

    Returns:
        {
          "farm_id": 익명화된 ID,
          "sensor_summary": 집계 센서값 요약,
          "prediction_summary": 예측 결과 요약,
        }
    """
    # 센서 데이터 필터링
    safe_sensor = filter_context(sensor_data, "llm_context")

    # 예측 데이터 필터링
    safe_pred = filter_context(prediction or {}, "llm_context")

    anon_farm = policy_engine.anonymize_farm_id(farm_id)

    sensor_summary = ", ".join(
        f"{k}={v}" for k, v in safe_sensor.items()
        if v is not None
    )

    pred_summary = ""
    if safe_pred:
        score = safe_pred.get("anomaly_score", "N/A")
        stage = safe_pred.get("stage", "N/A")
        pred_summary = f"황백화지수={score}, 단계={stage}"

    return {
        "farm_id": anon_farm,
        "sensor_summary": sensor_summary,
        "prediction_summary": pred_summary,
    }
