from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, BigInteger, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db import Base

EMBEDDING_DIM = 768  # jhgan/ko-sroberta-multitask 출력 차원


class RAGDocument(Base):
    __tablename__ = "rag_documents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doc_id = Column(String(20), unique=True, nullable=False)  # corpus.json의 id (재빌드 시 upsert 키)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(255))
    source_type = Column(String(30))
    tags = Column(JSONB, server_default="[]")
    embedding = Column(Vector(EMBEDDING_DIM))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
