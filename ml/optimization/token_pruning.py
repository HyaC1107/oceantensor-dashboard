"""Token Pruning 유틸리티 — 추론 시 k_ratio 동적 조정.

Edge 디바이스에서 부하에 따라 pruning 비율을 실시간으로 변경해
지연시간 vs 정확도 트레이드오프를 제어.
"""
import time
from dataclasses import dataclass, field

import torch
import torch.nn as nn


@dataclass
class PruningConfig:
    """Pruning 정책 설정."""
    mode: str = "fixed"         # "fixed" | "adaptive"
    k_ratio: float = 0.3        # fixed 모드: 고정 비율
    latency_target_ms: float = 30.0  # adaptive 모드: 목표 지연시간
    k_min: float = 0.1          # 최소 유지 비율
    k_max: float = 1.0          # 최대 유지 비율 (no pruning)
    history_len: int = 20       # 지연시간 이동평균 윈도우


class AdaptiveTokenPruner:
    """추론 지연시간에 따라 k_ratio를 동적으로 조정.

    지연시간이 목표보다 크면 → k_ratio 감소 (더 많이 pruning)
    지연시간이 목표보다 작으면 → k_ratio 증가 (정확도 회복)
    """

    def __init__(self, config: PruningConfig | None = None):
        self.cfg = config or PruningConfig()
        self._k_ratio = self.cfg.k_ratio
        self._latency_history: list[float] = []

    @property
    def k_ratio(self) -> float:
        return self._k_ratio

    def update(self, latency_ms: float):
        """추론 후 지연시간을 보고해 다음 k_ratio를 업데이트."""
        if self.cfg.mode != "adaptive":
            return

        self._latency_history.append(latency_ms)
        if len(self._latency_history) > self.cfg.history_len:
            self._latency_history.pop(0)

        avg_latency = sum(self._latency_history) / len(self._latency_history)
        target = self.cfg.latency_target_ms

        if avg_latency > target * 1.1:
            # 지연 초과 → pruning 강화
            self._k_ratio = max(self.cfg.k_min, self._k_ratio - 0.05)
        elif avg_latency < target * 0.85:
            # 여유 있음 → pruning 완화
            self._k_ratio = min(self.cfg.k_max, self._k_ratio + 0.02)

    def __repr__(self) -> str:
        avg = (sum(self._latency_history) / len(self._latency_history)
               if self._latency_history else 0.0)
        return (
            f"AdaptiveTokenPruner(k_ratio={self._k_ratio:.2f}, "
            f"avg_latency={avg:.1f}ms, mode={self.cfg.mode})"
        )


def timed_inference(
    model: nn.Module,
    sensor_seq: torch.Tensor,
    pruner: AdaptiveTokenPruner,
    img: torch.Tensor | None = None,
) -> tuple[dict, float]:
    """Pruner를 사용한 시간 측정 추론.

    Args:
        model:      TinyTransformer
        sensor_seq: (B, T, C)
        pruner:     AdaptiveTokenPruner
        img:        (B, 3, H, W) or None

    Returns:
        (model_output, latency_ms)
    """
    # k_ratio를 TokenScorer에 주입
    if hasattr(model, "token_scorer"):
        original_k = model.k_ratio
        model.k_ratio = pruner.k_ratio

    t0 = time.perf_counter()
    with torch.no_grad():
        output = model(sensor_seq, img)
    latency_ms = (time.perf_counter() - t0) * 1000

    if hasattr(model, "token_scorer"):
        model.k_ratio = original_k

    pruner.update(latency_ms)
    return output, latency_ms


def analyze_pruning_impact(
    model: nn.Module,
    sensor_dim: int = 8,
    t_in: int = 24,
    k_ratios: list[float] | None = None,
    n_runs: int = 50,
) -> list[dict]:
    """다양한 k_ratio에서 지연시간 vs 정확도 분석.

    Returns:
        list of {k_ratio, mean_latency_ms, score_mean, score_std}
    """
    import numpy as np

    ratios = k_ratios or [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
    results = []

    for k in ratios:
        original_k = getattr(model, "k_ratio", 0.3)
        model.k_ratio = k
        model.eval()

        latencies = []
        scores = []
        with torch.no_grad():
            for _ in range(n_runs):
                x = torch.randn(1, t_in, sensor_dim)
                t0 = time.perf_counter()
                out = model(x)
                latencies.append((time.perf_counter() - t0) * 1000)
                scores.append(out["anomaly_score"].item())

        results.append({
            "k_ratio": k,
            "mean_latency_ms": round(float(np.mean(latencies)), 2),
            "score_mean": round(float(np.mean(scores)), 4),
            "score_std": round(float(np.std(scores)), 4),
        })
        model.k_ratio = original_k

    return results
