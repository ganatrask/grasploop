# Benchmark statistics: 48 matched scenarios, 6 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 43/48 (90%) | 0.78–0.95 | 43/48 | 0 / 0 | 1.0 | 0.0 | 3.2 |
| B one-shot | 6/48 (12%) | 0.06–0.25 | 6/48 | 0 / 0 | 1.0 | 0.001 | 6.8 |
| C0 rerun, no repair | 6/48 (12%) | 0.06–0.25 | 6/48 | 0 / 0 | 2.75 | 0.0 | 6.1 |
| C physics feedback | 12/48 (25%) | 0.15–0.39 | 7/48 | 4 / 1 | 2.62 | 0.0018 | 15.5 |
| D physics + vision | 17/48 (35%) | 0.23–0.50 | 10/48 | 5 / 2 | 2.48 | 0.0049 | 20.3 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 48 | +0.125 | -0.04, +0.29 | 11 | 5 | 1 | 31 | no |
| D physics + vision − B one-shot | 48 | +0.229 | +0.12, +0.35 | 11 | 0 | 6 | 31 | yes |
| C physics feedback − C0 rerun, no repair | 48 | +0.125 | -0.04, +0.29 | 11 | 5 | 1 | 31 | no |
| D physics + vision − C physics feedback | 48 | +0.104 | -0.04, +0.25 | 9 | 4 | 8 | 27 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback | D physics + vision |
|---|---|---|---|---|---|
| franka/box_flat | 8/8 | 2/8 | 2/8 | 2/8 | 6/8 |
| franka/box_tall | 8/8 | 2/8 | 2/8 | 2/8 | 4/8 |
| franka/capsule_s | 8/8 | 0/8 | 0/8 | 1/8 | 0/8 |
| franka/cube | 8/8 | 2/8 | 2/8 | 7/8 | 7/8 |
| franka/sphere_m | 3/8 | 0/8 | 0/8 | 0/8 | 0/8 |
| franka/sphere_s | 8/8 | 0/8 | 0/8 | 0/8 | 0/8 |

## Last-attempt failure categories

- A scripted reference: object_off_table 5
- B one-shot: object_missed 20, slipped 6, object_off_table 5, program_error 4, insufficient_lift 3, invalid_program 2, ik_not_reached 1, dropped_in_hold 1
- C0 rerun, no repair: object_missed 20, slipped 6, object_off_table 5, program_error 4, insufficient_lift 3, invalid_program 2, ik_not_reached 1, dropped_in_hold 1
- C physics feedback: slipped 16, program_error 5, insufficient_lift 4, object_missed 4, ik_not_reached 3, no_contact 2, object_off_table 2
- D physics + vision: slipped 14, object_off_table 7, ik_not_reached 4, program_error 2, object_missed 2, gripper_open 1, insufficient_lift 1

## Vision reviewer vs physics judge, 473 filmed attempts

agreement 444/473 (94%), false positives 29, false negatives 0, abstained 0, invalid JSON 0, $0.4256

physics failure / reviewer failure type: object_missed / no_lift_attempted ×78; slipped / object_dropped ×48; object_off_table / object_pushed_away ×37; object_missed / closed_on_nothing ×26; program_error / no_lift_attempted ×20; object_missed / object_dropped ×19; object_missed / object_pushed_away ×16; slipped / closed_on_nothing ×13; slipped / object_pushed_away ×13; invalid_program / no_lift_attempted ×12; slipped / no_lift_attempted ×9; ik_not_reached / object_pushed_away ×8
