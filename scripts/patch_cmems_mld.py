"""기존 cmems.parquet에 mld(mlotst) 컬럼만 추가 패치.

기존 current_u/v 데이터를 재수집하지 않고, mlotst만 별도 수집 후
date+lat+lon 기준으로 merge해서 cmems.parquet를 업데이트한다.

사용:
    PYTHONPATH=. uv run python scripts/patch_cmems_mld.py
    PYTHONPATH=. uv run python scripts/patch_cmems_mld.py --out-dir output/checkpoints
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pandas as pd

_REANALYSIS_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
_INTERIM_ID    = "cmems_mod_glo_phy_myint_0.083deg_P1D-m"

_LAT_MIN, _LAT_MAX = 34.0, 37.0
_LON_MIN, _LON_MAX = 125.0, 128.0


def fetch_mld(start_date: str, end_date: str, user: str, pw: str) -> pd.DataFrame:
    try:
        import copernicusmarine as cm
    except ImportError:
        print("[patch] copernicusmarine 없음 — uv add copernicusmarine")
        return pd.DataFrame()

    dfs: list[pd.DataFrame] = []
    for dataset_id in [_REANALYSIS_ID, _INTERIM_ID]:
        try:
            ds = cm.open_dataset(
                dataset_id=dataset_id,
                variables=["mlotst"],
                minimum_latitude=_LAT_MIN,
                maximum_latitude=_LAT_MAX,
                minimum_longitude=_LON_MIN,
                maximum_longitude=_LON_MAX,
                start_datetime=f"{start_date}T00:00:00",
                end_datetime=f"{end_date}T23:59:59",
                minimum_depth=0.0,
                maximum_depth=1.0,
                username=user,
                password=pw,
            )
            if "depth" in ds.dims:
                ds = ds.isel(depth=0)
            df = ds[["mlotst"]].to_dataframe().reset_index()
            df = df.rename(columns={
                "mlotst": "mld",
                "latitude": "lat",
                "longitude": "lon",
            }, errors="ignore")
            df = df[["time", "lat", "lon", "mld"]].dropna(subset=["mld"])
            if not df.empty:
                print(f"[patch] {dataset_id}: {len(df):,}건")
                dfs.append(df)
        except Exception as e:
            print(f"[patch] {dataset_id} 건너뜀: {e}")

    if not dfs:
        return pd.DataFrame()

    df_all = pd.concat(dfs, ignore_index=True)
    df_all["time"] = pd.to_datetime(df_all["time"])
    df_all = df_all.drop_duplicates(subset=["time", "lat", "lon"], keep="first")
    df_all = df_all.rename(columns={"time": "date"})
    return df_all.sort_values(["date", "lat", "lon"]).reset_index(drop=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="output/checkpoints")
    args = p.parse_args()

    out_dir = ROOT / args.out_dir
    cmems_path = out_dir / "cmems.parquet"

    if not cmems_path.exists():
        print(f"[patch] {cmems_path} 없음 — 먼저 collect_only.py 실행")
        sys.exit(1)

    user = os.getenv("CMEMS_USER", "")
    pw   = os.getenv("CMEMS_PASSWORD", "")
    if not user or not pw:
        print("[patch] .env에 CMEMS_USER / CMEMS_PASSWORD 필요")
        sys.exit(1)

    print("[patch] 기존 cmems.parquet 로드 중...")
    base = pd.read_parquet(cmems_path)
    print(f"[patch] 기존: {base.shape}, 컬럼: {base.columns.tolist()}")

    if "mld" in base.columns:
        print("[patch] 이미 mld 컬럼 있음 — 종료")
        sys.exit(0)

    start_date = str(base["date"].min().date())
    end_date   = str(base["date"].max().date())
    print(f"[patch] 수집 기간: {start_date} ~ {end_date}")

    print("[patch] CMEMS mlotst 수집 시작...")
    mld_df = fetch_mld(start_date, end_date, user, pw)
    if mld_df.empty:
        print("[patch] mlotst 수집 실패 — 종료")
        sys.exit(1)

    print(f"[patch] mlotst 수집 완료: {len(mld_df):,}건")

    # lat/lon 반올림 맞추기 (부동소수점 키 불일치 방지)
    base["lat"]   = base["lat"].round(6)
    base["lon"]   = base["lon"].round(6)
    mld_df["lat"] = mld_df["lat"].round(6)
    mld_df["lon"] = mld_df["lon"].round(6)

    print("[patch] date+lat+lon 기준 merge 중...")
    merged = base.merge(mld_df, on=["date", "lat", "lon"], how="left")
    print(f"[patch] merge 완료: {merged.shape}")
    filled = merged["mld"].notna().sum()
    print(f"[patch] mld 채워진 행: {filled:,} / {len(merged):,} ({filled/len(merged)*100:.1f}%)")

    # 백업
    backup = cmems_path.with_suffix(".parquet.bak")
    shutil.copy2(cmems_path, backup)
    print(f"[patch] 백업: {backup}")

    merged.to_parquet(cmems_path, index=False)
    print(f"[patch] 저장 완료: {cmems_path}")


if __name__ == "__main__":
    main()
