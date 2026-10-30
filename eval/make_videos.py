"""Review videos from --video recordings: one mp4 per filmed attempt (both cameras side by side under a
banner with the trial, the clock, the object's rise, the gripper state and the physics verdict) and
one reel of all of them with a title card each, in the order the result files are given. Title cards of
Nemotron attempts show the program that ran.

    $PY eval/make_videos.py --video-dir _logs/showcase/video --results _logs/showcase/*.json --out _logs/showcase/review

Needs PIL + numpy (any interpreter that has them, the GA venv does) and the ffmpeg binary at
~/.local/bin/ffmpeg (the pinned static build) or on PATH. No sim, no GPU.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

FFMPEG = os.path.expanduser("~/.local/bin/ffmpeg")
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BANNER = 56
TAG_RE = re.compile(r"^(?:franka_|allegro_|go2_|g1_)?(?P<shape>.+)_s(?P<seed>\d+)_(?P<cond>[a-z]+)(?:_a(?P<n>\d+))?$")
COND_NAMES = {"scripted": "scripted reference", "none": "Nemotron one-shot", "rerun": "rerun, no repair",
              "physics": "Nemotron + physics feedback", "vision": "Nemotron + physics + vision feedback",
              "refilm": "replay of the recorded program"}
ROBOT_NAMES = {"franka": "Franka Panda", "allegro": "Kuka iiwa + Allegro", "go2": "Unitree Go2", "g1": "Unitree G1"}
BG, FG, DIM, OK, BAD = (18, 18, 22), (235, 235, 235), (190, 190, 190), (90, 220, 110), (240, 90, 80)


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def walk(obj, ctx: dict, out: list) -> None:
    """Every dict with a `video` directory and a `verdict` is a filmed attempt, whichever runner wrote it."""
    if isinstance(obj, dict):
        if obj.get("video") and isinstance(obj.get("verdict"), dict):
            out.append(dict(video=obj["video"], verdict=obj["verdict"], code=obj.get("code"), **ctx))
        for v in obj.values():
            walk(v, ctx, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, ctx, out)


def collect(results: list[str]) -> list[dict]:
    clips, seen = [], set()
    for path in results:
        if path.endswith(".partial.json"):
            continue
        with open(path) as f:
            d = json.load(f)
        found = []
        walk(d, dict(robot=d.get("robot", "franka"), model=d.get("model"), source=os.path.basename(path), shape=d.get("shape")), found)
        for c in found:
            if c["video"] not in seen and os.path.exists(os.path.join(c["video"], "meta.json")):
                seen.add(c["video"])
                clips.append(c)
    return clips


def describe(c: dict) -> dict:
    tag = os.path.basename(c["video"].rstrip("/"))
    m = TAG_RE.match(tag)
    shape, seed, cond, n = (m.group("shape"), m.group("seed"), m.group("cond"), m.group("n")) if m else (tag, "?", "?", None)
    shape = c.get("shape") or shape  # the record's scenario name (place_cube, nav) beats the tag's: one-shot/physics tags of the place task carried the bare shape
    cond_label = ("replay: " + COND_NAMES.get(cond[6:], cond[6:])) if cond.startswith("refilm") else COND_NAMES.get(cond, cond)
    title = f"{ROBOT_NAMES.get(c['robot'], c['robot'])}  |  {shape}  |  seed {seed}  |  {cond_label}"
    if n:
        title += f"  |  attempt {n}"
    v = c["verdict"]
    ok = bool(v.get("success"))
    if "final_dist_m" in v and "waypoint_passed" in v:  # navigation
        result = f"PASS  stopped {v['final_dist_m']:.2f} m from the goal" if ok else f"FAIL  {v.get('failure')}"
    elif "final_dist_m" in v:  # placement
        result = f"PASS  placed {v['final_dist_m']:.3f} m from the target" if ok else f"FAIL  {v.get('failure')}"
    elif "opening_m" in v:  # drawer
        result = f"PASS  drawer open {v['opening_m']:.2f} m" if ok else f"FAIL  {v.get('failure')}"
    else:
        result = f"PASS  held {v.get('final_rise_m', 0):.3f} m" if ok else f"FAIL  {v.get('failure')}"
    model = (c.get("model") or "").split("/")[-1] if cond != "scripted" else ""
    return dict(tag=tag, title=title, ok=ok, result=result, model=model, cond=cond, shape=shape, seed=seed, n=n)


def _encoder(path: str, W: int, H: int, fps: int) -> subprocess.Popen:
    return subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                             "-movflags", "+faststart", path], stdin=subprocess.PIPE)


def compose(c: dict, info: dict, out_mp4: str) -> dict:
    with open(os.path.join(c["video"], "meta.json")) as f:
        meta = json.load(f)
    cams, frames = meta["cameras"], meta["frames"]
    # frames lost on disk (an early recorder shared one staging folder between concurrent grids) are skipped;
    # a clip with fewer than two surviving frames is dropped and flagged in the index
    present = [fm for fm in frames if all(os.path.exists(os.path.join(c["video"], cam, f"frame_{fm['i']:06d}.png")) for cam in cams)]
    lost = len(frames) - len(present)
    if len(present) < 2:
        print(f"[video] {info['tag']}: {lost} of {len(frames)} frames missing, clip skipped")
        return None
    if lost:
        print(f"[video] {info['tag']}: {lost} of {len(frames)} frames missing, clip built from the rest")
    frames = present
    fps = max(1, round(1.0 / meta["frame_dt_s"]))
    w, h = Image.open(os.path.join(c["video"], cams[0], f"frame_{frames[0]['i']:06d}.png")).size
    W, H = w * len(cams), h + BANNER
    big, small = _font(FONT, 20), _font(FONT, 16)
    enc = _encoder(out_mp4, W, H, fps)
    hold = fps  # the end state stays on screen for a second
    for k, fm in enumerate(frames):
        canvas = Image.new("RGB", (W, H), BG)
        for j, cam in enumerate(cams):
            canvas.paste(Image.open(os.path.join(c["video"], cam, f"frame_{fm['i']:06d}.png")).convert("RGB"), (j * w, BANNER))
        d = ImageDraw.Draw(canvas)
        d.text((10, 6), info["title"], font=big, fill=FG)
        grip = "" if info["shape"] == "nav" else f"     gripper {'closed' if fm['closed'] else 'open'}"  # walkers have no gripper
        d.text((10, 33), f"t = {fm['t']:5.2f} s     {meta.get('metric_name', 'object rise')} = {fm['rise_m']:+.3f} m{grip}"
               + (f"     {info['model']}" if info["model"] else ""), font=small, fill=DIM)
        tw = d.textlength(info["result"], font=big)
        d.text((W - tw - 10, 18), info["result"], font=big, fill=OK if info["ok"] else BAD)
        for j, cam in enumerate(cams):
            d.text((j * w + 8, BANNER + 6), cam.replace("_", " "), font=small, fill=FG, stroke_width=2, stroke_fill=BG)
        buf = canvas.tobytes()
        enc.stdin.write(buf)
        if k == len(frames) - 1:
            for _ in range(hold):
                enc.stdin.write(buf)
    enc.stdin.close()
    enc.wait()
    return dict(W=W, H=H, fps=fps, seconds=round((len(frames) + hold) / fps, 1))


def title_card(c: dict, info: dict, out_mp4: str, W: int, H: int, fps: int) -> float:
    """Black card with the trial, the result and, for Nemotron attempts, the program that ran."""
    seconds = 3.5 if c.get("code") else 1.5
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.text((24, 20), info["title"], font=_font(FONT, 24), fill=FG)
    d.text((24, 56), info["result"] + (f"     model {info['model']}" if info["model"] else ""), font=_font(FONT, 20),
           fill=OK if info["ok"] else BAD)
    if c.get("code"):
        mono = _font(MONO, 15)
        lines = [ln for ln in c["code"].strip().splitlines() if ln.strip()]
        y = 96
        for ln in lines[: (H - 110) // 19]:
            d.text((24, y), ln[:150], font=mono, fill=DIM)
            y += 19
        if len(lines) > (H - 110) // 19:
            d.text((24, y), f"... {len(lines) - (H - 110) // 19} more lines", font=mono, fill=DIM)
    enc = _encoder(out_mp4, W, H, fps)
    buf = canvas.tobytes()
    for _ in range(int(seconds * fps)):
        enc.stdin.write(buf)
    enc.stdin.close()
    enc.wait()
    return seconds


def main():
    ap = argparse.ArgumentParser(description="GraspLoop review videos")
    ap.add_argument("--video-dir", required=True, help="the --video directory the runners filmed into")
    ap.add_argument("--results", nargs="+", required=True, help="result JSONs (gate_t1, run_loop, run_grid), in reel order")
    ap.add_argument("--out", default="_logs/review")
    ap.add_argument("--no-reel", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    clips = collect(args.results)
    if not clips:
        raise SystemExit(f"no filmed attempts with a verdict in {args.results}")
    rows, concat, total = [], [], 0.0
    cards = os.path.join(args.out, "_cards")
    os.makedirs(cards, exist_ok=True)
    for i, c in enumerate(clips):
        info = describe(c)
        mp4 = os.path.join(args.out, f"{i + 1:02d}_{info['tag']}.mp4")
        enc = compose(c, info, mp4)
        if enc is None:  # footage lost; the record still has the verdict
            continue
        card = os.path.join(cards, f"{i + 1:02d}_title.mp4")
        t_card = title_card(c, info, card, enc["W"], enc["H"], enc["fps"])
        concat += [card, mp4]
        total += enc["seconds"] + t_card
        rows.append(dict(i=i + 1, **info, mp4=mp4, seconds=enc["seconds"], source=c["source"]))
        print(f"[video] {i + 1:02d} {info['tag']:40s} {info['result']:28s} {enc['seconds']:5.1f} s -> {mp4}")
    reel = None
    if not args.no_reel and len(concat) > 0:
        lst = os.path.join(cards, "concat.txt")
        with open(lst, "w") as f:
            for p in concat:
                f.write(f"file '{os.path.abspath(p)}'\n")
        reel = os.path.join(args.out, "reel.mp4")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", reel], check=True)
    with open(os.path.join(args.out, "index.md"), "w") as f:
        f.write("# GraspLoop review videos\n\n")
        if reel:
            f.write(f"Reel of everything, with title cards: `{reel}` ({total / 60:.1f} min)\n\n")
        f.write("| # | trial | result | s | clip | from |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['i']} | {r['title']} | {r['result']} | {r['seconds']} | `{os.path.basename(r['mp4'])}` | {r['source']} |\n")
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(dict(reel=reel, total_s=round(total, 1), clips=rows), f, indent=1)
    print(f"[video] {len(rows)} clips, {total / 60:.1f} min" + (f", reel -> {reel}" if reel else "") + f"; index -> {args.out}/index.md")


if __name__ == "__main__":
    main()
