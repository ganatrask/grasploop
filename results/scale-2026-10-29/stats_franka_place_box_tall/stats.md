# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 8/8 (100%) | 0.68–1.00 | 8/8 | 0 / 0 | 1.0 | 0.0 | 7.0 |
| B one-shot | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 1.0 | — | 55.6 |
| C0 rerun, no repair | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 3.0 | — | 13.6 |
| C physics feedback | 1/8 (12%) | 0.02–0.47 | 0/8 | 1 / 0 | 2.88 | 0.0944 | 266.2 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 8 | +0.125 | +0.00, +0.38 | 1 | 0 | 0 | 7 | no |
| C physics feedback − C0 rerun, no repair | 8 | +0.125 | +0.00, +0.38 | 1 | 0 | 0 | 7 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback |
|---|---|---|---|---|
| franka/place_box_tall | 8/8 | 0/8 | 0/8 | 1/8 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: never_lifted 7, placed_off_target 1
- C0 rerun, no repair: never_lifted 7, placed_off_target 1
- C physics feedback: invalid_program 3, placed_off_target 2, never_lifted 2
