"""Run the vision reviewer over every filmed attempt of a grid record and compare it with the physics judge.

    $PY eval/review_record.py _logs/scale/go2_nav.json --out _logs/scale/review_go2_nav.json [--limit 3]

The grid's --review-all does this for grasp records from the review frames it saved; the walker grids saved
films only, so this reads up to 8 evenly spaced frames per attempt from the film folder (the top-down
camera for walkers, the side camera otherwise) and uses the task's own reviewer prompt (judges/vision.py).
Writes per-attempt rows and the agreement summary: agree, false positives, false negatives, abstentions.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="review only the first N attempts (smoke test)")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--exclude-before", default="", help="skip attempts whose film predates this time (YYYY-MM-DD HH:MM) and has no replay: "
                                                       "films from before the per-process staging fix can hold another robot's frames")
    ap.add_argument("--no-end-frame", action="store_true", help="walkers: do not append the chase camera's last frame")
    args = ap.parse_args()
    import time as _time
    cutoff = _time.mktime(_time.strptime(args.exclude_before, "%Y-%m-%d %H:%M")) if args.exclude_before else None

    import numpy as np
    from PIL import Image

    from judges.vision import make_reviewer, review

    rec = json.load(open(args.record))
    shape0 = rec.get("shape", "")
    mode = "nav" if shape0 == "nav" else ("place" if shape0.startswith("place_") else "grasp")
    cam = "front_cam" if mode == "nav" else "side_cam"  # the walkers' front_cam is the top-down view
    usage = os.path.splitext(args.out)[0] + ".usage.jsonl"
    rv = make_reviewer(usage_log=usage)
    shape = shape0.replace("place_", "").replace("_", " ") or "object"
    sizes = {"cube": "5 cm cube", "box flat": "thin box, 2.5 x 5 x 5 cm", "box tall": "tall box, 5 x 5 x 10 cm"}
    rows, n_done = [], 0
    for cond, eps in rec["episodes"].items():
        for e in eps:
            for a in (e.get("attempts") or [e]):
                vdir = a.get("video")
                if not vdir or not a.get("verdict"):
                    continue
                # a replay film of the same attempt (eval/refilm.py) is preferred: it was filmed after the staging fix
                root, tag = os.path.split(vdir.rstrip("/"))
                robot_scen = f"{rec.get('robot', 'franka')}_{shape0}"
                replay = os.path.join(root, f"{robot_scen}_s{e['seed']}_refilm{cond}_a{a.get('n', 1)}")
                footage = "replay" if os.path.isdir(os.path.join(replay, cam)) else "original"
                if footage == "replay":
                    vdir = replay
                if not os.path.isdir(os.path.join(vdir, cam)):
                    continue
                if footage == "original" and cutoff and os.path.getmtime(os.path.join(vdir, "meta.json")) < cutoff:
                    print(f"[review] {cond:8s} s{e['seed']} a{a.get('n', 1)}: film predates the staging fix, no replay: excluded", flush=True)
                    continue
                files = sorted(glob.glob(os.path.join(vdir, cam, "frame_*.png")))
                if len(files) < 2:
                    continue
                meta = json.load(open(os.path.join(vdir, "meta.json")))
                dt = meta.get("frame_dt_s", 0.04)
                frames = [np.asarray(Image.open(f).convert("RGB")) for f in files]
                note = ""
                if mode == "nav" and not args.no_end_frame:  # the body hides the disc from above: add the chase camera's end state
                    side = sorted(glob.glob(os.path.join(vdir, "side_cam", "frame_*.png")))
                    if side:
                        frames = frames + [np.asarray(Image.open(side[-1]).convert("RGB"))]
                        note = ("Camera note. The first frames are a top-down camera that FOLLOWS the robot: the robot is always near the "
                                "centre of the frame and the discs move relative to it; a disc that slides under the robot and disappears "
                                "beneath its body means the robot is standing over it. The LAST frame is a chase camera behind the robot "
                                "at the end of the attempt: the robot is at the lower middle of that frame; a disc it stands on surrounds "
                                "its feet, while a disc higher up in that frame is still ahead of it.")
                r = review(rv.tf, frames, shape, sizes.get(shape, ""), frame_dt_s=dt, max_frames=args.frames, mode=mode, extra_note=note,
                           tag=f"review_record:{cond}:s{e['seed']}:a{a.get('n', 1)}")
                phys = bool(a["verdict"].get("success"))
                vis = r["structured"].get("visual_success")
                rows.append(dict(condition=cond, seed=e["seed"], attempt=a.get("n", 1), physics_success=phys,
                                 physics_failure=a["verdict"].get("failure"), visual_success=vis,
                                 visual_failure=r["structured"].get("failure_type"), confidence=r["structured"].get("confidence"),
                                 evidence=r["structured"].get("evidence", ""), valid_json=r["valid_json"], cost_usd=r["cost_usd"],
                                 n_frames=r["n_frames"], video=vdir, footage=footage))
                n_done += 1
                print(f"[review] {cond:8s} s{e['seed']} a{a.get('n', 1)}: physics {'PASS' if phys else 'fail'}, "
                      f"camera {vis} ({r['structured'].get('failure_type')}) ${r['cost_usd']:.4f}", flush=True)
                if args.limit and n_done >= args.limit:
                    break
            if args.limit and n_done >= args.limit:
                break
        if args.limit and n_done >= args.limit:
            break
    n = len(rows)
    summary = dict(n=n, agree=sum(r["visual_success"] == r["physics_success"] for r in rows),
                   false_positive=sum(r["visual_success"] is True and not r["physics_success"] for r in rows),
                   false_negative=sum(r["visual_success"] is False and r["physics_success"] for r in rows),
                   abstain=sum(r["visual_success"] is None for r in rows), invalid_json=sum(not r["valid_json"] for r in rows),
                   cost_usd=round(sum(r["cost_usd"] for r in rows), 4), camera=cam, frames_per_attempt=args.frames,
                   end_frame=(mode == "nav" and not args.no_end_frame), replays=sum(r["footage"] == "replay" for r in rows),
                   excluded_before=args.exclude_before or None)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(dict(script="eval/review_record.py", record=args.record, robot=rec.get("robot"), shape=shape,
                   model=rv.tf.model, mode=mode, summary=summary, reviews=rows), open(args.out, "w"), indent=1)
    print(f"[review] {n} attempts: agree {summary['agree']}, false positives {summary['false_positive']}, "
          f"false negatives {summary['false_negative']}, abstain {summary['abstain']}, ${summary['cost_usd']:.3f} -> {args.out}")


if __name__ == "__main__":
    main()
