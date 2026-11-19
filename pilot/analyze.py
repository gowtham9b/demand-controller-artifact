"""Summarize pilot results: scores per condition, paired bootstrap CIs, behaviour.

Usage: python analyze.py   (reads eval_reports/eval_report_pilot_C*.csv and runs/*)
Writes results/summary.json.
"""

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent / "harness" / "eval_reports"
CONDS = ["C0", "C1", "C2"]
SELF_PROFILE = re.compile(r"cProfile|profile\.run|pstats|line_profiler|py-spy|pyinstrument|yappi|tracemalloc")
B = 10_000
TASKS = os.environ.get("DC_TASKS", str(HERE / "tasks_final.txt"))
OUT = HERE / os.environ.get("DC_RESULTS", "results")


def overall(sr: np.ndarray) -> float:
    sr = np.clip(sr, 0.001, None)
    return len(sr) / np.sum(1 / sr)


def session(path: Path) -> dict:
    """Tool calls, shell commands and token usage from a Cursor CLI stream-json log."""
    tools, cmds, usage = 0, [], {}
    for line in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "tool_call" and e.get("subtype") == "started":
            tools += 1
            for v in (e.get("tool_call") or {}).values():
                if isinstance(v, dict) and "command" in (v.get("args") or {}):
                    cmds.append(v["args"]["command"])
        if e.get("type") == "result":
            usage = e.get("usage") or {}
    return {"tool_calls": tools, "shell_commands": len(cmds),
            "self_profiled": any(SELF_PROFILE.search(c) for c in cmds),
            "input_tokens": usage.get("inputTokens", 0) + usage.get("cacheReadTokens", 0) + usage.get("cacheWriteTokens", 0),
            "output_tokens": usage.get("outputTokens", 0)}


def load(cond: str) -> pd.DataFrame:
    df = pd.read_csv(REPORTS / f"eval_report_pilot_{cond}.csv").set_index("instance_id")
    ran = [p.name for p in (HERE / "runs_cursor" / cond).iterdir() if (p / "result.json").exists()]
    tasks = set(Path(TASKS).read_text().split())
    df = df.loc[sorted(set(ran) & tasks)]
    rows = []
    for iid in df.index:
        run = HERE / "runs_cursor" / cond / iid
        r = json.loads((run / "result.json").read_text())
        rows.append({"instance_id": iid, "profile_calls": r["profile_calls"], "minutes": r["seconds"] / 60,
                     "exit_status": r["exit_status"], "empty_patch": r["patch_chars"] == 0,
                     "refusals": sum(e["status"] == "refused" for e in r["profile_events"]),
                     **session(run / "stream.jsonl")})
    return df.join(pd.DataFrame(rows).set_index("instance_id"))


def main():
    data = {c: load(c) for c in CONDS}
    ids = sorted(set.intersection(*(set(d.index) for d in data.values())))
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(ids), size=(B, len(ids)))
    out = {"n_tasks": len(ids), "conditions": {}, "paired": {}}
    for c, d in data.items():
        d = d.loc[ids]
        sr = d["human_speedup_ratio"].to_numpy()
        boots = np.array([overall(sr[i]) for i in idx])
        out["conditions"][c] = {
            "overall_score": overall(sr),
            "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "incorrect": float((d["correctness"] < 1).mean()),
            "correct_no_speedup": float(((d["correctness"] == 1) & (d["raw_pred_speedup_ratio"] < 1)).mean()),
            "faster_than_baseline": float(((d["correctness"] == 1) & (d["raw_pred_speedup_ratio"] > 1.05)).mean()),
            "matched_expert": float((d["human_speedup_ratio"] >= 1).mean()),
            "empty_patch": float(d["empty_patch"].mean()),
            "mean_profile_calls": float(d["profile_calls"].mean()),
            "self_profiled_share": float(d["self_profiled"].mean()),
            "refusal_tasks": int((d["refusals"] > 0).sum()),
            "mean_tool_calls": float(d["tool_calls"].mean()),
            "mean_input_tokens": float(d["input_tokens"].mean()),
            "mean_output_tokens": float(d["output_tokens"].mean()),
            "mean_minutes": float(d["minutes"].mean()),
            "exit_status": d["exit_status"].value_counts().to_dict(),
        }
    for a, b in [("C1", "C0"), ("C2", "C0"), ("C2", "C1")]:
        sa = data[a].loc[ids, "human_speedup_ratio"].to_numpy()
        sb = data[b].loc[ids, "human_speedup_ratio"].to_numpy()
        diffs = np.array([overall(sa[i]) - overall(sb[i]) for i in idx])
        out["paired"][f"{a}-{b}"] = {
            "diff": overall(sa) - overall(sb),
            "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "tasks_better": int((sa > sb * 1.05).sum()), "tasks_worse": int((sa < sb / 1.05).sum()),
        }
    per_task = pd.DataFrame({c: data[c].loc[ids, "human_speedup_ratio"] for c in CONDS})
    per_task["gold_speedup"] = data["C0"].loc[ids, "gold_speedup_ratio"]
    OUT.mkdir(exist_ok=True)
    per_task.to_csv(OUT / "per_task_sr.csv")
    (OUT / "summary.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out, indent=2, default=float))
    print(per_task.round(3))


if __name__ == "__main__":
    main()
