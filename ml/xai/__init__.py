# lazy import
__all__ = ["extract_attention_map", "build_top_causes", "render_attention_heatmap_base64", "generate_report"]

def __getattr__(name):
    if name in __all__:
        import importlib
        mapping = {
            "extract_attention_map":        ("ml.xai.attention_viz", "extract_attention_map"),
            "build_top_causes":             ("ml.xai.attention_viz", "build_top_causes"),
            "render_attention_heatmap_base64": ("ml.xai.attention_viz", "render_attention_heatmap_base64"),
            "generate_report":              ("ml.xai.xai_reporter",  "generate_report"),
        }
        mod_path, attr = mapping[name]
        return getattr(importlib.import_module(mod_path), attr)
    raise AttributeError(f"module 'ml.xai' has no attribute {name!r}")
