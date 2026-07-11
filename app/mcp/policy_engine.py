"""MCP Policy Engine — LLM 데이터 접근 정책 & 민감정보 보호."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    FILTER = "filtered"


@dataclass
class PolicyResult:
    action: PolicyAction
    reason: str
    payload: dict | None = None
    removed_fields: list[str] = field(default_factory=list)
    risk_level: str = "low"  # low | medium | high


class MCPPolicyEngine:
    """어가 데이터 보호를 위한 LLM 접근 정책 엔진.

    원칙:
    - RAW 센서 데이터 직접 노출 금지
    - 개인식별정보(어가명, 정밀좌표, IP) 익명화
    - 집계(시간평균) 수치 데이터만 LLM 컨텍스트에 허용
    - 예측/알람 결과는 허용 (개인정보 없음)
    """

    # 완전 차단 요청 유형
    BLOCKED_REQUEST_TYPES = frozenset({
        "raw_sensor",      # 원시 IoT 센서 RAW 스트림
        "personal_info",   # 어가 개인정보 직접 조회
        "farm_pii",        # 양식장 주소·연락처
    })

    # 필터링할 개인정보 필드
    PII_FIELDS = frozenset({
        "owner_name", "owner_phone", "owner_email",
        "ip_address", "exact_geom", "address",
        "account_no", "registration_no",
    })

    # LLM에 노출 허용된 집계 필드 (화이트리스트)
    ALLOWED_AGGREGATE_FIELDS = frozenset({
        "water_temp", "dissolved_oxygen", "din", "dip",
        "np_ratio", "salinity", "wbi_score", "severity",
        "anomaly_score", "severity_pct", "farm_id",
        "observed_at", "predicted_at", "stage",
        "chlorophyll_a", "precipitation", "top_causes",
        "attention_map_json", "model_version",
    })

    def evaluate(self, request_type: str, data: dict) -> PolicyResult:
        """데이터 접근 요청 평가.

        Args:
            request_type: 요청 유형 문자열
            data:         전달할 데이터 dict

        Returns:
            PolicyResult (action, reason, payload, removed_fields)
        """
        # 1. 완전 차단
        if request_type in self.BLOCKED_REQUEST_TYPES:
            return PolicyResult(
                action=PolicyAction.BLOCK,
                reason=f"'{request_type}' 접근은 MCP 정책에 의해 차단됩니다.",
                risk_level="high",
            )

        # 2. PII 필터링
        filtered = {}
        removed = []
        for k, v in data.items():
            if k in self.PII_FIELDS:
                removed.append(k)
            else:
                filtered[k] = v

        # 3. 화이트리스트 밖 필드 추가 필터 (집계 데이터 전용 요청)
        if request_type == "llm_context":
            extra_removed = [k for k in filtered if k not in self.ALLOWED_AGGREGATE_FIELDS]
            for k in extra_removed:
                removed.append(k)
                del filtered[k]

        if removed:
            return PolicyResult(
                action=PolicyAction.FILTER,
                reason=f"민감 필드 {len(removed)}개 제거됨",
                payload=filtered,
                removed_fields=removed,
                risk_level="medium" if len(removed) > 2 else "low",
            )

        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason="정책 통과 — 모든 필드 허용",
            payload=data,
            risk_level="low",
        )

    def anonymize_farm_id(self, farm_id: str) -> str:
        """양식장 ID를 단방향 해시로 익명화."""
        import hashlib
        return "FARM_" + hashlib.sha256(farm_id.encode()).hexdigest()[:8].upper()


# 싱글턴
policy_engine = MCPPolicyEngine()
