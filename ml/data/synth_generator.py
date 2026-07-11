"""합성 OceanCube 생성기 — ST-MMT 파이프라인 검증용.

실데이터 확보 전, 학습 파이프라인이 끝까지 도는지(그리고 모델이 실제로
신호를 학습하는지) 확인하기 위한 **물리 모사 합성 데이터**.

핵심 설계:
    - 시공간적으로 움직이는 '스트레스 핫스팟'(적조/빈산소 패치 모사)을 만든다.
    - 16개 채널 중 일부는 핫스팟과 상관(수온 ↑, DO ↓ 등), 나머지는 distractor 노이즈.
    - 라벨 = 시간 누적(EMA) 스트레스를 분위수로 5단계 구간화.
      → 채널(공간) + 시간 누적(시간) 둘 다 봐야 풀리는 진짜 시공간 과제.
    - 분위수 구간화로 클래스 비율을 명시 제어(96% 정상 함정 회피).

반환 규격은 OceanCubeDataset 입력과 일치: cube (T,H,W,C), labels (T,H,W).
"""
from __future__ import annotations

import numpy as np
import torch


def _gaussian_field(h_grid, w_grid, cy, cx, sigma):
    """(H,W) 가우시안 봉우리. cy,cx 중심, sigma 폭."""
    return np.exp(-(((h_grid - cy) ** 2 + (w_grid - cx) ** 2) / (2.0 * sigma**2)))


def generate_ocean_cube(
    T: int = 240,
    H: int = 32,
    W: int = 32,
    C: int = 16,
    n_stages: int = 5,
    n_hotspots: int = 3,
    ema_alpha: float = 0.3,
    # 클래스 누적 비율 경계 (정상 40% / 초기 20% / 경계 18% / 진행 12% / 심각 10%)
    class_quantiles=(0.40, 0.60, 0.78, 0.90),
    noise: float = 0.4,
    seed: int = 42,
):
    """물리 모사 합성 OceanCube 생성.

    Returns:
        cube:   (T, H, W, C) float32 — 채널별 표준화됨
        labels: (T, H, W)    int64   — 0~4 황백화 단계
        meta:   dict — 클래스 분포 등
    """
    rng = np.random.default_rng(seed)
    h_grid, w_grid = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")

    # --- 움직이는 핫스팟들의 궤적/세기 ---
    centers_y = rng.uniform(4, H - 4, size=n_hotspots)
    centers_x = rng.uniform(4, W - 4, size=n_hotspots)
    vel_y = rng.uniform(-0.15, 0.15, size=n_hotspots)
    vel_x = rng.uniform(-0.15, 0.15, size=n_hotspots)
    sigmas = rng.uniform(3.5, 6.0, size=n_hotspots)
    phases = rng.uniform(0, 2 * np.pi, size=n_hotspots)
    freqs = rng.uniform(0.02, 0.06, size=n_hotspots)

    inst = np.zeros((T, H, W), dtype=np.float64)  # 순간 스트레스장
    for t in range(T):
        field = np.zeros((H, W))
        for k in range(n_hotspots):
            cy = np.clip(centers_y[k] + vel_y[k] * t, 0, H - 1)
            cx = np.clip(centers_x[k] + vel_x[k] * t, 0, W - 1)
            amp = 0.5 + 0.5 * np.sin(freqs[k] * t + phases[k])  # 0~1 진동
            field += amp * _gaussian_field(h_grid, w_grid, cy, cx, sigmas[k])
        inst[t] = field

    # --- 시간 누적(EMA) 스트레스 → 라벨 근거 ---
    accum = np.zeros_like(inst)
    accum[0] = inst[0]
    for t in range(1, T):
        accum[t] = ema_alpha * inst[t] + (1 - ema_alpha) * accum[t - 1]

    # --- 채널 구성: 일부는 신호 상관, 나머지는 distractor ---
    cube = np.zeros((T, H, W, C), dtype=np.float64)
    cube[..., 0] = inst                              # 수온 anomaly (양의 상관)
    cube[..., 1] = np.roll(inst, 1, axis=0)          # 1시점 지연 상관
    cube[..., 2] = -inst                             # 용존산소 DO (음의 상관)
    cube[..., 3] = 0.6 * inst + 0.4 * accum          # DIN 누적성
    cube[..., 4] = accum                             # N:P 비율 누적성
    for c in range(5, C):                            # distractor 채널들
        cube[..., c] = rng.normal(0, 1, size=(T, H, W))
        if c % 3 == 0:                               # 일부는 약한 상관만
            cube[..., c] += 0.2 * inst
    cube += rng.normal(0, noise, size=cube.shape)    # 관측 노이즈

    # 채널별 표준화 (zero mean / unit var)
    mean = cube.mean(axis=(0, 1, 2), keepdims=True)
    std = cube.std(axis=(0, 1, 2), keepdims=True) + 1e-6
    cube = (cube - mean) / std

    # --- 분위수 구간화로 라벨 생성 (클래스 비율 제어) ---
    thresholds = np.quantile(accum, class_quantiles)
    labels = np.digitize(accum, thresholds).astype(np.int64)  # 0..n_stages-1
    labels = np.clip(labels, 0, n_stages - 1)

    counts = np.bincount(labels.reshape(-1), minlength=n_stages)
    meta = {
        "shape": cube.shape,
        "class_counts": counts.tolist(),
        "class_ratio": (counts / counts.sum()).round(3).tolist(),
        "thresholds": thresholds.round(4).tolist(),
    }
    return (
        torch.from_numpy(cube.astype(np.float32)),
        torch.from_numpy(labels),
        meta,
    )


def make_dataset(t_in: int = 12, stride: int = 3, **gen_kwargs):
    """생성기 → OceanCubeDataset 래퍼 (편의 함수)."""
    from ml.models.st_mmt import OceanCubeDataset

    cube, labels, meta = generate_ocean_cube(**gen_kwargs)
    ds = OceanCubeDataset(cube, labels, t_in=t_in, stride=stride)
    return ds, meta
