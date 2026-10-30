# 05 — GraspLoop build log, 2026-10-27 to 2026-10-29

What was built, what broke, what fixed it, with the numbers: the first day in §1–§5, the overnight
scale grids and the demo footage of 2026-10-29 in §6–§7. Everything ran on the laptop; the kit-less
Isaac Lab 3.0.0 GA interpreter (`~/workspace/isaaclab-3.0.0-ga/.venv/bin/python`), Newton/MJWarp
physics, NVIDIA's Franka lift scene. Records are under `_logs/` (git-ignored).

## 1. Timeline

| PT | Milestone | Evidence |
|---|---|---|
| 15:12 | Build plan agreed | — |
| 15:40 | `agent/env.py`: NVIDIA Franka lift scene + the soft task's IK action + the lift task's Newton preset, as a `ManagerBasedEnv`; builds and steps kit-less in 13 s | `_logs/env_smoke.json` |
| 16:05 | **Gate T1 passed**: hand-written reference program lifts the cube 5/5 (13.4–14.2 cm held) | `_logs/gate_t1.json` |
| 16:10 | Nemotron loop end to end, first run 1/3 (truncation) | `_logs/loop_cube_lightning.json` |
| 16:16 | **Gate W1 passed**: Nemotron 3.5 Lightning's code lifts the cube 3/3, one repair, 7 calls, $0.018 | `_logs/loop_cube_lightning2.json` |
| 16:25 | Vision condition end to end: frames → Super-VL → structured JSON → repair prompt; $0.0022 per episode | `_logs/vision_test/loop.json` |
| 16:35 | Stiff gripper: cube 5/5, thin box 5/5, sphere 1/5 | `_logs/gate_t1_*.json` |
| 16:40 | Cube pilot grid launched (5 conditions × 5 seeds) | `_logs/grid/cube_pilot2.*` |

## 2. What is NVIDIA's and what is ours

NVIDIA, unchanged: `FrankaSceneCfg` (robot with the lift-task gains, table, object presets,
fingertip contact sensors), `DifferentialInverseKinematicsActionCfg` + `BinaryJointPositionActionCfg`
as the soft task configures them, `lift_env_cfg.PhysicsCfg.newton_mjwarp`, `resolve_presets`, the
Warp camera renderer, `FRANKA_PANDA_HIGH_PD_CFG`'s gravity-off choice.

Ours (`agent/`, `judges/`, `eval/`): the env wrapper and seeded placement, the 12-function grasp
API, the sandbox, the physics judge, the Token Factory client, the repair loop, the review
cameras, the vision reviewer, the grid runner. About 1,100 lines.

## 3. Traps and fixes, in order

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `PhysicsCfg.newton_mjwarp` attribute error; `clone(NewtonCfg)` TypeError | presets live on instances; `NewtonCfg.class_type` is derived | `resolve_presets(cfg)` on the whole config, as the task loader does |
| 2 | IK drove the hand 0.65 m away from a 9 cm target | "hand down" asked as 180° about x is a 180° wrist yaw from home, beyond joint 7's ±166° | hand-down = 180° about **y** (`(0,1,0,0)` xyzw), `yaw_quat` = qz(yaw)⊗qy(180) |
| 3 | 2–4 cm steady residual, no joint at a limit | the position-restarting IK never integrates out PD gravity sag (the IK term's own ee estimate agrees with ours) | `disable_gravity=True` on the robot (NVIDIA's HIGH_PD choice) + a gated outer-loop integrator for the remainder |
| 4 | "reached" fired with the hand 48–50° from vertical | position tolerance met before the orientation converged | reached = position < 6 mm **and** orientation < 4° |
| 5 | descent shoved the cube 3–5 cm; pads closed on the diagonal | stepped IK command → curved path; 8 cm opening on a 5 cm cube leaves ~1 cm per side | ramp the command along a straight line at 0.15 m/s; integrators only once the command is stationary |
| 6 | fingers "close" to 3.8 cm on air and on a 2.5 cm box, no contact | lift task's gripper drive is RL-slowed (τ = 0.5 s) | gripper gains 2e3 / 1e2 |
| 7 | `open()` rejected by the sandbox | clashes with the builtin | `open_gripper()` / `close_gripper()` |
| 8 | a third of Nemotron replies had no code | Lightning spent the whole 6k budget reasoning (`finish: length`) | 12k budget, one retry at 24k, `truncated` recorded; `--reasoning none` switch |
| 9 | judge said `ik_not_reached` for a formed grasp that slipped | precedence | only > 2 cm shortfalls count; a closed grasp that loses the object is `slipped` |

Still open: the approach move from home converges to 0.8–1.0 cm, just above the 6 mm tolerance,
so it reports `reached: False` although the descent that follows reaches 5–6 mm; cosmetic for
now, confusing for a model reading the trace. The medium sphere rolls off the table in 3 of 5
reference runs: that is a real challenge object, left in the benchmark on purpose.

## 4. Numbers worth keeping

- Env build + first step: 13 s cold; a 5-seed scripted gate: 14–17 s wall.
- One Nemotron Lightning episode (thinking on): 45–110 s wall, mostly waiting on 8–15k reasoning
  tokens; $0.003–0.007. Thinking off: 15 s, $0.0004, but 0/3 on the first try.
- Super-VL review of 8 frames at 320×240: valid JSON every time so far (3/3), ≈ $0.0006 per review.
- Reference program: cube 5/5, thin box 5/5, medium sphere 1/5 (rolls).

## 4a. Cube pilot grid (17:00 PT): 5 evaluation seeds (100–104), Lightning with thinking, 3 attempts

| Condition | Success | 95 % CI | Mean attempts | $ | Last failure reasons |
|---|---|---|---|---|---|
| A scripted reference | 5/5 | 0.57–1.00 | 1.0 | 0 | — |
| B Nemotron one-shot | 3/5 | 0.23–0.88 | 1.0 | 0.025 | invalid (truncated twice), no_contact |
| C0 rerun of B's program, no repair | 3/5 | 0.23–0.88 | 1.8 | 0 | same two: **no outcome flipped on rerun** |
| C physics feedback | 4/5 | 0.38–0.96 | 2.0 | 0.023 | slipped |
| D physics + vision | 4/5 | 0.38–0.96 | 2.0 | 0.034 | object_missed |

25 episodes, $0.082, 31 min wall on the laptop. The reviewer (Super-VL) agreed with the physics
judge on 5/5 reviewed attempts, all failures; `--review-all` was added afterwards to measure
false positives on successes too. At n = 5 nothing separates C from D; the pilot's job was to
prove the pipeline and find headroom: one-shot at 60 % leaves room, and the repairs are not
luck (C0 = B).

## 4b. Allegro rung, first evening (17:15–18:30 PT)

NVIDIA's `Isaac-Lift-KukaAllegro` scene, kit-less, with our IK action on the arm and absolute finger
targets. Measured and fixed:

| Symptom | Cause | Fix |
|---|---|---|
| Every IK target 10–20 cm short, hand sinking to the table even on "+10 cm up" | the task's Kuka gains (stiffness 200) are RL gains; `disable_gravity` has no visible effect on this asset; the arm sagged 13 cm at home | arm and finger gains ×8 (`ALLEGRO_GAIN_SCALE`): all hand-down targets then reach 5–6 mm / 1–2.5° |
| Fingers push the cube past the thumb | thumb closed pose | the "flex" thumb pose (1.5, 0.5, 1.3, 1.3) from a 12-combination sweep: 19.8 cm lift, 4 fingertips in contact |
| Yawed hand-down targets at yaw 45/90 hit the joint-4 limit | wrist configuration | reference program uses yaw 0; the Allegro API doc states the smaller yaw range (`agent/graspapi.py`) |

Scripted power grasp, 5 seeds: **cube 1/5**, **small sphere 0/5** (rolls off the table every time).
The IK side is done; the grasp itself is fragile against the object's yaw and the sphere needs a
different approach (slower closure, lower grasp point). Gate W2 (≥ 3/5 on sphere and box by Wed
18:00 PT) is open; the Franka track is unaffected (regression 5/5 after every change).

## 4c. Filmed showcase (18:27–18:50 PT): every stage on camera, `_logs/showcase/review/`

`eval/record_showcase.sh` films each stage with `--video` (both Warp cameras, 640×480, 15 fps, per
attempt) and `eval/make_videos.py` composes one mp4 per attempt (banner: trial, clock, object rise,
gripper state, physics verdict) and a 7.7-min reel with title cards that show the program that ran.
36 clips, 20 min of sim, $0.04 of Token Factory credit. Seeds 100–102.

| Stage | Result | Clips |
|---|---|---|
| Franka scripted: cube, thin box, small sphere | 3/3, 3/3, 3/3 | 1–9 |
| Franka scripted: medium sphere, tall box, capsule | 1/3 (rolls off), 0/3 (palm meets the top), 0/3 | 10–18 |
| Franka cube, Nemotron: one-shot / physics / physics+vision | 1/2 / 1/2 / 2/2 | 19–27 |
| Franka thin box, Nemotron + physics | 2/2 (one repair; attempt 2 lifted 36 cm) | 28–30 |
| Franka tall box, Nemotron + physics | 0/1 in 3 attempts | 31–33 |
| Allegro scripted cube | 0/3 (no_contact ×2, object_missed) | 34–36 |

Seen on film, not in the numbers:
- **The dominant Nemotron failure is one misconception**: it sends the grasp point to
  `pos.z + half_height + 0.03`, i.e. the fingertips stop 5 cm above the cube and close on air
  (clips 19, 22–24, 26, 29). The physics feedback reports "no fingertip ever touched the object" and the
  raw fingertip/object positions, and the model repeated the same z three times (seed 101, physics).
  The vision reviewer's sentence ("the gripper descends onto the cube... presses down on it") made the
  same model fix it in one attempt (clip 27). Cheap fix for the physics feedback: state the vertical
  offset between the fingertips and the object centre at close time in words.
- The tall box is beyond the top-down strategy for both the reference and the model: a centre grasp
  jams the palm on the top (`insufficient_lift`, 3 cm), and the yaw-aligned retry knocks it over.
- Allegro: the hand reaches the target (5 mm) but at object yaws 97°/167°/−119° only two fingertips
  touch and the cube is pushed, never enclosed. Grasp-point and closure sequence need work, not IK.
- Two robots filming the same tag overwrote each other's frames; directories now carry the robot name.

## 5. Fixes after the showcase (19:00–19:40 PT), all verified by gate before commit

| Issue seen on film | Fix | Evidence |
|---|---|---|
| Nemotron closed 5 cm above the cube three times with the raw fingertip/object positions in front of it | `close_gripper` records the fingertip offset from the object centre, the object's top and the palm face; `feedback_text` says it in words ("closed 3.0 cm ABOVE the object's centre, 0.5 cm above its top face: they closed on air") | cube seed 101, physics: 0/3 → pass on attempt 2 |
| The straight path from home swept the tall box over; the feedback never mentioned the object moving before the close | every trace record carries `moved_xy_m`; a jump > 1.5 cm during a non-lift call is reported as a collision with advice to approach from above | box_tall seeds 100–101, physics: 0/1 → 2/2 |
| Reference program jams the palm on objects taller than the fingers | palm face is 4.9 cm above the fingertip point (`PALM_OFFSET`); the reference grasps 3.5 cm below the top when the object is taller than 7 cm; the API doc states the palm distance | box_tall scripted 0/5 → 5/5 |
| Approach from home reported `reached: False` at 1–1.4 cm | `move_to` timeout is at least the ramp time plus 2.5 s | vision a1 traces: approach now reaches |
| The standing capsule toppled on its own before the hand arrived (0/5, no contact) | capsules spawn lying along x; `object_yaw_deg()` reports the long axis heading (robust to the 90° pitch); extents updated | capsule_s scripted 0/5 → 5/5 |
| Both robots filmed under the same tag and overwrote each other | video and frame folders carry the robot name | Allegro clips present in the rebuilt reel |

Regression after all of it: cube 5/5, thin box 5/5, small sphere 5/5. Prompt and model settings are
fixed for the benchmark from here on (doc 01).

## 6. Overnight 2026-10-29 (00:00–02:00 PT): what the scale grids found, all fixed and committed

| Issue | Fix | Evidence |
|---|---|---|
| Three grids filmed at once: every recorder staged frames in the same `_recording/` folder and each reset wiped the others' frames, so the Go2 clips held other robots' frames | the staging folder is `_recording_<pid>`; `eval/refilm.py` replays a stored program on its seed and films it, tagged `refilm<condition>` | Go2 physics passes replayed 5/5, place-cube episodes 7/7, same verdicts as recorded |
| The hand-written walking reference toppled the Go2 on 2 of 8 starts: it spun in place at the full 0.8 rad/s while facing 150–170° from the waypoint | turns at ≤ 0.6 rad/s with 0.15 m/s forward speed; the scripted condition rerun and folded in with `eval/merge_grid.py`, which keeps the source and the replaced numbers | Go2 scripted 6/8 → 8/8, G1 8/8 → 8/8 (doc 03 §3) |
| Walking feedback showed the first 30 trace events: the first 15 s of a 60 s run, with every `get_pose` echo doubling the volume | head and tail of the run, no echoes, a count of heading-error sign changes ("the turn commands overshoot the bearing"), closest approach to the goal | physics condition rerun as v2 for both walkers; v1 kept as the ablation (doc 03 §3) |
| The clip banner said "gripper open" on a quadruped and "cube" on a pick-and-place clip (one-shot/physics tags carried the bare shape, scripted ones the scenario name) | banner drops the gripper field for walkers; the loop tags recordings with the scenario name; clip titles take the shape from the record | rebuilt `_logs/scale/review/` |
| No way to see *why* a walker failed without reading 60 trace lines | `eval/nav_paths.py`: top-down path of every attempt from the saved trace, waypoint and goal discs, labels per attempt; the demo cut shows it after each walker clip | `_logs/scale/figures/` |
| The vision reviewer's prompt was about grasps, so the walkers' and place cells had no camera judgement; the first review pass over the films then produced 13 place-cube false negatives whose evidence read "a quadruped walking" (contaminated footage) and 14 G1 false negatives reading "the robot never moved" (the top camera follows the robot) | task texts per family (`judges/vision.py`), `eval/review_record.py` over every filmed attempt with replay films preferred and pre-fix footage excluded, a camera note for walkers plus the chase camera's last frame | agreement with physics: place cube 37/50 on replays, G1 35 → 39 of 50 with the note, tall box 63/63 (doc 03 §3) |

## 7. Demo footage (2026-10-29, 10:00–12:00 PT): the films were made for the reviewer, not for people

The demo cut was assembled from the review clips: two Warp-rendered 640x480 cameras side by side, shadows off,
under a banner. The frames read poorly as a demo against the conventions of published robotics demos (open on
footage, one clean hero view, state the playback rate on the frame, show failures, show many seeds at once).

| Issue | Fix | Evidence |
|---|---|---|
| Review cameras render flat: `NewtonWarpRendererCfg.enable_shadows` defaults to False, 640x480, fixed side views | A hero camera on NVIDIA's OVRTX path tracer (`agent/cameras.py` `hero_camera_cfg`, `--hero DIR` on every runner, `eval/refilm.py --hero`): 1280x720, three-quarter view, soft shadows; the walkers' hero camera chases the robot (`agent/locomotion.py` `HERO_CHASE_CAM`). The review cameras are untouched: the reviewer's frames are part of the frozen method | `_logs/hero_probe/{warp,ovrtx}/sheet.png`: Warp with shadows vs OVRTX on the same episode; 78 ms per OVRTX frame |
| The cut's clips were the review clips, banner and all | `eval/make_demo.py` cuts hero shots full frame: translucent lower third for the narration, a two-line trial chip, the live clock and metric that turn into the verdict at the end, the reviewer's 320x240 camera as a picture-in-picture where the story is about the reviewer, "simulation, real time" stated on every shot, and 2x2 montages of four seeds | `_logs/demo/grasploop_draft.mp4`, `_logs/demo/test_hero_sheet.png` |
| Replays are not deterministic: Go2 seeds 103 and 106 failed on replay after passing in the record | montage and single shots take only replays whose verdict passed again (`hero_passes` checks the refilm record, not the grid record) | `_logs/hero/refilm_go2.json` `same_outcome` |
| Card text ran off the frame ("What the simulator measured") | card lines wrap at the frame width | card 2 at 0:32 |

## Commands used on the day

```bash
PY=~/workspace/isaaclab-3.0.0-ga/.venv/bin/python
$PY eval/gate_t1.py --viz none --shape cube --seeds 5 --json _logs/gate_t1.json
$PY eval/run_loop.py --viz none --shape cube --seeds 3 --model lightning --feedback physics --json _logs/loop.json
$PY eval/run_loop.py --viz none --shape cube --seeds 1 --feedback vision --cameras _logs/v/frames --json _logs/v/loop.json
$PY eval/run_grid.py --viz none --shape cube --seeds 5 --seed0 100 --conditions scripted,oneshot,rerun,physics,vision \
    --cameras _logs/grid/cube/frames --json _logs/grid/cube.json
```
