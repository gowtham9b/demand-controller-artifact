"""Pre-registered task sampling: 2 eligible tasks per repository, random.Random(0).

Writes tasks_sampled.json with, per repository, the full shuffled eligible list so that
replacements (see PREREGISTRATION.md) are taken in a fixed order.
"""

import csv
import json
import random
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent / "harness" / "eval_reports" / "eval_report_claude-sonnet-4-5-20250929_maxiter_100_N_v0.51.1-no-hint-run_1.csv"

pre = {r["instance_id"]: float(r["pre_edit_runtime"]) for r in csv.DictReader(open(REPORT))}
df = pd.read_pickle(HERE / "tasks_meta.pkl")
df = df[df.pure_py & df.instance_id.map(lambda i: pre.get(i, 1e9) <= 0.5)]

rng = random.Random(0)
order = {}
for repo in sorted(df.repo.unique()):
    ids = sorted(df[df.repo == repo].instance_id)
    rng.shuffle(ids)
    order[repo] = ids

initial = {k: v[:2] for k, v in order.items()}
# scikit-learn has no eligible task; its two slots go to the largest pool (pandas).
initial["pandas-dev/pandas"] = order["pandas-dev/pandas"][:4]
out = {"eligible_per_repo": {k: len(v) for k, v in order.items()}, "order": order, "initial": initial}
(HERE / "tasks_sampled.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out["eligible_per_repo"], indent=1))
print(json.dumps(out["initial"], indent=1))
