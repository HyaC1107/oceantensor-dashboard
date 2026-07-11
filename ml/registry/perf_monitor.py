"""Performance Monitor — 운영 중 모델 성능 추적 & 드리프트 탐지.

실시간 추론 결과를 sliding window로 집계하고
예측 분포 변화(데이터 드리프트)를 감지한다.
"""
from __future__ import annotations

import json
import statistics
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


class PerfMonitor:
    """모델 추론 성능 & 예측 분포 실시간 모니터링.

    Args:
        window_size: 슬라이딩 윈도우 크기 (추론 횟수)
        drift_threshold: KL divergence 드리프트 임계값
        log_path: 성능 로그 저장 경로
    """

    def __init__(
        self,
        window_size: int = 200,
        drift_threshold: float = 0.3,
        log_path: str = "logs/perf_monitor.jsonl",
    ):
        self.window_size = window_size
        self.drift_threshold = drift_threshold
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Sliding windows
        self._latencies: deque[float] = deque(maxlen=window_size)
        self._scores: deque[float] = deque(maxlen=window_size)
        self._stages: deque[int] = deque(maxlen=window_size)

        # 기준 분포 (학습 시 캘리브레이션)
        self._baseline_stage_dist: list[float] | None = None

        self._total_inferences = 0
        self._drift_alerts = 0

    def record(
        self,
        latency_ms: float,
        anomaly_score: float,
        stage: int,
        farm_id: str = "unknown",
    ) -> dict:
        """추론 결과 1건 기록.

        Returns:
            현재 윈도우 통계 + 드리프트 여부
        """
        self._latencies.append(latency_ms)
        self._scores.append(anomaly_score)
        self._stages.append(stage)
        self._total_inferences += 1

        stats = self.get_stats()
        drift = self._check_drift()
        if drift["is_drift"]:
            self._drift_alerts += 1

        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "farm_id": farm_id,
            "latency_ms": round(latency_ms, 2),
            "anomaly_score": round(anomaly_score, 4),
            "stage": stage,
            "drift": drift,
        }
        self._append_log(log_entry)

        return {**stats, "drift": drift}

    def get_stats(self) -> dict:
        """현재 윈도우 집계 통계."""
        if not self._latencies:
            return {}

        lats = list(self._latencies)
        scores = list(self._scores)

        return {
            "n": len(lats),
            "total_inferences": self._total_inferences,
            "latency": {
                "mean_ms": round(statistics.mean(lats), 2),
                "p50_ms": round(self._percentile(lats, 50), 2),
                "p95_ms": round(self._percentile(lats, 95), 2),
                "p99_ms": round(self._percentile(lats, 99), 2),
            },
            "anomaly_score": {
                "mean": round(statistics.mean(scores), 4),
                "stdev": round(statistics.stdev(scores) if len(scores) > 1 else 0.0, 4),
                "min": round(min(scores), 4),
                "max": round(max(scores), 4),
            },
            "stage_distribution": self._stage_dist(),
            "drift_alerts": self._drift_alerts,
        }

    def set_baseline(self, stage_distribution: list[float]):
        """기준 단계 분포 설정 (학습 데이터 기반).

        Args:
            stage_distribution: 단계별 비율 [정상, 초기, 경계, 진행, 심각]
                                 합계 = 1.0
        """
        assert abs(sum(stage_distribution) - 1.0) < 1e-6
        self._baseline_stage_dist = stage_distribution
        print(f"  [PerfMonitor] 기준 분포 설정: {stage_distribution}")

    def _stage_dist(self) -> list[float]:
        """현재 윈도우의 단계별 분포."""
        if not self._stages:
            return [0.0] * 5
        n = len(self._stages)
        return [round(self._stages.count(i) / n, 4) for i in range(5)]

    def _check_drift(self) -> dict:
        """현재 분포와 기준 분포 간 KL divergence로 드리프트 탐지."""
        if self._baseline_stage_dist is None or len(self._stages) < 30:
            return {"is_drift": False, "kl_div": None, "method": "insufficient_data"}

        current = self._stage_dist()
        baseline = self._baseline_stage_dist
        eps = 1e-8

        kl = sum(
            c * (c / (b + eps) + eps)
            for c, b in zip(current, baseline)
            if c > 0
        )
        kl_approx = abs(kl - 1.0)  # 정규화된 근사치

        is_drift = kl_approx > self.drift_threshold
        return {
            "is_drift": is_drift,
            "kl_div": round(kl_approx, 4),
            "threshold": self.drift_threshold,
            "current_dist": current,
            "baseline_dist": baseline,
            "method": "kl_divergence",
        }

    def _append_log(self, entry: dict):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 로그 실패는 추론 흐름에 영향 없어야 함

    @staticmethod
    def _percentile(data: list[float], p: int) -> float:
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        return sorted_data[min(idx, len(sorted_data) - 1)]

    def reset_window(self):
        self._latencies.clear()
        self._scores.clear()
        self._stages.clear()

    def summary(self) -> str:
        stats = self.get_stats()
        if not stats:
            return "데이터 없음"
        lat = stats["latency"]
        sc = stats["anomaly_score"]
        return (
            f"추론 {stats['total_inferences']}회 | "
            f"지연: mean={lat['mean_ms']}ms p95={lat['p95_ms']}ms | "
            f"WBI: mean={sc['mean']:.3f} | "
            f"드리프트 경보: {stats['drift_alerts']}회"
        )
