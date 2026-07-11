"""Rate Limiter — LLM API 호출 빈도 제한 (메모리 기반, Redis 없어도 동작)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateLimit:
    requests: int    # 허용 요청 수
    window_s: int    # 시간 윈도우 (초)


# 기본 정책 — 엔드포인트별 제한
DEFAULT_LIMITS: dict[str, RateLimit] = {
    "/rag/query":    RateLimit(requests=20, window_s=60),   # 분당 20회
    "/predict":      RateLimit(requests=60, window_s=60),   # 분당 60회
    "/explain":      RateLimit(requests=30, window_s=60),   # 분당 30회
    "default":       RateLimit(requests=100, window_s=60),  # 기본
}


class InMemoryRateLimiter:
    """슬라이딩 윈도우 방식 메모리 기반 Rate Limiter.

    Redis 없이도 동작 — 단일 프로세스에서 유효.
    멀티 인스턴스 환경에서는 Redis 기반으로 교체 필요.
    """

    def __init__(self, limits: dict[str, RateLimit] | None = None):
        self._limits = limits or DEFAULT_LIMITS
        # {(user_id, endpoint): deque[timestamp]}
        self._windows: dict[tuple[str, str], deque] = defaultdict(deque)

    def is_allowed(self, user_id: str, endpoint: str) -> tuple[bool, dict]:
        """Rate limit 체크.

        Returns:
            (allowed: bool, info: dict)
        """
        limit = self._limits.get(endpoint) or self._limits["default"]
        now = time.time()
        key = (user_id, endpoint)
        window = self._windows[key]

        # 만료된 항목 제거
        cutoff = now - limit.window_s
        while window and window[0] < cutoff:
            window.popleft()

        remaining = limit.requests - len(window)
        reset_at = int((window[0] + limit.window_s) if window else now + limit.window_s)

        if remaining <= 0:
            return False, {
                "allowed": False,
                "limit": limit.requests,
                "remaining": 0,
                "reset_at": reset_at,
                "retry_after": max(0, reset_at - int(now)),
            }

        window.append(now)
        return True, {
            "allowed": True,
            "limit": limit.requests,
            "remaining": remaining - 1,
            "reset_at": reset_at,
        }

    def get_usage(self, user_id: str, endpoint: str) -> dict:
        """현재 사용량 조회."""
        limit = self._limits.get(endpoint) or self._limits["default"]
        now = time.time()
        key = (user_id, endpoint)
        window = self._windows[key]
        cutoff = now - limit.window_s
        current = sum(1 for t in window if t >= cutoff)
        return {
            "user_id": user_id,
            "endpoint": endpoint,
            "current_requests": current,
            "limit": limit.requests,
            "window_s": limit.window_s,
            "remaining": max(0, limit.requests - current),
        }


# 싱글턴
rate_limiter = InMemoryRateLimiter()
