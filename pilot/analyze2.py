"""Pilot 2 analysis: scores per condition with bootstrap CIs, paired differences,
evidence use, behaviour, cost and infrastructure failures.

Primary analysis: every task in tasks2_final.txt; correctness under the amended
baseline-relative rule (all PASS_TO_PASS tests that pass on the unmodified code on this
machine must pass; results2/correctness.json from score2.py), speedups from the harness
report (an unresolved infrastructure failure is scored as the harness scores a missing
prediction: incorrect, no speedup). The same metrics under the harness's raw correctness
(all PASS_TO_PASS tests) are reported as "*_raw_harness". Secondary analysis: tasks whose
run and scoring are valid in all three conditions.

Usage (agent venv): python analyze2.py      Writes results2/summary.json, results2/per_task.csv.
"""

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from analyze import SELF_PROFILE, overall

HERE = Path(__file__).resolve().parent
REPORTS = Path(os.environ.get("DC_REPORTS", str(HERE.parent / "harness" / "eval_reports")))
RUN_NAME = os.environ.get("DC_RUN_NAME", "pilot2")
RUNS = HERE / os.environ.get("DC_RUNS_DIR", "runs_cursor2")
OUT = HERE / os.environ.get("DC_RESULTS", "results2")
TASKS = Path(os.environ.get("DC_TASKS", str(HERE / "tasks2_final.txt")))
CONDS = ["C0", "C1", "C2"]
PAIRS = [("C1", "C0"), ("C2", "C0"), ("C2", "C1")]
B = 10_000
TOP_FILES = 3


def geo(x: np.ndarray) -> float:
    return float(np.exp(np.mean(np.log(np.clip(x, 0.001, None)))))


METRICS = {  # name: (column, aggregate); columns are suffixed with the correctness rule
    "hm_human_sr": ("human_speedup_ratio", overall),  # primary: SWE-fficiency overall score
    "gm_human_sr": ("human_speedup_ratio", geo),
    "gm_adj_speedup": ("pred_speedup_ratio", geo),  # speedup over the original code, 1.0 if incorrect
}
RULES = {"rel": "baseline-relative required tests (primary)", "raw": "harness PASS_TO_PASS (secondary)"}


def session(path: Path) -> dict:
    """Shell commands, self-profiling and token usage from a Cursor CLI stream-json log."""
    tools, cmds, usage = 0, [], None
    for line in path.read_text(errors="replace").splitlines() if path.exists() else []:
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
            "dc_profile_commands": sum("dc-profile" in c for c in cmds),
            "has_usage": usage is not None,
            "input_tokens": np.nan if usage is None else
            usage.get("inputTokens", 0) + usage.get("cacheReadTokens", 0) + usage.get("cacheWriteTokens", 0),
            "output_tokens": np.nan if usage is None else usage.get("outputTokens", 0)}


def patch_files(diff: str) -> set[str]:
    return set(re.findall(r"^diff --git a/(\S+) b/", diff, re.M))


def hotspot_files(iid: str) -> set[str]:
    """Files of the top repository functions by self time in the original workload (validation profile)."""
    f = OUT / "profiler_validation" / iid / "profile.json"
    if not f.exists():
        return set()
    funcs = [x for x in json.loads(f.read_text())["funcs"] if x["file"].startswith("/testbed/")]
    files: list[str] = []
    for x in sorted(funcs, key=lambda x: -x["tottime"]):
        p = x["file"][len("/testbed/"):]
        if p not in files:
            files.append(p)
    return set(files[:TOP_FILES])


def load(cond: str, ids: list[str], status: dict, gold_patch: dict, correctness: dict,
         gold_speedup: dict) -> pd.DataFrame:
    rep = pd.read_csv(REPORTS / f"eval_report_{RUN_NAME}_{cond}.csv").set_index("instance_id")
    rows = []
    for iid in ids:
        if iid in rep.index:
            h = rep.loc[iid, ["human_speedup_ratio", "raw_pred_speedup_ratio", "pred_speedup_ratio",
                              "gold_speedup_ratio", "correctness", "correctness_pct"]].to_dict()
        else:  # no prediction: scored as the harness scores a missing prediction
            g = gold_speedup[iid]
            h = {"human_speedup_ratio": 1 / g, "raw_pred_speedup_ratio": 1.0, "pred_speedup_ratio": 1.0,
                 "gold_speedup_ratio": g, "correctness": 0.0, "correctness_pct": 0.0}
        cj = (correctness.get(cond) or {}).get(iid, {})
        rel_ok = bool(cj.get("rel_correct", False))
        pred_rel = h["raw_pred_speedup_ratio"] if rel_ok else 1.0
        h = {f"{k}_raw": v for k, v in h.items() if k != "gold_speedup_ratio" and k != "raw_pred_speedup_ratio"} | {
            "gold_speedup_ratio": h["gold_speedup_ratio"], "raw_pred_speedup_ratio": h["raw_pred_speedup_ratio"],
            "correctness_rel": float(rel_ok), "correctness_pct_rel": cj.get("rel_pct", 0.0),
            "pred_speedup_ratio_rel": pred_rel, "human_speedup_ratio_rel": pred_rel / h["gold_speedup_ratio"],
            "required_failed": len(cj.get("required_failed") or []),
            "required_missing": len(cj.get("required_missing") or []),
            "crashed_files": len(cj.get("crashed_files") or [])}
        run = RUNS / cond / iid
        r = json.loads((run / "result.json").read_text()) if (run / "result.json").exists() else {}
        sc = (status.get(cond) or {}).get(iid, {}).get("final", "no_prediction") if r.get("valid") else "no_valid_run"
        diff = (run / "patch.diff").read_text() if (run / "patch.diff").exists() else ""
        hot = hotspot_files(iid)
        events = r.get("profile_events", [])
        rows.append({
            "instance_id": iid, "run_valid": bool(r.get("valid")), "score_status": sc,
            "valid": bool(r.get("valid")) and sc in ("scored", "patch_failure"),
            "run_attempts": len(r.get("attempts", [])),
            "run_infra_retries": sum(not a["valid"] for a in r.get("attempts", [])),
            "exit_status": r.get("exit_status", ""), "minutes": r.get("agent_seconds", np.nan) / 60,
            "auto_profile": sum(e.get("kind") == "auto" and e["status"] == "ok" for e in events),
            "agent_profile_calls": sum(e.get("kind") == "agent" and e["status"] != "refused" for e in events),
            "agent_profile_errors": sum(e.get("kind") == "agent" and e["status"] == "error" for e in events),
            "refusals": sum(e["status"] == "refused" for e in events),
            "empty_patch": r.get("patch_chars", 0) == 0,
            "touches_hotspot_file": bool(patch_files(diff) & hot) if hot else np.nan,
            "gold_touches_hotspot_file": bool(patch_files(gold_patch[iid]) & hot) if hot else np.nan,
            **session(run / "stream.jsonl"),
            **h,
        })
    return pd.DataFrame(rows).set_index("instance_id")


def analyse(data: dict, ids: list[str], rule: str = "rel", rng_seed: int = 0) -> dict:
    out = {"n_tasks": len(ids), "correctness_rule": RULES[rule], "conditions": {}, "paired": {}}
    if not ids:
        return out
    idx = np.random.default_rng(rng_seed).integers(0, len(ids), size=(B, len(ids)))
    for c, d in data.items():
        d = d.loc[ids]
        metrics = {}
        for m, (col, agg) in METRICS.items():
            x = d[f"{col}_{rule}"].to_numpy()
            boots = np.array([agg(x[i]) for i in idx])
            metrics[m] = {"value": agg(x), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}
        correct = d[f"correctness_{rule}"] == 1
        out["conditions"][c] = {
            **metrics,
            "incorrect": float((~correct).mean()),
            "correct_no_speedup": float((correct & (d["raw_pred_speedup_ratio"] < 1)).mean()),
            "faster_than_baseline": float((correct & (d["raw_pred_speedup_ratio"] > 1.05)).mean()),
            "matched_expert": float((d[f"human_speedup_ratio_{rule}"] >= 1).mean()),
            "empty_patch": float(d["empty_patch"].mean()),
            "auto_profile_runs": int((d["auto_profile"] > 0).sum()),
            "mean_agent_profile_calls": float(d["agent_profile_calls"].mean()),
            "runs_with_agent_profile_call": int((d["agent_profile_calls"] > 0).sum()),
            "agent_profile_calls_total": int(d["agent_profile_calls"].sum()),
            "agent_profile_errors": int(d["agent_profile_errors"].sum()),
            "refusal_runs": int((d["refusals"] > 0).sum()),
            "self_profiled_share": float(d["self_profiled"].mean()),
            "touches_hotspot_file_share": float(d["touches_hotspot_file"].mean()),
            "mean_tool_calls": float(d["tool_calls"].mean()),
            "mean_minutes": float(d["minutes"].mean()),
            "median_minutes": float(d["minutes"].median()),
            "runs_with_usage": int(d["has_usage"].sum()),
            "mean_input_tokens": float(d["input_tokens"].mean()),
            "mean_output_tokens": float(d["output_tokens"].mean()),
            "exit_status": d["exit_status"].value_counts().to_dict(),
        }
    for a, b in PAIRS:
        pair = {}
        for m, (col, agg) in METRICS.items():
            sa, sb = data[a].loc[ids, f"{col}_{rule}"].to_numpy(), data[b].loc[ids, f"{col}_{rule}"].to_numpy()
            diffs = np.array([agg(sa[i]) - agg(sb[i]) for i in idx])
            pair[m] = {"diff": agg(sa) - agg(sb),
                       "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
                       "p_boot_le_0": float((diffs <= 0).mean())}
        sa = data[a].loc[ids, f"human_speedup_ratio_{rule}"].to_numpy()
        sb = data[b].loc[ids, f"human_speedup_ratio_{rule}"].to_numpy()
        pair.update(tasks_better=int((sa > sb * 1.05).sum()), tasks_worse=int((sa < sb / 1.05).sum()))
        out["paired"][f"{a}-{b}"] = pair
    return out


def main():
    ids = TASKS.read_text().split()
    status = json.loads((OUT / "scoring_status.json").read_text()) if (OUT / "scoring_status.json").exists() else {}
    gold_patch = pd.read_pickle(HERE / "tasks.pkl").set_index("instance_id")["patch"].to_dict()
    correctness = json.loads((OUT / "correctness.json").read_text())
    final = json.loads(TASKS.with_suffix(".json").read_text())["gold"]
    gold_speedup = {i: final[i]["improvement"] for i in ids}
    data = {c: load(c, ids, status, gold_patch, correctness, gold_speedup) for c in CONDS}
    valid_all = [i for i in ids if all(data[c].loc[i, "valid"] for c in CONDS)]
    infra = {c: {
        "runs_with_infra_retries": int((data[c]["run_infra_retries"] > 0).sum()),
        "infra_retries_total": int(data[c]["run_infra_retries"].sum()),
        "runs_never_valid": data[c].index[~data[c]["run_valid"]].tolist(),
        "scoring_status_counts": data[c]["score_status"].value_counts().to_dict(),
        "scoring_infra_unresolved": data[c].index[data[c]["score_status"].isin(["infra", "missing", "no_prediction"])].tolist(),
        "scoring_rescored": [i for i, h in (status.get(c) or {}).items() if len(h["rounds"]) > 1],
    } for c in CONDS}
    disagree = {c: data[c].index[data[c]["correctness_rel"] != data[c]["correctness_raw"]].tolist() for c in CONDS}
    out = {"primary": analyse(data, ids, "rel"), "primary_raw_harness": analyse(data, ids, "raw"),
           "valid_in_all_three": analyse(data, valid_all, "rel"),
           "valid_in_all_three_raw_harness": analyse(data, valid_all, "raw"),
           "valid_in_all_three_ids": valid_all, "infra": infra,
           "correctness_rule_disagreements": disagree,
           "gold_correct": {"baseline_relative": sum(v["rel_correct"] for v in correctness["gold"].values()),
                            "raw_harness": sum(v["raw_correct"] for v in correctness["gold"].values()),
                            "n": len(correctness["gold"])},
           "gold_touches_hotspot_file_share": float(data["C0"]["gold_touches_hotspot_file"].mean())}
    per_task = pd.concat({c: data[c][["human_speedup_ratio_rel", "correctness_rel", "human_speedup_ratio_raw",
                                      "correctness_raw", "raw_pred_speedup_ratio", "valid", "required_failed",
                                      "required_missing",
                                      "agent_profile_calls", "self_profiled", "touches_hotspot_file", "minutes"]]
                          for c in CONDS}, axis=1)
    per_task[("gold", "speedup")] = data["C0"]["gold_speedup_ratio"]
    OUT.mkdir(exist_ok=True)
    per_task.to_csv(OUT / "per_task.csv")
    (OUT / "summary.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out, indent=2, default=float))
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        print(per_task.xs("human_speedup_ratio_rel", axis=1, level=1).join(data["C0"]["gold_speedup_ratio"]).round(3))


if __name__ == "__main__":
    main()
