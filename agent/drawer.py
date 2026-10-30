"""Drawer opening on NVIDIA's kit-less Franka cabinet scene (Isaac-Open-Drawer-Franka): an articulated
object instead of a free one. The grasp API is the same, plus get_handle() and drawer_opening(); the hand's
default orientation is the handle's, the judge reads the drawer joint. Reached through agent.env when
--task is drawer.
"""
from __future__ import annotations

import math
import random

from agent.env import GraspEnv
from agent.graspapi import GraspAPI
from agent.loop import feedback_text as grasp_feedback_text

OPEN_MIN = 0.20
WORKSPACE_DRAWER = dict(x=(0.10, 0.80), y=(-0.45, 0.45), z=(0.05, 0.95))
CAB_SIDE = dict(eye=(0.55, -1.15, 0.85), target=(0.55, 0.0, 0.45), up=(0.0, 0.0, 1.0), focal_length=20.0)
CAB_OVER = dict(eye=(-0.75, 0.0, 1.25), target=(0.55, 0.0, 0.40), up=(0.0, 0.0, 1.0), focal_length=18.0)


def make_drawer_env_cfg(cameras: bool = False, camera_res=None, ik_lambda: float = 0.05):
    from isaaclab.controllers import DifferentialIKControllerCfg
    from isaaclab.envs import ManagerBasedEnvCfg, mdp
    from isaaclab.managers import EventTermCfg as EventTerm
    from isaaclab.managers import ObservationGroupCfg as ObsGroup
    from isaaclab.managers import ObservationTermCfg as ObsTerm
    from isaaclab.sensors import ContactSensorCfg
    from isaaclab.utils import configclass, replace
    from isaaclab_assets.robots.franka import FRANKA_PANDA_HIGH_PD_CFG
    from isaaclab_tasks.core.cabinet import cabinet_env_cfg as cab
    from isaaclab_tasks.core.cabinet.config.franka.joint_pos_env_cfg import FrankaCabinetSceneCfg
    from isaaclab_tasks.utils import preset
    from isaaclab_tasks.utils.hydra import resolve_presets

    @configclass
    class ActionsCfg:
        arm_action = mdp.DifferentialInverseKinematicsActionCfg(
            asset_name="robot", joint_names=["panda_joint.*"], body_name="panda_hand",
            controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls",
                                                   ik_params={"lambda_val": ik_lambda}))
        gripper_action = mdp.BinaryJointPositionActionCfg(asset_name="robot", joint_names=["panda_finger.*"],
                                                          open_command_expr={"panda_finger_.*": 0.04},
                                                          close_command_expr={"panda_finger_.*": 0.0})

    @configclass
    class ObservationsCfg:
        @configclass
        class PolicyCfg(ObsGroup):
            joint_pos = ObsTerm(func=mdp.joint_pos_rel)

        policy: PolicyCfg = PolicyCfg()

    @configclass
    class EventCfg:
        reset_all = EventTerm(func=mdp.reset_scene_to_default, mode="reset")

    @configclass
    class DrawerEnvCfg(ManagerBasedEnvCfg):
        scene: FrankaCabinetSceneCfg = FrankaCabinetSceneCfg(num_envs=1, env_spacing=3.0, replicate_physics=True)
        observations: ObservationsCfg = ObservationsCfg()
        actions: ActionsCfg = ActionsCfg()
        events: EventCfg = EventCfg()

        def __post_init__(self):
            self.sim = cab.CabinetSimCfg()  # NVIDIA's per-backend presets; resolve_presets picks newton_mjwarp
            self.decimation = cab.CabinetDecimationCfg()
            # the stiff IK robot NVIDIA ships for scripted control, gravity off, our stiff gripper drive
            self.scene.robot = replace(FRANKA_PANDA_HIGH_PD_CFG, prim_path="{ENV_REGEX_NS}/Robot")
            self.scene.robot.spawn.variants["Physics"] = preset(default="mujoco", isaacsim_physx="physx", physx="physx", ovphysx="physx")
            self.scene.robot.spawn.rigid_props.disable_gravity = True
            hand = self.scene.robot.actuators["panda_hand"]
            hand.stiffness, hand.damping = 2e3, 1e2
            self.scene.ee_frame.debug_vis = False
            self.scene.cabinet_frame.debug_vis = False
            self.scene.left_handle_s = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/(Geometry/.*/)?panda_leftfinger", update_period=0.0,
                                                        filter_prim_paths_expr=["{ENV_REGEX_NS}/Cabinet/drawer_handle_top"])
            self.scene.right_handle_s = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/(Geometry/.*/)?panda_rightfinger", update_period=0.0,
                                                         filter_prim_paths_expr=["{ENV_REGEX_NS}/Cabinet/drawer_handle_top"])
            if cameras:
                from agent.cameras import RES, camera_cfg
                res = camera_res or RES
                self.scene.side_cam = camera_cfg("SideCam", CAB_SIDE, res)
                self.scene.front_cam = camera_cfg("FrontCam", CAB_OVER, res)

    return resolve_presets(DrawerEnvCfg())


class DrawerEnv(GraspEnv):
    SENSOR_NAMES = {"left": "left_handle_s", "right": "right_handle_s"}
    WORKSPACE = WORKSPACE_DRAWER
    TASK = "Open the top drawer of the cabinet by at least 20 cm and keep holding it open."
    SUCCESS_TEXT = f"Success: the top drawer is open by at least {OPEN_MIN:.2f} m at the end of the program."
    METRIC_LABEL = "drawer opening"
    TOL_DEG = 8.0  # the handle pose is at the wrist's limit; 7 deg residual is normal here
    HAND_DESC = ("a two-finger parallel gripper (max opening 0.08 m) on a Franka arm facing a cabinet. The cabinet's "
                 "top drawer has a horizontal handle bar; get_handle() gives the bar's centre and the gripper orientation "
                 "that grasps it (pass that quat to move_to). The drawer slides out towards the robot, along -x. A spring "
                 "pulls it shut again when released")

    def __init__(self, env, shape: str = "drawer"):
        import torch
        from isaaclab.utils import math as mu

        self.env = env.unwrapped if hasattr(env, "unwrapped") else env
        self.shape = self.SCENARIO = "drawer"
        self.extent = dict(size_xyz=[0.02, 0.20, 0.02], half_height=0.01, narrow_width=0.02)
        self.scene = self.env.scene
        self.robot, self.object = self.scene["robot"], None
        self.cab, self.frame = self.scene["cabinet"], self.scene["cabinet_frame"]
        self._drawer = self.cab.find_joints("drawer_top_joint")[0][0]
        self.sensors = {k: self.scene[v] for k, v in self.SENSOR_NAMES.items()}
        self.device, self.dt = self.env.device, self.env.step_dt
        self._hand_idx = self.robot.find_bodies(self.HAND_BODY)[0][0]
        self._tool = torch.tensor(self.TOOL_OFFSET, dtype=torch.float32, device=self.device)
        self._action = torch.zeros((1, self.env.action_manager.total_action_dim), device=self.device)
        self._comp, self._rot_comp = torch.zeros(3, device=self.device), torch.zeros(3, device=self.device)
        self._mu, self._torch = mu, torch
        self.steps, self.gripper_closed, self.object_start = 0, False, None
        self.on_step = self.on_reset = None
        self.max_opening = 0.0

    # ---- state ------------------------------------------------------------------------------------
    def handle_pose(self):
        p = self.frame.data.target_pos_w.torch[0, 0] - self.scene.env_origins[0]
        q = self.frame.data.target_quat_w.torch[0, 0]
        return p, q

    def object_pose(self):
        return self.handle_pose()

    def opening(self) -> float:
        return float(self.cab.data.joint_pos.torch[0, self._drawer])

    def object_rise(self) -> float:
        return self.opening()

    def metric(self) -> float:
        return self.opening()

    def object_yaw_deg(self) -> float:
        return 0.0

    def step(self):
        super().step()
        self.max_opening = max(self.max_opening, self.opening())

    def reset(self, seed: int, xy_jitter: float = 0.05, yaw_deg=None):
        torch = self._torch
        self.env.reset()
        rng = random.Random(seed)
        # the cabinet is fixed-base and cannot be moved after the Newton build; the scenario varies through the
        # drawer's initial opening and the arm's start configuration instead
        open0 = rng.uniform(0.0, 0.05)
        jp = self.cab.data.default_joint_pos.torch[:1].clone()
        jp[0, self._drawer] = open0
        self.cab.write_joint_position_to_sim_index(position=jp)
        self.cab.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(jp))
        rq = self.robot.data.default_joint_pos.torch[:1].clone()
        arm = self.robot.find_joints("panda_joint.*")[0]
        for j in arm:
            rq[0, j] += rng.uniform(-0.12, 0.12)
        self.robot.write_joint_position_to_sim_index(position=rq)
        self.robot.write_joint_velocity_to_sim_index(velocity=torch.zeros_like(rq))
        dx, dy = 0.0, open0
        self.steps, self.gripper_closed, self.max_opening = 0, False, 0.0
        self._comp.zero_()
        self._rot_comp.zero_()
        p, q = self.ee_pose()
        self._set_target(p, q)
        for _ in range(15):
            self.step()
        hp, hq = self.handle_pose()
        self.HAND_DOWN = tuple(round(float(c), 6) for c in hq.tolist())  # the hand's default orientation is the handle's
        self.object_start = hp.tolist()
        if self.on_reset:
            self.on_reset()
        return dict(seed=seed, handle=[round(c, 4) for c in hp.tolist()], initial_opening=round(dy, 3))

    # ---- hooks ------------------------------------------------------------------------------------
    def make_api(self):
        return DrawerAPI(self)

    def api_doc(self) -> str:
        from agent.graspapi import api_doc
        doc = api_doc(self)
        return doc.replace("The table top is at z = 0.255.", "The cabinet stands in front of the robot at about x = 0.8.") + (
            "  get_handle() -> dict: pos [x, y, z] of the drawer handle's centre, quat [x, y, z, w] of the gripper pose that\n"
            "                  grasps it, pull_dir [-1, 0, 0], opening (m)\n"
            "  drawer_opening() -> float: how far the top drawer is open, in metres\n")

    @property
    def REFERENCE_PROGRAM(self) -> str:
        return REFERENCE_PROGRAM_DRAWER

    def judge(self, run: dict) -> dict:
        self.wait(0.1)
        o, trace = self.opening(), run.get("trace", [])
        touched = any(any(r["contacts"].values()) for r in trace) or any(self.contacts().values())
        out = dict(success=False, failure=None, final_rise_m=round(o, 4), max_rise_m=round(self.max_opening, 4), opening_m=round(o, 4),
                   contacts=self.contacts(), gripper_closed=self.gripper_closed, n_calls=len(trace), detail="")
        if run["status"] == "invalid":
            out.update(failure="invalid_program", detail="; ".join(run["problems"]))
        elif run["status"] in ("error", "timeout"):
            out.update(failure="program_error", detail=str(run["exception"]))
        elif run["status"] == "budget":
            out.update(failure="budget_exhausted", detail=str(run["exception"]))
        elif o >= OPEN_MIN:
            out.update(success=True, detail=f"drawer open by {o:.3f} m")
        elif not touched:
            out.update(failure="handle_missed", detail="no fingertip ever touched the handle")
        elif self.max_opening >= 0.05 and not self.gripper_closed:
            out.update(failure="released_too_early", detail=f"the drawer reached {self.max_opening:.3f} m but sprang back to {o:.3f} m after the gripper opened")
        elif self.max_opening >= 0.05:
            out.update(failure="slipped_off_handle", detail=f"the drawer reached {self.max_opening:.3f} m, then the handle slipped out; now {o:.3f} m")
        else:
            out.update(failure="insufficient_pull", detail=f"the drawer only opened {self.max_opening:.3f} m (needs {OPEN_MIN} m)")
        return out

    def feedback_text(self, run: dict, verdict: dict, attempt: int, max_attempts: int) -> str:
        base = grasp_feedback_text(run, verdict, attempt, max_attempts)
        lines = [ln for ln in base.splitlines() if not ln.startswith("At the end:")]
        end = (f"At the end: the drawer is open by {verdict['opening_m']} m (needs >= {OPEN_MIN} m; the most it opened during the run "
               f"was {verdict['max_rise_m']} m), gripper {'closed' if verdict['gripper_closed'] else 'open'}, fingertips touching the handle "
               f"{verdict['contacts']}. Note: 'object rise' in the lines above is the drawer opening.")
        i = next(k for k, ln in enumerate(lines) if ln.startswith("Fix the program."))
        return "\n".join(lines[:i] + [end] + lines[i:])


class DrawerAPI(GraspAPI):
    def get_handle(self) -> dict:
        p, q = self.g.handle_pose()
        return self._rec("get_handle", {}, dict(pos=[round(c, 4) for c in p.tolist()], quat=[round(c, 4) for c in q.tolist()],
                                                pull_dir=[-1.0, 0.0, 0.0], opening=round(self.g.opening(), 4)))

    def drawer_opening(self) -> float:
        return self._rec("drawer_opening", {}, round(self.g.opening(), 4))

    def namespace(self) -> dict:
        ns = super().namespace()
        ns["get_handle"], ns["drawer_opening"] = self.get_handle, self.drawer_opening
        return ns


REFERENCE_PROGRAM_DRAWER = """
# hand-written reference: line up in front of the handle, grasp the bar, pull straight back, keep holding
h = get_handle()
x, y, z = h["pos"]
q = h["quat"]
open_gripper()
move_to([x - 0.12, y, z], quat=q)
move_to([x - 0.005, y, z], quat=q)
close_gripper()
move_to([x - 0.25, y, z], quat=q, timeout=6.0)  # the drawer stops at ~0.33 m; pulling past the stop tore the handle out of the fingers
wait(0.5)
log(f"opening {drawer_opening():.3f}")
"""
