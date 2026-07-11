# lazy import — torch/onnx 없는 환경에서도 임포트 가능
__all__ = [
    "export_tiny_transformer", "benchmark_onnx",
    "quantize_int8", "compare_accuracy",
    "AdaptiveTokenPruner", "PruningConfig", "timed_inference",
    "TRTInferenceEngine", "generate_deploy_manifest",
]

def __getattr__(name):
    if name in __all__:
        import importlib
        mapping = {
            "export_tiny_transformer": ("ml.optimization.onnx_export",  "export_tiny_transformer"),
            "benchmark_onnx":          ("ml.optimization.onnx_export",  "benchmark_onnx"),
            "quantize_int8":           ("ml.optimization.quantizer",     "quantize_int8"),
            "compare_accuracy":        ("ml.optimization.quantizer",     "compare_accuracy"),
            "AdaptiveTokenPruner":     ("ml.optimization.token_pruning", "AdaptiveTokenPruner"),
            "PruningConfig":           ("ml.optimization.token_pruning", "PruningConfig"),
            "timed_inference":         ("ml.optimization.token_pruning", "timed_inference"),
            "TRTInferenceEngine":      ("ml.optimization.tensorrt_opt",  "TRTInferenceEngine"),
            "generate_deploy_manifest":("ml.optimization.tensorrt_opt",  "generate_deploy_manifest"),
        }
        mod_path, attr = mapping[name]
        return getattr(importlib.import_module(mod_path), attr)
    raise AttributeError(f"module 'ml.optimization' has no attribute {name!r}")
