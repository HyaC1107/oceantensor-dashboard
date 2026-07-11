"""history.json → loss curve 이미지 저장.

사용:
    uv run python scripts/plot_history.py --history checkpoints/real_v5/history.json
    uv run python scripts/plot_history.py --history checkpoints/real_v5/history.json --out report/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


LABEL_COLOR = {"train_loss": "#4C9BE8", "val_loss": "#E86B4C"}


def plot(history: list[dict], out_dir: Path, title: str = "") -> Path:
    epochs     = [r["epoch"]      for r in history]
    train_loss = [r["train_loss"] for r in history]
    val_loss   = [r["val_loss"]   for r in history]
    best_val   = min(val_loss)
    best_ep    = val_loss.index(best_val) + 1

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(title or f"학습 곡선  (총 {len(epochs)} epoch)", fontsize=14, y=1.01)

    # ── 왼쪽: loss curve ───────────────────────────────────
    ax = axes[0]
    ax.plot(epochs, train_loss, label="train loss",
            color=LABEL_COLOR["train_loss"], linewidth=2)
    ax.plot(epochs, val_loss,   label="val loss",
            color=LABEL_COLOR["val_loss"],   linewidth=2)
    ax.axvline(best_ep, linestyle="--", color="gray", alpha=0.6,
               label=f"best val epoch={best_ep} ({best_val:.4f})")
    ax.scatter([best_ep], [best_val], color="gold", zorder=5, s=80)
    ax.set_xlabel("Epoch"); ax.set_ylabel("Loss")
    ax.set_title("Loss Curve")
    ax.legend(fontsize=9); ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    # ── 오른쪽: train/val gap (과적합 모니터) ────────────────
    ax2 = axes[1]
    gap = [v - t for t, v in zip(train_loss, val_loss)]
    ax2.plot(epochs, gap, color="#9B59B6", linewidth=2)
    ax2.axhline(0, linestyle="--", color="gray", alpha=0.5)
    ax2.fill_between(epochs, gap, 0,
                     where=[g > 0 for g in gap],
                     alpha=0.15, color="#E86B4C", label="over-fitting zone")
    ax2.set_xlabel("Epoch"); ax2.set_ylabel("val - train loss")
    ax2.set_title("Generalization Gap")
    ax2.legend(fontsize=9); ax2.grid(alpha=0.3)
    ax2.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    fig.tight_layout()
    out_path = out_dir / "loss_curve.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"저장: {out_path}")
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--history", required=True, help="history.json 경로")
    p.add_argument("--out",     default=None,  help="저장 폴더 (기본: history.json 폴더)")
    p.add_argument("--title",   default="",    help="그래프 제목")
    args = p.parse_args()

    hist_path = Path(args.history)
    out_dir   = Path(args.out) if args.out else hist_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(hist_path, encoding="utf-8") as f:
        history = json.load(f)

    print(f"epoch 수: {len(history)}")
    print(f"best val: {min(r['val_loss'] for r in history):.4f} "
          f"@ epoch {min(range(len(history)), key=lambda i: history[i]['val_loss'])+1}")

    plot(history, out_dir, title=args.title or hist_path.parent.name)


if __name__ == "__main__":
    main()
