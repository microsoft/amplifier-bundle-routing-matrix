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
