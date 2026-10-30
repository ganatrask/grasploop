"""Copy benchmark records into the tracked results/ folder for the public repo: the grid JSONs with
their frame and video paths stripped (the frames stay under _logs/, ~250 MB per run), the usage logs,
and the stats tables. Nothing is edited by hand; rerun it and the folder is rebuilt.

    python3 eval/publish_results.py _logs/bench --out results/bench-2026-10-27
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil


def strip_media(obj):
    if isinstance(obj, dict):
        return {k: strip_media(v) for k, v in obj.items() if k not in ("frames", "video")}
    if isinstance(obj, list):
        return [strip_media(v) for v in obj]
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bench_dir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    n = 0
    for p in sorted(glob.glob(os.path.join(args.bench_dir, "*_*.json"))):
        with open(p) as f:
            d = json.load(f)
        if "episodes" not in d or "summary" not in d or p.endswith(".partial.json"):
            continue
        with open(os.path.join(args.out, os.path.basename(p)), "w") as f:
            json.dump(strip_media(d), f, indent=1)
        n += 1
        usage = os.path.splitext(p)[0] + ".usage.jsonl"
        if os.path.exists(usage):
            shutil.copy(usage, args.out)
    # every statistics folder (stats, stats_allegro, stats_<cell>), the figures and the matrix travel with the records;
    # the HTML report links frames by relative path, so only its summary table is published
    for src in sorted(glob.glob(os.path.join(args.bench_dir, "stats*"))) + [os.path.join(args.bench_dir, "figures")]:
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(args.out, os.path.basename(src)), dirs_exist_ok=True)
    for p in sorted(glob.glob(os.path.join(args.bench_dir, "review_*.json"))):  # eval/review_record.py: reviewer vs physics
        shutil.copy(p, args.out)
    for name in ("run.log", "matrix.md", os.path.join("report", "summary.md")):
        src = os.path.join(args.bench_dir, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(args.out, "report_summary.md" if name.endswith("summary.md") else os.path.basename(name)))
    print(f"[publish] {n} grid file(s) -> {args.out}")


if __name__ == "__main__":
    main()
