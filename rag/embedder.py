"""문서 임베딩 — 황백화 관련 해양과학 문서를 벡터화해 인덱스 구축.

sentence-transformers 없는 환경에서는 TF-IDF fallback 사용.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np


# 황백화 관련 기초 지식베이스 (항상 사용 가능)
BUILTIN_DOCS: list[dict] = [
    {
        "id": "hw_001",
        "title": "황백화 정의 및 발생 원인",
        "content": (
            "황백화(白化, Hwangbaekwha)는 양식 김(방사무늬김)에서 발생하는 생리장애로, "
            "엽체가 황색 또는 백색으로 변색되어 상품성을 잃는 현상이다. "
            "주요 원인: (1) DIN(용존무기질소) 5 μmol/L 이하 시 질소 결핍, "
            "(2) 수온 25℃ 초과 시 고온 스트레스, "
            "(3) N:P 비율 10 이하 시 영양염 불균형, "
            "(4) DO(용존산소) 5 mg/L 이하 시 저산소 스트레스. "
            "발생 시기: 통상 11월~2월 양식 성수기에 집중."
        ),
        "tags": ["황백화", "정의", "원인", "din", "수온"],
    },
    {
        "id": "hw_002",
        "title": "DIN과 황백화 임계치",
        "content": (
            "DIN(Dissolved Inorganic Nitrogen)은 NO3-N + NO2-N + NH4-N의 합으로 "
            "황백화 예측에서 가중치 0.38로 1순위 변수다. "
            "임계치: DIN < 5 μmol/L에서 황백화 발생 위험이 급격히 증가. "
            "DIN < 3 μmol/L이면 심각 단계. "
            "대응: 유기질 비료 투입, 조류 식물 제거, 외부 수계 유입 차단."
        ),
        "tags": ["din", "임계치", "황백화", "질소", "예측"],
    },
    {
        "id": "hw_003",
        "title": "수온 영향 및 관리",
        "content": (
            "수온이 황백화에 미치는 영향: 25℃ 초과 시 광합성 효율 감소, "
            "호흡 소비 증가로 DIN 고갈 가속. "
            "황백화 지수(WBI) 공식에서 수온 위험지수 = max(0, (수온 - 20) / 10). "
            "완도 지역 기준: 1~2월 평균 수온 8~12℃, 황백화 발생 수온 임계치 15℃ 초과. "
            "모니터링 주기: NIFS 수온 실시간 관측소 1시간 단위 수집."
        ),
        "tags": ["수온", "황백화", "광합성", "완도", "nifs"],
    },
    {
        "id": "hw_004",
        "title": "N:P 비율과 영양염 균형",
        "content": (
            "레드필드 비율(Redfield Ratio) N:P = 16:1이 해양 생물의 기준. "
            "김 양식에서 N:P < 10이면 질소 상대적 결핍 → 황백화 유발. "
            "DIP(Dissolved Inorganic Phosphorus) 과잉 시 N:P 감소. "
            "KOEM 해양환경측정망에서 DIN, DIP 월 1회 측정. "
            "이상감지 임계: N:P < 10 → CAUTION, N:P < 5 → WARNING."
        ),
        "tags": ["np비율", "영양염", "din", "dip", "레드필드", "koem"],
    },
    {
        "id": "hw_005",
        "title": "황백화 단계 분류 기준",
        "content": (
            "황백화 5단계 분류: "
            "0단계(정상): WBI < 0.2, 엽체 정상 녹색. "
            "1단계(초기): 0.2 ≤ WBI < 0.4, 엽체 일부 황색 반점. "
            "2단계(경계): 0.4 ≤ WBI < 0.6, 엽체 30% 이상 변색. "
            "3단계(진행): 0.6 ≤ WBI < 0.8, 엽체 60% 이상 변색, 즉각 조치 필요. "
            "4단계(심각): WBI ≥ 0.8, 상품성 불가, 조기 수확 검토."
        ),
        "tags": ["단계", "분류", "wbi", "황백화", "기준"],
    },
    {
        "id": "hw_006",
        "title": "ST-MMT 모델 개요",
        "content": (
            "어텐션플리즈(ATTENTIONPLZ) 시스템의 핵심 AI 모델. "
            "ST-MMT(Spatio-Temporal Multi-Modal Transformer): "
            "Ocean Tensor Cube [T=72h, H=64, W=64, C=16채널] 입력, "
            "1.63M 파라미터, 공간×시간 attention으로 황백화 확산 패턴 예측. "
            "TinyTransformer: Jetson Orin Nano 엣지 배포용 경량 모델, "
            "센서 시계열 (T=24h, C=8) 입력, ~2M 파라미터, <30ms 추론."
        ),
        "tags": ["st-mmt", "tiny-transformer", "ai", "모델", "엣지"],
    },
    {
        "id": "hw_007",
        "title": "대응 방안 및 예방",
        "content": (
            "황백화 예방 및 대응 방안: "
            "(1) 조기경보: WBI > 0.5 시 SMS/앱 알림 발송. "
            "(2) 조류 관리: DIN 저하 시 식물플랑크톤 번성 억제. "
            "(3) 수확 시기 조정: 3단계 이상 시 조기 수확 검토. "
            "(4) 시설 이동: 수온 상승 지역 외 이동식 시설 활용. "
            "(5) 영양염 보충: 법적 허용 범위 내 유기물 투입. "
            "문의: 국립수산과학원 서해수산연구소 (041-400-5700)."
        ),
        "tags": ["대응", "예방", "조기경보", "수확", "관리"],
    },
    {
        "id": "hw_008",
        "title": "공공 API 데이터 소스",
        "content": (
            "어텐션플리즈 시스템 데이터 수집 소스: "
            "NIFS(국립수산과학원): 수온/염분/DO 실시간 부이 (femoSeaList, risaList), "
            "KOEM(해양환경공단): DIN/DIP/클로로필-a 측정망 (OceanEnviron API), "
            "KMA(기상청): 강수량/풍속/풍향 ASOS 관측 (1시간 주기), "
            "K-water: 댐 수문 운영 정보 (육상 오염 유입 지표), "
            "Sentinel-2: 위성 클로로필-a (10m 해상도, 5일 주기)."
        ),
        "tags": ["api", "nifs", "koem", "kma", "k-water", "sentinel"],
    },
]


class SimpleRAGIndex:
    """TF-IDF 기반 간단한 문서 검색 인덱스.

    sentence-transformers 없이도 동작하는 fallback 구현.
    """

    def __init__(self):
        self._docs: list[dict] = []
        self._tfidf_matrix: np.ndarray | None = None
        self._vectorizer = None

    def build(self, docs: list[dict]):
        """문서 목록으로 인덱스 구축."""
        self._docs = docs
        texts = [d["title"] + " " + d["content"] for d in docs]

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._vectorizer = TfidfVectorizer(
                analyzer="char_wb", ngram_range=(2, 3), max_features=5000
            )
            self._tfidf_matrix = self._vectorizer.fit_transform(texts).toarray()
        except ImportError:
            self._tfidf_matrix = None

        return self

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """쿼리와 가장 유사한 문서 top_k개 반환."""
        if self._tfidf_matrix is None or self._vectorizer is None:
            return self._keyword_search(query, top_k)

        q_vec = self._vectorizer.transform([query]).toarray()
        scores = self._tfidf_matrix @ q_vec.T  # cosine 유사도 근사
        ranked = np.argsort(scores.flatten())[::-1][:top_k]
        return [self._docs[i] for i in ranked]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        """fallback: 태그 & 키워드 매칭."""
        query_lower = query.lower()
        scored = []
        for doc in self._docs:
            score = 0
            for tag in doc.get("tags", []):
                if tag in query_lower:
                    score += 2
            for word in query_lower.split():
                if word in doc["content"].lower():
                    score += 1
            scored.append((score, doc))
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored[:top_k]]


# 전역 인덱스 (서버 시작 시 1회 구축)
_index: SimpleRAGIndex | None = None


def get_index() -> SimpleRAGIndex:
    global _index
    if _index is None:
        _index = SimpleRAGIndex().build(BUILTIN_DOCS)
    return _index
