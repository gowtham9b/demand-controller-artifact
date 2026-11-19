"""Run the pilot with the Cursor CLI agent inside each SWE-fficiency container.

The demand controller runs on the host as a small HTTP server; inside the container,
`dc-profile` calls it with a per-run token. Allowance, metering and rendering stay on
the host, so the agent cannot change them.

Pilot 2: in C1 and C2 the controller profiles the original workload once before the
agent starts (through the same metered code path as `dc-profile`) and puts the
rendered evidence in the initial prompt. Runs that never reach a model session
(container, setup, install or auto-profile failure) are infrastructure failures: they
are retried and never recorded as valid results.

Usage: python cursor_runner.py --model claude-sonnet-5-5-medium [--tasks tasks2_final.txt]
       [--conditions C0 C1 C2] [--workers 3] [--only <instance_id>]
Env: DC_RUNS_DIR (default runs_cursor2), DC_PRED_PREFIX (default predictions2),
     DC_RUN_NAME (default pilot2), DC_WALL (seconds, default 1800).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets as pysecrets
import shutil
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from jinja2 import StrictUndefined, Template

from controller import RENDERERS
from keyfile import cursor_api_key

HERE = Path(__file__).resolve().parent
RUNS = HERE / os.environ.get("DC_RUNS_DIR", "runs_cursor2")
PRED_PREFIX = os.environ.get("DC_PRED_PREFIX", "predictions2")
RUN_NAME = os.environ.get("DC_RUN_NAME", "pilot2")
WALL_SECONDS = int(os.environ.get("DC_WALL", "1800"))
ALLOWANCE = 4
ATTEMPTS_PER_CALL = 3
MAX_ATTEMPTS = 6
INSTALL_TRIES = 3
PORT = 47321
CPUSETS = ["4-7", "8-11", "12-15"]

PROMPT = Template((HERE / "prompts" / "task_cursor.j2").read_text(), undefined=StrictUndefined)
TOOL_TEXT = {
    "C1": (HERE / "prompts" / "tool_dump_auto.txt").read_text(),
    "C2": (HERE / "prompts" / "tool_ranked_auto.txt").read_text(),
}
CA_SETUP = (
    "cat /certs/host-ca.pem >> /etc/ssl/certs/ca-certificates.crt && "
    "echo 'ca_certificate = /etc/ssl/certs/ca-certificates.crt' >> /etc/wgetrc && "
    "printf '[global]\\ncert = /etc/ssl/certs/ca-certificates.crt\\n' > /etc/pip.conf && "
    "(for py in /opt/miniconda3/envs/*/bin/python /opt/miniconda3/bin/python; do "
    "$py -c 'import certifi; print(certifi.where())' 2>/dev/null; "
    "$py -c 'import pip._vendor.certifi as c; print(c.where())' 2>/dev/null; "
    "done | sort -u | while read f; do cat /certs/host-ca.pem >> \"$f\"; done)"
)
INSTALL = (
    "set -o pipefail; curl -fsS --retry 3 https://cursor.com/install -o /tmp/cursor_install.sh && "
    "bash /tmp/cursor_install.sh > /tmp/cursor_install.log 2>&1 && "
    "ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && cursor-agent --version"
)


class InfraFailure(Exception):
    pass


def sh(args: list[str], timeout: int, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env,
                          encoding="utf-8", errors="replace")


class Run:
    def __init__(self, condition: str, container: str):
        self.condition, self.container = condition, container
        self.used, self.events, self.lock = 0, [], threading.Lock()

    def meter(self) -> str:
        return f"[dc-profile allowance: {self.used} of {ALLOWANCE} calls used; {ALLOWANCE - self.used} remaining]"

    def profile(self, kind: str = "agent") -> tuple[bool, str]:
        t0 = time.time()
        with self.lock:
            if self.used >= ALLOWANCE:
                self.events.append({"t": t0, "kind": kind, "status": "refused"})
                return False, "Request refused: profiling allowance exhausted. Continue by editing and testing.\n" + self.meter()
            self.used += 1
            n = self.used
        out = f"/tmp/dc_prof_{n}.json"
        r = sh(["docker", "exec", "-w", "/testbed", self.container, "bash", "-c",
                f"source /root/.bashrc; python /dc/profile_runner.py /dcwork/workload.py {out}"], 900)
        if r.returncode != 0:
            self.events.append({"t": t0, "kind": kind, "status": "error", "seconds": time.time() - t0,
                                "output": (r.stdout + r.stderr)[-3000:]})
            return False, "Profiling failed:\n" + (r.stdout + r.stderr)[-3000:] + "\n" + self.meter()
        data = json.loads(sh(["docker", "exec", self.container, "cat", out], 120).stdout)
        text = RENDERERS[self.condition](data) + "\n" + self.meter()
        self.events.append({"t": t0, "kind": kind, "status": "ok", "seconds": time.time() - t0, "chars": len(text),
                            "iters": data["iters"], "n_funcs": len(data["funcs"])})
        return True, text


RUNS_BY_TOKEN: dict[str, Run] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        run = RUNS_BY_TOKEN.get((q.get("token") or [""])[0])
        body = run.profile("agent")[1] if run else "dc-profile is not available for this task."
        data = (body + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def start_container(name: str, row: dict, slot: int, work: Path, token: str, env: dict) -> None:
    sh(["docker", "rm", "-f", name], 60)
    start = sh(["docker", "run", "-d", "--name", name, "--platform", "linux/amd64",
                "--memory", os.environ.get("DC_MEM", "2300m"), "--cpuset-cpus", CPUSETS[slot], "-w", "/testbed",
                "-e", "CURSOR_API_KEY", "-e", "BASH_ENV=/root/.bashrc", "-e", "NODE_EXTRA_CA_CERTS=/certs/host-ca.pem",
                "-e", f"DC_TOKEN={token}", "-e", f"DC_PORT={PORT}",
                "-v", f"{HERE / 'dc'}:/dc:ro", "-v", f"{work}:/dcwork:ro", "-v", f"{HERE / 'certs'}:/certs:ro",
                row["image_name"], "sleep", "4h"], 1800, env)
    if start.returncode != 0:
        raise InfraFailure("docker run failed: " + start.stderr[-1000:])
    r = sh(["docker", "exec", name, "bash", "-c", CA_SETUP], 600)
    if r.returncode != 0:
        raise InfraFailure("CA setup failed: " + (r.stdout + r.stderr)[-1000:])


def install_agent(name: str) -> str:
    log = []
    for i in range(INSTALL_TRIES):
        r = sh(["docker", "exec", name, "bash", "-c", INSTALL], 600)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[-1]
        log.append(f"try {i + 1}: exit {r.returncode}: {(r.stdout + r.stderr)[-500:]}")
        time.sleep(20)
    raise InfraFailure("cursor-agent install not verified:\n" + "\n".join(log))


def session_started(stream: Path) -> bool:
    """True if the Cursor CLI reached a model session (init event or any model output)."""
    if not stream.exists():
        return False
    for line in stream.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if (e.get("type") == "system" and e.get("subtype") == "init") or e.get("type") in ("assistant", "tool_call", "result"):
            return True
    return False


def attempt(model: str, row: dict, condition: str, slot: int, key: str, out: Path) -> dict:
    iid = row["instance_id"]
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    (work / "workload.py").write_text(row["workload"])
    for f in ("stream.jsonl", "patch.diff", "prompt.txt"):
        (out / f).unlink(missing_ok=True)

    token = pysecrets.token_hex(16) if condition in RENDERERS else ""
    name = f"dcpilot2-{condition}-{iid}".replace("_", "-")[:60]
    env = dict(os.environ, CURSOR_API_KEY=key)
    t0 = time.time()
    run = Run(condition, name)
    res = {"instance_id": iid, "condition": condition, "model": model, "valid": False, "infra_failure": "",
           "exit_status": "", "error": "", "agent_version": "", "agent_seconds": 0.0}
    session_ok = False
    try:
        start_container(name, row, slot, work, token, env)
        res["agent_version"] = install_agent(name)
        tool_text = ""
        if token:
            sh(["docker", "exec", name, "ln", "-sf", "/dc/dc-profile", "/usr/local/bin/dc-profile"], 60)
            ok, evidence = run.profile("auto")
            if not ok:
                raise InfraFailure("automatic profile failed:\n" + evidence)
            tool_text = TOOL_TEXT[condition].replace("{evidence}", evidence)
            RUNS_BY_TOKEN[token] = run
        prompt = PROMPT.render(workload=row["workload"], test_cmd=row["test_cmd"], rebuild_cmd=row["rebuild_cmd"],
                               tool_text=tool_text, minutes=WALL_SECONDS // 60)
        (work / "prompt.txt").write_text(prompt)
        (out / "prompt.txt").write_text(prompt)
        agent_cmd = (
            "source /root/.bashrc; cd /testbed; "
            f"timeout {WALL_SECONDS} cursor-agent -p --force --trust --sandbox disabled "
            f"--output-format stream-json --model {model} \"$(cat /dcwork/prompt.txt)\""
        )
        ta = time.time()
        with open(out / "stream.jsonl", "w") as log:
            p = subprocess.run(["docker", "exec", "-w", "/testbed", "-e", "CURSOR_API_KEY", name, "bash", "-c", agent_cmd],
                               stdout=log, stderr=subprocess.STDOUT, timeout=WALL_SECONDS + 300, env=env)
        res["agent_seconds"] = time.time() - ta
        res["exit_status"] = {0: "completed", 124: "TimeExceeded"}.get(p.returncode, f"exit_{p.returncode}")
        session_ok = session_started(out / "stream.jsonl")
        if not session_ok:
            raise InfraFailure(f"no model session ({res['exit_status']}): "
                               + (out / "stream.jsonl").read_text(errors="replace")[-1000:])
    except InfraFailure as e:
        res["infra_failure"] = str(e)[-3000:]
    except Exception:  # noqa: BLE001
        res["error"] = traceback.format_exc()
        session_ok = session_started(out / "stream.jsonl")
        if not session_ok:
            res["infra_failure"] = "runner exception before a model session"
    finally:
        RUNS_BY_TOKEN.pop(token, None)
    diff = ""
    if session_ok:
        d = sh(["docker", "exec", "-w", "/testbed", name, "git", "-c", "core.fileMode=false", "diff", "HEAD"], 120)
        if d.returncode != 0:
            res["infra_failure"] = "could not collect diff: " + d.stderr[-500:]
        diff = d.stdout
    sh(["docker", "rm", "-f", name], 120)
    (out / "patch.diff").write_text(diff)
    res.update(valid=session_ok and not res["infra_failure"], seconds=time.time() - t0,
               profile_calls=run.used, auto_profile_calls=sum(e["kind"] == "auto" and e["status"] == "ok" for e in run.events),
               agent_profile_calls=sum(e["kind"] == "agent" and e["status"] != "refused" for e in run.events),
               profile_events=run.events, patch_chars=len(diff))
    res["error"] = res["error"][-2000:].replace(key, "<redacted>")
    res["infra_failure"] = res["infra_failure"].replace(key, "<redacted>")
    return res


def run_one(model: str, row: dict, condition: str, slot: int, key: str) -> dict:
    out = RUNS / condition / row["instance_id"]
    prev = json.loads((out / "result.json").read_text()) if (out / "result.json").exists() else None
    if prev and (prev.get("valid") or len(prev.get("attempts", [])) >= MAX_ATTEMPTS):
        return prev
    out.mkdir(parents=True, exist_ok=True)
    attempts = (prev or {}).get("attempts", [])
    if not prev and (out / "work").exists():
        # A previous pipeline process died mid-run: archive it and count it as an infra attempt.
        attempts = [{"valid": False, "infra_failure": "pipeline process killed mid-run", "exit_status": "",
                     "seconds": 0.0} for _ in out.glob("interrupted_*")]
        dest = out / f"interrupted_{len(attempts) + 1}"
        dest.mkdir()
        for f in ("stream.jsonl", "prompt.txt", "patch.diff"):
            if (out / f).exists():
                shutil.move(str(out / f), dest / f)
        attempts.append({"valid": False, "infra_failure": "pipeline process killed mid-run", "exit_status": "",
                         "seconds": 0.0})
    res = prev
    for _ in range(ATTEMPTS_PER_CALL):
        if len(attempts) >= MAX_ATTEMPTS:
            break
        res = attempt(model, row, condition, slot, key, out)
        attempts.append({k: res[k] for k in ("valid", "infra_failure", "exit_status", "seconds")})
        if res["valid"]:
            break
        failed = out / f"infra_attempt_{len(attempts)}"
        failed.mkdir(exist_ok=True)
        for f in ("stream.jsonl", "prompt.txt"):
            if (out / f).exists():
                shutil.copy(out / f, failed / f)
        (failed / "result.json").write_text(json.dumps(res, indent=2))
        time.sleep(30)
    res["attempts"] = attempts
    (out / "result.json").write_text(json.dumps(res, indent=2))
    return res


def write_predictions(conditions: list[str], ids: list[str]) -> None:
    """Predictions for valid runs only; infra failures are reported, never scored as results."""
    for c in conditions:
        preds = []
        for iid in ids:
            f = RUNS / c / iid / "result.json"
            if f.exists() and json.loads(f.read_text()).get("valid"):
                preds.append({"instance_id": iid, "model_patch": (RUNS / c / iid / "patch.diff").read_text(),
                              "model_name_or_path": f"{RUN_NAME}_{c}"})
        (HERE / f"{PRED_PREFIX}_{c}.jsonl").write_text("".join(json.dumps(p) + "\n" for p in preds))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tasks", default=str(HERE / "tasks2_final.txt"))
    ap.add_argument("--conditions", nargs="+", default=["C0", "C1", "C2"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    key = cursor_api_key()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    df = pd.read_pickle(HERE / "tasks.pkl").set_index("instance_id", drop=False)
    ids = [a.only] if a.only else Path(a.tasks).read_text().split()
    jobs = [(iid, c) for iid in ids for c in a.conditions]
    random.Random(1).shuffle(jobs)
    slots = list(range(a.workers))
    slot_lock = threading.Lock()

    def go(job):
        iid, c = job
        with slot_lock:
            slot = slots.pop()
        try:
            r = run_one(a.model, df.loc[iid].to_dict(), c, slot, key)
        finally:
            with slot_lock:
                slots.append(slot)
        print(f"{c} {iid}: valid={r['valid']} {r['exit_status'] or r['infra_failure'][:80]!r} "
              f"auto={r['auto_profile_calls']} agent_prof={r['agent_profile_calls']} "
              f"{r['seconds'] / 60:.1f}min patch={r['patch_chars']} attempts={len(r['attempts'])}", flush=True)
        return r

    with ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(go, jobs))
    server.shutdown()
    write_predictions(a.conditions, ids)


if __name__ == "__main__":
    main()
