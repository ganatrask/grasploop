"""GraspLoop environment: NVIDIA's Franka lift scene wrapped for scripted / LLM-written grasp programs.

Everything physical is NVIDIA's; make_env_cfg() marks the control settings changed for scripted IK
(robot gravity off, a stiff gripper drive, the IK damping; GraspEnv applies the tool offset):
  - scene (robot with the lift-task gains, table, object presets, fingertip contact sensors):
    isaaclab_tasks.core.lift.config.franka.franka_env_cfg.FrankaSceneCfg
  - arm control: the differential-IK action term the Isaac-Lift-Soft-Franka task ships
    (DLS IK on panda_joint.*, body panda_hand, 0.107 m tool offset) + its binary gripper action
  - physics: the lift task's newton_mjwarp preset, kit-less Newton / MuJoCo-Warp

Our part is this file: a ManagerBasedEnv (not the RL env, whose reset bank spawns the object
in the hand 75 % of the time and randomises gains), one env, a seeded object placement, and
readers for object pose, end-effector pose and fingertip contact that the grasp API and the
physics judge use.

Conventions (GA, verified in the source on 2026-10-27):
  - quaternions are (x, y, z, w) everywhere, including the IK action
  - the IK target is in the robot root frame; the Franka root is rotated 180 deg about z, so
    the table sits at negative world x. The API converts world -> root, so programs see world.
  - hand pointing down = quaternion (1, 0, 0, 0): 180 deg about the root x-axis
  - table top is at world z = TABLE_TOP

Run `$PY -m agent.env --viz none` from the repo root for a smoke test: reset, then one move_to 25 cm
above the table (writes _logs/env_smoke.json).
"""
from __future__ import annotations

import argparse
import math

from isaaclab.app import add_launcher_args

TABLE_TOP = 0.235 + 0.02  # lift scene: table centre z + half thickness
OBJECT_XY_HOME = (-0.55, 0.0)  # table centre, in front of the robot
# 180 deg about world y. The home pose is already this orientation; the other hand-down quaternion,
# 180 deg about x, is a 180 deg wrist yaw away, beyond panda_joint7's +-166 deg, and the DLS IK
# wanders off trying to reach it (diag 2026-10-27). Fingers close along world y at yaw 0.
HAND_DOWN_XYZW = (0.0, 1.0, 0.0, 0.0)
GRIPPER_MAX_OPENING = 0.08  # two 0.04 m fingers

# object presets: name -> primitive kind and dimensions (m); shape_extent() derives half-height and narrow width
SHAPES = {
    "cube": dict(kind="cuboid", size=(0.05, 0.05, 0.05)),
    "box_tall": dict(kind="cuboid", size=(0.05, 0.05, 0.10)),
    "box_flat": dict(kind="cuboid", size=(0.025, 0.05, 0.05)),
    "bar_thin": dict(kind="cuboid", size=(0.01, 0.05, 0.05)),
    "bar_long": dict(kind="cuboid", size=(0.025, 0.025, 0.10)),
    "sphere_s": dict(kind="sphere", radius=0.02),
    "sphere_m": dict(kind="sphere", radius=0.025),
    "sphere_big": dict(kind="sphere", radius=0.05),  # 10 cm: does not fit the gripper
    "capsule_s": dict(kind="capsule", radius=0.025, height=0.1),
    "capsule_thin": dict(kind="capsule", radius=0.01, height=0.2),
}


def add_env_args(parser: argparse.ArgumentParser) -> None:
    add_launcher_args(parser)
    parser.add_argument("--robot", choices=["franka", "allegro", "go2", "g1"], default="franka",
                        help="franka: Panda + parallel gripper (Isaac-Lift-Franka scene); allegro: Kuka iiwa + Allegro "
                             "four-finger hand (Isaac-Lift-KukaAllegro scene); go2 / g1: Unitree quadruped / humanoid walking "
                             "on a trained RSL-RL policy")
    parser.add_argument("--shape", choices=sorted(SHAPES), default="cube")
    parser.add_argument("--task", choices=["lift", "place", "drawer"], default="lift",
                        help="lift: raise the object 10 cm and hold (the benchmark task); place: set it down on a target marker; "
                             "drawer: open the cabinet's top drawer (Franka)")
    parser.add_argument("--ik-lambda", type=float, default=0.05,
                        help="DLS damping of the IK action. The soft task's 0.6 takes >3 s per 10 cm on this "
                             "stiffer robot; 0.05 converges in ~1.5 s (diag 2026-10-27).")
    parser.add_argument("--cameras", type=str, default=None,
                        help="Directory for camera frames (Warp renderer, works with --viz none). Off if unset.")
    parser.add_argument("--video", type=str, default=None,
                        help="Film every attempt from both cameras at 640x480, 15 fps, into DIR/<tag>/ (frames + "
                             "meta.json); eval/make_videos.py turns them into mp4s. Implies cameras.")
    parser.add_argument("--hero", type=str, default=None,
                        help="Demo footage: add a 1280x720 hero camera on NVIDIA's OVRTX path tracer and film every attempt "
                             "from it (plus the side camera for picture-in-picture) into DIR/<tag>/. Implies --video-grade cameras. "
                             "eval/make_demo.py --hero DIR cuts from these.")
    parser.add_argument("--hero-renderer", choices=["ovrtx", "warp"], default="ovrtx",
                        help="warp: the Warp ray tracer with shadows on, if OVRTX is unavailable")


def shape_spawner(name: str):
    """NVIDIA's object preset physics (lift_env_cfg.OBJECT_PHYSICS) on the requested primitive."""
    import isaaclab.sim as sim_utils
    from isaaclab.sim import MeshCapsuleCfg, MeshCuboidCfg, MeshSphereCfg
    from isaaclab_physx.sim.schemas import PhysxRigidBodyCfg
    from isaaclab_tasks.core.lift import lift_env_cfg as lift

    s = dict(SHAPES[name])
    kind = s.pop("kind")
    cls = {"cuboid": MeshCuboidCfg, "sphere": MeshSphereCfg, "capsule": MeshCapsuleCfg}[kind]
    return cls(
        **s, **lift.OBJECT_PHYSICS,
        rigid_props=PhysxRigidBodyCfg(solver_position_iteration_count=16, solver_velocity_iteration_count=0,
                                      disable_gravity=False),
        mass_props=sim_utils.MassCfg(mass=0.2),
        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.85, 0.15, 0.1)),
    )


def shape_extent(name: str) -> dict:
    """Axis-aligned extents at yaw 0 and the resting half-height, from the preset geometry."""
    s = SHAPES[name]
    if s["kind"] == "cuboid":
        sx, sy, sz = s["size"]
        return dict(size_xyz=[sx, sy, sz], half_height=sz / 2, narrow_width=min(sx, sy))
    if s["kind"] == "sphere":
        d = 2 * s["radius"]
        return dict(size_xyz=[d, d, d], half_height=s["radius"], narrow_width=d)
    d, h = 2 * s["radius"], s["height"]
    # a capsule lies on the table with its axis along x at yaw 0: standing on a rounded end it topples
    # by itself before the hand arrives (gate 2026-10-27, 0/5 with no contact)
    return dict(size_xyz=[round(h + d, 4), d, d], half_height=s["radius"], narrow_width=d)


def make_env_cfg(shape: str, cameras: bool = False, ik_lambda: float = 0.05, gain_scale: float = 1.0,
                 robot: str = "franka", camera_res=None, task: str = "lift"):
    """ManagerBasedEnvCfg built from NVIDIA's parts. Imports are deferred past argument parsing."""
    from isaaclab.controllers import DifferentialIKControllerCfg
    from isaaclab.envs import ManagerBasedEnvCfg, mdp
    from isaaclab.managers import EventTermCfg as EventTerm
    from isaaclab.managers import ObservationGroupCfg as ObsGroup
    from isaaclab.managers import ObservationTermCfg as ObsTerm
    from isaaclab.utils import configclass
    from isaaclab_tasks.core.lift import lift_env_cfg as lift
    from isaaclab_tasks.utils.hydra import resolve_presets

    if robot == "allegro":
        from isaaclab_tasks.core.lift.config.kuka_allegro.kuka_allegro_env_cfg import KukaAllegroSceneCfg as SceneCfgCls

        from agent.allegro import allegro_actions_cfg
        ActionsCfg = allegro_actions_cfg(ik_lambda)
    else:
        from isaaclab_tasks.core.lift.config.franka.franka_env_cfg import FrankaSceneCfg as SceneCfgCls

        @configclass
        class ActionsCfg:
            # the Isaac-Lift-Soft-Franka task's IK preset, with lambda_val from --ik-lambda and no body_offset
            arm_action = mdp.DifferentialInverseKinematicsActionCfg(
                asset_name="robot", joint_names=["panda_joint.*"], body_name="panda_hand",
                controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls",
                                                       ik_params={"lambda_val": ik_lambda}),
                # no body_offset: GraspEnv applies TOOL_OFFSET itself (see _set_target)
            )
            gripper_action = mdp.BinaryJointPositionActionCfg(
                asset_name="robot", joint_names=["panda_finger_joint1"],
                open_command_expr={"panda_finger_joint1": 0.04}, close_command_expr={"panda_finger_joint1": 0.01},
            )

    @configclass
    class ObservationsCfg:
        @configclass
        class PolicyCfg(ObsGroup):
            joint_pos = ObsTerm(func=mdp.joint_pos_rel)

            def __post_init__(self):
                self.enable_corruption = False
                self.concatenate_terms = True

        policy: PolicyCfg = PolicyCfg()

    @configclass
    class EventCfg:
        reset_all = EventTerm(func=mdp.reset_scene_to_default, mode="reset")

    @configclass
    class GraspEnvCfg(ManagerBasedEnvCfg):
        scene: SceneCfgCls = SceneCfgCls(num_envs=1, env_spacing=3.0, replicate_physics=True)
        observations: ObservationsCfg = ObservationsCfg()
        actions: ActionsCfg = ActionsCfg()
        events: EventCfg = EventCfg()

        def __post_init__(self):
            self.decimation = 4  # 30 Hz control, as the lift task
            self.sim.dt = 1 / 120
            self.sim.render_interval = self.decimation
            # the lift task's preset set; resolve_presets() below picks its default, newton_mjwarp
            self.sim.physics = lift.PhysicsCfg()
            # NVIDIA's IK preset (isaaclab_assets FRANKA_PANDA_HIGH_PD_CFG) switches gravity off on the
            # robot links; the lift task's RL gains otherwise let the arm sag ~4 cm and the wrist droop ~14 deg
            # under a position-restarting differential IK (diag 2026-10-27). Same choice here.
            self.scene.robot.spawn.rigid_props.disable_gravity = True
            # The lift task slows the gripper for RL (stiffness 350, damping 175: a 0.5 s time constant,
            # so 0.6 s after "close" the fingers are still 3.8 cm apart and a 2.5 cm box is untouched).
            # Use the stiff gripper drive Isaac Lab's Franka IK examples have always used (2e3 / 1e2:
            # a 0.05 s time constant) instead.
            if robot == "allegro":
                from agent.allegro import tune_allegro_actuators
                tune_allegro_actuators(self.scene.robot, gain_scale)
            else:
                hand = self.scene.robot.actuators["panda_hand"]
                hand.stiffness, hand.damping = 2000.0, 100.0
                if gain_scale != 1.0:  # experiment knob: scale the lift task's arm PD gains
                    arm = self.scene.robot.actuators["panda_arm"]
                    arm.stiffness = {k: v * gain_scale for k, v in arm.stiffness.items()}
                    arm.damping = {k: v * gain_scale ** 0.5 for k, v in arm.damping.items()}
            # one fixed object instead of the per-env multi-asset bank
            self.scene.object.spawn = shape_spawner(shape)
            self.scene.object.init_state.pos = (OBJECT_XY_HOME[0], OBJECT_XY_HOME[1],
                                                TABLE_TOP + shape_extent(shape)["half_height"] + 0.002)
            if task == "place":
                from agent.place import target_marker_cfg
                self.scene.target = target_marker_cfg()
            if cameras:
                from agent.cameras import RES, add_cameras
                add_cameras(self.scene, res=camera_res or RES)

    # NVIDIA's resolver: every PresetCfg in the tree (physics, robot USD variants) -> its default
    return resolve_presets(GraspEnvCfg())


def make_env_cfg_from_args(args):
    """make_env_cfg for a parser that went through add_env_args: cameras are on for --cameras or --video,
    and at video resolution when --video is set."""
    from agent.cameras import HERO_CAM_NAME, VIDEO_RES, hero_camera_cfg
    hero = getattr(args, "hero", None)
    video = getattr(args, "video", None) or hero  # hero footage also films the side camera at video resolution
    if getattr(args, "task", "lift") == "drawer":
        from agent.drawer import make_drawer_env_cfg
        args.shape = "drawer"
        cfg = make_drawer_env_cfg(cameras=bool(args.cameras or video), camera_res=VIDEO_RES if video else None, ik_lambda=args.ik_lambda)
    elif args.robot in ("go2", "g1"):
        from agent.locomotion import make_loco_env_cfg
        args.shape = "nav"  # the scenario family, used in tags and records where the arms use the object shape
        cfg = make_loco_env_cfg(args.robot, cameras=bool(args.cameras or video), camera_res=VIDEO_RES if video else None)
    else:
        cfg = make_env_cfg(args.shape, cameras=bool(args.cameras or video), ik_lambda=args.ik_lambda, robot=args.robot,
                           camera_res=VIDEO_RES if video else None, task=getattr(args, "task", "lift"))
    if hero:
        from agent.cameras import HERO_CAM, HERO_CAM_ALLEGRO
        from agent.locomotion import HERO_CHASE_CAM
        spec = HERO_CHASE_CAM if args.robot in ("go2", "g1") else (HERO_CAM_ALLEGRO if args.robot == "allegro" else HERO_CAM)
        setattr(cfg.scene, HERO_CAM_NAME, hero_camera_cfg(spec=spec, renderer=getattr(args, "hero_renderer", "ovrtx")))
    return cfg


def create_env(cfg, args):
    """The simulation env plus our wrapper for the robot in `args`; call inside launch_simulation()."""
    if args.robot in ("go2", "g1"):
        from isaaclab.envs import ManagerBasedRLEnv

        from agent.locomotion import LocoEnv
        return LocoEnv(ManagerBasedRLEnv(cfg), args.robot)
    from isaaclab.envs import ManagerBasedEnv
    if getattr(args, "task", "lift") == "drawer":
        from agent.drawer import DrawerEnv
        return DrawerEnv(ManagerBasedEnv(cfg))
    if getattr(args, "task", "lift") == "place":
        from agent.place import PlaceEnv
        return PlaceEnv(ManagerBasedEnv(cfg), args.shape)
    return make_grasp_env(ManagerBasedEnv(cfg), args.shape, args.robot)


def make_grasp_env(env, shape: str, robot: str = "franka"):
    """The GraspEnv subclass for the robot the config was built for."""
    if robot == "allegro":
        from agent.allegro import AllegroEnv
        return AllegroEnv(env, shape)
    return GraspEnv(env, shape)


class GraspEnv:
    """One Franka, one object. All poses returned in world frame, quaternions (x, y, z, w).
    Robot-specific facts live in class attributes so a subclass (agent/allegro.py) can swap them."""

    ROBOT = "franka"
    HAND_BODY = "panda_hand"
    TOOL_OFFSET = (0.0, 0.0, 0.107)  # hand frame -> the point between the fingertips
    PALM_OFFSET = (0.0, 0.0, 0.0584)  # hand frame -> the palm face (finger base); the fingers are 4.9 cm long
    HAND_DOWN = HAND_DOWN_XYZW
    SENSOR_NAMES = {"left": "panda_leftfinger_object_s", "right": "panda_rightfinger_object_s"}
    HAND_DESC = ("a two-finger parallel gripper (max opening 0.08 m). The fingertip point is the bottom of the "
                 "finger pads; the pads extend about 2 cm above it and close towards each other (parallel jaws, "
                 "2 cm wide). The palm face is 4.9 cm above the fingertip point. At yaw 0 the two fingers close "
                 "along the world y-axis")

    def __init__(self, env, shape: str):
        import torch
        from isaaclab.utils import math as mu

        self.env = env.unwrapped if hasattr(env, "unwrapped") else env
        self.shape = shape
        self.extent = shape_extent(shape)
        self.scene = self.env.scene
        self.robot = self.scene["robot"]
        self.object = self.scene["object"]
        self.sensors = {k: self.scene[v] for k, v in self.SENSOR_NAMES.items()}
        self.device = self.env.device
        self.dt = self.env.step_dt
        self._hand_idx = self.robot.find_bodies(self.HAND_BODY)[0][0]
        self._tool = torch.tensor(self.TOOL_OFFSET, dtype=torch.float32, device=self.device)
        self._action = torch.zeros((1, self.env.action_manager.total_action_dim), device=self.device)
        # Gravity-sag compensation. The IK restarts from the measured joints every step, so the
        # PD arm settles ~4 cm below (and 1 cm short of) any target. move_to() integrates the
        # measured error into the commanded point; the offset carries over between moves.
        self._comp = torch.zeros(3, device=self.device)
        self._rot_comp = torch.zeros(3, device=self.device)  # same for the wrist: it droops ~14 deg
        self._mu, self._torch = mu, torch
        self.steps = 0
        self.gripper_closed = False
        self.object_start = None
        self.on_step = None  # optional hooks: on_step(step) after every env step, on_reset() at reset
        self.on_reset = None

    # ---- lifecycle -------------------------------------------------------------------------
    def reset(self, seed: int, xy_jitter: float = 0.05, yaw_deg: float | None = None):
        """Seeded placement: object on the table centre plus a jitter drawn from `seed`."""
        import random
        torch = self._torch
        self.env.reset()
        rng = random.Random(seed)
        dx, dy = (rng.uniform(-xy_jitter, xy_jitter) for _ in range(2))
        yaw = math.radians(yaw_deg) if yaw_deg is not None else rng.uniform(-math.pi, math.pi)
        z = TABLE_TOP + self.extent["half_height"] + 0.002
        quat = self._mu.quat_from_euler_xyz(torch.zeros(1), torch.zeros(1), torch.tensor([yaw]))  # xyzw
        if SHAPES[self.shape]["kind"] == "capsule":  # lay the capsule down: its axis (local z) -> world x, then yaw
            lie = self._mu.quat_from_euler_xyz(torch.zeros(1), torch.tensor([math.pi / 2]), torch.zeros(1))
            quat = self._mu.quat_mul(quat, lie)
        pose = torch.tensor([[OBJECT_XY_HOME[0] + dx, OBJECT_XY_HOME[1] + dy, z, *quat[0].tolist()]],
                            device=self.device) + torch.cat([self.scene.env_origins[:1], torch.zeros(1, 4, device=self.device)], 1)
        self.object.write_root_pose_to_sim_index(root_pose=pose)
        self.object.write_root_velocity_to_sim_index(root_velocity=torch.zeros(1, 6, device=self.device))
        self.steps = 0
        self.gripper_closed = False
        self._comp.zero_()
        self._rot_comp.zero_()
        if self.on_reset:
            self.on_reset()
        # hold the current pose: start the IK target at the actual hand pose
        p, q = self.ee_pose()
        self._set_target(p, q)
        for _ in range(15):  # let the object settle on the table
            self.step()
        self.object_start = self.object_pose()[0].tolist()
        return dict(seed=seed, object_start=self.object_start, yaw_deg=math.degrees(yaw))

    def step(self):
        self.env.step(self._action)
        self.steps += 1
        if self.on_step:
            self.on_step(self.steps)

    # ---- readers -------------------------------------------------------------------------
    def object_pose(self):
        p = self.object.data.root_link_pos_w.torch[0] - self.scene.env_origins[0]
        return p, self.object.data.root_link_quat_w.torch[0]

    def object_rise(self) -> float:
        return float(self.object_pose()[0][2] - self.object_start[2])

    def ee_pose(self):
        """panda_hand frame + 0.107 m tool offset, i.e. the point between the fingertips."""
        p = self.robot.data.body_link_pos_w.torch[0, self._hand_idx] - self.scene.env_origins[0]
        q = self.robot.data.body_link_quat_w.torch[0, self._hand_idx]
        tip = p + self._mu.quat_apply(q, self._tool)
        return tip, q

    def object_yaw_deg(self) -> float:
        """Heading of the object's long axis on the table (its local x, or the axis for a lying capsule), so the
        value stays meaningful for a capsule whose quaternion carries a 90 deg pitch."""
        _, q = self.object_pose()
        axis = (0.0, 0.0, 1.0) if SHAPES[self.shape]["kind"] == "capsule" else (1.0, 0.0, 0.0)
        a = self._mu.quat_apply(q[None], self._torch.tensor([axis], dtype=self._torch.float32, device=self.device))[0]
        return math.degrees(math.atan2(float(a[1]), float(a[0])))

    def palm_pos(self):
        """World position of the palm face (the surface an object hits when the grasp is too low)."""
        p = self.robot.data.body_link_pos_w.torch[0, self._hand_idx] - self.scene.env_origins[0]
        q = self.robot.data.body_link_quat_w.torch[0, self._hand_idx]
        return p + self._mu.quat_apply(q, self._torch.tensor(self.PALM_OFFSET, dtype=self._torch.float32, device=self.device))

    def contacts(self) -> dict:
        out = {}
        for side, s in self.sensors.items():
            f = s.data.force_matrix_w.torch  # (envs, bodies, filtered prims, 3)
            out[side] = float(f[0].norm(dim=-1).max()) > 0.5
        return out

    def gripper_width(self) -> float:
        j = self.robot.find_joints("panda_finger_joint1")[0][0]
        return 2 * float(self.robot.data.joint_pos.torch[0, j])

    # ---- commands --------------------------------------------------------------------------
    def _set_target(self, pos_w, quat_w):
        """Grasp-point target (world) -> hand-body target in the root frame. The tool offset is
        applied here, not through the action's body_offset: with the Allegro's 13 cm lateral offset
        the action converged 15 cm off (diag 2026-10-27), so both robots drive the body directly."""
        root_p = self.robot.data.root_link_pos_w.torch[0]
        root_q = self.robot.data.root_link_quat_w.torch[0]
        body_w = pos_w - self._mu.quat_apply(quat_w, self._tool)
        p_b, q_b = self._mu.subtract_frame_transforms(root_p[None], root_q[None],
                                                       (body_w + self.scene.env_origins[0])[None], quat_w[None])
        self._action[0, :3] = p_b[0]
        self._action[0, 3:7] = q_b[0]
        self._write_hand_action()

    def _write_hand_action(self):
        """Franka: one binary channel after the 7-D pose."""
        self._action[0, 7] = -1.0 if self.gripper_closed else 1.0

    def move_to(self, pos_w, quat_w=None, tol: float = 0.006, tol_deg: float = 4.0, timeout_s: float = 5.0) -> dict:
        """Reached means position within `tol` AND orientation within `tol_deg`: the position
        often arrives first while the hand is still 50 deg from vertical. The tolerances are tight
        because an 8 cm gripper on a 5 cm cube leaves ~1 cm per side; at 1.5 cm a pad landed on
        the cube's edge and shoved it 4-5 cm during the descent (diag 2026-10-27)."""
        torch = self._torch
        pos_w = torch.as_tensor(pos_w, dtype=torch.float32, device=self.device)
        quat_w = torch.as_tensor(quat_w if quat_w is not None else self.HAND_DOWN, dtype=torch.float32, device=self.device)
        mu = self._mu
        # Ramp the command along a straight line at 0.15 m/s so the hand tracks a line instead of
        # the IK's curved path: a stepped command made the descent swing sideways and a finger pad
        # clipped the cube on the way down (diag 2026-10-27).
        start_p, start_q = self.ee_pose()
        if float(torch.dot(start_q, quat_w)) < 0:  # same rotation, opposite sign: keep the lerp short
            start_q = -start_q
        ramp_steps = max(1, int(float((pos_w - start_p).norm()) / (0.15 * self.dt)))

        def command(k):
            a = min(1.0, k / ramp_steps)
            p_cmd = start_p + a * (pos_w - start_p)
            q_cmd = (1 - a) * start_q + a * quat_w
            return p_cmd, q_cmd / q_cmd.norm()

        p_cmd, q_cmd = command(1)
        self._set_target(p_cmd + self._comp, self._cmd_quat(q_cmd))
        # the ramp itself takes dist / 0.15 s; a fixed timeout cut the long approach from home short at
        # 1-1.4 cm and reported reached=False for a move that was still converging (showcase 2026-10-27)
        n = int(max(timeout_s, ramp_steps * self.dt + 2.5) / self.dt)
        curve = []  # error every 0.5 s: tells "still moving" from "stalled"
        for i in range(n):
            self.step()
            tip, q_meas = self.ee_pose()
            err_vec = pos_w - tip
            err = float(err_vec.norm())
            oe = float(mu.quat_error_magnitude(q_meas[None], quat_w[None]))
            if err < tol and math.degrees(oe) < tol_deg:
                for _ in range(10):  # settle before the next command
                    self.step()
                oe = float(mu.quat_error_magnitude(self.ee_pose()[1][None], quat_w[None]))
                return dict(reached=True, error_m=round(err, 4), steps=i + 1, error_curve=curve,
                            orient_err_deg=round(math.degrees(oe), 1))
            if (i + 1) % 15 == 0:
                curve.append(round(err, 3))
            # the integrators see the gap between the commanded pose and the measured one, and only
            # once the command has stopped moving: while ramping, that gap is tracking lag, not sag
            if (i + 1) % 15 == 0 and i + 1 > ramp_steps + 15:
                lag = p_cmd - tip
                q_err = mu.quat_unique(mu.quat_mul(q_cmd[None], mu.quat_inv(q_meas[None])))
                rv = mu.axis_angle_from_quat(q_err)[0]
                if float(lag.norm()) < 0.06:
                    self._comp = (self._comp + 0.8 * lag).clamp(-0.08, 0.08)
                if float(rv.norm()) < 0.45:  # ~25 deg
                    self._rot_comp = (self._rot_comp + 0.5 * rv).clamp(-0.35, 0.35)
            p_cmd, q_cmd = command(i + 2)
            self._set_target(p_cmd + self._comp, self._cmd_quat(q_cmd))
        oe = float(mu.quat_error_magnitude(self.ee_pose()[1][None], quat_w[None]))
        return dict(reached=False, error_m=round(err, 4), steps=n, error_curve=curve, orient_err_deg=round(math.degrees(oe), 1))

    def _cmd_quat(self, quat_w):
        """Desired orientation pre-rotated by the accumulated wrist-droop compensation."""
        angle = self._rot_comp.norm()
        if float(angle) < 1e-6:
            return quat_w
        q_c = self._mu.quat_from_angle_axis(angle[None], (self._rot_comp / angle)[None])
        return self._mu.quat_mul(q_c, quat_w[None])[0]

    def set_gripper(self, closed: bool, settle_s: float = 0.6):
        self.gripper_closed = closed
        self._write_hand_action()
        for _ in range(int(settle_s / self.dt)):
            self.step()

    def wait(self, seconds: float):
        for _ in range(int(seconds / self.dt)):
            self.step()


def main():
    parser = argparse.ArgumentParser(description="GraspLoop env smoke")
    add_env_args(parser)
    parser.add_argument("--json", default="_logs/env_smoke.json")
    args = parser.parse_args()
    import json, time
    from isaaclab.app import launch_simulation
    from isaaclab.envs import ManagerBasedEnv

    cfg = make_env_cfg_from_args(args)
    t0 = time.time()
    with launch_simulation(cfg, args):
        env = ManagerBasedEnv(cfg)
        g = make_grasp_env(env, args.shape, args.robot)
        info = g.reset(seed=0)
        p, q = g.ee_pose()
        before = p.tolist()
        r = g.move_to([OBJECT_XY_HOME[0], OBJECT_XY_HOME[1], TABLE_TOP + 0.25])
        after = g.ee_pose()[0].tolist()
        verdict = dict(script="agent/env.py", shape=args.shape, reset=info, ee_before=before, ee_after=after,
                       move=r, object_rise_m=g.object_rise(), contacts=g.contacts(), gripper_width=g.gripper_width(),
                       wall_s=round(time.time() - t0, 1))
        verdict["checks"] = dict(ik_reached=r["reached"], object_still=abs(g.object_rise()) < 0.01)
        verdict["pass"] = all(verdict["checks"].values())
        env.close()
    with open(args.json, "w") as f:
        json.dump(verdict, f, indent=1)
    print("[env_smoke]", json.dumps(verdict["checks"]), "pass" if verdict["pass"] else "FAIL")


if __name__ == "__main__":
    main()
