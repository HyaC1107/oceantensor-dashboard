"""평가 지표 — ADI 회귀(MAE/RMSE) + warn/severe 이진(AUC/AP/F1).

멀티헤드 ST-MMT 전용. 회귀 지표는 스트리밍 합으로 계산(대용량 val OOM 방어),
warn/severe는 픽셀당 1값이라 전량 수집해 AUC/AP 계산.
"""
import time
import numpy as np
import torch
from sklearn.metrics import roc_auc_score, average_precision_score, f1_score

from ml.models.st_mmt import STMMT


def _binary_metrics(p: np.ndarray, t: np.ndarray):
    """이진 확률 p, 정답 t → (AUC, AP, F1@0.5). 한 클래스뿐이면 AUC/AP=nan."""
    if t.size == 0:
        return float("nan"), float("nan"), float("nan")
    two_class = len(np.unique(t)) > 1
    try:
        auc = float(roc_auc_score(t, p)) if two_class else float("nan")
    except ValueError:
        auc = float("nan")
    try:
        ap = float(average_precision_score(t, p)) if two_class else float("nan")
    except ValueError:
        ap = float("nan")
    f1 = float(f1_score(t, (p >= 0.5).astype(np.int8), zero_division=0))
    return auc, ap, f1


def evaluate_model(
    model: torch.nn.Module,
    dataloader: torch.utils.data.DataLoader,
    device: torch.device,
    warn_thresh: float | None = None,
    severe_thresh: float | None = None,
) -> dict:
    """멀티헤드 ST-MMT 평가.

    Returns dict:
        adi_mae, adi_rmse,
        warn_auc/ap/f1, severe_auc/ap/f1, warn_severe_corr,
        warn_pos_rate, severe_pos_rate,
        avg_latency_ms, p95_latency_ms, n_valid
    """
    warn_thresh = warn_thresh if warn_thresh is not None else STMMT.WARN_THRESH
    severe_thresh = severe_thresh if severe_thresh is not None else STMMT.SEVERE_THRESH

    model.eval()
    # 회귀: 스트리밍 누적 (전량 저장 금지 — OOM 방어)
    sae = 0.0   # sum abs err
    sse = 0.0   # sum sq err
    n_valid = 0
    # 이진: 픽셀당 1값이라 전량 수집 (AUC/AP용)
    warn_p_all, warn_t_all = [], []
    severe_p_all, severe_t_all = [], []
    latencies = []

    with torch.no_grad():
        for batch in dataloader:
            x, y = batch                 # y: (B, t_out, H, W) 연속 ADI, IGNORE=-1
            x = x.to(device)
            y = y.to(device)

            t0 = time.perf_counter()
            out = model(x)
            latencies.append((time.perf_counter() - t0) * 1000)

            adi = out["adi"]                              # (B, t_out, H, W)
            warn_p = torch.sigmoid(out["warn_logit"])     # (B, H, W)
            severe_p = torch.sigmoid(out["severe_logit"]) # (B, H, W)

            valid = y >= 0                                # (B, t_out, H, W)
            if valid.any():
                err = (adi[valid] - y[valid])
                sae += float(err.abs().sum().item())
                sse += float((err * err).sum().item())
                n_valid += int(valid.sum().item())

            # warn/severe 타깃: 7일창 유효일 max ADI
            neg = torch.full_like(y, -1.0)
            pix_max = torch.where(valid, y, neg).amax(dim=1)   # (B, H, W)
            pix_valid = valid.any(dim=1)                        # (B, H, W)
            if pix_valid.any():
                warn_t_all.append((pix_max[pix_valid] >= warn_thresh).cpu().numpy().astype(np.int8))
                severe_t_all.append((pix_max[pix_valid] >= severe_thresh).cpu().numpy().astype(np.int8))
                warn_p_all.append(warn_p[pix_valid].cpu().numpy())
                severe_p_all.append(severe_p[pix_valid].cpu().numpy())

    lat_mean = float(np.mean(latencies)) if latencies else float("nan")
    lat_p95 = float(np.percentile(latencies, 95)) if latencies else float("nan")

    # 유효 픽셀 0개 방어
    if n_valid == 0:
        return {
            "adi_mae": float("nan"), "adi_rmse": float("nan"),
            "warn_auc": float("nan"), "warn_ap": float("nan"), "warn_f1": float("nan"),
            "severe_auc": float("nan"), "severe_ap": float("nan"), "severe_f1": float("nan"),
            "warn_severe_corr": float("nan"),
            "warn_pos_rate": float("nan"), "severe_pos_rate": float("nan"),
            "avg_latency_ms": lat_mean, "p95_latency_ms": lat_p95, "n_valid": 0,
        }

    adi_mae = sae / n_valid
    adi_rmse = float(np.sqrt(sse / n_valid))

    warn_p = np.concatenate(warn_p_all) if warn_p_all else np.array([])
    warn_t = np.concatenate(warn_t_all) if warn_t_all else np.array([])
    severe_p = np.concatenate(severe_p_all) if severe_p_all else np.array([])
    severe_t = np.concatenate(severe_t_all) if severe_t_all else np.array([])

    warn_auc, warn_ap, warn_f1 = _binary_metrics(warn_p, warn_t)
    severe_auc, severe_ap, severe_f1 = _binary_metrics(severe_p, severe_t)

    # warn↔severe 예측 상관 (데이터 바이모달 → near-redundant 여부 확인용)
    if warn_p.size > 1 and np.std(warn_p) > 0 and np.std(severe_p) > 0:
        warn_severe_corr = float(np.corrcoef(warn_p, severe_p)[0, 1])
    else:
        warn_severe_corr = float("nan")

    return {
        "adi_mae": adi_mae, "adi_rmse": adi_rmse,
        "warn_auc": warn_auc, "warn_ap": warn_ap, "warn_f1": warn_f1,
        "severe_auc": severe_auc, "severe_ap": severe_ap, "severe_f1": severe_f1,
        "warn_severe_corr": warn_severe_corr,
        "warn_pos_rate": float(warn_t.mean()) if warn_t.size else float("nan"),
        "severe_pos_rate": float(severe_t.mean()) if severe_t.size else float("nan"),
        "avg_latency_ms": lat_mean, "p95_latency_ms": lat_p95,
        "n_valid": int(n_valid),
    }
