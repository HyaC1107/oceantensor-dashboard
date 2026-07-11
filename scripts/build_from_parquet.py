"""parquet → 스트리밍 IDW 보간 → Zarr 저장 (H100용).

collect_only.py + collect_kosc.py로 수집한 parquet을 읽어 채널 빌드 + Zarr 저장.
메모리 사용량: 하루치 ~35MB (전체 큐브를 메모리에 올리지 않음).

V2 채널 구성 (31채널):
  ch00~08: sst/din/dip/sio2/np_ratio/salinity/precipitation/discharge/dist_estuary
  ch09   : solar_radiation (KMA 직접 측정값 — par_proxy 대체)
  ch10~18: chlorophyll_a/DO/current_u/current_v/water_depth/sst_anomaly/sst_7d_avg/days_since_rain/turbidity
  ch19~25: wind_speed/sin/cos/air_temp/ph/no3/nh4
  ch26~27: sst_gradient/salinity_3d_change
  ch28   : nir_idx (GOCI-II B865/B555 — kosc.parquet)
  ch29~30: month_sin/month_cos

제거됨 (V1 대비): tn_proxy, exposure_time, growth_stage, sentinel_ndci

사용 (로컬):
    PYTHONPATH=. python scripts/build_from_parquet.py

사용 (H100):
    PYTHONPATH=. python scripts/build_from_parquet.py \\
        --checkpoint-dir ~/cheolyoung/checkpoints \\
        --output-dir ~/cheolyoung/output \\
        --version v4

결과:
    output/cube_v4/
      ├── data.zarr      (T, 128, 128, 31) float32
      ├── labels.zarr    (T, 128, 128)     int8   ← cube_v4 자체 생성 (T=1691, cube_v3 재사용 불가)
      └── meta.json

학습 명령:
    PYTHONPATH=. python scripts/train_real.py --cube-dir output/cube_v4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import pandas as pd

from ml.data.channel_builder import build_channels_to_zarr


def main():
    p = argparse.ArgumentParser(description="parquet → 스트리밍 보간 → Zarr (V2 31채널)")
    p.add_argument("--checkpoint-dir", type=str, default="output/cube_v3_parquet",
                   help="parquet 폴더 (nifs/kma/koem/kwater/kosc/cmems.parquet)")
    p.add_argument("--output-dir",     type=str, default="output",
                   help="Zarr 저장 상위 경로")
    p.add_argument("--version",        type=str, default="v4",
                   help="큐브 버전 태그 (출력 폴더명: cube_<version>)")
    p.add_argument("--grid-h",         type=int, default=128, help="격자 H")
    p.add_argument("--grid-w",         type=int, default=128, help="격자 W")
    p.add_argument("--start-date",     type=str, default=None, help="시작일 YYYY-MM-DD")
    p.add_argument("--end-date",       type=str, default=None, help="종료일 YYYY-MM-DD")
    args = p.parse_args()

    ckpt = Path(args.checkpoint_dir)
    out  = Path(args.output_dir) / f"cube_{args.version}"
    out.mkdir(parents=True, exist_ok=True)

    zarr_data_path   = str(out / "data.zarr")
    zarr_labels_path = str(out / "labels.zarr")

    print("=" * 60)
    print(f"OceanTensorCube V2 스트리밍 빌드 — cube_{args.version}")
    print(f"  parquet 경로 : {ckpt}/")
    print(f"  격자 크기    : {args.grid_h} × {args.grid_w}")
    print(f"  출력 경로    : {out}/")
    print("=" * 60)

    # ── parquet 로드 ──────────────────────────────────────────────────────
    def load(name: str) -> pd.DataFrame:
        path = ckpt / f"{name}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            print(f"  {name}.parquet → {len(df):,}건")
            return df
        print(f"  ⚠️  {name}.parquet 없음 — 빈 DataFrame 사용")
        return pd.DataFrame()

    print("\n[1/2] parquet 로드...")
    nifs_df   = load("nifs")
    kma_df    = load("kma")
    koem_df   = load("koem")
    kwater_df = load("kwater")
    kosc_df   = load("kosc")   # GOCI-II nir_idx + chl_a (V2 ch28)
    if (ckpt / "cmems.parquet").exists():
        kodc_df = load("cmems")   # CMEMS 표층 해류 (current_u/v, month 기반)
    elif (ckpt / "kodc.parquet").exists():
        kodc_df = load("kodc")    # 레거시 KODC 수동 다운로드
    else:
        kodc_df = None
        print("  ⚠️  해류 데이터 없음 (ch12/13 NaN) — collect_only.py로 cmems 수집 필요")

    # sentinel_df: V2에서 제거 (커버리지 50% 미만, nir_idx로 대체)

    total = sum(len(df) for df in [nifs_df, kma_df, koem_df, kwater_df] if not df.empty)
    if total == 0:
        print("\n❌ 수집 데이터가 없습니다. collect_only.py를 먼저 실행하세요.")
        sys.exit(1)

    # ── 스트리밍 보간 + Zarr 저장 ──────────────────────────────────────────
    print(f"\n[2/2] 스트리밍 IDW 보간 + Zarr 저장 중...")
    t0 = time.time()
    result = build_channels_to_zarr(
        nifs_df=nifs_df,
        kma_df=kma_df,
        koem_df=koem_df,
        kwater_df=kwater_df,
        kosc_df=kosc_df,
        kodc_df=kodc_df,
        sentinel_df=None,          # V2: sentinel 제거
        zarr_data_path=zarr_data_path,
        zarr_labels_path=zarr_labels_path,
        start_date=args.start_date,
        end_date=args.end_date,
        grid_h=args.grid_h,
        grid_w=args.grid_w,
    )
    elapsed = time.time() - t0

    # ── meta.json 저장 ────────────────────────────────────────────────────
    meta = {
        "version":        args.version,
        "schema_version": "v2",
        "n_channels":     len(result["channel_names"]),
        "shape":          [len(result["dates"]), args.grid_h, args.grid_w, len(result["channel_names"])],
        "channel_names":  result["channel_names"],
        "dates":          result["dates"],
        "norm_stats":     result["norm_stats"],
        "grid_meta":      result["grid_meta"],
        "label_distribution": result["label_distribution"],
        "T_resolution":   "1day",
        # 4단계 라벨 (이벤트 이력 기반, 발생 후 경과 주차로 결정)
        "label_schema":   {0: "정상", 1: "초기 (0~4주)", 2: "활성 (4~10주)", 3: "심화 (10주+)"},
        "label_note":     "labels.zarr는 cube_v4 자체 생성 (T=1691) — cube_v3(T=1553)과 T 달라 재사용 불가",
        "removed_channels": ["tn_proxy", "exposure_time", "growth_stage", "sentinel_ndci"],
        "added_channels":   ["solar_radiation (par_proxy 대체)", "month_sin", "month_cos"],
    }
    with open(out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── 요약 출력 ────────────────────────────────────────────────────────
    T, H, W, C = meta["shape"]
    lbl = result["label_distribution"]

    print("\n" + "=" * 60)
    print(f"빌드 완료 — cube_{args.version} (V2 {C}채널)")
    print("=" * 60)
    print(f"  큐브 크기  : ({T}, {H}, {W}, {C})  T×H×W×C")
    print(f"  저장 경로  : {out}")
    print(f"  총 소요    : {elapsed:.1f}s ({elapsed/60:.1f}분)")
    print("\n  라벨 분포:")
    for name, cnt in lbl.items():
        total_px = T * H * W
        pct = cnt / total_px * 100 if total_px > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"    {name:6s}: {cnt:10,d} ({pct:5.1f}%) {bar}")
    print(f"\n  학습 명령:")
    print(f"    PYTHONPATH=. python scripts/train_real.py --cube-dir {out}")


if __name__ == "__main__":
    main()
