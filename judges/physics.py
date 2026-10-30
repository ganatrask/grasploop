"""Deterministic success judge for a grasp-and-lift episode.

Reads the API trace and the live env after the program has returned, then runs the hold check
itself: the gripper stays as the program left it and the object must stay >= MIN_RISE above its
start for HOLD_S. Produces the verdict that is the benchmark label; the vision reviewer never
sees it.

Caller: agent/loop.py (run_judge, used by every runner). Output: see judge() docstring.
"""
from __future__ import annotations

from agent.env import TABLE_TOP, GraspEnv

MIN_RISE = 0.10
HOLD_S = 0.5

FAILURES = ("invalid_program", "program_error", "budget_exhausted", "ik_not_reached", "object_missed", "no_contact",
            "insufficient_lift", "slipped", "dropped_in_hold", "object_off_table", "gripper_open")


def judge(run: dict, genv: GraspEnv) -> dict:
    """Return dict(success, failure, final_rise_m, max_rise_m, hold_min_rise_m, contacts, gripper_closed, detail,
    n_calls, unreached_moves).

    `run` is the sandbox result; `genv` the env the program drove (still live).
    """
    trace = run.get("trace", [])
    rises = [r["rise_m"] for r in trace] + [genv.object_rise()]
    max_rise = max(rises) if rises else 0.0
    moves = [r for r in trace if r["call"] in ("move_to", "lift")]
    # a sub-2 cm shortfall is not why a grasp failed; only count real misses
    unreached = [r for r in moves if not (r["result"] or {}).get("reached", False) and (r["result"] or {}).get("error_m", 1) > 0.02]
    touched = any(any(r["contacts"].values()) for r in trace)
    # a close with the object between the pads (width well above fully-closed, some contact)
    grasped = any(r["call"] == "close_gripper" and r["result"]["width"] > 0.012 and any(r["result"]["contacts"].values())
                  for r in trace)
    out = dict(success=False, failure=None, final_rise_m=None, max_rise_m=round(max_rise, 4), hold_min_rise_m=None,
               contacts=genv.contacts(), gripper_closed=genv.gripper_closed, n_calls=len(trace), unreached_moves=len(unreached))

    # 1. program-level failures first
    if run["status"] == "invalid":
        out.update(failure="invalid_program", detail="; ".join(run["problems"])); return out
    if run["status"] in ("error", "timeout"):
        out.update(failure="program_error", detail=run["exception"]); return out
    if run["status"] == "budget":
        out.update(failure="budget_exhausted", detail=run["exception"]); return out

    # 2. the hold: keep stepping with the program's last command, watch the object
    hold_rises = []
    for _ in range(int(HOLD_S / genv.dt)):
        genv.step()
        hold_rises.append(genv.object_rise())
    final = genv.object_rise()
    out.update(final_rise_m=round(final, 4), hold_min_rise_m=round(min(hold_rises), 4), contacts=genv.contacts())
    obj_z = float(genv.object_pose()[0][2])

    if obj_z < TABLE_TOP - 0.05:
        out.update(failure="object_off_table", detail=f"object centre at z={obj_z:.3f}"); return out
    if min(hold_rises) >= MIN_RISE and genv.gripper_closed:
        out.update(success=True, detail=f"held {HOLD_S} s at >= {min(hold_rises):.3f} m"); return out

    # 3. why not
    if not genv.gripper_closed and max_rise >= MIN_RISE:
        out.update(failure="gripper_open", detail="object was lifted but the program ended with the gripper open")
    elif max_rise >= MIN_RISE and final < MIN_RISE:
        name = "dropped_in_hold" if (hold_rises and hold_rises[0] >= MIN_RISE) else "slipped"
        out.update(failure=name, detail=f"peak rise {max_rise:.3f} m, final {final:.3f} m")
    elif max_rise >= 0.01:
        out.update(failure="insufficient_lift", detail=f"peak rise {max_rise:.3f} m < {MIN_RISE} m")
    elif grasped:
        out.update(failure="slipped", detail="the object was between the closed fingers but left the hand when lifting")
    elif unreached:
        r = unreached[0]
        out.update(failure="ik_not_reached", detail=f"{r['call']} to {r['args'].get('pos') or r['args']} ended {r['result']['error_m']:.3f} m short")
    elif not touched:
        out.update(failure="object_missed", detail="no fingertip ever touched the object")
    else:
        out.update(failure="no_contact", detail="fingers touched the object but did not hold it when closing")
    return out
