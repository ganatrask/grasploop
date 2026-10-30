# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 8/8 (100%) | 0.68–1.00 | 8/8 | 0 / 0 | 1.0 | 0.0 | 15.4 |
| B one-shot | 4/8 (50%) | 0.21–0.79 | 4/8 | 0 / 0 | 1.0 | 0.0056 | 55.2 |
| C0 rerun, no repair | 4/8 (50%) | 0.21–0.79 | 4/8 | 0 / 0 | 2.0 | 0.0 | 23.3 |
| C physics feedback | 7/8 (88%) | 0.53–0.98 | 2/8 | 2 / 3 | 2.25 | 0.0059 | 111.4 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 8 | +0.375 | +0.12, +0.75 | 3 | 0 | 4 | 1 | yes |
| C physics feedback − C0 rerun, no repair | 8 | +0.375 | +0.12, +0.75 | 3 | 0 | 4 | 1 | yes |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback |
|---|---|---|---|---|
| franka/place_cube | 8/8 | 4/8 | 4/8 | 7/8 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: never_lifted 3, placed_off_target 1
- C0 rerun, no repair: never_lifted 3, placed_off_target 1
- C physics feedback: placed_off_target 1
