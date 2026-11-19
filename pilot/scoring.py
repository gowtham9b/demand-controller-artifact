"""Pilot 2 scoring helpers: run the SWE-fficiency harness, classify each scored
instance, rescore infrastructure failures, and judge correctness against the
baseline-relative required test set (PREREGISTRATION.md, Pilot 2 amendment).

Classification of one instance directory of a harness run:
- "scored":        perf_summary.txt (not needed for baseline runs) and
                   covering_test_status.json exist, and the correctness stage did not
                   lose required tests to a crash (below).
- "infra":         outputs missing or incomplete because of the machine, not the patch:
                   the pre-edit timing failed or timed out (the patch is not applied
                   yet), an OOM / kill signature appears in the logs, a harness-side
                   exception occurred, timing finished but the correctness stage did
                   not, or the correctness stage finished but a test file's pytest
                   ended on a signal (exit >= 128, e.g. 137 Killed, 133 crash) or never
                   finished while at least one required test has no result at all.
- "patch_failure": outputs missing after the patch was applied (patch does not apply,
                   post-edit workload fails or times out) with no infra signature. The
                   harness scores these as incorrect / no speedup.
- "missing":       the instance was never run.

Required tests: for the baseline run (empty patch) they are the task's PASS_TO_PASS
tests; for gold and agent runs they are the PASS_TO_PASS tests that PASS in the
baseline run on this machine (`required_from_baseline`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent / "harness"
LOGS = HARNESS / "logs" / "run_evaluation"
RUN_ID = os.environ.get("DC_RUN_NAME", "pilot2")
SUPERSEDED = LOGS / f"{RUN_ID}_superseded"
WORKERS = 3
MEM = "2500m"
RESCORE_MEM = "6g"
RESCORE_ROUNDS = 2
RESCORE_TEST_WORKERS = [2, 1]  # pytest processes per container in rescore round 1, 2
BASELINE = "baseline"

INFRA_SIGNATURES = re.compile(
    r"Killed signal|\bKilled\b|OOMKilled|MemoryError|exit code 137|returned non-zero exit status 137|"
    r"No such file or directory: '/Users/|docker\.errors|APIError|ReadTimeout|Read timed out|"
    r"ConnectionError|Cannot allocate memory|No space left on device"
)
FINISHED = re.compile(r"Finished processing \[(\d+)\] with exit (\d+): (\S+)")
STARTED = re.compile(r"Processing \[(\d+)\]: (\S+)")


def harness_env(mem: str, test_workers: int | None = None) -> dict:
    # The harness downloads requirements files from GitHub while building test specs and
    # silently skips an instance whose download fails (TLS-intercepting proxy), so the CA
    # bundle must not depend on the caller's environment (launchd has none).
    ca = str(HERE / "certs" / "host-ca.pem")
    env = dict(os.environ, SWEF_FORCE_X86="1", SWEF_MEM_LIMIT=mem, SWEF_MEM_RESERVATION="1g",
               SWEF_EXTRA_CA=ca, HF_HUB_OFFLINE="1", REQUESTS_CA_BUNDLE=ca, SSL_CERT_FILE=ca, CURL_CA_BUNDLE=ca)
    env.pop("SWEF_TEST_WORKERS", None)
    if test_workers:
        env["SWEF_TEST_WORKERS"] = str(test_workers)
    return env


def baseline_predictions(ids: list[str]) -> Path:
    path = HERE / os.environ.get("DC_RESULTS", "results2") / "baseline_predictions.jsonl"
    path.parent.mkdir(exist_ok=True)
    have = {json.loads(x)["instance_id"] for x in path.read_text().splitlines() if x.strip()} if path.exists() else set()
    with path.open("a") as f:
        for i in sorted(set(ids) - have):
            f.write(json.dumps({"instance_id": i, "model_name_or_path": BASELINE, "model_patch": ""}) + "\n")
    return path


def harness_eval(ids: list[str], predictions: Path | None = None, workers: int = WORKERS, mem: str = MEM,
                 test_workers: int | None = None, perf: bool = True) -> None:
    if not ids:
        return
    print(f"harness eval: {len(ids)} instances, {workers} workers, mem {mem}, test workers "
          f"{test_workers or 'default'}, perf={perf}, preds={predictions}", flush=True)
    if perf:
        cmd = [str(HARNESS / ".venv" / "bin" / "swefficiency"), "eval", "--run_id", RUN_ID,
               "--num_workers", str(workers), "--instances_regex", "^(" + "|".join(sorted(ids)) + ")$"]
        if predictions:
            cmd += ["--prediction_path", str(predictions)]
    else:
        # Correctness only (baseline runs): run_validation.main as `swefficiency eval` calls it,
        # with the perf stage off.
        code = (
            "import sys, json; from swefficiency.harness.run_validation import main; "
            "main(dataset_name='swefficiency/swefficiency', split='test', instance_ids=json.loads(sys.argv[1]), "
            "max_workers=int(sys.argv[2]), max_build_workers=16, force_rebuild=False, cache_level='env', "
            "clean=False, open_file_limit=4096, run_id=sys.argv[3], timeout=7200, allow_test_patch=False, "
            "run_coverage=False, run_perf=False, run_perf_profiling=False, run_correctness=True, "
            "empty_patch=False, model_predictions=sys.argv[4], gdrive_annotation_sheet='', "
            "push_to_dockerhub=False, use_dockerhub_images=True, use_podman=False, workload_predictions='', "
            "force_rerun=False, process_isolation=True)"
        )
        cmd = [str(HARNESS / ".venv" / "bin" / "python"), "-c", code, json.dumps(sorted(ids)), str(workers),
               RUN_ID, str(predictions)]
    logs = HERE / os.environ.get("DC_RESULTS", "results2") / "harness_logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{time.strftime('%Y%m%d-%H%M%S')}_{RUN_ID}_{'perf' if perf else 'corr'}_{len(ids)}.log"
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n")
        f.flush()
        rc = subprocess.run(cmd, cwd=HARNESS, env=harness_env(mem, test_workers), check=False,
                            stdout=f, stderr=subprocess.STDOUT).returncode
    print(f"harness exit {rc}; log {log}", flush=True)


def _read(p: Path) -> str:
    return p.read_text(errors="replace") if p.exists() else ""


def test_status(run_dir: Path) -> dict | None:
    try:
        return json.loads((run_dir / "covering_test_status.json").read_text())
    except (OSError, ValueError):
        return None


def crashed_files(run_dir: Path) -> list[str]:
    """Test files whose pytest ended on a signal (final exit >= 128, after the harness's
    own retries) or that started but never finished, from correctness_output.txt."""
    out = _read(run_dir / "correctness_output.txt")
    started = dict(STARTED.findall(out))
    finished = {i: (int(e), p) for i, e, p in FINISHED.findall(out)}
    bad = [f"{p} (exit {e})" for i, (e, p) in finished.items() if e >= 128]
    bad += [f"{p} (unfinished)" for i, p in started.items() if i not in finished]
    if "Timeout error:" in out:
        bad.append("correctness stage timed out")
    return bad


def classify(run_dir: Path, required: list[str] | None = None, perf: bool = True) -> tuple[str, str]:
    """Return (status, reason) for one instance directory of a harness run."""
    if not (run_dir / "run_instance.log").exists():
        return "missing", "never run"
    st = test_status(run_dir)
    if st is not None and (not perf or (run_dir / "perf_summary.txt").exists()):
        if required:
            lost = [t for t in required if t not in st]
            crashes = crashed_files(run_dir) if lost else []
            if lost and crashes:
                return "infra", (f"correctness crash: {len(lost)} required tests without result; "
                                 f"{'; '.join(crashes[:4])}")
        return "scored", ""
    log = _read(run_dir / "run_instance.log")
    pre = _read(run_dir / "perf_output_preedit.txt")
    post = _read(run_dir / "perf_output_postedit.txt")
    corr = _read(run_dir / "correctness_output.txt")
    m = INFRA_SIGNATURES.search(log + pre + post + corr)
    if m:
        return "infra", f"signature {m.group(0)!r}"
    if not perf:
        return "infra", "correctness outputs are missing"
    if (run_dir / "perf_summary.txt").exists():
        return "infra", "timing finished but correctness outputs are missing"
    if not post:
        if pre and "PERF_END" not in pre:
            return "infra", "pre-edit timing failed (patch not yet applied)"
        if "Perf workload timed out" in log and "Post-edit" not in log:
            return "infra", "pre-edit timing timed out"
        if not pre:
            return "infra", "harness stopped before timing"
    return "patch_failure", "post-edit stage failed without an infra signature"


def statuses(run_name: str, ids: list[str], required: dict | None = None, perf: bool = True) -> dict[str, tuple[str, str]]:
    return {i: classify(LOGS / RUN_ID / run_name / i, (required or {}).get(i), perf) for i in ids}


def supersede(run_name: str, iid: str) -> None:
    """Move a run directory out of the run before it is rescored (kept, never deleted)."""
    src = LOGS / RUN_ID / run_name / iid
    if src.exists():
        dst = SUPERSEDED / run_name / f"{iid}.{time.strftime('%Y%m%d-%H%M%S')}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def score_with_rescore(run_name: str, ids: list[str], predictions: Path | None = None,
                       required: dict | None = None, perf: bool = True,
                       rounds: int = RESCORE_ROUNDS) -> dict[str, dict]:
    """Score `ids` (gold if predictions is None), then rescore infra failures with one
    worker, more memory and fewer pytest processes per container, up to `rounds` times.
    `required` maps instance -> required tests (crash-lost required tests are infra).
    Already scored instances are reused. Returns per-instance history."""
    hist: dict[str, dict] = {i: {"rounds": []} for i in ids}
    todo = [i for i, (s, _) in statuses(run_name, ids, required, perf).items() if s == "missing"]
    harness_eval(todo, predictions, perf=perf)
    for rnd in range(rounds + 1):
        st = statuses(run_name, ids, required, perf)
        for i, (s, why) in st.items():
            if not hist[i]["rounds"] or hist[i]["rounds"][-1] != [s, why]:
                hist[i]["rounds"].append([s, why])
        infra = [i for i, (s, _) in st.items() if s in ("infra", "missing")]
        if not infra or rnd == rounds:
            break
        for i in infra:
            supersede(run_name, i)
        harness_eval(infra, predictions, workers=1, mem=RESCORE_MEM,
                     test_workers=RESCORE_TEST_WORKERS[min(rnd, len(RESCORE_TEST_WORKERS) - 1)], perf=perf)
    for i, (s, why) in statuses(run_name, ids, required, perf).items():
        hist[i].update(final=s, reason=why)
    return hist


def required_from_baseline(iid: str, pass_to_pass: list[str]) -> list[str]:
    """PASS_TO_PASS tests that PASS in this machine's baseline (unmodified code) run."""
    st = test_status(LOGS / RUN_ID / BASELINE / iid) or {}
    return [t for t in pass_to_pass if "PASS" in st.get(t, "")]


def judge(run_dir: Path, pass_to_pass: list[str], required: list[str]) -> dict:
    """Correctness of one run: raw harness rule (all PASS_TO_PASS PASS) and the
    baseline-relative rule (all required tests PASS)."""
    st = test_status(run_dir)
    if st is None:
        return {"raw_correct": False, "raw_pct": 0.0, "rel_correct": False, "rel_pct": 0.0,
                "n_required": len(required), "required_failed": None, "required_missing": None,
                "crashed_files": crashed_files(run_dir)}
    ok = lambda t: "PASS" in st.get(t, "")  # noqa: E731
    raw = sum(map(ok, pass_to_pass))
    rel = sum(map(ok, required))
    return {"raw_correct": raw == len(pass_to_pass), "raw_pct": raw / len(pass_to_pass) if pass_to_pass else 1.0,
            "rel_correct": rel == len(required), "rel_pct": rel / len(required) if required else 1.0,
            "n_required": len(required),
            "required_failed": [t for t in required if t in st and not ok(t)],
            "required_missing": [t for t in required if t not in st],
            "crashed_files": crashed_files(run_dir)}
