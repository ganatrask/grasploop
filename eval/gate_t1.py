"""Gate T1: the hand-written reference program lifts the object on seeded starts.

    $PY eval/gate_t1.py --viz none --shape cube --seeds 5 --json _logs/gate_t1.json

Pass: >= 4 of 5 seeds succeed under judges/physics.py. The same loop (reset -> API -> sandbox ->
judge) is what agent/loop.py runs with Nemotron's program instead of REFERENCE_PROGRAM.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.env import add_env_args  # noqa: E402

parser = argparse.ArgumentParser(description="Gate T1: scripted reference grasp")
add_env_args(parser)
parser.add_argument("--seeds", type=int, default=5)
parser.add_argument("--seed0", type=int, default=0)
parser.add_argument("--program", type=str, default=None, help="Path to a program file; default is REFERENCE_PROGRAM")
parser.add_argument("--json", type=str, default="_logs/gate_t1.json")
args = parser.parse_args()

from isaaclab.app import launch_simulation  # noqa: E402

from agent import sandbox  # noqa: E402
from agent.env import make_env_cfg, make_env_cfg_from_args, create_env  # noqa: E402
from agent.graspapi import REFERENCE_PROGRAMS, GraspAPI  # noqa: E402
from agent.loop import make_api, reference_program, run_judge  # noqa: E402
from judges.vision import attach_recorder  # noqa: E402


def main():
    code = open(args.program).read() if args.program else None
    cfg = make_env_cfg_from_args(args)
    t0 = time.time()
    episodes = []
    with launch_simulation(cfg, args):
        g = create_env(cfg, args)
        env = g.env
        shape_for_cfg, args.shape = args.shape, getattr(g, "SCENARIO", args.shape)  # tags and records name the scenario
        rec = attach_recorder(g, args)
        code = code or reference_program(g, args.robot)
        for seed in range(args.seed0, args.seed0 + args.seeds):
            t1 = time.time()
            start = g.reset(seed=seed)
            api = make_api(g)
            run = sandbox.run(code, api)
            verdict = run_judge(run, g)
            frames = []
            if rec is not None:
                rec.final()
                rec.tag = f"{args.shape}_s{seed}_scripted"
                frames = rec.save()
            ep = dict(seed=seed, start=start, status=run["status"], exception=run["exception"], stdout=run["stdout"],
                      verdict=verdict, sim_steps=g.steps, sim_s=round(g.steps * g.dt, 1), wall_s=round(time.time() - t1, 1),
                      trace=run["trace"], frames=frames, video=rec.last_video if rec is not None else None)
            episodes.append(ep)
            print(f"[gate_t1] seed {seed}: {'PASS' if verdict['success'] else 'fail:' + str(verdict['failure'])} "
                  f"{verdict.get('detail') or ('rise ' + str(verdict.get('final_rise_m')) + ' contacts ' + str(verdict.get('contacts')))} ({ep['wall_s']} s)")
        env.close()
    n_ok = sum(e["verdict"]["success"] for e in episodes)
    out = dict(script="eval/gate_t1.py", robot=args.robot, shape=args.shape, program="file:" + args.program if args.program else "REFERENCE_PROGRAM",
               seeds=args.seeds, successes=n_ok, failures=[e["verdict"]["failure"] for e in episodes if not e["verdict"]["success"]],
               wall_s=round(time.time() - t0, 1), checks=dict(scripted_lift_4_of_5=n_ok >= min(4, args.seeds)), episodes=episodes)
    out["pass"] = all(out["checks"].values())
    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[gate_t1] {n_ok}/{args.seeds} {'pass' if out['pass'] else 'FAIL'} -> {args.json}")


if __name__ == "__main__":
    main()
