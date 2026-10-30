"""Validate and run a generated grasp program against a GraspAPI.

Static check first (AST allow-list), then exec in-process with a stripped builtins table, a
wall-clock alarm and the API's own step budget. In-process is deliberate: the program has to
step the simulator, which lives in this process. The isolation unit is therefore the worker
process that runs one batch of episodes, not the episode.

Callers: eval/gate_t1.py, agent/loop.py. Output of run(): see RunResult below.
"""
from __future__ import annotations

import ast
import builtins
import io
import signal
import traceback
from contextlib import redirect_stdout

from agent.graspapi import BudgetExceeded, GraspAPI

FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Yield,
                   ast.YieldFrom, ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith, ast.Try, ast.TryStar,
                   ast.Lambda)
FORBIDDEN_NAMES = {"exec", "eval", "open", "compile", "__import__", "getattr", "setattr", "delattr", "globals",
                   "locals", "vars", "input", "breakpoint", "exit", "quit", "type", "object", "super", "memoryview"}
SAFE_BUILTINS = {n: getattr(builtins, n) for n in (
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max", "min", "print", "range",
    "round", "sorted", "str", "sum", "tuple", "zip", "isinstance", "True", "False", "None", "ValueError",
    "RuntimeError", "Exception") if hasattr(builtins, n)}
MAX_LINES = 120


def validate(code: str) -> list[str]:
    """Return a list of problems; empty means the program may run."""
    problems = []
    if len(code.splitlines()) > MAX_LINES:
        problems.append(f"program longer than {MAX_LINES} lines")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error: {e.msg} (line {e.lineno})"]
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            problems.append(f"{type(node).__name__} is not allowed (line {getattr(node, 'lineno', '?')})")
        elif isinstance(node, ast.While):
            # a while loop that never calls the API cannot be stopped by the step budget
            problems.append(f"while loops are not allowed; use for i in range(n) (line {node.lineno})")
        elif isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or node.id.startswith("__")):
            problems.append(f"name {node.id!r} is not allowed (line {node.lineno})")
        elif isinstance(node, ast.Attribute):
            base = node.value
            if node.attr.startswith("_"):
                problems.append(f"private attribute {node.attr!r} is not allowed (line {node.lineno})")
            elif not (isinstance(base, ast.Name) and base.id == "math") and node.attr not in (
                    "get", "keys", "values", "items", "append", "copy", "index"):
                problems.append(f"attribute access .{node.attr} is not allowed; use dict['key'] (line {node.lineno})")
    return sorted(set(problems))


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def run(code: str, api: GraspAPI, wall_s: float = 120.0) -> dict:
    """Execute a validated program. Never raises; everything lands in the returned dict.

    RunResult keys: status in {ok, invalid, error, budget, timeout}, problems (validate output),
    exception (type: message), traceback (last 3 frames of the program), stdout, trace (API calls).
    """
    problems = validate(code)
    if problems:
        return dict(status="invalid", problems=problems, exception=None, traceback="", stdout="", trace=[])
    ns = {"__builtins__": SAFE_BUILTINS, **api.namespace()}
    out = io.StringIO()
    status, exc, tb = "ok", None, ""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, wall_s)
    try:
        with redirect_stdout(out):
            exec(compile(code, "<program>", "exec"), ns)
    except _Timeout:
        status, exc = "timeout", f"TimeoutError: program exceeded {wall_s:.0f} s of wall-clock time"
    except BudgetExceeded as e:
        status, exc = "budget", f"BudgetExceeded: {e}"
    except Exception as e:  # noqa: BLE001 - every program error becomes feedback
        status, exc = "error", f"{type(e).__name__}: {e}"
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == "<program>"]
        tb = "".join(traceback.format_list(frames[-3:]))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
    return dict(status=status, problems=[], exception=exc, traceback=tb, stdout=out.getvalue()[-2000:], trace=api.trace)
