# Pilot pre-registration (written before any agent run)

Date: 2026-11-11

## Question
Does metered, ranked profiler evidence help a coding agent optimize real repositories
more than no profiler or a truncated raw profiler dump, at the same step and time budget?

## Tasks
- Source: SWE-fficiency test split (498 tasks).
- Eligible: expert patch edits only `.py` files (no native rebuild needed under emulation),
  and published pre-edit workload runtime <= 0.5 s (from the released Claude Sonnet 4.5
  OpenHands report), to keep profiling and scoring tractable.
- Sample: 2 tasks per repository (9 repositories, 18 tasks), `random.Random(0)` over
  eligible instance IDs sorted alphabetically within each repository.
- Deviation recorded before any run: no scikit-learn task is eligible, so its two slots
  are filled by the next two sampled pandas tasks (pandas has the largest eligible pool).
  The pilot therefore covers 8 repositories and 18 tasks.
- Replacement rule: before any agent run, the expert patch is scored on this machine.
  If its measured improvement is below 1.05x or the harness fails, the task is replaced by
  the next sampled task from the same repository. Replacements are logged.

## Conditions (identical model, prompt, step and time limits)
- C0: no controller tool.
- C1: `dc-profile` returns a cProfile listing sorted by cumulative time, truncated at
  16,000 characters (~4,000 tokens).
- C2: `dc-profile` returns a ranked table: up to 8 repository functions by self-time share
  with file:line, plus the 3 largest non-repository entries (~500 tokens).
- C1 and C2 share the same allowance (4 calls per task) and show a meter after every call;
  the meter is kept on the host and cannot be modified by the agent. Requests beyond the
  allowance return a refusal.
- In every condition the agent may still profile by itself through the shell.

## Agent and limits
- Amended 2026-11-11, before any pilot run: no Anthropic API key was available, so the
  agent is the Cursor CLI (`cursor-agent`, version 2026.11.11-b912975) running headless
  inside each task container, the same harness approach SWE-fficiency used for its
  published Cursor CLI results. Model fixed for all runs: `claude-sonnet-5-5-medium`.
- The Cursor CLI has no step or cost limit, so each run is limited to 30 minutes of wall
  clock (`timeout 1800`). Each container gets 4 dedicated CPUs and 3.5 GB of memory; two
  runs execute in parallel on disjoint CPU sets. The agent's changes are collected with
  `git diff HEAD` when the session ends.
- `dc-profile` inside the container calls a host-side HTTP controller with a per-run
  token; the controller meters the allowance, runs the profiler with `docker exec`, and
  renders the result. Only C1 and C2 containers receive the tool and a token.
- Prompt: SWE-fficiency's released instruction prompt, with the submission instructions
  replaced by "leave your changes in the working tree".
- The original mini-swe-agent design (run_agent.py) is kept for reference but not used.

## Scoring
- SWE-fficiency harness (commit at clone time, with local macOS patches: force x86_64
  images, fixed 4-CPU cpuset inside the Docker VM, 6 GB memory cap), 1 worker.
- Primary: harmonic-mean speedup ratio (overall_score). Secondary: proportion incorrect,
  proportion correct-but-not-faster, profiler calls, self-profiling in shell, cost.
- Paired comparisons across the same 18 tasks with bootstrap 95% CIs (10,000 resamples).

## Amendment 2026-11-11 20:50, before any agent run
- Scoring under emulation took 20-40 minutes per task (pandas workload timing alone
  took 7.5 minutes; scipy rebuilds C++ code), making one-worker scoring take more than a
  day. From this point the harness runs 3 workers on disjoint 4-CPU sets (4-7, 8-11,
  12-15) with 2.5 GB per container; agent runs also use 3 parallel containers (2.3 GB).
  Ten gold tasks had already been scored with 1 worker. Speedups are pre/post ratios
  measured inside one container, so parallel load adds noise but no systematic bias.
- Corporate TLS interception (Zscaler) broke three gold tasks (a workload that downloads
  data; two matplotlib rebuilds that fetch build tools). The harness now copies the
  host's trusted CA certificates into each container (SWEF_EXTRA_CA); those three tasks
  are rescored before the replacement rule is applied.
- Docker memory: two unrelated containers (gitlab, tdm-dev-process-webserver-1) were
  stopped for the duration of the pilot.

## Amendment 2026-11-12 05:40: two pipeline bugs and the correction
- Bug 1 (CA injection): the harness's `copy_to_container` keeps the source file name,
  so the certificate was copied to /tmp/host-ca.pem while the patch read
  /tmp/extra-ca.pem; the fix never applied. Separately, wget ignores the system bundle
  file. Gold tasks that download data or build tools therefore still failed. Fixed and
  verified in a container (pip, curl and default wget all succeed).
- Bug 2 (selection): finalize_tasks.py read validation_report_pilot.json, which every
  harness invocation overwrites, so tasks that had been scored correctly looked
  unscored and were replaced. Fixed to read each task's own perf_summary.txt.
- Consequence: the first 45 agent runs (15 tasks, tasks_buggy_set.txt) used a set that
  is not the pre-registered sample. Replacements still followed the pre-registered
  random order and were fixed before any agent run, so the set does not depend on
  outcomes.
- Correction: gold tasks that failed only because of bug 1 are rescored; the
  replacement rule is re-applied with the fixed code (tasks_final.txt); missing
  agent runs and scoring are completed. Primary analysis: the corrected pre-registered
  set. Secondary analysis: all tasks with complete runs in all three conditions.
  Preliminary results on the 15-task set were inspected before this amendment; they do
  not change the rule or the analysis.

## Known threats
- x86_64 images run under Rosetta emulation on Apple M4 Max; absolute speedups differ from
  published values (probe: expert speedup 2.18x here vs 1.35x published on
  sympy__sympy-10621). Gold and model patches are scored on the same machine.
- n = 18 tasks, one run per task and condition: a pilot, not a definitive result.

# Pilot 2 (pre-registered 2026-11-12, before any pilot-2 agent run)

Pilot 1 did not test the evidence formats: agents called `dc-profile` 8 times in 64
runs, so C1 and C2 mostly ran as C0. It also had pipeline faults. Pilot 1 results
(scores and behaviour) were inspected before this design was written; the changes
below respond to the low tool use and to the faults, not to score differences.
Pilot 2 uses run id `pilot2` and separate outputs (`runs_cursor2/`,
`predictions2_C*.jsonl`, harness logs `logs/run_evaluation/pilot2/`, `results2/`);
pilot-1 artifacts are kept unchanged.

## Fixes to pilot-1 faults
- Profiler runner (`dc/profile_runner.py`). Pilot 1: both `dc-profile` calls on
  pydata__xarray-9001 failed because the runner executed the whole workload script with
  timeit neutralized, so the script's module-level cleanup (deleting the downloaded
  dataset after the timing call) ran before `setup()`. Fix: like the harness's own
  isolation transform, the script runs as `__main__` only up to its first timeit call,
  which raises a sentinel (a BaseException, so `except Exception` cannot swallow it);
  the timed callable, `setup` and `number` come from that call. Each profiled repeat
  calls setup once and the workload `number` times, as timeit does; only workload calls
  are profiled.
- Validation: before any agent run, the controller's profile code path is run once in
  every final task's container (same image, CPU set, memory, mounts and CA setup as an
  agent run) and rendered in both formats (`validate_profiler.py`). Agent runs start
  only if it succeeds on every task; if it fails, the runner is fixed (tasks are not
  dropped) and validation is repeated.
- Harness CA race: `copy_to_container` writes and deletes `<src>.tar` next to the
  source, so with 3 workers the shared CA file's tar was deleted by another worker
  (2 pilot-1 predictions unscored). The CA file is now copied into each instance's log
  directory first.

## Task set and replacement rule
- Same pre-registered sample and random order (`tasks_sampled.json`, including the
  scikit-learn -> pandas deviation). The gold (expert) patch of every candidate is
  rescored under run id `pilot2`; nothing from pilot 1's gold run is reused.
- A task is kept only if, on this machine, the gold patch (a) passes every required
  test: all PASS_TO_PASS tests are PASS in the harness's `covering_test_status.json`
  (the harness's own correctness = 1), and (b) improves the workload by >= 1.05x.
  Otherwise it is replaced by the next task in the same repository's order. Candidates
  still undecided are scored together in rounds (wall time only). If a repository runs
  out of candidates, its slot is dropped and reported. (`finalize2_tasks.py`,
  output `tasks2_final.txt` / `tasks2_final.json`.)
- Gold infrastructure failures (see below) are rescored before the rule decides.
- Amended 2026-11-12 17:25 (see "Pilot 2 amendment" at the end): required tests are the
  PASS_TO_PASS tests that pass on the unmodified code on this machine.

## Evidence design (the main change)
- C0: unchanged (no evidence, no tool).
- C1 and C2: after container setup and before the agent starts, the controller profiles
  the original workload once through the same metered code path as `dc-profile` and puts
  the evidence, rendered in the condition's format (C1 truncated cProfile dump, C2
  ranked table) with the meter, into the initial prompt. The agent may call `dc-profile`
  for further profiles; the allowance stays 4 in total including the automatic profile
  (meter shows "1 of 4 used" at the start). The prompt paragraph describing the tool
  says so (`prompts/tool_dump_auto.txt`, `prompts/tool_ranked_auto.txt`).
- Everything else is identical across conditions and to pilot 1: model
  `claude-sonnet-5-5-medium`, Cursor CLI headless, 30-minute agent wall clock (the
  automatic profile runs before the clock starts), same prompt template, 3 parallel
  containers on CPU sets 4-7, 8-11, 12-15 with 2.3 GB each, jobs in a fixed shuffled
  order (`random.Random(1)`).

## Infrastructure handling
- Agent runs (`cursor_runner.py`). The Cursor CLI install is verified with
  `cursor-agent --version` (3 install tries; pilot 1's install could fail silently
  because `curl | bash` hid curl errors). A run is valid if and only if a model session
  started (the stream contains an init, assistant, tool or result event) after a
  verified install and, in C1/C2, a successful automatic profile, and the diff was
  collected. Anything else is an infrastructure failure: the whole run is retried in a
  fresh container (up to 6 attempts) and is never recorded as a result. A run that
  reached a model session is never retried, whatever its outcome. Failed attempts are
  archived and counted.
- Scoring (`scoring.py`, `score2.py`). Harness: 3 workers, 2.5 GB per container (no
  other containers running). Each scored instance is classified: scored (timing and
  correctness outputs present); infrastructure failure (pre-edit timing failed or timed
  out, i.e. before the patch is applied; OOM/kill signature in the logs; harness-side
  exception; or timing done but correctness outputs missing); patch failure (post-edit
  stage failed with no infrastructure signature; the harness scores it as incorrect /
  no speedup, and so do we). Infrastructure failures are rescored with 1 worker and
  6 GB, up to 2 times. Speedups are pre/post ratios within one container, so the worker
  count changes noise, not the ratio's meaning.
- Predictions contain valid runs only. Unresolved infrastructure failures (agent or
  scoring) are reported separately by condition.
- Docker: the two unrelated containers (gitlab, tdm-dev-process-webserver-1) are
  stopped. With nothing running, Docker Desktop's Resource Saver stopped the VM, and
  its restart revived those restart=always containers (seen during the first smoke
  attempt, which died with the VM and is kept as runs_smoke2_aborted_vm_restart). The
  pipeline therefore keeps one idle 16 MB container on CPU 0 and re-stops the two
  containers if a VM restart revives them (logged).
- Smoke test (runs_smoke2, not analysed): pydata__xarray-9001 in C0, C1, C2 with a
  10-minute clock; all three runs valid, automatic profile delivered in C1 and C2.

## Analysis (`analyze2.py`)
- Primary: every task in the final pilot-2 set, per condition, scored by the harness
  report; an unresolved infrastructure failure is scored as the harness scores a missing
  prediction (incorrect, no speedup) and is reported.
- Secondary: tasks valid (run valid and scored or patch failure) in all three conditions.
- Primary metric: harmonic-mean human speedup ratio (SWE-fficiency overall score), 95%
  bootstrap CIs and paired differences C1-C0, C2-C0, C2-C1 (10,000 task resamples, seed
  0). Added before any pilot-2 run because the harmonic mean is dominated by tasks with
  very large expert speedups (pilot 1): geometric mean of the human speedup ratio, and
  geometric mean of the correctness-adjusted speedup over the original code (1.0 if
  incorrect), with the same CIs and paired differences.
- Also reported: proportions incorrect / correct-no-speedup / faster than baseline /
  matched expert; automatic and agent-initiated `dc-profile` calls, refusals; shell
  self-profiling (same regex as pilot 1); agent minutes; tokens (sessions that reported
  usage); exit statuses; empty patches; infrastructure failures and retries.
- Exploratory: share of runs whose patch edits one of the 3 repository files with the
  most self time in the original workload's profile (from validation), in each
  condition and for the gold patch.
- Expected direction (design principles): C2 >= C1 (ranked beats dump at equal
  allowance) and C1, C2 >= C0. With about 18 tasks and one run per task and condition
  this is a pilot: we report point estimates and CIs and do not claim significance.

## Pilot 2 amendment 2026-11-12 17:25: baseline-relative required tests, crash rescoring (before any pilot-2 agent run)
Approved by the user at 13:45. No pilot-2 agent run had started; only gold scoring
(task selection) had run. The selection step was stopped at 17:16.
- What failed. The rule "gold passes all PASS_TO_PASS tests on this machine" dropped
  tasks for reasons that have nothing to do with the gold patch. On this machine (Apple
  M4 Max, Docker Desktop VM with 16 CPUs / 7.7 GB, x86_64 images under Rosetta) many
  "failing" required tests had no result at all: a test file's pytest process was
  OOM-killed (exit 137; 4 pytest processes per 2.5 GB container) or crashed (exit 133,
  numpy), and its tests were missing from `covering_test_status.json`. Some tests also
  fail or are skipped on the unmodified code here (e.g. AVX512-only tests, 32 astropy
  tests). `scoring.py` classified a run as scored once the timing and test-status files
  existed, so these runs were never rescored with more memory. In about 3.5 h the rule
  scored 31 gold patches and dropped e.g. matplotlib-22108/23287 (0.992/0.991), numpy-21394/
  21832 (0.81/0.84), pandas-43281/26697 (0.9999) and astropy-16295 (0.991), and was
  running out of candidates. The same cause probably inflated pilot 1's incorrect rates
  for numpy and matplotlib (noted for the paper; pilot-1 results are not changed).
- Baseline runs. For every candidate whose gold patch is scored and reaches 1.05x, the
  harness runs the unmodified code once (empty patch, model name `baseline`, run id
  `pilot2`, correctness stage only: same images, CA, test script and settings as other
  runs). A task's required tests are its PASS_TO_PASS tests that PASS in that baseline
  run (`results2/required_tests.json`).
- Amended replacement rule: keep a task if the gold patch passes every baseline-passing
  required test AND improves the workload by >= 1.05x; otherwise replace it as before
  (same `tasks_sampled.json` order, `tasks_initial.txt` start, 2 slots per repository,
  scikit-learn's slots to pandas, xarray has only 2 candidates). Gold results already
  scored under `pilot2` are reused and re-judged under this rule; only missing results
  are scored. Replacements and reasons are in `tasks2_final.json`.
- Crash rescoring (`scoring.py`). A correctness run is an infrastructure failure if a
  test file's pytest ended on a signal (final exit >= 128 after the harness's own two
  retries, e.g. 137 Killed, 133) or never finished, AND at least one required test has
  no result (for baseline runs the required tests are all PASS_TO_PASS tests). Such runs
  are rescored with 1 harness worker, 6 GB, and 2 (first rescore) then 1 (second rescore)
  pytest processes per container (new harness env `SWEF_TEST_WORKERS`; default 4 is
  unchanged), up to 2 times (baseline: once). Earlier infra rules are unchanged.
  Rescored run directories are moved to `logs/run_evaluation/pilot2_superseded/`, never
  deleted. A run whose crash persists keeps its last verdict: missing required tests
  count as not passed (incorrect), as the harness counts them, and are reported.
- Flaky / crash-affected tests are handled the same way everywhere: a test is required
  only if it passed in the (rescored) baseline run, so tests that crash or fail
  deterministically on this machine (e.g. numpy files ending in exit 133) are not
  required. A test that passed at baseline but has no result in a later run because of a
  crash triggers rescoring of that run; if it is still missing, the run is incorrect.
- Applies equally to all conditions. C0, C1 and C2 predictions are scored, rescored and
  judged with the same required-test set and rules (`score2.py`,
  `results2/correctness.json`). `analyze2.py` reports every metric under the
  baseline-relative rule (primary) and under the harness's raw PASS_TO_PASS verdict
  (secondary, `*_raw_harness`), and lists tasks where the two disagree. Speedups are the
  harness's, unchanged.

## Pilot 2 amendment 2026-11-13 (selection bug: harness skips treated as task failures)

Found before any pilot-2 agent run; no agent run, prediction or agent score exists yet.

- Bug. Under launchd the pipeline had no `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`. The
  harness downloads requirements files from GitHub while building a test spec; behind
  the TLS-intercepting proxy that download failed (`SSLError`), and the harness prints
  "Error making test spec" and silently skips the instance (no run directory). Affected:
  pandas, dask, matplotlib, xarray (environments built from requirements files); numpy,
  astropy, scipy, sympy were unaffected. Harness output went to /dev/null, so this was
  not visible. `finalize2_tasks.py` then classified these instances as "missing (never
  run)" and replaced them as if they had failed the rule ("gold not scored (never run)",
  "baseline correctness unavailable (never run)", and "no replacement left; slot
  dropped" for dask and matplotlib). This contradicts the rule above: infrastructure
  failures are retried, never replaced. Reproduced: `make_test_spec` fails for
  pandas-52381, dask-7104, matplotlib-18018 with the CA variables unset and succeeds with
  them set. The selection run was stopped; its log stays in `orchestrate2.log`.
- Fix. `scoring.harness_env` sets `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`
  to `certs/host-ca.pem` (the same bundle already injected into containers) regardless
  of the caller's environment; `supervise2.sh` exports them too. Harness stdout/stderr is
  saved to `results2/harness_logs/`. An instance the harness did not run at all after
  rescoring now stops the selection step (exit 1) instead of being replaced.
- Rerun. The selection step is rerun from the start with the same rule, order and slots.
  Already scored gold and baseline results are reused and re-judged unchanged; only
  instances without results are scored. No rule, threshold, order or metric changes.

# Pilot 2b: second model (pre-registered 2026-11-19, before any pilot-2b agent run)

Pilot 2 used one model. A reviewer asked for more than one coding agent. Pilot 2b
replicates Pilot 2 with a model from a different vendor. Pilot 2 results had been
inspected (they are reported in the revised paper); only the model changes.

- Model: `gpt-5.6-sol-medium`, run through the same Cursor CLI headless command as
  Pilot 2. The scaffold is unchanged, so Pilot 2b tests a second model family, not a
  second agent scaffold. The CLI is installed fresh in each container; its version is
  recorded per run.
- Tasks: `tasks2_final.txt` unchanged (18 tasks). Gold and baseline results are reused
  from run id `pilot2` (linked under `logs/run_evaluation/pilot2b/`); required tests are
  `results2/required_tests.json`, copied unchanged to `results2b/`.
- Before any agent run, profiler validation is repeated in every task container
  (`results2b/profiler_validation.json`), with the same rule as Pilot 2.
- Unchanged: conditions C0/C1/C2, prompts, automatic profile plus 3 calls, 30-minute
  clock, containers and CPU sets, job order `random.Random(1)`, run validity and
  infrastructure retry rules, scoring and crash rescoring, analysis (`analyze2.py`).
- Outputs: run id `pilot2b`, `runs_cursor2b/`, `predictions2b_C*.jsonl`,
  `logs/run_evaluation/pilot2b/`, `results2b/`, `orchestrate2b.log`
  (`orchestrate2b.sh`, `supervise2b.sh`).
- Smoke test (not analysed): `pydata__xarray-9001` in C0 and C2 with a 10-minute clock
  (`runs_smoke2b/`), to check that the model name is accepted and the pipeline runs.
  If the model name is not accepted, another GPT-family model is chosen before any
  analysed run and recorded here.
- Analysis: Pilot 2b is reported as a separate replication with the same primary and
  secondary metrics and paired comparisons. Comparisons across the two models
  (same task, same condition) are exploratory. With 18 tasks this is not powered to
  detect format effects (see the power analysis in the paper).
