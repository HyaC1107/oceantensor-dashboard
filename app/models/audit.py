from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.sql import func
from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    logged_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_id = Column(String(50), nullable=False)
    endpoint = Column(String(100))
    llm_prompt_hash = Column(String(64))
    llm_response_hash = Column(String(64))
    policy_action = Column(String(30))  # allow / block / filtered
    tokens_used = Column(Integer)
    ip_address = Column(INET)
