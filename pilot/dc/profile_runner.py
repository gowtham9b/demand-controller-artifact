# Runs inside the task container (Python 3.6+). Profiles the task's workload()
# with cProfile and writes raw per-function statistics as JSON.
# Usage: python profile_runner.py <workload.py> <out.json>
#
# Like the SWE-fficiency harness, the workload script is executed as __main__ only up
# to its first timeit call; the timed callable, setup and `number` are taken from that
# call. Code after the call (e.g. deleting downloaded data) never runs, so setup()
# still finds what the module-level code prepared.
import cProfile
import json
import os
import pstats
import sys
import time
import timeit
import types

TARGET_SECONDS = 2.0
MAX_REPEATS = 50

src_path, out_path = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
with open(src_path) as f:
    src = f.read()


class _TimingCall(BaseException):
    """Raised at the workload's timing call; BaseException so `except Exception` cannot swallow it."""


captured = {}


def _capture(stmt, setup, number):
    captured.update(stmt=stmt, setup=setup, number=number)
    raise _TimingCall()


def _repeat(stmt="pass", setup="pass", timer=None, repeat=5, number=1000000, globals=None):
    _capture(stmt, setup, number)


def _timeit(stmt="pass", setup="pass", timer=None, number=1000000, globals=None):
    _capture(stmt, setup, number)


class _Timer(object):
    def __init__(self, stmt="pass", setup="pass", timer=None, globals=None):
        self.stmt, self.setup = stmt, setup

    def timeit(self, number=1000000):
        _capture(self.stmt, self.setup, number)

    def repeat(self, repeat=5, number=1000000):
        _capture(self.stmt, self.setup, number)

    def autorange(self, callback=None):
        _capture(self.stmt, self.setup, 1)


real = (timeit.repeat, timeit.timeit, timeit.Timer)
timeit.repeat, timeit.timeit, timeit.Timer = _repeat, _timeit, _Timer
_runner = sys.modules["__main__"]
main = types.ModuleType("__main__")
main.__file__ = src_path
sys.modules["__main__"] = main
sys.argv = [src_path]
sys.path[0] = os.path.dirname(src_path)
os.chdir("/testbed")
try:
    exec(compile(src, src_path, "exec"), main.__dict__)
    stopped = False
except _TimingCall:
    stopped = True
finally:
    timeit.repeat, timeit.timeit, timeit.Timer = real

if stopped:
    workload = captured["stmt"] if callable(captured["stmt"]) else main.__dict__["workload"]
    setup = captured["setup"] if callable(captured["setup"]) else None
    number = max(1, int(captured["number"]))
else:
    workload = main.__dict__["workload"]
    setup = main.__dict__.get("setup") if callable(main.__dict__.get("setup")) else None
    number = 1


def one_repeat(prof=None):
    """One timeit repeat: setup once, then `number` workload calls (only these are profiled)."""
    if setup:
        setup()
    if prof:
        prof.enable()
    for _ in range(number):
        workload()
    if prof:
        prof.disable()


t0 = time.perf_counter()
one_repeat()
one = max(time.perf_counter() - t0, 1e-6)
repeats = int(max(1, min(MAX_REPEATS, TARGET_SECONDS / one)))

prof = cProfile.Profile()
wall0 = time.perf_counter()
for _ in range(repeats):
    one_repeat(prof)
wall = time.perf_counter() - wall0

stats = pstats.Stats(prof).stats
funcs = []
for (fn, ln, name), (cc, nc, tt, ct, callers) in stats.items():
    funcs.append({
        "file": fn, "line": ln, "func": name, "ncalls": nc, "primcalls": cc,
        "tottime": tt, "cumtime": ct,
        "callers": [[c[0], c[1], c[2], v[3]] for c, v in callers.items()],
    })
iters = repeats * number
with open(out_path, "w") as f:
    json.dump({"iters": iters, "repeats": repeats, "number": number, "stopped_at_timing_call": stopped,
               "wall": wall, "single_call_s": one / number, "funcs": funcs}, f)
print("ok", iters, round(wall, 3))
