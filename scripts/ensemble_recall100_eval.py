#!/usr/bin/env python3
"""v19 × v13 스코어 레벨 앙상블 — 재현율100% F1 오프라인 평가.

v19 모델·데이터는 일절 건드리지 않는다. 필요한 입력은 김광진 측이 내보낸
윈도우별 검증 CSV 하나와, 우리 v13 예측(서빙 팩 또는 H100 재추출 CSV)이다.

입력 형식
---------
--v19-csv : window_id,target_date,region,lat,lon,y_true,v19_score
            (재현율100% F1 0.8953을 산출한 그 검증셋 그대로. 서천 외부검증셋도 동일 형식)
--v13-src : (a) v13_predictions*.json 서빙 팩  또는
            (b) CSV target_date,gid,warn  (H100 재추출본 — 2021 완도·목포는 팩에 없어 이쪽)

매칭: 각 v19 윈도우의 (lat,lon) → 최근접 우리 어장 gid → target_date의 warn.
      매칭 실패/무신호(전기간 warn<0.01인 死어장)는 별도 카운트해 보고한다.

평가: 스코어를 각각 검증셋 내 랭크 정규화(v13 이진 포화 왜곡 방지) 후
      score = α·v19 + (1-α)·v13 를 α∈{0,0.1,...,1.0}로 스윕.
      각 α에서 재현율 100%를 만족하는 임계값 중 F1 최대 지점을 보고.
      기준선 = α=1.0(v19 단독). α<1에서 F1이 오르면 앙상블 가치 있음.

사용 예
-------
uv run python scripts/ensemble_recall100_eval.py \
    --v19-csv v19_val_windows.csv \
    --v13-src app/data/v13_predictions_all.json \
    --out analysis_ensemble_result.json
"""
import argparse, csv, json, math, sys
from collections import defaultdict


def rank_normalize(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    n = len(xs)
    for rank, i in enumerate(order):
        r[i] = rank / (n - 1) if n > 1 else 0.5
    return r


def recall100_best_f1(y, s):
    """재현율 100%(양성 전원 포착)를 만족하는 임계값 중 F1 최대."""
    pos = [si for si, yi in zip(s, y) if yi == 1]
    if not pos:
        return None
    thr = min(pos)  # 이 임계값 이하로 내려야 재현율 100%
    tp = sum(1 for si, yi in zip(s, y) if yi == 1 and si >= thr)
    fp = sum(1 for si, yi in zip(s, y) if yi == 0 and si >= thr)
    fn = sum(1 for si, yi in zip(s, y) if yi == 1 and si < thr)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"threshold": thr, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


def load_v13_lookup(src):
    """(date, gid) -> warn. 서빙 팩 json 또는 재추출 CSV 모두 지원."""
    lut = {}
    if src.endswith(".json"):
        pack = json.load(open(src))
        for date, day in pack["predictions"].items():
            for gid, v in day.items():
                if isinstance(v, dict) and "warn" in v:
                    lut[(date, str(gid))] = float(v["warn"])
    else:
        for row in csv.DictReader(open(src)):
            lut[(row["target_date"], str(row["gid"]))] = float(row["warn"])
    return lut


def load_farm_centroids(poly_path):
    poly = json.load(open(poly_path))
    def flat(c):
        if isinstance(c[0], (int, float)):
            return [c]
        out = []
        for x in c:
            out += flat(x)
        return out
    cents = {}
    for f in poly["features"]:
        pts = flat(f["geometry"]["coordinates"])
        gid = str(f["properties"]["gid"])
        cents[gid] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return cents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v19-csv", required=True)
    ap.add_argument("--v13-src", required=True)
    ap.add_argument("--polygons", default="frontend/src/data/kimFarmPolygons2025.json")
    ap.add_argument("--out", default="ensemble_recall100_result.json")
    args = ap.parse_args()

    lut = load_v13_lookup(args.v13_src)
    cents = load_farm_centroids(args.polygons)

    rows = list(csv.DictReader(open(args.v19_csv)))
    y, s19, s13, unmatched = [], [], [], 0
    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        gid = min(cents, key=lambda g: (cents[g][0] - lon) ** 2 + (cents[g][1] - lat) ** 2)
        w = lut.get((r["target_date"], gid))
        if w is None:
            unmatched += 1
            continue
        y.append(int(r["y_true"]))
        s19.append(float(r["v19_score"]))
        s13.append(w)

    if not y:
        sys.exit("매칭된 윈도우가 없음 — 날짜 범위/좌표 확인")

    dead13 = sum(1 for w in s13 if w < 0.01)
    r19, r13 = rank_normalize(s19), rank_normalize(s13)

    result = {"n_windows": len(y), "n_pos": sum(y), "unmatched": unmatched,
              "v13_near_zero": dead13, "sweep": []}
    for a in [round(x * 0.1, 1) for x in range(11)]:
        mix = [a * u + (1 - a) * v for u, v in zip(r19, r13)]
        m = recall100_best_f1(y, mix)
        m["alpha_v19"] = a
        result["sweep"].append(m)

    base = next(m for m in result["sweep"] if m["alpha_v19"] == 1.0)
    best = max(result["sweep"], key=lambda m: m["f1"])
    result["baseline_v19_only_f1"] = base["f1"]
    result["best"] = best
    result["verdict"] = ("앙상블 이득 있음" if best["f1"] > base["f1"] + 1e-9 and best["alpha_v19"] < 1.0
                         else "v19 단독이 최선 — 앙상블 무익")

    json.dump(result, open(args.out, "w"), ensure_ascii=False, indent=2)
    print(f"윈도우 {len(y)}개(양성 {sum(y)}), 매칭실패 {unmatched}, v13 무신호 {dead13}")
    print(f"v19 단독 F1 {base['f1']} → 최적 α={best['alpha_v19']} F1 {best['f1']}")
    print(result["verdict"], "→", args.out)


if __name__ == "__main__":
    main()
