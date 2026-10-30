"""Review cameras on NVIDIA's Warp ray tracer: no GL, no EGL, works with --viz none and in a
compute-only container. One fixed external camera looking at the table from the side
of the robot, one from the front. Frames are what the vision reviewer and the demo video see.

Callers: agent/env.py (add_cameras, at config time), judges/vision.py and eval/* (grab).
"""
from __future__ import annotations

import os

import numpy as np

RES = (320, 240)  # (width, height): small enough for cheap image tokens, large enough to see the pads
VIDEO_RES = (640, 480)  # --video: both cameras at this size, composed side by side (1280x480) by eval/make_videos.py

# (eye, target) in world metres. The table centre is at x=-0.55, top z=0.255; the robot at the origin.
SIDE_CAM = dict(eye=(-0.55, 0.55, 0.48), target=(-0.55, 0.0, 0.29), up=(0.0, 0.0, 1.0), focal_length=24.0)
FRONT_CAM = dict(eye=(-1.10, 0.0, 0.50), target=(-0.55, 0.0, 0.29), up=(0.0, 0.0, 1.0), focal_length=24.0)

# Hero camera for demo footage (--hero): a three-quarter view from the front-right, slightly elevated, rendered by
# NVIDIA's OVRTX path tracer at HERO_RES. The review cameras stay on the Warp ray tracer: the reviewer's frames
# are part of the frozen method, the hero footage is for people. Probe 2026-10-29: 78 ms per 1280x720 frame.
HERO_RES = (1280, 720)
HERO_CAM = dict(eye=(-1.30, -0.80, 0.75), target=(-0.52, 0.0, 0.33), up=(0.0, 0.0, 1.0), focal_length=30.0)
# the Kuka iiwa + Allegro reaches the table from higher up and further back: pull the camera out so the hand stays in frame
HERO_CAM_ALLEGRO = dict(eye=(-1.55, -1.05, 1.00), target=(-0.50, 0.0, 0.42), up=(0.0, 0.0, 1.0), focal_length=28.0)
HERO_CAM_NAME = "hero_cam"


def look_at_quat(eye, target, up) -> tuple[float, float, float, float]:
    """xyzw rotation of a 'world'-convention camera frame (x forward, z up) looking from eye at target."""
    from scipy.spatial.transform import Rotation

    f = np.subtract(target, eye).astype(float)
    f /= np.linalg.norm(f)
    left = np.cross(up, f)
    left /= np.linalg.norm(left)
    u = np.cross(f, left)
    return tuple(float(v) for v in Rotation.from_matrix(np.stack([f, left, u], axis=1)).as_quat())


def camera_cfg(name: str, spec: dict, res=RES, renderer_cfg=None):
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg
    from isaaclab_newton.renderers import NewtonWarpRendererCfg

    if renderer_cfg is None:
        renderer_cfg = NewtonWarpRendererCfg()
    return CameraCfg(
        prim_path="{ENV_REGEX_NS}/" + name,
        offset=CameraCfg.OffsetCfg(pos=tuple(spec["eye"]), rot=look_at_quat(spec["eye"], spec["target"], spec["up"]),
                                   convention="world"),
        data_types=["rgb"], width=res[0], height=res[1],
        update_period=0.0,  # lazy: a frame renders only when the output is read
        update_latest_camera_pose=True,
        spawn=sim_utils.PinholeCameraCfg(focal_length=spec["focal_length"], clipping_range=(0.01, 10.0)),
        renderer_cfg=renderer_cfg,
    )


def hero_camera_cfg(spec: dict = HERO_CAM, res=HERO_RES, renderer: str = "ovrtx"):
    """The demo camera: OVRTX path tracer (shadows, ambient occlusion, materials) or the Warp tracer with shadows."""
    if renderer == "ovrtx":
        from isaaclab_ov.renderers import OVRTXRendererCfg
        rcfg = OVRTXRendererCfg()
    else:
        from isaaclab_newton.renderers import NewtonWarpRendererCfg
        rcfg = NewtonWarpRendererCfg(enable_shadows=True)
    return camera_cfg("HeroCam", spec, res, renderer_cfg=rcfg)


def add_cameras(scene_cfg, res=RES) -> None:
    """Attach the review cameras to an InteractiveSceneCfg (call before the env is built)."""
    scene_cfg.side_cam = camera_cfg("SideCam", SIDE_CAM, res)
    scene_cfg.front_cam = camera_cfg("FrontCam", FRONT_CAM, res)


CAMERA_NAMES = ("side_cam", "front_cam")


def grab(scene, name: str = "side_cam") -> np.ndarray:
    """One RGB frame (H, W, 3) uint8 from a scene camera; reading the output triggers the render."""
    rgb = scene[name].data.output["rgb"]
    rgb = rgb.torch[0] if hasattr(rgb, "torch") else rgb[0]
    arr = rgb.detach().cpu().numpy()
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8) if arr.max() <= 1.0 else arr.astype(np.uint8)
    return arr[..., :3]


def save_png(arr: np.ndarray, path: str) -> str:
    from PIL import Image

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Image.fromarray(arr).save(path, compress_level=1)
    return path
