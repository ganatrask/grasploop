"""The manipulation API that generated programs call. One class, 12 calls, every call traced.

api_doc() below builds the text Nemotron is shown, next to the implementation it describes. Frames: world, metres, quaternions (x, y, z, w). The robot stands at the origin and
the table is at negative x; "hand down" is the default orientation.
"""
from __future__ import annotations

import time

from agent.env import TABLE_TOP, GraspEnv

WORKSPACE = dict(x=(-0.85, -0.25), y=(-0.40, 0.40), z=(TABLE_TOP - 0.005, TABLE_TOP + 0.55))

_DOC_HEAD = """
You control a robot arm with {hand} in a physics simulation. Units: metres, seconds. Frame: world.
Quaternions are (x, y, z, w). The table top is at z = {table:.3f}. The workspace is x in {wx}, y in {wy},
z in ({wz0:.3f}, {wz1:.3f}). The hand points straight down by default.

Functions (already defined; do not import anything):
  get_object() -> dict with keys: shape (str), size_xyz [sx, sy, sz] at yaw 0, narrow_width,
                  pos [x, y, z] (centre), yaw_deg (rotation about z), half_height
  ee_pose() -> dict: pos [x, y, z] of the grasp point, quat [x, y, z, w]
  move_to(pos, quat=None, timeout=4.0) -> dict: reached (bool), error_m, orient_err_deg, steps.
                  Moves the grasp point (the point between the fingertips) to pos. quat=None keeps the
                  hand pointing down.
  yaw_quat(yaw_deg) -> quat [x, y, z, w] for a downward-pointing hand rotated yaw_deg about z.
                  Keep yaw_deg within [-90, 90] (wrist limit).
  lift(dz, timeout=4.0) -> dict: moves the grasp point straight up by dz
  wait(seconds) -> None: let the simulation run
  object_height() -> float: how far the object centre has risen from its start (0 at start)
  fingers_in_contact() -> dict of finger name -> bool: fingertip touching the object
  log(message) -> None: write a note into the trace for the reviewer
"""
_DOC_FRANKA_HAND = """  open_gripper() -> None: opens the gripper fully (takes ~0.6 s)
  close_gripper() -> None: closes the gripper on whatever is between the fingers (~0.6 s)
  gripper_width() -> float: current opening in metres
"""
_DOC_ALLEGRO_HAND = """  grasp(kind, closure) -> None: shape the hand. kind is "power" (all fingers curl against the thumb),
                  "pinch" (index against thumb) or "tripod" (index + middle against thumb);
                  closure 0.0 is fully open, 1.0 fully closed. Takes ~0.8 s.
  open_gripper() -> None: same as grasp(current kind, 0.0)
  close_gripper() -> None: same as grasp(current kind, 1.0)
  gripper_width() -> float: current closure, 0 (open) .. 1 (closed)
  Note: this wrist reaches hand-down yaws only within about [-45, 45] deg; beyond that move_to reports
  reached=False. A cube or box looks the same every 90 deg, so fold the yaw into that range.
"""
_DOC_TAIL = """
Success: the object rises by at least 0.10 m and stays there for 0.5 s with the hand closed.
Write plain Python using only these functions, plus math. No imports, no classes, no while loops.
"""


def api_doc(genv: GraspEnv) -> str:
    """The API text shown to the model for this robot: the same functions, the robot's own hand."""
    ws = getattr(genv, "WORKSPACE", WORKSPACE)
    hand = _DOC_ALLEGRO_HAND if genv.ROBOT == "allegro" else _DOC_FRANKA_HAND
    if getattr(genv, "target", None) is not None:
        hand += "  get_target() -> dict: pos [x, y, z] of the target marker's centre on the table, radius\n"
    if hasattr(genv, "SUCCESS_TEXT"):
        return (_DOC_HEAD.format(hand=genv.HAND_DESC, table=TABLE_TOP, wx=ws["x"], wy=ws["y"],
                                 wz0=ws["z"][0], wz1=ws["z"][1]) + hand
                + _DOC_TAIL.replace(_DOC_TAIL.strip().splitlines()[0], genv.SUCCESS_TEXT))
    return (_DOC_HEAD.format(hand=genv.HAND_DESC, table=TABLE_TOP, wx=ws["x"], wy=ws["y"],
                             wz0=ws["z"][0], wz1=ws["z"][1]) + hand + _DOC_TAIL)


API_DOC = (_DOC_HEAD.format(hand=GraspEnv.HAND_DESC, table=TABLE_TOP, wx=WORKSPACE["x"], wy=WORKSPACE["y"],
                            wz0=WORKSPACE["z"][0], wz1=WORKSPACE["z"][1]) + _DOC_FRANKA_HAND + _DOC_TAIL)


def _qmul(a, b):
    """xyzw quaternion product a * b."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]

class BudgetExceeded(RuntimeError):
    pass


class GraspAPI:
    """Bound to one GraspEnv episode. `namespace()` returns the names handed to exec()."""

    SIM_BUDGET_S = 30.0

    def __init__(self, genv: GraspEnv, step_budget: int | None = None, wall_budget_s: float = 120.0):
        self.g = genv
        self.step_budget = step_budget or int(self.SIM_BUDGET_S / genv.dt)  # 30 s of simulated time at any control rate
        self.wall_budget_s = wall_budget_s
        self.t0 = time.time()
        self.trace: list[dict] = []

    # ---- bookkeeping -----------------------------------------------------------------------
    def _rec(self, call: str, args: dict, result):
        p = self.g.object_pose()[0]
        moved = float((p[:2] - self.g._torch.tensor(self.g.object_start[:2], device=p.device)).norm())
        self.trace.append(dict(t=round(self.g.steps * self.g.dt, 2), step=self.g.steps, call=call, args=args,
                               result=result, rise_m=round(self.g.object_rise(), 4), moved_xy_m=round(moved, 4),
                               contacts=self.g.contacts()))
        return result

    def _check_budget(self):
        if self.g.steps > self.step_budget:
            raise BudgetExceeded(f"simulation budget of {self.step_budget} steps ({self.step_budget * self.g.dt:.0f} s) used up")
        if time.time() - self.t0 > self.wall_budget_s:
            raise BudgetExceeded(f"wall-clock budget of {self.wall_budget_s:.0f} s used up")

    def _vec3(self, v, name):
        try:
            x, y, z = (float(c) for c in v)
        except Exception:
            raise ValueError(f"{name} must be three numbers [x, y, z], got {v!r}")
        ws = getattr(self.g, "WORKSPACE", WORKSPACE)
        for axis, val in zip("xyz", (x, y, z)):
            lo, hi = ws[axis]
            if not (lo <= val <= hi):
                raise ValueError(f"{name}.{axis}={val:.3f} is outside the workspace {axis} in [{lo}, {hi}]")
        return [x, y, z]

    # ---- the API ---------------------------------------------------------------------------
    def get_object(self) -> dict:
        import math
        p, _ = self.g.object_pose()
        return self._rec("get_object", {}, dict(shape=self.g.shape, **self.g.extent, pos=[round(c, 4) for c in p.tolist()],
                                                yaw_deg=round(self.g.object_yaw_deg(), 1)))

    def ee_pose(self) -> dict:
        p, q = self.g.ee_pose()
        return self._rec("ee_pose", {}, dict(pos=[round(c, 4) for c in p.tolist()], quat=[round(c, 4) for c in q.tolist()]))

    def yaw_quat(self, yaw_deg: float) -> list:
        import math
        # the robot's hand-down orientation, then yaw about world z: q = qz(yaw) * HAND_DOWN
        h = math.radians(float(yaw_deg)) / 2
        return [round(c, 6) for c in _qmul([0.0, 0.0, math.sin(h), math.cos(h)], list(self.g.HAND_DOWN))]

    def grasp(self, kind: str = "power", closure: float = 1.0) -> None:
        self._check_budget()
        self.g.set_hand(str(kind), float(closure))
        return self._rec("grasp", dict(kind=str(kind), closure=float(closure)), dict(contacts=self.g.contacts()))

    def move_to(self, pos, quat=None, timeout: float = 3.0) -> dict:
        self._check_budget()
        pos = self._vec3(pos, "pos")
        if quat is not None:
            quat = [float(c) for c in quat]
            if len(quat) != 4:
                raise ValueError("quat must be [x, y, z, w]")
        timeout = max(0.1, min(float(timeout), 10.0))
        r = self.g.move_to(pos, quat, timeout_s=timeout, tol_deg=getattr(self.g, "TOL_DEG", 4.0))
        return self._rec("move_to", dict(pos=pos, quat=quat, timeout=timeout), r)

    def lift(self, dz: float, timeout: float = 3.0) -> dict:
        self._check_budget()
        p, q = self.g.ee_pose()
        target = p.tolist()
        target[2] += float(dz)
        target = self._vec3(target, "lift target")
        r = self.g.move_to(target, q.tolist(), timeout_s=max(0.1, min(float(timeout), 10.0)), tol_deg=getattr(self.g, "TOL_DEG", 4.0))
        return self._rec("lift", dict(dz=float(dz)), r)

    def open_gripper(self) -> None:
        self._check_budget()
        self.g.set_gripper(False)
        return self._rec("open_gripper", {}, dict(width=round(self.g.gripper_width(), 4)))

    def close_gripper(self) -> None:
        self._check_budget()
        self.g.set_gripper(True)
        tip_t, obj_t = self.g.ee_pose()[0], self.g.object_pose()[0]
        tip = [round(c, 3) for c in tip_t.tolist()]
        obj = [round(c, 3) for c in obj_t.tolist()]
        # where the fingers closed relative to the object, so the feedback can say it in words
        d = (tip_t - obj_t).tolist()
        geom = dict(dz_m=round(d[2], 3), dxy_m=round((d[0] ** 2 + d[1] ** 2) ** 0.5, 3),
                    object_top_z=round(obj[2] + self.g.extent["half_height"], 3),
                    palm_z=round(float(self.g.palm_pos()[2]), 3))
        return self._rec("close_gripper", {}, dict(width=round(self.g.gripper_width(), 4), contacts=self.g.contacts(),
                                                   fingertip_pos=tip, object_pos=obj, **geom))

    def get_target(self) -> dict:
        t = self.g.target
        return self._rec("get_target", {}, dict(pos=[t["x"], t["y"], t["z"]], radius=0.03))

    def wait(self, seconds: float) -> None:
        self._check_budget()
        seconds = max(0.0, min(float(seconds), 5.0))
        self.g.wait(seconds)
        return self._rec("wait", dict(seconds=seconds), None)

    def object_height(self) -> float:
        return self._rec("object_height", {}, round(self.g.object_rise(), 4))

    def fingers_in_contact(self) -> dict:
        return self._rec("fingers_in_contact", {}, self.g.contacts())

    def gripper_width(self) -> float:
        return self._rec("gripper_width", {}, round(self.g.gripper_width(), 4))

    def log(self, message) -> None:
        return self._rec("log", dict(message=str(message)[:300]), None)

    def namespace(self) -> dict:
        import math
        names = ["get_object", "ee_pose", "yaw_quat", "move_to", "lift", "open_gripper", "close_gripper", "wait",
                 "object_height", "fingers_in_contact", "gripper_width", "log"]
        if hasattr(self.g, "set_hand"):
            names.append("grasp")
        if getattr(self.g, "target", None) is not None:
            names.append("get_target")
        ns = {n: getattr(self, n) for n in names}
        ns["math"] = math
        ns["HAND_DOWN"] = list(self.g.HAND_DOWN)
        return ns


REFERENCE_PROGRAM_ALLEGRO = """
# hand-written reference for the Allegro hand (sweep 2026-10-27, cube 3/5): square the hand to the
# object's faces within the wrist's range, come down over it, fingertips a little below the centre,
# close in two stages so the fingers wrap instead of flicking the object, lift
obj = get_object()
x, y, z = obj["pos"]
yaw = ((obj["yaw_deg"] + 45.0) % 90.0) - 45.0
q = yaw_quat(yaw)
grasp("power", 0.0)
move_to([x, y, z + 0.15], quat=q)
move_to([x, y, z - 0.015], quat=q)
grasp("power", 0.5)
wait(0.3)
grasp("power", 1.0)
lift(0.15)
wait(0.6)
log(f"height {object_height():.3f} contacts {fingers_in_contact()}")
"""

REFERENCE_PROGRAM = """
# hand-written reference: top-down grasp across the object's narrow side
obj = get_object()
x, y, z = obj["pos"]
sx, sy, sz = obj["size_xyz"]
# fingers close along world y at yaw 0; the object's narrow axis is its x (if sx <= sy) or y axis,
# rotated by the object's yaw. Point the closing axis along it, staying within the wrist range.
yaw = obj["yaw_deg"] - 90.0 if sx <= sy else obj["yaw_deg"]
yaw = ((yaw + 90.0) % 180.0) - 90.0  # same closing axis every 180 deg; stay inside the wrist range
# grasp height: slightly below the centre so the pads sit around the lower half; on an object taller than
# the fingers (palm face 4.9 cm above the fingertips) grasp 3.5 cm below the top instead, or the palm lands on it
gz = z - 0.015 if sz <= 0.07 else z + sz / 2 - 0.035
open_gripper()
move_to([x, y, gz + 0.12], quat=yaw_quat(yaw))
move_to([x, y, gz], quat=yaw_quat(yaw))
close_gripper()
lift(0.15)
wait(0.6)
log(f"height {object_height():.3f} contacts {fingers_in_contact()}")
"""

REFERENCE_PROGRAMS = {"franka": REFERENCE_PROGRAM, "allegro": REFERENCE_PROGRAM_ALLEGRO}
