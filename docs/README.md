# GraspLoop docs

Numbered in reading order. The results in 02–04 are computed from the records in `../results/`; the
build log (05) also cites local runs under `_logs/` that were not published.

| Doc | What it covers |
|---|---|
| [01 — Benchmark protocol](01-benchmark-protocol.md) | What the Franka benchmark measures, with which frozen code, model settings, seeds and conditions |
| [02 — Benchmark results](02-benchmark-results.md) | 48 matched Franka scenarios plus the Allegro cell: success rates, paired differences, reviewer agreement, known defects; the thinking-off axis in §6 |
| [03 — Robots × tasks](03-robots-x-tasks.md) | The same loop on the Go2 and G1 walkers and on Franka pick-and-place (drawer built, not benchmarked); the camera reviewer on every filmed attempt |
| [04 — Nebius cloud and web hints](04-nebius-cloud-and-web-hints.md) | The cube cell replicated and extended to 16 seeds on a Nebius H100; condition E, Tavily web hints |
| [05 — Build log](05-build-log.md) | Every trap and fix from 2026-10-27 to 2026-10-29, the pilot grid, the filmed showcase and the demo footage |

Conditions, as used throughout: A scripted reference, B one-shot, C0 rerun of B's program without
repair, C physics feedback, D physics + vision reviewer, E physics + Tavily web hints.
