"""The experiment grid for one shape: matched seeds across feedback conditions, Wilson intervals.

    $PY eval/run_grid.py --viz none --shape cube --seeds 8 --conditions scripted,oneshot,rerun,physics,vision \
        --model lightning --reasoning default --cameras _logs/grid/cube/frames --json _logs/grid/cube.json

Conditions (docs/01):
  scripted  A: the hand-written REFERENCE_PROGRAM, one run
  oneshot   B: Nemotron, one program, no repair
  rerun     C0: B's first program run again up to --attempts times with NO repair: what luck alone gives
  physics   C: Nemotron, up to --attempts programs, measured feedback
  vision    D: C plus the vision reviewer's diagnosis (needs --cameras)
  hints     E: C plus a Tavily web search on the failure mode (needs TAVILY_API_KEY or ~/.tavily/config.json)
One process = one shape (the scene is built once). Every episode record is kept; the summary is
computed from them, never typed in.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.env import add_env_args  # noqa: E402

parser = argparse.ArgumentParser(description="GraspLoop experiment grid")
add_env_args(parser)
parser.add_argument("--seeds", type=int, default=5)
parser.add_argument("--seed0", type=int, default=100, help="evaluation seeds start at 100 so they never overlap development seeds")
parser.add_argument("--conditions", default="scripted,oneshot,rerun,physics")
parser.add_argument("--model", default="lightning")
parser.add_argument("--reasoning", choices=["default", "low", "none"], default="default")
parser.add_argument("--attempts", type=int, default=3)
parser.add_argument("--temperature", type=float, default=0.2)
parser.add_argument("--review-all", action="store_true",
                    help="after the grid, have the vision reviewer judge EVERY filmed attempt (successes too) and "
                         "record its agreement with the physics judge; needs --cameras")
parser.add_argument("--json", default="_logs/grid.json")
args = parser.parse_args()

from isaaclab.app import launch_simulation  # noqa: E402

from agent import sandbox  # noqa: E402
from agent.env import GraspEnv, make_env_cfg_from_args, create_env  # noqa: E402
from agent.graspapi import REFERENCE_PROGRAMS, GraspAPI  # noqa: E402
from agent.loop import make_api, reference_program, run_judge, run_scenario  # noqa: E402
from agent.nemotron import TokenFactory, TokenFactoryError  # noqa: E402
from judges.physics import judge  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def run_program(g: GraspEnv, seed: int, code: str, tag: str) -> dict:
    """One scripted attempt: reset, run, judge, film."""
    start = g.reset(seed=seed)
    api = make_api(g)
    run = sandbox.run(code, api)
    verdict = run_judge(run, g)
    frames = []
    rec = getattr(g, "_recorder", None)
    if rec is not None:
        rec.final()
        rec.tag = tag
        frames = rec.save()
    return dict(seed=seed, start=start, run_status=run["status"], exception=run["exception"], verdict=verdict,
                trace=run["trace"], frames=frames, video=rec.last_video if rec is not None else None, sim_steps=g.steps)


def main():
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    usage_log = os.path.splitext(args.json)[0] + ".usage.jsonl"
    extra = {} if args.reasoning == "default" else {"reasoning_effort": args.reasoning}
    tf = TokenFactory(args.model, usage_log=usage_log, temperature=args.temperature, extra=extra)
    if any(c in conditions for c in ("oneshot", "rerun", "physics", "vision", "hints")):
        tf.check_model()
    reviewer = None
    hints = None
    if "hints" in conditions:
        from agent.hints import WebHints
        hints = WebHints()
    if "vision" in conditions:
        if not args.cameras:
            parser.error("the vision condition needs --cameras <dir>")
        from judges.vision import make_reviewer
        reviewer = make_reviewer(usage_log=usage_log)
    cfg = make_env_cfg_from_args(args)
    seeds = list(range(args.seed0, args.seed0 + args.seeds))
    t0 = time.time()
    episodes = {c: [] for c in conditions}
    with launch_simulation(cfg, args):
        g = create_env(cfg, args)
        env = g.env
        shape_for_cfg, args.shape = args.shape, getattr(g, "SCENARIO", args.shape)  # tags and records name the scenario
        from judges.vision import attach_recorder
        attach_recorder(g, args)
        for seed in seeds:
            first_program = None
            for cond in conditions:
                t1 = time.time()
                try:
                    if cond == "scripted":
                        ep = run_program(g, seed, reference_program(g, args.robot), f"{args.shape}_s{seed}_scripted")
                        ep.update(success=ep["verdict"]["success"], attempts_used=1, cost_usd=0.0)
                    elif cond == "oneshot":
                        ep = run_scenario(g, seed, tf, max_attempts=1, feedback="none")
                        first_program = ep["attempts"][0]["code"]
                    elif cond == "rerun":
                        if first_program is None:  # oneshot not in the list: generate the program once here
                            one = run_scenario(g, seed, tf, max_attempts=1, feedback="none")
                            first_program = one["attempts"][0]["code"]
                            reruns, cost = [one["attempts"][0]], one["cost_usd"]
                        else:
                            reruns, cost = [], 0.0
                        ok = any(a["verdict"]["success"] for a in reruns)
                        while not ok and len(reruns) < args.attempts:
                            r = run_program(g, seed, first_program, f"{args.shape}_s{seed}_rerun_a{len(reruns) + 1}")
                            reruns.append(r)
                            ok = r["verdict"]["success"]
                        ep = dict(seed=seed, condition="rerun", code=first_program, attempts=reruns, success=ok,
                                  attempts_used=len(reruns), cost_usd=cost)
                    elif cond == "physics":
                        ep = run_scenario(g, seed, tf, max_attempts=args.attempts, feedback="physics")
                    elif cond == "vision":
                        ep = run_scenario(g, seed, tf, max_attempts=args.attempts, feedback="vision", reviewer=reviewer)
                    elif cond == "hints":
                        ep = run_scenario(g, seed, tf, max_attempts=args.attempts, feedback="hints", hints=hints)
                    else:
                        raise SystemExit(f"unknown condition {cond}")
                except TokenFactoryError as e:
                    # one failed API call must not end the shape: HTTP 529 killed sphere_s (2026-10-27)
                    ep = dict(seed=seed, condition=cond, success=False, attempts=[], attempts_used=0, cost_usd=0.0,
                              infra_error=str(e)[:300])
                    print(f"[grid] {args.shape} seed {seed} {cond:8s}: INFRA ERROR {str(e)[:120]}")
                ep["condition"] = cond
                ep["wall_s"] = round(time.time() - t1, 1)
                episodes[cond].append(ep)
                print(f"[grid] {args.shape} seed {seed} {cond:8s}: {'PASS' if ep['success'] else 'fail'} "
                      f"in {ep.get('attempts_used', 1)} attempt(s), ${ep.get('cost_usd', 0):.4f}, {ep['wall_s']} s")
            with open(os.path.splitext(args.json)[0] + ".partial.json", "w") as f:  # survives a crash mid-shape
                json.dump(dict(script="eval/run_grid.py", robot=args.robot, shape=args.shape, seeds_done=seed, episodes=episodes), f)
        env.close()
    reviews = []
    if args.review_all and args.cameras and args.robot not in ("go2", "g1"):  # the reviewer prompt is about grasps
        # The loop reviews failures only (that is what gets repaired). Reviewing successes as well is
        # what measures false positives: does the camera judge call a drop a success?
        from PIL import Image

        from judges.vision import make_reviewer, review
        rv = reviewer or make_reviewer(usage_log=usage_log)
        ext = [c * 100 for c in g.extent["size_xyz"]]
        size = f"{ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} cm"
        for cond, eps in episodes.items():
            for e in eps:
                for a in (e.get("attempts") or [e]):
                    if not a.get("frames"):
                        continue
                    import numpy as np
                    frames = [np.asarray(Image.open(p).convert("RGB")) for p in a["frames"]]
                    r = review(rv.tf, frames, args.shape, size, frame_dt_s=0.5, tag=f"review_all:{cond}:s{e['seed']}:a{a.get('n', 1)}")
                    phys = bool(a["verdict"]["success"])
                    reviews.append(dict(condition=cond, seed=e["seed"], attempt=a.get("n", 1), physics_success=phys,
                                        physics_failure=a["verdict"]["failure"], visual_success=r["structured"].get("visual_success"),
                                        visual_failure=r["structured"].get("failure_type"), confidence=r["structured"].get("confidence"),
                                        valid_json=r["valid_json"], cost_usd=r["cost_usd"]))
        n = len(reviews)
        agree = sum(1 for r in reviews if r["visual_success"] == r["physics_success"])
        fp = sum(1 for r in reviews if r["visual_success"] is True and not r["physics_success"])
        fn = sum(1 for r in reviews if r["visual_success"] is False and r["physics_success"])
        abstain = sum(1 for r in reviews if r["visual_success"] is None)
        print(f"[grid] reviewer vs physics on {n} attempts: agree {agree}, false positives {fp}, false negatives {fn}, abstain {abstain}")
    summary = {}
    for cond, eps in episodes.items():
        ok = [e for e in eps if not e.get("infra_error")]  # an API outage is not a method failure
        k, n = sum(e["success"] for e in ok), len(ok)
        p, lo, hi = wilson(k, n)
        summary[cond] = dict(successes=k, n=n, rate=round(p, 3), ci95=[round(lo, 3), round(hi, 3)],
                             mean_attempts=round(sum(e.get("attempts_used", 1) for e in ok) / max(1, n), 2),
                             cost_usd=round(sum(e.get("cost_usd", 0.0) for e in ok), 4),
                             cost_per_success_usd=round(sum(e.get("cost_usd", 0.0) for e in ok) / k, 4) if k else None,
                             infra_errors=len(eps) - n)
    if reviews:
        n = len(reviews)
        summary["reviewer"] = dict(n=n, agree=sum(r["visual_success"] == r["physics_success"] for r in reviews),
                                   false_positive=sum(r["visual_success"] is True and not r["physics_success"] for r in reviews),
                                   false_negative=sum(r["visual_success"] is False and r["physics_success"] for r in reviews),
                                   abstain=sum(r["visual_success"] is None for r in reviews),
                                   invalid_json=sum(not r["valid_json"] for r in reviews),
                                   cost_usd=round(sum(r["cost_usd"] for r in reviews), 4))
    out = dict(script="eval/run_grid.py", robot=args.robot, shape=args.shape, model=tf.model, reasoning=args.reasoning, attempts=args.attempts,
               seeds=seeds, conditions=conditions, summary=summary, reviews=reviews,
               total_cost_usd=round(tf.total_cost_usd + (reviewer.tf.total_cost_usd if reviewer else 0.0), 4),
               wall_s=round(time.time() - t0, 1), episodes=episodes)
    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w") as f:
        json.dump(out, f, indent=1)
    print("[grid] summary:", json.dumps(summary))
    print(f"[grid] total ${out['total_cost_usd']:.4f}, {out['wall_s']} s -> {args.json}")


if __name__ == "__main__":
    main()
