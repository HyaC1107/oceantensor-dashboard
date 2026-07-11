#!/usr/bin/env python3
"""v7 STMMT 사전 계산 — 어장별 날짜별 stage 추출 후 JSON 저장."""
import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import torch

ROOT = Path.home() / "cheolyoung"
sys.path.insert(0, str(ROOT))

from ml.data.cube_builder import load_cube
from ml.models.st_mmt import STMMT

CUBE_DIR = ROOT / "output/cube_v3"
CKPT     = ROOT / "checkpoints/v7/best_model.pt"
OUT      = ROOT / "checkpoints/v7/v7_predictions.json"
T_IN     = 24
BATCH    = 16
DEVICE   = "cuda" if torch.cuda.is_available() else "cpu"

FARMS = [
    {"id": "F01", "lat": 34.34595, "lon": 126.49395},
    {"id": "F02", "lat": 34.40074, "lon": 126.31771},
    {"id": "F03", "lat": 34.77521, "lon": 126.2969},
    {"id": "F04", "lat": 34.80153, "lon": 126.29768},
    {"id": "F05", "lat": 34.42183, "lon": 126.37053},
    {"id": "F06", "lat": 37.19106, "lon": 126.54392},
    {"id": "F07", "lat": 34.77955, "lon": 126.28648},
    {"id": "F08", "lat": 34.81203, "lon": 126.2493},
    {"id": "F09", "lat": 34.83408, "lon": 126.24423},
    {"id": "F10", "lat": 34.35148, "lon": 126.49376},
    {"id": "F11", "lat": 34.37549, "lon": 126.1247},
    {"id": "F12", "lat": 34.37689, "lon": 126.12169},
    {"id": "F13", "lat": 34.88051, "lon": 127.81527},
    {"id": "F14", "lat": 34.50179, "lon": 127.16116},
    {"id": "F15", "lat": 35.84335, "lon": 126.34829},
    {"id": "F16", "lat": 36.02531, "lon": 126.54941},
    {"id": "F17", "lat": 36.02553, "lon": 126.55061},
    {"id": "F18", "lat": 37.06182, "lon": 126.61193},
    {"id": "F19", "lat": 37.05683, "lon": 126.63319},
    {"id": "F20", "lat": 37.04575, "lon": 126.62975},
    {"id": "F21", "lat": 35.73271, "lon": 126.49949},
    {"id": "F22", "lat": 34.56137, "lon": 126.0337},
    {"id": "F23", "lat": 34.55239, "lon": 126.0951},
    {"id": "F24", "lat": 34.55205, "lon": 126.09337},
    {"id": "F25", "lat": 34.55212, "lon": 126.08872},
    {"id": "F26", "lat": 34.56388, "lon": 126.03557},
    {"id": "F27", "lat": 34.82776, "lon": 126.24988},
    {"id": "F28", "lat": 34.36139, "lon": 126.45752},
    {"id": "F29", "lat": 34.33317, "lon": 126.49885},
    {"id": "F30", "lat": 34.34907, "lon": 126.45643},
    {"id": "F31", "lat": 34.70853, "lon": 127.71156},
    {"id": "F32", "lat": 34.70826, "lon": 127.71136},
    {"id": "F33", "lat": 34.7761,  "lon": 126.29489},
    {"id": "F34", "lat": 34.43445, "lon": 126.37036},
    {"id": "F35", "lat": 37.11734, "lon": 126.61991},
    {"id": "F36", "lat": 37.04366, "lon": 126.53304},
    {"id": "F37", "lat": 34.78501, "lon": 126.28889},
    {"id": "F38", "lat": 34.56449, "lon": 126.04942},
    {"id": "F39", "lat": 37.18643, "lon": 126.55408},
    {"id": "F40", "lat": 37.10979, "lon": 126.64004},
    {"id": "F41", "lat": 37.18917, "lon": 126.59125},
    {"id": "F42", "lat": 37.14878, "lon": 126.6365},
    {"id": "F43", "lat": 37.17279, "lon": 126.54936},
    {"id": "F44", "lat": 37.16177, "lon": 126.6062},
    {"id": "F45", "lat": 37.11377, "lon": 126.62037},
    {"id": "F46", "lat": 34.76942, "lon": 126.19123},
    {"id": "F47", "lat": 35.73357, "lon": 126.49627},
    {"id": "F48", "lat": 34.57408, "lon": 126.0721},
    {"id": "F49", "lat": 37.10963, "lon": 126.54527},
    {"id": "F50", "lat": 34.81959, "lon": 126.27875},
    {"id": "F51", "lat": 35.8432,  "lon": 126.35317},
    {"id": "F52", "lat": 37.05496, "lon": 126.55733},
    {"id": "F53", "lat": 37.05811, "lon": 126.55893},
    {"id": "F54", "lat": 37.1939,  "lon": 126.57216},
    {"id": "F55", "lat": 37.12696, "lon": 126.59888},
    {"id": "F56", "lat": 37.14832, "lon": 126.59911},
    {"id": "F57", "lat": 35.85099, "lon": 126.42763},
    {"id": "F58", "lat": 35.84494, "lon": 126.37219},
    {"id": "F59", "lat": 34.80203, "lon": 126.27834},
    {"id": "F60", "lat": 34.75073, "lon": 126.28152},
    {"id": "F61", "lat": 34.22246, "lon": 126.4325},
    {"id": "F62", "lat": 34.20233, "lon": 126.44639},
    {"id": "F63", "lat": 34.17643, "lon": 126.42558},
    {"id": "F64", "lat": 34.18442, "lon": 126.36343},
    {"id": "F65", "lat": 34.74833, "lon": 127.92594},
    {"id": "F66", "lat": 34.8737,  "lon": 126.18229},
    {"id": "F67", "lat": 37.19104, "lon": 126.52152},
    {"id": "F68", "lat": 37.07254, "lon": 126.59217},
    {"id": "F69", "lat": 34.35436, "lon": 126.46623},
    {"id": "F70", "lat": 34.42473, "lon": 126.36235},
    {"id": "F71", "lat": 34.42615, "lon": 126.37047},
    {"id": "F72", "lat": 34.70857, "lon": 127.71184},
    {"id": "F73", "lat": 34.31939, "lon": 126.78838},
    {"id": "F74", "lat": 34.51628, "lon": 127.165},
    {"id": "F75", "lat": 34.52323, "lon": 127.16425},
    {"id": "F76", "lat": 34.51791, "lon": 127.16853},
    {"id": "F77", "lat": 34.33667, "lon": 126.46216},
    {"id": "F78", "lat": 34.70862, "lon": 127.71218},
    {"id": "F79", "lat": 34.34933, "lon": 126.46778},
]


def main():
    # ── 1. 큐브 로드 ──────────────────────────────────────────────────────
    print(f"[1/4] cube_v3 로드... ({CUBE_DIR})")
    cube, labels, meta = load_cube(str(CUBE_DIR))
    T, H, W, C = cube.shape
    dates = meta["dates"]
    channel_names = list(meta["channel_names"])
    print(f"  shape: {cube.shape}, 기간: {dates[0]} ~ {dates[-1]}")

    # DIN mask 채널 추가 (train_real.py와 동일)
    if "din" in channel_names:
        din_ch = channel_names.index("din")
        din_vals = cube[:, 0, 0, din_ch]
        din_mask = np.zeros(T, dtype=np.float32)
        din_mask[0] = 1.0
        for ti in range(1, T):
            if not np.isclose(din_vals[ti], din_vals[ti - 1]):
                din_mask[ti] = 1.0
        mask_3d = np.broadcast_to(din_mask[:, None, None], (T, H, W)).copy()
        cube = np.concatenate([cube, mask_3d[:, :, :, None]], axis=-1)
        channel_names.append("din_mask")
        C += 1
        print(f"  DIN 마스크 추가 → C={C}")

    # Z-score 정규화
    norm_stats = meta.get("norm_stats", {})
    cube_norm = cube.astype(np.float32)
    for ci, name in enumerate(channel_names):
        s = norm_stats.get(name, {})
        mean = float(s.get("mean", 0.0))
        std  = float(s.get("std", 1.0)) or 1.0
        cube_norm[:, :, :, ci] = (cube_norm[:, :, :, ci] - mean) / std

    # (T, H, W, C) → (T, C, H, W) tensor
    cube_t = torch.from_numpy(cube_norm).permute(0, 3, 1, 2)
    print(f"  정규화 완료, tensor shape: {cube_t.shape}")

    # ── 2. 좌표 → 픽셀 매핑 ──────────────────────────────────────────────
    g = meta["grid_meta"]
    lat_min, lat_max = g["lat_min"], g["lat_max"]
    lon_min, lon_max = g["lon_min"], g["lon_max"]

    out_of_grid = []
    farm_pixels = {}
    for f in FARMS:
        lat, lon = f["lat"], f["lon"]
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            out_of_grid.append(f["id"])
        h_idx = int((lat_max - lat) / (lat_max - lat_min) * H)
        w_idx = int((lon - lon_min) / (lon_max - lon_min) * W)
        farm_pixels[f["id"]] = (max(0, min(H - 1, h_idx)), max(0, min(W - 1, w_idx)))

    print(f"  어장 매핑 완료: {len(farm_pixels)}개 (그리드 외 {len(out_of_grid)}개 클램프)")
    if out_of_grid:
        print(f"  그리드 외: {out_of_grid}")

    # ── 3. 모델 로드 ──────────────────────────────────────────────────────
    print(f"[2/4] 모델 로드... ({CKPT})")
    model = STMMT(
        in_channels=C, d_model=256, n_heads=8,
        n_layers=4, d_ff=512, n_stages=4, patch_size=4,
    )
    model.load_state_dict(torch.load(CKPT, map_location=DEVICE, weights_only=True))
    model.to(DEVICE).eval()
    print(f"  로드 완료 (device={DEVICE})")

    # ── 4. 배치 추론 ──────────────────────────────────────────────────────
    indices = list(range(T_IN, T))
    print(f"[3/4] 추론 시작... (날짜 {len(indices)}개, batch={BATCH})")
    predictions = {}

    for b_start in range(0, len(indices), BATCH):
        batch_idx = indices[b_start:b_start + BATCH]
        # (B, T_IN, C, H, W)
        windows = torch.stack([cube_t[t - T_IN:t] for t in batch_idx]).to(DEVICE)
        with torch.no_grad():
            out = model(windows)
        stage_maps = out["last_logits"].argmax(dim=1).cpu().numpy()  # (B, H, W)

        for i, t in enumerate(batch_idx):
            stage_map = stage_maps[i]
            predictions[dates[t]] = {
                fid: int(stage_map[h, w])
                for fid, (h, w) in farm_pixels.items()
            }

        if b_start % 160 == 0:
            pct = b_start / len(indices) * 100
            print(f"  [{pct:5.1f}%] {dates[batch_idx[0]]}")

    # ── 5. 저장 ───────────────────────────────────────────────────────────
    print(f"[4/4] 저장... ({OUT})")
    result = {
        "meta": {
            "model": "stmmt-v7",
            "cube": "cube_v3",
            "t_in": T_IN,
            "n_farms": len(FARMS),
            "date_range": [dates[T_IN], dates[-1]],
            "stage_labels": {"0": "정상", "1": "초기", "2": "경계", "3": "진행"},
            "out_of_grid_farms": out_of_grid,
            "generated_at": datetime.now().isoformat()[:10],
        },
        "predictions": predictions,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    print(f"완료! 총 {len(predictions)}일치 예측 저장됨")
    print(f"  파일: {OUT}")


if __name__ == "__main__":
    main()
