# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| A scripted reference | 8/8 (100%) | 0.68–1.00 | 8/8 | 0 / 0 | 1.0 | 0.0 | 10.9 |
| B one-shot | 4/8 (50%) | 0.21–0.79 | 4/8 | 0 / 0 | 1.0 | 0.0037 | 70.1 |
| C0 rerun, no repair | 4/8 (50%) | 0.21–0.79 | 3/8 | 1 / 0 | 2.12 | 0.0 | 78.8 |
| C physics feedback | 6/8 (75%) | 0.41–0.93 | 1/8 | 4 / 1 | 2.25 | 0.0097 | 176.6 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| C physics feedback − B one-shot | 8 | +0.250 | -0.25, +0.75 | 3 | 1 | 3 | 1 | no |
| C physics feedback − C0 rerun, no repair | 8 | +0.250 | -0.25, +0.75 | 3 | 1 | 3 | 1 | no |

## Per shape (successes / scenarios)

| robot/shape | A scripted reference | B one-shot | C0 rerun, no repair | C physics feedback |
|---|---|---|---|---|
| go2/nav | 8/8 | 4/8 | 4/8 | 6/8 |

## Last-attempt failure categories

- A scripted reference: none
- B one-shot: not_at_goal 3, missed_waypoint 1
- C0 rerun, no repair: not_at_goal 3, missed_waypoint 1
- C physics feedback: not_at_goal 1, missed_waypoint 1
