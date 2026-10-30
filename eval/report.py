"""Turn grid JSONs into the judge-facing report: a summary table and a static trial viewer.

    python3 eval/report.py _logs/grid/*.json --out _logs/report

Writes <out>/summary.md and <out>/index.html. Every number comes from the saved episode records;
frames are linked by relative path, so the folder can be opened from a file:// URL or zipped.
Plain stdlib: runs under any interpreter.
"""
from __future__ import annotations

import argparse
import html
import json
import os


def load(paths):
    grids = []
    for p in paths:
        with open(p) as f:
            d = json.load(f)
        d["_path"] = p
        grids.append(d)
    return grids


def summary_md(grids) -> str:
    rows = ["| shape | model | condition | success | 95% CI | mean attempts | $ total | $ / success |",
            "|---|---|---|---|---|---|---|---|"]
    for g in grids:
        for cond, s in g["summary"].items():
            if "successes" not in s:  # the "reviewer" entry from --review-all
                continue
            cps = s.get("cost_per_success_usd")
            rows.append(f"| {g['shape']} | {g['model'].split('/')[-1]} | {cond} | {s['successes']}/{s['n']} ({s['rate']:.0%}) | "
                        f"{s['ci95'][0]:.2f}–{s['ci95'][1]:.2f} | {s['mean_attempts']} | {s['cost_usd']:.4f} | "
                        f"{'—' if cps is None else f'{cps:.4f}'} |")
    return "\n".join(rows) + "\n"


def _rel(path, out):
    return os.path.relpath(path, out) if path else ""


def _frames_strip(frames, out, k=4):
    if not frames:
        return "<em>no frames</em>"
    idx = sorted(set([0, len(frames) // 3, 2 * len(frames) // 3, len(frames) - 1]))[:k]
    return "".join(f'<img src="{html.escape(_rel(frames[i], out))}" width="240">' for i in idx)


def episode_cards(g, out) -> str:
    parts = []
    for cond, eps in g["episodes"].items():
        for e in eps:
            ok = e.get("success")
            parts.append(f'<details class="ep {"ok" if ok else "fail"}"><summary><b>{html.escape(g["shape"])}</b> seed {e["seed"]} · '
                         f'{html.escape(cond)} · {"PASS" if ok else "fail"} · {e.get("attempts_used", 1)} attempt(s) · ${e.get("cost_usd", 0):.4f}</summary>')
            if e.get("infra_error"):  # an API outage, kept out of the counts; shown so nothing is hidden
                parts.append(f'<p><em>API error, not counted: {html.escape(e["infra_error"])}</em></p></details>')
                continue
            attempts = e.get("attempts") or [e]
            for a in attempts:
                v = a.get("verdict", {})
                code = a.get("code") or e.get("code") or ""
                parts.append('<div class="att"><div class="row">')
                parts.append(f'<div class="frames">{_frames_strip(a.get("frames", []), out)}</div>')
                parts.append(f'<pre class="code">{html.escape(code)}</pre></div>')
                parts.append(f'<p><b>Physics judge:</b> {"success" if v.get("success") else html.escape(str(v.get("failure")))} — '
                             f'{html.escape(str(v.get("detail", "")))} (final rise {v.get("final_rise_m")} m, contacts {html.escape(str(v.get("contacts")))})</p>')
                vis = a.get("vision")
                if vis and vis.get("structured"):
                    s = vis["structured"]
                    parts.append(f'<p><b>Vision reviewer:</b> visual_success={s.get("visual_success")} · {html.escape(str(s.get("failure_type")))} · '
                                 f'{html.escape(s.get("evidence", ""))} <i>Suggested:</i> {html.escape(s.get("suggested_correction", ""))}</p>')
                if a.get("feedback"):
                    parts.append(f'<details><summary>feedback sent to the model</summary><pre>{html.escape(a["feedback"])}</pre></details>')
                parts.append("</div>")
            parts.append("</details>")
    return "\n".join(parts)


CSS = """body{font-family:system-ui,sans-serif;margin:2rem;max-width:1200px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}
.ep{margin:8px 0;border:1px solid #ddd;padding:6px}.ep.ok>summary{color:#1a7f37}.ep.fail>summary{color:#b42318}.att{border-top:1px dashed #ccc;padding:6px 0}
.row{display:flex;gap:12px;align-items:flex-start}.frames img{margin:2px;border:1px solid #999}.code{flex:1;background:#f6f8fa;padding:8px;font-size:12px;overflow:auto;max-height:320px}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grids", nargs="+")
    ap.add_argument("--out", default="_logs/report")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    grids = load(a.grids)
    grids = [g for g in grids if "summary" in g]  # .partial.json checkpoints carry episodes only
    md = summary_md(grids)
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write(md)
    table = "<table>" + "".join(
        "<tr>" + "".join(f"<td>{html.escape(c.strip())}</td>" for c in r.strip("|").split("|")) + "</tr>"
        for r in md.strip().splitlines() if not r.startswith("|---")) + "</table>"
    body = ["<h1>GraspLoop results</h1>", table]
    for g in grids:
        body.append(f"<h2>{html.escape(g['shape'])} · {html.escape(g['model'])} · reasoning {html.escape(str(g.get('reasoning')))} · "
                    f"seeds {g['seeds'][0]}–{g['seeds'][-1]} · ${g['total_cost_usd']:.4f} · {g['wall_s']} s</h2>")
        body.append(episode_cards(g, a.out))
    with open(os.path.join(a.out, "index.html"), "w") as f:
        f.write(f"<!doctype html><meta charset='utf-8'><title>GraspLoop</title><style>{CSS}</style>" + "\n".join(body))
    print(md)
    print(f"-> {a.out}/index.html")


if __name__ == "__main__":
    main()
