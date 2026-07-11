"""공공 API 수집 → parquet 저장 (로컬 PC용).

사용:
    PYTHONPATH=. python scripts/collect_only.py
    PYTHONPATH=. python scripts/collect_only.py --days 365 --out-dir output/checkpoints

결과:
    output/checkpoints/
      ├── nifs.parquet
      ├── kma.parquet
      ├── koem.parquet
      ├── kwater.parquet
      ├── cmems.parquet      (--no-cmems 없을 때, CMEMS 표층 해류 current_u/v)
      └── sentinel.parquet   (--no-sentinel 없을 때)

이후 H100에서:
    scp -r output/checkpoints tta@123.41.22.216:/data/tta/shared/
    PYTHONPATH=. python scripts/build_from_parquet.py --checkpoint-dir /data/tta/shared/checkpoints
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from ml.data.collectors import fetch_nifs_df, fetch_kma_df, fetch_koem_df, fetch_kwater_df, fetch_cmems_df


def main():
    p = argparse.ArgumentParser(description="공공 API 수집 → parquet")
    p.add_argument("--days",        type=int, default=365,             help="수집 기간 (일) — start-date 지정 시 무시됨")
    p.add_argument("--start-date",  type=str, default=None,            help="수집 시작일 YYYY-MM-DD")
    p.add_argument("--end-date",    type=str, default=None,            help="수집 종료일 YYYY-MM-DD")
    p.add_argument("--out-dir",     type=str, default="output/checkpoints", help="저장 폴더")
    p.add_argument("--no-sentinel", action="store_true",               help="Sentinel-2 건너뜀")
    p.add_argument("--no-cmems",    action="store_true",               help="CMEMS 해류 건너뜀")
    args = p.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    period_desc = f"{args.start_date} ~ {args.end_date}" if args.start_date else f"최근 {args.days}일"
    print("=" * 60)
    print("공공 API 수집 시작")
    print(f"  수집 기간 : {period_desc}")
    print(f"  저장 경로 : {out}/")
    print("=" * 60)

    t_total = time.time()

    sd, ed = args.start_date, args.end_date

    print("\nNIFS 어장환경관측 수집...")
    t0 = time.time()
    nifs_df = fetch_nifs_df(days=args.days, start_date=sd, end_date=ed)
    nifs_df.to_parquet(out / "nifs.parquet", index=False)
    print(f"  → {len(nifs_df)}건 ({time.time()-t0:.1f}s) → nifs.parquet")

    print("KMA 기상 수집...")
    t0 = time.time()
    kma_df = fetch_kma_df(days=args.days, start_date=sd, end_date=ed)
    kma_df.to_parquet(out / "kma.parquet", index=False)
    print(f"  → {len(kma_df)}건 ({time.time()-t0:.1f}s) → kma.parquet")

    print("KOEM 해양환경 수집...")
    t0 = time.time()
    koem_df = fetch_koem_df(days=args.days, start_date=sd, end_date=ed)
    koem_df.to_parquet(out / "koem.parquet", index=False)
    print(f"  → {len(koem_df)}건 ({time.time()-t0:.1f}s) → koem.parquet")

    print("K-water 방류량 수집...")
    t0 = time.time()
    kwater_df = fetch_kwater_df(days=args.days, start_date=sd, end_date=ed)
    kwater_df.to_parquet(out / "kwater.parquet", index=False)
    print(f"  → {len(kwater_df)}건 ({time.time()-t0:.1f}s) → kwater.parquet")

    if not args.no_cmems:
        print("CMEMS 표층 해류 수집 (Copernicus Marine Service)...")
        t0 = time.time()
        try:
            # CMEMS는 큐브 전체 기간 커버 필요 — start_date 미지정 시 2021-11-01부터
            cmems_start = sd or "2021-11-01"
            cmems_end   = ed or date.today().isoformat()
            cmems_df = fetch_cmems_df(start_date=cmems_start, end_date=cmems_end)
            if not cmems_df.empty:
                cmems_df.to_parquet(out / "cmems.parquet", index=False)
                print(f"  → {len(cmems_df)}건 ({time.time()-t0:.1f}s) → cmems.parquet")
            else:
                print(f"  ⚠️ CMEMS 빈 결과 (계정/네트워크 확인)")
        except Exception as e:
            print(f"  ⚠️ CMEMS 실패 (건너뜀): {e}")
    else:
        print("CMEMS: --no-cmems 지정, 건너뜀")

    # KOSC (GOCI-II) — 느린 위성 수집, 별도 실행 권장
    # 실행: uv run python scripts/collect_kosc.py --start 2026-02-01
    # 결과: output/checkpoints/kosc.parquet (체크포인트 재시작 가능)
    if not (out / "kosc.parquet").exists():
        print("\n⚠️  kosc.parquet 없음 — nir_idx(ch28) 0값 처리됨")
        print("   → uv run python scripts/collect_kosc.py 로 수집 후 재빌드 필요")

    if not args.no_sentinel:
        print("Sentinel-2 NDCI 수집 (Element84 STAC)...")
        t0 = time.time()
        try:
            from ml.data.collectors.sentinel_ml import SentinelCollector
            s2_end   = ed or (date.today() - timedelta(days=1)).isoformat()
            s2_start = sd or (date.today() - timedelta(days=args.days)).isoformat()
            sc = SentinelCollector()
            sentinel_df = sc.fetch_date_range(s2_start, s2_end)
            sentinel_df.to_parquet(out / "sentinel.parquet", index=False)
            print(f"  → {len(sentinel_df)}건 ({time.time()-t0:.1f}s) → sentinel.parquet")
        except Exception as e:
            print(f"  ⚠️ Sentinel-2 실패 (건너뜀): {e}")
    else:
        print("Sentinel-2: --no-sentinel 지정, 건너뜀")

    print(f"\n✅ 수집 완료 ({time.time()-t_total:.1f}s)")
    print(f"\nH100 전송 명령:")
    print(f"  scp -r {out.resolve()} tta@123.41.22.216:/data/tta/shared/")
    print(f"\n보간 실행 명령 (H100에서):")
    print(f"  PYTHONPATH=. python scripts/build_from_parquet.py --checkpoint-dir /data/tta/shared/checkpoints")


if __name__ == "__main__":
    main()
