"""Kuka iiwa + Allegro four-finger hand, on NVIDIA's Isaac-Lift-KukaAllegro scene.

Geometry measured at the home pose (diag 2026-10-27): the fingers run along the palm's +x axis,
the palm normal is +z, the fingertips sit at palm-frame (0.15, -0.05..0.05, 0.08) and the thumb tip
at (0.03, 0.00, 0.12). The grasp volume between them is GRASP_OFFSET; that point is what move_to()
drives, so "put the grasp point at the object centre, close" is the same program as for the Franka.
Hand down = palm normal to world -z with the fingers along world +y: a 180 deg turn about (1,1,0)/sqrt2.

Used by agent/env.py (make_env_cfg / make_grasp_env). Exposes AllegroEnv, allegro_actions_cfg(),
tune_allegro_actuators(), POSTURES.
"""
from __future__ import annotations

import math

from agent.env import GraspEnv

FINGERS = ("index", "middle", "ring", "thumb")
FINGER_JOINTS = [f"{f}_joint_{i}" for f in FINGERS for i in range(4)]  # the task's joint order
GRASP_OFFSET = (0.09, 0.0, 0.10)
R = 1 / math.sqrt(2)
HAND_DOWN_ALLEGRO = (R, R, 0.0, 0.0)  # xyzw

# joint targets [index0..3, middle0..3, ring0..3, thumb0..3]: open hand and the fully closed pose of
# each grasp. closure in [0, 1] interpolates open -> closed per joint.
OPEN = [0.0, 0.1, 0.1, 0.1] * 3 + [1.37, 0.3, 0.1, 0.1]
POSTURES = {
    # all three fingers curl, thumb flexes across the palm. Thumb (1.5, 0.5, 1.3, 1.3) was the only one
    # of four poses that held the cube in the 12-combination sweep of 2026-10-27 (19.8 cm lift, four
    # fingertips in contact); (1.5, 0.9, 1.0, 1.0) let the fingers push the cube past the thumb.
    "power": [0.0, 1.4, 1.4, 1.2] * 3 + [1.5, 0.5, 1.3, 1.3],
    # index and thumb meet, the others stay out of the way
    "pinch": [0.0, 1.2, 1.3, 1.0] + [0.0, 0.1, 0.1, 0.1] * 2 + [1.5, 0.7, 0.9, 0.9],
    # index + middle against the thumb
    "tripod": [0.0, 1.2, 1.3, 1.0] * 2 + [0.0, 0.1, 0.1, 0.1] + [1.5, 0.8, 0.9, 0.9],
}


def allegro_actions_cfg(ik_lambda: float):
    from isaaclab.controllers import DifferentialIKControllerCfg
    from isaaclab.envs import mdp
    from isaaclab.utils import configclass

    @configclass
    class ActionsCfg:
        # Drive the arm's last link, not palm_link: for that fixed-joint body the action's Jacobian moved
        # the hand the wrong way even on a pure +10 cm request (diag 2026-10-27). AllegroEnv carries the
        # constant link_7 -> palm transform so programs still see the palm and the grasp point.
        arm_action = mdp.DifferentialInverseKinematicsActionCfg(
            asset_name="robot", joint_names=["iiwa7_joint_[1-7]"], body_name="iiwa7_link_7",
            controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls",
                                                   ik_params={"lambda_val": ik_lambda}),
            # no body_offset: GraspEnv applies GRASP_OFFSET itself (env._set_target)
        )
        hand_action = mdp.JointPositionActionCfg(asset_name="robot", joint_names=FINGER_JOINTS, use_default_offset=False)

    return ActionsCfg


ALLEGRO_GAIN_SCALE = 8.0


def tune_allegro_actuators(robot_cfg, gain_scale: float = 1.0) -> None:
    """The lift task's Kuka gains (arm stiffness 200) are RL gains: under them the arm sank 13 cm at
    home and no IK target was reached; at x8 (1600, the Franka's 600 with gravity off being the
    reference) every hand-down target converged to 6 mm (diag 2026-10-27). `gain_scale` multiplies
    that default, so 1.0 means x8 overall."""
    s = ALLEGRO_GAIN_SCALE * gain_scale
    for name, act in robot_cfg.actuators.items():
        if isinstance(act.stiffness, dict):
            act.stiffness = {k: v * s for k, v in act.stiffness.items()}
            act.damping = {k: v * s ** 0.5 for k, v in act.damping.items()}
        elif isinstance(act.stiffness, (int, float)):
            act.stiffness, act.damping = act.stiffness * s, act.damping * s ** 0.5


class AllegroEnv(GraspEnv):
    ROBOT = "allegro"
    HAND_BODY = "iiwa7_link_7"  # the IK body; palm_link is a fixed-joint child of it
    TOOL_OFFSET = GRASP_OFFSET  # in the PALM frame; converted to the link_7 frame at init
    HAND_DOWN = HAND_DOWN_ALLEGRO
    SENSOR_NAMES = {f: f"{f}_link_3_object_s" for f in FINGERS}
    HAND_DESC = ("a four-finger Allegro hand (index, middle, ring, thumb). The grasp point is the volume between "
                 "the fingertips and the thumb, about 10 cm below the palm; the fingers curl towards the thumb. "
                 "At yaw 0 the fingers point along world +y and the thumb opposes them from -y")

    def __init__(self, env, shape: str):
        super().__init__(env, shape)
        import torch
        self._hand_names = list(self.env.action_manager.get_term("hand_action")._joint_names)
        order = [FINGER_JOINTS.index(j) for j in self._hand_names]  # action slot -> POSTURES index
        self._open = torch.tensor([OPEN[i] for i in order], device=self.device)
        self._postures = {k: torch.tensor([v[i] for i in order], device=self.device) for k, v in POSTURES.items()}
        self.posture, self.closure = "power", 0.0
        # constant transform link_7 -> palm_link (fixed joints), measured once from the spawn pose
        mu = self._mu
        P, Q = self.robot.data.body_link_pos_w.torch[0], self.robot.data.body_link_quat_w.torch[0]
        pi = self.robot.find_bodies("palm_link")[0][0]
        self._p_rel, self._q_rel = mu.subtract_frame_transforms(P[self._hand_idx][None], Q[self._hand_idx][None],
                                                                P[pi][None], Q[pi][None])
        self._p_rel, self._q_rel = self._p_rel[0], self._q_rel[0]
        # the grasp point in the link_7 frame: p_rel + R_rel * GRASP_OFFSET
        self._tool = self._p_rel + mu.quat_apply(self._q_rel, torch.tensor(GRASP_OFFSET, device=self.device))

    def ee_pose(self):
        """Grasp point (world) and the PALM orientation, so hand-down targets compare like with like."""
        p7 = self.robot.data.body_link_pos_w.torch[0, self._hand_idx] - self.scene.env_origins[0]
        q7 = self.robot.data.body_link_quat_w.torch[0, self._hand_idx]
        tip = p7 + self._mu.quat_apply(q7, self._tool)
        return tip, self._mu.quat_mul(q7[None], self._q_rel[None])[0]

    def palm_pos(self):
        p7 = self.robot.data.body_link_pos_w.torch[0, self._hand_idx] - self.scene.env_origins[0]
        q7 = self.robot.data.body_link_quat_w.torch[0, self._hand_idx]
        return p7 + self._mu.quat_apply(q7, self._p_rel)

    def _set_target(self, pos_w, quat_palm_w):
        """Palm target -> link_7 target (q7 = q_palm * q_rel^-1), then root frame."""
        mu = self._mu
        q7 = mu.quat_mul(quat_palm_w[None], mu.quat_inv(self._q_rel[None]))[0]
        root_p = self.robot.data.root_link_pos_w.torch[0]
        root_q = self.robot.data.root_link_quat_w.torch[0]
        body_w = pos_w - mu.quat_apply(q7, self._tool)
        p_b, q_b = mu.subtract_frame_transforms(root_p[None], root_q[None], (body_w + self.scene.env_origins[0])[None], q7[None])
        self._action[0, :3] = p_b[0]
        self._action[0, 3:7] = q_b[0]
        self._write_hand_action()

    def _write_hand_action(self):
        target = self._open + self.closure * (self._postures[self.posture] - self._open)
        self._action[0, 7:7 + len(self._hand_names)] = target

    def set_hand(self, posture: str, closure: float, settle_s: float = 0.8):
        if posture not in self._postures:
            raise ValueError(f"unknown grasp {posture!r}; choose one of {sorted(self._postures)}")
        self.posture, self.closure = posture, max(0.0, min(1.0, float(closure)))
        self.gripper_closed = self.closure > 0.5
        self._write_hand_action()
        for _ in range(int(settle_s / self.dt)):
            self.step()

    def set_gripper(self, closed: bool, settle_s: float = 0.8):
        self.set_hand(self.posture, 1.0 if closed else 0.0, settle_s)

    def gripper_width(self) -> float:
        """No jaw width on a hand: report closure (0 open .. 1 fully closed) instead."""
        return round(self.closure, 3)

    def contacts(self) -> dict:
        out = {}
        for f, s in self.sensors.items():
            fm = s.data.force_matrix_w.torch
            out[f] = float(fm[0].norm(dim=-1).max()) > 0.5
        return out
