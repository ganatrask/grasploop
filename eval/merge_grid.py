"""Replace one condition of a grid record with the same condition from another record.

Used when a condition had to be rerun on its own, e.g. the scripted reference after the
walking reference program was fixed (docs/03 §3). The target keeps every other condition
untouched and records where the replacement came from under "merged".

    $PY eval/merge_grid.py --into _logs/scale/go2_nav.json --from _logs/scale/go2_nav_scripted2.json --condition scripted
"""
import argparse
import json
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--into", required=True, help="grid record to update in place")
    ap.add_argument("--from", dest="src", required=True, help="grid record holding the rerun condition")
    ap.add_argument("--condition", required=True)
    args = ap.parse_args()

    into, src = json.load(open(args.into)), json.load(open(args.src))
    c = args.condition
    if c not in src["episodes"] or c not in src["summary"]:
        raise SystemExit(f"{args.src} has no condition {c!r}")
    for key in ("robot", "shape", "seeds"):
        if into.get(key) != src.get(key):
            raise SystemExit(f"{key} differs: {into.get(key)!r} vs {src.get(key)!r}")
    old = into["summary"].get(c, {})
    into["episodes"][c] = src["episodes"][c]
    into["summary"][c] = src["summary"][c]
    into["total_cost_usd"] = round(sum(s.get("cost_usd", 0.0) for s in into["summary"].values()), 4)
    into.setdefault("merged", []).append(dict(
        condition=c, source=args.src, source_script=src.get("script"), when=time.strftime("%Y-%m-%d %H:%M"),
        replaced=dict(successes=old.get("successes"), n=old.get("n"))))
    Path(args.into).write_text(json.dumps(into, indent=1))
    print(f"[merge] {args.into}: {c} {old.get('successes')}/{old.get('n')} -> "
          f"{src['summary'][c]['successes']}/{src['summary'][c]['n']} from {args.src}")


if __name__ == "__main__":
    main()
