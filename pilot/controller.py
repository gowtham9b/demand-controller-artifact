"""Host-side demand controller: meters, runs and renders profiler evidence.

The agent issues `dc-profile`; the controller (outside the container, so the agent
cannot alter the meter) checks the allowance, runs cProfile on the task workload
inside the container, and returns the evidence in the condition's format.
"""

from __future__ import annotations

import json
import re
import time

from minisweagent.environments.docker import DockerEnvironment

DUMP_CHARS = 16_000
RANK_REPO = 8
RANK_OTHER = 3
PROFILE_CMD = re.compile(r"^\s*(cd\s+\S+\s*&&\s*)?dc-profile\s*;?\s*$")


def _loc(f: dict) -> str:
    path = f["file"]
    if path.startswith("/testbed/"):
        path = path[len("/testbed/"):]
    if path == "~":
        return f["func"]
    return f"{path}:{f['line']} {f['func']}"


def _funcs(data: dict) -> list[dict]:
    return [f for f in data["funcs"] if not f["file"].startswith("/dc/") and "profile_runner" not in f["file"]
            and not (f["file"] == "~" and "disable" in f["func"] and "Profiler" in f["func"])]


def render_dump(data: dict) -> str:
    funcs = sorted(_funcs(data), key=lambda f: -f["cumtime"])
    lines = [
        f"cProfile of workload(): {data['iters']} calls, {data['wall']:.3f}s profiled "
        f"(times are totals over all calls, sorted by cumulative time)",
        "   ncalls  tottime  cumtime  filename:lineno(function)",
    ]
    for f in funcs:
        nc = f"{f['ncalls']}/{f['primcalls']}" if f["ncalls"] != f["primcalls"] else str(f["ncalls"])
        lines.append(f"{nc:>9} {f['tottime']:8.4f} {f['cumtime']:8.4f}  {f['file']}:{f['line']}({f['func']})")
    text = "\n".join(lines)
    if len(text) > DUMP_CHARS:
        text = text[:DUMP_CHARS] + "\n[... output truncated at ~4,000 tokens]"
    return text


def render_ranked(data: dict) -> str:
    funcs = _funcs(data)
    n = data["iters"]
    total = sum(f["tottime"] for f in funcs) or 1e-12
    repo = sorted((f for f in funcs if f["file"].startswith("/testbed/") and not f["file"].endswith("workload.py")),
                  key=lambda f: -f["tottime"])
    other = sorted((f for f in funcs if not f["file"].startswith("/testbed/")), key=lambda f: -f["tottime"])
    other_share = sum(f["tottime"] for f in other) / total
    lines = [
        f"Ranked hotspots for workload() (cProfile, {n} calls; times per call)",
        " #  self%   self ms   cum ms   calls  repository location",
    ]
    for i, f in enumerate(repo[:RANK_REPO], 1):
        lines.append(f"{i:>2} {100 * f['tottime'] / total:5.1f}% {1000 * f['tottime'] / n:9.3f} "
                     f"{1000 * f['cumtime'] / n:8.3f} {f['ncalls'] / n:7.0f}  {_loc(f)}")
    if other:
        top = "; ".join(f"{_loc(f)} {100 * f['tottime'] / total:.1f}%" for f in other[:RANK_OTHER])
        lines.append(f"Outside the repository: {100 * other_share:.1f}% of self time. Largest: {top}")
    return "\n".join(lines)


RENDERERS = {"C1": render_dump, "C2": render_ranked}


class ControllerEnvironment(DockerEnvironment):
    """Docker environment that serves `dc-profile` through the demand controller."""

    def __init__(self, *, condition: str, allowance: int = 4, **kwargs):
        self.condition = condition
        self.allowance = allowance
        self.used = 0
        self.events: list[dict] = []
        super().__init__(**kwargs)

    def _meter(self) -> str:
        return f"[dc-profile allowance: {self.used} of {self.allowance} calls used; {self.allowance - self.used} remaining]"

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict:
        command = action.get("command", "")
        if self.condition in RENDERERS and "dc-profile" in command:
            if not PROFILE_CMD.match(command):
                return {"output": "dc-profile must be run as a standalone command, e.g. `dc-profile`.",
                        "returncode": 2, "exception_info": ""}
            return self._profile()
        return super().execute(action, cwd, timeout=timeout)

    def _profile(self) -> dict:
        t0 = time.time()
        if self.used >= self.allowance:
            self.events.append({"t": t0, "status": "refused"})
            return {"output": "Request refused: profiling allowance exhausted. Continue by editing and testing.\n"
                              + self._meter(), "returncode": 1, "exception_info": ""}
        self.used += 1
        out_path = f"/tmp/dc_prof_{self.used}.json"
        run = super().execute({"command": f"python /dc/profile_runner.py /dcwork/workload.py {out_path}"},
                              "/testbed", timeout=600)
        if run["returncode"] != 0:
            self.events.append({"t": t0, "status": "error", "seconds": time.time() - t0})
            return {"output": "Profiling failed:\n" + run["output"][-3000:] + "\n" + self._meter(),
                    "returncode": 1, "exception_info": ""}
        raw = super().execute({"command": f"cat {out_path}"}, "/testbed", timeout=120)
        data = json.loads(raw["output"])
        text = RENDERERS[self.condition](data) + "\n" + self._meter()
        self.events.append({"t": t0, "status": "ok", "seconds": time.time() - t0, "chars": len(text),
                            "iters": data["iters"], "n_funcs": len(data["funcs"])})
        return {"output": text, "returncode": 0, "exception_info": ""}
