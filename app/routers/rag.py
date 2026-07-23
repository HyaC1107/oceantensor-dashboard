"""RAG 라우터 — 황백화 지식베이스 기반 Q&A (실제 RAG 체인 연동)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.mcp.rate_limiter import rate_limiter
from app.mcp.context_filter import build_llm_context

router = APIRouter()


class RAGQuery(BaseModel):
    query: str
    top_k: int = 3
    user_id: str = "anonymous"
    farm_id: str = "A7"
    include_sensor_context: bool = False


class RAGResponse(BaseModel):
    query: str
    answer: str
    sources: list[str]
    mode: str = "template"
    tokens_used: int = 0


@router.post("/query", response_model=RAGResponse)
async def rag_query(
    req: RAGQuery,
    db: AsyncSession = Depends(get_db),
):
    """황백화 관련 질문에 대한 RAG 기반 답변.

    - Anthropic API 키 있으면 Claude Haiku로 생성
    - 없으면 내장 지식베이스 기반 템플릿 답변
    - Rate limiting: 분당 20회
    """
    # Rate limit 체크
    allowed, limit_info = rate_limiter.is_allowed(req.user_id, "/rag/query")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit 초과",
                "retry_after": limit_info.get("retry_after", 60),
            }
        )

    # 센서 컨텍스트 (선택) — "Personal RAG": 해당 어장 실측 근거로 답변 보강
    sensor_ctx = None
    if req.include_sensor_context:
        from sqlalchemy import select, desc
        from app.models.sensor import OceanSensorRaw
        result = await db.execute(
            select(OceanSensorRaw).order_by(desc(OceanSensorRaw.observed_at)).limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            # OceanSensorRaw엔 DIP(인) 컬럼 자체가 없음 — 실측 없는 값을 지어내지 않는다.
            din = (row.no3_nitrogen or 0) + (row.nh4_nitrogen or 0) if (row.no3_nitrogen is not None or row.nh4_nitrogen is not None) else None
            raw_data = {
                "water_temp": row.water_temp,
                "dissolved_oxygen": row.dissolved_oxygen,
                "din": din,
                "dip": None,  # 미측정 — build_llm_context가 "DIP 미측정"으로 표기
                "np_ratio": None,
                "salinity": row.salinity,
            }
            ctx = build_llm_context(raw_data, farm_id=req.farm_id)
            sensor_ctx = {
                "farm_id": ctx["farm_id"],
                "sensor_summary": ctx["sensor_summary"],
            }

    # RAG 체인 실행 (LangChain 리트리버 → pgvector 검색 → Gemini/Claude/템플릿)
    from rag.rag_chain import get_chain
    chain = get_chain()
    result = await chain.aquery(req.query, db, sensor_context=sensor_ctx, max_tokens=512)

    return RAGResponse(
        query=result["query"],
        answer=result["answer"],
        sources=result["sources"],
        mode=result["mode"],
        tokens_used=result.get("tokens_used", 0),
    )


@router.get("/docs")
async def list_docs(db: AsyncSession = Depends(get_db)):
    """황백화 지식베이스 문서 목록 조회 (docs/active 기술문서 + 연구자료 코퍼스)."""
    from sqlalchemy import select
    from app.models.rag_document import RAGDocument
    result = await db.execute(select(RAGDocument.doc_id, RAGDocument.title, RAGDocument.source, RAGDocument.tags))
    return [
        {"id": r.doc_id, "title": r.title, "source": r.source, "tags": r.tags or []}
        for r in result.all()
    ]


@router.get("/docs/{doc_id}")
async def get_doc(doc_id: str, db: AsyncSession = Depends(get_db)):
    """특정 문서 청크 상세 내용 조회."""
    from sqlalchemy import select
    from app.models.rag_document import RAGDocument
    result = await db.execute(select(RAGDocument).where(RAGDocument.doc_id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"문서 없음: {doc_id}")
    return {
        "id": doc.doc_id, "title": doc.title, "content": doc.content,
        "source": doc.source, "source_type": doc.source_type, "tags": doc.tags or [],
    }
