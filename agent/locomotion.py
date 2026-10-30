"""Quadruped and humanoid navigation on NVIDIA's kit-less Newton velocity tasks
(Isaac-Velocity-Flat-UnitreeGo2, Isaac-Velocity-Flat-G1). NVIDIA's RSL-RL policy, trained with NVIDIA's
own train.py on this laptop (Go2 8 min, G1 36 min; eval/train_walkers.sh), is the low-level controller. The program
Nemotron writes drives it through walk(vx, vy, wz, seconds); the judge checks the waypoint and the goal.
Same loop, same sandbox, same recorder and clips as the arms: the robot supplies its API, judge,
reference program and feedback wording through the hooks agent/loop.py looks for.

Reached through agent.env (make_env_cfg_from_args / create_env) when --robot is go2 or g1.
"""
from __future__ import annotations

import glob
import math
import os
import re
import time

ISAACLAB = os.path.expanduser("~/workspace/isaaclab-3.0.0-ga")
ROBOTS = {
    "go2": dict(task="Isaac-Velocity-Flat-UnitreeGo2", experiment="unitree_go2_flat", min_height=0.18,
                desc="a Unitree Go2 quadruped", vx=(-0.8, 1.0), vy=(-0.5, 0.5), wz=(-1.0, 1.0)),
    "g1": dict(task="Isaac-Velocity-Flat-G1", experiment="g1_flat", min_height=0.45,
               desc="a Unitree G1 humanoid", vx=(-0.5, 0.8), vy=(-0.3, 0.3), wz=(-0.8, 0.8)),
}
LOCO_ROBOTS = tuple(ROBOTS)
GOAL_RADIUS, WAY_RADIUS, ARENA_RADIUS = 0.5, 0.6, 8.0
STEP_BUDGET, WALL_BUDGET_S = 3000, 180.0  # 60 s of simulated walking at 50 Hz
HIGH_CAM = dict(eye=(-2.6, -0.9, 1.3), target=(0.0, 0.0, 0.3), up=(0.0, 0.0, 1.0), focal_length=18.0)  # initial; follows the robot
TOP_CAM = dict(eye=(0.0, 0.0, 6.0), target=(0.001, 0.0, 0.0), up=(1.0, 0.0, 0.0), focal_length=14.0)  # initial; follows the robot
HERO_CHASE_CAM = dict(eye=(-2.4, -1.4, 1.0), target=(0.0, 0.0, 0.35), up=(0.0, 0.0, 1.0), focal_length=28.0)  # --hero: lower, closer, follows
_AGENT_CFGS: dict = {}


def latest_checkpoint(robot: str) -> str:
    """Newest run of NVIDIA's training script for this robot, highest model number; or GRASPLOOP_POLICY_<ROBOT>."""
    env_path = os.environ.get(f"GRASPLOOP_POLICY_{robot.upper()}")
    if env_path:
        return env_path
    root = os.path.join(ISAACLAB, "logs", "rsl_rl", ROBOTS[robot]["experiment"])
    runs = sorted(glob.glob(os.path.join(root, "*")), key=os.path.getmtime)
    for run in reversed(runs):
        cks = glob.glob(os.path.join(run, "model_*.pt"))
        if cks:
            return max(cks, key=lambda p: int(re.findall(r"model_(\d+)", p)[0]))
    raise FileNotFoundError(f"no RSL-RL checkpoint under {root}: train with NVIDIA's train.py first")


def make_loco_env_cfg(robot: str, cameras: bool = False, camera_res=None):
    """NVIDIA's velocity task config in play mode, one env, no RL time-out or fall reset (we judge those),
    a fixed command we overwrite, goal and waypoint markers, review cameras."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import RigidObjectCfg
    from isaaclab_physx.sim.schemas import PhysxRigidBodyCfg
    from isaaclab_tasks.utils import resolve_task_config
    from isaaclab_tasks.utils.hydra import resolve_presets

    from agent.cameras import RES, camera_cfg

    import sys
    argv, sys.argv = sys.argv, sys.argv[:1]  # resolve_task_config parses sys.argv for preset overrides and rejects ours
    try:
        env_cfg, agent_cfg = resolve_task_config(ROBOTS[robot]["task"], "rsl_rl_cfg_entry_point", play_mode=True)
    finally:
        sys.argv = argv
    _AGENT_CFGS[robot] = agent_cfg
    env_cfg.scene.num_envs = 1
    env_cfg.episode_length_s = 1.0e4  # our step budget ends an episode, not the RL time-out
    env_cfg.terminations.base_contact = None  # a fall is a verdict, not a reset
    env_cfg.commands.base_velocity.heading_command = False
    env_cfg.commands.base_velocity.resampling_time_range = (1.0e4, 1.0e4)
    for name in ("push_robot", "base_external_force_torque", "add_base_mass"):  # no random shoves during a trial
        if hasattr(env_cfg.events, name):
            setattr(env_cfg.events, name, None)

    def marker(name, colour, pos):
        return RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/" + name,
            # a 6 mm disc: the robot tripped over a 2 cm one (gate 2026-10-28), and a collision-free marker is
            # not drawn by the Warp renderer at all, so thin and colliding it is
            spawn=sim_utils.MeshCylinderCfg(radius=0.35, height=0.006,
                                            rigid_props=PhysxRigidBodyCfg(solver_position_iteration_count=4, solver_velocity_iteration_count=0),
                                            mass_props=sim_utils.MassCfg(mass=0.5),
                                            collision_props=sim_utils.CollisionPropertiesCfg(),
                                            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=colour)),
            init_state=RigidObjectCfg.InitialStateCfg(pos=pos))

    env_cfg.scene.goal_marker = marker("Goal", (0.1, 0.8, 0.2), (3.0, 0.0, 0.004))
    env_cfg.scene.way_marker = marker("Waypoint", (0.2, 0.4, 0.95), (1.5, 1.0, 0.004))
    if cameras:
        res = camera_res or RES
        env_cfg.scene.side_cam = camera_cfg("SideCam", HIGH_CAM, res)
        env_cfg.scene.front_cam = camera_cfg("FrontCam", TOP_CAM, res)
    return resolve_presets(env_cfg)


def _yaw_deg(q):
    x, y, z, w = (float(c) for c in q)
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _wrap(deg: float) -> float:
    return ((deg + 180.0) % 360.0) - 180.0


class LocoEnv:
    """One robot driven by its trained policy; the program sets the velocity command."""

    HAND_DESC = ""
    METRIC_LABEL = "dist to goal"

    def __init__(self, rl_env, robot: str, policy_path: str | None = None):
        import torch
        from isaaclab.utils import math as math_utils
        from isaaclab_rl.rsl_rl.utils import check_rsl_rl_version, create_rsl_rl_runner, handle_deprecated_rsl_rl_cfg
        from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper

        self.ROBOT, self.spec = robot, ROBOTS[robot]
        self.shape = self.SCENARIO = "nav"  # the scenario family: tags, records and prompts use it where the arms use the object shape
        self.TASK = ("Walk to the goal marker and stop on it, passing over the waypoint marker on the way. "
                     "Stay upright.")
        self.env, self.scene, self.device = rl_env, rl_env.scene, rl_env.device
        self.robot = rl_env.scene["robot"]
        self.dt = rl_env.step_dt
        self._torch, self._mu = torch, math_utils
        agent_cfg = handle_deprecated_rsl_rl_cfg(_AGENT_CFGS[robot], check_rsl_rl_version())  # as NVIDIA's play backend does
        self.wrapped = RslRlVecEnvWrapper(rl_env, clip_actions=agent_cfg.clip_actions)
        runner = create_rsl_rl_runner(self.wrapped, agent_cfg)
        self.policy_path = policy_path or latest_checkpoint(robot)
        runner.load(self.policy_path)
        self.policy = runner.get_inference_policy(device=self.device)
        self.cmd_term = rl_env.command_manager.get_term("base_velocity")
        self.obs = None
        self.steps, self.fell, self.way_passed, self.way_min = 0, False, False, float("inf")
        self.goal = self.way = None
        self.cmd = (0.0, 0.0, 0.0)
        self.on_step = None  # recorder hooks, as GraspEnv
        self.on_reset = None
        self.gripper_closed = False  # the recorder reads it; meaningless here
        self.object_start = None

    # ---- state --------------------------------------------------------------------------------
    def pose(self) -> dict:
        p = self.robot.data.root_link_pos_w.torch[0] - self.scene.env_origins[0]
        q = self.robot.data.root_link_quat_w.torch[0]
        return dict(x=round(float(p[0]), 3), y=round(float(p[1]), 3), z=round(float(p[2]), 3), heading_deg=round(_yaw_deg(q), 1))

    def dist(self, target) -> float:
        p = self.pose()
        return math.hypot(target["x"] - p["x"], target["y"] - p["y"])

    def bearing(self, target) -> float:
        p = self.pose()
        return math.degrees(math.atan2(target["y"] - p["y"], target["x"] - p["x"]))

    def metric(self) -> float:
        return self.dist(self.goal) if self.goal else 0.0

    def object_rise(self) -> float:  # recorder compatibility
        return self.metric()

    # ---- control --------------------------------------------------------------------------------
    def set_command(self, vx: float, vy: float, wz: float):
        s = self.spec
        vx, vy, wz = (max(lo, min(hi, float(v))) for v, (lo, hi) in ((vx, s["vx"]), (vy, s["vy"]), (wz, s["wz"])))
        self.cmd = (vx, vy, wz)
        self.cmd_term.vel_command_b[0, 0], self.cmd_term.vel_command_b[0, 1], self.cmd_term.vel_command_b[0, 2] = vx, vy, wz

    def step(self):
        torch = self._torch
        if self.fell:  # a fallen robot gets a zero velocity command; the policy keeps running
            self.set_command(0.0, 0.0, 0.0)
        with torch.inference_mode():
            actions = self.policy(self.obs)
        self.obs, _, _, _ = self.wrapped.step(actions)
        self.steps += 1
        g = self.robot.data.projected_gravity_b.torch[0]
        p = self.robot.data.root_link_pos_w.torch[0] - self.scene.env_origins[0]
        if float(g[2]) > -0.5 or float(p[2]) < self.spec["min_height"]:
            self.fell = True
        if self.way is not None:
            d = self.dist(self.way)
            self.way_min = min(self.way_min, d)
            if d < WAY_RADIUS:
                self.way_passed = True
        if self.steps % 2 == 0:
            self._follow_cameras()
        if self.on_step:
            self.on_step(self.steps)

    def _follow_cameras(self):
        """Chase camera behind the robot and a top-down one above it: a fixed camera showed a speck."""
        if "side_cam" not in self.scene.keys():
            return
        torch = self._torch
        from agent.cameras import look_at_quat
        p = self.robot.data.root_link_pos_w.torch[0]
        yaw = math.radians(self.pose()["heading_deg"])
        eye = (float(p[0]) - 2.6 * math.cos(yaw) + 0.9 * math.sin(yaw), float(p[1]) - 2.6 * math.sin(yaw) - 0.9 * math.cos(yaw), float(p[2]) + 1.3)
        tgt = (float(p[0]), float(p[1]), float(p[2]) + 0.1)
        top_eye, top_tgt = (float(p[0]), float(p[1]), float(p[2]) + 6.0), (float(p[0]) + 1e-3, float(p[1]), 0.0)
        hero_eye = (float(p[0]) - 2.4 * math.cos(yaw) + 1.4 * math.sin(yaw), float(p[1]) - 2.4 * math.sin(yaw) - 1.4 * math.cos(yaw), float(p[2]) + 1.0)
        hero_tgt = (float(p[0]), float(p[1]), float(p[2]) + 0.05)
        views = [("side_cam", eye, tgt, (0.0, 0.0, 1.0)), ("front_cam", top_eye, top_tgt, (1.0, 0.0, 0.0))]
        if "hero_cam" in self.scene.keys():
            views.append(("hero_cam", hero_eye, hero_tgt, (0.0, 0.0, 1.0)))
        for name, e, t, up in views:
            cam = self.scene[name]
            cam.set_world_poses(positions=torch.tensor([e], device=self.device, dtype=torch.float32),
                                orientations=torch.tensor([look_at_quat(e, t, up)], device=self.device, dtype=torch.float32),
                                convention="world")

    def walk(self, vx: float, vy: float, wz: float, seconds: float):
        self.set_command(vx, vy, wz)
        for _ in range(int(max(0.0, min(float(seconds), 5.0)) / self.dt)):
            self.step()
            if self.fell:
                break

    def reset(self, seed: int) -> dict:
        import random
        torch = self._torch
        self.env.seed(seed)
        self.obs, _ = self.wrapped.reset()
        rng = random.Random(seed)
        self.steps, self.fell, self.way_passed, self.way_min = 0, False, False, float("inf")
        self.set_command(0.0, 0.0, 0.0)
        for _ in range(25):  # half a second standing before the goal is placed
            self.step()
        p = self.pose()
        ang, dist = rng.uniform(-math.pi, math.pi), rng.uniform(3.0, 4.5)
        self.goal = dict(x=round(p["x"] + dist * math.cos(ang), 3), y=round(p["y"] + dist * math.sin(ang), 3), radius=GOAL_RADIUS)
        side = rng.choice((-1.5, 1.5))
        mx, my = p["x"] + 0.5 * dist * math.cos(ang), p["y"] + 0.5 * dist * math.sin(ang)
        self.way = dict(x=round(mx - side * math.sin(ang), 3), y=round(my + side * math.cos(ang), 3), radius=WAY_RADIUS)
        for name, t in (("goal_marker", self.goal), ("way_marker", self.way)):
            obj = self.scene[name]
            pose = torch.tensor([[t["x"], t["y"], 0.004, 0.0, 0.0, 0.0, 1.0]], device=self.device)
            pose[:, :3] += self.scene.env_origins[:1]
            obj.write_root_pose_to_sim_index(root_pose=pose)
            obj.write_root_velocity_to_sim_index(root_velocity=torch.zeros(1, 6, device=self.device))
        self.steps, self.fell, self.way_passed, self.way_min = 0, False, False, self.dist(self.way)
        if self.on_reset:
            self.on_reset()
        return dict(seed=seed, start=p, goal=self.goal, waypoint=self.way, policy=os.path.basename(self.policy_path))

    # ---- hooks the loop and the runners look for ----------------------------------------------------
    def make_api(self):
        return LocoAPI(self)

    def api_doc(self) -> str:
        s = self.spec
        return _DOC.format(desc=s["desc"], vx0=s["vx"][0], vx1=s["vx"][1], vy1=s["vy"][1], wz1=s["wz"][1],
                           goal=GOAL_RADIUS, way=WAY_RADIUS, budget=int(STEP_BUDGET * self.dt))

    @property
    def REFERENCE_PROGRAM(self) -> str:
        return REFERENCE_PROGRAM_LOCO

    def judge(self, run: dict) -> dict:
        """Hold still for a second, then: upright, waypoint passed, within the goal radius."""
        if not self.fell:
            self.walk(0.0, 0.0, 0.0, 1.0)
        d_goal, p = self.dist(self.goal), self.pose()
        n_calls = sum(1 for r in run.get("trace", []) if r["call"] == "walk")
        out = dict(success=False, failure=None, final_dist_m=round(d_goal, 3), waypoint_min_dist_m=round(self.way_min, 3),
                   waypoint_passed=self.way_passed, fell=self.fell, n_calls=n_calls, final_pose=p, detail="")
        if run["status"] == "invalid":
            out.update(failure="invalid_program", detail="; ".join(run.get("problems", [])))
        elif run["status"] == "error":
            out.update(failure="program_error", detail=str(run.get("exception")))
        elif self.fell:
            out.update(failure="fell", detail=f"the robot fell at ({p['x']}, {p['y']}), {d_goal:.2f} m from the goal")
        elif run["status"] in ("budget", "timeout"):
            out.update(failure="budget_exhausted", detail=f"{d_goal:.2f} m from the goal when the budget ran out")
        elif math.hypot(p["x"], p["y"]) > ARENA_RADIUS:
            out.update(failure="left_arena")
        elif not self.way_passed:
            out.update(failure="missed_waypoint", detail=f"closest approach to the waypoint {self.way_min:.2f} m (needs < {WAY_RADIUS} m)")
        elif d_goal > GOAL_RADIUS:
            out.update(failure="not_at_goal", detail=f"stopped {d_goal:.2f} m from the goal (needs < {GOAL_RADIUS} m)")
        else:
            out.update(success=True)
        return out

    def feedback_text(self, run: dict, verdict: dict, attempt: int, max_attempts: int) -> str:
        lines = [f"Attempt {attempt} of {max_attempts} FAILED: {verdict['failure']}. {verdict.get('detail', '')}"]
        if run["status"] == "invalid":
            lines.append("The program was rejected before running: " + "; ".join(run["problems"]))
        elif run["exception"]:
            lines.append(f"The program raised: {run['exception']}")
        # Every walk/stop/log call (get_pose echoes are dropped: each walk result already carries the pose).
        # A long run is shown head and tail, so the model sees how the run ended, not only how it began:
        # with the first 30 events only, a 60 s run was judged on its first 15 s (docs/03 §3).
        ev, errs, min_goal = [], [], None
        for r in run.get("trace", []):
            res, a = r["result"], r["args"]
            if r["call"] == "walk":
                errs.append(res["heading_error_deg"])
                min_goal = res["dist_goal_m"] if min_goal is None else min(min_goal, res["dist_goal_m"])
                ev.append(f"t={r['t']}s walk(vx={a['vx']}, vy={a['vy']}, wz={a['wz']}, seconds={a['seconds']}) -> now at "
                          f"({res['pose']['x']}, {res['pose']['y']}) heading {res['pose']['heading_deg']} deg; goal {res['dist_goal_m']} m away at "
                          f"bearing {res['bearing_goal_deg']} deg (heading error {res['heading_error_deg']:+.0f} deg, positive means the goal is to the "
                          f"left); waypoint {res['dist_way_m']} m away" + ("; the robot FELL during this call" if res["fell"] else ""))
            elif r["call"] == "stop":
                ev.append(f"t={r['t']}s stop({a['seconds']}) -> at ({res['pose']['x']}, {res['pose']['y']}), goal {res['dist_goal_m']} m away")
            elif r["call"] == "log":
                ev.append(f"t={r['t']}s log: {a['message']}")
        if ev:
            lines.append("Measured during the run:")
            head, tail = 10, 12
            shown = ev if len(ev) <= head + tail + 2 else ev[:head] + [f"... {len(ev) - head - tail} more calls omitted ..."] + ev[-tail:]
            lines.extend("  " + e for e in shown)
        flips = sum(1 for i in range(1, len(errs)) if abs(errs[i]) > 15 and abs(errs[i - 1]) > 15 and (errs[i] > 0) != (errs[i - 1] > 0))
        if len(errs) >= 4 and flips >= 3:
            lines.append(f"The heading error changed sign {flips} times over {len(errs)} walk calls while staying above 15 deg: "
                         f"the turn commands overshoot the bearing instead of settling on it.")
        if min_goal is not None and not verdict.get("fell"):
            lines.append(f"Closest the robot came to the goal centre: {min_goal} m.")
        lines.append(f"At the end: {verdict['final_dist_m']} m from the goal (needs < {GOAL_RADIUS} m), waypoint "
                     f"{'passed' if verdict['waypoint_passed'] else 'MISSED (closest ' + str(verdict['waypoint_min_dist_m']) + ' m)'}, "
                     f"{'fallen' if verdict['fell'] else 'upright'}.")
        lines.append("Fix the program. Reply with the complete corrected program in one fenced python block.")
        return "\n".join(lines)


_DOC = """
You control {desc} in a physics simulation through its walking controller. Units: metres, seconds, degrees.
Frame: world x-y on flat ground; heading 0 points along +x, positive headings turn left (counter-clockwise).
The robot must pass over the waypoint marker (within {way} m of its centre) and then stop on the goal marker
(within {goal} m). Walking time is limited to {budget} s of simulation.

Functions (already defined; do not import anything):
  get_pose() -> dict: x, y, heading_deg of the robot now
  get_goal() -> dict: x, y, radius of the goal marker
  get_waypoint() -> dict: x, y, radius of the waypoint marker
  distance_to(x, y) -> float: distance from the robot to that point
  heading_to(x, y) -> float: the heading (deg) that points the robot at that point
  walk(vx, vy, wz, seconds) -> dict: command a body velocity for that long: vx forward in [{vx0}, {vx1}] m/s,
                  vy left in [-{vy1}, {vy1}] m/s, wz turn rate in [-{wz1}, {wz1}] rad/s (positive turns left); seconds <= 5.
                  Returns pose, dist_goal_m, dist_way_m, bearing_goal_deg, heading_error_deg, fell.
  stop(seconds) -> dict: stand still for that long
  log(message) -> None: write a note into the trace

Turning while walking fast makes the robot fall. Programs are plain Python with these functions plus math:
no imports, no classes, no while loops (use for loops with a fixed count and break).
"""

REFERENCE_PROGRAM_LOCO = """
# hand-written reference: face each target, walk towards it, slow down near it.
# Turns keep a little forward speed and stay under 0.6 rad/s: spinning in place at the
# full turn rate toppled the Go2 policy on 2 of 8 starts (docs/03 §3).
for target in (get_waypoint(), get_goal()):
    for i in range(16):
        p = get_pose()
        d = distance_to(target["x"], target["y"])
        if d < 0.3:
            break
        err = ((heading_to(target["x"], target["y"]) - p["heading_deg"] + 180.0) % 360.0) - 180.0
        wz = max(-0.6, min(0.6, err / 45.0))
        vx = 0.15 if abs(err) > 35.0 else (0.7 if d > 1.0 else 0.35)
        walk(vx, 0.0, wz, 1.0)
stop(1.0)
log(f"final distance {distance_to(get_goal()['x'], get_goal()['y']):.2f}")
"""


class LocoAPI:
    """Bound to one LocoEnv episode. Every call traced like GraspAPI."""

    def __init__(self, genv: LocoEnv, step_budget: int = STEP_BUDGET, wall_budget_s: float = WALL_BUDGET_S):
        self.g, self.step_budget, self.wall_budget_s, self.t0, self.trace = genv, step_budget, wall_budget_s, time.time(), []

    def _rec(self, call, args, result):
        g = self.g
        self.trace.append(dict(t=round(g.steps * g.dt, 2), step=g.steps, call=call, args=args, result=result,
                               rise_m=round(g.metric(), 3), moved_xy_m=0.0, contacts={}))
        return result

    def _check_budget(self):
        from agent.graspapi import BudgetExceeded
        if self.g.steps > self.step_budget:
            raise BudgetExceeded(f"walking budget of {self.step_budget * self.g.dt:.0f} s used up")
        if time.time() - self.t0 > self.wall_budget_s:
            raise BudgetExceeded(f"wall-clock budget of {self.wall_budget_s:.0f} s used up")

    def _state(self) -> dict:
        g, p = self.g, self.g.pose()
        b = g.bearing(g.goal)
        return dict(pose=p, dist_goal_m=round(g.dist(g.goal), 3), dist_way_m=round(g.dist(g.way), 3),
                    bearing_goal_deg=round(b, 1), heading_error_deg=round(_wrap(b - p["heading_deg"]), 1), fell=g.fell)

    def scenario(self) -> dict:
        return dict(robot=self.g.pose(), goal=self.g.goal, waypoint=self.g.way)

    def get_pose(self):
        return self._rec("get_pose", {}, self.g.pose())

    def get_goal(self):
        return self._rec("get_goal", {}, dict(self.g.goal))

    def get_waypoint(self):
        return self._rec("get_waypoint", {}, dict(self.g.way))

    def distance_to(self, x, y):
        return self._rec("distance_to", dict(x=float(x), y=float(y)), round(self.g.dist(dict(x=float(x), y=float(y))), 3))

    def heading_to(self, x, y):
        return self._rec("heading_to", dict(x=float(x), y=float(y)), round(self.g.bearing(dict(x=float(x), y=float(y))), 1))

    def walk(self, vx, vy, wz, seconds):
        self._check_budget()
        args = dict(vx=round(float(vx), 3), vy=round(float(vy), 3), wz=round(float(wz), 3), seconds=round(float(seconds), 2))
        self.g.walk(vx, vy, wz, seconds)
        return self._rec("walk", args, self._state())

    def stop(self, seconds):
        self._check_budget()
        self.g.walk(0.0, 0.0, 0.0, seconds)
        return self._rec("stop", dict(seconds=round(float(seconds), 2)), self._state())

    def log(self, message):
        return self._rec("log", dict(message=str(message)[:300]), None)

    def namespace(self) -> dict:
        names = ["get_pose", "get_goal", "get_waypoint", "distance_to", "heading_to", "walk", "stop", "log"]
        ns = {n: getattr(self, n) for n in names}
        ns["math"] = math
        return ns
