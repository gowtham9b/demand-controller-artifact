# Artifact: AI Demand Controller for Resource-Aware Diagnostic Evidence Delivery in Codebase Tuning

Pre-registration, code, prompts, task lists, agent logs, predictions, harness outputs
and analysis scripts for the paper's two pre-registered pilots on SWE-fficiency.

## Contents

| Path | What it is |
|---|---|
| `pilot/PREREGISTRATION.md` | Pre-registration and every timestamped amendment (Pilot 1, Pilot 2, Pilot 2b) |
| `pilot/controller.py`, `pilot/dc/` | Demand controller renderers, `dc-profile` client, cProfile runner |
| `pilot/cursor_runner.py` | Runs the Cursor CLI agent in each task container; host-side metered controller |
| `pilot/prompts/` | Task prompt and the C1/C2 tool paragraphs (on-demand and automatic delivery) |
| `pilot/select_tasks.py`, `finalize_tasks.py`, `finalize2_tasks.py` | Task sampling and replacement rules |
| `pilot/tasks_*.{txt,json}`, `tasks2_final.*` | Sampled order, final task sets, replacements and reasons |
| `pilot/validate_profiler.py` | Pre-run profiler validation in every task container |
| `pilot/scoring.py`, `score2.py` | Scoring, crash rescoring, baseline-relative correctness |
| `pilot/analyze.py`, `analyze2.py` | Analyses for Pilot 1 and Pilot 2 (all numbers in the paper) |
| `pilot/orchestrate*.sh`, `supervise*.sh` | Pipelines as run |
| `pilot/runs_cursor/`, `pilot/runs_cursor2/` | Per-run agent stream logs, prompts, patches, metadata (Pilot 1, Pilot 2) |
| `pilot/predictions*_C*.jsonl` | Predictions submitted to the harness |
| `pilot/results*/` | Analysis outputs (`summary.json`, `per_task*.csv`, correctness, profiler validation) |
| `harness_logs/pilot/`, `harness_logs/pilot2/` | SWE-fficiency harness outputs per instance (gold, baseline, C0-C2) |
| `eval_reports/` | Harness reports per condition |
| `pilot/harness_commit.txt`, `pilot/harness_macos.patch` | Harness commit and local patches |
| `paper/` | Paper source and PDF |

Files larger than 5 MB are gzipped. Run `find . -name '*.gz' -exec gunzip {} +` before
re-running any script.

Removed for release: the API key file (`.env`), the corporate proxy's CA certificate
(also stripped from harness logs), harness-generated test scripts, raw per-test-file
pytest output and image tarballs.

## Reproducing the paper's numbers from the logs

```bash
git clone https://github.com/swefficiency/swefficiency harness
git -C harness checkout "$(cat pilot/harness_commit.txt)"
git -C harness apply ../pilot/harness_macos.patch
mkdir -p harness/logs/run_evaluation harness/eval_reports
cp -r harness_logs/* harness/logs/run_evaluation/
cp eval_reports/* harness/eval_reports/
cd pilot
python analyze2.py          # Pilot 2: results2/summary.json, results2/per_task.csv
DC_RESULTS=results_all DC_TASKS=tasks_all_run.txt python analyze.py   # Pilot 1, all complete tasks
python analyze.py           # Pilot 1, pre-registered set
```

`analyze*.py` need `numpy` and `pandas`. Bootstrap seed 0, 10,000 resamples.

## Re-running the experiment

Requirements: Docker (x86_64 images; the paper used Docker Desktop on Apple silicon
under Rosetta), the harness above with its virtual environment in `harness/.venv`,
an agent environment in `../.venv-agent` with `pandas` and `jinja2`, and a Cursor API key
in `../../.env` as `CURSOR_API_KEY=...` (read by `pilot/keyfile.py`). Then run
`pilot/orchestrate2.sh`. Each step is resumable. Settings are listed in Table III of
the paper and in `PREREGISTRATION.md`.
