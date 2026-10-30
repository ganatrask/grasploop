"""The robots x tasks matrix from every grid record given: per cell, successes / scenarios for each
condition, plus the scripted reference as the feasibility ceiling. Pure stdlib; markdown out.

    python3 eval/matrix.py _logs/bench/franka_*.json _logs/bench/allegro_cube.json _logs/scale/*.json --out _logs/scale/matrix.md
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

ROBOT = {"franka": "Franka Panda (arm, 2-finger)", "allegro": "Kuka iiwa + Allegro (arm, 4-finger hand)",
         "go2": "Unitree Go2 (quadruped)", "g1": "Unitree G1 (humanoid)"}
COND = [("scripted", "reference"), ("oneshot", "one-shot"), ("rerun", "rerun"), ("physics", "physics fb"), ("vision", "physics+vision")]


def task_of(shape: str) -> tuple[str, str]:
    if shape == "nav":
        return "navigate: waypoint then goal", "flat ground"
    if shape.startswith("place_"):
        return "pick and place on a target", shape[6:]
    return "pick up and hold 10 cm", shape


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grids", nargs="+")
    ap.add_argument("--out", default="_logs/matrix.md")
    a = ap.parse_args()
    cells = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    meta = {}
    for p in a.grids:
        if p.endswith(".partial.json"):
            continue
        with open(p) as f:
            d = json.load(f)
        if "summary" not in d or not str(d.get("script", "")).endswith("run_grid.py"):  # skip refilm records
            continue
        robot, (task, variant) = d.get("robot", "franka"), task_of(d["shape"])
        key = (robot, task, variant)
        meta[key] = dict(model=(d.get("model") or "").split("/")[-1], reasoning=d.get("reasoning"), cost=d.get("total_cost_usd", 0.0), wall_s=d.get("wall_s", 0.0))
        for cond, eps in d["episodes"].items():
            ok = [e for e in eps if not e.get("infra_error")]
            cells[key][cond][0] += sum(bool(e["success"]) for e in ok)
            cells[key][cond][1] += len(ok)
    conds = [c for c, _ in COND if any(c in v for v in cells.values())]
    L = ["| robot | task | object / terrain | " + " | ".join(lbl for c, lbl in COND if c in conds) + " | model | $ |",
         "|---|---|---|" + "---|" * len(conds) + "---|---|"]
    for key in sorted(cells, key=lambda k: (list(ROBOT).index(k[0]) if k[0] in ROBOT else 9, k[1], k[2])):
        robot, task, variant = key
        row = [ROBOT.get(robot, robot), task, variant]
        for c in conds:
            k, n = cells[key].get(c, [0, 0])
            row.append(f"{k}/{n}" if n else "—")
        m = meta[key]
        row += [m["model"] + (" (no thinking)" if m["reasoning"] == "none" else ""), f"{m['cost']:.2f}"]
        L.append("| " + " | ".join(row) + " |")
    robots = {k[0] for k in cells}
    tasks = {k[1] for k in cells}
    scen = sum(v[conds[0]][1] for v in cells.values() if conds and conds[0] in v)
    head = (f"# Robots x tasks: {len(robots)} robots, {len(tasks)} task families, {len(cells)} cells, "
            f"{scen} scenarios per condition\n")
    out = head + "\n" + "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        f.write(out)
    print(out)


if __name__ == "__main__":
    main()
