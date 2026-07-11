import os
import sys
import json
import time
from pathlib import Path

# Add project root to path automatically
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader

from ml.data.cube_builder import load_cube, RealCubeDataset
from ml.models.st_mmt import STMMT
from ml.training.eval import evaluate_model

# Default Paths (H100 GPU server standard paths, adjustable via environment/arguments)
CUBE_DIR = os.getenv("CUBE_DIR", str(ROOT / "output/cube_v5"))
MODEL_PATH = os.getenv("MODEL_PATH", str(ROOT.parent.parent / "checkpoints/v10/best_model.pt"))

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"=== ST-MMT Permutation Feature Importance ===")
print(f"Using device: {device}")
print(f"Cube Dir: {CUBE_DIR}")
print(f"Model Path: {MODEL_PATH}")

if not os.path.exists(CUBE_DIR):
    # Fallback to local cube_v1 for debugging/local tests
    CUBE_DIR = str(ROOT / "output/cube_v1")
    print(f"Warning: Target cube not found. Falling back to local: {CUBE_DIR}")
    
if not os.path.exists(MODEL_PATH):
    # Fallback to local checkpoints
    MODEL_PATH = str(ROOT.parent.parent / "checkpoints/v10/best_model.pt")
    if not os.path.exists(MODEL_PATH):
        print(f"Error: Model file not found at {MODEL_PATH}")
        sys.exit(1)

# 1. Load Cube
print("Loading cube...")
cube, labels, meta = load_cube(CUBE_DIR)
T, H, W, C = cube.shape
print(f"Cube shape: {cube.shape}, Labels shape: {labels.shape}")

# 2. Add din_mask like train_real.py does (C+=1)
channel_names = list(meta["channel_names"])
din_mask_1d = None
if "din" in channel_names:
    din_ch = channel_names.index("din")
    din_vals = np.array(cube[:, 0, 0, din_ch], dtype=np.float32)
    din_mask_1d = np.zeros(T, dtype=np.float32)
    din_mask_1d[0] = 1.0
    for ti in range(1, T):
        if not np.isclose(din_vals[ti], din_vals[ti-1]):
            din_mask_1d[ti] = 1.0
    channel_names.append("din_mask")
    C += 1

# 3. Add Feature Engineering like train_real.py (ch08, ch28, ch29 overwrite)
din_ch = channel_names.index("din")
sst_ch = channel_names.index("sst")
deficit_T = np.clip(70.0 - cube[:, :, :, din_ch], 0.0, None)
sst_T = cube[:, :, :, sst_ch]
sst_mean_T = np.nanmean(np.where(np.isnan(sst_T), 12.0, sst_T), axis=(1, 2), keepdims=True)
weight_T = np.where(sst_mean_T >= 15.0, 1.5, np.where(sst_mean_T >= 10.0, 1.0, 0.7))
daily_score = deficit_T * weight_T

cumsum_daily = np.cumsum(daily_score, axis=0)
deficit_30d = np.zeros_like(daily_score)
deficit_30d[29:] = cumsum_daily[29:] - cumsum_daily[:-29]
deficit_30d[:29] = cumsum_daily[:29]

deficit_60d = np.zeros_like(daily_score)
deficit_60d[59:] = cumsum_daily[59:] - cumsum_daily[:-59]
deficit_60d[:59] = cumsum_daily[:59]

din_diff = np.zeros_like(cube[:, :, :, din_ch])
din_diff[1:] = cube[1:, :, :, din_ch] - cube[:-1, :, :, din_ch]

replace_targets = [
    ("chlorophyll_a", "deficit_30d", deficit_30d),
    ("chl_7d_avg", "deficit_60d", deficit_60d),
    ("nir_7d_avg", "din_diff", din_diff)
]

for old_name, new_name, arr in replace_targets:
    if old_name in channel_names:
        idx = channel_names.index(old_name)
        cube[:, :, :, idx] = arr
        channel_names[idx] = new_name
        meta["norm_stats"][new_name] = {"mean": float(np.mean(arr)), "std": float(np.std(arr))}

# 4. Dataset Setup (Use Validation indices)
t_in = 24
stride = 6
val_ratio = 0.2

all_t = []
for t in range(0, T - t_in + 1):
    target_idx = t + t_in - 1
    lbl = labels[target_idx, 0, 0]
    if lbl == 0:
        if t % stride == 0:
            all_t.append(t)
    elif lbl in (1, 2, 3):
        all_t.append(t)

date_labels = [int(labels[t + t_in - 1, 0, 0]) for t in all_t]
from collections import defaultdict
by_label = defaultdict(list)
for t, l in zip(all_t, date_labels):
    by_label[l].append(t)

val_t = []
for lbl, ts in sorted(by_label.items()):
    cut = int(len(ts) * (1 - val_ratio))
    val_t += ts[cut:]
val_t = sorted(val_t)

ds_val = RealCubeDataset(
    cube=cube, labels=labels,
    norm_stats=meta["norm_stats"], channel_names=channel_names,
    t_in=t_in, stride=stride,
    patch_h=64, patch_w=64,
    augment=False, t_indices=val_t, din_mask=din_mask_1d,
)
print(f"Val samples count: {len(ds_val)}")

# 5. Load Model (in_channels=32, n_stages=4 for v10 baseline compatibility)
model = STMMT(
    in_channels=32,
    d_model=256,
    n_heads=8,
    n_layers=4,
    d_ff=512,
    n_stages=4,
    patch_size=4,
)
model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model = model.to(device)
model.eval()

# Helper loader
val_loader = DataLoader(ds_val, batch_size=16, shuffle=False)

# 6. Base Evaluation
print("Evaluating Baseline performance...")
base_res = evaluate_model(model, val_loader, device, n_stages=4)
base_f1 = base_res["f1_macro"]
base_acc = base_res["accuracy"]
print(f"Baseline -> F1 macro: {base_f1:.4f}, Accuracy: {base_acc:.4f}")

# 7. Permutation Feature Importance
channels_to_evaluate = {
    "ch14: days_since_rain": channel_names.index("days_since_rain") if "days_since_rain" in channel_names else -1,
    "ch00: sst": channel_names.index("sst") if "sst" in channel_names else -1,
    "ch12: sst_anomaly": channel_names.index("sst_anomaly") if "sst_anomaly" in channel_names else -1,
    "ch01: din": channel_names.index("din") if "din" in channel_names else -1,
    "ch08: deficit_30d (Oversized/Overwritten ch08 chlorophyll_a)": channel_names.index("deficit_30d") if "deficit_30d" in channel_names else -1,
    "ch28: deficit_60d (Oversized/Overwritten ch28 chl_7d_avg)": channel_names.index("deficit_60d") if "deficit_60d" in channel_names else -1,
    "ch29: din_diff (Oversized/Overwritten ch29 nir_7d_avg)": channel_names.index("din_diff") if "din_diff" in channel_names else -1
}

pfi_results = {}

def evaluate_shuffled(ch_idx):
    if ch_idx == -1:
        return 0.0, 0.0
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch in val_loader:
            x, y = batch
            x = x.to(device)
            B = x.size(0)
            if B > 1:
                shuffled_idx = torch.randperm(B)
                x_shuffled = x.clone()
                x_shuffled[:, :, ch_idx, :, :] = x[shuffled_idx, :, ch_idx, :, :]
            else:
                x_shuffled = x
                
            out = model(x_shuffled)
            logits = out["last_logits"]
            preds = logits.argmax(dim=1).view(-1).cpu().numpy()
            y_np = y.view(-1).cpu().numpy()
            
            all_preds.extend(preds.flatten().tolist())
            all_labels.extend(y_np.tolist())
            
    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    
    valid_mask = (all_labels != -1)
    all_preds = all_preds[valid_mask]
    all_labels = all_labels[valid_mask]
    
    from sklearn.metrics import f1_score
    f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    acc = (all_preds == all_labels).mean()
    return f1, acc

print("\nStarting Permutation Feature Importance Loop...")
for name, idx in channels_to_evaluate.items():
    if idx == -1:
        print(f"  - {name}: Skipping (not found in channel names)")
        continue
    f1, acc = evaluate_shuffled(idx)
    f1_drop = base_f1 - f1
    acc_drop = base_acc - acc
    pfi_results[name] = {
        "ch_idx": idx,
        "f1": float(f1),
        "f1_drop": float(f1_drop),
        "accuracy": float(acc),
        "acc_drop": float(acc_drop)
    }
    print(f"  - {name}: F1={f1:.4f} (drop: -{f1_drop:.4f}), Acc={acc:.4f} (drop: -{acc_drop:.4f})")

# Save Results
out_path = Path(MODEL_PATH).parent / "pfi_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "baseline": {"f1_macro": base_f1, "accuracy": base_acc},
        "pfi": pfi_results
    }, f, indent=2, ensure_ascii=False)

print(f"\nPFI completed and saved to {out_path}")
