"""Replay a recorded program and film it: for demo clips of attempts whose frames were lost, or to
re-run any program from a grid record under the same seed. The verdict of the replay is what the
banner shows (physics is not run-to-run deterministic, so it may differ from the record; the clip
says so in its tag).

    $PY eval/refilm.py --record _logs/scale/go2_nav.json --condition physics --seed 100 --attempt 1 \
        --viz none --video _logs/scale/video_refilm --json _logs/scale/refilm_go2.json
Robot and task come from the record. Several --seed values may be given.
--hero DIR films the hero camera (NVIDIA OVRTX path tracer, 1280x720) plus the side camera (every step on the arms,
every other step on the walkers) into DIR/<robot>_<tag>/ for eval/make_demo.py --hero DIR.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.env import add_env_args  # noqa: E402

parser = argparse.ArgumentParser(description="replay recorded programs on film")
add_env_args(parser)
parser.add_argument("--record", required=True)
parser.add_argument("--condition", default="physics")
parser.add_argument("--seed", type=int, nargs="+", required=True)
parser.add_argument("--attempt", default="0", help="attempt number; 0 = the last attempt of the episode; 'all' = every attempt")
parser.add_argument("--skip-existing", action="store_true", help="skip an attempt whose replay film folder already exists")
parser.add_argument("--json", default="_logs/refilm.json")
args = parser.parse_args()

from isaaclab.app import launch_simulation  # noqa: E402

from agent import sandbox  # noqa: E402
from agent.env import create_env, make_env_cfg_from_args  # noqa: E402
from agent.loop import make_api, reference_program, run_judge  # noqa: E402
from judges.vision import attach_recorder  # noqa: E402


def main():
    with open(args.record) as f:
        rec = json.load(f)
    args.robot = rec.get("robot", "franka")
    shape = rec["shape"]
    if shape.startswith("place_"):
        args.task, args.shape = "place", shape[6:]
    elif shape == "drawer":
        args.task = "drawer"
    elif shape != "nav":
        args.shape = shape
    cfg = make_env_cfg_from_args(args)
    out = []
    with launch_simulation(cfg, args):
        g = create_env(cfg, args)
        args.shape = getattr(g, "SCENARIO", args.shape)
        rr = attach_recorder(g, args)
        jobs = []
        for seed in args.seed:
            ep = next(e for e in rec["episodes"][args.condition] if e["seed"] == seed)
            atts = ep.get("attempts") or [ep]
            chosen = atts if args.attempt == "all" else ([atts[int(args.attempt) - 1]] if int(args.attempt) else [atts[-1]])
            jobs += [(seed, ep, att) for att in chosen]
        for seed, ep, att in jobs:
            tag = f"{args.shape}_s{seed}_refilm{args.condition}_a{att.get('n', 1)}"  # parses like any attempt tag
            if args.skip_existing and rr is not None and os.path.isdir(os.path.join(args.hero or args.video, f"{args.robot}_{tag}")):
                print(f"[refilm] {tag}: film exists, skipped")
                continue
            code = att.get("code") or ep.get("code") or reference_program(g, args.robot)  # scripted episodes store no code
            t0 = time.time()
            g.reset(seed=seed)
            run = sandbox.run(code, make_api(g))
            verdict = run_judge(run, g)
            frames, video = [], None
            if rr is not None:
                rr.final()
                rr.tag = tag
                frames = rr.save()
                video = rr.last_video
            out.append(dict(seed=seed, condition=args.condition, n=att.get("n", 1), code=code, verdict=verdict, recorded_verdict=att["verdict"],
                            same_outcome=bool(verdict["success"]) == bool(att["verdict"]["success"]), frames=frames, video=video,
                            trace=run["trace"], wall_s=round(time.time() - t0, 1)))
            print(f"[refilm] {tag}: {'PASS' if verdict['success'] else 'fail:' + str(verdict['failure'])} (recorded: "
                  f"{'PASS' if att['verdict']['success'] else 'fail'})")
        g.env.close()
    if not out:  # every attempt was skipped: keep the record of the run that filmed them
        print(f"[refilm] nothing replayed, {args.json} left as it was")
    else:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(dict(script="eval/refilm.py", record=args.record, robot=args.robot, shape=args.shape, model=rec.get("model"),
                           summary={}, episodes={args.condition: [dict(seed=e["seed"], success=e["verdict"]["success"], attempts=[dict(e, n=e["n"])]) for e in out]}), f, indent=1)
        print(f"[refilm] -> {args.json}")
    if getattr(args, "hero", None):
        # the OVRTX renderer sometimes never returns from interpreter shutdown (FEEDBACK.md 2026-10-29); everything is on
        # disk by now, so leave without running the destructors
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
