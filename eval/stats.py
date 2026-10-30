"""Benchmark statistics from run_grid.py records (the tables of docs/02): success by attempt 3 per
condition with Wilson intervals, paired differences between conditions with a bootstrap interval over
matched scenarios, first-attempt success and attempt-2/3 recovery, cost per success, reviewer agreement
and the failure-category distribution. Pure stdlib; writes markdown and JSON.

    python3 eval/stats.py _logs/bench/franka_*.json --out _logs/bench/stats
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from collections import Counter, defaultdict

COND_LABEL = {"scripted": "A scripted reference", "oneshot": "B one-shot", "rerun": "C0 rerun, no repair",
              "physics": "C physics feedback", "vision": "D physics + vision",
              "hints": "E physics + web hints (Tavily)"}
PAIRS = [("physics", "oneshot"), ("vision", "oneshot"), ("physics", "rerun"), ("vision", "physics"), ("hints", "physics"), ("hints", "oneshot")]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def load(paths):
    """scenario key (robot, shape, seed) -> condition -> episode record; plus reviewer rows."""
    scen, reviews, meta = defaultdict(dict), [], []
    for p in paths:
        with open(p) as f:
            d = json.load(f)
        if "episodes" not in d or not str(d.get("script", "")).endswith("run_grid.py"):
            # a results folder also holds review_*.json and refilm_*.json; a replay record carries episodes too and
            # would overwrite the grid's attempts for its seeds
            print(f"[stats] {os.path.basename(p)}: not a grid record, skipped")
            continue
        meta.append(dict(file=os.path.basename(p), robot=d.get("robot", "franka"), shape=d["shape"], model=d.get("model"),
                         reasoning=d.get("reasoning"), seeds=d.get("seeds"), wall_s=d.get("wall_s"), cost_usd=d.get("total_cost_usd")))
        for cond, eps in d["episodes"].items():
            for e in eps:
                if e.get("infra_error"):
                    meta[-1]["infra_errors"] = meta[-1].get("infra_errors", 0) + 1
                    continue
                scen[(d.get("robot", "franka"), d["shape"], e["seed"])][cond] = e
        for r in d.get("reviews", []):
            reviews.append(dict(robot=d.get("robot", "franka"), shape=d["shape"], **r))
    return scen, reviews, meta


def attempts_of(e):
    return e.get("attempts") or [e]


def per_condition(scen, conds):
    out = {}
    for c in conds:
        eps = [s[c] for s in scen.values() if c in s]
        n = len(eps)
        if not n:
            continue
        k = sum(bool(e["success"]) for e in eps)
        first = sum(bool(attempts_of(e)[0]["verdict"]["success"]) for e in eps)
        rec2 = sum(1 for e in eps if len(attempts_of(e)) >= 2 and attempts_of(e)[1]["verdict"]["success"])
        rec3 = sum(1 for e in eps if len(attempts_of(e)) >= 3 and attempts_of(e)[2]["verdict"]["success"])
        failed_first = n - first
        cost = sum(e.get("cost_usd", 0.0) for e in eps)
        fails = Counter(attempts_of(e)[-1]["verdict"]["failure"] for e in eps if not e["success"])
        p, lo, hi = wilson(k, n)
        out[c] = dict(label=COND_LABEL.get(c, c), n=n, successes=k, rate=round(p, 3), ci95=[round(lo, 3), round(hi, 3)],
                      first_attempt=first, first_rate=round(first / n, 3),
                      recovered_attempt2=rec2, recovered_attempt3=rec3,
                      recovery_rate=round((rec2 + rec3) / failed_first, 3) if failed_first else None,
                      mean_attempts=round(sum(e.get("attempts_used", len(attempts_of(e))) for e in eps) / n, 2),
                      cost_usd=round(cost, 4), cost_per_success_usd=round(cost / k, 4) if k else None,
                      mean_wall_s=round(sum(e.get("wall_s", 0.0) for e in eps) / n, 1),
                      failures=dict(fails.most_common()))
    return out


def paired(scen, a, b, n_boot=10000, seed=0):
    """Success(a) - success(b) on the same scenarios, with a percentile bootstrap CI over scenarios."""
    keys = [k for k, s in scen.items() if a in s and b in s]
    if not keys:
        return None
    diffs = [int(bool(scen[k][a]["success"])) - int(bool(scen[k][b]["success"])) for k in keys]
    n = len(diffs)
    mean = sum(diffs) / n
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        s = sum(diffs[rng.randrange(n)] for _ in range(n))
        boots.append(s / n)
    boots.sort()
    lo, hi = boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]
    return dict(a=a, b=b, n=n, diff=round(mean, 3), ci95=[round(lo, 3), round(hi, 3)],
                a_only=sum(1 for d in diffs if d > 0), b_only=sum(1 for d in diffs if d < 0),
                both=sum(1 for k in keys if scen[k][a]["success"] and scen[k][b]["success"]),
                neither=sum(1 for k in keys if not scen[k][a]["success"] and not scen[k][b]["success"]),
                separated=lo > 0 or hi < 0)


def reviewer_stats(reviews):
    if not reviews:
        return None
    n = len(reviews)
    tp = sum(1 for r in reviews if r["visual_success"] is True and r["physics_success"])
    tn = sum(1 for r in reviews if r["visual_success"] is False and not r["physics_success"])
    fp = sum(1 for r in reviews if r["visual_success"] is True and not r["physics_success"])
    fn = sum(1 for r in reviews if r["visual_success"] is False and r["physics_success"])
    ab = sum(1 for r in reviews if r["visual_success"] is None)
    fail_match = Counter()
    for r in reviews:
        if not r["physics_success"] and r["visual_success"] is False:
            fail_match[(r["physics_failure"], r["visual_failure"])] += 1
    return dict(n=n, agree=tp + tn, agreement=round((tp + tn) / n, 3), false_positive=fp, false_negative=fn, abstain=ab,
                invalid_json=sum(1 for r in reviews if not r.get("valid_json", True)),
                cost_usd=round(sum(r.get("cost_usd", 0.0) for r in reviews), 4),
                failure_pairs={f"{a} / {b}": c for (a, b), c in fail_match.most_common(12)})


def per_shape(scen, conds):
    rows = defaultdict(dict)
    for (robot, shape, seed), s in scen.items():
        for c in conds:
            if c in s:
                rows[(robot, shape)].setdefault(c, [0, 0])
                rows[(robot, shape)][c][0] += bool(s[c]["success"])
                rows[(robot, shape)][c][1] += 1
    return {f"{r}/{sh}": {c: f"{k}/{n}" for c, (k, n) in v.items()} for (r, sh), v in sorted(rows.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grids", nargs="+")
    ap.add_argument("--out", default="_logs/stats")
    ap.add_argument("--boot", type=int, default=10000)
    args = ap.parse_args()
    scen, reviews, meta = load(args.grids)
    conds = [c for c in COND_LABEL if any(c in s for s in scen.values())]
    pc = per_condition(scen, conds)
    pairs = [p for p in (paired(scen, a, b, args.boot) for a, b in PAIRS) if p]
    rv = reviewer_stats(reviews)
    shapes = per_shape(scen, conds)
    os.makedirs(args.out, exist_ok=True)
    out = dict(script="eval/stats.py", inputs=meta, scenarios=len(scen), conditions=pc, paired=pairs, reviewer=rv, per_shape=shapes)
    with open(os.path.join(args.out, "stats.json"), "w") as f:
        json.dump(out, f, indent=1)
    L = [f"# Benchmark statistics: {len(scen)} matched scenarios, {len(meta)} grid file(s)\n"]
    L.append("| condition | success by attempt 3 | 95% CI | first attempt | recovered at 2 / 3 | mean attempts | $ / success | wall s |")
    L.append("|---|---|---|---|---|---|---|---|")
    for c in conds:
        r = pc[c]
        L.append(f"| {r['label']} | {r['successes']}/{r['n']} ({r['rate']:.0%}) | {r['ci95'][0]:.2f}–{r['ci95'][1]:.2f} | "
                 f"{r['first_attempt']}/{r['n']} | {r['recovered_attempt2']} / {r['recovered_attempt3']} | {r['mean_attempts']} | "
                 f"{r['cost_per_success_usd'] if r['cost_per_success_usd'] is not None else '—'} | {r['mean_wall_s']} |")
    L.append("\n## Paired differences (same scenarios), percentile bootstrap over scenarios\n")
    L.append("| a − b | n | diff | 95% CI | a only | b only | both | neither | separated from 0 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for p in pairs:
        L.append(f"| {COND_LABEL[p['a']]} − {COND_LABEL[p['b']]} | {p['n']} | {p['diff']:+.3f} | {p['ci95'][0]:+.2f}, {p['ci95'][1]:+.2f} | "
                 f"{p['a_only']} | {p['b_only']} | {p['both']} | {p['neither']} | {'yes' if p['separated'] else 'no'} |")
    L.append("\n## Per shape (successes / scenarios)\n")
    L.append("| robot/shape | " + " | ".join(COND_LABEL[c] for c in conds) + " |")
    L.append("|---|" + "---|" * len(conds))
    for k, v in shapes.items():
        L.append(f"| {k} | " + " | ".join(v.get(c, "—") for c in conds) + " |")
    L.append("\n## Last-attempt failure categories\n")
    for c in conds:
        L.append(f"- {COND_LABEL[c]}: " + (", ".join(f"{k} {v}" for k, v in pc[c]["failures"].items()) or "none"))
    if rv:
        L.append(f"\n## Vision reviewer vs physics judge, {rv['n']} filmed attempts\n")
        L.append(f"agreement {rv['agree']}/{rv['n']} ({rv['agreement']:.0%}), false positives {rv['false_positive']}, "
                 f"false negatives {rv['false_negative']}, abstained {rv['abstain']}, invalid JSON {rv['invalid_json']}, ${rv['cost_usd']}")
        if rv["failure_pairs"]:
            L.append("\nphysics failure / reviewer failure type: " + "; ".join(f"{k} ×{v}" for k, v in rv["failure_pairs"].items()))
    with open(os.path.join(args.out, "stats.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n-> {args.out}/stats.md, stats.json")


if __name__ == "__main__":
    main()
