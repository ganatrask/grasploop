"""Pick-and-place on the Franka lift scene: the same grasp API plus get_target(); success is the object
resting within PLACE_RADIUS of a target marker on the table with the gripper open. Reached through
agent.env (create_env) when --task is place. Everything else (sandbox, loop, recorder, grid) is shared.
"""
from __future__ import annotations

import math
import random

from agent.env import OBJECT_XY_HOME, TABLE_TOP, GraspEnv
from agent.loop import feedback_text as grasp_feedback_text

PLACE_RADIUS = 0.03
MARKER_RADIUS, MARKER_H = 0.06, 0.006


def target_marker_cfg():
    """A thin disc on the table; colliding because the Warp renderer draws only colliding shapes."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import RigidObjectCfg
    from isaaclab_physx.sim.schemas import PhysxRigidBodyCfg

    return RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Target",
        spawn=sim_utils.MeshCylinderCfg(radius=MARKER_RADIUS, height=MARKER_H,
                                        rigid_props=PhysxRigidBodyCfg(solver_position_iteration_count=4, solver_velocity_iteration_count=0),
                                        mass_props=sim_utils.MassCfg(mass=0.3),
                                        collision_props=sim_utils.CollisionPropertiesCfg(),
                                        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.1, 0.75, 0.25))),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(OBJECT_XY_HOME[0] - 0.18, OBJECT_XY_HOME[1], TABLE_TOP + MARKER_H / 2)))


class PlaceEnv(GraspEnv):
    TASK = "Pick up the object and set it down on the green target marker, then let go of it."
    SUCCESS_TEXT = (f"Success: the object rests on the table within {PLACE_RADIUS:.2f} m of the target marker's centre, "
                    "with the gripper open and not touching it.")
    METRIC_LABEL = "dist to target"

    def __init__(self, env, shape: str):
        super().__init__(env, shape)
        self.SCENARIO = f"place_{shape}"
        self.marker = self.scene["target"]
        self.target = None
        self._rest_z = None

    def reset(self, seed: int, xy_jitter: float = 0.05, yaw_deg=None):
        info = super().reset(seed, xy_jitter, yaw_deg)
        torch = self._torch
        rng = random.Random(seed + 7919)
        ox, oy = self.object_start[0], self.object_start[1]
        for _ in range(50):  # a spot 15-22 cm from the object, inside the workspace
            ang, dist = rng.uniform(-math.pi, math.pi), rng.uniform(0.15, 0.22)
            tx, ty = ox + dist * math.cos(ang), oy + dist * math.sin(ang)
            if -0.75 <= tx <= -0.38 and -0.25 <= ty <= 0.25:
                break
        self.target = dict(x=round(tx, 4), y=round(ty, 4), z=round(TABLE_TOP + MARKER_H, 4))
        pose = torch.tensor([[tx, ty, TABLE_TOP + MARKER_H / 2, 0.0, 0.0, 0.0, 1.0]], device=self.device)
        pose[:, :3] += self.scene.env_origins[:1]
        self.marker.write_root_pose_to_sim_index(root_pose=pose)
        self.marker.write_root_velocity_to_sim_index(root_velocity=torch.zeros(1, 6, device=self.device))
        for _ in range(10):
            self.step()
        self._rest_z = float(self.object_pose()[0][2])
        info["target"] = dict(self.target)
        return info

    def target_dist(self) -> float:
        p = self.object_pose()[0]
        return math.hypot(float(p[0]) - self.target["x"], float(p[1]) - self.target["y"])

    def metric(self) -> float:
        return self.target_dist() if self.target else 0.0

    def judge(self, run: dict) -> dict:
        """Let everything settle, then: lifted at some point, resting on the table within the radius, released."""
        self.wait(1.0)
        trace = run.get("trace", [])
        max_rise = max([r["rise_m"] for r in trace] + [self.object_rise()])
        p = self.object_pose()[0]
        d, z = self.target_dist(), float(p[2])
        held = self.gripper_closed and any(self.contacts().values())
        out = dict(success=False, failure=None, final_dist_m=round(d, 4), max_rise_m=round(max_rise, 4), final_rise_m=round(self.object_rise(), 4),
                   gripper_closed=self.gripper_closed, contacts=self.contacts(), n_calls=len(trace), target=dict(self.target), detail="")
        if run["status"] == "invalid":
            out.update(failure="invalid_program", detail="; ".join(run["problems"]))
        elif run["status"] in ("error", "timeout"):
            out.update(failure="program_error", detail=str(run["exception"]))
        elif run["status"] == "budget":
            out.update(failure="budget_exhausted", detail=str(run["exception"]))
        elif z < TABLE_TOP - 0.05:
            out.update(failure="object_off_table")
        elif max_rise < 0.03:
            out.update(failure="never_lifted", detail=f"peak rise {max_rise:.3f} m")
        elif held:
            out.update(failure="still_holding", detail=f"the gripper is still closed on the object, {d:.3f} m from the target")
        elif d > PLACE_RADIUS:
            dx, dy = float(p[0]) - self.target["x"], float(p[1]) - self.target["y"]
            out.update(failure="placed_off_target", detail=f"the object rests {d:.3f} m from the target centre (needs < {PLACE_RADIUS} m): "
                                                          f"{abs(dx) * 100:.1f} cm {'further from' if dx < 0 else 'closer to'} the robot, "
                                                          f"{abs(dy) * 100:.1f} cm to the {'left' if dy > 0 else 'right'}")
        elif abs(z - self._rest_z) > 0.03:
            out.update(failure="not_resting", detail=f"object height {z - self._rest_z:+.3f} m from its resting height")
        else:
            out.update(success=True, detail=f"rests {d:.3f} m from the target, released")
        return out

    def feedback_text(self, run: dict, verdict: dict, attempt: int, max_attempts: int) -> str:
        base = grasp_feedback_text(run, verdict, attempt, max_attempts)
        lines = [ln for ln in base.splitlines() if not ln.startswith("At the end:")]  # that line states the lift criterion
        end = (f"At the end: the object rests {verdict['final_dist_m']} m from the target marker's centre at "
               f"({self.target['x']}, {self.target['y']}, {self.target['z']}) (needs < {PLACE_RADIUS} m), peak rise during the run "
               f"{verdict['max_rise_m']} m, gripper {'closed' if verdict['gripper_closed'] else 'open'}, fingertips touching {verdict['contacts']}.")
        i = next(k for k, ln in enumerate(lines) if ln.startswith("Fix the program."))
        return "\n".join(lines[:i] + [end] + lines[i:])


REFERENCE_PROGRAM_PLACE = """
# hand-written reference: top-down grasp across the narrow side, carry above the target, set down, release
obj = get_object()
x, y, z = obj["pos"]
sx, sy, sz = obj["size_xyz"]
tgt = get_target()
tx, ty, tz = tgt["pos"]
yaw = obj["yaw_deg"] - 90.0 if sx <= sy else obj["yaw_deg"]
yaw = ((yaw + 90.0) % 180.0) - 90.0
gz = z - 0.015 if sz <= 0.07 else z + sz / 2 - 0.035
dz = gz - z  # keep the same grip height relative to the object when setting it down
open_gripper()
move_to([x, y, gz + 0.12], quat=yaw_quat(yaw))
move_to([x, y, gz], quat=yaw_quat(yaw))
close_gripper()
lift(0.15)
move_to([tx, ty, gz + 0.15], quat=yaw_quat(yaw))
move_to([tx, ty, tz + sz / 2 + dz + 0.005], quat=yaw_quat(yaw))
open_gripper()
lift(0.12)
wait(0.5)
log(f"object {get_object()['pos']} target {tgt['pos']}")
"""
