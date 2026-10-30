"""Run the Nemotron write-run-repair loop on seeded scenarios and write a JSON record.

    export NEBIUS_API_KEY=...
    $PY eval/run_loop.py --viz none --shape cube --seeds 3 --model lightning --feedback physics \
        --attempts 3 --json _logs/loop_cube_lightning.json

--feedback none|physics|vision|hints (vision needs --cameras and judges/vision.py; hints needs a Tavily key, agent/hints.py). The usage log of
every model call goes next to the JSON as <name>.usage.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.env import add_env_args  # noqa: E402

parser = argparse.ArgumentParser(description="GraspLoop: Nemotron writes the grasp program")
add_env_args(parser)
parser.add_argument("--seeds", type=int, default=3)
parser.add_argument("--seed0", type=int, default=0)
parser.add_argument("--model", default="lightning", help="short name in agent/nemotron.MODELS or a Token Factory ID")
parser.add_argument("--feedback", choices=["none", "physics", "vision", "hints"], default="physics")
parser.add_argument("--attempts", type=int, default=3)
parser.add_argument("--temperature", type=float, default=0.2)
parser.add_argument("--reasoning", choices=["default", "low", "none"], default="default",
                    help="reasoning_effort sent to Token Factory; 'none' switches Nemotron's thinking off (10x fewer tokens)")
parser.add_argument("--json", default="_logs/loop.json")
args = parser.parse_args()

from isaaclab.app import launch_simulation  # noqa: E402

from agent.env import make_env_cfg, make_env_cfg_from_args, create_env  # noqa: E402
from agent.loop import run_scenario  # noqa: E402
from agent.nemotron import TokenFactory  # noqa: E402


def main():
    usage_log = os.path.splitext(args.json)[0] + ".usage.jsonl"
    extra = {} if args.reasoning == "default" else {"reasoning_effort": args.reasoning}
    tf = TokenFactory(args.model, usage_log=usage_log, temperature=args.temperature, extra=extra)
    tf.check_model()  # a wrong ID fails here, not after hours of retries
    reviewer = None
    if args.feedback == "vision":
        if not args.cameras:
            parser.error("--feedback vision needs --cameras <dir>")
        from judges.vision import make_reviewer
        reviewer = make_reviewer(usage_log=usage_log)
    hints = None
    if args.feedback == "hints":
        from agent.hints import WebHints
        hints = WebHints()
    cfg = make_env_cfg_from_args(args)
    t0 = time.time()
    episodes = []
    with launch_simulation(cfg, args):
        g = create_env(cfg, args)
        env = g.env
        shape_for_cfg, args.shape = args.shape, getattr(g, "SCENARIO", args.shape)  # tags and records name the scenario
        from judges.vision import attach_recorder
        attach_recorder(g, args)
        for seed in range(args.seed0, args.seed0 + args.seeds):
            rec = run_scenario(g, seed, tf, max_attempts=args.attempts, feedback=args.feedback, reviewer=reviewer, hints=hints)
            episodes.append(rec)
            outcome = "PASS" if rec["success"] else "fail:" + str(rec["attempts"][-1]["verdict"]["failure"])
            print(f"[loop] {args.shape} seed {seed}: {outcome} in {rec['attempts_used']} attempt(s), "
                  f"${rec['cost_usd']:.4f}, {rec['wall_s']} s")
        env.close()
    n_ok = sum(e["success"] for e in episodes)
    out = dict(script="eval/run_loop.py", shape=args.shape, model=tf.model, condition=args.feedback, attempts=args.attempts,
               seeds=args.seeds, seed0=args.seed0, successes=n_ok, cost_usd=round(tf.total_cost_usd, 5), calls=tf.calls,
               wall_s=round(time.time() - t0, 1), episodes=episodes)
    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[loop] {n_ok}/{args.seeds} succeeded, {tf.calls} calls, ${tf.total_cost_usd:.4f} -> {args.json}")


if __name__ == "__main__":
    main()
