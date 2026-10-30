"""The write -> run -> judge -> repair loop: Nemotron programs the grasp, the sim grades it.

One scenario = one (shape, seed). Every attempt resets the sim to the same start, runs the
model's program through the sandbox, judges it (judges/physics.py, or the env's own judge hook),
and (if another attempt is allowed) feeds a compact, factual account of what happened back to the
model. Feedback conditions:
  none     - one shot, no repair (condition B)
  physics  - measured feedback: judge verdict, API trace, errors (condition C)
  vision   - physics plus the vision reviewer's diagnosis (condition D), via `reviewer`
  hints    - physics plus a Tavily web search on the failure mode (condition E), via `hints`

Caller: eval/run_loop.py, eval/run_grid.py. Returns an episode record (see run_scenario).
"""
from __future__ import annotations

import json
import time

from agent import sandbox
from agent.env import GraspEnv
from agent.graspapi import GraspAPI, api_doc
from agent.nemotron import TokenFactory, extract_code
from judges.physics import judge

SYSTEM = ("You are a robot programmer. You write short, plain Python programs that drive a simulated robot "
          "through a small API. Think about the geometry (object size, where the fingers close, the wrist "
          "range), then reply with exactly one fenced ```python code block containing the whole program. "
          "Never invent functions that are not in the API. Never claim an action worked; the simulator reports that.")

TASK = "Pick up the object from the table and hold it in the air."


def initial_prompt(obj: dict, doc: str, task: str = TASK) -> str:
    return (f"{doc}\n\nTask: {task}\n\nThe scene right now:\n{json.dumps(obj)}\n\n"
            "Write the program. One fenced python block, nothing else after it.")


def make_api(genv):
    return genv.make_api() if hasattr(genv, "make_api") else GraspAPI(genv)


def run_judge(run: dict, genv) -> dict:
    return genv.judge(run) if hasattr(genv, "judge") else judge(run, genv)


def make_feedback(genv, run: dict, verdict: dict, n: int, max_attempts: int) -> str:
    return genv.feedback_text(run, verdict, n, max_attempts) if hasattr(genv, "feedback_text") else feedback_text(run, verdict, n, max_attempts)


def reference_program(genv, robot: str) -> str:
    from agent.graspapi import REFERENCE_PROGRAMS
    if getattr(genv, "SCENARIO", "").startswith("place_"):
        from agent.place import REFERENCE_PROGRAM_PLACE
        return REFERENCE_PROGRAM_PLACE
    return getattr(genv, "REFERENCE_PROGRAM", None) or REFERENCE_PROGRAMS[robot]


def close_geometry(res: dict) -> list[str]:
    """Where the fingers closed relative to the object, in words. The raw positions alone did not get the
    model to lower its grasp: it closed 5 cm above the cube three times in a row (showcase 2026-10-27)."""
    if "dz_m" not in res:
        return []
    out, dz, dxy = [], res["dz_m"], res["dxy_m"]
    touched = any(res.get("contacts", {}).values())
    top, palm = res.get("object_top_z"), res.get("palm_z")
    if dz > 0.01:
        above_top = dz - (top - res["object_pos"][2]) if top is not None else None
        out.append(f"the fingertips closed {dz * 100:.1f} cm ABOVE the object's centre"
                   + (f", {above_top * 100:.1f} cm above its top face: they closed on air" if above_top is not None and above_top > 0 else "")
                   + ". To grasp, the grasp point must be at the object's height when the gripper closes.")
    elif dz < -0.01:
        out.append(f"the fingertips closed {-dz * 100:.1f} cm BELOW the object's centre.")
    if dxy > 0.02:
        out.append(f"the fingertips were {dxy * 100:.1f} cm to the side of the object's centre when closing.")
    if touched and top is not None and palm is not None and palm < top + 0.005:
        out.append(f"the palm face (z={palm:.3f}) was at or below the object's top (z={top:.3f}): the palm is resting on "
                   f"the object, which stops it rising. The grasp must sit higher on a tall object.")
    return out


def feedback_text(run: dict, verdict: dict, attempt: int, max_attempts: int) -> str:
    """What the simulator measured, in words a programmer can act on. No success label leaks beyond pass/fail."""
    lines = [f"Attempt {attempt} of {max_attempts} FAILED: {verdict['failure']}. {verdict.get('detail', '')}"]
    if run["status"] == "invalid":
        lines.append("The program was rejected before running: " + "; ".join(run["problems"]))
    elif run["exception"]:
        lines.append(f"The program raised: {run['exception']}")
        if run["traceback"]:
            lines.append(run["traceback"].strip())
    events = []
    moved_before = 0.0
    for r in run.get("trace", []):
        res = r["result"]
        # the object moving during a call that was not a lift means the hand hit it: the straight path from home
        # swept a tall box over and the old feedback never said so (showcase 2026-10-27)
        moved = r.get("moved_xy_m", 0.0)
        pushed = moved - moved_before > 0.015 and r["call"] in ("move_to", "close_gripper", "open_gripper", "grasp", "wait")
        moved_before = moved
        if r["call"] == "move_to":
            events.append(f"t={r['t']}s move_to(pos={r['args']['pos']}, quat={r['args'].get('quat')}) -> reached={res['reached']}, "
                          f"position error {res['error_m']} m, hand tilt error {res.get('orient_err_deg')} deg; object rise {r['rise_m']} m")
        elif r["call"] == "lift":
            events.append(f"t={r['t']}s lift({r['args']['dz']}) -> reached={res['reached']}, error {res['error_m']} m; object rise {r['rise_m']} m; "
                          f"fingertips touching: {r['contacts']}")
        elif r["call"] == "close_gripper":
            events.append(f"t={r['t']}s close_gripper() -> gripper width {res['width']} m, fingertips touching {res['contacts']}, "
                          f"fingertip point at {res['fingertip_pos']}, object centre at {res['object_pos']}")
            events.extend("    " + s for s in close_geometry(res))
        elif r["call"] == "open_gripper":
            events.append(f"t={r['t']}s open_gripper() -> width {res['width']} m")
        elif r["call"] == "log":
            events.append(f"t={r['t']}s log: {r['args']['message']}")
        elif r["call"] in ("object_height", "fingers_in_contact", "gripper_width"):
            events.append(f"t={r['t']}s {r['call']}() -> {res}")
        if pushed and r["call"] in ("move_to", "wait", "grasp", "open_gripper"):
            events.append(f"    during this call the object was pushed {moved * 100:.1f} cm from where it started: the hand "
                          f"collided with it on the way. Approach from straight above the object before descending.")
        elif pushed and r["call"] == "close_gripper":
            events.append(f"    closing pushed the object {moved * 100:.1f} cm sideways instead of holding it.")
    if events:
        lines.append("Measured during the run:")
        lines.extend("  " + e for e in events[:25])
    lines.append(f"At the end: object rise {verdict.get('final_rise_m')} m (needs >= 0.10 m held 0.5 s), "
                 f"gripper closed={verdict.get('gripper_closed')}, fingertips touching {verdict.get('contacts')}.")
    if run.get("stdout"):
        lines.append("Program output: " + run["stdout"].strip()[-500:])
    lines.append("Fix the program. Reply with the complete corrected program in one fenced python block.")
    return "\n".join(lines)


def run_scenario(genv: GraspEnv, seed: int, tf: TokenFactory, max_attempts: int = 3, feedback: str = "physics",
                 reviewer=None, on_attempt=None, hints=None) -> dict:
    """Run up to `max_attempts` programs for one seeded start. `reviewer(genv, run, verdict, attempt) -> dict|None`
    (keys text, cost_usd) adds a vision diagnosis to the feedback when feedback == 'vision'. `hints(obj, measured,
    verdict, robot, task) -> dict|None` (agent/hints.py, Tavily) adds a web answer when feedback == 'hints' (condition E).
    `on_attempt(attempt_record)` is a hook for recording media."""
    t0 = time.time()
    start = genv.reset(seed=seed)
    api0 = make_api(genv)
    obj = api0.scenario() if hasattr(api0, "scenario") else api0.get_object()
    doc = genv.api_doc() if hasattr(genv, "api_doc") else api_doc(genv)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": initial_prompt(obj, doc, task=getattr(genv, "TASK", TASK))}]
    rec = dict(seed=seed, start=start, object=obj, robot=genv.ROBOT, condition=feedback, model=tf.model, max_attempts=max_attempts,
               attempts=[], success=False, attempts_used=0, cost_usd=0.0)
    for n in range(1, max_attempts + 1):
        reply = tf.chat(messages, tag=f"gen:{feedback}:a{n}")
        truncated = 0
        if reply["finish"] == "length":  # ran out of tokens while reasoning: a model-side event, retry once, bigger
            truncated = 1
            rec["cost_usd"] += reply["cost_usd"]
            reply = tf.chat(messages, max_tokens=2 * tf.max_tokens, tag=f"gen:{feedback}:a{n}:retry")
            truncated += reply["finish"] == "length"
        code = extract_code(reply["content"])
        if n > 1:  # each attempt starts from the very same scenario
            genv.reset(seed=seed)
        api = make_api(genv)
        run = sandbox.run(code, api)
        verdict = run_judge(run, genv)
        frames = []
        rec_ = getattr(genv, "_recorder", None)
        if rec_ is not None:  # film every attempt, successes included
            rec_.final()
            rec_.tag = f"{getattr(genv, 'SCENARIO', genv.shape)}_s{seed}_{feedback}_a{n}"  # place_cube, nav, ... like the grid's scripted tags
            frames = rec_.save()
        att = dict(n=n, code=code, frames=frames, video=rec_.last_video if rec_ is not None else None, reply_usage=reply["usage"], reply_latency_s=reply["latency_s"], cost_usd=reply["cost_usd"],
                   finish=reply["finish"], truncated=truncated, run_status=run["status"], exception=run["exception"], problems=run["problems"],
                   stdout=run["stdout"], verdict=verdict, trace=run["trace"], sim_steps=genv.steps, feedback=None, vision=None, hints=None)
        rec["cost_usd"] += reply["cost_usd"]
        rec["attempts_used"] = n
        if on_attempt:
            on_attempt(att)
        if verdict["success"]:
            rec["success"] = True
            rec["attempts"].append(att)
            break
        if feedback == "none" or n == max_attempts:
            rec["attempts"].append(att)
            break
        fb = make_feedback(genv, run, verdict, n, max_attempts)
        if feedback == "vision" and reviewer is not None:
            review = reviewer(genv, run, verdict, n)
            att["vision"] = review
            if review and review.get("text"):
                fb = fb.replace("Fix the program.", "A reviewer watched the attempt on camera and says: "
                                + review["text"].strip() + "\nFix the program.")
                rec["cost_usd"] += review.get("cost_usd", 0.0)
        if feedback == "hints" and hints is not None:
            h = hints(obj, fb, verdict, robot=genv.ROBOT, task=getattr(genv, "TASK", TASK))
            att["hints"] = h
            if h and h.get("text"):
                fb = fb.replace("Fix the program.", "A web search on this failure mode (Tavily) says: "
                                + h["text"].strip() + "\nFix the program.")
        att["feedback"] = fb
        rec["attempts"].append(att)
        messages.append({"role": "assistant", "content": f"```python\n{code}\n```"})
        messages.append({"role": "user", "content": fb})
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec
