"""TensorRT 최적화 — Jetson Orin Nano용 엔진 빌드 가이드 + 래퍼.

실제 TensorRT 빌드는 Jetson 디바이스에서 실행.
이 모듈은: (1) 빌드 커맨드 생성, (2) TRT 엔진 추론 래퍼 제공.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def build_tensorrt_command(
    onnx_path: str,
    engine_path: str = "deploy/tiny_transformer.trt",
    fp16: bool = True,
    int8: bool = False,
    workspace_mb: int = 512,
) -> str:
    """Jetson에서 실행할 trtexec 커맨드 문자열 생성.

    Args:
        onnx_path:    변환할 ONNX 모델 경로
        engine_path:  출력 TRT 엔진 경로
        fp16:         FP16 모드 활성화 (Jetson Orin 지원)
        int8:         INT8 모드 (캘리브레이션 필요)
        workspace_mb: TensorRT 빌드 작업 메모리 (MB)

    Returns:
        실행 가능한 trtexec 커맨드 문자열
    """
    cmd = [
        "trtexec",
        f"--onnx={onnx_path}",
        f"--saveEngine={engine_path}",
        f"--workspace={workspace_mb}",
        "--verbose",
    ]
    if fp16:
        cmd.append("--fp16")
    if int8:
        cmd.append("--int8")

    return " ".join(cmd)


def run_trtexec(
    onnx_path: str,
    engine_path: str = "deploy/tiny_transformer.trt",
    fp16: bool = True,
) -> dict:
    """trtexec를 실행해 TRT 엔진 빌드 (Jetson에서만 동작).

    Returns:
        {"success": bool, "engine_path": str, "error": str|None}
    """
    cmd = build_tensorrt_command(onnx_path, engine_path, fp16=fp16)
    Path(engine_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            size_mb = Path(engine_path).stat().st_size / 1024 / 1024
            return {
                "success": True,
                "engine_path": engine_path,
                "size_mb": round(size_mb, 1),
                "error": None,
            }
        return {"success": False, "engine_path": None, "error": result.stderr[-500:]}
    except FileNotFoundError:
        return {
            "success": False,
            "engine_path": None,
            "error": "trtexec not found. Run this on Jetson Orin Nano.",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "engine_path": None, "error": "Build timeout (>5min)"}


class TRTInferenceEngine:
    """TensorRT 엔진 래퍼 — Jetson Orin Nano 추론 인터페이스.

    실제 tensorrt 패키지가 없는 환경에서는 ImportError를 graceful하게 처리.
    """

    def __init__(self, engine_path: str):
        self.engine_path = engine_path
        self._engine = None
        self._loaded = False

    def load(self) -> bool:
        """엔진 로드. 실패 시 False 반환 (graceful fallback)."""
        try:
            import tensorrt as trt
            import pycuda.driver as cuda
            import pycuda.autoinit  # noqa

            logger = trt.Logger(trt.Logger.WARNING)
            with open(self.engine_path, "rb") as f, trt.Runtime(logger) as rt:
                self._engine = rt.deserialize_cuda_engine(f.read())
            self._loaded = True
            return True
        except (ImportError, Exception) as e:
            print(f"  TRT 엔진 로드 실패 (비 Jetson 환경): {e}")
            return False

    def infer(self, sensor_np) -> dict | None:
        """TRT 엔진으로 추론. 로드 안 됐으면 None 반환."""
        if not self._loaded:
            return None
        try:
            import numpy as np
            import pycuda.driver as cuda

            context = self._engine.create_execution_context()
            # 입력/출력 버퍼 할당
            bindings = []
            for i in range(self._engine.num_bindings):
                shape = self._engine.get_binding_shape(i)
                size = int(np.prod(shape)) * np.float32().itemsize
                buf = cuda.mem_alloc(size)
                bindings.append(int(buf))

            # 입력 복사
            cuda.memcpy_htod(bindings[0], sensor_np.astype(np.float32))
            context.execute_v2(bindings)

            # 출력 읽기
            out = np.empty(self._engine.get_binding_shape(1), dtype=np.float32)
            cuda.memcpy_dtoh(out, bindings[1])
            return {"anomaly_score": float(out[0])}
        except Exception as e:
            print(f"  TRT 추론 실패: {e}")
            return None


def generate_deploy_manifest(
    onnx_path: str,
    trt_path: str | None = None,
    int8_path: str | None = None,
    sensor_dim: int = 8,
    t_in: int = 24,
) -> dict:
    """배포 매니페스트 JSON 생성 — Jetson에서 참조."""
    manifest = {
        "model_name": "TinyTransformer-황백화탐지",
        "version": "1.0.0",
        "input": {"name": "sensor_seq", "shape": [1, t_in, sensor_dim], "dtype": "float32"},
        "outputs": ["anomaly_score", "severity_pct", "stage_logits"],
        "artifacts": {
            "onnx": onnx_path,
            "trt_fp16": trt_path,
            "int8": int8_path,
        },
        "target_device": "Jetson Orin Nano",
        "latency_target_ms": 30,
        "trtexec_cmd": build_tensorrt_command(onnx_path, trt_path or "deploy/model.trt"),
    }
    save_path = Path(onnx_path).parent / "deploy_manifest.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  배포 매니페스트 저장: {save_path}")
    return manifest
