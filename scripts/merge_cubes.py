"""두 Zarr 큐브를 T 축으로 병합 → cube_final 생성.

사용:
    uv run python scripts/merge_cubes.py \
        --cube-a output/cube_pre2021 \
        --cube-b output/cube_v3 \
        --out    output/cube_final

주의:
    - 두 큐브의 H, W, C가 동일해야 함
    - 날짜 중복 시 cube-b 우선 (더 최신 데이터)
    - norm_stats는 병합 후 전체 재계산
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def load_zarr_cube(cube_dir: str):
    import zarr
    p = Path(cube_dir)
    with open(p / "meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    data   = zarr.open(str(p / "data.zarr"),   mode="r")[:]
    labels = zarr.open(str(p / "labels.zarr"), mode="r")[:]
    return data.astype(np.float32), labels.astype(np.int8), meta


def recompute_norm_stats(cube: np.ndarray, channel_names: list[str]) -> dict:
    """병합 후 전체 채널별 mean/std 재산정."""
    T, H, W, C = cube.shape
    flat = cube.reshape(-1, C)
    stats = {}
    for ci, name in enumerate(channel_names):
        col = flat[:, ci]
        valid = col[np.isfinite(col)]
        if len(valid) == 0:
            stats[name] = {"mean": 0.0, "std": 1.0}
        else:
            std = float(np.std(valid))
            stats[name] = {
                "mean": float(np.mean(valid)),
                "std":  std if std > 1e-8 else 1.0,
            }
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cube-a", required=True, help="첫 번째 큐브 (오래된 기간)")
    p.add_argument("--cube-b", required=True, help="두 번째 큐브 (최신 기간)")
    p.add_argument("--out",    required=True, help="출력 경로")
    p.add_argument("--version", default="final", help="버전 태그")
    args = p.parse_args()

    print("=" * 60)
    print("큐브 병합 시작")

    print(f"  [A] {args.cube_a}")
    data_a, labels_a, meta_a = load_zarr_cube(args.cube_a)
    print(f"      shape={data_a.shape}, 날짜={meta_a['dates'][0]} ~ {meta_a['dates'][-1]}")

    print(f"  [B] {args.cube_b}")
    data_b, labels_b, meta_b = load_zarr_cube(args.cube_b)
    print(f"      shape={data_b.shape}, 날짜={meta_b['dates'][0]} ~ {meta_b['dates'][-1]}")

    # 채널 수 검증
    if data_a.shape[1:] != data_b.shape[1:]:
        raise ValueError(
            f"H/W/C 불일치: A={data_a.shape[1:]}, B={data_b.shape[1:]}\n"
            "DIN mask 유무 차이일 수 있음 — 작은 쪽에 0 채널 추가 필요"
        )

    # 날짜 중복 제거 (B 우선)
    dates_a = set(meta_a["dates"])
    dates_b = set(meta_b["dates"])
    overlap = dates_a & dates_b
    if overlap:
        print(f"  ⚠️ 날짜 중복 {len(overlap)}일 — A에서 제거 (B 우선)")
        keep_a = [i for i, d in enumerate(meta_a["dates"]) if d not in overlap]
        data_a   = data_a[keep_a]
        labels_a = labels_a[keep_a]
        dates_a_list = [meta_a["dates"][i] for i in keep_a]
    else:
        dates_a_list = meta_a["dates"]

    # T 축 병합
    data_merged   = np.concatenate([data_a,   data_b],   axis=0)
    labels_merged = np.concatenate([labels_a, labels_b], axis=0)
    dates_merged  = dates_a_list + meta_b["dates"]

    # 날짜 기준 정렬
    order = sorted(range(len(dates_merged)), key=lambda i: dates_merged[i])
    data_merged   = data_merged[order]
    labels_merged = labels_merged[order]
    dates_merged  = [dates_merged[i] for i in order]

    T, H, W, C = data_merged.shape
    print(f"\n  병합 결과: ({T}, {H}, {W}, {C})")
    print(f"  날짜 범위: {dates_merged[0]} ~ {dates_merged[-1]}")

    # 라벨 분포
    label_counts = np.bincount(labels_merged.ravel(), minlength=5)
    total_px = label_counts.sum()
    names = ["정상", "초기", "경계", "진행", "심각"]
    print("\n  라벨 분포:")
    for i, (n, cnt) in enumerate(zip(names, label_counts)):
        bar = "█" * int(cnt / total_px * 30)
        print(f"    {n} : {cnt:>10,} ({cnt/total_px*100:5.1f}%) {bar}")

    # norm_stats 재산정
    print("\n  norm_stats 재산정 중...")
    channel_names = meta_b.get("channel_names", meta_a.get("channel_names", []))
    norm_stats = recompute_norm_stats(data_merged, channel_names)

    # 저장
    import zarr
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n  Zarr 저장 중: {out}/")
    z_data = zarr.open(
        str(out / "data.zarr"), mode="w",
        shape=data_merged.shape, dtype="float32",
        chunks=(min(72, T), H, W, C),
    )
    z_data[:] = data_merged

    z_labels = zarr.open(
        str(out / "labels.zarr"), mode="w",
        shape=labels_merged.shape, dtype="int8",
        chunks=(min(72, T), H, W),
    )
    z_labels[:] = labels_merged

    meta_out = {
        "version":        args.version,
        "shape":          list(data_merged.shape),
        "channel_names":  channel_names,
        "dates":          dates_merged,
        "norm_stats":     norm_stats,
        "grid_meta":      meta_b.get("grid_meta", meta_a.get("grid_meta", {})),
        "label_distribution": {
            n: int(c) for n, c in zip(names, label_counts)
        },
        "T_resolution":   "1day",
        "label_schema":   {0: "정상", 1: "초기", 2: "경계", 3: "진행", 4: "심각"},
        "source_cubes":   [args.cube_a, args.cube_b],
    }
    with open(out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 병합 완료 → {out}")
    print(f"\n학습 명령:")
    print(f"  uv run python scripts/train_real.py --cube-dir {out}")


if __name__ == "__main__":
    main()
