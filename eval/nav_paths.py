"""Top-down paths of a walking episode: one line per attempt, over the waypoint and goal discs.

    $PY eval/nav_paths.py _logs/scale/go2_nav.json --seed 106 --condition physics --out _logs/scale/figures/go2_s106_physics.png
    $PY eval/nav_paths.py _logs/scale/go2_nav.json --seed all --condition physics --out _logs/scale/figures/go2_physics_all.png

Every pose comes from the saved trace (the pose returned by each walk/stop call), so the figure
is a reading of the record, not a new run. `--seed all` draws the final attempt of every seed as
small multiples. Colours: attempt 1 blue, 2 orange, 3 aqua, fixed order; each path is labelled at
its end so identity never rests on colour alone.
"""
import argparse
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # attempt colours 1-3, fixed order
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
NAMES = {"go2": "Unitree Go2", "g1": "Unitree G1", "franka": "Franka"}


def episode(rec: dict, cond: str, seed: int) -> dict:
    for e in rec["episodes"][cond]:
        if e["seed"] == seed:
            return e
    raise SystemExit(f"no {cond} episode for seed {seed}")


def attempt_paths(ep: dict):
    """[(n, [(x, y), ...], verdict)] for each attempt (scripted episodes hold a single implicit attempt)."""
    atts = ep.get("attempts") or [dict(n=1, trace=ep.get("trace", []), verdict=ep.get("verdict", {}))]
    s = ep["start"]["start"] if "start" in ep["start"] else ep["start"]
    out = []
    for a in atts:
        pts = [(s["x"], s["y"])]
        for r in a.get("trace") or []:
            if r["call"] in ("walk", "stop") and isinstance(r.get("result"), dict) and "pose" in r["result"]:
                pts.append((r["result"]["pose"]["x"], r["result"]["pose"]["y"]))
        out.append((a.get("n", 1), pts, a.get("verdict") or {}))
    return out


def draw(ax, ep: dict, paths, title: str, legend: bool):
    st = ep["start"]
    s = st["start"] if "start" in st else st
    wp, gp = st["waypoint"], st["goal"]
    ax.set_facecolor(SURFACE)
    ax.add_patch(Circle((wp["x"], wp["y"]), wp["radius"], fill=False, ls="--", lw=1.2, ec=INK2))
    ax.add_patch(Circle((gp["x"], gp["y"]), gp["radius"], fill=True, fc="#dfe9f7", ec=INK2, lw=1.2))
    ax.text(wp["x"], wp["y"] + wp["radius"] + 0.12, "waypoint", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.text(gp["x"], gp["y"] + gp["radius"] + 0.12, "goal", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.plot([s["x"]], [s["y"]], marker="o", ms=7, mfc="white", mec=INK, mew=1.5, ls="none", zorder=5)
    ax.annotate("", xy=(s["x"] + 0.35 * math.cos(math.radians(s["heading_deg"])), s["y"] + 0.35 * math.sin(math.radians(s["heading_deg"]))),
                xytext=(s["x"], s["y"]), arrowprops=dict(arrowstyle="->", color=INK, lw=1.2), zorder=5)
    for k, (n, pts, v) in enumerate(paths):
        c = SERIES[(n - 1) % len(SERIES)]
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=c, lw=2, alpha=0.95, zorder=3 + k, solid_capstyle="round")
        ax.plot(xs[-1], ys[-1], marker="o", ms=6, color=c, mec="white", mew=1.0, ls="none", zorder=6)
        ok = v.get("success")
        lab = f"attempt {n}: {'PASS' if ok else 'fail, ' + str(v.get('failure', '?')).replace('_', ' ')}"
        # labels stack in a fixed column (axes coordinates) so close endpoints never collide; the border carries the colour
        ax.text(0.02, 0.97 - 0.065 * k, lab, transform=ax.transAxes, fontsize=8, color=INK, va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=c, lw=1.4), zorder=7)
    xs_all = [p[0] for _, pts, _ in paths for p in pts] + [wp["x"], gp["x"], s["x"]]
    ys_all = [p[1] for _, pts, _ in paths for p in pts] + [wp["y"], gp["y"], s["y"]]
    pad = 1.0
    ax.set_xlim(min(xs_all) - pad, max(xs_all) + pad)
    ax.set_ylim(min(ys_all) - pad, max(ys_all) + pad)
    ax.set_aspect("equal")
    ax.grid(True, color=GRID, lw=0.8)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.set_xlabel("x (m)", color=INK2, fontsize=8)
    ax.set_ylabel("y (m)", color=INK2, fontsize=8)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    # the stacked labels double as the legend (one per series, in series order)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("--seed", default="all", help="seed number, or 'all' for small multiples of the final attempt")
    ap.add_argument("--condition", default="physics")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rec = json.load(open(args.record))
    robot = NAMES.get(rec.get("robot", "franka"), rec.get("robot"))
    cond_name = {"scripted": "hand-written reference", "oneshot": "Nemotron one-shot", "rerun": "Nemotron rerun",
                 "physics": "Nemotron + physics feedback"}.get(args.condition, args.condition)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if args.seed == "all":
        eps = rec["episodes"][args.condition]
        cols = 4
        rows = math.ceil(len(eps) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 4.0 * rows), facecolor=SURFACE)
        for ax, ep in zip(axes.flat, eps):
            paths = attempt_paths(ep)
            draw(ax, ep, paths[-1:], f"seed {ep['seed']}: final attempt {paths[-1][0]}", legend=False)
        for ax in list(axes.flat)[len(eps):]:
            ax.axis("off")
        fig.suptitle(f"{robot}, {cond_name}: path of the final attempt per seed", fontsize=12, color=INK, x=0.01, ha="left")
    else:
        ep = episode(rec, args.condition, int(args.seed))
        paths = attempt_paths(ep)
        fig, ax = plt.subplots(figsize=(8, 6), facecolor=SURFACE)
        draw(ax, ep, paths, f"{robot}, seed {ep['seed']}, {cond_name}: every attempt", legend=True)
    fig.tight_layout()
    fig.savefig(args.out, dpi=130, facecolor=SURFACE)
    print(f"[paths] -> {args.out}")


if __name__ == "__main__":
    main()
