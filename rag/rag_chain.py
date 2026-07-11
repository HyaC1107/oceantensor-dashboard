"""RAG Chain — 검색 + LLM 생성 통합 파이프라인.

생성 우선순위: Gemini(Google AI Studio) → Claude(Anthropic) → 검색 기반 템플릿.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from rag.embedder import get_index, BUILTIN_DOCS
from rag.prompt_injector import build_rag_prompt

try:
    from app.config import settings
except Exception:  # 단독 실행/테스트 대비
    settings = None


class RAGChain:
    """황백화 Q&A RAG 체인.

    Args:
        top_k:    검색할 문서 수
        use_llm:  True면 Claude API 사용, False면 검색 기반 답변
    """

    def __init__(self, top_k: int = 3, use_llm: bool = True):
        self.top_k = top_k
        self.use_llm = use_llm
        self._client = None
        self._index = get_index()

    def _get_client(self):
        """Anthropic 클라이언트 lazy init."""
        if self._client:
            return self._client
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                return None
            self._client = anthropic.Anthropic(api_key=api_key)
            return self._client
        except ImportError:
            return None

    def _gemini_generate(self, system_prompt: str, user_prompt: str, max_tokens: int):
        """Gemini(Google AI Studio)로 답변 생성. 키 없거나 실패 시 None."""
        key = getattr(settings, "gemini_api_key", "") if settings else os.getenv("GEMINI_API_KEY", "")
        if not key:
            return None
        try:
            import google.generativeai as genai
            model_name = getattr(settings, "gemini_model", "gemini-2.5-flash") if settings else "gemini-2.5-flash"
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
            resp = model.generate_content(
                user_prompt,
                generation_config={"temperature": 0.3, "max_output_tokens": max_tokens},
            )
            text = (getattr(resp, "text", "") or "").strip()
            if not text:
                return None
            um = getattr(resp, "usage_metadata", None)
            tokens = int(getattr(um, "total_token_count", 0) or 0) if um else 0
            return {"answer": text, "tokens": tokens, "model": model_name}
        except Exception as e:
            print(f"[RAG] Gemini 생성 실패: {e} — fallback")
            return None

    def query(
        self,
        question: str,
        sensor_context: dict | None = None,
        max_tokens: int = 512,
    ) -> dict:
        """질문에 대한 답변 생성.

        Returns:
            {
              "query": 원본 질문,
              "answer": 생성된 답변,
              "sources": 참고 문서 제목 목록,
              "retrieved_docs": 검색된 문서 내용,
              "mode": "llm" | "template",
            }
        """
        # 1. 문서 검색
        docs = self._index.search(question, top_k=self.top_k)
        sources = [d["title"] for d in docs]

        # 2. 프롬프트 구성
        system_prompt, user_prompt = build_rag_prompt(question, docs, sensor_context)

        # 3. LLM 생성 시도 — Gemini 우선 → Anthropic → 템플릿
        if self.use_llm:
            gem = self._gemini_generate(system_prompt, user_prompt, max_tokens)
            if gem:
                return {
                    "query": question,
                    "answer": gem["answer"],
                    "sources": sources,
                    "mode": f"llm-gemini ({gem['model']})",
                    "tokens_used": gem["tokens"],
                }

            client = self._get_client()
            if client:
                try:
                    msg = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=max_tokens,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    answer = msg.content[0].text
                    return {
                        "query": question,
                        "answer": answer,
                        "sources": sources,
                        "mode": "llm-claude",
                        "tokens_used": msg.usage.input_tokens + msg.usage.output_tokens,
                    }
                except Exception as e:
                    print(f"[RAG] LLM 생성 실패: {e} — template fallback")

        # 4. Template fallback (LLM 없거나 실패 시)
        answer = self._template_answer(question, docs)
        return {
            "query": question,
            "answer": answer,
            "sources": sources,
            "mode": "template",
            "tokens_used": 0,
        }

    def _template_answer(self, question: str, docs: list[dict]) -> str:
        """검색 문서 기반 템플릿 답변 생성."""
        if not docs:
            return "관련 정보를 찾을 수 없습니다. 국립수산과학원(1800-7030)에 문의하세요."

        top_doc = docs[0]
        content = top_doc["content"]

        # 질문 키워드 기반 요약 추출
        sentences = content.split(". ")
        relevant = [s for s in sentences if any(
            kw in s for kw in question.split()[:3]
        )]
        summary = ". ".join(relevant[:3]) if relevant else ". ".join(sentences[:3])

        refs = "\n".join(f"  - {d['title']}" for d in docs)
        return (
            f"{summary}.\n\n"
            f"[참고 문서]\n{refs}\n\n"
            "더 자세한 내용은 국립수산과학원 또는 KOEM 해양환경측정망을 참고하세요."
        )


# 싱글턴
_chain: RAGChain | None = None


def get_chain() -> RAGChain:
    global _chain
    if _chain is None:
        gemini_key = getattr(settings, "gemini_api_key", "") if settings else os.getenv("GEMINI_API_KEY", "")
        anthropic_key = (getattr(settings, "anthropic_api_key", "") if settings else "") or os.getenv("ANTHROPIC_API_KEY", "")
        _chain = RAGChain(top_k=3, use_llm=bool(gemini_key or anthropic_key))
    return _chain
