"""Pilot 2 replacement rule (as amended, PREREGISTRATION.md); writes tasks2_final.txt,
tasks2_final.json and results2/required_tests.json.

A sampled task is kept if, on this machine, its expert (gold) patch scored under run id
pilot2 (a) passes every required test and (b) improves the workload by at least 1.05x.
Required tests are the task's PASS_TO_PASS tests that PASS when the harness runs the
unmodified code (empty patch, model name "baseline", correctness stage only). Baseline
and gold runs whose correctness stage lost required tests to a crash (OOM kill, signal)
are infrastructure failures and are rescored with one worker, 6 GB and fewer pytest
processes (scoring.py) before the rule decides. Already scored gold results are reused
and re-judged; only missing results are scored. A baseline run is needed only for
candidates whose gold patch is scored and reaches 1.05x. A task that fails is replaced by
the next task in the pre-registered order (tasks_sampled.json) for the same repository.
An instance the harness did not run at all stops the step (exit 1) instead of being replaced.
Candidates still undecided in a round are scored together, which changes only wall time.
"""

import json
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from swefficiency.harness.utils import load_swefficiency_dataset  # noqa: E402
from swefficiency.report import evaluate_instance  # noqa: E402

from scoring import (BASELINE, LOGS, RUN_ID, baseline_predictions, judge,  # noqa: E402
                     required_from_baseline, score_with_rescore)

HERE = Path(__file__).resolve().parent
GOLD = LOGS / RUN_ID / "gold"
OUT = HERE / os.environ.get("DC_RESULTS", "results2")
MIN_IMPROVEMENT = 1.05
BASELINE_RESCORE_ROUNDS = 1


def main():
    ds = {d["instance_id"]: d for d in load_swefficiency_dataset("swefficiency/swefficiency", "test")}
    sampled = json.loads((HERE / "tasks_sampled.json").read_text())
    order, initial = sampled["order"], sampled["initial"]
    slots = [(repo, iid) for repo, ids in initial.items() for iid in ids]
    queues = {repo: [i for i in order[repo] if i not in ids] for repo, ids in initial.items()}
    current = {k: iid for k, (repo, iid) in enumerate(slots)}
    decided: dict[int, str | None] = {}
    log, gold, required_all = [], {}, {}
    OUT.mkdir(exist_ok=True)
    while len(decided) < len(slots):
        open_slots = [k for k in current if k not in decided]
        batch = [current[k] for k in open_slots]
        p2p = {i: ds[i]["PASS_TO_PASS"] for i in batch}
        print(f"round: {len(batch)} candidates: {batch}", flush=True)
        hist = score_with_rescore("gold", batch)
        speed = {i: evaluate_instance(ds[i], GOLD, GOLD)["gold_speedup_ratio"] for i in batch}
        need = [i for i in batch if hist[i]["final"] == "scored" and speed[i] >= MIN_IMPROVEMENT]
        base_hist = score_with_rescore(BASELINE, need, baseline_predictions(need), required=p2p,
                                       perf=False, rounds=BASELINE_RESCORE_ROUNDS) if need else {}
        required = {i: required_from_baseline(i, p2p[i]) for i in need}
        if need:
            # Re-judge gold against the baseline-relative set; crash-lost required tests are infra.
            hist2 = score_with_rescore("gold", need, required=required)
            for i in need:
                hist[i]["rounds"] += [["rejudged with baseline-relative required tests", ""]] + hist2[i]["rounds"]
                hist[i].update(final=hist2[i]["final"], reason=hist2[i]["reason"])
                speed[i] = evaluate_instance(ds[i], GOLD, GOLD)["gold_speedup_ratio"]
        never_run = [f"{run}:{i}" for run, h in (("gold", hist), (BASELINE, base_hist))
                     for i in h if h[i]["final"] == "missing"]
        if never_run:
            # The harness did not start these instances: a machine problem, never a rule outcome.
            raise SystemExit(f"harness did not run {never_run}; see results2/harness_logs; stopping")
        for k in open_slots:
            iid, repo = current[k], slots[k][0]
            rec = {"repo": repo, "instance_id": iid, "status": hist[iid]["final"], "reason": hist[iid]["reason"],
                   "rescore_history": hist[iid]["rounds"], "improvement": speed[iid],
                   "n_pass_to_pass": len(p2p[iid])}
            if iid in required:
                bh = base_hist[iid]
                bdir = LOGS / RUN_ID / BASELINE / iid
                bj = judge(bdir, p2p[iid], p2p[iid])
                rec["baseline"] = {"status": bh["final"], "reason": bh["reason"], "rescore_history": bh["rounds"],
                                   "n_pass_to_pass_passing": len(required[iid]),
                                   "n_pass_to_pass_not_passing": len(p2p[iid]) - len(required[iid]),
                                   "n_pass_to_pass_without_result": len(bj["required_missing"] or []),
                                   "crashed_files": bj["crashed_files"]}
                gj = judge(GOLD / iid, p2p[iid], required[iid])
                rec.update(n_required_tests=len(required[iid]), gold_raw_correct=gj["raw_correct"],
                           gold_raw_correctness_pct=gj["raw_pct"], gold_rel_correct=gj["rel_correct"],
                           gold_rel_correctness_pct=gj["rel_pct"],
                           gold_required_failed=gj["required_failed"], gold_required_missing=gj["required_missing"],
                           gold_crashed_files=gj["crashed_files"])
                required_all[iid] = required[iid]
            rec["passes_rule"] = bool(rec["status"] == "scored" and rec.get("gold_rel_correct")
                                      and speed[iid] >= MIN_IMPROVEMENT and required.get(iid))
            gold[iid] = rec
            print(json.dumps({x: rec.get(x) for x in ("instance_id", "status", "reason", "improvement",
                                                      "n_pass_to_pass", "n_required_tests", "gold_rel_correct",
                                                      "gold_raw_correctness_pct", "passes_rule")}), flush=True)
            if rec["passes_rule"]:
                decided[k] = iid
                continue
            why = [] if rec["status"] == "scored" else [f"gold not scored ({rec['reason']})"]
            if rec["status"] == "scored" and speed[iid] < MIN_IMPROVEMENT:
                why.append(f"improvement {speed[iid]:.3f} < {MIN_IMPROVEMENT}")
            if iid in required and not required[iid]:
                why.append("no PASS_TO_PASS test passes at baseline on this machine"
                           if (LOGS / RUN_ID / BASELINE / iid / "covering_test_status.json").exists()
                           else f"baseline correctness unavailable ({rec['baseline']['reason']})")
            elif rec["status"] == "scored" and iid in required and not rec["gold_rel_correct"]:
                why.append(f"gold fails baseline-passing required tests ({len(rec['gold_required_failed'] or [])} "
                           f"failed, {len(rec['gold_required_missing'] or [])} without result, of {len(required[iid])})")
            log.append({"repo": repo, "dropped": iid, "why": "; ".join(why)})
            if queues[repo]:
                current[k] = queues[repo].pop(0)
            else:
                log.append({"repo": repo, "note": "no replacement left; slot dropped"})
                decided[k] = None
        print(json.dumps(log, indent=1), flush=True)
        (OUT / "required_tests.json").write_text(json.dumps(required_all, indent=1))
    final = [decided[k] for k in range(len(slots)) if decided[k]]
    (OUT / "required_tests.json").write_text(json.dumps(required_all, indent=1))
    (HERE / "tasks2_final.txt").write_text("\n".join(final) + "\n")
    (HERE / "tasks2_final.json").write_text(json.dumps(
        {"rule": "gold passes all baseline-passing PASS_TO_PASS tests and improves >= 1.05x (amended)",
         "final": final, "replacements": log, "gold": gold}, indent=2))
    print(json.dumps({"n": len(final), "final": final, "replacements": log}, indent=2))


if __name__ == "__main__":
    main()
