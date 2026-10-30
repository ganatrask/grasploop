# 02 — Benchmark results, run 2026-10-27 19:45 → 2026-10-28 01:45 PT

The final local benchmark of `docs/01-benchmark-protocol.md`, as run. Everything below is
computed by `eval/stats.py` from the grid records in `results/bench-2026-10-27/` (frames and clips
stay under `_logs/bench/`). Code at commit `1818cc0` of the working repo (the Token Factory retry
fix) plus the frozen method of `508f033`; no prompt, model setting or API changed during the run.

- Robot: Franka Panda (NVIDIA `Isaac-Lift-Franka` scene, Newton/MJWarp). Second robot: Kuka iiwa +
  Allegro, cube only.
- Model: `nvidia/Nemotron-3_5-Lightning`, thinking on, T = 0.2. Reviewer: `nvidia/Nemotron-3.5-Super-VL`.
- 6 shapes × 8 seeds (100–107) = **48 matched scenarios**, 5 conditions, ≤ 3 attempts. 437 filmed
  attempts reviewed. Total Token Factory cost **$1.37**; 5.7 h wall on one laptop GPU.

## 1. Franka, all shapes (48 scenarios)

| condition | success by attempt 3 | 95 % CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s / episode |
|---|---|---|---|---|---|---|---|
| A scripted reference | 43/48 (90 %) | 0.78–0.95 | 43/48 | — | 1.0 | 0 | 3 |
| B one-shot | 14/48 (29 %) | 0.18–0.43 | 14/48 | — | 1.0 | 0.0054 | 33 |
| C0 rerun of B, no repair | 14/48 (29 %) | 0.18–0.43 | 14/48 | 0 / 0 | 2.42 | 0 | 5 |
| C physics feedback | 23/48 (48 %) | 0.34–0.62 | 12/48 | 9 / 2 | 2.31 | 0.0143 | 162 |
| D physics + vision | 26/48 (54 %) | 0.40–0.67 | 8/48 | 14 / 4 | 2.38 | 0.0140 | 137 |

Paired over the same scenarios (percentile bootstrap, 10,000 resamples):

| a − b | diff | 95 % CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|
| C physics − B one-shot | +0.19 | +0.04, +0.33 | 11 | 2 | 12 | 23 | **yes** |
| D physics+vision − B one-shot | +0.25 | +0.10, +0.42 | 15 | 3 | 11 | 19 | **yes** |
| C physics − C0 rerun | +0.19 | +0.04, +0.33 | 11 | 2 | 12 | 23 | **yes** |
| D physics+vision − C physics (primary) | +0.06 | −0.10, +0.23 | 9 | 6 | 17 | 16 | no |

Per shape (successes / 8):

| shape | A scripted | B one-shot | C0 rerun | C physics | D physics+vision |
|---|---|---|---|---|---|
| cube | 8 | 4 | 4 | 8 | 8 |
| thin box (2.5 × 5 × 5 cm) | 8 | 5 | 5 | 7 | 7 |
| small sphere (r 2 cm) | 8 | 0 | 0 | 1 | 2 |
| tall box (5 × 5 × 10 cm) | 8 | 1 | 1 | 3 | 3 |
| lying capsule (r 2.5 cm) | 8 | 4 | 4 | 4 | 6 |
| medium sphere (r 2.5 cm) | 3 | 0 | 0 | 0 | 0 |

## 2. Second robot: Kuka iiwa + Allegro hand, cube, 8 seeds

| condition | success | 95 % CI |
|---|---|---|
| A scripted reference | 7/8 | 0.53–0.98 |
| B / C0 / C / D | 0/8 each | 0.00–0.32 |

The same API, prompt and loop on a four-finger hand: the reference (yaw folded into the wrist range,
grasp point 1.5 cm below the centre, two-stage closure) works, Nemotron never does. Every failure is
`object_missed`: its programs put the grasp point at or above the cube's top face and close on air,
and none approaches from above first. The feedback said so in words only when the program closed the
hand with `close_gripper()` ("closed 4.6 cm above the object's centre, 2.1 cm above its top face"),
7 of the 32 repair messages, and the next program moved the point by millimetres. The other common
closure, the Allegro's own `grasp()`, has no line in the feedback: 19 of the 32 messages followed a
program that closed only with `grasp()` and said nothing about where the hand closed (§4). The 0/8
is therefore partly a feedback gap, not only a missing prior. Reviewer agreement 88/88.

## 3. Findings

1. **Repairs are real, not luck.** Rerunning the one-shot program up to three times without repair
   changed no outcome at all (C0 = B on every scenario, 14/48). Physics feedback lifts the same
   scenarios from 14 to 23, +0.19 with an interval that excludes zero. Nine of the eleven wins come at
   attempt 2.
2. **Vision on top of physics is not separated from zero** (+0.06, −0.10 to +0.23). Its gains sit on
   the capsule (+2) and the small sphere (+1); it loses on 6 scenarios that physics alone won. The
   primary comparison therefore reads: at this sample size, the camera reviewer's diagnosis
   adds little once the measured feedback already says where the fingers closed and whether the
   object moved.
3. **Where measured feedback fails: missing priors.** On the small sphere the reference lifts 8/8
   and Nemotron 1–2/8. Every failed program closes the pads at the ball's equator (the feedback
   reports "0.1 cm below the centre, both fingertips touching") and the ball squirts out during the
   lift. The reference grasps 1.5 cm below the centre. The feedback states the offset; it does not
   state the rule, and the model does not infer it in three attempts. The Allegro shows the same
   gap at a larger scale, compounded by feedback that is silent about `grasp()` closures (§2).
4. **The camera judge is categorical, not metric.** 423/437 agreement (97 %), 0 false negatives,
   14 false positives: 12 on the tall box and 2 on the thin box, all attempts where the object did
   rise, by 1–9.8 cm, under the 10 cm threshold. From a 320 × 240 frame the reviewer cannot tell
   3 cm from 10 cm and says "success" at 0.9 confidence. On every categorical outcome (missed,
   dropped, pushed off the table) it agreed.
5. **Cost.** $0.014 per successful scenario for C and D; the whole 48-scenario, 5-condition
   benchmark with 437 reviews cost $1.37. Lightning's thinking is the wall clock: 33 s per one-shot
   episode, 137–162 s per repair episode, almost all of it waiting on reasoning tokens.
6. **Sampling noise on identical prompts.** First-attempt success was 14, 12 and 8 of 48 for B, C
   and D, which receive the same first prompt. That spread at T = 0.2 is why the matched C0 control
   and paired statistics are in the design: single success rates from this stack are one draw.
7. **One infrastructure failure, fixed mid-run.** A single HTTP 529 "System is overloaded" from
   Token Factory ended the first small-sphere process because the client retried only
   429/500/502/503/504. Retries now cover every 5xx with capped backoff, the grid isolates API
   failures per episode, and the shape was rerun. Zero infrastructure errors after the fix.

## 4. Known defects left in the frozen method

- The Allegro feedback prints the hand's closure as "gripper width 1.0 m": the Franka wording
  applied to a four-finger hand. Cosmetic, but misleading for the model.
- `feedback_text` (`agent/loop.py`) has no branch for the Allegro's `grasp()` call, so a program that
  closes the hand that way gets no account of where the fingers closed (19 of 32 Allegro repair
  messages, §2).
- The API text tells the model that `move_to` and `lift` default to `timeout=4.0`; the code defaults
  are 3.0. The effect is small, because `move_to` extends any timeout to the ramp time plus 2.5 s.
- The reviewer's frames are 320 × 240 from one side camera; the threshold blindness in finding 4
  is partly a resolution choice made to keep image tokens cheap.

## 5. Reproduce

```bash
ALLEGRO_SHAPES=cube eval/run_benchmark.sh                     # ~6 h on one GPU, ~$1.4
python3 eval/stats.py _logs/bench/franka_*.json --out _logs/bench/stats
python3 eval/stats.py _logs/bench/allegro_cube.json --out _logs/bench/stats_allegro
python3 eval/report.py _logs/bench/franka_*.json _logs/bench/allegro_cube.json --out _logs/bench/report
python3 eval/publish_results.py _logs/bench --out results/bench-2026-10-27
```

## 6. Second axis: the same 48 scenarios with Lightning's thinking off (run 01:48–02:48 PT)

`REASONING=none` (`reasoning_effort: "none"`), everything else identical. Records in
`results/bench-2026-10-28-nothink/`.

| condition | thinking on | thinking off | off: 95 % CI | off: $ / success | off: wall s / episode |
|---|---|---|---|---|---|
| B one-shot | 14/48 | **6/48** | 0.06–0.25 | 0.0010 | 7 |
| C0 rerun, no repair | 14/48 | 6/48 | 0.06–0.25 | 0 | 6 |
| C physics feedback | 23/48 | **12/48** | 0.15–0.39 | 0.0018 | 16 |
| D physics + vision | 26/48 | **17/48** | 0.23–0.50 | 0.0049 | 20 |

Paired, thinking off: C − B +0.13 (−0.04, +0.29) not separated; D − B +0.23 (+0.12, +0.35)
separated; D − C +0.10 (−0.04, +0.25) not separated. Reviewer agreement 444/473 (94 %), 29 false
positives, 0 false negatives, again all on lifts under the threshold.

Whole run: **$0.54 and 0.98 h** against $1.16 and 4.88 h with thinking on (Franka shapes only).
Four fifths of the thinking-off bill is the vision reviewer, not the code model.

What it says:
- Reasoning is worth its cost here: thinking on roughly doubles success in every Nemotron
  condition (14→6, 23→12, 26→17 the other way) for 5× the wall time and 2× the bill.
- Without reasoning, the repair loop recovers less from the physics text alone (C − B no longer
  separated) and the camera reviewer's plain-language diagnosis matters more (D − B separated,
  D − C +0.10 against +0.06 with thinking). A weaker model leans on the reviewer.
- Per shape, thinking off collapses on the capsule (0–1/8 against 4–6/8) and the small sphere
  (0/8), and holds on the cube (7/8 with repair).
