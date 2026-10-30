# Benchmark statistics: 16 matched scenarios, 2 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 16/16 (100%) | 0.81–1.00 | 16/16 | 0 / 0 | 1.0 | 0.0 | 7.9 |
| B one-shot | 8/16 (50%) | 0.28–0.72 | 8/16 | 0 / 0 | 1.0 | 0.0032 | 30.3 |
| C0 rerun, no repair | 8/16 (50%) | 0.28–0.72 | 8/16 | 0 / 0 | 2.0 | 0.0 | 6.5 |
| C physics feedback | 14/16 (88%) | 0.64–0.96 | 7/16 | 6 / 1 | 1.75 | 0.0043 | 65.2 |
| D physics + vision | 12/16 (75%) | 0.51–0.90 | 4/16 | 7 / 1 | 2.06 | 0.0068 | 70.8 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 16 | +0.375 | +0.06, +0.69 | 7 | 1 | 7 | 1 | yes |
| D physics + vision − B one-shot | 16 | +0.250 | +0.00, +0.50 | 5 | 1 | 7 | 3 | no |
| C physics feedback − C0 rerun, no repair | 16 | +0.375 | +0.06, +0.69 | 7 | 1 | 7 | 1 | yes |
| D physics + vision − C physics feedback | 16 | -0.125 | -0.44, +0.19 | 2 | 4 | 10 | 0 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback | D physics + vision |
|---|---|---|---|---|---|
| franka/cube | 16/16 | 8/16 | 8/16 | 14/16 | 12/16 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: slipped 4, object_missed 3, invalid_program 1
- C0 rerun, no repair: object_missed 4, slipped 3, invalid_program 1
- C physics feedback: invalid_program 1, object_missed 1
- D physics + vision: slipped 2, invalid_program 1, ik_not_reached 1

## Vision reviewer vs physics judge, 125 filmed attempts

agreement 125/125 (100%), false positives 0, false negatives 0, abstained 0, invalid JSON 0, $0.1098

physics failure / reviewer failure type: slipped / object_dropped ×17; object_missed / no_lift_attempted ×12; object_missed / object_dropped ×11; invalid_program / no_lift_attempted ×10; slipped / closed_on_nothing ×6; object_missed / closed_on_nothing ×5; slipped / object_pushed_away ×2; object_missed / object_pushed_away ×1; dropped_in_hold / object_dropped ×1; ik_not_reached / no_lift_attempted ×1; slipped / no_lift_attempted ×1
