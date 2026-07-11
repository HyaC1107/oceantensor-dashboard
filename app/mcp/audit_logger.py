"""Audit Logger — LLM 입출력 SHA-256 해싱 & DB 기록."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def log_llm_call(
    db: AsyncSession,
    user_id: str,
    endpoint: str,
    prompt: str,
    response: str,
    policy_action: str,
    tokens_used: int = 0,
    ip_address: str | None = None,
) -> AuditLog:
    """LLM API 호출 1건을 audit_log 테이블에 기록.

    원문 프롬프트/응답은 저장하지 않고 SHA-256 해시만 저장.
    """
    entry = AuditLog(
        logged_at=datetime.now(timezone.utc),
        user_id=user_id,
        endpoint=endpoint,
        llm_prompt_hash=_sha256(prompt),
        llm_response_hash=_sha256(response),
        policy_action=policy_action,
        tokens_used=tokens_used,
        ip_address=ip_address,
    )
    db.add(entry)
    try:
        await db.commit()
        await db.refresh(entry)
    except Exception as e:
        await db.rollback()
        print(f"[audit] DB 저장 실패: {e}")
    return entry


def log_to_file(
    log_path: str,
    user_id: str,
    endpoint: str,
    prompt: str,
    response: str,
    policy_action: str,
    tokens_used: int = 0,
):
    """DB 없이 파일로 감사 로그 기록 (Mock 모드 / 개발 환경용)."""
    entry = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "endpoint": endpoint,
        "llm_prompt_hash": _sha256(prompt),
        "llm_response_hash": _sha256(response),
        "policy_action": policy_action,
        "tokens_used": tokens_used,
    }
    try:
        import os
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[audit] 파일 저장 실패: {e}")
