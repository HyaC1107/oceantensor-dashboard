"""cube_v5에서 라벨별 샘플 추출 → 엑셀 파일 생성.

사용 (H100):
    PYTHONPATH=. uv run python scripts/export_label_samples.py
    PYTHONPATH=. uv run python scripts/export_label_samples.py --n-samples 200 --cube-dir output/cube_v5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import zarr

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ml.data.channel_builder import CHANNEL_NAMES

LABEL_NAMES = {0: "정상", 1: "초기", 2: "경계", 3: "진행"}

_START_DATE = date(2021, 11, 1)


def idx_to_date(t_idx: int) -> str:
    return (_START_DATE + timedelta(days=int(t_idx))).strftime("%Y-%m-%d")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cube-dir",  default="output/cube_v5")
    p.add_argument("--n-samples", type=int, default=100, help="라벨별 샘플 수")
    p.add_argument("--out",       default="output/label_samples_v5.xlsx")
    args = p.parse_args()

    cube_path = ROOT / args.cube_dir
    print(f"[export] cube 로드: {cube_path}")

    data   = zarr.open_array(str(cube_path / "data.zarr"),   mode="r")
    labels = zarr.open_array(str(cube_path / "labels.zarr"), mode="r")

    T, H, W, C = data.shape
    print(f"[export] shape: {data.shape}, 채널: {C}")

    rng = np.random.default_rng(42)
    sheets: dict[str, pd.DataFrame] = {}

    for label_id, label_name in LABEL_NAMES.items():
        print(f"[export] {label_name}({label_id}) 샘플 추출 중...")

        # 해당 라벨 위치 수집 (t, h, w)
        coords = np.argwhere(labels[:] == label_id)   # (N, 3)
        total  = len(coords)
        print(f"         총 {total:,}개 중 {args.n_samples}개 샘플링")

        if total == 0:
            print(f"         ⚠️ 해당 라벨 없음 — 스킵")
            continue

        n = min(args.n_samples, total)
        idx = rng.choice(total, size=n, replace=False)
        sampled = coords[idx]  # (n, 3)

        rows = []
        for t, h, w in sampled:
            ch_vals = data[int(t), int(h), int(w), :]   # (C,)
            row = {
                "date":      idx_to_date(t),
                "t_idx":     int(t),
                "h_idx":     int(h),
                "w_idx":     int(w),
                "label_id":  label_id,
                "label_name": label_name,
            }
            for ci, ch_name in enumerate(CHANNEL_NAMES):
                row[ch_name] = round(float(ch_vals[ci]), 4)
            rows.append(row)

        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        sheets[label_name] = df
        print(f"         ✅ {len(df)}행 완료")

    # 요약 시트
    summary_rows = []
    for label_id, label_name in LABEL_NAMES.items():
        total = int((labels[:] == label_id).sum())
        pct   = total / (T * H * W) * 100
        summary_rows.append({
            "label_id":   label_id,
            "label_name": label_name,
            "total_px":   total,
            "pct":        round(pct, 2),
            "sampled":    len(sheets.get(label_name, pd.DataFrame())),
        })
    sheets["요약"] = pd.DataFrame(summary_rows)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n[export] 엑셀 저장 중: {out_path}")

    with pd.ExcelWriter(str(out_path), engine="openpyxl") as writer:
        # 요약 시트 먼저
        sheets["요약"].to_excel(writer, sheet_name="요약", index=False)
        for label_name in ["정상", "초기", "경계", "진행"]:
            if label_name in sheets:
                sheets[label_name].to_excel(writer, sheet_name=label_name, index=False)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"[export] 완료: {out_path} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
