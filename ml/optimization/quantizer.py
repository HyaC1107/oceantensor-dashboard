"""INT8 Dynamic Quantization — TinyTransformer 경량화.

Edge(Jetson Orin Nano) 배포 전 정수화로 메모리·연산량 감소.
PyTorch dynamic quantization: Linear 레이어만 INT8화, 추가 캘리브레이션 불필요.
"""
from pathlib import Path

import torch
import torch.nn as nn
from torch.quantization import quantize_dynamic


def quantize_int8(
    model: nn.Module,
    save_path: str = "deploy/tiny_transformer_int8.pt",
) -> tuple[nn.Module, dict]:
    """Dynamic INT8 양자화.

    Args:
        model:     학습 완료된 TinyTransformer (eval 모드)
        save_path: 양자화 모델 저장 경로

    Returns:
        (quantized_model, size_info)
    """
    model.eval()
    model.cpu()

    quantized = quantize_dynamic(
        model,
        {nn.Linear},
        dtype=torch.qint8,
    )

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(quantized.state_dict(), save_path)

    orig_size = _model_size_mb(model)
    quant_size = _model_size_mb(quantized)
    ratio = orig_size / quant_size if quant_size > 0 else float("nan")

    info = {
        "original_mb": round(orig_size, 2),
        "quantized_mb": round(quant_size, 2),
        "compression_ratio": round(ratio, 2),
        "save_path": save_path,
    }
    print(
        f"  INT8 양자화 완료: {orig_size:.1f} MB → {quant_size:.1f} MB "
        f"(x{ratio:.1f} 압축)"
    )
    return quantized, info


def _model_size_mb(model: nn.Module) -> float:
    """모델 파라미터 메모리 크기 (MB)."""
    param_size = sum(p.nelement() * p.element_size() for p in model.parameters())
    buffer_size = sum(b.nelement() * b.element_size() for b in model.buffers())
    return (param_size + buffer_size) / 1024 / 1024


def compare_accuracy(
    original: nn.Module,
    quantized: nn.Module,
    sensor_dim: int = 8,
    t_in: int = 24,
    n_samples: int = 100,
) -> dict:
    """원본 vs 양자화 모델 출력 차이 측정."""
    import numpy as np

    original.eval()
    quantized.eval()
    diffs = []

    with torch.no_grad():
        for _ in range(n_samples):
            x = torch.randn(1, t_in, sensor_dim)
            out_orig = original(x)["anomaly_score"].item()
            out_quant = quantized(x)["anomaly_score"].item()
            diffs.append(abs(out_orig - out_quant))

    return {
        "mean_diff": round(float(np.mean(diffs)), 5),
        "max_diff": round(float(np.max(diffs)), 5),
        "p95_diff": round(float(np.percentile(diffs, 95)), 5),
    }
