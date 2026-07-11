"""실데이터 ST-MMT 학습 — OceanTensorCube Zarr 기반.

사용 (로컬):
    PYTHONPATH=. python scripts/train_real.py --cube-dir output/cube_v1

사용 (H100):
    PYTHONPATH=. python scripts/train_real.py \
        --cube-dir /data/tta/shared/datasets/cube_v1 \
        --epochs 100 --batch-size 32 --device cuda

합성데이터와 차이:
    - 데이터: RealCubeDataset (Zarr + 공간 랜덤 크롭)
    - 입력 채널: 32 (합성은 16)
    - t_in: 24일 (합성은 12시간)
    - patch: 64×64 공간 크롭
    - 정규화: norm_stats.json z-score
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import torch

from ml.data.cube_builder import load_cube, RealCubeDataset
from ml.models.st_mmt import STMMT
from ml.training.trainer import Trainer


def main():
    p = argparse.ArgumentParser(description="실데이터 ST-MMT 학습")
    p.add_argument("--cube-dir",   type=str, required=True,         help="큐브 경로 (cube_v1/)")
    p.add_argument("--adi-path",   type=str,
                   default="/data/tta/cheolyoung/labels/adi_v7.zarr",
                   help="연속 ADI 회귀 타깃 zarr (T,H,W float32, IGNORE=-1)")
    p.add_argument("--device",     type=str,
                   default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--epochs",     type=int, default=50)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr",         type=float, default=1e-4)
    p.add_argument("--t-in",       type=int, default=24,            help="입력 타임스텝 (일)")
    p.add_argument("--t-out",      type=int, default=7,             help="미래 예측 지평 (일) — 조기경보 라벨 시퀀스 길이")
    p.add_argument("--stride",     type=int, default=6)
    p.add_argument("--patch-h",    type=int, default=64)
    p.add_argument("--patch-w",    type=int, default=64)
    p.add_argument("--d-model",    type=int, default=256)
    p.add_argument("--n-layers",   type=int, default=4)
    p.add_argument("--n-heads",    type=int, default=8)
    p.add_argument("--val-ratio",   type=float, default=0.2)
    p.add_argument("--save-dir",    type=str, default="checkpoints/real")
    p.add_argument("--dropout",      type=float, default=0.1, help="dropout 비율 (0.0=제거)")
    p.add_argument("--seed",        type=int, default=42)
    p.add_argument("--wandb",       action="store_true", help="wandb 로깅 활성화")
    p.add_argument("--wandb-name",  type=str, default=None, help="wandb run 이름")
    p.add_argument("--oversample-minor", type=int, default=2,
                   help="경고(1)+발생(2) 오버샘플링 배수 (1=비활성)")
    p.add_argument("--class-weights", type=float, nargs=3,
                   default=[0.25, 1.5, 2.5],
                   metavar=("W0", "W1", "W2"),
                   help="FocalLoss alpha [정상 경고 발생]")
    p.add_argument("--focal-gamma", type=float, default=3.0, help="FocalLoss gamma")
    p.add_argument("--val-start-date", type=str, default=None,
                   help="에피소드 홀드아웃: 이 날짜(YYYY-MM-DD) 이후 시작 윈도우=val, "
                        "스팬(t_in+t_out)이 이 날짜 전에 끝나는 윈도우=train, 경계 걸친 윈도우는 제외(purge). "
                        "미지정 시 기존 라벨별 80/20 분할.")
    p.add_argument("--rep-label", type=str, choices=["corner", "area"], default="corner",
                   help="윈도우 대표라벨 방식. corner=코너픽셀(0,0)만(구버전, 시즌 놓침) / "
                        "area=일별 이상픽셀 면적비율 기반(v14+, 3시즌 전체 인식)")
    p.add_argument("--rep-area-thresh", type=float, default=0.01,
                   help="area 방식: 미래창 내 단계별 이상픽셀 비율이 이 값 이상이면 해당 단계로 대표 (기본 1%%)")
    args = p.parse_args()

    torch.manual_seed(args.seed)
    print("=" * 60)
    print(f"실데이터 ST-MMT 학습")
    print(f"  디바이스  : {args.device}")
    if args.device == "cuda":
        print(f"  GPU       : {torch.cuda.get_device_name(0)}")
    print(f"  큐브 경로 : {args.cube_dir}")
    print("=" * 60)

    # ── 1. 큐브 로드 ────────────────────────────────────────────────────
    print("\n[1/4] 큐브 로드...")
    cube, labels, meta = load_cube(args.cube_dir)
    T, H, W, C = cube.shape
    print(f"  큐브: {cube.shape}  labels: {labels.shape}")
    print(f"  날짜: {meta['dates'][0]} ~ {meta['dates'][-1]}")
    print(f"  채널: {C}개")

    import numpy as np
    import zarr
    # 연속 ADI 회귀 타깃 로드 (labels.zarr와 100% 정합 검증됨 — verify_adi_repass 일치율 1.0)
    adi = zarr.open_array(args.adi_path, mode="r")[:].astype(np.float32)  # (T,H,W) IGNORE=-1
    assert adi.shape == (T, H, W), f"adi shape {adi.shape} != cube {(T, H, W)}"
    _av = adi[adi >= 0]
    print(f"  ADI 타깃: {args.adi_path} | 유효 min={_av.min():.2f} max={_av.max():.2f} mean={_av.mean():.2f}")

    valid_labels = labels.ravel()[labels.ravel() != -1]
    ld = np.bincount(valid_labels, minlength=4) if len(valid_labels) > 0 else np.zeros(4, dtype=int)
    ignore_count = np.sum(labels.ravel() == -1)
    names = ["정상","초기","경계","진행"]
    dist_dict = {n: int(c) for n, c in zip(names, ld)}
    dist_dict["IGNORE"] = int(ignore_count)
    print(f"  라벨 분포: {dist_dict}")

    # ── 1b. DIN 관측 마스크 채널 추가 (1D array — cube 복사 없음) ─────
    channel_names = list(meta["channel_names"])
    din_mask_1d: np.ndarray | None = None
    if "din" in channel_names:
        din_ch   = channel_names.index("din")
        din_vals = np.array(cube[:, 0, 0, din_ch], dtype=np.float32)  # zarr → 1D (T,)
        din_mask_1d = np.zeros(T, dtype=np.float32)
        din_mask_1d[0] = 1.0
        for ti in range(1, T):
            if not np.isclose(din_vals[ti], din_vals[ti - 1]):
                din_mask_1d[ti] = 1.0
        channel_names.append("din_mask")
        C += 1
        print(f"  DIN 관측 마스크 채널 추가 → C={C} (실측일: {int(din_mask_1d.sum())}일)")

    # ── 1c. 장기 누적 채널 & 미분 채널 추가 (In-place 대체로 메모리 보존) ──
    din_ch = channel_names.index("din")
    sst_ch = channel_names.index("sst")
    print("  장기 누적 및 미분 피처 연산 중 (In-place 메모리 절약 기법 적용)...")
    
    # 1) 일별 Deficit 계산 (din <= 70.0 μg/L 일 때 결핍 강도 축적)
    deficit_T = np.clip(70.0 - cube[:, :, :, din_ch], 0.0, None)  # (T, H, W)
    
    # 2) 수온(SST) 가중치 적용
    sst_T = cube[:, :, :, sst_ch]
    sst_mean_T = np.nanmean(np.where(np.isnan(sst_T), 12.0, sst_T), axis=(1, 2), keepdims=True)  # (T, 1, 1)
    weight_T = np.where(sst_mean_T >= 15.0, 1.5, np.where(sst_mean_T >= 10.0, 1.0, 0.7))  # (T, 1, 1)
    daily_score = deficit_T * weight_T  # (T, H, W)
    
    # 3) 30일 & 60일 누적 연산 (Prefix Sum 기법으로 O(1) 고속 연산)
    cumsum_daily = np.cumsum(daily_score, axis=0)
    deficit_30d = np.zeros_like(daily_score)
    deficit_30d[29:] = cumsum_daily[29:] - cumsum_daily[:-29]
    deficit_30d[:29] = cumsum_daily[:29]
    
    deficit_60d = np.zeros_like(daily_score)
    deficit_60d[59:] = cumsum_daily[59:] - cumsum_daily[:-59]
    deficit_60d[:59] = cumsum_daily[:59]
        
    # 4) DIN 1차 미분(기울기) 계산
    din_diff = np.zeros_like(cube[:, :, :, din_ch])
    din_diff[1:] = cube[1:, :, :, din_ch] - cube[:-1, :, :, din_ch]
    
    # 5) In-place 대체 (정답 누수/결과 채널들을 입력에서 파지하고 원인 장기 지수로 대체)
    replace_targets = [
        ("chlorophyll_a", "deficit_30d", deficit_30d),
        ("chl_7d_avg", "deficit_60d", deficit_60d),
        ("nir_7d_avg", "din_diff", din_diff)
    ]
    
    for old_name, new_name, arr in replace_targets:
        if old_name in channel_names:
            idx = channel_names.index(old_name)
            # 메모리 복사 없이 In-place 할당
            cube[:, :, :, idx] = arr
            # 이름 및 정규화 통계 업데이트
            channel_names[idx] = new_name
            arr_mean = float(np.mean(arr))
            arr_std  = float(np.std(arr))
            meta["norm_stats"][new_name] = {"mean": arr_mean, "std": arr_std}
            print(f"    채널 대체 완료: {old_name} ➡️ {new_name} (chIdx: {idx})")
            
    T, H, W, _ = cube.shape
    print(f"  피처 엔지니어링 완료 → C={C} (정규 채널 3개 In-place 대체 완료)")

    # ── 1d. 라벨 병합 제거 — ADI 회귀 전환 ────────────────────────────────────
    # 학습 타깃은 이제 연속 ADI(adi). labels(0/1/2/3)는 "층화분할 대표라벨"로만 사용.
    # 진행(3)을 경계(2)에 병합하지 않음 → 진행 구간이 독립 층으로 train/val 양쪽 보장(극단 ADI 커버리지↑).
    labels = np.copy(labels)

    # ── 2. Dataset — Stratified Temporal Split ──────────────────────────
    print("\n[2/4] 데이터셋 구성...")
    
    # [수정] 정상(0) 시점은 stride 간격으로 듬성듬성, 이상(1,2,3) 시점은 stride=1로 촘촘히 윈도우 수집
    # 미래 t_out일 예측: 대표라벨 = 미래창[t+t_in : t+t_in+t_out] 기준
    if args.rep_label == "area":
        # ── v14: 면적 기반 대표라벨 ──────────────────────────────────
        # 코너픽셀(0,0) 하나만 보던 구방식은 21-22시즌 전체 + 각 시즌 12~3월 진행/심화
        # 구간을 "정상"으로 오인(2026-07-05 진단: 이벤트시즌 346윈도우 중 40개만 dense).
        # 일별 단계별 이상픽셀 면적비율을 사전집계 → 미래창 내 max 비율 ≥ 임계면 해당 단계.
        print("  대표라벨: area 방식 — 일별 이상면적 사전집계 중...")
        _valid_cnt = (labels >= 0).sum(axis=(1, 2)).astype(np.float64)          # (T,)
        _frac = {}
        for _s in (1, 2, 3):
            _cnt = (labels >= _s).sum(axis=(1, 2)).astype(np.float64)           # (T,)
            _frac[_s] = np.where(_valid_cnt > 0, _cnt / np.maximum(_valid_cnt, 1.0), 0.0)

        def _win_label(t: int) -> int:
            d0, d1 = t + args.t_in, t + args.t_in + args.t_out
            if _valid_cnt[d0:d1].max() == 0:
                return -1  # 미래창 전체 무효 → IGNORE (윈도우 제외)
            for _s in (3, 2, 1):  # 높은 단계 우선
                if _frac[_s][d0:d1].max() >= args.rep_area_thresh:
                    return _s
            return 0
    else:
        # ── 구버전: 코너픽셀 대표라벨 (재현용으로만 유지) ─────────────
        def _win_label(t: int) -> int:
            return int(labels[t + args.t_in : t + args.t_in + args.t_out, 0, 0].max())

    all_t = []
    for t in range(0, T - args.t_in - args.t_out + 1):
        lbl = _win_label(t)
        if lbl == 0:
            if t % args.stride == 0:
                all_t.append(t)
        elif lbl in (1, 2, 3):
            all_t.append(t)

    date_labels = [_win_label(t) for t in all_t]
    # 라벨별로 따로 80/20 분할 → 경고/발생 모두 val에 포함
    from collections import defaultdict
    by_label: dict = defaultdict(list)
    for t, l in zip(all_t, date_labels):
        by_label[l].append(t)

    def _lbl_hist(ts: list[int]) -> dict:
        h: dict = {}
        for _t in ts:
            _l = _win_label(_t)
            h[_l] = h.get(_l, 0) + 1
        return dict(sorted(h.items()))

    if args.val_start_date:
        # ── 에피소드 홀드아웃 분할 (v13+) ─────────────────────────────
        # 시간 경계 하나로 절단: 안 본 시즌(에피소드)을 통째로 val에 격리.
        # 기존 라벨별 80/20은 같은 에피소드가 train/val 양쪽에 섞여
        # onset 지표가 "본 에피소드 인접" 성능으로 낙관 오염됨(2026-07-05 검증).
        dates = [str(d)[:10] for d in meta["dates"]]
        vi = next((i for i, d in enumerate(dates) if d >= args.val_start_date), None)
        assert vi is not None, f"--val-start-date {args.val_start_date}가 큐브 날짜범위({dates[0]}~{dates[-1]}) 밖"
        span = args.t_in + args.t_out
        train_t = sorted(t for t in all_t if t + span <= vi)   # 스팬 전체가 경계 이전
        val_t   = sorted(t for t in all_t if t >= vi)          # 시작이 경계 이후
        n_purged = len(all_t) - len(train_t) - len(val_t)      # 경계 걸침 → 제외
        print(f"  [episode-holdout] val_start={args.val_start_date}(t={vi}) | purge {n_purged}개")
        print(f"  train {len(train_t)}개 {_lbl_hist(train_t)} / val {len(val_t)}개 {_lbl_hist(val_t)}")
        assert any(_win_label(t) >= 1 for t in val_t), \
            "val에 이상(1/2/3) 윈도우가 0개 — val_start_date를 이벤트 시즌 앞으로 조정 필요"
        assert any(_win_label(t) >= 1 for t in train_t), \
            "train에 이상(1/2/3) 윈도우가 0개 — 학습 불가, val_start_date 조정 필요"
    else:
        # ── 기존: 라벨별로 따로 80/20 분할 ────────────────────────────
        train_t, val_t = [], []
        for lbl, ts in sorted(by_label.items()):
            cut = int(len(ts) * (1 - args.val_ratio))
            train_t += ts[:cut]
            val_t   += ts[cut:]
            print(f"  label={lbl}: {len(ts)}개 → train {cut} / val {len(ts)-cut}")
        train_t = sorted(train_t)
        val_t   = sorted(val_t)

    # 이상 구간(1/2/3) 오버샘플링 — train에만 적용, val은 그대로
    extra: list[int] = []
    _os_report = []
    for _lbl in (1, 2, 3):
        _lbl_train = [t for t in train_t if t in set(by_label.get(_lbl, []))]
        extra += _lbl_train * (args.oversample_minor - 1)
        _os_report.append(f"lbl{_lbl} {len(_lbl_train)}→{len(_lbl_train)*args.oversample_minor}")
    train_t = sorted(train_t + extra)
    print(f"  오버샘플링(×{args.oversample_minor}): {' / '.join(_os_report)} / train 총 {len(train_t)}개")

    ds_train = RealCubeDataset(
        cube=cube, labels=labels, adi=adi,
        norm_stats=meta["norm_stats"], channel_names=channel_names,
        t_in=args.t_in, t_out=args.t_out, stride=args.stride,
        patch_h=args.patch_h, patch_w=args.patch_w,
        augment=True, t_indices=train_t, din_mask=din_mask_1d,
    )
    ds_val = RealCubeDataset(
        cube=cube, labels=labels, adi=adi,
        norm_stats=meta["norm_stats"], channel_names=channel_names,
        t_in=args.t_in, t_out=args.t_out, stride=args.stride,
        patch_h=args.patch_h, patch_w=args.patch_w,
        augment=False, t_indices=val_t, din_mask=din_mask_1d,
    )
    print(f"  train: {len(ds_train)}샘플 / val: {len(ds_val)}샘플")
    print(f"  패치 크기: {args.patch_h}×{args.patch_w}, t_in={args.t_in}일")

    # ── 3. 모델 ────────────────────────────────────────────────────────
    print("\n[3/4] 모델 초기화...")
    model = STMMT(
        in_channels=C,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        d_ff=args.d_model * 2,
        n_stages=3,
        patch_size=4,
        t_out=args.t_out,
    )
    n_params = model.count_params()
    print(f"  STMMT params: {n_params:,}")

    # ── 4. 학습 — Trainer 내부 val_ratio로 분리 ───────────────────────
    print("\n[4/4] 학습 시작...")
    default_thresholds = {1: 0.15, 2: 0.30}
    print(f"  class_weights : {args.class_weights}")
    print(f"  focal_gamma   : {args.focal_gamma}")
    print(f"  thresholds    : {default_thresholds}")

    trainer = Trainer(
        model=model,
        dataset=ds_train,
        val_dataset=ds_val,
        save_dir=args.save_dir,
        device=args.device,
        lr=args.lr,
        batch_size=args.batch_size,
        epochs=args.epochs,
        patience=15,
        n_stages=3,
        use_wandb=args.wandb,
        wandb_project="hwangbaek",
        wandb_name=args.wandb_name or Path(args.save_dir).name,
        wandb_config=vars(args),
        class_weights=args.class_weights,
        focal_gamma=args.focal_gamma,
        thresholds=default_thresholds,
    )
    t0 = time.time()
    result = trainer.fit()
    train_time = time.time() - t0

    # ── 결과 저장 ───────────────────────────────────────────────────────
    out = {
        "device":       args.device,
        "gpu":          torch.cuda.get_device_name(0) if args.device == "cuda" else None,
        "train_time_s": round(train_time, 1),
        "cube_dir":     args.cube_dir,
        "cube_shape":   list(cube.shape),
        "model_params": n_params,
        "config":       vars(args),
        "eval":         result["eval"],
        "history":      result["history"],
        "data_source":  "real_public_api",
        "note": (
            "T=1day 해상도. DIN/DIP는 분기 조사 보간값으로 느린 변화 반영."
            " 위성 데이터 추가 시 T=1hour으로 업그레이드 예정."
        ),
    }

    save_path = Path(args.save_dir) / "results_real.json"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    ev = result["eval"]
    print("\n" + "=" * 60)
    print("최종 지표 요약 (실데이터 — ADI 회귀 멀티헤드)")
    print("=" * 60)
    print(f"  ADI MAE / RMSE      : {ev['adi_mae']:.4f} / {ev['adi_rmse']:.4f}")
    print(f"  warn(≥4)  AUC/AP/F1 : {ev['warn_auc']:.4f} / {ev['warn_ap']:.4f} / {ev['warn_f1']:.4f}  (양성률 {ev['warn_pos_rate']:.3f})")
    print(f"  severe(≥6) AUC/AP/F1: {ev['severe_auc']:.4f} / {ev['severe_ap']:.4f} / {ev['severe_f1']:.4f}  (양성률 {ev['severe_pos_rate']:.3f})")
    print(f"  warn↔severe 예측상관 : {ev['warn_severe_corr']:.4f}")
    print(f"  추론 지연(avg/p95)  : {ev['avg_latency_ms']:.1f} / {ev['p95_latency_ms']:.1f} ms")
    print(f"  학습 시간           : {train_time:.1f}s ({args.epochs} epochs)")
    print(f"  결과 저장           : {save_path}")


if __name__ == "__main__":
    main()
