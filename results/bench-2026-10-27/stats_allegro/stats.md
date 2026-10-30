# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 7/8 (88%) | 0.53–0.98 | 7/8 | 0 / 0 | 1.0 | 0.0 | 4.5 |
| B one-shot | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 1.0 | — | 56.9 |
| C0 rerun, no repair | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 3.0 | — | 8.5 |
| C physics feedback | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 3.0 | — | 146.0 |
| D physics + vision | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 3.0 | — | 136.2 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 8 | +0.000 | +0.00, +0.00 | 0 | 0 | 0 | 8 | no |
| D physics + vision − B one-shot | 8 | +0.000 | +0.00, +0.00 | 0 | 0 | 0 | 8 | no |
| C physics feedback − C0 rerun, no repair | 8 | +0.000 | +0.00, +0.00 | 0 | 0 | 0 | 8 | no |
| D physics + vision − C physics feedback | 8 | +0.000 | +0.00, +0.00 | 0 | 0 | 0 | 8 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback | D physics + vision |
|---|---|---|---|---|---|
| allegro/cube | 7/8 | 0/8 | 0/8 | 0/8 | 0/8 |

## Last-attempt failure categories

- A scripted reference: ik_not_reached 1
- B one-shot: object_missed 7, ik_not_reached 1
- C0 rerun, no repair: object_missed 7, ik_not_reached 1
- C physics feedback: object_missed 8
- D physics + vision: object_missed 7, ik_not_reached 1

## Vision reviewer vs physics judge, 88 filmed attempts

agreement 88/88 (100%), false positives 0, false negatives 0, abstained 0, invalid JSON 0, $0.082

physics failure / reviewer failure type: object_missed / closed_on_nothing ×46; object_missed / no_lift_attempted ×15; object_missed / object_pushed_away ×7; ik_not_reached / closed_on_nothing ×5; ik_not_reached / no_lift_attempted ×4; object_missed / object_dropped ×3; insufficient_lift / object_pushed_away ×1
