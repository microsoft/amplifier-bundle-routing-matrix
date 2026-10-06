# Routing catalog and evidence handoff — updated 2026-10-06

**Current main contains the bounded catalog and maintained offline evaluation
program**, delivered in `f8bd250`. The vision and catalog contract remain DRAFT,
not ratified or frozen. The implemented API is documented in
[catalog-api](catalog-api.md), including two additive exact-module OpenAI
profiles. Repository delivery is not consumer adoption, mandatory dispatch
containment or live model-quality evidence.

The remainder of the design-review and continuation record below preserves the
October 2 implementation history. Its verification counts are historical, not
results of a new evaluation campaign. Current offline usage is documented in
[evals/README](../evals/README.md); historical model-policy decisions are indexed
in [evals/REVIEW](../evals/REVIEW.md#historical-routing-decisions).

## Read in this order

1. `AGENTS.md`, `README.md`, `docs/PROVIDER_AVAILABILITY.md` and applicable module/test conventions.
2. `docs/VISION.md` and `contracts/routing-catalog.v1.md` for proposed ownership/promises.
3. `docs/CATALOG-SPEC.md` for concrete identity/scope/preview/discovery cases.
4. `docs/EVALUATION-PROGRAM.md` for hard-task sourcing, reuse, privacy and recurring evaluation modes.
5. `.github/workflows/ci.yml`, `ruff.toml`, resolver/loader source and tests before any implementation.

The governance shape is grounded in the [public Converge protocol](https://github.com/microsoft/amplifier-bundle-converge/blob/41679679fd449ecc16b6af58d0ce8ec2cb2d29ad/docs/PROTOCOL.md), especially §§3.1–3.2 and 5. This project has not installed or declared the full manager/ledger/lane operation merely by creating drafts. Do not copy inaccessible/private governance text into public source.

## Request and interpretation

The requested outcome is repeatable evidence-driven routing: hard real-work-inspired or public tasks; light new-model screening that reuses valid prior results; exhaustive recalibration when task/model/role/runtime conditions change; private local evidence isolation; persistent agent guidance; and a strategy catalog for consumers without moving policy into their UI.

Catalog requirements: stable provider-oriented IDs with compatible aliases; bundle-owned labels/descriptions/notes/order/classification; versioned list/describe/assess sharing execution semantics without inference or writes; provider-only discovery ranked by compatibility; exact provider-module/account scope through aliases/fallbacks/overrides; required/optional-role coverage with unknown/stale/dynamic catalogs; source/revision/custom provenance; separately persisted identity and approved scope; unchanged saved meaning when policy updates. Acceptance includes multiple backends/accounts, general fallback without fake identity, dynamic/manual discovery, missing roles and later configuration changes.

This page is a labeled interpretation, not a verbatim quote or grant of further
implementation/publication authority. The bounded scope and distinct-ID Option A
were accepted for this slice; protected input is not reproduced in public documents.

## Delivered catalog scope

The first slice used [routing revision
183b453](https://github.com/microsoft/amplifier-bundle-routing-matrix/tree/183b453c5674fa9c4d51c24cd68e79bce34b28ea)
as its baseline. The following catalog scope was delivered in `f8bd250`; these
are source facts, not live adoption claims:

| Area | Current evidence | Consequence |
| --- | --- | --- |
| Strategies | Ten matrices; `routing/catalog.v1.json` describes ten canonical strategies and the `copilot` alias | Versioned descriptor API exists; custom alias equivalence remains source-qualified |
| Legacy OpenAI | README and `resolver.py` family alias prefer API then ChatGPT | Bare `openai` is not API-only; do not change silently |
| Composition/provenance | `matrix_loader.py` first custom-file hit wins; requested filename differs from declared name | Preview must share composition and show the actual winner/override lineage |
| Role resolution | Resolver capability, lifecycle and immutable catalog assessment reuse `resolve_model_role` | New-run roles use independent initial planning state; next-dispatch is unsupported |
| Pins/catalogs | `resolver.py` accepts exact strings without catalog membership | Configured selection is not availability/entitlement evidence |
| Preview effects | Catalog operations use pure snapshot providers and local state; runtime resolution still has provider catalogs/counters | Preparation is explicit; assessment does not call real providers or mutate live state |
| Availability | `docs/PROVIDER_AVAILABILITY.md` defines synchronous exact-instance checks and failure behavior | Availability is not consent or universal dispatch admission |
| Scope | Exact-module constraints are threaded through routed execution; catalog assessment filters exact approved binding revisions | Runtime account admission and universal containment remain unimplemented |
| Dynamic providers | Template wildcard and empty/error/manual catalogs have different meanings | Do not infer compatible discovery from an empty list or wildcard |

Core's provider discovery contract permits manual-entry/empty lists. Runtime integration inspection also found direct mounted-provider access, auxiliary provider.complete calls, explicit spawn preferences and foreign-runtime dispatch outside the routing hook. The provider:request hook currently handles a banner, not mandatory admission. Catalog source alone cannot qualify those paths.

No Azure-specific provider checkout/discovery contract was verified. Require an actual adapter/deployment snapshot before claiming support; preserve unknown rather than inventing a module or models.

## Review record for the expanded design

Both requested supplied-evidence, read-only reviews now support the revised method for explicit scoped planning. Neither inspected source files or independently verified the reported checks. Reviewer configuration and receipts belong in local project records, not public source. Main feedback and disposition:
- Separate scope-aware selection from enforcement; strict readiness must be false for partial admission coverage. Incorporated in RC6 and the specification tiers.
- Prefer distinct IDs over an ambiguous new meaning of bare `openai`. Both options were retained at design review; Option A was subsequently accepted for the bounded implementation.
- Shared composition/resolution was the first implementation prerequisite; it is now exercised by bounded snapshot/runtime parity checks. That evidence is not next-dispatch state or universal admission qualification.
- Public class fingerprints are weaker than private comparability. Private envelope mapping/IDs stay private; public release IDs are separate and reviewed.
- Failure seeds need hardness/role/grader calibration and rotating unseen families. Incorporated; no prescribed weak-model failure rate or claimed measured hardness.
- Do not create a recommendation contract/ledger before a real consumer exists. Recommendation semantics remain in the evaluation program; no extra formal seam created.
- Define reuse eligibility from preregistered assigned conditions, not identical call trees, tool choices, scores or success. Treatment-dependent behavior remains an outcome; all scheduled cells and missingness remain visible.
- State whether assessment predicts a new-run baseline or a revision-bound next dispatch. Mutable-state capture, parity and admission race handling are explicit qualification prerequisites.
- Clear privacy/rights separately from challenge/grader fitness, using a fresh fixture-author context that never saw private inputs. Keep private clearance receipts and require independent artifact review.

**The expanded-design review dependency is resolved.** Review support itself did
not authorize implementation, settle identity, clear fixtures or establish
runtime conformance. The later bounded implementation decision adopted distinct
IDs; it did not authorize a paid batch or prove remaining qualification gates:
accepted path ownership with independently observed request prevention;
state-sensitive preview/admission parity; privacy and role/grader acceptance;
and an adjacent two-cycle reuse demonstration. Review opinion is never steward
ratification or runtime proof.

## Evaluation starting point

The maintained routing [`evals/`](../evals/README.md) program implements offline plan/readiness/analyze through a reusable library and thin Click CLI. Relocation preserves the original 93 contract cases and adds bounded dependency/import/CLI regressions; the original independent task/grader schema checks covered five benchmark tasks. Routing owns evaluation configurations, scenarios, graders, reuse rules and promotion policy; generic execution bricks remain in the separate evaluation library as optional development dependencies. It has no live execution, telemetry normalization, privacy export, cost enforcement or recurring runner. The five existing rubrics include unqualified criteria. Preserve that honest boundary.

Every command requires an explicit local `--benchmark-root`; tests require `ROUTING_EVAL_BENCHMARK_ROOT` only for the two pinned-portfolio cases and fail actionably if absent. CI acquires the sample's pinned public task assets in an ignored development cache, with no evaluator runtime install, upstream-script execution, secrets or result uploads. Historical subject/source/task/grader locks are not rewritten to the new repository HEAD. Raw results remain outside source repositories.

Public synthetic proposals and benchmark pins are in EVALUATION-PROGRAM; no raw protected inputs or source maps belong here. Related mechanisms must not be counted as independent trials. Provisional seeds lack executed/live qualification; writing/creative/image-gen gaps remain. No current model is proven better by these proposals.

### Unmerged live instrumentation

As observed on 2026-10-06, [PR #82](https://github.com/microsoft/amplifier-bundle-routing-matrix/pull/82) at `cdaa9fd26121f1eaea42e1d723d869481f4ed009` proposes evaluation-only admission, request accounting and a restricted interval-union task. It is not included in the main revision above. Its miniature-bundle checks do not qualify a real Anchors or app-cli journey; the corrected paid campaign is not claimed. Inspect its current source and qualification limits before extending it instead of duplicating its transport machinery.

## Decisions and unresolved dependencies

| Decision | Recommendation | Why it matters |
| --- | --- | --- |
| Scope/binding and admission | Host binding authority plus mandatory portable dispatch/credential boundary; no child-launch-only enforcement claim | Caller consent must survive every supported execution path |
| First hard calibration families | Independently authored geometry, stateful handoff, non-vacuous proof, observation limits and quantitative/privacy tasks as role-appropriate | Real observed mistakes need reproducible graders and modern difficulty calibration |
| Reuse/promotion policy | Private comparability validation; public weak class; holdout confirmation and explicit workload/margins | Prevent stale evidence, privacy leakage and automatic ranking |
| Paid execution envelope | Decide output/retention, whole token/time/spend budget after instrumentation readiness and small calibration estimate | No paid recurrence or large batch is authorized by a draft |

No runtime owner has accepted an implementation item merely because an owner category is named. The host consumer's active project must be checked before overlapping its files.

## Implementation sequence after reviewed direction

1. Distinct-ID Option A and bounded scope planning are implemented; retain DRAFT until lock conditions are actually met and assign remaining runtime ownership.
2. Independently review/qualify the implemented descriptor and pure planning seam. Explicit preferences and next-dispatch prediction are refused, not implemented; source-qualified custom aliases need deliberate host handling.
3. Qualify portable admission with its owners across root/spawn/resume/nested/auxiliary/direct/foreign/provider-fallback paths and external credential channels. Unsupported paths remain unavailable under strict scope. Fixture peers first, then real integration.
4. Integrate a consumer through public descriptors (not private `_matrix_roles`) and exact revision/capability adoption. Same-schema UI/agent journey, custom shadowing, stale invalidation and legacy saved-selection cases must pass.
5. Independently implement isolated acquisition/telemetry/grading/export and reuse adapters once authorized. Clear abstract scenario handoffs and fresh-context fixture privacy/rights before challenge qualification; then instrumented baseline, paired calibration and an adjacent two-cycle reuse journey. Roles with no qualified baseline require deeper scenario calibration. Only then approve targeted screening or deeper recalibration and an evidence-backed preference PR.

Descriptor work, admission prerequisites and isolated evaluation research may proceed as separately owned slices once authorized; one cannot declare another delivered. No new umbrella service or full private-family checkout is needed.

## Verification gradient and honesty gates

Existing offline gates live in CI: root and module tests with real optional dependencies present, Ruff `0.15.11`, YAML/frontmatter structure. Documentation checks alone do not prove the new catalog/scope/reuse promises. For each proposed clause, add a discriminating good/bad pair and observe the actual boundary. Count selected tests; a skipped dependency or empty selection is not a result.

Before freezing the contract, require written spec, machine-checkable kit, passing real implementation, end-to-end worked example and steward decision. Do not manufacture a frozen ledger now. Before runtime merge, run isolated full-stack checks; before release/adoption claims, verify actual consumer/runtime versions. Before public source/artifact upload, apply privacy allowlists/scans and a fresh-context stranger review. No private provenance, config hashes or reviewer-resolution receipts enter public artifacts.

## Continuation record

The first slice adds routing-library source/tests, two exact-module profiles,
catalog metadata and implementation documentation. Evaluation, Core/Foundation,
providers, consumer configuration and shared installations are not changed.
The subsequent routing-owned relocation adds `evals/` and its separate offline
CI job; it leaves the historical evaluation-branch sources untouched.
Use the real-dependency pre-import test command in [catalog-api](catalog-api.md)
and CI's gates. Existing eight golden entries must not be bulk regenerated.

Independent verification of this slice: **858 routing tests**, including **107
catalog cases**, passed with actual Core/Foundation pre-imported in isolation;
Ruff **0.15.11** and structure checks passed. The existing evidence starter's
**93 tests** and the evaluation library's **26 tests** passed in the same isolated
environment. A parent-owned synthetic integration used native Rust Core,
actual session initialization/execute/cleanup and the routing entry point for
12 start/resume cases with 48 role-plan comparisons. API-only, ChatGPT-only,
legacy both-backend resolution, approved-account narrowing, rebound binding
rejection and custom canonical/alias separation were observed with zero
inference or network transport. Provider discovery there was fabricated only.

The routing-owned relocation was independently checked in a fresh isolated
environment: **104 evaluation tests** (93 retained plus 11 relocation cases) and
all **858 routing tests** passed together, **962 total with no skips**. Ruff
**0.15.11**, scoped formatting and bundle structure checks passed. The relocated
CLI ran from an unrelated working directory using explicit pinned benchmark
inputs; actual TaskSpec and GraderConfig loading matched all five task IDs,
timeouts and criterion bounds. The unchanged library/sample bytes and historical
locks were verified. `plan` exited 0, `readiness` exited 1 with execution
unsupported, and omission of `--benchmark-root` exited 2 before input reads.
No subject evaluation or model call was made. Independent relocation and
publication review found no material blocker.

Independent source/stranger review found three release blockers: custom
canonical/bundled-alias identity collapse, root CI's missing runtime dependencies,
and snapshot resolution reaching live logging handlers. Targeted regressions
failed before their fixes; follow-up review cleared the corrections. CI now
pre-imports real dependencies in the pytest process and catalog reporting is
isolated without changing runtime logging.

Remaining gates: consumer adoption and owner-qualified dispatch
prevention. No unit count or synthetic integration establishes account
containment or live model quality. Every operation reports
`not_enforced` and `execution_ready: false`; explicit preferences and
next-dispatch assessment are rejected. No new runtime binding/admission
capability or consumer persistence is supplied. Stop at the owned boundary
rather than asserting upstream enforcement or approval from this page.
