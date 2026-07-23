"""pgvector 기반 문서 검색 — sentence-transformers 임베딩 + LangChain 리트리버.

기획서(디렉토리_데이터모델링_소스코드_어텐션플리즈.md) 스펙:
  embedder.py(sentence-transformers) + pgvector + LangChain 리트리버.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_document import RAGDocument

EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"  # 한국어 특화, 768차원
CORPUS_PATH = Path(__file__).parent / "docs" / "corpus.json"

_embedder: HuggingFaceEmbeddings | None = None


def get_embedder() -> HuggingFaceEmbeddings:
    """전역 임베딩 모델 (CPU, 최초 호출 시 1회 다운로드/로드)."""
    global _embedder
    if _embedder is None:
        _embedder = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},  # 코사인 유사도 = 내적
        )
    return _embedder


async def build_index(session: AsyncSession, batch_size: int = 32) -> int:
    """corpus.json → 임베딩 → rag_documents 테이블 upsert. 반환값 = 처리 청크 수."""
    docs: list[dict[str, Any]] = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    embedder = get_embedder()

    n = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        texts = [f"{d['title']}\n{d['content']}" for d in batch]
        vectors = embedder.embed_documents(texts)

        for d, vec in zip(batch, vectors):
            stmt = pg_insert(RAGDocument).values(
                doc_id=d["id"],
                title=d["title"],
                content=d["content"],
                source=d.get("source"),
                source_type=d.get("source_type"),
                tags=d.get("tags", []),
                embedding=vec,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["doc_id"],
                set_={
                    "title": stmt.excluded.title,
                    "content": stmt.excluded.content,
                    "source": stmt.excluded.source,
                    "source_type": stmt.excluded.source_type,
                    "tags": stmt.excluded.tags,
                    "embedding": stmt.excluded.embedding,
                },
            )
            await session.execute(stmt)
        n += len(batch)
        print(f"  [rag] 인덱싱 {n}/{len(docs)}")

    await session.commit()
    return n


class HwangbaekRetriever(BaseRetriever):
    """rag_documents 테이블(pgvector)에서 코사인 유사도 검색."""

    session: AsyncSession
    top_k: int = 3

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        raise NotImplementedError("동기 경로 미지원 — ainvoke()로 호출할 것 (앱 전체가 async)")

    async def _aget_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        """DB 연결 실패 시 예외를 던지지 않고 빈 리스트 반환 — RAG 전체가 죽지 않고
        '문서 없음' 경로로 자연 강등되게 한다(LLM은 일반지식으로, 템플릿은 안내문으로)."""
        try:
            embedder = get_embedder()
            q_vec = embedder.embed_query(query)

            stmt = (
                select(RAGDocument)
                .order_by(RAGDocument.embedding.cosine_distance(q_vec))
                .limit(self.top_k)
            )
            result = await self.session.execute(stmt)
            rows = result.scalars().all()
        except Exception as e:
            print(f"[RAG] 문서 검색 실패(DB 연결 문제 등) — 문서 없이 진행: {e}")
            return []

        return [
            Document(
                page_content=r.content,
                metadata={
                    "id": r.doc_id,
                    "title": r.title,
                    "source": r.source,
                    "source_type": r.source_type,
                    "tags": r.tags or [],
                },
            )
            for r in rows
        ]
