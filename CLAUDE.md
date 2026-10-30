# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GraspLoop: NVIDIA Nemotron, served by Nebius Token Factory, writes a robot program against a small API;
kit-less Isaac Lab 3.0.0 GA runs it on Newton physics; a physics judge grades it; what the simulator
measured goes back to the model in words, and it repairs the program, up to three attempts. Matched-seed
conditions A (scripted reference), B (one-shot), C0 (rerun, no repair), C (physics feedback), D (physics +
vision reviewer), E (physics + Tavily web hints).

- `README.md`: what it is, every result, every command. Read it first.
- `docs/01`: the frozen benchmark protocol. `docs/02`, `docs/03`, `docs/04`: the experiments and their
  numbers. `docs/05`: the build log with every trap and fix. `docs/README.md` indexes them.
  `FEEDBACK.md`: the tool-friction log.
- `results/`: the JSON records every table comes from; `eval/stats.py` must reproduce them.
- The commit hashes some docs cite are in the private working repo this one was split from.

## Stack: Isaac Lab 3.0.0 GA, kit-less, Newton only

```bash
PY=~/workspace/isaaclab-3.0.0-ga/.venv/bin/python
```

Isaac Lab tag `v3.0.0`, `uv sync --frozen --extra ovrtx` in its checkout: torch 2.11+cu130, Warp 1.17,
Newton 1.6.1. No Isaac Sim, no Kit, no display; any CUDA GPU, RT cores not needed.
`eval/cloud/bootstrap_nebius_vm.sh` installs it from scratch on a fresh Ubuntu CUDA image. The walking
robots need policies under `~/workspace/isaaclab-3.0.0-ga/logs/rsl_rl/<experiment>/`:
`eval/train_walkers.sh` trains both with NVIDIA's `train.py` (Go2 8 min, G1 36 min on an RTX 5090 laptop).

## Commands

There is no test suite, linter config or package metadata; the checks are the smoke runs below. Scripts
that import `isaaclab` (`agent/env.py`, `eval/gate_t1.py`, `run_loop.py`, `run_grid.py`, `refilm.py`)
need `$PY` and a CUDA GPU, and take `--viz none`. `eval/stats.py`, `report.py`, `matrix.py`,
`merge_grid.py` and `publish_results.py` are pure stdlib and need no GPU, but only Python 3.12 or newer
reproduces the committed tables exactly (3.12 changed float `sum()`; 3.9 differs in a last digit).

```bash
$PY -m agent.env --viz none                                              # reset + one move_to -> _logs/env_smoke.json
$PY eval/gate_t1.py --viz none --shape cube --seeds 5 --json _logs/t1.json  # scripted reference, no API key; pass >= 4/5
$PY eval/run_grid.py --viz none --shape cube --seeds 1 --conditions scripted,oneshot --json _logs/smoke.json
$PY eval/review_record.py <grid.json> --out _logs/review_smoke.json --limit 3   # reviewer on 3 filmed attempts
python3 eval/stats.py results/cloud-2026-10-29/cube.json results/cloud-2026-10-29/cube16.json --out _logs/stats
```

To reproduce a committed table, pass every record listed under `inputs` in its `stats.json`; the output
matches byte for byte. `eval/run_benchmark.sh` and `eval/run_scale.sh` run one grid process per cell and
skip any cell whose JSON already exists (env knobs at the top of each script). The full command list is
README "Run it".

## Layout

```
agent/    env, grasp API, sandbox, Token Factory client, repair loop, cameras, locomotion, place, drawer, web hints
judges/   physics judge, vision reviewer
eval/     gate, loop, grid, stats, matrix, report, videos, refilm, demo cut, drivers, cloud/ (Nebius VM)
results/  frozen records: bench-2026-10-27, bench-2026-10-28-nothink, scale-2026-10-29, cloud-2026-10-29, tavily-2026-10-29
docs/     01 protocol, 02 benchmark results, 03 robots x tasks, 04 cloud and web hints, 05 build log
```

## Architecture

- Every runner goes `add_env_args` -> `make_env_cfg_from_args` -> `launch_simulation` -> `create_env`
  (`agent/env.py`). `--robot` and `--task` pick the wrapper: `GraspEnv` (Franka lift), `AllegroEnv`
  (subclass; robot facts are class attributes), `PlaceEnv`, `DrawerEnv`, or `LocoEnv` for go2/g1 (wraps a
  `ManagerBasedRLEnv`, not a `GraspEnv`). The scene is built once per process, so one grid process is one
  robot x task x shape cell.
- `agent/loop.py:run_scenario` does not know the robot. It calls these env hooks when present and falls
  back to the Franka grasp defaults otherwise: `make_api`, `api_doc`, `judge`, `feedback_text`,
  `REFERENCE_PROGRAM`, plus the attributes `ROBOT`, `TASK` (the prompt's task sentence) and `SCENARIO`
  (record and film tags; a `place_` prefix selects the place reference program). The vision reviewer
  keeps its own per-family prompt and failure vocabulary in `judges/vision.py`.
- `agent/sandbox.py` runs generated code in-process, because the program steps the simulator: AST
  allow-list, stripped builtins, a SIGALRM wall clock and the API's step budget. The worker process is
  the isolation unit.
- The feedback wording is the thing condition C measures, and changing it moved the walkers' repair rate
  (doc 03 §3). Prompt, model settings and API text are frozen for a benchmark (`run_benchmark.sh`
  header, doc 01); a change means rerunning the affected cells. Feedback reports pass/fail only, and the
  reviewer never sees the physics verdict.
- `eval/run_grid.py`: `rerun` reruns the same seed's `oneshot` program, so list `oneshot` first (without
  it, `rerun` generates its own). A `TokenFactoryError` marks the episode `infra_error` and excludes it
  from n. Evaluation seeds start at 100 (`--seed0` default); `gate_t1.py` defaults to seed 0, the
  development range. `--review-all` skips go2/g1; walker grids are reviewed afterwards with
  `eval/review_record.py`.
- Records: runners write to `_logs/` (gitignored), with `<name>.usage.jsonl` (per-call tokens and cost)
  beside each JSON. `eval/publish_results.py` copies into `results/<set>/` with frame and video paths
  stripped; `eval/merge_grid.py` replaces one condition and records its source under `merged`. Nothing
  in `results/` is edited by hand.
- Models: short names `lightning` (default), `ultra`, `super_vl` (reviewer), `gpt_oss` map to Token
  Factory IDs and prices in `agent/nemotron.py`. Lightning spends most of its output on reasoning;
  `max_tokens` is 12000 and a reply cut off at the limit is retried once at double.

## Rules

- A result is a JSON record with `--json`; the record is the citable thing, not console output. Anything
  long runs detached: `nohup … > _logs/<name>.log 2>&1 &`. Grid stdout is block-buffered; progress is the
  episode count in `*.partial.json`.
- While a grid is running (`pgrep -af '[r]un_grid'`), do not edit `agent/`, `judges/` or
  `eval/run_grid.py`: each cell starts a new process that imports the code afresh.
- Keys come from the environment only: `NEBIUS_API_KEY`, `TAVILY_API_KEY` (or `~/.tavily/config.json`).
  Never in files, never in chat.
- `FEEDBACK.md` is a judged submission item: add a row when a Nebius or NVIDIA tool causes friction, at
  the time it happens.
- Set `NewtonCfg(solver_cfg=MJWarpSolverCfg(...))` explicitly: kit-less defaults can fall back to PhysX.
- Newton/MJWarp is not run-to-run deterministic; condition C0 measures that noise floor. Compare
  replications within it.
- `pgrep -f` and `pkill -f` match the shell that runs them; bracket the first letter of the pattern.
