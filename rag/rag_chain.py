"""RAG Chain — LangChain 리트리버(pgvector) + LLM 생성 통합 파이프라인.

생성 우선순위: Gemini(Google AI Studio) → Claude(Anthropic) → 검색 기반 템플릿.
"""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from rag.prompt_injector import build_rag_prompt
from rag.vectorstore import HwangbaekRetriever

try:
    from app.config import settings
except Exception:  # 단독 실행/테스트 대비
    settings = None


def _get_key(env_name: str, attr: str) -> str:
    if settings is not None:
        v = getattr(settings, attr, "") or ""
        if v:
            return v
    return os.getenv(env_name, "")


class RAGChain:
    """황백화 Q&A RAG 체인 (LangChain 리트리버 + 채팅모델).

    Args:
        top_k:    검색할 문서 수
        use_llm:  True면 LLM 생성 시도, False면 검색 기반 템플릿만
    """

    def __init__(self, top_k: int = 3, use_llm: bool = True):
        self.top_k = top_k
        self.use_llm = use_llm

    async def aquery(
        self,
        question: str,
        session: AsyncSession,
        sensor_context: dict | None = None,
        max_tokens: int = 512,
    ) -> dict:
        """질문에 대한 답변 생성.

        Returns:
            {"query", "answer", "sources", "mode", "tokens_used"}
        """
        # 1. 문서 검색 (LangChain 리트리버 → pgvector 코사인 검색)
        retriever = HwangbaekRetriever(session=session, top_k=self.top_k)
        docs = await retriever.ainvoke(question)
        sources = [d.metadata.get("title", "") for d in docs]

        # 2. 프롬프트 구성
        system_prompt, user_prompt = build_rag_prompt(question, docs, sensor_context)

        # 3. LLM 생성 시도 — Gemini 우선 → Anthropic → 템플릿
        if self.use_llm:
            gem = self._gemini_generate(system_prompt, user_prompt, max_tokens)
            if gem:
                return {
                    "query": question, "answer": gem["answer"], "sources": sources,
                    "mode": f"llm-gemini ({gem['model']})", "tokens_used": gem["tokens"],
                }
            claude = self._claude_generate(system_prompt, user_prompt, max_tokens)
            if claude:
                return {
                    "query": question, "answer": claude["answer"], "sources": sources,
                    "mode": "llm-claude", "tokens_used": claude["tokens"],
                }

        # 4. Template fallback (LLM 없거나 실패 시)
        answer = self._template_answer(docs)
        return {"query": question, "answer": answer, "sources": sources, "mode": "template", "tokens_used": 0}

    def _gemini_generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> dict | None:
        key = _get_key("GEMINI_API_KEY", "gemini_api_key")
        if not key:
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = getattr(settings, "gemini_model", "gemini-2.5-flash") if settings else "gemini-2.5-flash"
            llm = ChatGoogleGenerativeAI(
                model=model_name, google_api_key=key,
                temperature=0.3, max_output_tokens=max_tokens,
            )
            resp = llm.invoke([("system", system_prompt), ("human", user_prompt)])
            text = (resp.content or "").strip()
            if not text:
                return None
            usage = getattr(resp, "usage_metadata", None) or {}
            tokens = int(usage.get("total_tokens", 0) or 0)
            return {"answer": text, "tokens": tokens, "model": model_name}
        except Exception as e:
            print(f"[RAG] Gemini 생성 실패: {e} — fallback")
            return None

    def _claude_generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> dict | None:
        key = _get_key("ANTHROPIC_API_KEY", "anthropic_api_key")
        if not key:
            return None
        try:
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(
                model="claude-haiku-4-5-20251001", api_key=key, max_tokens=max_tokens,
            )
            resp = llm.invoke([("system", system_prompt), ("human", user_prompt)])
            text = (resp.content or "").strip()
            if not text:
                return None
            usage = getattr(resp, "usage_metadata", None) or {}
            tokens = int((usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0))
            return {"answer": text, "tokens": tokens}
        except Exception as e:
            print(f"[RAG] Claude 생성 실패: {e} — template fallback")
            return None

    def _template_answer(self, docs: list) -> str:
        """검색 문서 기반 템플릿 답변 생성 (LLM 미사용 시)."""
        if not docs:
            return "관련 정보를 찾지 못했습니다. 국립수산과학원 서해수산연구소 누리집을 참고하세요."

        top = docs[0]
        sentences = top.page_content.split(". ")
        summary = ". ".join(sentences[:3])

        refs = "\n".join(f"  - {d.metadata.get('title', '')} (출처: {d.metadata.get('source', '?')})" for d in docs)
        return (
            f"{summary}\n\n"
            f"[참고 문서]\n{refs}\n\n"
            "더 자세한 내용은 국립수산과학원 또는 KOEM 해양환경측정망을 참고하세요."
        )


# 싱글턴
_chain: RAGChain | None = None


def get_chain() -> RAGChain:
    global _chain
    if _chain is None:
        gemini_key = _get_key("GEMINI_API_KEY", "gemini_api_key")
        anthropic_key = _get_key("ANTHROPIC_API_KEY", "anthropic_api_key")
        _chain = RAGChain(top_k=3, use_llm=bool(gemini_key or anthropic_key))
    return _chain
