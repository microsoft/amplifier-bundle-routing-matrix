# Offline routing-matrix evaluation program

**Plan and reconcile; do not execute.** This is maintained routing-specific tooling
owned by this bundle, relocated from the evaluation-library example without changing
the library semantics or historical sample bytes. It implements design v3's bounded
offline contract. It never imports the evaluation runtime, initializes a model,
reads production events, launches a CLI/DTU, fetches data, or enforces budgets.
There is no `run` command, installation change, runtime hook, or generic API change.

Routing owns evaluation configurations, scenarios, graders, reuse rules and promotion
policy; generic execution bricks remain in the separate evaluation library as optional
development dependencies. No evaluation dependency is imported by the production hook.
This directory contains public mechanisms and a synthetic sample, not live raw results.

## Commands and library

From the routing repository root, with an existing Python environment containing Click
and PyYAML:

```sh
export ROUTING_EVAL_BENCHMARK_ROOT=/path/to/pinned/amplifier-benchmark/tasks
python evals/cli.py plan evals/sample_manifest.json \
  --benchmark-root "$ROUTING_EVAL_BENCHMARK_ROOT"
python evals/cli.py readiness evals/sample_manifest.json \
  --benchmark-root "$ROUTING_EVAL_BENCHMARK_ROOT"
python evals/cli.py analyze evals/sample_manifest.json /path/to/private/normalized-evidence.json \
  --benchmark-root "$ROUTING_EVAL_BENCHMARK_ROOT"
```

Every command **requires** `--benchmark-root PATH`. There is no implicit default,
sibling-checkout discovery, download, network access or checkout in the planner.
Supply an existing local tasks directory explicitly. The test environment variable
does not substitute for this CLI option. Reports are JSON on stdout. No
report files are written; saving stdout is a caller decision. Malformed or
unreadable input exits **2** with a redacted JSON error. A valid plan may exit
**0** with rubric warnings. Readiness reports `plan_valid: true` separately from
`execution_supported: false`, `ready: false`, and exits **1**, even with clean
rubrics. Argument/usage errors use Click's normal stderr/exit-2 handling.

`evidence.py` is usable directly. From the routing root, explicitly put `evals/`
on the library import path (or import from a process started in `evals/`):

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path("evals").resolve()))
from evidence import analyze, plan, readiness, read_json

run_plan = plan(
    read_json("evals/sample_manifest.json"),
    Path(os.environ["ROUTING_EVAL_BENCHMARK_ROOT"]),
)
capability = readiness(run_plan)
report = analyze(run_plan, read_json("/path/to/private/normalized-evidence.json"))
```

Inputs and outputs are ordinary dictionaries/arrays. `plan` reads benchmark
files; `readiness` and `analyze` do not. Library validation raises `ValueError`;
filesystem/YAML decoding errors may also propagate. CLI errors do not echo
inputs or private paths.

### Explicit public asset dependency

The sample needs the five public in-repo task trees from
[`microsoft/amplifier-bundle-evaluation` at
`7c3646796eea2b042bbe6ffb2de3906d31daa381`](https://github.com/microsoft/amplifier-bundle-evaluation/tree/7c3646796eea2b042bbe6ffb2de3906d31daa381/amplifier-benchmark/tasks).
Use a separately acquired checkout at that revision and set the variable above to
its `amplifier-benchmark/tasks` directory. Source acquisition is a separate step,
not planner behavior. A local checkout at another HEAD is not presumed equivalent:
`plan` checks actual task-tree/grader hashes and complete criterion locks.

CI acquires that revision automatically using a second pinned `actions/checkout`,
with `persist-credentials: false`, under `/.eval-deps/`. The separate
`routing-evidence` job tests Python 3.11–3.13 with pytest, Click and PyYAML only.
It does not install the evaluator runtime, execute upstream benchmark scripts,
acquire other industry datasets, use provider secrets, or upload result artifacts.
The cache is ignored, not vendored task data. `/evals/results/` is also ignored as
an accidental-output safeguard, **not an approved raw-results location**: raw
results belong in explicit private ignored workspace storage outside source repos.

## Sample, locks and audit

The sample is explicitly **synthetic / exploratory**, not observed evidence or
approval to spend. It embeds the complete `balanced.yaml` data at routing
`183b453c5674fa9c4d51c24cd68e79bce34b28ea` and a deep-copied candidate changing
only `roles.coding.candidates[0].model`: `gpt-6.1-sol` to `gpt-6-astra`.
Both use native `reasoning_effort: high`; the shared root is Sol 6.1/high on the
OpenAI API, fixed through session/settings rather than the matrix `general` role.
Unchanged fallbacks remain intact; they are not experiments on subscription-versus-API
cost. Fallback delivery retains observed completion but blocks model-effect attribution.

The source map locks CLI/Core/Foundation/routing/evaluation and each backend's
provider to 40 lowercase hex characters. These are declared revisions, not
verification of installation or a dirty working tree. Driver/extractor/judge
settings are global and thus identical across arms. Their protocol hashes are
the actual source-file byte hashes at the evaluation lock, and their config
hashes cover the declared identity plus protocol hash. The sample declares
an Anthropic Sonnet 5.5/medium evaluation configuration; it does not initialize
or verify that configuration. Credential **variable names only** are accepted.
Unknown fields, backend endpoints, explicit overrides/pins, recognized secret
shapes, nonfinite values, and malformed locks are rejected. This is not a
general-purpose secret detector; do not put secrets in any input text.

Manifest version 1 fields are demonstrated in `sample_manifest.json`:

* Shared hypothesis, `estimand` (`model` or `effort` only), target role, root,
  exact backend mounts, source/evaluator locks, credential names, seed,
  repetitions, and declared budgets. Null budgets mean undeclared, **not zero**.
* Two ordered arms, `baseline` then `candidate`, each containing the entire
  matrix plus its canonical JSON SHA256. No per-arm evaluator/root overrides.
* Task metadata ID, confined relative path, development/heldout split, exact
  tree/rubric hashes, complete criterion bounds, success/critical thresholds,
  and a false-positive policy for recall/discrepancy rubrics.

`fingerprint` hashes sorted-key compact JSON encoded as UTF-8 (Unicode retained,
array order retained). Matrix hashes cover parsed YAML data, not YAML comments.
`task_tree_hash` hashes a sorted list of `{path, sha256}` for every task file,
including instructions, metadata, profile, grader and binary/hidden fixtures.
Only generated cache directories (`__pycache__`, `.pytest_cache`, `.ruff_cache`,
`.cache`) and `.pyc`/`.pyo` files are excluded; empty directories do not count.
Symlinks, including links inside excluded caches or in ancestor paths, are
rejected. Grader SHA256 hashes its exact file bytes independently.

The pure local task reader follows the existing `load_task` contract for
required files, nonempty instructions, `meta.name` ID (directory name only as
fallback), and timeout. It deliberately avoids importing evaluation/DTU/LLM.
Independent verification compared the five task IDs/timeouts, criterion identities,
point bounds and evaluation weights with the pinned
`amplifier_evaluation.harness.loaders.load_task` and `GraderConfig.from_yaml`.
This is an offline schema integration check, not executor readiness.

The five portfolio locks are from evaluation
`7c3646796eea2b042bbe6ffb2de3906d31daa381`: PDF HR Q2, Knack discrepancies,
CPSC recall monitor, news research tool, and Markdown deck converter. Criterion
identities are **evaluation name + "." + rubric key**, with bounds from all
upstream grader criteria, not arbitrary aggregate scores.

The sample success endpoint provisionally requires every criterion's maximum;
critical thresholds are explicit subsets. These are deliberately conservative
**unqualified exploratory rules**, not approved functional endpoints. The
discrepancy/recall false-positive policy is an explicit qualification gate,
not a claim the upstream score penalizes false positives.

Unresolved `{{...}}` rubric references block execution readiness. Year/recency,
live-URL and model-choice flags require recorded follow-up and repaired, relocked
rubrics. The starter neither executes grader steps nor rewrites/zero-weights
them. Hidden reference provenance, functional endpoint qualification,
strong/weak/adversarial grader calibration, blinding, instrumentation and pricing
remain pending. All readiness is execution-unsupported regardless.

The schedule has 5 tasks × 2 arms × 3 repeats = **30 cells**. Seeded arm-order
randomization is blocked by task/repeat, globally balanced within one first-arm
assignment (15 blocks). Cell/pair IDs derive from the manifest fingerprint;
the plan fingerprint also covers the entire schedule, expected calls, task
audit and limits. Evidence carries both plan and source/matrix/task/rubric locks.
The 1800/4500-second metadata allowances sum to **28.5 subject agent-hours**
for the full schedule; this excludes setup/controller/grading/cleanup and is
neither an elapsed-time prediction nor an enforced lifecycle limit.

## Normalized receipt and analysis semantics

Evidence must be a JSON **array of attempts**, never JSONL or production events.
`synthetic_record` in `test_evidence.py` constructs a complete synthetic example
from a plan without fake placeholder hashes. Tests generate fixtures locally
and remove them; no generated evidence is presented as actual measurements.

Every attempt requires exactly:

* `synthetic`, `plan_sha256`, scheduled `cell_id`, immutable `attempt_id`,
  `sources_sha256`, `matrix_sha256`, `task_sha256`, `rubric_sha256`.
* `setup` and `treatment`: valid/invalid/unknown; `outcome`:
  success/failure/timeout/unknown; `outcome_evidence_ids` (unique receipt IDs).
* `actual_target_calls`: array of `{id, actual_role, backend, model,
  native_config}`. Valid treatment requires at least one call and every supplied
  target call to match the expected role/backend/model/native configuration.
  Other unchanged-role calls belong in an external full trace, not this array.
* `grade`: `{validity, rubric_sha256, criteria, critical}`. Validity is
  valid/invalid/missing; criteria maps exact criterion IDs to bounded awards;
  critical is pass/fail/unknown. Valid requires the complete rubric; partial
  invalid awards remain visible but are not numerical comparisons. Invalid
  grades cannot establish critical pass/fail. Missing grades have empty awards
  and unknown critical status.
* Finite nonnegative `elapsed_s`; `cost`: `{coverage, subject_usd,
  evaluation_usd, application_usd}` where coverage is measured/unknown and each
  component is nonnegative or null; `cleanup`: confirmed/unconfirmed.

These are asserted receipts, **not proof that calls or grades occurred**.
Adapters must classify subject failure/timeout with evidence; controller,
infrastructure, extraction or ambiguous lifecycle faults must not be relabeled
as subject failure. Valid setup plus outcome receipts is needed for completion.
Success additionally needs valid complete grading, critical pass and every
declared success threshold. A failed necessary success threshold remains a
failure when critical status is unknown. Without grading, observed subject success stays
unknown at the functional endpoint; verified subject failure/timeout counts as
completion failure even with no grade. Missing grading never becomes zero.

Analysis retains every scheduled cell, all attempts and all costs. Multiple
attempts block a cell's endpoints/pairs until a preregistered retry policy exists;
the analyzer never selects a best attempt. Quality eligibility requires valid
setup and a valid complete grade, independently of cost, cleanup or subject
outcome; completion additionally requires outcome receipts. Numeric upstream
scores are the existing evaluation-weighted normalized scores and remain
descriptive only. Critical failure may coexist with numeric grading, but cannot
declare functional success.

Missing treatment blocks paired attribution, not arm outcome reporting.
Per-task differences require both single-attempt cells to be quality-eligible
and treatment-valid. Scheduled pair denominators and missing/ineligible pair
counts remain visible; arm completion counts, conservative rate bounds and
missingness accompany comparisons. Durations summarize **all observed attempts**
as median/max/count, not p95.

Cost coverage and cleanup are independent dimensions. Known partial component
totals are labeled lower bounds; wholly unknown totals remain null, never zero.
All attempt components must be measured, all scheduled cells present and no
multi-attempt ambiguity before USD comparison eligibility. Totals still include
blocked/repeated attempts. Unconfirmed cleanup blocks operational cleanup
readiness without erasing an observed outcome. There are no rankings, winners,
confidence intervals, population noninferiority, or automatic model promotion;
synthetic analysis is always non-promotional.

## Exact future adapter boundary (not implemented)

The seam is **one normalized attempt dictionary per scheduled cell** supplied
to `analyze`. Do not add raw event parsing or a money-spending `run` command to
this offline library. A separately authorized adapter must:

1. Reuse pinned `TaskSpec`, `AgentSpec`, `TrialSpec`, installer/DTU, AIUser,
   Extractor and Grader bricks in an isolated subject/controller/assessment
   lifecycle. Existing `run_trial` has no telemetry hooks; wrapping its return
   value is not verified instrumentation. An instrumentation design is required
   before consumer orchestration or any generic runtime change.
2. Enforce pinned source installation, exact secret-env allowlists with
   subject/evaluator separation, fresh subject environments and frozen/blind
   driver/judge protocols. Keep assessment environments and immutable artifacts
   separate; do not grade concurrently in one mutable subject DTU.
3. Establish post-clamp expectations using the **pinned routing planner** for
   matrix + root + caller context before accepting presets/inheritance. Reject
   observationally equivalent arms. Calibration must cover strict effort
   override and above-caller-rung model clamps. This version rejects **any
   preset in either matrix**, explicit slice pins/overrides, changed-candidate
   globs, fallback changes, backend substitutions and whole-policy treatments.
4. Capture authenticated role origin, request/response/config/usage and unique
   call receipts across descendants/retries. Validate each non-target call
   against its complete routing plan too. Redact before normalization; keep raw
   traces privately outside source control. Record subject failure classification,
   complete rubric awards, critical decisions and separate subject/evaluation/
   application costs with pricing provenance. Test timeout/partial-response/
   cancellation uncertainty, blinding and grader faults.
5. Obtain an explicit approved budget and private git-ignored output directory;
   enforce whole-lifecycle time/token/spend/application-egress controls, register
   every resource and reconcile cleanup. Calibrate real instrumentation and
   repaired rubrics before even a paired paid pilot. Unknown subscription/API
   pricing is not zero; parsed-but-inert preset limits are not enforcement.

## Offline author tests

From the routing repository root, use an existing environment with pytest, Click,
PyYAML and CI-pinned Ruff `0.15.11`. No model setup, source build or DTU is required:

```sh
export ROUTING_EVAL_BENCHMARK_ROOT=/path/to/pinned/amplifier-benchmark/tasks
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest -q -p no:cacheprovider --import-mode=importlib evals
ruff check --no-cache evals
ruff format --check --no-cache --config line-length=88 evals
```

The two pinned-portfolio tests require the environment variable and validate actual
task/grader locks through `plan`; absent or wrong assets fail actionably, never skip.
The other tests use synthetic local fixtures without external task data. Tests
exercise Click in process and a direct `evals/cli.py` subprocess from an unrelated
working directory; no expensive evaluation runtime or installed evaluator CLI is
invoked. Formatting uses 88 columns explicitly to retain the original library
bytes without changing the root's 100-column policy or unrelated files.

Original pre-relocation independent verification: **93 tests passed**, Ruff lint/format clean,
actual task/grader schema integration passed. Separate implementation review
identified two reproduced scoring defects; regression tests failed before the
minimal corrections and passed afterward. Both corrections passed re-review.
See `REVIEW.md`. None of these checks establishes live execution readiness.
Relocation preserves those 93 cases and adds 11 bounded regressions for explicit
dependencies, historical sample preservation, redacted errors and import/CWD behavior.