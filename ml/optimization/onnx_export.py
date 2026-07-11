"""ONNX Export — TinyTransformer → ONNX → Jetson Orin Nano 배포.

Usage:
    from ml.optimization.onnx_export import export_tiny_transformer
    export_tiny_transformer("checkpoints/best_model.pt", "deploy/tiny_transformer.onnx")
"""
from pathlib import Path

import torch
import torch.nn as nn


def export_tiny_transformer(
    model_or_path: str | nn.Module,
    output_path: str = "deploy/tiny_transformer.onnx",
    sensor_dim: int = 8,
    t_in: int = 24,
    opset: int = 17,
    dynamic_batch: bool = True,
) -> str:
    """TinyTransformer를 ONNX로 변환.

    Args:
        model_or_path: 학습된 모델 객체 또는 .pt 파일 경로
        output_path:   출력 .onnx 파일 경로
        sensor_dim:    입력 센서 채널 수
        t_in:          입력 타임스텝 수
        opset:         ONNX opset 버전
        dynamic_batch: True면 배치 차원을 동적으로 설정

    Returns:
        output_path
    """
    from ml.models.tiny_transformer import TinyTransformer

    if isinstance(model_or_path, str):
        model = TinyTransformer(sensor_dim=sensor_dim)
        state = torch.load(model_or_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
    else:
        model = model_or_path

    model.eval()

    dummy_sensor = torch.randn(1, t_in, sensor_dim)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    dynamic_axes = {}
    if dynamic_batch:
        dynamic_axes = {
            "sensor_seq": {0: "batch"},
            "anomaly_score": {0: "batch"},
            "severity_pct": {0: "batch"},
            "stage_logits": {0: "batch"},
        }

    # ONNX export — TinyTransformer forward를 센서 입력만으로 trace
    class _ExportWrapper(nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, sensor_seq):
            out = self.m(sensor_seq, img=None)
            return out["anomaly_score"], out["severity_pct"], out["stage_logits"]

    wrapper = _ExportWrapper(model)
    wrapper.eval()

    torch.onnx.export(
        wrapper,
        dummy_sensor,
        output_path,
        input_names=["sensor_seq"],
        output_names=["anomaly_score", "severity_pct", "stage_logits"],
        dynamic_axes=dynamic_axes if dynamic_batch else None,
        opset_version=opset,
        do_constant_folding=True,
    )

    print(f"  ONNX 변환 완료: {output_path}")
    _validate_onnx(output_path, dummy_sensor)
    return output_path


def _validate_onnx(onnx_path: str, dummy_input: torch.Tensor):
    """ONNX 모델 유효성 검증."""
    try:
        import onnx
        model_onnx = onnx.load(onnx_path)
        onnx.checker.check_model(model_onnx)
        size_mb = Path(onnx_path).stat().st_size / 1024 / 1024
        print(f"  ONNX 검증 통과 | 크기: {size_mb:.1f} MB")
    except ImportError:
        print("  onnx 패키지 없음 — 검증 생략")
    except Exception as e:
        print(f"  ONNX 검증 실패: {e}")


def benchmark_onnx(
    onnx_path: str,
    sensor_dim: int = 8,
    t_in: int = 24,
    n_runs: int = 100,
) -> dict:
    """ONNX Runtime 추론 속도 벤치마크."""
    import time
    import numpy as np

    try:
        import onnxruntime as ort
    except ImportError:
        return {"error": "onnxruntime not installed"}

    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    dummy = np.random.randn(1, t_in, sensor_dim).astype(np.float32)
    input_name = sess.get_inputs()[0].name

    # warmup
    for _ in range(10):
        sess.run(None, {input_name: dummy})

    latencies = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        sess.run(None, {input_name: dummy})
        latencies.append((time.perf_counter() - t0) * 1000)

    return {
        "mean_ms": round(float(np.mean(latencies)), 2),
        "p95_ms": round(float(np.percentile(latencies, 95)), 2),
        "min_ms": round(float(np.min(latencies)), 2),
    }
