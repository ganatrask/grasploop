"""Web hints for the repair loop (condition E): after a failed attempt, one Tavily search on the judge's
failure mode, and Tavily's answer goes into the feedback next to the measurements.

Tavily is Nebius's search API for agents. The key comes from TAVILY_API_KEY or from
~/.tavily/config.json (written by `tvly login`). One basic search per distinct
query per process (robot, task, object shape, and the feedback's first line: attempt number, failure
name, judge detail); a repeated query comes from the cache, so an 8-seed grid costs a handful of credits.

The injected text is Tavily's `answer` (its summary of the top results) plus the source titles, trimmed
to MAX_CHARS. The judge's measured feedback stays first; the hint is an addendum, exactly like the
vision reviewer's diagnosis in condition D, so E − C isolates what web retrieval adds.
"""
from __future__ import annotations

import json
import os
import time

import requests

URL = "https://api.tavily.com/search"
MAX_CHARS = 700
CONFIG = os.path.expanduser("~/.tavily/config.json")


def load_key() -> str:
    key = os.environ.get("TAVILY_API_KEY")
    if not key and os.path.exists(CONFIG):
        with open(CONFIG) as f:
            key = json.load(f).get("api_key")
    if not key:
        raise SystemExit("hints: set TAVILY_API_KEY or run `tvly login` (no ~/.tavily/config.json)")
    return key


def describe(obj: dict) -> str:
    keep = {k: v for k, v in obj.items() if k in ("shape", "kind", "size", "size_m", "dims", "dims_m", "radius", "radius_m",
                                                   "height", "height_m", "mass", "mass_kg", "color")}
    return ", ".join(f"{k} {v}" for k, v in (keep or obj).items())[:200]


class WebHints:
    def __init__(self, key: str | None = None, max_results: int = 3, depth: str = "basic"):
        self.key = key or load_key()
        self.max_results, self.depth = max_results, depth
        self.cache: dict[str, dict] = {}
        self.calls = 0

    def query_for(self, obj: dict, measured: str, verdict: dict, robot: str, task: str) -> str:
        first = measured.strip().split("\n")[0][:240]  # the feedback's first line: attempt, failure name, judge detail
        return (f"{robot} robot, task: {task}. Object: {describe(obj)}. The attempt failed ({verdict.get('failure')}): {first} "
                f"How should the approach pose, closing height or grip be changed?")

    def __call__(self, obj: dict, measured: str, verdict: dict, robot: str, task: str) -> dict | None:
        q = self.query_for(obj, measured, verdict, robot, task)
        if q in self.cache:
            return dict(self.cache[q], cached=True)
        t0 = time.time()
        try:
            r = requests.post(URL, json=dict(api_key=self.key, query=q, search_depth=self.depth, include_answer=True,
                                             max_results=self.max_results), timeout=30)
            r.raise_for_status()
            j = r.json()
        except Exception as e:  # a search failure must not end the attempt: the loop continues on measurements alone
            return dict(text=None, query=q, answer=None, sources=[], latency_s=round(time.time() - t0, 1), cached=False, error=str(e)[:200])
        self.calls += 1
        answer = (j.get("answer") or "").strip()
        sources = [dict(title=(s.get("title") or "")[:90], url=s.get("url")) for s in j.get("results", [])[: self.max_results]]
        text = answer
        if sources:
            text += " Sources: " + "; ".join(s["title"] for s in sources if s["title"])
        out = dict(text=text[:MAX_CHARS] if text else None, query=q, answer=answer, sources=sources,
                   latency_s=round(time.time() - t0, 1), cached=False)
        self.cache[q] = out
        return out
