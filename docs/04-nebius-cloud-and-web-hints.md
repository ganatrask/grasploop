# 04 — The same loop on a Nebius H100, and web hints from Tavily (2026-10-29)

Two additions on the last day before the freeze, both using Nebius beyond Token Factory. The first
runs the frozen benchmark's cube cell, unchanged, on a Nebius AI Cloud H100 and then extends it with
eight new seeds. The second adds a condition to the repair loop in which Tavily, Nebius's search API,
answers one question per failure mode. Records: `results/cloud-2026-10-29/` and
`results/tavily-2026-10-29/`. Frictions are rows in `FEEDBACK.md` dated 2026-10-29.

## 1. Why run the same thing on an H100

The physics result is not new, and this document does not claim it is. The run is evidence for three
things the submission otherwise only asserts:

1. **It reproduces off the laptop.** Every number in the repo came from one machine until today. A
   second machine, a different GPU architecture and a fresh install from the lockfile produce the same
   cell within the noise the benchmark already measures (condition C0).
2. **It runs on the GPU a cloud has in bulk.** The H100 has no RT cores; Nebius's own Isaac Sim recipe
   says H100 and A100 cannot run it. The kit-less Isaac Lab 3.0.0 GA stack on Newton with Warp ray-traced
   cameras runs there, filming included.
3. **It gives the scaling numbers.** Wall seconds and dollars per scenario on an H100 are what sizing a
   64-scenario run on Nebius needs.

## 2. Setup

Nebius AI Cloud is a separate product from Token Factory, with its own tenant and billing: the
hackathon account (`aitenant-…`) could create no compute, so a second sign-up and a $25 card payment
were needed (`FEEDBACK.md`). The CLI profile was pointed at the eu-north1 project, the one region with
both H100 and L40S.

```bash
eval/cloud/nebius_vm.sh create gpu-h100-sxm 1gpu-16vcpu-200gb   # ubuntu24.04-cuda13.0 image, 100 GiB disk, public IP
eval/cloud/nebius_vm.sh bootstrap                                # IsaacLab v3.0.0, uv sync --frozen: 1 min 52 s
eval/cloud/nebius_vm.sh push                                     # the code (working-repo commit 17db1e7), the two walker policies, the API key
eval/cloud/nebius_vm.sh run cube --shape cube --seeds 8 --seed0 100 \
    --conditions scripted,oneshot,rerun,physics,vision --review-all \
    --cameras _logs/cloud/frames --video _logs/cloud/video
eval/cloud/nebius_vm.sh pull && eval/cloud/nebius_vm.sh delete
```

| | laptop | Nebius VM |
|---|---|---|
| GPU | RTX 5090 Laptop, 24 GB, sm_120 | H100 80 GB HBM3, sm_90 |
| driver | 580.173.02 | 580.173.02 (image `ubuntu24.04-cuda13.0`) |
| stack | Isaac Lab 3.0.0 GA `v3.0.0`, torch 2.11+cu130, Warp 1.17, Newton 1.6.1, `ovrtx` extra | identical, from the same `uv.lock`; the `ovrtx` extra (hero camera only) was missing from the first bootstrap and added before the hero shots |
| Isaac Sim | none | none |
| price | owned | $4.50 per hour on demand |

`push` writes `NEBIUS_API_KEY` to `~/.grasploop_env` on the VM (mode 600) so detached runs can read it;
it lives there until `delete` destroys the VM and its boot disk.

The first VM was unreachable: the Compute quickstart pipes the cloud-config through `jq -Rrs`, and
CLI 0.12.298 stored that JSON literal verbatim, so cloud-init created no user. Raw text works. One
create-and-delete cycle, about ten minutes.

## 3. Replication: the cube cell, seeds 100–107

Same command, same five conditions, same seeds, same model and reviewer on Token Factory. The laptop
column is the frozen benchmark record `results/bench-2026-10-27/franka_cube.json`.

| condition | laptop | H100 | laptop pass seeds | H100 pass seeds | wall s per scenario, laptop / H100 |
|---|---|---|---|---|---|
| A scripted reference | 8/8 | 8/8 | 100–107 | 100–107 | 3.1 / 10.9 |
| B one-shot | 4/8 | 6/8 | 102 103 106 107 | 100 101 104 105 106 107 | 22.0 / 37.9 |
| C0 rerun, no repair | 4/8 | 6/8 | same as B | same as B | 4.4 / 5.2 |
| C physics feedback | 8/8 | 7/8 | 100–107 | all but 106 | 33.6 / 62.9 |
| D physics + vision | 8/8 | 7/8 | 100–107 | all but 103 | 61.9 / 76.5 |

Reading it:

- **The cell replicates.** The scripted reference is 8/8 on both. The model conditions differ by one or
  two seeds in either direction, which is what the benchmark's own noise floor predicts: C0 reruns the
  identical program and gets a different outcome on some seeds, and Nemotron samples at temperature 0.2.
  Nothing in the H100 column is outside what the laptop's intervals allow.
- **A single-environment simulation is latency-bound, and the H100 is the slower machine for it.** The
  scripted scenario takes 3.5× longer on the H100 and the model conditions 1.2–1.9×. The sim steps one
  environment at a time, so a datacenter GPU's throughput buys nothing and its lower clocks cost; the
  Token Factory endpoint is in us-central1, so eu-north1 adds a round trip per model call. The lesson is
  the one Nebius's own serving post drew for Cosmos: for this workload, many small replicas beat one big
  one. The way to 64 scenarios is 8 L40S jobs, not one H100.
- **Reviewer.** The Super-VL reviewer, run over all 55 filmed attempts of the cell afterwards, agreed with
  the physics judge on 55 of 55 (the laptop's 437-attempt figure was 423, with 14 under-threshold lifts
  counted as false positives; none occurred here).
- **Cost.** The whole cell, 8 scenarios × 5 conditions with every attempt filmed and reviewed: $0.134 of Token Factory
  credit, 28 minutes of grid wall time plus the review pass, about 35 minutes of H100 time, $2.60 at
  list price. Bootstrapping the stack from the lockfile took 1 min 52 s. The whole day on the VM, replication,
  extension, hero shots and idle time included, was 1 h 41 min (created 20:04 UTC, deleted 21:45 UTC): $7.60 at list
  price, plus the ten-minute first VM, plus $0.28 of Token Factory credit.

## 4. Extension: seeds 108–115, and the 16-seed cell on one machine

The same command with `--seed0 108`, started when the replication's review pass ended: 24 minutes of grid wall
time, $0.142 of Token Factory credit, 70 filmed attempts. Record `results/cloud-2026-10-29/cube16.json`; the
pooled statistics over both H100 records are in `results/cloud-2026-10-29/stats/stats.md`.

| condition | seeds 108–115 | pooled, 16 seeds on the H100 | 95% CI | first attempt |
|---|---|---|---|---|
| A scripted reference | 8/8 | 16/16 | 0.81–1.00 | 16/16 |
| B one-shot | 2/8 | 8/16 | 0.28–0.72 | 8/16 |
| C0 rerun, no repair | 2/8 | 8/16 | 0.28–0.72 | 8/16 |
| C physics feedback | 7/8 | 14/16 | 0.64–0.96 | 7/16 |
| D physics + vision | 5/8 | 12/16 | 0.51–0.90 | 4/16 |

Paired over the 16 scenarios: physics feedback beats one-shot and the no-repair rerun by +0.375 (+0.06 to +0.69),
separated from zero; vision on top of physics is −0.125 (−0.44 to +0.19), not separated. The Super-VL reviewer
agreed with the physics judge on 125 of 125 filmed attempts across both runs.

Reading it: the new seeds were harder for the one-shot program (2/8) and physics feedback recovered five of them,
so the repair effect on the cube is now established on 16 scenarios from one machine, with an interval that
excludes zero on its own. Vision did worse than physics alone on the new seeds (5/8 against 7/8), which is the
same conclusion the laptop's 48 scenarios reached: the camera's diagnosis adds nothing separable on top of the
measurements. The laptop's eight seeds and the H100's first eight are reported side by side as a replication
pair (§3) and not pooled with these, because they came from a different machine.

## 5. Renders from the cloud

Every attempt on the H100 was filmed by the two Warp review cameras (640 × 480 PNG frames per attempt, pulled to
`_logs/cloud/vm/video/`), and `eval/make_videos.py` turned them into 55 banner clips and a 10.2-minute reel
(`_logs/cloud/review/`). After the grid, `eval/refilm.py --hero` replayed three passing physics attempts
(seeds 100, 102, 105; all three passed again) with the OVRTX path-traced hero camera at 1280 × 720, on the
same H100: 220–242 frames each, `_logs/cloud/vm/hero/`. The first replay took 176 s, the shader compile on
first use; the next two 23–26 s. `_logs/cloud/nebius_h100_clip.mp4` is a 20-second labelled cut of the three
(lower third, trial chip, verdict chip, the reviewer's camera as picture-in-picture), and
`eval/make_demo.py --cloud-hero` places the first of them in the demo after the thin-box shot and amends the
closing card.

```bash
ssh grasploop@<vm> 'cd ~/grasploop && . ~/.grasploop_env && .../python eval/refilm.py --record _logs/cloud/cube.json \
    --condition physics --seed 100 102 105 --attempt 0 --viz none --hero _logs/cloud/hero --json _logs/cloud/refilm_hero.json'
$PY eval/make_videos.py --video-dir _logs/cloud/video --results results/cloud-2026-10-29/cube.json --out _logs/cloud/review
```

## 6. Web hints from Tavily: condition E

`agent/hints.py`. After a failed attempt, one Tavily `POST /search` with `include_answer`, the query
built from the robot, the task, the object's shape and the feedback's first line (attempt number,
failure name and the judge's detail). The answer plus the three source titles join the feedback as an
addendum, exactly as the vision reviewer's diagnosis does in condition D, so E − C isolates what web
retrieval adds. One call per distinct query per process; a repeated query comes from a cache.

Measured on the small sphere, the one shape where every Nemotron program fails the same way (closes at
the equator) and where a rule from outside the measurements could in principle help:

```bash
$PY eval/run_grid.py --viz none --shape sphere_s --seeds 8 --seed0 100 --conditions physics,hints \
    --json _logs/tavily/sphere_s.json
```

| condition | success | first attempt | final failure modes | wall s | Token Factory $ |
|---|---|---|---|---|---|
| C physics feedback | 0/8 | 0/8 | slipped ×8 | 143.9 | 0.064 |
| E physics + web hints | 0/8 | 0/8 | slipped ×4, invalid program ×2, IK not reached ×1, missed ×1 | 172.3 | 0.066 |

Paired difference +0.00 on 8 scenarios. Six real Tavily calls, ten cache hits, 4 s per call, +28 s per
scenario. The hints changed what the model wrote and not whether it worked: the answers were Franka
handbook passages about fingertips and de-energised grippers, because no web page describes this scene.
That is the expected shape of the result and it is reported as such. A null on one shape and eight
seeds bounds the effect loosely; the table in `results/tavily-2026-10-29/stats/stats.md` has the
intervals. One defect in the queries as run: `describe()` keeps only object keys that `get_object()`
does not return, so every query said "Object: shape sphere_s" without the 4 cm diameter. A query with
the size might have found more specific text; the null holds for the queries the record shows.

The loop ran on Nebius compute as a VM rather than a Serverless Job because a Job needs a container
image or a public repository to fetch from, and neither existed on the day.
