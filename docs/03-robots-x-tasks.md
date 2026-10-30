# 03 — Robots × tasks: the same loop on a quadruped, a humanoid and a second manipulation task

Built overnight 2026-10-28/29 after the Franka benchmark (doc 02), because one arm on one scene reads
as a demo, not a platform. Everything here reuses the loop unchanged: prompt → program → sandbox →
physics judge → feedback in words → repair. A robot plugs in by supplying four things through
`agent/loop.py`'s hooks: an API object (`make_api`), its documentation (`api_doc`), a judge
(`judge`) and the wording of its feedback (`feedback_text`). The grid, the statistics, the recorder,
the clips and the demo cut did not change.

## 1. Walking robots: NVIDIA's policy as the controller (`agent/locomotion.py`)

- Scenes: NVIDIA's kit-less Newton velocity tasks `Isaac-Velocity-Flat-UnitreeGo2` and
  `Isaac-Velocity-Flat-G1`, in play mode, one environment, the RL time-out and the fall reset
  removed (a fall is a verdict, not a reset), random shoves disabled, the velocity command term left
  in place but overwritten by the program.
- Controllers: NVIDIA's RSL-RL PPO policies trained with NVIDIA's own `train.py` on this laptop,
  4096 environments, no Isaac Sim: Go2 1500 iterations in 8 minutes, G1 3000 iterations in about
  36 minutes (`eval/train_walkers.sh`). Loaded with the play backend's recipe (RSL-RL config
  migration, `RslRlVecEnvWrapper`, `get_inference_policy`).
- Task: pass over a waypoint marker (within 0.6 m) and stop on the goal marker (within 0.5 m),
  both placed from the seed 3–4.5 m away, 60 s of simulated walking. API: `get_pose`,
  `get_goal`, `get_waypoint`, `distance_to`, `heading_to`, `walk(vx, vy, wz, seconds)`, `stop`.
  Failures: `fell`, `missed_waypoint`, `not_at_goal`, `left_arena`, `budget_exhausted`, plus the
  program-level ones. Feedback per call: pose, distance and bearing to the goal, heading error with
  its sign explained, waypoint distance, whether the robot fell during that call.
- Cameras follow the robot (a chase view and a top-down view): a fixed camera showed a speck.

Traps (all in `FEEDBACK.md`): `resolve_task_config` parses `sys.argv`; RSL-RL 5 needs the config
migration outside the play script; the Warp renderer does not draw collision-free shapes, and a
2 cm colliding marker tripped the Go2, so the markers are 6 mm discs.

## 2. Pick-and-place on the Franka (`agent/place.py`)

`--task place` adds a green target disc on the table 15–22 cm from the object (placed from the
seed), `get_target()` to the grasp API, and a judge that wants the object resting within 3 cm of
the disc's centre with the gripper open after a lift of at least 3 cm. Failures: `never_lifted`,
`still_holding`, `placed_off_target` (with the offset in words), `not_resting`, `object_off_table`.
The reference program is the lift reference plus carry, lower and release.

## 2b. Drawer opening on NVIDIA's cabinet scene (`agent/drawer.py`): built, not benchmarked

`--task drawer` builds our env around NVIDIA's `Isaac-Open-Drawer-Franka` scene with its Newton preset
(600 Hz physics, decimation 10), our IK action, finger contact sensors against the handle, and a
judge on the drawer joint (open ≥ 0.20 m at the end of the program). The hand's default orientation
is the handle's; `get_handle()` and `drawer_opening()` join the API. Found on the way: a fixed-base
cabinet cannot be moved after the Newton build, so scenarios vary through the drawer's initial
opening and the arm's start pose; the step budget had to become time-based (900 steps is 15 s at
60 Hz); the drawer stops at about 0.33 m and pulling past the stop tore the handle out of the
fingers. The scripted reference opens the drawer on 1 of 5 seeds (0.26 m); on two seeds the handle
slips out of the gripper under the drawer spring during the pull, on two the approach misses the bar
when the drawer starts partly open. That is a grasp-tuning problem, left open: the task is in the
repo and the matrix, but without a Nemotron run.

## 3. Results (grids of 2026-10-29, 00:00–02:00 PT)

Eight seeds (100–107) per cell, four conditions, Lightning with thinking, three attempts, same
matched-seed design as the Franka benchmark (doc 01). Records: `_logs/scale/<cell>.json`, published
under `results/scale-2026-10-29/`; the table is `eval/matrix.py`'s output; the paired statistics per
cell come from `eval/stats.py`.

| robot | task | reference | one-shot | rerun | physics feedback | $ |
|---|---|---|---|---|---|---|
| Unitree Go2 (quadruped) | navigate: waypoint, then goal | 8/8 | 4/8 | 4/8 | 6/8 | 0.07 |
| Unitree G1 (humanoid) | navigate: waypoint, then goal | 8/8 | 2/8 | 2/8 | 6/8 | 0.05 |
| Franka Panda | pick and place, cube | 8/8 | 4/8 | 4/8 | 7/8 | 0.06 |
| Franka Panda | pick and place, thin box | 8/8 | 3/8 | 3/8 | 5/8 | 0.07 |
| Franka Panda | pick and place, tall box | 8/8 | 0/8 | 0/8 | 1/8 | 0.12 |
| **all five cells, paired** | 40 scenarios | 40/40 | 13/40 | 13/40 | **25/40** | 0.37 |

Pooled over the 40 scenarios (`results/scale-2026-10-29/stats/stats.md`): one-shot 13/40 (32 %), rerun 13/40,
physics feedback 25/40 (62 %); paired physics − one-shot **+0.30, 95 % bootstrap interval
[+0.12, +0.47]**, the same against the rerun. The Franka lift benchmark (doc 02) found +0.19
[+0.04, +0.33] over 48 scenarios; the effect carries to new bodies and a new task.

What the cells say:

- **The loop transfers.** On every cell the physics-feedback condition beats one-shot, and the
  rerun control (same program three times, no feedback) never does: the gain is the words, not the
  retries. G1: 2/8 → 6/8, paired difference +0.50 with a bootstrap interval [+0.00, +0.88] that
  touches zero at n=8 (the first physics run, 7/8, had +0.63 [+0.12, +1.00]). Place on the cube:
  4/8 → 7/8, +0.38 [+0.12, +0.75], clear of zero; thin box 3/8 → 5/8, +0.25 [+0.00, +0.50].
- **What Nemotron gets wrong on a walker** (last-attempt categories, one-shot): on G1, two
  programs raised `NameError` (a variable set in one branch only, `waypoint` used as a function),
  one used a `while` loop for angle wrapping, which the sandbox refuses, one missed the waypoint,
  two stopped short. The physics feedback repairs all but one of these within three attempts. On
  Go2 the programs run but oscillate: a bang-bang turn (`wz = ±1.0` for a whole second, or a gain
  of 0.15 rad/s per degree) overshoots the bearing every call, and the run ends at the 60 s budget
  one or two metres from the goal. `eval/nav_paths.py` draws it from the saved trace
  (`results/scale-2026-10-29/figures/`).
- **Two things found and fixed during the grids, both documented in the records.**
  1. *The hand-written reference toppled the Go2 on 2 of 8 starts* (seeds 105, 106: it spun in
     place at 0.8 rad/s for 3 s while facing 150–170° away from the waypoint; the 8-minute policy
     does not survive that). The reference now turns at ≤ 0.6 rad/s with 0.15 m/s forward speed.
     The scripted condition was rerun for both walkers on the fixed reference (Go2 6/8 → 8/8, G1
     8/8 → 8/8) and folded into the records with `eval/merge_grid.py`, which stores the source and
     the replaced numbers under `merged`. The Nemotron conditions were not touched: they never see
     the reference. First records: `results/scale-2026-10-29/parts/*_v1.json`.
  2. *The walking feedback showed only the first 30 trace events*, i.e. the first 15 s of a 60 s
     run: Nemotron was repairing a program whose ending it had never seen. It now shows the first
     10 and last 12 calls, drops the `get_pose` echoes, counts sign changes of the heading error
     ("the turn commands overshoot the bearing instead of settling on it") and states the closest
     approach to the goal. The physics condition was rerun for both walkers with the new wording
     (`results/scale-2026-10-29/parts/*_physics_v2.json`) and is the number in the table; the first run is the
     ablation: **Go2 5/8 → 6/8, G1 7/8 → 6/8.** Same seeds and model, but not the same
     first programs: Nemotron's sampling is not deterministic, and on G1 the first attempts, which
     see no feedback at all, passed 6/8 in the first run and 4/8 in the second; on Go2, 3/8 and
     then 1/8. What the wording changes is the repair rate after a failed first attempt: Go2 2 of 5
     → 5 of 7, G1 1 of 2 → 2 of 4, together 3 of 7 → 7 of 11. Suggestive, not significant at this
     size; the second wording is the one in the code. Go2 paired C − B: +0.25 [−0.25, +0.75].
- **Pick-and-place is a harder grasp than lift**: `never_lifted` dominates the failures (the place
  programs also have to carry, lower and open), and `placed_off_target` appears when the release
  happens above the disc's edge. The thin box, which the lift loop handled at 7/8 (doc 02), drops
  to 5/8 once the program also has to carry it, lower it and let go. The tall box is the floor of
  the matrix: 0/8 one-shot, 1/8 with feedback (seed 107, attempt 2), 14 of 24 physics attempts
  `never_lifted` and 4 rejected by the sandbox; the lift benchmark had it at 1/8 → 3/8. The
  feedback states the fingertip offset and the palm distance, and Nemotron still closes too high
  on a 14 cm box more often than not: the prior it lacks is the same one doc 02 found on the
  small sphere.
- **Cost**: the five cells plus the two scripted and two physics reruns cost $0.47 of Token
  Factory credit and 3.8 grid-hours of laptop GPU, run three to four grids at a time
  between 00:00 and 01:45 PT.

**Thinking off on the walkers** (`--reasoning none`, one-shot and physics only, same seeds;
`results/scale-2026-10-29/parts/*_nav_nothink.json`): Go2 one-shot 2/8 and physics 2/8 (thinking on:
4/8 and 6/8); G1 0/8 and 0/8 (2/8 and 6/8). The dominant failure is `left_arena`: without reasoning
the programs command a heading and walk until the 8 m boundary, and the feedback does not rescue
them within three attempts. Cost $0.005 and $0.007 per robot against $0.07 and $0.05 with thinking.
Doc 02 §6 found reasoning roughly doubling success on the Franka; on a walker it is the difference
between a working loop and none.

**The camera reviewer on the new bodies and tasks** (`eval/review_record.py`, Nemotron Super-VL, 8 frames
per attempt, every filmed attempt of every condition, physics verdict hidden; records
`results/scale-2026-10-29/review_*.json`). The reviewer needed a task text per family (walk over the
blue disc and stop on the green one; pick up, carry, set down, open) and, for the walkers, a camera
note: the top-down camera follows the robot, so the robot sits at the frame's centre and the discs
move under it, and the chase camera's last frame is appended because a humanoid's body hides a 35 cm
disc from six metres up.

| cell | attempts | agree | false positive | false negative | what the misses are |
|---|---|---|---|---|---|
| Go2 navigate | 51 | 45 | 6 | 0 | one program (seed 103, one-shot and its three reruns) passed 1.4 m from the waypoint and the reviewer calls the disc crossed; one run 1.9 m short of the goal read as on it in the chase frame; one fall read as a success. Top view only: 45 (5 false positives, 1 false negative) |
| G1 navigate | 50 | 39 | 3 | 8 | top view only: 35 (14 false negatives, "never reached the disc" while standing on it); with the chase end frame but no note: 34; with the note: 39. The rest are depth reads in the chase view |
| place, cube | 50 | 37 | 0 | 13 | every miss is "still holding at the end" on a cube the judge saw released: the side camera cannot resolve a 1.5 cm finger gap |
| place, thin box | 50 | 47 | 0 | 3 | the same "still holding" read |
| place, tall box | 63 | 63 | 0 | 0 | the reviewer and the judge agree on every fall and every miss |

Pooled: **231 of 264 attempts agree, 9 false positives, 24 false negatives**, $0.26 of reviewer calls.
Same shape of result as the Franka benchmark's 423/437 (doc 02): the camera judge is categorical and
never once calls a clear failure a success on the Franka, while every false negative sits at a
metric boundary the frame cannot resolve. For walkers the first question is what the camera can see at
all; one sentence about the camera moved the G1 agreement from 35 to 39 of 50. These reviews used
clean footage: the place-cube films and the Go2 one-shot and rerun films were replayed with
`eval/refilm.py` (49 of 49 replays, 33 place-cube and 16 Go2, reproduced their recorded outcome;
the originals held another grid's frames, doc 05 §6), and `--exclude-before` drops any film that predates the staging
fix without a replay.

Films (local run artefacts, not in this repository): `_logs/scale/review/` (273 clips, one per attempt, title, clock, metric and verdict burned
in; the place-cube one-shot and physics episodes are replays via `eval/refilm.py`, and 25 Go2
one-shot/rerun and place-cube rerun clips were rebuilt from the frames that survived the shared
staging folder, doc 05 §6), `_logs/scale/report/index.html`, `_logs/scale/figures/` (attempt paths),
and the demo cut's "Robots × tasks" section (`eval/make_demo.py --scale _logs/scale`).

## 4. What this is not

- Not a second benchmark at the Franka's sample size: 8 seeds per cell, four conditions, intervals
  wide. The vision reviewer judged every filmed attempt after the fact (above) but did not drive
  repairs on these cells: there is no D condition here.
- The G1 ran on NVIDIA's flat preset as shipped, whose MJWarp contact cap is 10 while the humanoid
  makes up to 30 contacts in play mode: the surplus is dropped and the log says so on every step
  (`FEEDBACK.md`, 2026-10-29). The reference still walked 16/16 across both scripted runs; the cap was
  left alone so the records and the code agree. Raising it is a one-line change in
  `make_loco_env_cfg` and would be the first thing to re-verify.
- Not bimanual, not an AMR, not a humanoid manipulation: those need scenes NVIDIA does not ship
  kit-less (OpenArm has a two-arm config and GR1T2 a Newton asset, but no tabletop task), and
  are the first items after the hackathon.

## 5. Next steps, in order of value per hour

1. **A D condition (physics + vision feedback) on the walkers and the place cells**, since the
   reviewer has a task text per family: `run_grid --conditions vision --cameras …` per cell, about
   40 min and $0.10 per cell, and the matrix's last column fills in. Only worth it if the reviewer's
   false positives on the Go2 (6 of 51) are acceptable in the loop.
2. **The nav API doc could pre-empt two sandbox rejections** (`while` loops, attribute access on
   the walk result) that cost first attempts on both walkers. Changes conditions B and C, so it
   means rerunning them (about 1 h for both walkers); the records here stay as the "before".
3. **Raise the G1 preset's contact cap** (`nconmax` 10 → 40, one line in `make_loco_env_cfg`),
   re-verify the scripted gate, and note the records were produced on the shipped preset.
4. **The drawer task**: the reference opens it on 1 of 5 seeds; the handle slips under the spring.
   A firmer grasp (higher finger gains or a deeper grip on the bar) is the fix to try; then one grid.
5. **More seeds on Nebius**: the cube cell has run on a Nebius H100 VM (doc 04), which showed a
   one-environment sim is latency-bound, so growing the 8-seed cells to 16 is cheapest as several
   small GPU replicas (L40S jobs running `eval/run_scale.sh`) rather than one H100.

