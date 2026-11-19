"""Apply the pre-registered replacement rule and write tasks_final.txt.

A task is kept if its expert patch, scored on this machine, passes and improves the
workload by at least 1.05x. Otherwise it is replaced by the next task in the
pre-registered order for the same repository, which is scored first.
"""

import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent / "harness"
GOLD = HARNESS / "logs" / "run_evaluation" / "pilot" / "gold"
MIN_IMPROVEMENT = 1.05


def gold_results() -> dict:
    """Per-task gold improvement read from each task's own perf_summary.txt.

    (validation_report_pilot.json is rewritten by every harness invocation and only
    holds that invocation's tasks, so it cannot be used as the record.)
    """
    out = {}
    for d in GOLD.iterdir():
        f = d / "perf_summary.txt"
        if d.is_dir() and (d / "run_instance.log").exists():
            imp = None
            if f.exists():
                vals = dict(line.split(":", 1) for line in f.read_text().splitlines() if ":" in line)
                imp = float(vals["Before Mean"]) / float(vals["After Mean"])
            out[d.name] = {"perf_report": {"improvement": imp} if imp is not None else {}}
    return out


def ok(res: dict) -> bool:
    perf = (res or {}).get("perf_report") or {}
    return perf.get("improvement") is not None and perf["improvement"] >= MIN_IMPROVEMENT


def score_gold(ids: list[str]) -> None:
    env = dict(os.environ, SWEF_FORCE_X86="1", SWEF_MEM_LIMIT="2500m", SWEF_MEM_RESERVATION="1g",
               SWEF_EXTRA_CA=str(HERE / "certs" / "host-ca.pem"))
    regex = "^(" + "|".join(ids) + ")$"
    subprocess.run([str(HARNESS / ".venv" / "bin" / "swefficiency"), "eval", "--run_id", "pilot",
                    "--num_workers", "1", "--instances_regex", regex], cwd=HARNESS, env=env, check=False)


def main():
    sampled = json.loads((HERE / "tasks_sampled.json").read_text())
    order, chosen = sampled["order"], sampled["initial"]
    log = []
    final = []
    for repo, ids in chosen.items():
        queue = [i for i in order[repo] if i not in ids]
        for iid in ids:
            current = iid
            while True:
                res = gold_results().get(current)
                if res is None:
                    score_gold([current])
                    res = gold_results().get(current)
                if ok(res):
                    final.append(current)
                    break
                imp = ((res or {}).get("perf_report") or {}).get("improvement")
                log.append({"repo": repo, "dropped": current, "measured_improvement": imp})
                if not queue:
                    log.append({"repo": repo, "note": "no replacement left"})
                    break
                current = queue.pop(0)
    (HERE / "tasks_final.txt").write_text("\n".join(final) + "\n")
    improvements = {i: gold_results()[i]["perf_report"]["improvement"] for i in final}
    (HERE / "tasks_final.json").write_text(json.dumps({"final": final, "replacements": log,
                                                        "gold_improvement_here": improvements}, indent=2))
    print(json.dumps({"n": len(final), "replacements": log}, indent=2))


if __name__ == "__main__":
    main()
