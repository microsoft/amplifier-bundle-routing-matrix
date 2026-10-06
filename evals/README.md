# Routing-matrix evaluation program

**Plan and reconcile; do not execute.** This is maintained routing-specific tooling
owned by this bundle, relocated from the evaluation-library example without changing
the library semantics or historical sample bytes. It implements design v3's bounded
offline contract. It never imports the evaluation runtime, initializes a model,
reads production events, launches a CLI/DTU, fetches data, or enforces budgets.
There is no `run` command in `cli.py`, installation change, runtime hook, or
generic API change. A separate, blocked smoke prototype is described below; it
does not change offline v1 or make its readiness supported.

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

## Separate bounded smoke prototype

**Pre-trial qualification, not paid execution authority.** `smoke_cli.py`
exposes `preflight`, `run-baseline`, `run-pair` and `report` for the separate
`routing-live-smoke/v1` contract. No shipped policy or offline v1 readiness changes.

The evaluation-only shim now passes unchanged Core validation by mounting a
permanently dormant, truthful unavailable Provider when no factory exists.
That object never constructs a client and always refuses inference, listing
and parsing. Actual sessions use the pinned OpenAIProvider, public `client=`
injection and exact factory-object authority checked before load and before
send. A capability key, provider class or coordinator classname is not authority.
The standalone Foundation child receives only actual coding-resolver preferences
and has zero tools. Current SDK 3.24 uses its supported HTTPX2 client/transport;
the older SDK qualification is historical.

Native count requests are refused **before underlying HTTP**, with local
refusal receipts, not fake successful counts. Count billing remains unknown.
Financial admission reserves the externally qualified full native context
window and highest long-context input/output rates, rounded upward to cents:
one Sol liability 5.32 USD; one Astra liability 26.56 USD. These are liabilities,
not expected spend. The internal envelope is 100 USD campaign / 40 USD cell,
three generations per cell (two root, one worker). The 8192 bound is UTF-8
serialized BODY BYTES, not input tokens. No local estimate establishes a dollar
bound. Requests require exact model/high effort, explicit default Standard tier,
nonstreaming/store:false, the controlled root function or tool-free worker, and
finite HTTP timeouts. Unknown usage/errors retain full liability; complete
vendor gross/cache/reasoning usage alone may settle it without double billing.
Quote rates/window/category semantics must come from parent-qualified evidence,
never provider tables. Test quotes are synthetic.

The synthetic task explicitly discloses `restricted-python-v1`: a finite
task-specific AST grammar, protected bindings, direct approved calls/methods,
no imports/reflection/IO/private names and separate model/driver namespaces.
Host parses/hashes only. The assessor independently validates immutable source
and normalized hashes inside a pinned credential-free network-none/nonroot
read-only capability-dropped container. Expected answers remain controller-side.
Correct, nonmerge, bool, mutation, constant and hang controls exercise actual
Docker execution; spoofing and malformed code are refused before execution.
Grammar refusal or incomplete grading yields no awards. Critical pass denotes
observed input immutability on the complete set only. This is not arbitrary
Python sandbox support.

Preflight requires the exact source/quote/task/grammar/driver/image-bound
qualification receipt, isolated controller/output authority and accounted
resource-cost policy. Only parent-verified no-charge infrastructure is currently
supported; priced resources require a separately implemented reservation and
are refused, not silently treated as free. Hashes provide integrity and binding, not a trusted
issuer: the parent must accept/pin the evidence. Old reference strings and
image booleans cannot enable execution. Missing qualification remains blocked.
An independently accepted whole-cell run/assessment/cleanup handoff and real
quote are separate from direct SDK or synthetic CLI checks.

The assignment is A0 instrumentation baseline, then fresh A1/B1 serial cells;
the candidate changes only the coding model leaf. The root stays fixed.
Descriptive instrumentation does not establish modern-model discrimination,
model ranking, routing promotion, account containment or deployed adoption.
All scheduled cells remain in offline reports, including blocked/not-run cells.

### Check without model calls

Dependency-light checks (pytest/Click; HTTPX is optional on this path):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest -q -p no:cacheprovider --import-mode=importlib \
  evals/test_live_transport.py evals/test_live_smoke.py
```

Explicit real-stack checks, **only in the separately supplied isolated mock
environment** with the real native Core/Foundation, stock loop/context,
provider, routing module and SDK installed, plus the local evaluation-only shim:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -c "import amplifier_core, amplifier_foundation, pytest; \
raise SystemExit(pytest.main(['evals/live_tests', '-q', '-p', 'no:cacheprovider', \
'--import-mode=importlib']))"
```

Ordinary offline CI does not select those full-stack cases or import optional
runtime dependencies. Explicit qualification must verify a nonempty selection;
absence is not a pass. Retained actual root/child positive checks now require
successful unchanged Core validation, zero transmitted counts, exact high effort
and Standard tier, parentage, routing resolution and closure. Authority-negative
checks cover absent/replaced/copied factories and replacement before send.
Direct SDK guards do not replace those real session checks.
No generated solution executes in these tests.

### Private controller input

The library accepts frozen `CampaignSpec`, `CellSpec`, `SmokeLimits`,
`PriceQuote`, `AdmissionAuthority` and `AssessmentSpec` objects. The thin CLI
reads the same private contract via `load_campaign`; no sample containing
private configuration is shipped. Private source locks cover bounded complete
package trees, the native Core artifact, task, and adapter/assessor code.
Quotes contain externally verified timestamps, model rates, binding reference,
currency/cache/window semantics and long-context rates; there are no live
pricing defaults. `AssessmentAuthority` pins the registrar/claim scripts and
private staging root. Resource intent and registration precede create; cleanup
uses exact owned names and an independent absence probe. Whole-cell execution
reserves time for assessment and cleanup and retains assessor custody through
repeated cancellation. Parent-owned resources are never swept by this adapter.

`--output-dir` must be exactly the qualified private root plus the campaign ID,
outside source/package trees, with private permissions. Changing the directory
cannot reset the same campaign's ledger; changing the spec cannot reuse its
existing ledger. Output-root exclusion from publication still needs independent
qualification. The dedicated runtime-only `SMOKE_OPENAI_CREDENTIAL` is never
read by preflight/report or placed in argv, source, bundle config or receipts.
Missing source-bound execution qualification prevents both execution commands
from reaching that credential read or making any paid request. This source is
not itself a paid authorization or accepted raw-result archive.

```sh
python evals/smoke_cli.py preflight --spec "$PRIVATE_SPEC" --output-dir "$PRIVATE_OUTPUT"
python evals/smoke_cli.py report --spec "$PRIVATE_SPEC" --output-dir "$PRIVATE_OUTPUT"
```

Malformed input exits 2, readiness/measurement/protocol blockers exit 1,
valid offline reporting exits 0. No live trial, broad model-quality conclusion,
promotion or automatic publication is established by these mock/control checks.

## Foundation-hosted Anchors interval repair

This separate executable library uses **`routing-anchors-repair/v2`**. Offline
v1 and the restricted smoke profile above retain their contracts. It is not a
generic eval runner, an app-cli qualification, or promotion evidence.

V2 preserves complete reported cache-write usage under unpriced observe-only
accounting. It does not infer category overlap or apply a no-write quote to
writes. V1 source/qualification and refused trials remain historical; changes to
the accounting profile require fresh source-bound qualification.

`anchors_adapter.load_anchors` loads the complete real
Foundation `bundles/anchors.md` closure through a private nonpersistent registry.
Every declared Git source resolves to an explicit content-locked local repository;
missing roots fail before fetch. It loads actual agent metadata, then applies a
declared evaluation ablation: stock delegate only at the root; real
`anchors:builder` `[coding, general]` with filesystem/search/bash in the child;
no unrelated UX, logging or Context Intelligence hooks/tools. Instructions and
namespaced context remain real Anchors content. Stock tool-delegate reaches a
thin `session.spawn` adapter forwarding Foundation's `before_initialize` callback.
Child composition is complete/nonrecursive (`compose=False`), not parent-tool
inheritance. The role resolver selects the worker; direct preferences are refused.
The fixed instruction and `context_depth=none` are checked before delegate execution.

### Controller API and parent-owned isolation

The public library seams are:

1. `Sources(repositories, runtime)` with `RepositoryLock` and existing `SourceLock`
   inventories: private paths/content locks for complete declared closure and
   actually imported Core/native artifact, Foundation, modules, provider/SDK/HTTP.
2. `AnchorsLedger(path, campaign_lock, Limits())`, `start_cell("A0")`, and
   `Authority(ledger, quote_or_none, exact_configured_endpoint, True, True)`.
   Qualification flags are **parent assertions**, not authenticated proof.
3. `AnchorsRun(sources, authority, new_repo_path, private_matrix_dir, cell_id,
   root_model, worker_model, root_effort, worker_effort, receiver_factory)`.
   `await run.run()` returns immutable artifact bytes; always
   `await run.close()` in `finally`. The parent owns cell finish/abort, assessor,
   private receipt retention and overall cleanup.
4. `repair_assessor.make_request(artifact, private_cases)` and
   `repair_assessor.assess(artifact, private_cases, isolated_runner=qualified_runner)`.
   The runner contract is documented in that module; absence refuses. Its emitted
   standalone driver can execute arbitrary repair code **only in the assessor**.
5. `candidates.discover(selected_provider, binding_ref, family_masks,
   required_capabilities, provenance=...)`, saved exact snapshots, and
   `plan_refresh(...)`. `candidates_cli.py subset` is a saved-JSON Click wrapper,
   not a discovery client, scheduler, credential reader or matrix editor.

**No live-safe external controller is provisioned here.** `receiver_factory(policy)`
must return an HTTPX-compatible receiver (`handle_async_request`, `aclose`).
It receives the already admitted finalized SDK request and returns the complete
vendor JSON response. A missing receiver cannot fall back to direct HTTP.
The SDK uses only an inert auth placeholder and preserves the exact configured
gateway URL. The parent must wire that receiver to a separately credentialed
controller, which independently enforces exact session/binding/request admission.
The solver must have no upstream key in environment, home, settings, mounted
files or accessible controller storage. Independently deny direct/unmetered
network from bash and generated applications; a DTU `allow_external` setting
or a substituted dummy key does not establish this. Direct SDK endpoint/schema
negative tests do **not** establish OS/network containment. An arbitrary callable
receiver is not an authenticated external authority. These missing parent
boundaries are blockers to live execution, not reasons to simulate auth.

Before admission, discover the selected configured binding's actual catalog and
freeze candidate IDs. Fix one root configuration across the pair. Resolve both
assigned arms under the same source/root/context policy and call
`require_distinct_arms` on their post-resolver model/config projections. This
bounded adapter constructs a preset-free coding slice; it does not qualify an
arbitrary preset experiment. Inherited/erased arms must not be relabeled a model
comparison. Run only the changed subset plus a fresh incumbent anchor, not a
historic sweep. Actual delivered service revision may remain unknown even with
an exact catalog ID; such receipts cannot be exact-comparable reuse.

### Limits and accounting

Proposed tiny pilot maximum: **24 generations per cell**, at most two root
generations, **4096 output tokens per generation**, **131072 UTF-8 body bytes**,
**1200 seconds** for subject loading/preparation/execution, and a conservative
**25298304 reserved context+output tokens** across all attempts. The native
context upper bound (default 1050000) needs independent parent/provider evidence;
body bytes are not input tokens. All limits can be lowered, not raised.
Assessment and cleanup have separate finite allowances and need an outer parent
lifecycle deadline. Cancellation preserves unresolved remote/accounting state.

`Limits(dollar_ceiling=None)` is explicit observe-only cost. Complete generation
usage is metered even without prices; missing cost stays `total_usd: null`, with
known priced lower bound and missing-request count separately. An optional
externally sourced `Quote` reuses the smoke USD/cache/reasoning-token semantics;
no live prices are shipped. A requested dollar ceiling requires a valid quote.
Native count requests refuse before receiver, retries are disabled and repeated
logical/payload/usage receipts refuse. Unknown/partial generation usage retains
unresolved custody and prevents another generation. Invalid supplied quotes
are explicit accounting qualification errors; the parent can run an approved
observe-only trial with `quote=None` rather than a guessed price or giant cap.

### Repair and objective assessment

`tasks/interval-repair-v1` is newly authored, MIT-covered mathematical development
input: validating but buggy union code, public tests and instructions. It is an
actual repo repair, not a restricted snippet-generation task. The builder must
retain `test_regression.py`; byte snapshots protect public inputs and exclude
symlinks/hardlinks/unexpected files. Use `python -B` for local tests.

The assessor receives private cases separately (overlap, touching, order,
invalid-input policy, observed input immutability). It checks immutable copied
artifacts, public tests, repaired-code regression green and identical retained
regression assertion-red on restored original code, with nonempty equal
selections. Missing/malformed/hanging/control/cleanup failures remain invalid or
failed, never fake zero awards. Public good/bad/malformed/hang controls are in
`test_interval_repair.py`; they are **not hidden benchmark answers**. Ordinary
tests validate receipts without executing solver code. Parent must execute those
controls in its qualified assessor and retain cleanup proof before accepting
grader qualification. Separate processes do not make the emitted checker
tamper-proof against actively malicious arbitrary Python; that boundary is not
claimed.

### Qualification command (intercepted, no live requests)

Prepare a **new local env or parent tester DTU**, with actual Core/Foundation and
stock runtime/tool dependencies. Source-select the local shim, avoiding the
shared-site-packages ambiguity described in AGENTS. `ANCHORS_SOURCE_ROOTS` is
private JSON mapping exact repository names to pinned local roots; pass it
explicitly. The complete required map is determined by the stock closure and
fails when a transitive source is missing, never falling back to `@main`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -c "import amplifier_core, amplifier_core.models, amplifier_foundation, pytest; \
raise SystemExit(pytest.main(['evals/live_tests', 'evals/test_anchors_transport.py', \
'-q', '-p', 'no:cacheprovider', '--import-mode=importlib']))"
```

Check selected counts, not a dependency-induced skip. The real-stack positives
use synthetic Sol/Luna IDs only as intercepted configurations, not discovery or
quality evidence. They exercise actual stock delegation and filesystem repair,
exact gateway preservation, effective effort, usage and cleanup. Latest catalog
discovery, tester DTU adoption, external credential/egress authority, actual
assessor controls and the paid pair remain parent-owned qualification. The one
synthetic family is provisional plumbing evidence, not a model preference.

Source checks for this increment: Python **3.13.11**, actual native Core and
Foundation pre-imported in the same pytest process, **1826 passed, zero skips**
(189 root, 669 routing-module, 938 evaluation-controller, 17 retained smoke-stack
and 13 Anchors-stack cases), plus four subtests. A fresh dependency-light Python
**3.11.14** env with pytest/Click/PyYAML only passed **891 controller cases**,
zero skips; the 77 real-runtime/optional HTTPX cases were not selected there,
not claimed passed. Ruff **0.15.11** lint/88-column scoped formatting and bundle
structure passed. No live discovery/inference, solver bash execution, DTU or
assessor execution occurred. Independent source/security/privacy review cleared
limited implementation publication, not the parent-owned execution gates above.