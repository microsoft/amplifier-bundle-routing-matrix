# Bounded Anchors controller/campaign

**Private parent execution only.** These additive files do not change the existing
adapter, routing policy, historical evidence schema, or paid authorization.
`anchors_bridge.py` supplies real authenticated Unix-socket IPC; `anchors_campaign.py`
supplies the serial campaign and concrete Bubblewrap solver/assessor runner.
`solver_entry.py` uses the real existing `AnchorsRun`, never a miniature solver.

## What is and is not established

| Boundary | Evidence supplied here | Remaining qualification |
| --- | --- | --- |
| Controller IPC | Actual local UDS roundtrip with intercepted upstream, independent schema/model/effort/route checks and shared ledger | Parent's selected credential projection and accepted process/mount boundary |
| Two-arm journey | Intercepted orchestration, exact catalog freezing, immutable artifact/grade/report joins | Real installed Core/Foundation/Anchors closure through the new IPC; actual solver OS launch |
| Assessor | Concrete standalone-driver runner and receipt controls; no host execution fallback | Actual positive/bad/malformed/hang/resource/log/cancellation executions and descendant cleanup |

Actual OS execution and assessor qualification are **not established** by these
intercepted tests. Synthetic tool schemas and catalog fixtures are not mounted-schema or
live-model evidence. Dynamic session names are bounded capability claims, **not
independent proof of Foundation role provenance**.

## Parent setup in an existing DTU

Use the parent's already-owned environment; do not create one per cell or request.
Install dependencies **before** denying solver egress. Do not invoke host
`amplifier` or change shared settings/installations.

1. Prepare audited read-only source/runtime projections in the existing DTU.
   Source-select actual native Core, Foundation, stock module sources and the sole
   evaluation `provider-openai` entry point as described in `README.md`. A stock
   provider implementation is import-only. Supply an explicit private
   `Sources(repositories, runtime)` map using the existing byte-lock contracts.
   Complete the real Anchors include closure; do not fetch missing `@main` sources
   while executing. No personal HOME, global settings, browser, key store, `.git`
   credentials, controller storage or hidden cases may enter these projections.
2. Run parent-owned checks against the exact `SandboxSpec` projections. Record a
   private, independently accepted `IsolationAcceptance` bound to `spec.lock`.
   The spec lock includes full projection inventories (no ignored files),
   interpreter/Bubblewrap bytes and launcher source. `resource_envelope` identifies
   the parent's **already-enforced** DTU/cgroup aggregate memory/process/storage
   envelope; per-process rlimits are not an aggregate cgroup limit. Writable `/tmp`
   and `/work` tmpfs mounts each have finite `tmpfs_bytes` capacity.
3. Discover only the configured API provider instance with
   `await select_pair(provider, binding_ref, {"sol": sol_mask, "luna": luna_mask},
   provenance="live")`. This calls its actual `list_models()` once, with no inference.
   Require exactly one bounded latest winner per family. Preserve its provenance
   and private binding; never infer entitlement or served revision from an alias.
   Freeze those exact IDs in `Campaign.catalog` and `Campaign.workers`.
4. Freeze exact **ordered** root and worker wire-tool schemas from an independent
   source-qualified mount/intercept qualification. Store canonical JSON bytes in
   `root_tools`/`worker_tools`; the controller never enrolls schemas supplied by the
   solver. Root model/effort remains identical across A0/B1; only worker model changes.
5. Run the parent entry using its own selected mount's explicit credential-env
   reference. `selected_headers(name)` reads **only that named variable**. It does
   not inspect CLI settings, personal stores, OAuth refresh files or default clients.
   Exact configured HTTPS endpoint is preserved; this profile supports only
   `POST <configured-endpoint>/responses`.

Supported DTU commands (run by the parent):

```sh
# Copy only reviewed source changes / private factory inputs, never a personal HOME.
amplifier-digital-twin file-push "$EXISTING_DTU_ID" \
  evals/anchors_bridge.py evals/anchors_campaign.py evals/anchors_campaign_cli.py \
  evals/solver_entry.py "$DTU_EVALS_DIRECTORY/"

# Trusted parent_factory is installed in the private controller environment.
amplifier-digital-twin exec "$EXISTING_DTU_ID" -- \
  python -B "$DTU_EVALS_DIRECTORY/anchors_campaign_cli.py" run \
  --private-config "$PRIVATE_CONTROLLER_CONFIG" \
  --parent-factory parent_factory:run
```

The factory is trusted parent integration, not a solver-supplied plugin or an
acceptance file parser. The CLI redacts failures and prints only bounded completion
status; full evidence is stored privately. No example binding/path/key is shipped.

### Parent library wiring

`parent_factory.run(config)` constructs these objects from the parent's explicit
private inputs. The API is callable without the CLI:

```python
from anchors_bridge import selected_headers
from anchors_campaign import (
    BubblewrapSandbox, Campaign, IsolatedAssessor, run_campaign, select_pair,
)

async def execute_parent_pair(
    *, selected_provider, binding_ref, family_masks, sources, campaign_id,
    endpoint, effort, root_tool_bytes, worker_tool_bytes,
    solver_spec, solver_acceptance, assessor_spec, assessor_acceptance,
    credential_env, private_output_root, private_cases_bytes,
):
    # Acceptances are independently issued by the parent infrastructure owner.
    # Never deserialize acceptance from solver input or accept a True flag instead.
    solver = BubblewrapSandbox(solver_spec, solver_acceptance)
    assessor = IsolatedAssessor(BubblewrapSandbox(assessor_spec, assessor_acceptance))
    snapshot, pair = await select_pair(
        selected_provider, binding_ref, family_masks, provenance="live"
    )
    campaign = Campaign(
        campaign_id, sources, pair[0], pair, effort, endpoint,
        root_tool_bytes, worker_tool_bytes, snapshot,
    )
    return await run_campaign(
        campaign, private_output_root, selected_headers(credential_env),
        solver, assessor, private_cases_bytes,
    )
```

`SandboxSpec(purpose, python, readonly, projection_locks, resource_envelope, ...)`
requires canonical existing absolute paths and explicit full
`projection_digest(path)` locks. Use a minimal copied runtime root, not `/usr`
plus an arbitrary workspace. Interpreter dependencies, shell tools and source
closure must all be in the audited projection. Full inventory revalidation
detects changed content, including newly introduced credential files; it is not
protection against concurrent parent-side mutation. The parent must keep
projections immutable throughout execution. Broad HOME/store mounts are refused.

`IsolationAcceptance(spec.lock, private_receipt_ref, frozenset(checks))` must be
issued outside the solver. Required checks: `network_denied`,
`credentials_absent`, `private_paths_absent`, `descendants_reaped`,
`resource_bounds`, plus `uds_only` for solver or `assessor_controls` for assessor.
This object is a trusted-parent acceptance result, not cryptographic issuer proof.
To qualify assessor controls initially, the infrastructure owner must independently
run the same bounded driver/launcher spec and retain the results before issuing
acceptance. Do not mark controls passed merely to bootstrap campaign execution.

### Actual OS boundary and negative checks

The concrete launcher uses an empty filesystem root, all unshared namespaces,
private PID/proc, network-none, UID/GID 65534, no capabilities, disabled nested user
namespaces, empty inherited environment, private HOME/tmp/work, finite tmpfs,
an explicit `C.UTF-8` locale, bounded stdout/stderr/CPU/file/address-space/process
limits and closed inherited
descriptors. It binds **only** audited read-only projections. The solver sees one
read-only-bound socket inode at `/ipc/controller.sock`; assessor sees no IPC.
Generated artifacts and private cases execute only in the assessor's separate
namespace. Sandbox exit kills PID-namespace descendants; the parent also reaps
its exact owned outer process group, including during repeated cancellation.
No socket listener survives `Controller.close()` or test cleanup.

The existing DTU's `allow_external` is **not** this security boundary. Independently
probe the actual launched sandbox, retaining positive/negative pairs:

1. A bounded admitted request through `/ipc/controller.sock` succeeds. Attempts
   at external DNS/TCP and alternate local sockets fail, including from bash
   and subprocesses. Never use a paid target for the negative test.
2. A parent canary credential/config/hidden-case file is readable by the parent,
   but neither environment inspection nor filesystem access in the solver finds
   it. No personal-store mounts or access to the outer controller's `/proc`.
3. Direct UDS attempts with wrong/cross-cell capabilities, auxiliary count routes,
   wrong schemas/models/effort, duplicate IDs and altered payload limits reach
   **zero upstream sends**. Attempts which bypass the SDK but remain valid bounded
   IPC are still metered by the authoritative controller.
4. Run actual good/bad/malformed/hang/resource-exceed/log-flood controls using
   immutable artifacts and `IsolatedAssessor.run(make_request(...))`. Reuse public
   `GOOD_SOURCE`, `BAD_SOURCE`, `MALFORMED_SOURCE`, `HANG_SOURCE`,
   `REGRESSION_SOURCE`, `DEVELOPMENT_CASES` from `test_interval_repair.py`;
   those are development controls, not hidden answers. Require restored original
   regression assertion-red and fixed regression green with equal nonempty
   selections. Hang/fault/incomplete grades award nothing, never fake zeros.
5. Cancel a running hanging assessor, await cleanup even under repeated
   cancellation, and independently confirm the owned namespace/process tree is
   absent. Exercise log/output/memory/tmpfs limits and cleanup fault separately.
   Refused namespace setup is a stop, not permission to use host eval.

The emitted checker and generated Python share an assessor trust domain. This
does **not** claim tamper-proof grades against malicious arbitrary Python.
Parent acceptance must explicitly retain that threat-model limitation.

## Limits, custody and reporting

The campaign uses A0 **fresh incumbent** and B1 **changed worker**, not the old
three-cell smoke schedule. The inherited ledger's campaign header still lists
A0/A1/B1; only A0/B1 are admitted by this controller. It remains reused accounting,
not a newly invented ledger. One single-use controller owns both cells and serial
requests; a new output path cannot resume/reset an existing ledger.

Default finite limits: 4096 output tokens, 24 generations/cell, 1200 subject
seconds/cell, 131072 serialized body bytes, 48 campaign requests, 50596608
campaign conservative context-plus-output reservations, 3600 campaign seconds.
Parent infrastructure must additionally impose an independent outer process/DTU
deadline. Cooperative timers refuse new dispatch/execution after expiration;
blocking filesystem/legacy source-lock I/O, OS process creation and mandatory
custody reconciliation can outlast them. These source checks do not prove a hard
OS wall limit, and cancellation never refunds an unresolved request.
The default native context bound still requires independent provider evidence.
Reservations are not estimates of input tokens. Counts/auxiliary requests are
refused before upstream. Complete usage settles request custody. Failed, partial,
timed-out or cancelled responses leave custody unresolved, block later sends,
and keep cost unknown. Duplicate request/payload/response IDs are rejected.

Dollar stop is **None**, not an inflated USD cap. Optional externally qualified
`quote` records observe-only prices; no price or endpoint defaults are shipped.
Unknown prices stay `total_usd: null`, with known lower bound and missing coverage
separate. Controller credentials/headers never enter solver frames, SDK config,
response headers, ledger or reports. JSON credential echoes are refused; arbitrary
covert encodings by a malicious upstream are outside that guarantee.

The solver entry consumes bounded stdin `{spec, capability}` with no key, argv
capability, controller cases or global settings. The entry suppresses ordinary
framework output and returns only immutable artifact bytes, task/grader binding,
resolved preference projection and cleanup. Do not run it directly on the host.
The adapter still performs source-selected real session loading and cleanup.

Private reports join sources/task/grader, scheduled cells, role call receipts,
functional completion, grading, usage accounting, elapsed time and cleanup.
Every cell remains visible when blocked/not-run. Missing served revision remains
unknown: exact catalog IDs alone do not establish exact-comparable reuse.
`refresh_report` reuses existing `candidates.plan_refresh`; the adjacent-cycle
test retains historical receipts and schedules a changed subset plus fresh
incumbent, without selecting by score. Reports are private, **not sanitized
public exports**, and are not broad model winners or automatic promotion.

## Intercepted checks

Use a fresh workspace-local environment with pytest, Click, PyYAML and HTTPX2.
All temporary UDS sockets must live in the worktree. Linux dirfd socket addresses
avoid sockaddr path-length failures in long worktree paths.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -q -p no:cacheprovider --import-mode=importlib \
  --basetemp=.venv/test-tmp \
  evals/test_anchors_bridge.py evals/test_anchors_campaign.py
ruff check --no-cache evals/anchors_bridge.py evals/anchors_campaign.py \
  evals/anchors_campaign_cli.py evals/solver_entry.py \
  evals/test_anchors_bridge.py evals/test_anchors_campaign.py
```

Real-stack qualification still requires the parent's explicit private
`ANCHORS_SOURCE_ROOTS` and actual Core/Foundation pre-imported in the **same**
pytest process, as in `README.md`. Existing adapter tests alone do not exercise
this new authenticated bridge; repeat the stock root/worker repair through the
new `receiver_factory` with independently frozen actual mounted schemas before
calling that boundary qualified. Do not count an empty selection or dependency
skip as success.