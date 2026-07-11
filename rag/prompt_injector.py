"""Prompt Injector — RAG 검색 결과를 LLM 프롬프트에 주입."""
from __future__ import annotations


SYSTEM_PROMPT = """당신은 어텐션플리즈(ATTENTIONPLZ) 황백화 조기경보 시스템의 AI 어시스턴트입니다.
양식 김의 황백화(白化) 현상 탐지·예방·대응에 관한 전문 지식을 보유하고 있습니다.

원칙:
- 제공된 참고 문서를 최우선으로 활용하세요.
- 과학적 근거 없는 추측은 하지 마세요.
- 어가(양식 농가)가 이해하기 쉬운 언어로 답변하세요.
- 긴급 상황(3단계 이상)에는 즉각 대응 방안을 먼저 안내하세요.
"""


def build_rag_prompt(
    query: str,
    retrieved_docs: list[dict],
    sensor_context: dict | None = None,
) -> tuple[str, str]:
    """RAG 프롬프트 구성.

    Args:
        query:          사용자 질문
        retrieved_docs: 검색된 문서 리스트
        sensor_context: 현재 센서 상태 요약 dict

    Returns:
        (system_prompt, user_prompt) 튜플
    """
    # 참고 문서 섹션
    doc_section = "\n\n".join(
        f"[참고 {i+1}] {doc['title']}\n{doc['content']}"
        for i, doc in enumerate(retrieved_docs)
    )

    # 센서 컨텍스트 섹션
    sensor_section = ""
    if sensor_context:
        lines = [f"{k}: {v}" for k, v in sensor_context.items() if v is not None]
        if lines:
            sensor_section = "\n\n[현재 양식장 센서 상태]\n" + "\n".join(lines)

    user_prompt = (
        f"{sensor_section}\n\n"
        f"[참고 문서]\n{doc_section}\n\n"
        f"[질문]\n{query}\n\n"
        "위 참고 문서와 센서 상태를 바탕으로 질문에 답변해주세요."
    )

    return SYSTEM_PROMPT, user_prompt


def build_report_prompt(report: dict) -> tuple[str, str]:
    """XAI 보고서 기반 자연어 설명 생성 프롬프트."""
    stage_name = report.get("stage_name", "알 수 없음")
    score = report.get("anomaly_score", 0)
    top_causes = report.get("top_causes", [])
    causes_text = "\n".join(
        f"- {c['feature']}: {c.get('value', 'N/A')} (임계치: {c.get('threshold', 'N/A')}, 상태: {c.get('status', '')})"
        for c in top_causes[:3]
    )

    user_prompt = (
        f"양식장 황백화 분석 결과:\n"
        f"- 황백화 단계: {stage_name}\n"
        f"- 황백화 지수: {score:.1%}\n"
        f"- 주요 원인 변수:\n{causes_text}\n\n"
        "위 결과를 어가(농가 주인)가 이해하기 쉽게 3~5문장으로 설명하고, "
        "즉각 취해야 할 조치 1~2가지를 안내해주세요."
    )
    return SYSTEM_PROMPT, user_prompt
