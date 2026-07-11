# lazy import — torch 없는 환경에서도 임포트 가능
__all__ = ["Trainer", "KDTrainer", "evaluate_model", "benchmark_latency", "finetune", "SensorSequenceDataset"]

def __getattr__(name):
    if name in __all__:
        import importlib
        mapping = {
            "Trainer":              ("ml.training.trainer",  "Trainer"),
            "KDTrainer":            ("ml.training.kd_trainer", "KDTrainer"),
            "evaluate_model":       ("ml.training.eval",     "evaluate_model"),
            "benchmark_latency":    ("ml.training.eval",     "benchmark_latency"),
            "finetune":             ("ml.training.finetune", "finetune"),
            "SensorSequenceDataset":("ml.training.finetune", "SensorSequenceDataset"),
        }
        mod_path, attr = mapping[name]
        return getattr(importlib.import_module(mod_path), attr)
    raise AttributeError(f"module 'ml.training' has no attribute {name!r}")
