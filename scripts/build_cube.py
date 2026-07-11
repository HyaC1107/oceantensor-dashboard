"""OceanTensorCube 빌드 스크립트 — 공공API 수집 → Zarr 저장.

사용:
    PYTHONPATH=. python scripts/build_cube.py
    PYTHONPATH=. python scripts/build_cube.py --days 365 --grid-h 512 --grid-w 512
    PYTHONPATH=. python scripts/build_cube.py --no-sentinel   # Sentinel-2 건너뜀
    PYTHONPATH=. python scripts/build_cube.py --dry-run       # API 호출 없이 구조만 확인

결과: output/cube_v1/ (또는 --output-dir 지정)
채널 수: 31 V2 (par_proxy→solar_radiation, tn_proxy/exposure_time/growth_stage/sentinel_ndci 제거, month_sin/cos 추가)
H100 업로드:
    scp -r output/cube_v1 tta@123.41.22.216:/data/tta/shared/datasets/
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from ml.data.collectors import fetch_nifs_df, fetch_kma_df, fetch_koem_df, fetch_kwater_df
from ml.data.collectors.sentinel_ml import SentinelCollector
from ml.data.channel_builder import build_channels
from ml.data.cube_builder import save_cube


def main():
    p = argparse.ArgumentParser(description="OceanTensorCube 빌드")
    p.add_argument("--days",       type=int,   default=365,          help="수집 기간 (일)")
    p.add_argument("--grid-h",     type=int,   default=128,          help="격자 H (기본 128, 최대 512)")
    p.add_argument("--grid-w",     type=int,   default=128,          help="격자 W (기본 128, 최대 512)")
    p.add_argument("--start-date", type=str,   default=None,         help="시작일 YYYY-MM-DD")
    p.add_argument("--end-date",   type=str,   default=None,         help="종료일 YYYY-MM-DD")
    p.add_argument("--output-dir", type=str,   default="output",     help="저장 경로")
    p.add_argument("--version",    type=str,   default="v1",         help="큐브 버전 태그")
    p.add_argument("--dry-run",     action="store_true",              help="API 호출 없이 구조만 확인")
    p.add_argument("--no-sentinel", action="store_true",              help="Sentinel-2 수집 건너뜀 (의존성 없거나 느릴 때)")
    args = p.parse_args()

    print("=" * 60)
    print("OceanTensorCube 빌드 시작")
    print(f"  수집 기간  : {args.days}일")
    print(f"  격자 크기  : {args.grid_h} × {args.grid_w}")
    print(f"  출력 경로  : {args.output_dir}/cube_{args.version}/")
    print("=" * 60)

    if args.dry_run:
        print("[DRY RUN] API 키 및 의존성 확인만 합니다.")
        keys = {
            "NIFS_API_KEY_femoSeaList": os.getenv("NIFS_API_KEY_femoSeaList", ""),
            "ServiceKey (KMA/KOEM)":   os.getenv("ServiceKey", ""),
        }
        for k, v in keys.items():
            status = "✅ 있음" if v else "❌ 없음"
            print(f"  {k}: {status}")
        if not args.no_sentinel:
            try:
                SentinelCollector()
                print("  Sentinel-2 의존성: ✅ pystac-client + rasterio 설치됨")
            except ImportError as e:
                print(f"  Sentinel-2 의존성: ❌ {e}")
        return

    t_total = time.time()

    # ── 1. 데이터 수집 ──────────────────────────────────────────────────
    print("\n[1/4] 공공 API 수집 중...")
    t0 = time.time()

    print("  NIFS 어장환경관측 수집...")
    nifs_df = fetch_nifs_df(days=args.days)
    print(f"  → {len(nifs_df)}건")

    print("  KMA 기상 수집...")
    kma_df = fetch_kma_df(days=args.days)
    print(f"  → {len(kma_df)}건")

    print("  KOEM 해양환경 수집...")
    koem_df = fetch_koem_df(days=args.days)
    print(f"  → {len(koem_df)}건")

    print("  K-water 방류량 수집...")
    kwater_df = fetch_kwater_df(days=args.days)
    print(f"  → {len(kwater_df)}건")

    # Sentinel-2 수집 (--no-sentinel 없을 때)
    sentinel_df = None
    if not args.no_sentinel:
        print("  Sentinel-2 NDCI 수집 (Element84 STAC)...")
        try:
            from datetime import date, timedelta
            s2_end   = (date.today() - timedelta(days=1)).isoformat()
            s2_start = (date.today() - timedelta(days=args.days)).isoformat()
            sc = SentinelCollector()
            sentinel_df = sc.fetch_date_range(s2_start, s2_end)
            print(f"  → {len(sentinel_df)}건 (Sentinel-2 NDCI 포인트)")
        except Exception as e:
            print(f"  ⚠️ Sentinel-2 수집 실패 (건너뜀): {e}")
            sentinel_df = None
    else:
        print("  Sentinel-2: --no-sentinel 지정, 건너뜀")

    t_collect = time.time() - t0
    total_rows = len(nifs_df) + len(kma_df) + len(koem_df) + len(kwater_df)

    if total_rows == 0:
        print("\n❌ 수집된 데이터가 없습니다. API 키를 .env에 설정하세요.")
        print("   필요 키: NIFS_API_KEY_femoSeaList, ServiceKey")
        sys.exit(1)

    print(f"  수집 완료: {total_rows}건 합계, {t_collect:.1f}s")

    # ── 2. 채널 빌드 (IDW 보간) ─────────────────────────────────────────
    print("\n[2/4] 채널 빌드 + IDW 보간 중...")
    t0 = time.time()
    result = build_channels(
        nifs_df=nifs_df,
        kma_df=kma_df,
        koem_df=koem_df,
        kwater_df=kwater_df,
        sentinel_df=sentinel_df,
        start_date=args.start_date,
        end_date=args.end_date,
        grid_h=args.grid_h,
        grid_w=args.grid_w,
    )
    t_build = time.time() - t0
    print(f"  빌드 완료: {t_build:.1f}s")

    # ── 3. Zarr 저장 ────────────────────────────────────────────────────
    print("\n[3/4] Zarr 저장 중...")
    t0 = time.time()
    out_path = save_cube(result, args.output_dir, args.version)
    t_save = time.time() - t0
    print(f"  저장 완료: {out_path} ({t_save:.1f}s)")

    # ── 4. 요약 ─────────────────────────────────────────────────────────
    cube = result["cube"]
    labels = result["labels"]
    import numpy as np
    label_dist = np.bincount(labels.ravel(), minlength=5)
    label_pct  = label_dist / label_dist.sum() * 100

    print("\n" + "=" * 60)
    print("빌드 완료 요약")
    print("=" * 60)
    print(f"  큐브 크기  : {cube.shape}  (T×H×W×C)")
    print(f"  저장 경로  : {out_path}")
    print(f"  총 소요    : {time.time()-t_total:.1f}s")
    print("\n  라벨 분포:")
    for i, (name, cnt, pct) in enumerate(
        zip(["정상","초기","경계","진행","심각"], label_dist, label_pct)
    ):
        bar = "█" * int(pct / 2)
        print(f"    {i}-{name:3s}: {cnt:8,d} ({pct:5.1f}%) {bar}")

    print(f"\n  H100 업로드 명령:")
    print(f"    scp -r {out_path} tta@123.41.22.216:/data/tta/shared/datasets/")
    print(f"\n  학습 명령:")
    print(f"    PYTHONPATH=. python scripts/train_real.py --cube-dir {out_path}")


if __name__ == "__main__":
    main()
