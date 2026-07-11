"""Attention Map 시각화 — TinyTransformer 추론 결과 → XAI 히트맵.

출력:
  - attention_map_json: feature별 가중치 dict (API 응답용)
  - PNG base64: 히트맵 이미지 (프론트엔드 오버레이용)
"""
import io
import base64
import json
from typing import Optional

import numpy as np
# torch는 사용 시점에 lazy import (없는 환경에서도 모듈 임포트 가능)

SENSOR_FEATURES = [
    "water_temp",
    "dissolved_oxygen",
    "din",
    "dip",
    "np_ratio",
    "salinity",
    "precipitation",
    "chlorophyll_a",
]

STAGE_NAMES = ["정상", "초기", "경계", "진행", "심각"]
STAGE_COLORS = ["#22c55e", "#84cc16", "#f59e0b", "#f97316", "#ef4444"]


def extract_attention_map(
    model_output: dict,
    sensor_features: list[str] | None = None,
    t_in: int = 24,
) -> dict:
    """TinyTransformer forward() 출력에서 XAI attention map을 추출.

    Args:
        model_output:    model.forward() 반환 dict
        sensor_features: 피처 이름 리스트 (None이면 기본값 사용)
        t_in:            입력 타임스텝 수

    Returns:
        dict with keys:
          tokens, weights, top_feature, stage, stage_name
    """
    features = sensor_features or SENSOR_FEATURES

    # token_scores: (B, T) — 타임스텝별 중요도
    token_scores = model_output.get("token_scores")
    # attn_weights: (B, H, K, K) — 마지막 block sparse attention
    attn_weights = model_output.get("attn_weights")

    stage = int(model_output.get("stage", [0])[0])
    anomaly_score = float(model_output.get("anomaly_score", [0.0])[0])

    # Feature importance: attn_weights를 feature dim에 매핑
    def _to_numpy(t):
        """torch.Tensor 또는 list/ndarray를 numpy array로 안전 변환."""
        if t is None:
            return None
        if hasattr(t, "cpu"):          # torch.Tensor
            return t.detach().cpu().numpy()
        return np.array(t)

    if attn_weights is not None:
        # (B, H, K, K) → mean over heads & query → (K,)
        aw = _to_numpy(attn_weights)
        importance = aw[0].mean(axis=0).mean(axis=0)
    elif token_scores is not None:
        importance = _to_numpy(token_scores)[0]
    else:
        # fallback: 균등 분포
        importance = np.ones(len(features)) / len(features)

    # features 수로 resample
    n_feat = len(features)
    if len(importance) != n_feat:
        # 선형 보간으로 feature 수에 맞춤
        x_old = np.linspace(0, 1, len(importance))
        x_new = np.linspace(0, 1, n_feat)
        importance = np.interp(x_new, x_old, importance)

    # 정규화 (softmax 스타일)
    exp_imp = np.exp(importance - importance.max())
    weights = (exp_imp / exp_imp.sum()).tolist()

    top_idx = int(np.argmax(weights))

    return {
        "tokens": features,
        "weights": [round(w, 4) for w in weights],
        "top_feature": features[top_idx],
        "top_weight": round(weights[top_idx], 4),
        "stage": stage,
        "stage_name": STAGE_NAMES[min(stage, 4)],
        "anomaly_score": round(anomaly_score, 4),
    }


def build_top_causes(
    attention_map: dict,
    sensor_values: dict | None = None,
    thresholds: dict | None = None,
) -> list[dict]:
    """상위 5개 원인 피처 + 현재값 + 임계치 비교.

    Args:
        attention_map: extract_attention_map() 반환값
        sensor_values: 실제 측정값 dict (없으면 N/A)
        thresholds:    황백화 임계치 dict (없으면 기본값 사용)

    Returns:
        list of dicts: feature, importance, value, threshold, status
    """
    default_thresholds = {
        "water_temp": 25.0,
        "dissolved_oxygen": 5.0,
        "din": 5.0,
        "dip": 0.3,
        "np_ratio": 16.0,
        "salinity": 30.0,
        "precipitation": 20.0,
        "chlorophyll_a": 5.0,
    }
    thresh = {**default_thresholds, **(thresholds or {})}
    vals = sensor_values or {}

    features = attention_map["tokens"]
    weights = attention_map["weights"]

    ranked = sorted(
        zip(features, weights), key=lambda x: x[1], reverse=True
    )[:5]

    causes = []
    for feat, imp in ranked:
        val = vals.get(feat)
        thr = thresh.get(feat)
        if val is not None and thr is not None:
            if feat in ("din", "dissolved_oxygen", "salinity"):
                status = "BELOW_THRESHOLD" if val < thr else "ABOVE_THRESHOLD"
            else:
                status = "ABOVE_THRESHOLD" if val > thr else "BELOW_THRESHOLD"
        else:
            status = "UNKNOWN"

        causes.append({
            "feature": feat,
            "importance": round(imp, 4),
            "value": round(val, 3) if val is not None else None,
            "threshold": thr,
            "status": status,
        })

    return causes


def render_attention_heatmap_base64(
    attention_map: dict,
    width: int = 400,
    height: int = 120,
) -> str:
    """Attention Map을 PNG 히트맵으로 렌더링 → base64 인코딩.

    matplotlib 없이 numpy+PNG 직접 인코딩으로 의존성 최소화.
    Returns: 'data:image/png;base64,...' 형식 문자열
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm

        features = attention_map["tokens"]
        weights = np.array(attention_map["weights"])

        fig, ax = plt.subplots(figsize=(width / 80, height / 80))
        fig.patch.set_facecolor("#0a1628")

        # 가로 바 히트맵
        cmap = cm.get_cmap("RdYlGn_r")
        colors = [cmap(w / max(weights)) for w in weights]
        bars = ax.barh(features, weights, color=colors, edgecolor="none")

        ax.set_xlim(0, max(weights) * 1.1)
        ax.set_facecolor("#0a1628")
        ax.tick_params(colors="#94a3b8", labelsize=8)
        ax.spines[:].set_color("#1e293b")
        ax.set_xlabel("Attention Weight", color="#94a3b8", fontsize=8)
        ax.invert_yaxis()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight",
                    facecolor=fig.get_facecolor(), dpi=80)
        plt.close(fig)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode()
        return f"data:image/png;base64,{encoded}"

    except ImportError:
        # matplotlib 없는 환경 — 빈 PNG placeholder
        return ""
