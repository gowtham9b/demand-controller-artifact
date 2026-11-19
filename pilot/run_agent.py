"""Run the pilot agent on tasks x conditions and write predictions for scoring.

Usage: python run_agent.py --model anthropic/<model-id> [--tasks tasks_final.txt]
       [--conditions C0 C1 C2] [--workers 2] [--only <instance_id>]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yaml
from minisweagent.agents.default import DefaultAgent
from minisweagent.models import get_model

from controller import ControllerEnvironment

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
CONFIG = yaml.safe_load(
    (Path(__import__("minisweagent").__file__).parent / "config" / "benchmarks" / "swebench.yaml").read_text())

STEP_LIMIT = 40
WALL_SECONDS = 1800
COST_LIMIT = 4.0
ALLOWANCE = 4

TASK_PROMPT = (HERE / "prompts" / "task.j2").read_text()
TOOL_TEXT = {
    "C0": "",
    "C1": (HERE / "prompts" / "tool_dump.txt").read_text(),
    "C2": (HERE / "prompts" / "tool_ranked.txt").read_text(),
}


def observation_template() -> str:
    return CONFIG["model"]["observation_template"].replace("10000", "20000").replace("5000", "10000")


def run_one(model_name: str, row: dict, condition: str) -> dict:
    iid = row["instance_id"]
    out = RUNS / condition / iid
    if (out / "result.json").exists():
        return json.loads((out / "result.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)
    (work / "workload.py").write_text(row["workload"])

    env = ControllerEnvironment(
        condition=condition,
        allowance=ALLOWANCE,
        image=row["image_name"],
        cwd="/testbed",
        timeout=600,
        interpreter=["bash", "-c"],
        env=CONFIG["environment"]["env"],
        run_args=["--rm", "--platform", "linux/amd64", "--memory", "3500m", "--cpus", "4",
                  "-v", f"{HERE / 'dc'}:/dc:ro", "-v", f"{work}:/dcwork:ro"],
        pull_timeout=1800,
        container_timeout="3h",
    )
    model = get_model(model_name, {
        "model_kwargs": {"drop_params": True, "parallel_tool_calls": True},
        "observation_template": observation_template(),
        "format_error_template": CONFIG["model"]["format_error_template"],
    })
    agent = DefaultAgent(
        model, env,
        system_template=CONFIG["agent"]["system_template"],
        instance_template=TASK_PROMPT,
        step_limit=STEP_LIMIT,
        cost_limit=COST_LIMIT,
        wall_time_limit_seconds=WALL_SECONDS,
        output_path=out / "trajectory.json",
    )
    t0 = time.time()
    status, error = "", ""
    try:
        info = agent.run(task="", workload=row["workload"], test_cmd=row["test_cmd"],
                         rebuild_cmd=row["rebuild_cmd"], tool_text=TOOL_TEXT[condition])
        status = info.get("exit_status", "")
    except Exception as e:  # noqa: BLE001
        status, error = type(e).__name__, traceback.format_exc()
    diff = env.execute({"command": "git -c core.fileMode=false diff HEAD"}, "/testbed", timeout=120)["output"]
    env.cleanup()
    (out / "patch.diff").write_text(diff)
    result = {
        "instance_id": iid, "condition": condition, "model": model_name, "exit_status": status,
        "error": error[-2000:], "seconds": time.time() - t0, "cost": agent.cost, "model_calls": agent.n_calls,
        "profile_calls": env.used, "profile_events": env.events, "patch_chars": len(diff),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tasks", default=str(HERE / "tasks_final.txt"))
    ap.add_argument("--conditions", nargs="+", default=["C0", "C1", "C2"])
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    df = pd.read_pickle(HERE / "tasks.pkl").set_index("instance_id", drop=False)
    ids = [a.only] if a.only else Path(a.tasks).read_text().split()
    jobs = [(iid, c) for iid in ids for c in a.conditions]
    random.Random(1).shuffle(jobs)

    def go(job):
        iid, c = job
        r = run_one(a.model, df.loc[iid].to_dict(), c)
        print(f"{c} {iid}: {r['exit_status']} calls={r['model_calls']} prof={r['profile_calls']} "
              f"cost=${r['cost']:.2f} {r['seconds'] / 60:.1f}min patch={r['patch_chars']}", flush=True)
        return r

    with ThreadPoolExecutor(a.workers) as pool:
        results = list(pool.map(go, jobs))

    for c in a.conditions:
        preds = [{"instance_id": r["instance_id"], "model_patch": (RUNS / c / r["instance_id"] / "patch.diff").read_text(),
                  "model_name_or_path": f"pilot_{c}"} for r in results if r["condition"] == c]
        (HERE / f"predictions_{c}.jsonl").write_text("".join(json.dumps(p) + "\n" for p in preds))


if __name__ == "__main__":
    main()
