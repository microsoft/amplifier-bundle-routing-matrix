# Catalog and assessment — proposed v1 specification

**DRAFT, partially implemented; not frozen or dispatch-qualified.** This elaborates [RC1–RC8](../contracts/routing-catalog.v1.md). The bounded library API and its exact implemented shapes are documented in [catalog-api](catalog-api.md). [HANDOFF](HANDOFF.md) records independent planning/composed-session evidence and remaining qualification. Examples on this specification page remain illustrative; they are not a second executable schema. Existing host commands and resolver capability names are unchanged.

## 1. Identity and display

A descriptor identifies an effective matrix strategy, not a root-chat model and not a billing account. Its identity invariants include provider-domain meaning, required/default role policy and scope semantics. Model preferences, effort preferences and candidate ordering may evolve under those invariants; breaking them requires explicit adoption/migration.

```json
{
  "schema_version": 1,
  "matrix_id": "balanced",
  "semantic_generation": 1,
  "requested_id": "balanced",
  "aliases": [],
  "label": "Balanced",
  "description": "Quality and resource tradeoffs for mixed agent workloads.",
  "strategy_note": "Use the approved provider connections only.",
  "display_order": 10,
  "kind": "shared",
  "declared_provider_modules": ["provider-openai", "provider-anthropic", "provider-gemini"],
  "policy_revision": "fixture-policy-revision"
}
```

This shortened synthetic descriptor is not a complete shipped balanced inventory. `list` returns descriptors from a prepared immutable source snapshot, with warnings for unsupported/custom metadata. Presentation order is separate from candidate order, provider priority and bundle composition order. Classification follows effective module semantics, not filename. Templates are labeled as templates even when a host has a useful catalog.

Aliases are explicit, acyclic, unambiguous and bundle-owned. Preserve requested and canonical lineage. A general fallback keeps `matrix_id: balanced`; do not render or persist it as a synthetic provider-profile alias.

### Existing-ID migration decision

Current `openai` is **API-first across OpenAI API and ChatGPT subscription backends**. It is not an exact API-only strategy. `copilot` can gain a same-meaning `github-copilot` canonical ID with a preserved alias; a new exact `openai-chatgpt` profile is additive. Provider suffix alignment is preferred but cannot override compatibility.

| Option | Proposed behavior | Consequence |
| --- | --- | --- |
| A — accepted for the bounded slice | Preserve legacy `openai`; introduce distinct `openai-api` and `openai-chatgpt` IDs. | No bare-ID reinterpretation; API-only ID is a documented suffix-alignment exception. Both additive policies clone legacy roles/preset and constrain exact module selection. |
| B — stronger suffix alignment | New records use `(openai, semantic_generation)` for API-only; missing generation means legacy API+ChatGPT. Every old consumer and storage format gets an explicit migration. | Identity is the pair, not the bare string; all new records require generation, and mixed versions must refuse ambiguous interpretation. |

**Option A is accepted for implementation of this slice.** This is an identity decision, not contract freezing or permission to merge. Legacy `openai.yaml` and the eight old golden entries remain unchanged. Exact profiles are module-selection constraints, not account consent or universal containment. `github-copilot` maps to unchanged `copilot.yaml`; custom filename/declared-name differences retain source-qualified dispositions rather than automatic equivalence. The deleted `openai-knob-consistent` name is not resurrected: it works only if an actual custom file exists.

### Bounded implementation disposition

Implemented: twelve public descriptors plus explicit Copilot lineage; immutable
explicit-source preparation; shared effective composition and runtime role
resolution using snapshot providers; exact approved-binding filtering; evidence
states and required/optional role reports; ranked provider-only discovery.
Assessment is `new_run` / `model_role_resolution` /
`independent_initial_resolution`. It reports only scope-aware **planning**.
Every operation remains `not_enforced`, `execution_ready: false`.

Explicit-preference assessment raises `NotImplementedError` rather than ignoring
input. `next_dispatch` raises `UnsupportedPredictionError` before planning.
The source-qualified custom identity surface is deliberately narrower than
universal alias equivalence. Host capability application, live-state capture,
mandatory portable admission/revision fencing, consumer persistence/adoption and
principal attestation remain gaps. The normative contract/vision remain DRAFT;
unit parity is not full-stack or dispatch qualification.

### Current strategy choices (2026-10-06)

The mixed strategies are `quality`, `speed`, `economy` and `balanced`. Names
describe objectives: successful-task quality/critical defects, time to successful
completion subject to quality floors, resource cost per successful task, and a
tradeoff across those quantities. They are not measured optimum claims.
`speed` is explicitly provisional; its dials and qualification limits are in
[MATRIX_CURATOR_GUIDE](MATRIX_CURATOR_GUIDE.md#strategy-objectives-and-provisional-speed-policy).
No `good`, `cheap` or `fast` compatibility aliases were added. The existing
`copilot` alias is unrelated and retained.

`custom-template` is a generic starter with only `general` and `fast`, both
using `replace-me-provider-instance` and `model: "*"`. Its effective descriptor
is `kind: template`, with an unknown provider domain, not an invented universal
`local`/`vllm` provider. Copy to a new filename, change `name`, replace both
provider fields with actual configured instance IDs and pin served models.
Untouched placeholders do not match ordinary configured mounts; assessment
reports uncovered required routes, never execution readiness. A wildcard alone
does not prove compatibility; a customized policy needs instance-bound evidence.

`ollama` remains separately listed and executable under its original saved ID
and Ollama-only policy. No visibility filter or identity rewrite was introduced.
All choices retain custom-file precedence and requested-filename lineage;
malformed winners still fail rather than selecting bundled policy.

## 2. Proposed operation boundary

| Operation | Inputs | Output / effects |
| --- | --- | --- |
| `list` | API version + prepared source snapshot | Descriptors and schema/capability metadata; no model discovery or installation. |
| `describe` | Exact selection identity + source snapshot | Descriptor, effective role/candidate policy, identity invariants, source/revision/override chain. |
| `assess` | Selection, immutable topology/catalog snapshots, exact scope, required/optional roles, explicit caller/root intent, isolated planning state | Resolved plan, evidence states, explanations and readiness. No inference or writes. |
| `discover_provider_only` | Exact provider/connection scope and the same assessment inputs | Ranked actual strategy IDs with dedicated/natural/restriction-required labels. |

Catalog refresh is a separate explicit host metadata operation. These operations never look up ambient secrets, silently fetch provider catalogs, activate a bundle, install dependencies, change settings, or consume live escalation state. Missing snapshot entries mean **unknown**, not permission to call `list_models()`.

The implementation must factor/reuse effective matrix composition, override precedence, sanitization, alias/instance matching and caller intent from production resolution. Production and assessment use the same planning core with explicit snapshots/state. Do not approximate runtime by scanning YAML or invoke the live mutable resolver. A fresh planning state may describe escalation effects; only admitted execution consumes them. Repeated assessment must leave live counters/sinks/cache/settings unchanged.

### What a preview predicts

Assessment declares its prediction mode. `new_run` describes the baseline for a new run with explicitly initialized planning state. It must not imply the next call of an already-running session. A future `next_dispatch` assessment requires a read-only, revision-bound snapshot of every applicable mutable input, including escalation allowance and caller state; unsupported capture of that state means next-dispatch prediction is unavailable.

Equal-input parity includes that planning-state snapshot. Fresh and exhausted escalation allowances may correctly produce different routes even when matrix/catalog/scope match. Admission revalidates all applicable revisions before dispatch; a changed counter, binding or caller condition requires reassessment. The admitted state revision must remain applicable through target selection and dispatch, using an owner-qualified revision fence or equivalent serialization; a race is refused or reassessed, not warned past. Assessment neither reserves nor consumes allowance. Preview can describe possible transitions, but cannot guarantee an entire future trajectory whose state changes after each call.

## 3. Snapshot and scope inputs

```json
{
  "schema_version": 1,
  "selection": {"matrix_id": "balanced", "semantic_generation": 1},
  "source_revision": "fixture-source-revision",
  "topology_revision": "fixture-topology-revision",
  "catalog_revision": "fixture-catalog-revision",
  "required_roles": ["general", "coding"],
  "optional_roles": ["image-gen"],
  "approved_scope": {
    "approval_revision": "fixture-approval",
    "allowed": [
      {"module": "provider-openai", "instance_id": "fixture-a", "binding_id": "fixture-binding-a"}
    ]
  },
  "caller_intent": {"model": "fixture-model", "native_config": {"reasoning_effort": "high"}}
}
```

Callers explicitly declare required roles or accept a named, returned bundle default-role policy. Never assume a template's two roles cover every agent in a composed runtime. Return every required/optional role disposition. Native effort semantics and root versus child selection remain distinct.

The host supplies module identity, runtime mount identity, availability and connection binding. Provider public IDs/families are not exact module/account consent. Binding handles are opaque local references, generation-sensitive and non-secret; they are **not** hashes of credentials, endpoint or account names. Principal assurance is separately `attested`, `host_connection_bound` or `unknown`; a host-bound handle is not a verified billing principal.

A token refresh preserving the same verified binding need not widen scope. Changed principal/endpoint or rebinding under the same instance ID invalidates the prior approval until the host reconciles it. Additional accounts are not automatically allowed. Child/resumed scope is a non-widening intersection, never copied from the current ambient provider list.

Apply scope before provider-family alias expansion and instance priority/model preference; validate all final targets after overrides, explicit preferences, inherited intent and fallback. A denied high-priority account must not hide a valid permitted account. Scope exhaustion cannot fall through to an excluded default. Model pins preserve intent within scope; they do not add connection consent.

## 4. Evidence and readiness are separate

```json
{
  "schema_version": 1,
  "matrix_id": "balanced",
  "source_revision": "fixture-source-revision",
  "discovery_kind": "requires_provider_restriction",
  "resolution_status": "resolved",
  "required_role_coverage": "complete",
  "catalog_confidence": "verified",
  "scope_planning": "contained",
  "enforcement": {"status": "not_enforced", "unsupported_paths": ["fixture-direct-dispatch"]},
  "execution_ready": false,
  "explanations": ["Planning is contained; strict dispatch coverage is not qualified."]
}
```

The example deliberately refuses execution despite a verified contained plan. Compatible policy/catalog evidence alone is not enforcement readiness. Define closed enums and per-role reason codes in the executable schema before implementation; these draft examples do not establish an exported schema.

Catalog snapshots distinguish fresh complete, fresh partial, stale, failed/unavailable, built-in fallback, manual and unknown evidence. Each is tied to the actual connection binding and observation/revision, not a provider-family cache. Fresh complete empty can establish no models; a failed or manual-entry empty list cannot. Authoritative fresh missing exact pins are incompatible; exact pin acceptance without evidence remains unverified. Context/capability claims require appropriate evidence; entitlement may still fail at delivery.

Dynamic Ollama needs its installed model inventory and supported capabilities. Azure-style deployments need the actual provider/deployment adapter and connection-bound discovery or explicitly reviewed manual evidence; no Azure implementation was verified during grounding. Neither endpoint appearance nor `*` establishes support. Unknown required-role evidence cannot become verified compatibility through a score or fallback catalog.

## 5. Discovery ranking

Evaluate the exact dedicated profile first, if one exists. If it is incompatible or unknown, assess other provider profiles and general strategies with the same required roles, scope and snapshots; preserve every relevant explanation. Rank verified compatibility/readiness before policy preference and display ordering. Unknown candidates remain inspectable but never outrank a verified ready candidate as though evidence were equal.

Labels:
- `dedicated_profile`: explicit exact-module profile, verified under the requested bindings and role requirements.
- `natural_provider_only`: unfiltered effective planning already uses only the requested exact domain; not merely a filename claim.
- `requires_provider_restriction`: general policy needs approved filtering/admission to stay in the requested domain.

Assessment can propose restriction-required alternatives, but strict execution remains unavailable without complete qualified admission. The host preserves the actual matrix ID and approved scope; it does not manufacture aliases or implicit approvals.

## 6. Execution integration dependency

**Tier A: scope-aware planning** is a routing-bundle responsibility. **Tier B: actual containment** requires a mandatory runtime/credential admission boundary. The current hook alone does not deliver Tier B. A strict host must disclose `not_enforced` and refuse ready execution whenever coverage is partial or unknown. Before qualification, each supported call path needs a named owner who has accepted its enforcement boundary; a proposed owner category is not an accepted handoff.

Qualification must cover root request overrides, child and nested delegation, resume, auxiliary naming/compaction, direct mounted-provider calls, supported foreign-runtime paths, and provider-internal model/backend fallback. Resolvers and spawners cannot enlarge approved scope. A hook deny protects only dispatchers that emit and honor it; exception logging is not fail-closed admission.

Containment tests must observe prevention before the outbound request or credential/egress grant. A denied call must produce zero unauthorized transport requests, not merely a warning or post-call audit record. Provider-internal fallback must reach the same prevention boundary before using its secondary target; inaccessible switches remain unsupported under strict scope.

Planning must supply an accepted path-ownership and observation map. The categories below are candidate responsibilities, **not accepted assignments**:

| Path class | Candidate responsibility | Qualification evidence still needed |
| --- | --- | --- |
| Scoped planning | Bundle planner owner | Effective composition, state-sensitive parity and exact binding filters |
| Root, direct and auxiliary model dispatch | Native runtime and provider-dispatch owners | Prevention boundary and independently observed transport/credential denial |
| Child, nested creation and resume | Host/session construction and spawn owners | Non-widening propagation plus final dispatch verification |
| Provider-internal target fallback | Provider adapter and dispatch owners | Every secondary target checked before any outbound attempt |
| Foreign runtime, subprocess and external model tool | Runtime/tool host and credential/egress owners | Equivalent prevention or explicit unsupported-path refusal |

Until the relevant owner accepts each path, it is unassigned. Negative fixtures need a transport recorder/proxy or independently observed egress boundary outside the subject's self-report; control real-network paths where applicable. Never send real unauthorized requests to demonstrate a denial.

Credential-bearing external tools/subprocesses are separate authority domains. Under a promised restriction, paths capable of independent model calls must be blocked or prove equivalent connection/egress containment. A Core admission primitive alone does not prove containment of unrestricted external API tools. The mechanism and ownership handoff are prerequisites, not asserted implementations in this bundle.

## 7. Saved selections and updates

Persist identity/semantic generation plus scope approval separately, retaining requested alias and effective source/revision/override lineage. Private source paths and binding handles stay local. A run pins its prepared source, scope and catalog inputs. Resume/new-run reassessment follows an explicit adoption boundary; updates do not mutate a running call.

Same-meaning preference improvements may be adopted within existing approved bindings. A changed provider domain, reinterpreted role policy, rebinding, added account, custom override or incompatible semantic generation invalidates readiness. Legacy missing scope remains disclosed legacy behavior, never inferred universal approval. Hosts must not silently normalize it into new strict consent.

## Acceptance cases

Planned discriminating observations, **not executed tests**:

| Case | Pass observation | Matched failure |
| --- | --- | --- |
| API-only | Every planned/admitted target is exact API module and approved binding | Family alias admits ChatGPT |
| ChatGPT-only | Dedicated compatible profile; no API credential required or used | API-first fallback escapes scope |
| Both configured | Explicit allowset governs; disposition reflects actual modules | Connected means implicitly approved |
| Two accounts same module | Only approved binding eligible, even if lower priority | High-priority excluded account selected |
| No dedicated profile | Qualifying general strategy returned under its real ID and accurate label | Host invents provider-profile alias |
| Dynamic providers | Inventory/deployment evidence proves required roles; template stays labeled | Wildcard or failed empty catalog reported compatible |
| Missing roles | Required gap blocks; optional gap explained | Unknown role inherits default and disappears |
| Source/custom override | Same winner and override lineage in preview/execution | Preview uses shipped matrix while custom file executes |
| Stale/partial/manual catalog | Uncertainty retained and strict readiness denied | Exact string or fallback catalog treated authoritative |
| Alias/explicit preference/caller fallback | Scope applies before matching and after final preference | One path bypasses restriction |
| Later account or principal change | Approval unchanged or invalidated; no ambient widening | Same display ID authorizes new principal |
| Equal snapshots | Same effective plans including planning state; repeated preview consumes no live state | Resolver counters/sinks/caches change, or fresh-state preview is called a live next-call guarantee |
| Input changed after preview | Counter/caller/binding revision revalidated; reassessment before execution | Old compatible badge authorizes a changed next-dispatch plan |
| Unsupported direct/auxiliary/foreign/tool path | Strict readiness false or call refused with zero unauthorized transport requests | Planner containment or post-call detection presented as enforcement |
| Provider-internal fallback | Final target is checked and retains actual model/backend | Initial approval licenses an unseen secondary target |
| Legacy selection | Old ID retains meaning; migration explicit | New suffix preference changes old saved strategy |

## Open decisions

The OpenAI distinct-ID decision is accepted for this bounded implementation.
Qualify exact binding/admission semantics with runtime owners, review the bounded
snapshot/response surface, select supported host/runtime capability versions and
independently verify consumer adoption. Remaining planned acceptance rows above
are not automatically satisfied by the library tests. No upstream owner has
accepted a work item merely because it is named here.
