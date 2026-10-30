"""Demo cut from the records and the films: cards plus shots with a narration bar, no voice.
Card tables and every line of code or feedback on a card are read from the grid records; the narration
captions quote headline numbers from docs/02, docs/03 and docs/04 as fixed text.

Shots come from the hero footage when it exists (`eval/refilm.py --hero`: NVIDIA's OVRTX path tracer,
1280x720, plus the side camera for a picture-in-picture of what the reviewer saw), and fall back to the
review clips (`eval/make_videos.py`, two Warp cameras side by side) otherwise.

    $PY eval/make_demo.py --bench _logs/bench --scale _logs/scale --hero _logs/hero/video --out _logs/demo/grasploop_draft.mp4
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

FFMPEG = os.path.expanduser("~/.local/bin/ffmpeg") if os.path.exists(os.path.expanduser("~/.local/bin/ffmpeg")) else "ffmpeg"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
W, H, FPS = 1280, 720, 15
CLIP_H = 536
BG, FG, DIM, OK, BAD, ACC = (18, 18, 22), (235, 235, 235), (170, 170, 175), (90, 220, 110), (240, 90, 80), (255, 196, 64)
HERO_RE = re.compile(r"^(?P<robot>franka|allegro|go2|g1)_(?P<shape>.+)_s(?P<seed>\d+)_refilm(?P<cond>[a-z]+)_a(?P<n>\d+)$")
ROBOT_NAMES = {"franka": "Franka Panda", "allegro": "Kuka iiwa + Allegro", "go2": "Unitree Go2", "g1": "Unitree G1"}
COND_NAMES = {"scripted": "scripted reference", "oneshot": "Nemotron one-shot", "rerun": "rerun, no repair",
              "physics": "Nemotron + physics feedback", "vision": "Nemotron + physics + vision feedback"}
OBJECTS = {"cube": "cube", "box_flat": "thin box", "box_tall": "tall box", "sphere_s": "small sphere", "sphere_m": "medium sphere", "capsule_s": "capsule"}
_FONTS: dict = {}


def f(path, size):
    key = (path, size)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]


def caption_bar(canvas, text):
    """The card layout: an opaque band under the clip area."""
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, CLIP_H, W, H], fill=(10, 10, 12))
    d.line([0, CLIP_H, W, CLIP_H], fill=(60, 60, 66), width=2)
    y = CLIP_H + 18
    for line in textwrap.wrap(text, 92):
        d.text((28, y), line, font=f(REG, 24), fill=FG)
        y += 32
    d.text((W - 150, H - 30), "GraspLoop", font=f(FONT, 16), fill=DIM)


def lower_third(canvas, text, rate=None):
    """The shot layout: a translucent band over the footage, two or three lines of narration, and the playback
    rate stated on the frame itself (IEEE RAS video guidance: say on screen whether footage is sped up)."""
    lines = textwrap.wrap(text, 84)
    size = 26 if len(lines) <= 2 else 22
    lines = textwrap.wrap(text, 84 if size == 26 else 100)
    band = 30 + len(lines) * (size + 8)
    overlay = Image.new("RGBA", (W, band), (8, 8, 10, 178))
    canvas.paste(Image.alpha_composite(canvas.crop((0, H - band, W, H)).convert("RGBA"), overlay).convert("RGB"), (0, H - band))
    d = ImageDraw.Draw(canvas)
    y = H - band + 14
    for line in lines:
        d.text((28, y), line, font=f(REG, size), fill=FG)
        y += size + 8
    tail = ("simulation, " + rate + "  ·  " if rate else "") + "GraspLoop"
    d.text((W - 24 - d.textlength(tail, font=f(FONT, 14)), H - 24), tail, font=f(FONT, 14), fill=DIM)
    return band


def chip(canvas, xy, text, font, fill=FG, bg=(8, 8, 10, 170), anchor="left"):
    """Text on a translucent pill; anchor="right" places it ending at xy[0]."""
    d = ImageDraw.Draw(canvas)
    tw = d.textlength(text, font=font)
    h = font.size + 14
    x = xy[0] if anchor == "left" else xy[0] - tw - 20
    box = canvas.crop((int(x), xy[1], int(x + tw + 20), xy[1] + h)).convert("RGBA")
    canvas.paste(Image.alpha_composite(box, Image.new("RGBA", box.size, bg)).convert("RGB"), (int(x), xy[1]))
    d.text((x + 10, xy[1] + 6), text, font=font, fill=fill)


def card(title, lines, caption, mono=False, highlight=()):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.text((40, 30), title, font=f(FONT, 34), fill=ACC)
    y = 96
    font = f(MONO if mono else REG, 21 if mono else 23)
    width = 94 if mono else 100  # a line longer than the frame wraps instead of running off the right edge
    for i, ln in enumerate(lines):
        colour = OK if i in highlight else (FG if mono else DIM)
        for part in (textwrap.wrap(ln, width, subsequent_indent="    ") or [""]):
            if y > CLIP_H - 30:
                break
            d.text((40, y), part, font=font, fill=colour)
            y += 28 if mono else 31
    caption_bar(canvas, caption)
    return canvas


def code_lines(code):
    return [ln for ln in code.strip().splitlines() if ln.strip() and not ln.strip().startswith("#")]


# ---- hero footage ---------------------------------------------------------------------------------------------

def hero_info(src: str) -> dict:
    """What a hero footage folder is: robot, shape, seed, condition, attempt, plus its meta.json."""
    tag = os.path.basename(src.rstrip("/"))
    m = HERO_RE.match(tag)
    with open(os.path.join(src, "meta.json")) as fh:
        meta = json.load(fh)
    info = dict(tag=tag, meta=meta, robot=m.group("robot"), shape=m.group("shape"), seed=int(m.group("seed")), cond=m.group("cond"), n=int(m.group("n")))
    shape = info["shape"]
    if shape == "nav":
        info["task"] = "navigate: waypoint, then goal"
    elif shape.startswith("place_"):
        info["task"] = f"pick and place, {OBJECTS.get(shape[6:], shape[6:])}"
    else:
        info["task"] = f"pick up and hold, {OBJECTS.get(shape, shape)}"
    return info


def verdict_text(v: dict) -> tuple[str, bool]:
    ok = bool(v.get("success"))
    if "final_dist_m" in v and "waypoint_passed" in v:
        return (f"PASS   stopped {v['final_dist_m']:.2f} m from the goal" if ok else f"FAIL   {v.get('failure')}"), ok
    if "final_dist_m" in v:
        return (f"PASS   placed {v['final_dist_m']:.3f} m from the target" if ok else f"FAIL   {v.get('failure')}"), ok
    return (f"PASS   held {v.get('final_rise_m', 0):.3f} m" if ok else f"FAIL   {v.get('failure')}"), ok


def load_verdicts(records_dir: str) -> dict:
    """tag -> verdict from the refilm records next to the hero footage (eval/refilm.py --json)."""
    out = {}
    for p in glob.glob(os.path.join(records_dir, "refilm_*.json")):
        with open(p) as fh:
            d = json.load(fh)
        for cond, eps in d.get("episodes", {}).items():
            for e in eps:
                for att in e.get("attempts") or []:
                    out[f"{d['robot']}_{d['shape']}_s{e['seed']}_refilm{cond}_a{att.get('n', 1)}"] = att["verdict"]
    return out


def frame_schedule(meta: dict, seconds: float, tail: bool, speed: float) -> list[tuple[dict, bool]]:
    """Which source frame each output frame shows, and whether the shot has reached its end state (held)."""
    frames = meta["frames"]
    T = frames[-1]["t"]
    hold = 1.5  # a tail shot keeps its end state on screen this long, so the verdict chip can be read
    t0 = max(0.0, T - (seconds - hold) * speed) if tail else 0.0
    out, j = [], 0
    for k in range(int(seconds * FPS)):
        t = t0 + k / FPS * speed
        while j + 1 < len(frames) and frames[j + 1]["t"] <= t:
            j += 1
        out.append((frames[j], t >= T - 1e-6 or j == len(frames) - 1))
    return out


def rate_text(speed: float) -> str:
    return "real time" if abs(speed - 1.0) < 1e-6 else f"{speed:g}x speed"


def status_chip(canvas, info, fm, ended, verdict):
    """Top-left, two lines: the robot and task, then the seed, condition and attempt. Top-right: the clock and the
    metric while the program runs, the verdict once it has ended."""
    cond = COND_NAMES.get(info["cond"], info["cond"])
    chip(canvas, (20, 18), f"{ROBOT_NAMES.get(info['robot'], info['robot'])}  ·  {info['task']}", f(FONT, 18))
    second = f"seed {info['seed']}  ·  {cond}" + (f", attempt {info['n']}" if info["cond"] != "scripted" else "")
    chip(canvas, (20, 54), second, f(REG, 16), fill=DIM)
    if ended and verdict is not None:
        text, ok = verdict_text(verdict)
        chip(canvas, (W - 20, 18), text, f(FONT, 20), fill=OK if ok else BAD, anchor="right")
    else:
        metric = info["meta"].get("metric_name", "object rise")
        chip(canvas, (W - 20, 18), f"t = {fm['t']:5.1f} s    {metric} {fm['rise_m']:+.3f} m", f(MONO, 19), fill=DIM, anchor="right")


class Encoder:
    def __init__(self, out):
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        self.p = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                   "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19",
                                   "-movflags", "+faststart", out], stdin=subprocess.PIPE)
        self.frames = 0
        self.verdicts: dict = {}

    def still(self, canvas, seconds, label="card"):
        self.mark(f"still {label}")
        buf = canvas.tobytes()
        for _ in range(int(seconds * FPS)):
            self.p.stdin.write(buf)
            self.frames += 1

    def mark(self, label):
        print(f"[demo] {self.frames / FPS:6.1f} s  {label}")

    def clip(self, path, seconds, caption, tail=False):
        """Fallback shot from a review clip (two Warp cameras under a banner) over the card-style caption bar."""
        # loglevel quiet: the pipe is closed early on purpose once the slot is filled
        # tail=True takes the clip's last `seconds` (the placement, the arrival) instead of its first
        self.mark(f"clip {os.path.basename(path)}{' (tail)' if tail else ''}: {caption[:70]}")
        seek = ["-sseof", str(-seconds - 1.0)] if tail else []  # the clip holds its end state for ~1 s
        dec = subprocess.Popen([FFMPEG, "-loglevel", "quiet", *seek, "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{CLIP_H}", "-r", str(FPS), "-"], stdout=subprocess.PIPE)
        n, last, size = 0, None, W * CLIP_H * 3
        while n < int(seconds * FPS):
            raw = dec.stdout.read(size)
            if len(raw) < size:
                break
            frame = Image.frombytes("RGB", (W, CLIP_H), raw)
            canvas = Image.new("RGB", (W, H), BG)
            canvas.paste(frame, (0, 0))
            caption_bar(canvas, caption)
            last = canvas.tobytes()
            self.p.stdin.write(last)
            n += 1
        dec.stdout.close()
        dec.wait()
        while last is not None and n < int(seconds * FPS):  # hold the end state to fill the slot
            self.p.stdin.write(last)
            n += 1
        self.frames += n

    def hero(self, src, seconds, caption, tail=False, pip=False, speed=1.0):
        """A shot from hero footage: the path-traced frame full screen, the trial and the live metric as chips,
        the verdict once the program has ended, the narration as a lower third, and optionally the reviewer's
        side camera as a picture-in-picture."""
        info = hero_info(src)
        verdict = self.verdicts.get(info["tag"])
        self.mark(f"hero {info['tag']}{' (tail)' if tail else ''}{' +pip' if pip else ''}: {caption[:60]}")
        for fm, ended in frame_schedule(info["meta"], seconds, tail, speed):
            canvas = Image.open(os.path.join(src, "hero_cam", f"frame_{fm['i']:06d}.png")).convert("RGB")
            if canvas.size != (W, H):
                canvas = canvas.resize((W, H))
            band = lower_third(canvas, caption, rate_text(speed))
            status_chip(canvas, info, fm, ended, verdict)
            if pip:
                side = Image.open(os.path.join(src, "side_cam", f"frame_{fm['i']:06d}.png")).convert("RGB").resize((288, 216))
                x, y = W - 288 - 24, H - band - 216 - 34
                d = ImageDraw.Draw(canvas)
                d.rectangle([x - 2, y - 2, x + 289, y + 217], outline=(235, 235, 235), width=2)
                canvas.paste(side, (x, y))
                d.text((x, y - 22), "the reviewer's camera, 320 x 240", font=f(FONT, 15), fill=FG, stroke_width=2, stroke_fill=(8, 8, 10))
            self.p.stdin.write(canvas.tobytes())
            self.frames += 1

    def montage(self, srcs, seconds, caption, tail=True, speed=1.0):
        """Four hero shots at once, each ending on its own end state: the same loop on four seeds."""
        srcs = list(srcs)[:4]
        infos = [hero_info(s) for s in srcs]
        self.mark(f"montage {', '.join(i['tag'] for i in infos)}: {caption[:50]}")
        schedules = [frame_schedule(i["meta"], seconds, tail, speed) for i in infos]
        tw, th = W // 2, H // 2
        for k in range(int(seconds * FPS)):
            canvas = Image.new("RGB", (W, H), BG)
            for j, (src, info, sch) in enumerate(zip(srcs, infos, schedules)):
                fm, ended = sch[k]
                tile = Image.open(os.path.join(src, "hero_cam", f"frame_{fm['i']:06d}.png")).convert("RGB").resize((tw - 2, th - 2))
                x, y = (j % 2) * tw + 1, (j // 2) * th + 1
                canvas.paste(tile, (x, y))
                label = f"seed {info['seed']}  ·  attempt {info['n']}"
                v = self.verdicts.get(info["tag"])
                if ended and v is not None:
                    label += "  ·  " + ("PASS" if v.get("success") else "FAIL")
                    chip(canvas, (x + 12, y + 12), label, f(FONT, 16), fill=OK if v.get("success") else BAD)
                else:
                    chip(canvas, (x + 12, y + 12), label, f(FONT, 16))
            lower_third(canvas, caption, rate_text(speed))
            self.p.stdin.write(canvas.tobytes())
            self.frames += 1

    def shot(self, hero_root, tag, review_dir, review_suffix, seconds, caption, tail=False, pip=False, speed=1.0):
        """Hero footage if `hero_root/tag` exists, else the review clip `*_review_suffix.mp4`."""
        src = os.path.join(hero_root, tag) if hero_root else ""
        if src and os.path.exists(os.path.join(src, "meta.json")):
            self.hero(src, seconds, caption, tail=tail, pip=pip, speed=speed)
        else:
            self.clip(find_clip(review_dir, review_suffix), seconds, caption, tail=tail)

    def close(self):
        self.p.stdin.close()
        self.p.wait()
        return self.frames / FPS


def find_clip(review_dir, suffix):
    hits = sorted(glob.glob(os.path.join(review_dir, f"*_{suffix}.mp4")))
    if not hits:
        raise SystemExit(f"no clip *_{suffix}.mp4 in {review_dir}")
    return hits[0]


def first_pass_clip(record: dict, review_dir: str, conds=("physics", "oneshot", "scripted")) -> tuple[str, str] | None:
    """The first successful attempt of the first condition that has one: (clip path, caption fragment)."""
    for cond in conds:
        for e in record["episodes"].get(cond, []):
            for att in (e.get("attempts") or [e]):
                if att.get("verdict", {}).get("success") and att.get("video"):
                    tag = os.path.basename(att["video"].rstrip("/"))
                    robot_shape = tag.split("_s")[0]
                    refilm = sorted(glob.glob(os.path.join(review_dir, f"*_{robot_shape}_s{e['seed']}_refilm{cond}_a{att.get('n', 1)}.mp4")))
                    hits = refilm or sorted(glob.glob(os.path.join(review_dir, f"*_{tag}.mp4")))
                    if hits:
                        return hits[0], cond
    return None


def hero_passes(record: dict, hero_root: str, verdicts: dict, cond="physics") -> list[str]:
    """Hero footage folders of this record's successful attempts under `cond`, in seed order, keeping only replays
    that passed again: physics is not run-to-run deterministic, and a replay that failed must not be shown as a pass."""
    out = []
    if not hero_root:
        return out
    robot, shape = record.get("robot", "franka"), record["shape"]
    for e in record["episodes"].get(cond, []):
        for att in (e.get("attempts") or [e]):
            if att.get("verdict", {}).get("success"):
                tag = f"{robot}_{shape}_s{e['seed']}_refilm{cond}_a{att.get('n', 1)}"
                src = os.path.join(hero_root, tag)
                if os.path.exists(os.path.join(src, "meta.json")) and verdicts.get(tag, {}).get("success"):
                    out.append(src)
    return out


def figure_still(path: str, caption: str) -> "Image.Image":
    """A saved figure (e.g. eval/nav_paths.py) letterboxed into the clip area, over the caption bar."""
    canvas = Image.new("RGB", (W, H), BG)
    im = Image.open(path).convert("RGB")
    k = min((W - 40) / im.width, (CLIP_H - 24) / im.height)
    im = im.resize((int(im.width * k), int(im.height * k)))
    canvas.paste(im, ((W - im.width) // 2, (CLIP_H - im.height) // 2))
    caption_bar(canvas, caption)
    return canvas


def scale_section(enc: "Encoder", scale_dir: str, hero_root: str) -> None:
    """Other robots and tasks, if their records and films exist: one shot each (a montage of four seeds after the
    first walker and the first place cell) plus the matrix card."""
    recs = []
    for p in sorted(glob.glob(os.path.join(scale_dir, "*.json"))):
        if p.endswith(".partial.json"):
            continue
        with open(p) as fh:
            d = json.load(fh)
        if "summary" in d and str(d.get("script", "")).endswith("run_grid.py"):  # not refilm records
            recs.append(d)
    if not recs:
        return
    order = {"go2": 0, "g1": 1}  # walkers first, then the place cells by object: cube, thin box, tall box
    objects = {"cube": "a cube", "box_flat": "a thin box", "box_tall": "a tall box"}
    recs.sort(key=lambda d: (order.get(d.get("robot"), 2), list(objects).index(d["shape"].replace("place_", "")) if d["shape"].replace("place_", "") in objects else 9))
    rv = os.path.join(scale_dir, "review")
    names = {"go2": "a Unitree Go2 quadruped", "g1": "a Unitree G1 humanoid", "franka": "the Franka"}
    montages_done = set()
    for d in recs:
        robot, shape = d.get("robot", "franka"), d["shape"]
        obj = objects.get(shape.replace("place_", ""), shape)
        sc = d["summary"]
        if shape == "nav":
            cap = (f"Same loop, different body: Nemotron writes a navigation program for {names.get(robot, robot)} over a policy trained "
                   f"with NVIDIA's RSL-RL on Newton in minutes. Reference {sc['scripted']['successes']}/{sc['scripted']['n']}, "
                   f"Nemotron with physics feedback {sc.get('physics', {}).get('successes', '?')}/{sc.get('physics', {}).get('n', '?')}.")
        else:
            cap = (f"Same loop, different task: pick {obj} up and place it on the target with {names.get(robot, robot)}. Reference "
                   f"{sc['scripted']['successes']}/{sc['scripted']['n']}, Nemotron with physics feedback "
                   f"{sc.get('physics', {}).get('successes', '?')}/{sc.get('physics', {}).get('n', '?')}.")
        heroes = hero_passes(d, hero_root, enc.verdicts)
        if heroes:
            enc.hero(heroes[0], 8, cap, tail=True)
        else:
            hit = first_pass_clip(d, rv)
            if not hit:
                continue
            enc.clip(hit[0], 8, cap, tail=True)
        fig = os.path.join(scale_dir, "figures", f"{robot}_{shape}_attempts.png")  # eval/nav_paths.py, one seed, every attempt
        if shape == "nav" and os.path.exists(fig):
            enc.still(figure_still(fig, f"Top-down, from the saved trace: the feedback names the overshoot and the end state; "
                                        f"Nemotron's next program settles on the bearing and reaches the goal."), 7)
        kind = "nav" if shape == "nav" else "place"
        if len(heroes) >= 4 and kind not in montages_done:
            montages_done.add(kind)
            what = "walks the waypoint and stops on the goal" if kind == "nav" else "places the object on the target"
            enc.montage(heroes[:4], 7, f"Four seeds, four programs written and repaired by Nemotron: each {what}. "
                                        f"Same prompt, same sandbox, same judge interface.", tail=True)
    rows = ["robot                         task                            reference   one-shot   physics"]
    tot = dict(scripted=[0, 0], oneshot=[0, 0], physics=[0, 0])
    for d in recs:
        sc = d["summary"]
        obj = objects.get(d["shape"].replace("place_", ""), "")
        task = "navigate (waypoint, goal)" if d["shape"] == "nav" else (f"pick and place, {obj.split(' ', 1)[1] if obj else d['shape']}" if d["shape"].startswith("place_") else "pick up and hold")
        rows.append(f"{names.get(d.get('robot', 'franka'), d.get('robot')):30s}{task:32s}{sc['scripted']['successes']:>3d}/{sc['scripted']['n']:<6d}"
                    f"{sc.get('oneshot', {}).get('successes', 0):>3d}/{sc.get('oneshot', {}).get('n', 0):<6d}"
                    f"{sc.get('physics', {}).get('successes', 0):>3d}/{sc.get('physics', {}).get('n', 0):<4d}")
        for k in tot:
            tot[k][0] += sc.get(k, {}).get("successes", 0)
            tot[k][1] += sc.get(k, {}).get("n", 0)
    rows.append("")
    rows.append(f"{'all cells, same seeds':30s}{'paired over ' + str(tot['physics'][1]) + ' scenarios':32s}{tot['scripted'][0]:>3d}/{tot['scripted'][1]:<6d}"
                f"{tot['oneshot'][0]:>3d}/{tot['oneshot'][1]:<6d}{tot['physics'][0]:>3d}/{tot['physics'][1]:<4d}")
    st = os.path.join(scale_dir, "stats", "stats.json")
    if os.path.exists(st):
        with open(st) as fh:
            sj = json.load(fh)
        for pr in sj.get("paired", []):
            if pr.get("a") == "physics" and pr.get("b") == "oneshot":
                rows.append(f"{'':30s}{'physics - one-shot':32s}{pr['diff']:+.2f}  95% CI [{pr['ci95'][0]:+.2f}, {pr['ci95'][1]:+.2f}]")
    enc.still(card("6. Robots x tasks: one loop, four bodies, three task families", rows,
                   "Arms, a dexterous hand, a quadruped and a humanoid; lifting, placing and navigating. Every cell: the same prompt loop, sandbox, judge interface and films.",
                   mono=True), 10, label="6. robots x tasks")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="_logs/bench")
    ap.add_argument("--out", default="_logs/demo/grasploop_draft.mp4")
    ap.add_argument("--scale", default="_logs/scale", help="grid records + review clips of the other robots and tasks; skipped if absent")
    ap.add_argument("--cloud-hero", default="_logs/cloud/vm/hero",
                    help="hero footage filmed on the Nebius H100 (eval/refilm.py --hero on the VM, pulled by eval/cloud/nebius_vm.sh); one shot if present")
    ap.add_argument("--hero", default="_logs/hero/video", help="hero footage from eval/refilm.py --hero; its refilm_*.json records are read from the parent directory")
    a = ap.parse_args()
    hero = a.hero if os.path.isdir(a.hero) else ""
    rv = os.path.join(a.bench, "review")
    cube = json.load(open(os.path.join(a.bench, "franka_cube.json")))
    stats = json.load(open(os.path.join(a.bench, "stats", "stats.json")))
    allegro = json.load(open(os.path.join(a.bench, "allegro_cube.json")))
    vis = [e for e in cube["episodes"]["vision"] if e["seed"] == 100][0]
    a1, a2 = vis["attempts"][0], vis["attempts"][1]
    one = [e for e in cube["episodes"]["oneshot"] if e["seed"] == 100][0]["attempts"][0]
    review = a1["vision"]["structured"]
    fb = [ln.strip() for ln in a1["feedback"].splitlines() if ln.strip()]
    fb_keep = [ln for ln in fb if any(k in ln for k in ("FAILED", "close_gripper", "ABOVE", "lift(", "At the end"))][:6]
    pc = stats["conditions"]
    pairs = {(p["a"], p["b"]): p for p in stats["paired"]}
    enc = Encoder(a.out)
    enc.verdicts = load_verdicts(os.path.dirname(hero.rstrip("/"))) if hero else {}
    print(f"[demo] hero footage: {hero or 'none, review clips only'}; {len(enc.verdicts)} replay verdicts")

    enc.shot(hero, "franka_cube_s100_refilmoneshot_a1", rv, "franka_cube_s100_none_a1", 10,
             "Writing robot manipulation code is only half the challenge. The harder problem is knowing why an action failed and what to change.")
    enc.still(card("1. Nemotron writes the program",
                   ["Task: pick up the object from the table and hold it in the air.", "",
                    "Model: nvidia/Nemotron-3_5-Lightning on Nebius Token Factory, one program against a 12-call grasp API:",
                    "get_object, ee_pose, move_to, yaw_quat, lift, open_gripper, close_gripper, wait, object_height, ...", ""]
                   + code_lines(one["code"]),
                   "GraspLoop asks NVIDIA Nemotron 3.5 Lightning, served by Nebius Token Factory, to write a grasp program for an Isaac Lab robot. No human writes robot code here.",
                   mono=False), 11)
    enc.shot(hero, "franka_cube_s100_refilmvision_a1", rv, "franka_cube_s100_vision_a1", 9,
             "The program runs on Newton physics in Isaac Lab 3.0, without Isaac Sim. The simulator measures the object, the contacts and the fingers; a side camera films every attempt for the reviewer.",
             pip=True)
    enc.still(card("2. What the simulator measured", fb_keep,
                   "The measurements go back to the model in plain words: where the fingers closed relative to the object, whether the object moved, what the hold achieved.",
                   mono=True, highlight=tuple(i for i, ln in enumerate(fb_keep) if "ABOVE" in ln)), 11)
    rl = [f"failure_type: {review.get('failure_type')}    confidence: {review.get('confidence')}", ""]
    rl += textwrap.wrap("evidence: " + str(review.get("evidence")), 88) + [""]
    rl += textwrap.wrap("suggested_correction: " + str(review.get("suggested_correction")), 88)
    enc.still(card("3. What the camera reviewer saw", rl,
                   "Nemotron 3.5 Super-VL watches eight frames of the attempt and returns a structured diagnosis. It never sees the physics verdict.",
                   mono=True), 11)
    c2 = code_lines(a2["code"])
    enc.still(card("4. The repaired program", c2 + ["", "changed: the grasp point moves from above the top face to inside the object"],
                   "Nemotron revises its program with both kinds of feedback and retries the very same scenario.",
                   mono=True, highlight=tuple(i for i, ln in enumerate(c2) if "half_height" in ln)), 9)
    enc.shot(hero, "franka_cube_s100_refilmvision_a2", rv, "franka_cube_s100_vision_a2", 10, "Second attempt, same scenario: the cube is lifted and held.", pip=True)
    enc.shot(hero, "franka_box_flat_s101_refilmphysics_a2", rv, "franka_box_flat_s101_physics_a2", 8,
             "The same loop on a thin box: first attempt missed, second attempt holds it.")
    cloud = a.cloud_hero if a.cloud_hero and os.path.exists(os.path.join(a.cloud_hero, "franka_cube_s100_refilmphysics_a1", "meta.json")) else ""
    if cloud:  # the same cell on a Nebius AI Cloud H100 (doc 04): its replay verdicts live beside the hero root
        saved, enc.verdicts = enc.verdicts, load_verdicts(os.path.dirname(cloud.rstrip("/")))
        enc.hero(os.path.join(cloud, "franka_cube_s100_refilmphysics_a1"), 8,
                 "Same code, same scene, on a Nebius AI Cloud H100: Isaac Lab 3.0 kit-less on Newton, no Isaac Sim, no RT cores. "
                 "The cube cell replicated there, 7 of 8, filmed by NVIDIA's OVRTX path tracer.", tail=True, pip=True)
        enc.verdicts = saved
    rows = [f"{'condition':30s} {'success':>9s}   {'95% CI':>11s}   first try"]
    for c in ("scripted", "oneshot", "rerun", "physics", "vision"):
        r = pc[c]
        rows.append(f"{r['label']:30s} {r['successes']:>3d}/{r['n']:<3d}     {r['ci95'][0]:.2f}-{r['ci95'][1]:.2f}    {r['first_attempt']}/{r['n']}")
    pb, pc0, dc = pairs[("physics", "oneshot")], pairs[("physics", "rerun")], pairs[("vision", "physics")]
    rows += ["", f"physics - one-shot     {pb['diff']:+.2f}  [{pb['ci95'][0]:+.2f}, {pb['ci95'][1]:+.2f}]  paired bootstrap",
             f"physics - rerun        {pc0['diff']:+.2f}  [{pc0['ci95'][0]:+.2f}, {pc0['ci95'][1]:+.2f}]  repairs are not luck",
             f"vision - physics       {dc['diff']:+.2f}  [{dc['ci95'][0]:+.2f}, {dc['ci95'][1]:+.2f}]  not separated from zero",
             "", f"reviewer vs physics: {stats['reviewer']['agree']}/{stats['reviewer']['n']} agree, {stats['reviewer']['false_positive']} false positives, {stats['reviewer']['false_negative']} false negatives"]
    enc.still(card(f"5. {stats['scenarios']} matched scenarios, 6 shapes, 5 conditions", rows,
                   "Every condition sees the same seeds. Physics feedback beats one-shot and beats a no-repair rerun by 19 points; the camera reviewer on top adds 6, inside the noise. All on one laptop GPU for $1.37 of Token Factory credit.",
                   mono=True), 15)
    enc.shot(hero, "franka_sphere_s_s100_refilmphysics_a3", rv, "franka_sphere_s_s100_physics_a3", 8,
             "Where it fails is as informative. The small sphere: the reference lifts 8 of 8, Nemotron at most 2 of 8, closing at the equator every time. Feedback states the offset, not the rule.")
    enc.shot(hero, "franka_box_tall_s100_refilmphysics_a1", rv, "franka_box_tall_s100_physics_a1", 7,
             "The camera judge agreed with physics on 97% of attempts and missed nothing that worked, but called every lift under the 10 cm threshold a success. Categorical, not metric.",
             pip=True)
    al = allegro["summary"]
    enc.shot(hero, "allegro_cube_s100_refilmscripted_a1", rv, "allegro_cube_s100_scripted", 7,
             f"The same API drives a four-finger Allegro hand: the reference lifts the cube {al['scripted']['successes']} of 8, the model {al['physics']['successes']} of 8. Priors the feedback cannot supply.")
    scale_section(enc, a.scale, hero)
    enc.still(card("GraspLoop", ["generate  ->  execute  ->  measure  ->  review  ->  repair", "",
                                 "NVIDIA Isaac Lab 3.0 GA, kit-less on Newton      NVIDIA Nemotron 3.5 Lightning and Super-VL",
                                 "Nebius Token Factory                               Apache-2.0, every record in results/"],
                   ("Everything in this video ran on one laptop GPU, except the shot from the Nebius H100. " if cloud else "Everything in this video ran on one laptop GPU. ")
                   + "The benchmark, its programs and the model calls are in the repository.", mono=False), 8)
    secs = enc.close()
    print(f"[demo] {secs:.0f} s -> {a.out}")


if __name__ == "__main__":
    main()
