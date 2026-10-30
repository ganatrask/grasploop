# Benchmark statistics: 40 matched scenarios, 5 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 40/40 (100%) | 0.91–1.00 | 40/40 | 0 / 0 | 1.0 | 0.0 | 10.3 |
| B one-shot | 13/40 (32%) | 0.20–0.48 | 13/40 | 0 / 0 | 1.0 | 0.0078 | 65.3 |
| C0 rerun, no repair | 13/40 (32%) | 0.20–0.48 | 12/40 | 1 / 0 | 2.38 | 0.0 | 33.3 |
| C physics feedback | 25/40 (62%) | 0.47–0.76 | 10/40 | 11 / 4 | 2.23 | 0.0109 | 166.2 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 40 | +0.300 | +0.12, +0.47 | 14 | 2 | 11 | 13 | yes |
| C physics feedback − C0 rerun, no repair | 40 | +0.300 | +0.12, +0.47 | 14 | 2 | 11 | 13 | yes |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback |
|---|---|---|---|---|
| franka/place_box_flat | 8/8 | 3/8 | 3/8 | 5/8 |
| franka/place_box_tall | 8/8 | 0/8 | 0/8 | 1/8 |
| franka/place_cube | 8/8 | 4/8 | 4/8 | 7/8 |
| g1/nav | 8/8 | 2/8 | 2/8 | 6/8 |
| go2/nav | 8/8 | 4/8 | 4/8 | 6/8 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: never_lifted 15, not_at_goal 5, missed_waypoint 2, program_error 2, placed_off_target 2, invalid_program 1
- C0 rerun, no repair: never_lifted 15, not_at_goal 5, missed_waypoint 2, program_error 2, placed_off_target 2, invalid_program 1
- C physics feedback: placed_off_target 5, never_lifted 3, invalid_program 3, not_at_goal 2, missed_waypoint 2
