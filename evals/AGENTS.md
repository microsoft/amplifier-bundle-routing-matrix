# Routing evaluation program — continuation rules

Read `README.md`, `DESIGN.md`, `REVIEW.md`, `RESULT-REUSE.md` and `../docs/EVALUATION-PROGRAM.md` before changing this maintained routing tooling. Repo conventions and more-specific rules still apply. The v3 offline implementation review and the expanded reuse/catalog method review are distinct: both requested expanded reviewers support scoped planning, not live readiness, fixture clearance or implementation authorization. Keep those boundaries explicit.

## Current executable boundary

`evidence.py` and thin Click `cli.py` implement **offline** plan/readiness/analyze. There is no live executor, production event normalizer, budget enforcer or qualified benchmark result archive. Readiness must remain unsupported until a separately instrumented adapter passes actual acceptance. Synthetic receipts test logic; they are not model-performance results or authenticated traces.

Routing owns its evaluation configurations, scenarios, graders, reuse rules and promotion policy here and in `../docs/EVALUATION-PROGRAM.md`; generic execution bricks belong in the separate evaluation library as optional development dependencies. Never import evaluation tooling/dependencies into the production routing hook. Future authorized adapters reuse TaskSpec/AgentSpec/DTU/installer/AIUser/Extractor/Grader bricks. A stock run_trial completion can contain failed extraction/grading; it is not valid grade evidence. Do not fake injectable lifecycle/telemetry hooks that do not exist.

## Offline verification

From the routing repository root, using an existing environment with pytest, Click,
PyYAML and CI-pinned Ruff `0.15.11`:

```sh
export ROUTING_EVAL_BENCHMARK_ROOT=/path/to/pinned/amplifier-benchmark/tasks
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest -q -p no:cacheprovider --import-mode=importlib evals
ruff check --no-cache evals
ruff format --check --no-cache --config line-length=88 evals
```

Check the actual pinned evaluation `load_task` and `GraderConfig.from_yaml` contracts for new task adapters. Counts, complete criterion IDs/bounds/weights and hashes must agree. Do not launch runtime setup or download protected fixtures just to validate planning. Do not install into a running shared CLI. A scratch AMPLIFIER_HOME does not isolate its shared editable installation.

Only the two original portfolio cases use the explicit benchmark fixture; missing
configuration fails rather than skipping or blocking synthetic test collection.
CI checks out public in-repo assets at `7c3646796eea2b042bbe6ffb2de3906d31daa381`;
see README for acquisition versus offline planning. All CLI commands require
`--benchmark-root`, with no ambient sibling defaults or downloads. Preserve the
historical sample's source/task/grader locks, not a fake new-HEAD update.

Preserve all scheduled cells, immutable attempts and costs. Missing grade is not zero; invalid grade cannot establish critical status; a failed necessary success threshold remains failure despite other unknown critical checks. Unknown cost is not zero. Multiple attempts remain blocked without a reviewed retry policy. Reject inheritance-erased experiments rather than silently measuring equal arms.

## Privacy and execution

No raw event capture reads into agent context. Use the capture-navigation owner for private discovery and bounded versioned adapters for normalized evidence. Do not commit private source maps, account/host identities, secret/config-derived hashes, raw artifacts or heldout answers. Newly authored synthetic public fixtures still need independent keys, lineage/difficulty calibration and license review.

Preserve only generic causal failure mechanisms from private inspiration. Author new domains, structures, inputs and references in a fresh context that has never seen private records. Obtain authorized abstract-handoff clearance and independent finished-fixture privacy/rights review; assess challenge/grader fitness separately. The task's novelty or difficulty does not make it safe to publish.

Live output requires an explicit private ignored directory outside source repos, approved budget and isolated acquisition/subject/assessment environments. No personal HOME/browser/key-store mounts or unmetered application egress. Register resources immediately and reconcile cleanup. Output exports require allowlists, local identity scans and fresh-context review; dashboards and CI artifacts count as publication.

`/.eval-deps/` is only the ignored development asset cache. `/evals/results/` is
an accidental-output safeguard, not an approved raw-results location.

## Separate smoke prototype

`live_smoke.py`, `live_transport.py`, `smoke_cli.py` and `live_provider/` use
`routing-live-smoke/v1`, not the offline experiment schema. It is pre-trial
instrumentation, not permission to spend or change routing policy. Preflight
requires exact source/quote/task/grammar/image-bound qualification evidence and
controller resource authority. A reference string or image boolean is not proof.

Core validates providers with a separate authority-less coordinator. The eval
shim mounts a permanently dormant public Provider there: truthful unavailable
metadata and model/list/parser calls that always refuse, even after cleanup.
Actual root/child initialization and each send require the exact controller
factory object through `provider.before_load` and independent wire gating.
Never bypass validation, authorize by coordinator classname, use a fake
successful inference provider or consult ambient credentials.

Native counts are locally refused before underlying HTTP because their billing
is unqualified. No fake count, successful zero response or byte/token estimate.
Financial reservation uses the parent-qualified full native context bound and
highest long-context category/output rates. The 8192 ceiling is serialized UTF-8
BODY BYTES only; actual tokens come from complete vendor generation usage.
Generation requires explicit default Standard service and exact model/high effort.

The task now discloses `restricted-python-v1` before trials. Its closed AST
grammar forbids imports/reflection/IO/indirect calls/protected rebinding and
separates the model namespace from the trusted driver. Host only parses/hashes;
compile/execute only in the qualified credential-free Docker assessor. Rejected
grammar is ungradable with no fabricated awards. Critical pass means only
observed input immutability across the complete case set, not universal safety.
Driver/validator/image changes invalidate qualification; never broaden grammar
after observing model output. Await assessor custody through repeated cancellation.

Pure smoke tests need no Core/Foundation/SDK installation. Full-stack tests are
selected only after real Core and Foundation are pre-imported in the same pytest
process; invoke them explicitly as in README and check the selected count.
Do not turn their mount failures into skips/xfails. Use one parent-supplied
isolated environment with intercepted HTTP and no credentials; launch no extra
environment and never execute generated artifacts in that subject/controller.
Quotes in tests are explicitly synthetic, not live price evidence.

`test_assessor_controls.py` is an explicit opt-in Docker check, not ordinary CI.
Use a parent-qualified isolation proof and registrar, one control container at a
time. Persist intent/register/claim before creation; destroy only each owned
exact name and independently verify absence. Never sweep other claimed resources.
Raw control journals stay private/ignored; the parent owns publication review.

Do not auto-run paid recurrence or mutate shipping matrix policy. If sources/tasks/grader/runtime change, use the reuse disposition in `RESULT-REUSE.md`; never relabel old scores as fresh execution. Capture tested commands, remaining gaps and agreed decisions here or in the document that owns them, without importing private project context.

## Separate Anchors repair profile

`anchors_adapter.py`/`anchors_transport.py` use `routing-anchors-repair/v2`.
Load the real pinned Anchors closure before applying the declared tool/telemetry
ablation. The root has stock delegate only; builder retains stock filesystem,
search and bash. Its instruction/context are fixed at the tool boundary.
The worker has no delegate or spawn capability. Do not label this app-cli-qualified
or qualification of the unmodified full Anchors UX/telemetry roster.

Use editable, source-selected module installs in a fresh workspace-local env.
A wheel fixture's `package.__file__.parents[1]` may be shared site-packages, not
its source root, causing Core to select an unrelated conventional package.
Keep the evaluation shim as the sole `provider-openai` distribution entry point;
the stock implementation is an explicit import-only source with its dependencies
installed. Never bypass Core validation to fix source selection.

Real-stack tests require explicit private `ANCHORS_SOURCE_ROOTS` JSON and
Core/Foundation pre-imported in the same process. Ordinary controller CI ignores
`tasks/`: solver repo tests execute only through their own subject/assessor path.
Use `python -B` for solver validation; snapshots refuse incidental extra files.
The controller never executes solver artifacts. Solver-local verification needs
the qualified subject environment; private grading executes only in the
parent-qualified assessor.
Controller receipt tests do not prove execution or hostile-code tamper resistance.

The Anchors profile has observe-only cost by default, not a giant dollar cap.
Missing price stays null; finite request/context-token/body/time controls remain.
Complete unpriced usage may report cache writes. Preserve those counts without
inferring read/write overlap or pricing them under a no-write quote. Historical
v1 qualification is not v2 qualification; retain refused live attempts separately.
Native counts and missing external receivers refuse before wire. Parent owns
credential-free solver isolation, independently enforced egress/controller authority,
assessor control execution and DTU/live qualification. Receiver injection is a
supported seam, not proof that those boundaries exist.

Bubblewrap qualification must exercise the actual launcher and projected runtime,
not command construction alone. Use explicit `--unshare-user` with
`--disable-userns`; merged-/usr loader/shell aliases belong in the immutable
sandbox specification and may target only projected system directories.
