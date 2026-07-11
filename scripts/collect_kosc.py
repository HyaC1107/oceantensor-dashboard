"""GOCI-II (KOSC) nir_idx / chl_a 대량 수집 스크립트.

출력:      output/checkpoints/kosc.parquet
체크포인트: output/checkpoints/kosc_checkpoint/YYYYMMDD.parquet

사용:
    uv run python scripts/collect_kosc.py                          # 2021-11-01 ~ 오늘
    uv run python scripts/collect_kosc.py --start 2026-02-01       # 특정 시작일부터
    uv run python scripts/collect_kosc.py --merge-only             # 체크포인트 → parquet 병합만

특징:
    - 중단 후 재시작 가능 (날짜별 체크포인트)
    - DEFAULT_END = 오늘 날짜 자동 (하드코딩 없음)
    - 비수확기(6~8월) 자동 스킵 — channel_builder가 forward-fill로 처리
    - 구름 덮인 날 → None 반환 → 해당 날짜 미저장 (forward-fill 처리)
    - 진행률 / 성공률 / ETA 실시간 출력
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ── 경로 설정 ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ml.data.collectors.kosc_ml import KOSCCollector  # noqa: E402

# ── 상수 ───────────────────────────────────────────────────────────────────
DEFAULT_START = date(2021, 11, 1)
DEFAULT_END   = date.today()           # 하드코딩 제거 — 항상 오늘까지
SKIP_MONTHS   = frozenset({6, 7, 8})   # 비수확기 — nir_idx 변동 적고 학습 미사용
OUTPUT_DIR    = ROOT / "output" / "checkpoints"   # collect_only.py와 경로 통일
CKPT_DIR      = OUTPUT_DIR / "kosc_checkpoint"
OUT_PARQUET   = OUTPUT_DIR / "kosc.parquet"
SLEEP_BETWEEN_DAYS = 1.0  # 서버 부하 분산 (초)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── 날짜 범위 생성 ──────────────────────────────────────────────────────────
def _date_range(start: date, end: date) -> list[date]:
    dates = []
    d = start
    while d <= end:
        if d.month not in SKIP_MONTHS:
            dates.append(d)
        d += timedelta(days=1)
    return dates


# ── 체크포인트 ──────────────────────────────────────────────────────────────
def _done_dates(ckpt_dir: Path) -> set[date]:
    if not ckpt_dir.exists():
        return set()
    return {
        date.fromisoformat(p.stem)
        for p in ckpt_dir.glob("*.parquet")
    }


def _save_ckpt(df: pd.DataFrame, d: date, ckpt_dir: Path) -> None:
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ckpt_dir / f"{d.isoformat()}.parquet", index=False)


# ── 병합 ───────────────────────────────────────────────────────────────────
def merge_checkpoints(ckpt_dir: Path, out_path: Path) -> None:
    files = sorted(ckpt_dir.glob("*.parquet"))
    if not files:
        log.error("체크포인트 파일 없음 — 수집된 데이터가 없습니다")
        return

    log.info(f"체크포인트 {len(files)}개 병합 중...")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values(["date", "lat", "lon"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    total_rows = len(df)
    date_min   = df["date"].min().date()
    date_max   = df["date"].max().date()
    log.info(f"저장 완료: {out_path}")
    log.info(f"  기간: {date_min} ~ {date_max}")
    log.info(f"  총 행수: {total_rows:,} / 날짜 수: {df['date'].nunique()}")
    log.info(f"  nir_idx 범위: {df['nir_idx'].min():.4f} ~ {df['nir_idx'].max():.4f}")


# ── 메인 수집 루프 ──────────────────────────────────────────────────────────
def collect(start: date, end: date) -> None:
    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    all_dates  = _date_range(start, end)
    done       = _done_dates(CKPT_DIR)
    todo       = [d for d in all_dates if d not in done]

    total      = len(all_dates)
    n_done     = len(done)
    n_todo     = len(todo)

    log.info(f"수집 범위: {start} ~ {end}")
    log.info(f"대상 날짜(비수확기 제외): {total}일 / 완료: {n_done}일 / 남은: {n_todo}일")

    if not todo:
        log.info("모든 날짜 수집 완료 — --merge-only 로 parquet 생성하세요")
        return

    collector  = KOSCCollector()
    n_success  = 0
    n_cloud    = 0
    t_start    = time.time()

    for i, d in enumerate(todo, 1):
        date_str = d.strftime("%Y%m%d")

        try:
            df = collector.build_daily_composite(date_str)
        except KeyboardInterrupt:
            log.warning("중단됨 — 재시작 시 이어서 수집합니다")
            break
        except Exception as e:
            log.warning(f"{d}: 예외 발생 — {e}")
            df = None

        if df is not None and not df.empty:
            _save_ckpt(df, d, CKPT_DIR)
            n_success += 1
            rows = len(df)
            nir_mean = df["nir_idx"].mean()
            status = f"✅ {rows:,}행, nir_idx avg={nir_mean:.3f}"
        else:
            n_cloud += 1
            status = "☁️  구름/결측"

        # 진행률 + ETA
        elapsed  = time.time() - t_start
        avg_sec  = elapsed / i
        eta_sec  = avg_sec * (n_todo - i)
        eta_min  = int(eta_sec / 60)
        pct      = (n_done + i) / total * 100

        log.info(
            f"[{n_done+i:4d}/{total}] {d} {status} "
            f"| 성공률 {n_success}/{i} ({n_success/i:.0%}) "
            f"| ETA {eta_min}분 ({pct:.1f}%)"
        )

        time.sleep(SLEEP_BETWEEN_DAYS)

    # 최종 요약
    log.info("─" * 60)
    log.info(f"수집 완료: 성공 {n_success}일 / 구름·결측 {n_cloud}일")
    log.info(f"체크포인트 위치: {CKPT_DIR}")
    log.info("병합하려면: uv run python scripts/collect_kosc.py --merge-only")


# ── CLI ────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="GOCI-II nir_idx 수집")
    parser.add_argument("--start",      default=DEFAULT_START.isoformat(),
                        help="수집 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end",        default=DEFAULT_END.isoformat(),
                        help="수집 종료일 (YYYY-MM-DD)")
    parser.add_argument("--merge-only", action="store_true",
                        help="체크포인트 → kosc.parquet 병합만 실행")
    args = parser.parse_args()

    if args.merge_only:
        merge_checkpoints(CKPT_DIR, OUT_PARQUET)
        return

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)
    collect(start, end)

    # 수집 후 자동 병합
    done = _done_dates(CKPT_DIR)
    if done:
        log.info("\n자동 병합 시작...")
        merge_checkpoints(CKPT_DIR, OUT_PARQUET)


if __name__ == "__main__":
    main()
