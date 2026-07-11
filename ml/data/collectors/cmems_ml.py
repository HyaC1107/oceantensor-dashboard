"""CMEMS 표층 해류 수집기 — ML 전용 (DB 없음, DataFrame 반환).

Copernicus Marine Service Global Ocean Physics Reanalysis/Interim 일별 표층 해류(uo, vo)
→ 일별 DataFrame 반환 (월별 집계 없음).
channel_builder.py의 _get_pts(kodc_df, tol_days=7)로 7일 스무딩 IDW 보간.
"""
from __future__ import annotations

import os

import pandas as pd

_REANALYSIS_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"    # 1993~2021-06 재분석
_INTERIM_ID    = "cmems_mod_glo_phy_myint_0.083deg_P1D-m"  # 2021-01~ 인터림 (약 2개월 지연)

_LAT_MIN, _LAT_MAX = 34.0, 37.0
_LON_MIN, _LON_MAX = 125.0, 128.0


def fetch_cmems_df(
    start_date: str,
    end_date: str,
    username: str | None = None,
    password: str | None = None,
) -> pd.DataFrame:
    """CMEMS 일별 표층 해류 DataFrame.

    Returns:
        Columns: date, lat, lon, current_u, current_v
        channel_builder.py의 kodc_df 자리에 대입 후 _get_pts(tol_days=7)로 사용.
        실패 시 빈 DataFrame 반환.
    """
    try:
        import copernicusmarine as cm
    except ImportError:
        print("[cmems_ml] copernicusmarine 패키지 없음 — uv add copernicusmarine")
        return pd.DataFrame()

    user = username or os.getenv("CMEMS_USER", "")
    pw   = password or os.getenv("CMEMS_PASSWORD", "")
    if not user or not pw:
        print("[cmems_ml] CMEMS_USER / CMEMS_PASSWORD 환경변수 미설정")
        return pd.DataFrame()

    dfs: list[pd.DataFrame] = []
    for dataset_id in [_REANALYSIS_ID, _INTERIM_ID]:
        try:
            ds = cm.open_dataset(
                dataset_id=dataset_id,
                variables=["uo", "vo"],
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
            avail = [v for v in ["uo", "vo", "mlotst"] if v in ds]
            df = ds[avail].to_dataframe().reset_index()
            df = df.rename(columns={
                "uo": "current_u", "vo": "current_v",
                "mlotst": "mld",
                "latitude": "lat", "longitude": "lon",
            }, errors="ignore")
            keep = ["time", "lat", "lon", "current_u", "current_v"]
            if "mld" in df.columns:
                keep.append("mld")
            df = df[keep].dropna(subset=["current_u", "current_v"])
            if not df.empty:
                print(f"[cmems_ml] {dataset_id}: {len(df):,}건")
                dfs.append(df)
        except Exception as e:
            print(f"[cmems_ml] {dataset_id} 건너뜀: {e}")

    if not dfs:
        print("[cmems_ml] 모든 데이터셋 실패 — 빈 DataFrame 반환")
        return pd.DataFrame()

    df_all = pd.concat(dfs, ignore_index=True)
    df_all["time"] = pd.to_datetime(df_all["time"])
    # 재분석+인터림 날짜 중복 시 재분석 우선 (앞에서 concat했으므로 keep="first")
    df_all = df_all.drop_duplicates(subset=["time", "lat", "lon"], keep="first")
    # channel_builder _get_pts가 "date" 컬럼으로 조회
    df_all = df_all.rename(columns={"time": "date"})

    result = df_all.sort_values(["date", "lat", "lon"]).reset_index(drop=True)
    print(f"[cmems_ml] 완료: {len(result):,}건 ({result['date'].min().date()} ~ {result['date'].max().date()})")
    return result
