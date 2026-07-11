"""합성 데이터 ST-MMT 학습 + 평가 진입점 (H100 / 로컬 공용).

사용:
    PYTHONPATH=. python scripts/train_synth.py            # 기본 (cuda 있으면 cuda)
    PYTHONPATH=. python scripts/train_synth.py --device cpu --epochs 5

결과: checkpoints/synth/results.json 에 history + eval 지표 저장.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch

from ml.data.synth_generator import generate_ocean_cube
from ml.models.st_mmt import STMMT, OceanCubeDataset
from ml.training.trainer import Trainer


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--t-in", type=int, default=12)
    p.add_argument("--stride", type=int, default=3)
    p.add_argument("--T", type=int, default=240)
    p.add_argument("--hw", type=int, default=32)
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--n-layers", type=int, default=3)
    p.add_argument("--n-heads", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", default="checkpoints/synth")
    args = p.parse_args()

    torch.manual_seed(args.seed)
    print("=" * 60)
    print(f"디바이스: {args.device}")
    if args.device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print("=" * 60)

    # --- 1) 합성 데이터 ---
    t0 = time.time()
    cube, labels, meta = generate_ocean_cube(
        T=args.T, H=args.hw, W=args.hw, seed=args.seed
    )
    ds = OceanCubeDataset(cube, labels, t_in=args.t_in, stride=args.stride)
    print(f"[데이터] cube={meta['shape']} | 샘플 수={len(ds)} | {time.time()-t0:.1f}s")
    print(f"[데이터] 클래스 분포(정상/초기/경계/진행/심각)={meta['class_ratio']}")

    # --- 2) 모델 ---
    model = STMMT(
        in_channels=16,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        d_ff=args.d_model * 2,
        n_stages=5,
        patch_size=4,
    )
    print(f"[모델] STMMT params={model.count_params():,}")

    # --- 3) 학습 + 평가 ---
    trainer = Trainer(
        model=model,
        dataset=ds,
        save_dir=args.save_dir,
        device=args.device,
        lr=args.lr,
        batch_size=args.batch_size,
        epochs=args.epochs,
        n_stages=5,
    )
    t0 = time.time()
    result = trainer.fit()
    train_time = time.time() - t0

    # --- 4) 결과 저장 ---
    out = {
        "device": args.device,
        "gpu": torch.cuda.get_device_name(0) if args.device == "cuda" else None,
        "train_time_s": round(train_time, 1),
        "data_meta": meta,
        "model_params": model.count_params(),
        "config": vars(args),
        "eval": {k: v for k, v in result["eval"].items() if k != "report"},
        "report": result["eval"]["report"],
        "history": result["history"],
    }
    save_path = Path(args.save_dir) / "results.json"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("최종 지표 요약")
    print("=" * 60)
    ev = result["eval"]
    print(f"  Accuracy     : {ev['accuracy']:.4f}")
    print(f"  F1 (macro)   : {ev['f1_macro']:.4f}")
    print(f"  F1 (weighted): {ev['f1_weighted']:.4f}")
    print(f"  AUC (ovo)    : {ev['auc_ovo']:.4f}")
    print(f"  추론 지연 avg: {ev['avg_latency_ms']:.2f} ms | p95: {ev['p95_latency_ms']:.2f} ms")
    print(f"  학습 시간    : {train_time:.1f}s ({args.epochs} epochs)")
    print(f"  결과 저장    : {save_path}")


if __name__ == "__main__":
    main()
