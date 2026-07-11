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

    # 센서 컨텍스트 (선택)
    sensor_ctx = None
    if req.include_sensor_context:
        from sqlalchemy import select, desc
        from app.models.sensor import OceanSensorRaw
        result = await db.execute(
            select(OceanSensorRaw).order_by(desc(OceanSensorRaw.observed_at)).limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            din = (row.no3_nitrogen or 0) + (row.nh4_nitrogen or 0)
            dip = 0.82
            raw_data = {
                "water_temp": row.water_temp,
                "dissolved_oxygen": row.dissolved_oxygen,
                "din": din,
                "dip": dip,
                "np_ratio": round(din / dip, 2) if dip else 0,
                "salinity": row.salinity,
            }
            ctx = build_llm_context(raw_data, farm_id=req.farm_id)
            sensor_ctx = {
                "farm_id": ctx["farm_id"],
                "sensor_summary": ctx["sensor_summary"],
            }

    # RAG 체인 실행
    from rag.rag_chain import get_chain
    chain = get_chain()
    result = chain.query(req.query, sensor_context=sensor_ctx, max_tokens=512)

    return RAGResponse(
        query=result["query"],
        answer=result["answer"],
        sources=result["sources"],
        mode=result["mode"],
        tokens_used=result.get("tokens_used", 0),
    )


@router.get("/docs")
async def list_docs():
    """내장 황백화 지식베이스 문서 목록 조회."""
    from rag.embedder import BUILTIN_DOCS
    return [
        {"id": d["id"], "title": d["title"], "tags": d["tags"]}
        for d in BUILTIN_DOCS
    ]


@router.get("/docs/{doc_id}")
async def get_doc(doc_id: str):
    """특정 문서 상세 내용 조회."""
    from rag.embedder import BUILTIN_DOCS
    doc = next((d for d in BUILTIN_DOCS if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail=f"문서 없음: {doc_id}")
    return doc
