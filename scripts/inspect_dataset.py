"""train/val 데이터 검수 스크립트 — cube_v4 기준.

실행:
    cd ~/cheolyoung && uv run python scripts/inspect_dataset.py \
        --cube-dir output/cube_v4 --t-in 24 --stride 6 --val-ratio 0.2
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ml.data.cube_builder import load_cube, RealCubeDataset


def inspect(args):
    print("=" * 60)
    print("데이터셋 검수")
    print("=" * 60)

    # ── 1. 큐브 로드 ──────────────────────────────────────────
    cube, labels, meta = load_cube(args.cube_dir)
    T, H, W, C = cube.shape
    dates = meta["dates"]
    channel_names = list(meta["channel_names"])

    print(f"\n[큐브 기본 정보]")
    print(f"  shape : {cube.shape}")
    print(f"  기간  : {dates[0]} ~ {dates[-1]} ({T}일)")
    print(f"  채널  : {C}개  {channel_names}")

    # ── 2. 라벨 분포 ──────────────────────────────────────────
    label_names = ["정상(0)", "초기(1)", "경계(2)", "진행(3)"]
    day_labels = labels[:, 0, 0].astype(int)  # (T,) — 대표 픽셀 라벨
    print(f"\n[날짜별 라벨 분포]")
    for i, name in enumerate(label_names):
        cnt = int((day_labels == i).sum())
        pct = cnt / T * 100
        print(f"  {name}: {cnt}일 ({pct:.1f}%)")

    # 연도별 이상 발생 날짜
    print(f"\n[연도별 이상(1/2/3) 발생 날짜]")
    for year in sorted(set(d[:4] for d in dates)):
        idx = [i for i, d in enumerate(dates) if d[:4] == year]
        yl = day_labels[idx]
        abnormal = int((yl > 0).sum())
        print(f"  {year}: {len(idx)}일 중 이상 {abnormal}일  "
              f"(초기 {int((yl==1).sum())} / 경계 {int((yl==2).sum())} / 진행 {int((yl==3).sum())})")

    # ── 3. Train/Val split 재현 ────────────────────────────────
    all_t = list(range(0, T - args.t_in, args.stride))
    date_labels_split = [int(day_labels[t + args.t_in - 1]) for t in all_t]

    by_label: dict = defaultdict(list)
    for t, l in zip(all_t, date_labels_split):
        by_label[l].append(t)

    train_t, val_t = [], []
    for lbl, ts in sorted(by_label.items()):
        cut = int(len(ts) * (1 - args.val_ratio))
        train_t += ts[:cut]
        val_t += ts[cut:]

    # 날짜 확인
    train_dates = sorted(set(dates[t + args.t_in - 1] for t in train_t))
    val_dates   = sorted(set(dates[t + args.t_in - 1] for t in val_t))

    print(f"\n[Train/Val split (target date 기준)]")
    for lbl, name in enumerate(label_names):
        tr = [t for t in train_t if date_labels_split[all_t.index(t) if t in all_t else 0] == lbl
              if t in all_t and date_labels_split[all_t.index(t)] == lbl]
        va = [t for t in val_t   if t in all_t and date_labels_split[all_t.index(t)] == lbl]
        print(f"  {name}: train {len(tr)}개 / val {len(va)}개")

    # temporal overlap 확인
    overlap = set(train_dates) & set(val_dates)
    print(f"\n[Temporal Leakage 확인]")
    print(f"  train 날짜 수: {len(train_dates)}")
    print(f"  val 날짜 수  : {len(val_dates)}")
    print(f"  중복 날짜    : {len(overlap)}개  {'⚠️ LEAK!' if overlap else '✅ 없음'}")
    if overlap:
        print(f"  중복 목록    : {sorted(overlap)[:10]}")

    # train/val 날짜 범위
    print(f"  train 범위   : {train_dates[0]} ~ {train_dates[-1]}")
    print(f"  val 범위     : {val_dates[0]} ~ {val_dates[-1]}")

    # ── 4. 채널별 통계 ────────────────────────────────────────
    print(f"\n[채널별 통계 (전체 날짜 × 중심 픽셀 64,64)]")
    cx, cy = H // 2, W // 2
    center = cube[:, cx, cy, :]  # (T, C)
    print(f"  {'채널':<20} {'mean':>8} {'std':>8} {'min':>8} {'max':>8} {'zero%':>7} {'nan%':>7}")
    print("  " + "-" * 68)
    for i, ch in enumerate(channel_names):
        col = center[:, i].astype(float)
        nan_pct  = float(np.isnan(col).mean() * 100)
        zero_pct = float((col == 0).mean() * 100)
        col_clean = col[~np.isnan(col)]
        if len(col_clean) == 0:
            print(f"  {ch:<20} {'NaN':>8}")
            continue
        print(f"  {ch:<20} {col_clean.mean():>8.4f} {col_clean.std():>8.4f} "
              f"{col_clean.min():>8.4f} {col_clean.max():>8.4f} "
              f"{zero_pct:>6.1f}% {nan_pct:>6.1f}%")

    # ── 5. Dead channel 확인 ──────────────────────────────────
    print(f"\n[Dead Channel 확인 (std≈0 또는 zero>90%)]")
    dead = []
    for i, ch in enumerate(channel_names):
        col = center[:, i].astype(float)
        col_clean = col[~np.isnan(col)]
        if len(col_clean) == 0 or col_clean.std() < 1e-6 or (col == 0).mean() > 0.9:
            dead.append(ch)
            print(f"  ⚠️  {ch} (idx={i}): std={col_clean.std():.6f}, zero%={(col==0).mean()*100:.1f}%")
    if not dead:
        print("  ✅ Dead channel 없음")

    # ── 6. 결과 저장 ──────────────────────────────────────────
    result = {
        "cube_shape": list(cube.shape),
        "date_range": [dates[0], dates[-1]],
        "label_dist_days": {name: int((day_labels == i).sum()) for i, name in enumerate(label_names)},
        "train_samples": len(train_t),
        "val_samples": len(val_t),
        "temporal_overlap": len(overlap),
        "dead_channels": dead,
    }
    out_path = Path(args.cube_dir) / "inspect_result.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n결과 저장: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cube-dir",  type=str, required=True)
    p.add_argument("--t-in",      type=int, default=24)
    p.add_argument("--stride",    type=int, default=6)
    p.add_argument("--val-ratio", type=float, default=0.2)
    inspect(p.parse_args())
