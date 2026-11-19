"""Validate the profiler on every task before any agent run.

For each task: start the task container exactly as an agent run does (same image,
CPU set, memory, mounts, CA setup), run the controller's metered profile once (the
automatic-profile code path), and render the evidence in both formats (C1 and C2).
Writes results2/profiler_validation.json and the rendered texts; exits 1 if any task fails.

Usage: python validate_profiler.py [--tasks tasks2_final.txt] [--workers 3]
"""

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from controller import RENDERERS
from cursor_runner import HERE, Run, sh, start_container

OUT = HERE / os.environ.get("DC_RESULTS", "results2") / "profiler_validation"


def validate(row: dict, slot: int) -> dict:
    iid = row["instance_id"]
    work = OUT / iid
    work.mkdir(parents=True, exist_ok=True)
    (work / "workload.py").write_text(row["workload"])
    name = f"dcvalid-{iid}".replace("_", "-")[:60]
    run = Run("C1", name)
    res = {"instance_id": iid, "ok": False}
    try:
        start_container(name, row, slot, work, "", dict(os.environ))
        ok, text_c1 = run.profile("auto")
        res.update(run.events[-1])
        if ok:
            raw = sh(["docker", "exec", name, "cat", "/tmp/dc_prof_1.json"], 120).stdout
            (work / "profile.json").write_text(raw)
            data = json.loads(raw)
            text_c2 = RENDERERS["C2"](data) + "\n" + run.meter()
            (work / "C1.txt").write_text(text_c1)
            (work / "C2.txt").write_text(text_c2)
            repo_funcs = sum(f["file"].startswith("/testbed/") for f in data["funcs"])
            res.update(ok=repo_funcs > 0, repo_funcs=repo_funcs, stopped_at_timing_call=data["stopped_at_timing_call"],
                       number=data["number"], repeats=data["repeats"], c1_chars=len(text_c1), c2_chars=len(text_c2))
    except Exception as e:  # noqa: BLE001
        res["error"] = repr(e)[-2000:]
    finally:
        sh(["docker", "rm", "-f", name], 120)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(HERE / "tasks2_final.txt"))
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    df = pd.read_pickle(HERE / "tasks.pkl").set_index("instance_id", drop=False)
    ids = Path(a.tasks).read_text().split()
    slots, lock = list(range(a.workers)), threading.Lock()

    def go(iid):
        with lock:
            slot = slots.pop()
        try:
            r = validate(df.loc[iid].to_dict(), slot)
        finally:
            with lock:
                slots.append(slot)
        print(f"{iid}: ok={r['ok']} {r.get('status', '')} {r.get('seconds', 0):.0f}s repo_funcs={r.get('repo_funcs')}",
              flush=True)
        return r

    with ThreadPoolExecutor(a.workers) as pool:
        results = list(pool.map(go, ids))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT.parent / "profiler_validation.json").write_text(json.dumps(results, indent=2))
    bad = [r["instance_id"] for r in results if not r["ok"]]
    print(f"profiler validation: {len(results) - len(bad)}/{len(results)} ok; failed: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
