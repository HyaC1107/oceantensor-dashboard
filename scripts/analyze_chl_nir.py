"""현재 라벨 기준 Chl-a / NIR 분포 분석 — 실측값 기반 임계값 도출용.

실행:
    cd ~/cheolyoung && uv run python scripts/analyze_chl_nir.py --cube-dir output/cube_v4
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ml.data.cube_builder import load_cube

LABEL_NAMES = ["정상(0)", "초기(1)", "경계(2)", "진행(3)"]


def percentiles(arr):
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {}
    return {
        "n":    len(arr),
        "mean": round(float(arr.mean()), 4),
        "std":  round(float(arr.std()),  4),
        "p10":  round(float(np.percentile(arr, 10)), 4),
        "p25":  round(float(np.percentile(arr, 25)), 4),
        "p50":  round(float(np.percentile(arr, 50)), 4),
        "p75":  round(float(np.percentile(arr, 75)), 4),
        "p90":  round(float(np.percentile(arr, 90)), 4),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cube-dir", required=True)
    args = p.parse_args()

    cube, labels, meta = load_cube(args.cube_dir)
    T, H, W, C = cube.shape
    ch = list(meta["channel_names"])

    chl_idx = ch.index("chlorophyll_a")
    nir_idx = ch.index("nir_idx")

    # 날짜별 대표값: 공간 중앙값 (ROI 전체 평균도 가능)
    day_labels = labels[:, 0, 0].astype(int)  # (T,)

    # 전체 공간 평균 (마스크 픽셀 제외)
    chl_daily = np.nanmean(cube[:, :, :, chl_idx].reshape(T, -1), axis=1)
    nir_daily = np.nanmean(cube[:, :, :, nir_idx].reshape(T, -1), axis=1)

    print("=" * 65)
    print("Chl-a / NIR_idx 라벨별 분포 분석")
    print("=" * 65)

    results = {}
    for lbl, name in enumerate(LABEL_NAMES):
        mask = (day_labels == lbl)
        chl_vals = chl_daily[mask]
        nir_vals = nir_daily[mask]
        pc = percentiles(chl_vals)
        pn = percentiles(nir_vals)
        results[name] = {"chl_a": pc, "nir_idx": pn}

        print(f"\n[{name}] — {pc.get('n',0)}일")
        print(f"  Chl-a  : mean={pc.get('mean','?'):6.3f} | "
              f"p25={pc.get('p25','?'):6.3f} p50={pc.get('p50','?'):6.3f} p75={pc.get('p75','?'):6.3f}")
        print(f"  NIR_idx: mean={pn.get('mean','?'):6.3f} | "
              f"p25={pn.get('p25','?'):6.3f} p50={pn.get('p50','?'):6.3f} p75={pn.get('p75','?'):6.3f}")

    # 정상 대비 감소율 추정
    chl_base = results["정상(0)"]["chl_a"]["p50"]
    nir_base = results["정상(0)"]["nir_idx"]["p50"]
    print("\n" + "=" * 65)
    print("정상(0) p50 기준 감소율")
    print("=" * 65)
    print(f"  Chl_base={chl_base:.3f}  NIR_base={nir_base:.3f}")
    for lbl, name in enumerate(LABEL_NAMES[1:], 1):
        c = results[name]["chl_a"].get("p50")
        n = results[name]["nir_idx"].get("p50")
        if c:
            print(f"  {name}: Chl-a {(1-c/chl_base)*100:+.1f}%  "
                  f"NIR {(1-n/nir_base)*100:+.1f}%")

    # 임계값 후보 자동 도출
    print("\n" + "=" * 65)
    print("임계값 후보 (p50 기준 경계)")
    print("=" * 65)

    def mid(a, b):
        return round((a + b) / 2, 3) if a and b else None

    c0 = results["정상(0)"]["chl_a"]["p50"]
    c1 = results["초기(1)"]["chl_a"].get("p50")
    c2 = results["경계(2)"]["chl_a"].get("p50")
    c3 = results["진행(3)"]["chl_a"].get("p50")

    n0 = results["정상(0)"]["nir_idx"]["p50"]
    n1 = results["초기(1)"]["nir_idx"].get("p50")
    n2 = results["경계(2)"]["nir_idx"].get("p50")
    n3 = results["진행(3)"]["nir_idx"].get("p50")

    t01_c = mid(c0, c1);  t12_c = mid(c1, c2);  t23_c = mid(c2, c3)
    t01_n = mid(n0, n1);  t12_n = mid(n1, n2);  t23_n = mid(n2, n3)

    print(f"  정상↔초기  : Chl-a={t01_c}  NIR={t01_n}")
    print(f"  초기↔경계  : Chl-a={t12_c}  NIR={t12_n}")
    print(f"  경계↔진행  : Chl-a={t23_c}  NIR={t23_n}")

    out = {
        "stats": results,
        "chl_base_p50": chl_base, "nir_base_p50": nir_base,
        "thresholds_candidate": {
            "chl_a":   {"정상↔초기": t01_c, "초기↔경계": t12_c, "경계↔진행": t23_c},
            "nir_idx": {"정상↔초기": t01_n, "초기↔경계": t12_n, "경계↔진행": t23_n},
        }
    }
    out_path = Path(args.cube_dir) / "chl_nir_analysis.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
