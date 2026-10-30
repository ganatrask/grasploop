# Benchmark statistics: 48 matched scenarios, 6 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 43/48 (90%) | 0.78–0.95 | 43/48 | 0 / 0 | 1.0 | 0.0 | 3.1 |
| B one-shot | 14/48 (29%) | 0.18–0.43 | 14/48 | 0 / 0 | 1.0 | 0.0054 | 33.2 |
| C0 rerun, no repair | 14/48 (29%) | 0.18–0.43 | 14/48 | 0 / 0 | 2.42 | 0.0 | 5.3 |
| C physics feedback | 23/48 (48%) | 0.34–0.62 | 12/48 | 9 / 2 | 2.31 | 0.0143 | 162.1 |
| D physics + vision | 26/48 (54%) | 0.40–0.67 | 8/48 | 14 / 4 | 2.38 | 0.014 | 136.6 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 48 | +0.188 | +0.04, +0.33 | 11 | 2 | 12 | 23 | yes |
| D physics + vision − B one-shot | 48 | +0.250 | +0.10, +0.42 | 15 | 3 | 11 | 19 | yes |
| C physics feedback − C0 rerun, no repair | 48 | +0.188 | +0.04, +0.33 | 11 | 2 | 12 | 23 | yes |
| D physics + vision − C physics feedback | 48 | +0.062 | -0.10, +0.23 | 9 | 6 | 17 | 16 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback | D physics + vision |
|---|---|---|---|---|---|
| franka/box_flat | 8/8 | 5/8 | 5/8 | 7/8 | 7/8 |
| franka/box_tall | 8/8 | 1/8 | 1/8 | 3/8 | 3/8 |
| franka/capsule_s | 8/8 | 4/8 | 4/8 | 4/8 | 6/8 |
| franka/cube | 8/8 | 4/8 | 4/8 | 8/8 | 8/8 |
| franka/sphere_m | 3/8 | 0/8 | 0/8 | 0/8 | 0/8 |
| franka/sphere_s | 8/8 | 0/8 | 0/8 | 1/8 | 2/8 |

## Last-attempt failure categories

- A scripted reference: object_off_table 5
- B one-shot: object_missed 21, slipped 8, insufficient_lift 2, object_off_table 2, invalid_program 1
- C0 rerun, no repair: object_missed 21, slipped 8, insufficient_lift 2, object_off_table 2, invalid_program 1
- C physics feedback: slipped 11, invalid_program 6, object_missed 5, insufficient_lift 1, no_contact 1, object_off_table 1
- D physics + vision: slipped 12, invalid_program 5, insufficient_lift 2, dropped_in_hold 1, object_missed 1, no_contact 1

## Vision reviewer vs physics judge, 437 filmed attempts

agreement 423/437 (97%), false positives 14, false negatives 0, abstained 0, invalid JSON 0, $0.3944

physics failure / reviewer failure type: object_missed / no_lift_attempted ×64; slipped / object_dropped ×48; object_missed / object_pushed_away ×29; object_missed / closed_on_nothing ×29; object_missed / object_dropped ×21; object_off_table / object_pushed_away ×18; invalid_program / no_lift_attempted ×17; slipped / object_pushed_away ×13; slipped / object_slipped_during_lift ×12; slipped / no_lift_attempted ×11; object_missed / object_slipped_during_lift ×11; slipped / closed_on_nothing ×9
