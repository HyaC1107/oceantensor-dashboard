"""LLM XAI Reporter — Google AI Studio(Gemini) 기반 황백화 자연어 보고서.

predict/explain 이 만든 정형 결과(stage·anomaly_score·top_causes·sensor_vals)를
어가(양식 농가)가 이해할 수 있는 자연어 분석으로 변환한다.

- GEMINI_API_KEY 가 있으면 실제 Gemini 호출.
- 키가 없거나 호출이 실패하면 규칙 기반 템플릿으로 graceful fallback.
"""
from __future__ import annotations

import json
import re

from app.config import settings

# 변수 표시명 / 단위 / 임계치 (xai_reporter 와 동일 기준)
FEATURE_DISPLAY = {
    "water_temp": "수온",
    "dissolved_oxygen": "용존산소(DO)",
    "din": "용존무기질소(DIN)",
    "dip": "용존무기인(DIP)",
    "np_ratio": "N:P 비율",
    "salinity": "염분",
    "precipitation": "강수량(3일)",
    "chlorophyll_a": "클로로필-a",
}
UNIT_MAP = {
    "water_temp": "℃", "dissolved_oxygen": "mg/L", "din": "μmol/L",
    "dip": "μmol/L", "np_ratio": "", "salinity": "PSU",
    "precipitation": "mm", "chlorophyll_a": "μg/L",
}
STAGE_NAMES = {0: "정상", 1: "초기", 2: "경계", 3: "진행", 4: "심각"}


# ---------------------------------------------------------------------------
# 프롬프트 구성
# ---------------------------------------------------------------------------
def _build_prompt(farm_id, farm_name, region, stage, score, sensor_vals, top_causes) -> str:
    stage_name = STAGE_NAMES.get(stage or 0, "정상")
    pct = round((score or 0.0) * 100, 1)

    cause_lines = []
    for c in (top_causes or [])[:5]:
        feat = c.get("feature")
        disp = FEATURE_DISPLAY.get(feat, feat)
        unit = UNIT_MAP.get(feat, "")
        val = c.get("value")
        thr = c.get("threshold")
        imp = round((c.get("importance") or 0) * 100)
        status = {"ABOVE_THRESHOLD": "기준 초과", "BELOW_THRESHOLD": "기준 미달"}.get(
            c.get("status"), "정상범위"
        )
        cause_lines.append(
            f"- {disp}: 측정 {val}{unit} / 기준 {thr}{unit} ({status}), 기여도 {imp}%"
        )
    causes_block = "\n".join(cause_lines) if cause_lines else "- (원인 변수 없음)"

    loc = f"{farm_name or farm_id}" + (f" ({region})" if region else "")

    return f"""너는 김(해조류) 양식 황백화(white rot) 조기경보 시스템의 해양 AI 분석가다.
아래 한 양식장의 실시간 센서 분석 결과를 보고, 양식 어가가 바로 이해하고 행동할 수 있는
한국어 분석 보고서를 작성해라. 전문용어는 쉽게 풀어쓰고, 과장 없이 데이터에 근거해라.

[양식장] {loc}
[황백화 단계] {stage}단계 · {stage_name} (위험지수 {pct}%)
[주요 원인 변수 (XAI Attention 기여도 순)]
{causes_block}

반드시 아래 JSON 형식 '하나만' 출력해라. 코드블록/설명 금지.
{{
  "summary": "현재 상황을 2~3문장으로 요약 (단계와 핵심 원인 포함)",
  "cause_analysis": [
    {{"feature": "변수영문키(예: din)", "text": "그 변수가 왜 문제/정상인지 1~2문장으로 쉽게"}}
  ],
  "recommendations": ["어가가 지금 할 수 있는 구체적 조치 1", "조치 2", "조치 3"]
}}
"""


# ---------------------------------------------------------------------------
# 템플릿 폴백
# ---------------------------------------------------------------------------
def _fallback_report(farm_id, farm_name, stage, score, top_causes) -> dict:
    stage = stage or 0
    stage_name = STAGE_NAMES.get(stage, "정상")
    pct = round((score or 0.0) * 100, 1)
    top = (top_causes or [{}])[0]
    top_disp = FEATURE_DISPLAY.get(top.get("feature"), top.get("feature") or "알 수 없음")

    base = {
        0: "현재 양식장은 정상 상태입니다. 황백화 위험이 낮습니다.",
        1: "황백화 초기 징후가 감지되었습니다. 주의 관찰이 필요합니다.",
        2: "황백화 경계 단계입니다. 조기 대응을 검토하세요.",
        3: "황백화가 진행 중입니다. 즉각적인 대응이 필요합니다.",
        4: "황백화 심각 단계입니다. 긴급 조치를 취하십시오.",
    }.get(stage, "상태를 확인하세요.")

    cause_analysis = []
    for c in (top_causes or [])[:3]:
        feat = c.get("feature")
        disp = FEATURE_DISPLAY.get(feat, feat)
        st = c.get("status")
        if st == "BELOW_THRESHOLD":
            txt = f"{disp}이(가) 기준치보다 낮습니다. 황백화 위험을 높이는 요인입니다."
        elif st == "ABOVE_THRESHOLD":
            txt = f"{disp}이(가) 기준치를 초과했습니다. 모니터링이 필요합니다."
        else:
            txt = f"{disp}은(는) 정상 범위입니다."
        cause_analysis.append({"feature": feat, "text": txt})

    recs = []
    if stage >= 2:
        recs.append("양식장 현장 육안 점검을 실시하세요.")
    if stage >= 3:
        recs.append("지역 어업기술센터 또는 국립수산과학원에 연락하세요.")
    if not recs:
        recs.append("현 상태를 유지하며 정기 모니터링을 계속하세요.")

    return {
        "used_llm": False,
        "model": "template-fallback",
        "farm_id": farm_id,
        "stage": stage,
        "stage_name": stage_name,
        "summary": f"{base} 황백화 위험지수 {pct}%. 주요 원인은 '{top_disp}'입니다.",
        "cause_analysis": cause_analysis,
        "recommendations": recs,
    }


def _parse_json(text: str) -> dict | None:
    """모델 출력에서 JSON 블록 추출/파싱."""
    if not text:
        return None
    # 코드펜스 제거
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------
def generate_llm_report(
    farm_id: str,
    farm_name: str | None = None,
    region: str | None = None,
    stage: int | None = None,
    anomaly_score: float | None = None,
    sensor_vals: dict | None = None,
    top_causes: list | None = None,
) -> dict:
    """Gemini 로 황백화 자연어 보고서 생성. 실패 시 템플릿 폴백."""
    if not settings.gemini_api_key:
        return _fallback_report(farm_id, farm_name, stage, anomaly_score, top_causes)

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        prompt = _build_prompt(
            farm_id, farm_name, region, stage, anomaly_score, sensor_vals, top_causes
        )
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.4, "response_mime_type": "application/json"},
        )
        parsed = _parse_json(getattr(resp, "text", "") or "")
        if not parsed or "summary" not in parsed:
            fb = _fallback_report(farm_id, farm_name, stage, anomaly_score, top_causes)
            fb["llm_error"] = "응답 파싱 실패"
            return fb

        return {
            "used_llm": True,
            "model": settings.gemini_model,
            "farm_id": farm_id,
            "stage": stage,
            "stage_name": STAGE_NAMES.get(stage or 0, "정상"),
            "summary": parsed.get("summary", ""),
            "cause_analysis": parsed.get("cause_analysis", []),
            "recommendations": parsed.get("recommendations", []),
        }
    except Exception as e:  # 키 오류/네트워크/쿼터 등 → 폴백
        fb = _fallback_report(farm_id, farm_name, stage, anomaly_score, top_causes)
        fb["llm_error"] = str(e)
        return fb
