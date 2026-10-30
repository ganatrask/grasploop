"""Vision reviewer: a VLM watches frames of an attempt and says what it saw, never told the verdict.

Default model is Nemotron-3.5-Super-VL on Token Factory (the only vision model served there on
2026-10-27; Cosmos 3 Reasoner left the serverless catalogue on 08-31). Any OpenAI-style
image-capable endpoint can be substituted through `model`.

Pieces:
  FrameRecorder  - hooks GraspEnv.on_step/on_reset, keeps one side-camera frame every `every`
                   steps and writes PNGs for the demo (agent/loop.py calls save() per attempt)
  review()       - sends up to `max_frames` evenly spaced frames + the task text, gets JSON back
  make_reviewer()- the callable agent/loop.run_scenario expects for feedback == 'vision'

Return of review(): {text, structured, valid_json, cost_usd, latency_s, n_frames, raw}
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil

import numpy as np

from agent.cameras import CAMERA_NAMES, RES, grab, save_png
from agent.nemotron import TokenFactory

REVIEW_SYSTEM = (
    "You are a robotic manipulation trial reviewer. You are shown frames, in time order, of a simulated "
    "robot arm attempting to grasp and lift an object from a table. Report only what the images support. "
    "Do not assume a grasp succeeded because the gripper closed or the object moved briefly. If the camera "
    "cannot establish something, say unknown.")

FAILURE_TYPES = ["none", "approach_off_target", "hand_too_high", "hand_too_low_or_collided", "fingers_misaligned_with_object",
                 "closed_on_nothing", "object_pushed_away", "object_slipped_during_lift", "object_dropped", "no_lift_attempted",
                 "unknown"]

REVIEW_TASK = (
    "Task given to the robot: pick up the {shape} ({size}) and hold it in the air.\n"
    "Frames are {n} snapshots of one attempt, oldest first, about {dt:.1f} s apart.\n"
    "Return JSON only, with exactly these keys:\n"
    '{{"visual_success": true|false|null, "confidence": 0-1, "approach_ok": true|false|null, '
    '"contact_visible": true|false|null, "lift_visible": true|false|null, "held_until_end": true|false|null, '
    '"failure_type": one of {types}, "evidence": "<one or two sentences on what is visible>", '
    '"suggested_correction": "<one concrete change to the robot program>", '
    '"visibility_limits": "<what the camera cannot establish>"}}')


# Walking robots: the same reviewer, a different task text and failure vocabulary. The frames come from the
# top-down camera, where the blue waypoint disc, the green goal disc and the robot are all in view.
REVIEW_SYSTEM_NAV = (
    "You are a robot locomotion trial reviewer. You are shown frames, in time order, of a simulated legged robot "
    "that was told to walk over a blue waypoint disc and then stop on a green goal disc. The frames are a top-down "
    "view; the robot is the small grey body. Report only what the images support. If the camera cannot establish "
    "something, say unknown.")

FAILURE_TYPES_NAV = ["none", "missed_waypoint", "stopped_short_of_goal", "overshot_goal", "wandered_or_circled", "fell",
                     "never_moved", "unknown"]

REVIEW_TASK_NAV = (
    "Task given to the robot: pass over the blue waypoint disc, then stop on the green goal disc, without falling.\n"
    "Frames are {n} snapshots of one attempt, oldest first, about {dt:.1f} s apart.\n"
    "Return JSON only, with exactly these keys:\n"
    '{{"visual_success": true|false|null, "confidence": 0-1, "waypoint_crossed": true|false|null, '
    '"on_goal_at_end": true|false|null, "fell": true|false|null, '
    '"failure_type": one of {types}, "evidence": "<one or two sentences on what is visible>", '
    '"suggested_correction": "<one concrete change to the robot program>", '
    '"visibility_limits": "<what the camera cannot establish>"}}')


# Pick-and-place: the grasp reviewer's vocabulary plus the placement, judged from the side camera.
FAILURE_TYPES_PLACE = FAILURE_TYPES[:-1] + ["released_off_target", "still_holding_at_end", "object_toppled", "unknown"]

REVIEW_TASK_PLACE = (
    "Task given to the robot: pick up the {shape} ({size}), carry it to the green target disc on the table, set it down "
    "on the disc and open the gripper.\n"
    "Frames are {n} snapshots of one attempt, oldest first, about {dt:.1f} s apart.\n"
    "Return JSON only, with exactly these keys:\n"
    '{{"visual_success": true|false|null, "confidence": 0-1, "lift_visible": true|false|null, '
    '"on_target_at_end": true|false|null, "gripper_open_at_end": true|false|null, '
    '"failure_type": one of {types}, "evidence": "<one or two sentences on what is visible>", '
    '"suggested_correction": "<one concrete change to the robot program>", '
    '"visibility_limits": "<what the camera cannot establish>"}}')


class FrameRecorder:
    """Keeps side-camera frames during an attempt for the reviewer (one every `every` steps, at RES), and
    with `video_dir` films both cameras to disk every `video_every` steps at whatever resolution the
    cameras were built with (VIDEO_RES through --video). Frames go to `video_dir/_recording_<pid>/` while the
    attempt runs and are moved to `video_dir/<tag>/` by save(), next to a meta.json with the step, time,
    object rise and gripper state of every frame. Clears on every env reset."""

    def __init__(self, genv, out_dir: str | None = None, every: int = 15, camera: str = "side_cam",
                 video_dir: str | None = None, video_every: int = 2, video_cameras=CAMERA_NAMES):
        self.genv, self.out_dir, self.every, self.camera = genv, out_dir, every, camera
        self.video_dir, self.video_every, self.video_cameras = video_dir, video_every, tuple(video_cameras)
        self.frames: list[np.ndarray] = []
        self.meta: list[dict] = []
        self.tag = "attempt"
        self.last_video: str | None = None
        self._n = 0
        genv.on_step = self.on_step
        genv.on_reset = self.start
        genv._recorder = self

    def _rec_dir(self) -> str:
        return os.path.join(self.video_dir, f"_recording_{os.getpid()}")  # per process: concurrent grids share a video dir

    def start(self):
        self.frames, self.meta, self._n = [], [], 0
        if self.video_dir:
            shutil.rmtree(self._rec_dir(), ignore_errors=True)
            for cam in self.video_cameras:
                os.makedirs(os.path.join(self._rec_dir(), cam), exist_ok=True)

    def _review_frame(self) -> np.ndarray:
        f = grab(self.genv.scene, self.camera)
        if f.shape[1] > RES[0]:  # cameras at video resolution: the reviewer still sees the pilot's 320x240
            from PIL import Image
            f = np.asarray(Image.fromarray(f).resize(RES, Image.BILINEAR))
        return f

    def _video_frame(self, step: int):
        for cam in self.video_cameras:
            save_png(grab(self.genv.scene, cam), os.path.join(self._rec_dir(), cam, f"frame_{self._n:06d}.png"))
        g = self.genv
        if hasattr(g, "metric"):
            rise = g.metric()
        else:
            rise = g.object_rise() if getattr(g, "object_start", None) is not None else 0.0  # None during reset's settle steps
        self.meta.append(dict(i=self._n, step=step, t=round(step * g.dt, 3), rise_m=round(rise, 4),
                              closed=bool(getattr(g, "gripper_closed", False))))
        self._n += 1

    def on_step(self, step: int):
        if step % self.every == 0:
            self.frames.append(self._review_frame())
        if self.video_dir and step % self.video_every == 0:
            self._video_frame(step)

    def final(self):
        self.frames.append(self._review_frame())
        if self.video_dir:
            self._video_frame(self.genv.steps)

    def save(self) -> list[str]:
        """Write the reviewer frames (if out_dir) and move the video frames under their tag. Returns the
        reviewer frame paths; the video directory is in `last_video`."""
        paths = []
        name = f"{self.genv.ROBOT}_{self.tag}"  # the robot is part of the directory name: both robots film the same tags
        if self.out_dir:
            paths = [save_png(f, os.path.join(self.out_dir, name, f"frame_{i:04d}.png")) for i, f in enumerate(self.frames)]
        self.last_video = None
        if self.video_dir and self.meta:
            dst = os.path.join(self.video_dir, name)
            shutil.rmtree(dst, ignore_errors=True)
            with open(os.path.join(self._rec_dir(), "meta.json"), "w") as f:
                json.dump(dict(tag=self.tag, cameras=list(self.video_cameras), frame_dt_s=self.video_every * self.genv.dt,
                               metric_name=getattr(self.genv, "METRIC_LABEL", "object rise"),
                               frames=self.meta), f)
            os.rename(self._rec_dir(), dst)
            self.last_video = dst
            self.meta, self._n = [], 0
        return paths


def attach_recorder(genv, args) -> "FrameRecorder | None":
    """The recorder a runner needs for its --cameras / --video arguments; None when neither is set."""
    video = getattr(args, "video", None)
    hero = getattr(args, "hero", None)
    if hero:  # demo footage: the hero camera and the side camera, 30 fps on the arms (every step), 25 on the walkers (every other)
        every = 2 if getattr(genv, "ROBOT", "") in ("go2", "g1") else 1
        return FrameRecorder(genv, out_dir=args.cameras, video_dir=hero, video_every=every, video_cameras=("hero_cam", "side_cam"))
    if not (args.cameras or video):
        return None
    return FrameRecorder(genv, out_dir=args.cameras, video_dir=video)


def _data_url(arr: np.ndarray) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", compress_level=3)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _pick(frames: list, k: int) -> list:
    if len(frames) <= k:
        return list(frames)
    idx = np.linspace(0, len(frames) - 1, k).round().astype(int)
    return [frames[i] for i in idx]


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def review(tf: TokenFactory, frames: list[np.ndarray], shape: str, size: str, frame_dt_s: float, max_frames: int = 8,
           tag: str = "review", nav: bool = False, mode: str | None = None, extra_note: str = "") -> dict:
    """mode 'grasp' (default), 'nav' or 'place' picks the task text and failure vocabulary; the JSON contract is the same.
    nav=True is the older spelling of mode='nav'."""
    picked = _pick(frames, max_frames)
    stride = max(1, len(frames) // max(1, len(picked)))
    mode = mode or ("nav" if nav else "grasp")
    nav = mode == "nav"
    system, task, types = {"nav": (REVIEW_SYSTEM_NAV, REVIEW_TASK_NAV, FAILURE_TYPES_NAV),
                           "place": (REVIEW_SYSTEM, REVIEW_TASK_PLACE, FAILURE_TYPES_PLACE)}.get(mode, (REVIEW_SYSTEM, REVIEW_TASK, FAILURE_TYPES))
    content = [{"type": "text", "text": task.format(shape=shape, size=size, n=len(picked), dt=frame_dt_s * stride,
                                                    types=json.dumps(types)) + (("\n" + extra_note) if extra_note else "")}]
    for i, f in enumerate(picked):
        content.append({"type": "text", "text": f"frame {i + 1} of {len(picked)}"})
        content.append({"type": "image_url", "image_url": {"url": _data_url(f)}})
    reply = tf.chat([{"role": "system", "content": system}, {"role": "user", "content": content}], max_tokens=1500, tag=tag)
    s = _parse_json(reply["content"])
    keys = {"nav": ("visual_success", "confidence", "waypoint_crossed", "on_goal_at_end", "fell"),
            "place": ("visual_success", "confidence", "lift_visible", "on_target_at_end", "gripper_open_at_end")}.get(
        mode, ("visual_success", "confidence", "approach_ok", "contact_visible", "lift_visible", "held_until_end"))
    norm = {k: s.get(k) for k in keys}
    ft = s.get("failure_type")
    norm["failure_type"] = ft if ft in types else ("unknown" if s else None)
    for k in ("evidence", "suggested_correction", "visibility_limits"):
        norm[k] = str(s.get(k, ""))[:400] if s else ""
    text = ""
    if s:
        outcome = "success" if norm["visual_success"] else "failure" if norm["visual_success"] is False else "unclear"
        text = (f"visible outcome: {outcome}; failure type: {norm['failure_type']}. Evidence: {norm['evidence']} "
                f"Suggested change: {norm['suggested_correction']}")
    return dict(text=text, structured=norm, valid_json=bool(s), cost_usd=reply["cost_usd"], latency_s=reply["latency_s"],
                n_frames=len(picked), raw=reply["content"][:1500])


def make_reviewer(usage_log: str | None, model: str = "super_vl"):
    """Build the callable agent/loop.run_scenario calls: reviewer(genv, run, verdict, attempt) -> dict.
    Frames come from the FrameRecorder attached to the env (genv._recorder)."""
    tf = TokenFactory(model, usage_log=usage_log, temperature=0.1, max_tokens=1500, extra={"reasoning_effort": "none"})
    tf.check_model()

    def reviewer(genv, run, verdict, attempt):
        rec = getattr(genv, "_recorder", None)
        if rec is None or not rec.frames:
            return dict(text="", structured={}, valid_json=False, cost_usd=0.0, n_frames=0, raw="no frames recorded")
        ext = genv.extent["size_xyz"]
        return review(tf, rec.frames, genv.shape, f"{ext[0] * 100:.1f} x {ext[1] * 100:.1f} x {ext[2] * 100:.1f} cm",
                      frame_dt_s=rec.every * genv.dt, tag=f"review:a{attempt}")

    reviewer.tf = tf
    return reviewer
