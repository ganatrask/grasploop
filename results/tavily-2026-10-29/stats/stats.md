# Benchmark statistics: 8 matched scenarios, 1 grid file(s)

| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |
|---|---|---|---|---|---|---|---|
| C physics feedback | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 3.0 | — | 143.9 |
| E physics + web hints (Tavily) | 0/8 (0%) | 0.00–0.32 | 0/8 | 0 / 0 | 3.0 | — | 172.3 |

## Paired differences (same scenarios), percentile bootstrap over scenarios

| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |
|---|---|---|---|---|---|---|---|---|
| E physics + web hints (Tavily) − C physics feedback | 8 | +0.000 | +0.00, +0.00 | 0 | 0 | 0 | 8 | no |

## Per shape (successes / scenarios)

| robot/shape | C physics feedback | E physics + web hints (Tavily) |
|---|---|---|
| franka/sphere_s | 0/8 | 0/8 |

## Last-attempt failure categories

- C physics feedback: slipped 8
- E physics + web hints (Tavily): slipped 4, invalid_program 2, ik_not_reached 1, object_missed 1
