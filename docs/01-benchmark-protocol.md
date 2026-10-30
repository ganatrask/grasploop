# 01 — The final local benchmark, launched Tue 2026-10-27 19:45 PT

What is being measured, with which code, and what happens with the result. The pipeline was ready
a day ahead of schedule and the GPU was free overnight, so the benchmark ran on the laptop; nothing
here depends on cloud compute.

## 1. Frozen configuration

- Code: commit `508f033` of the working repo (Allegro reference + benchmark driver) and everything
  before it. No file under `agent/`, `judges/` or `eval/run_grid.py` changes until the run has
  finished: prompt and model settings are fixed before the final tests. `eval/stats.py`, docs and
  the README may change.
- Driver: `eval/run_benchmark.sh` → one `run_grid.py` process per shape, sequentially, each with
  `--review-all --cameras --video`.
- Model: `nvidia/Nemotron-3_5-Lightning` on Token Factory, thinking on (default), temperature 0.2,
  12k tokens, one retry at 24k on truncation. Reviewer: `nvidia/Nemotron-3.5-Super-VL`, reasoning off,
  8 frames of 320×240.
- Conditions: A scripted reference, B one-shot, C0 rerun of B's program without repair, C physics
  feedback (≤3 attempts), D physics + vision feedback (≤3 attempts). Matched seeds 100–107.
- Scenarios: Franka × {cube, box_flat, sphere_s, box_tall, capsule_s, sphere_m} × 8 seeds =
  48 matched scenarios (64 was the target). Then Allegro × cube × 8 seeds as a second-robot
  demonstration, not part of the primary comparison (its reference did not reach 3/5 on every
  shape: cube 3–4/5, thin box 1/5, sphere 0/5).
- Success: object centre ≥ 0.10 m above its start, held 0.5 s with the hand closed, judged by the
  physics state. The reviewer never sees the physics label.
- Primary comparison: D versus C, paired over scenarios. Secondary: C versus B, C versus
  C0 (repair versus luck), first-attempt rate, recovery at attempts 2 and 3, cost per success,
  reviewer agreement, failure categories.

Expected: ~40 min and ~$0.15 per Franka shape, ~4.5 h and ~$1 in total.

## 2. Outputs

```
_logs/bench/run.log                 driver log: one line per shape with the summary
_logs/bench/<robot>_<shape>.json    every episode, attempt, program, trace, verdict, review
_logs/bench/<robot>_<shape>.usage.jsonl   every Token Factory call with tokens and cost
_logs/bench/video/<robot>_<tag>/    both cameras, 15 fps, per attempt
_logs/bench/report/index.html       per-trial viewer (eval/report.py)
_logs/bench/review/NN_<tag>.mp4     one clip per attempt (eval/make_videos.py)
```

Afterwards:

```bash
python3 eval/stats.py _logs/bench/franka_*.json --out _logs/bench/stats     # the tables in doc 02
python3 eval/stats.py _logs/bench/allegro_*.json --out _logs/bench/stats_allegro
```

The JSON records (not the frames) get copied into a tracked `results/` folder for the public repo.

## 3. What was fixed before the freeze (doc 05 §5)

The showcase films exposed two blind spots in the physics feedback (fingers closing above the
object; the hand pushing the object before the close) and two benchmark-object defects (standing
capsule topples by itself; the reference could not lift the tall box). All four are fixed and gated.
This is the only reason the benchmark is not the pilot pipeline: the method was corrected on
pilot evidence, which is what the pilot was for, and then frozen.
