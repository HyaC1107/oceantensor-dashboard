"""Sentinel-2 L2A 수집기 — NDCI (chl_a proxy) 추출.

데이터 소스: Element84 Earth Search STAC + AWS public COG (인증 불필요)
  STAC : https://earth-search.aws.element84.com/v1
  파일 : s3://sentinel-cogs (공개 버킷, /vsicurl/ 스트리밍)

NDCI = (B05 - B04) / (B05 + B04)
  B04: Red 665nm (10m)   — 황백화 시 흡수 감소 → 반사 증가
  B05: Red-edge 705nm (20m) — 클로로필 흡수 에지에 민감
  NDCI 범위: -1 ~ +1 (수체 양의 값, 클로로필 증가 시 상승)

반환: DataFrame(date, lat, lon, chl_a_s2)  ← channel_builder sentinel_df 인자와 동일 포맷

Sentinel-2 revisit ~5일. 채널 빌더에서 ±5일 tol_days로 보간 적용.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 서해안 김 양식 ROI [west, south, east, north] WGS84
ROI_BBOX = [125.3, 34.0, 128.0, 36.8]

STAC_URL   = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# SCL(Scene Classification Layer) 수체 픽셀 값
SCL_WATER = 6

# ROI 내 샘플링 격자 크기 (COG를 이 해상도로 리샘플)
# 100×100 → ~2.8km 간격, IDW 입력으로 충분
TARGET_H = 100
TARGET_W = 100

DEFAULT_MAX_CLOUD = 20   # cloud_cover < 20% 씬만 수집
DEFAULT_REVISIT   = 5    # Sentinel-2 재방문 주기 (일)


def _check_deps() -> None:
    missing = []
    try:
        import pystac_client  # noqa
    except ImportError:
        missing.append("pystac-client")
    try:
        import rasterio  # noqa
    except ImportError:
        missing.append("rasterio")
    if missing:
        raise ImportError(
            f"Sentinel-2 수집기 의존성 없음: {missing}\n"
            "설치: uv add " + " ".join(missing)
        )


def _read_band_to_grid(href: str, h: int = TARGET_H, w: int = TARGET_W) -> Optional[np.ndarray]:
    """
    COG URL → ROI 잘라서 (h, w) 격자로 리샘플.
    반환: float32 (h, w), 실패 시 None.
    """
    import rasterio
    import rasterio.enums
    from rasterio.windows import from_bounds as win_from_bounds
    from pyproj import Transformer

    vsi = f"/vsicurl/{href}" if href.startswith("http") else href
    try:
        with rasterio.open(vsi) as src:
            tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            west, south = tr.transform(ROI_BBOX[0], ROI_BBOX[1])
            east, north = tr.transform(ROI_BBOX[2], ROI_BBOX[3])

            win = win_from_bounds(west, south, east, north, src.transform)
            # 이미지 범위 클리핑
            col_off = max(0, int(win.col_off))
            row_off = max(0, int(win.row_off))
            col_end = min(src.width,  int(win.col_off + win.width))
            row_end = min(src.height, int(win.row_off + win.height))
            if col_end <= col_off or row_end <= row_off:
                return None
            win = rasterio.windows.Window(col_off, row_off,
                                          col_end - col_off,
                                          row_end - row_off)

            data = src.read(
                1, window=win,
                out_shape=(h, w),
                resampling=rasterio.enums.Resampling.average,
            )
        return data.astype(np.float32)
    except Exception as e:
        logger.debug(f"COG 읽기 실패 ({href[:70]}…): {e}")
        return None


def _make_roi_grid(h: int = TARGET_H, w: int = TARGET_W):
    """ROI 위경도 격자 생성. 반환: (lat_grid, lon_grid) shape (h, w)."""
    lats = np.linspace(ROI_BBOX[3], ROI_BBOX[1], h)  # north → south
    lons = np.linspace(ROI_BBOX[0], ROI_BBOX[2], w)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    return lat_grid, lon_grid


class SentinelCollector:
    """Sentinel-2 L2A NDCI 수집기."""

    def __init__(
        self,
        max_cloud_pct: int = DEFAULT_MAX_CLOUD,
        target_h: int = TARGET_H,
        target_w: int = TARGET_W,
    ):
        _check_deps()
        self.max_cloud_pct = max_cloud_pct
        self.target_h = target_h
        self.target_w = target_w

    # ------------------------------------------------------------------ #
    # STAC 검색
    # ------------------------------------------------------------------ #
    def _search(self, date_str: str):
        from pystac_client import Client
        catalog = Client.open(STAC_URL)
        all_items = list(catalog.search(
            collections=[COLLECTION],
            bbox=ROI_BBOX,
            datetime=f"{date_str}T00:00:00Z/{date_str}T23:59:59Z",
        ).items())
        # cloud_cover 후처리 필터 (STAC query extension 미지원 카탈로그 대응)
        items = [it for it in all_items
                 if it.properties.get("eo:cloud_cover", 100) < self.max_cloud_pct]
        logger.debug(f"[Sentinel] {date_str}: {len(items)}/{len(all_items)}개 (cloud<{self.max_cloud_pct}%)")
        return items

    # ------------------------------------------------------------------ #
    # 단일 씬 처리
    # ------------------------------------------------------------------ #
    def _process_item(self, item, date_str: str) -> Optional[pd.DataFrame]:
        assets = item.assets
        h, w = self.target_h, self.target_w

        def _href(key_candidates):
            for k in key_candidates:
                a = assets.get(k)
                if a is not None:
                    return a.href if hasattr(a, "href") else str(a)
            return None

        b04_href = _href(["red",      "B04"])
        b05_href = _href(["rededge1", "B05"])
        scl_href = _href(["scl",      "SCL"])

        if not b04_href or not b05_href:
            logger.debug(f"[Sentinel] {item.id}: B04/B05 에셋 없음")
            return None

        # B04 읽기 (10m → target grid)
        b04 = _read_band_to_grid(b04_href, h, w)
        if b04 is None:
            return None

        # B05 읽기 (20m → target grid, 같은 크기로 자동 맞춤)
        b05 = _read_band_to_grid(b05_href, h, w)
        if b05 is None:
            return None

        # L2A DN → surface reflectance (scale 0.0001, offset 0 for new baseline)
        # 0값 = no-data
        b04 = np.where(b04 == 0, np.nan, b04 * 0.0001)
        b05 = np.where(b05 == 0, np.nan, b05 * 0.0001)

        # SCL 수체 마스크
        water_mask = np.ones((h, w), dtype=bool)
        if scl_href:
            scl = _read_band_to_grid(scl_href, h, w)
            if scl is not None:
                water_mask = (np.round(scl).astype(int) == SCL_WATER)

        b04 = np.where(water_mask, b04, np.nan)
        b05 = np.where(water_mask, b05, np.nan)

        # NDCI = (B05 - B04) / (B05 + B04)
        with np.errstate(divide="ignore", invalid="ignore"):
            denom = b05 + b04
            ndci  = np.where(denom > 1e-6, (b05 - b04) / denom, np.nan)
        ndci = np.where(np.isfinite(ndci) & (np.abs(ndci) <= 1.0), ndci, np.nan)

        valid = np.isfinite(ndci)
        pct = valid.mean() * 100
        logger.debug(f"[Sentinel] {item.id}: 유효 픽셀 {pct:.1f}%")
        if pct < 1.0:
            return None

        lat_grid, lon_grid = _make_roi_grid(h, w)
        return pd.DataFrame({
            "date":     pd.Timestamp(date_str),
            "lat":      lat_grid[valid].ravel(),
            "lon":      lon_grid[valid].ravel(),
            "chl_a_s2": ndci[valid].ravel(),
        })

    # ------------------------------------------------------------------ #
    # 일별 합성
    # ------------------------------------------------------------------ #
    def fetch_daily_composite(self, date_str: str) -> pd.DataFrame:
        """날짜(YYYY-MM-DD) → cloud-free 일별 합성 DataFrame."""
        items = self._search(date_str)
        if not items:
            return pd.DataFrame()

        frames = [self._process_item(item, date_str) for item in items]
        frames = [f for f in frames if f is not None and len(f) > 0]
        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        # 같은 위치 중복 씬 → 중앙값 합성
        combined["_lr"] = combined["lat"].round(2)
        combined["_lc"] = combined["lon"].round(2)
        composite = (combined
                     .groupby(["_lr", "_lc"], as_index=False)
                     .agg(date=("date", "first"),
                          lat=("lat", "mean"),
                          lon=("lon", "mean"),
                          chl_a_s2=("chl_a_s2", "median"))
                     .drop(columns=["_lr", "_lc"]))
        logger.info(f"[Sentinel] {date_str}: {len(composite)}포인트 (씬 {len(frames)}개)")
        return composite

    # ------------------------------------------------------------------ #
    # 날짜 범위 수집
    # ------------------------------------------------------------------ #
    def fetch_date_range(
        self,
        start: str,
        end: str,
        revisit_days: int = DEFAULT_REVISIT,
        skip_offseason: bool = True,
    ) -> pd.DataFrame:
        """
        날짜 범위 → DataFrame.
        revisit_days: Sentinel-2 재방문 주기 간격으로 샘플링 (기본 5일).
        skip_offseason: 비수확기(5~9월) 건너뜀. 김 양식 시설은 10월~4월만 운영.
        """
        dates = pd.date_range(start, end, freq=f"{revisit_days}D")
        frames = []
        for dt in dates:
            if skip_offseason and dt.month in (5, 6, 7, 8, 9):
                continue
            df = self.fetch_daily_composite(dt.strftime("%Y-%m-%d"))
            if not df.empty:
                frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
