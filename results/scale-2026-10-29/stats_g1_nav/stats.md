# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 8/8 (100%) | 0.68–1.00 | 8/8 | 0 / 0 | 1.0 | 0.0 | 10.9 |
| B one-shot | 2/8 (25%) | 0.07–0.59 | 2/8 | 0 / 0 | 1.0 | 0.0061 | 54.4 |
| C0 rerun, no repair | 2/8 (25%) | 0.07–0.59 | 2/8 | 0 / 0 | 2.5 | 0.0 | 40.8 |
| C physics feedback | 6/8 (75%) | 0.41–0.93 | 4/8 | 2 / 0 | 1.75 | 0.0059 | 117.7 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 8 | +0.500 | +0.00, +0.88 | 5 | 1 | 1 | 1 | no |
| C physics feedback − C0 rerun, no repair | 8 | +0.500 | +0.00, +0.88 | 5 | 1 | 1 | 1 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback |
|---|---|---|---|---|
| g1/nav | 8/8 | 2/8 | 2/8 | 6/8 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: not_at_goal 2, program_error 2, invalid_program 1, missed_waypoint 1
- C0 rerun, no repair: not_at_goal 2, program_error 2, invalid_program 1, missed_waypoint 1
- C physics feedback: missed_waypoint 1, not_at_goal 1
