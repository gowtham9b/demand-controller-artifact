"""Score pilot-2 predictions per condition, rescore infrastructure failures (including
correctness runs that lost baseline-passing required tests to a crash), run the harness
report, and judge correctness under the raw harness rule and the baseline-relative rule.
Writes results2/scoring_status.json and results2/correctness.json.

Usage (harness venv): python score2.py [--conditions C0 C1 C2]
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from swefficiency.harness.utils import load_swefficiency_dataset  # noqa: E402

from scoring import HARNESS, LOGS, RUN_ID, harness_env, judge, score_with_rescore  # noqa: E402

HERE = Path(__file__).resolve().parent
PRED_PREFIX = os.environ.get("DC_PRED_PREFIX", "predictions2")
OUT = HERE / os.environ.get("DC_RESULTS", "results2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", nargs="+", default=["C0", "C1", "C2"])
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    required = json.loads((OUT / "required_tests.json").read_text())
    ds = {d["instance_id"]: d for d in load_swefficiency_dataset("swefficiency/swefficiency", "test")}
    path, cpath = OUT / "scoring_status.json", OUT / "correctness.json"
    status = json.loads(path.read_text()) if path.exists() else {}
    correctness = json.loads(cpath.read_text()) if cpath.exists() else {}
    tasks = (HERE / "tasks2_final.txt").read_text().split()
    correctness["gold"] = {i: judge(LOGS / RUN_ID / "gold" / i, ds[i]["PASS_TO_PASS"], required[i]) for i in tasks}
    for c in a.conditions:
        preds = HERE / f"{PRED_PREFIX}_{c}.jsonl"
        ids = [json.loads(line)["instance_id"] for line in preds.read_text().splitlines() if line.strip()]
        status[c] = score_with_rescore(f"{RUN_ID}_{c}", ids, preds, required={i: required[i] for i in ids})
        path.write_text(json.dumps(status, indent=2))
        correctness[c] = {i: judge(LOGS / RUN_ID / f"{RUN_ID}_{c}" / i, ds[i]["PASS_TO_PASS"], required[i])
                          for i in ids}
        cpath.write_text(json.dumps(correctness, indent=1))
        subprocess.run([str(HARNESS / ".venv" / "bin" / "swefficiency"), "report",
                        "--gold_run", str(LOGS / RUN_ID / "gold"), "--pred_run", str(LOGS / RUN_ID / f"{RUN_ID}_{c}")],
                       cwd=HARNESS, env=harness_env("2500m"), check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bad = {i: h["reason"] for i, h in status[c].items() if h["final"] != "scored"}
        rel = sum(v["rel_correct"] for v in correctness[c].values())
        raw = sum(v["raw_correct"] for v in correctness[c].values())
        print(f"{c}: {len(ids)} predictions; correct baseline-relative {rel}, raw harness {raw}; "
              f"not scored: {bad}", flush=True)


if __name__ == "__main__":
    main()
