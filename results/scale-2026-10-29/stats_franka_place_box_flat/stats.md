# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 8/8 (100%) | 0.68–1.00 | 8/8 | 0 / 0 | 1.0 | 0.0 | 7.4 |
| B one-shot | 3/8 (38%) | 0.14–0.69 | 3/8 | 0 / 0 | 1.0 | 0.0105 | 91.1 |
| C0 rerun, no repair | 3/8 (38%) | 0.14–0.69 | 3/8 | 0 / 0 | 2.25 | 0.0 | 10.0 |
| C physics feedback | 5/8 (62%) | 0.31–0.86 | 3/8 | 2 / 0 | 2.0 | 0.0086 | 159.1 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 8 | +0.250 | +0.00, +0.50 | 2 | 0 | 3 | 3 | no |
| C physics feedback − C0 rerun, no repair | 8 | +0.250 | +0.00, +0.50 | 2 | 0 | 3 | 3 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback |
|---|---|---|---|---|
| franka/place_box_flat | 8/8 | 3/8 | 3/8 | 5/8 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: never_lifted 5
- C0 rerun, no repair: never_lifted 5
- C physics feedback: placed_off_target 2, never_lifted 1
