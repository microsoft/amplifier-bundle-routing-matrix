# Catalog API v1 — bounded implementation

This is the implemented library surface, not a frozen contract or universal
execution admission mechanism. It predicts **model-role resolution**, not root
chat selection, a future dispatch, billing entitlement or task quality.
All operation outputs use `schema_version: 1`, `enforcement.status: not_enforced`
and `execution_ready: false`. Binding handles and source paths are **local-only
data, not public export artifacts**.

## Operations and preparation

Import from `amplifier_module_hooks_routing.catalog`:

```python
prepared = prepare_catalog_sources(
    bundle_routing_dir,                 # explicit public bundle routing directory
    custom_routing_dirs=(),              # explicit local directories only
    config_overrides=None,               # role mappings, same shape as mount
    capability_overrides=None,           # composed after config overrides
    disable_delegation_preset=False,
    source_revision="unknown",           # opaque caller-supplied revision
    custom_revisions=None,               # requested ID -> opaque revision
    config_override_revision="unknown",
    capability_override_revision="unknown",
)
catalog = RoutingCatalogV1(prepared, api_version=1)
catalog.list()
catalog.describe(Selection("openai-api", semantic_generation=1))
await catalog.assess(selection, inputs, prediction_mode="new_run")
await catalog.discover_provider_only("provider-openai", inputs)
```

Preparation is the **only filesystem operation**. It reads `catalog.v1.json`
and winning YAML policies from supplied directories. It never reads ambient
HOME, configuration stores, credentials or caches. First requested-filename
hit wins across custom directories then bundle; `github-copilot` subsequently
tries the mapped `copilot` stem. Malformed winning sources fail; there is no
silent recovery or version/generation downgrade.

The shared `compose_effective_matrix` helper performs config overrides, then
capability overrides, base-preset parsing/disable/validation and inert-key
stripping for both mount and catalog. Overrides are role policy, not a way to
replace top-level module constraints. Provider choice validation at mount keeps
its existing warning/error semantics. Assessment uses snapshot choice metadata
and reports incompatible or unknown evidence instead of invoking a provider.

The returned preparation object recursively freezes copied mappings and
sequences. Operation results are detached dictionaries. Refresh is an explicit
new preparation/snapshot operation by the host; these operations never refresh
provider inventories. Do not hash private inputs: only winning **public bundle
policy files** receive SHA-256 revisions. Custom policy and override revisions
are opaque supplied tokens or `unknown`; override contents are never hashed.
`bundle_routing_dir` identifies public policy, not a private custom directory.
Persist the full source/override lineage locally, not just the public base hash.

## Exact input shapes

Public types are frozen dataclasses in `catalog_types`. Keyword construction is
recommended. Collections accept tuples or lists at construction and become
immutable; maps become recursively read-only.

| Type | Fields |
| --- | --- |
| `Selection` | `matrix_id: str`; `semantic_generation: int = 1` |
| `ScopeBinding` | exact `module: str`, `instance_id: str`, `binding_id: str`, `binding_revision: str` |
| `ApprovedScope` | `approval_revision: str`; `allowed: tuple[ScopeBinding, ...] = ()` |
| `ProviderSnapshot` | binding fields above; `priority: int = 0`; `default_model: str = ""`; `availability = "unknown"`; `principal_assurance = "unknown"`; `config_choices: mapping[str, tuple[str, ...]] \| None = None`; `native_capabilities: tuple[str, ...] \| None = None`; `compatibility_config: mapping = {}` |
| `CatalogSnapshot` | binding fields above; `revision: str`; `state = "unknown"`; `models: tuple[str, ...] = ()`; `model_capabilities: mapping[model_id, tuple[str, ...]] \| None = None` |
| `AssessmentInputs` | `providers`, `catalogs`, `approved_scope`, `topology_revision: str`, `catalog_revision: str`, **nonempty** `required_roles`; `optional_roles = ()`; `caller_context = None`; `explicit_preferences = None`; `role_capability_needs = {}` |

`caller_context`, if supplied, is the existing frozen
`knob_consistency.CallerContext(family, model, effort=None, provider_key="")`.
Family is the ladder family; provider key is an actual mounted-instance handle,
not permission to approve it. Caller fields must be scalar strings. Providers
and catalogs are snapshots **only**, never actual provider/coordinator objects.
No credentials, endpoints, mount arguments, arbitrary provider options or
enforcement claims belong in these inputs. `config_choices` is safe choice
metadata, not configured account values.

`compatibility_config` is a narrow optional snapshot of inherited effort/thinking
knobs for concrete Haiku checks, **not the account mount config**. Its allowlist is
`effort`, `reasoning_effort`, `thinking_budget_tokens`, `thinking_budget`,
`budget_tokens`, `thinking`, `thinking_mode`, `thinking_type`, `between_tools`.
Nested `thinking` accepts only `type`, `mode`, `budget_tokens`; extra keys refuse.
Values are copied/frozen and no default is synthesized. Supply the same relevant
inherited knobs that runtime will clone; omission describes no supplied knobs,
not proof about a live mount. Never copy credentials or arbitrary account options.

Both preparation (exact known policy targets) and assessment (actual resolved
target/mounted module) can raise `HaikuCompatibilityError`. Its `code`, `model`,
and `key` match runtime refusal; it is not converted to a fallback route. Globs
and arbitrary instance policy IDs defer validation to concrete resolution.
Assessment never disables global logging or calls a provider transport.

Enums:

- Availability: `available`, `unavailable`, `unknown`.
- Principal assurance: `attested`, `host_connection_bound`, `unknown`.
  These are **host assertions**; the library does not attest a billing principal.
- Catalog evidence: `fresh_complete`, `fresh_partial`, `stale`, `failed`,
  `built_in_fallback`, `manual`, `unknown`.
- Role disposition: `selected`, `blocked`, `missing`, `unknown`.
- Compatibility/native-config evidence: `verified`, `incompatible`, `unknown`;
  required coverage: `complete`, `incomplete`, `unknown`;
  scope planning: `contained`, `blocked`, `unknown`.

Duplicate instance identities and catalog/provider binding mismatches raise
`ValueError`. An approved binding absent or rebound in the supplied topology
blocks assessment; additional unapproved accounts are ineligible. Empty approval
is not ambient consent. Scope filtering occurs before aliases, default-model
intent and priority; final selections retain exact module/instance/binding and
revision, with `local_only: true`.

Non-`None` `explicit_preferences` raises `NotImplementedError`: v1 does not
pretend to predict host/spawner explicit-preference paths. `next_dispatch` and
every non-`new_run` prediction raise `UnsupportedPredictionError` **before
resolution**. Unsupported API versions and semantic generations raise
`UnsupportedVersionError`. Unknown IDs raise `KeyError`; names must be safe
file stems, never paths.

## Report interpretation

`list()` returns `strategies`, source revision, warnings and supported prediction
modes. There are ten canonical public strategies. `github-copilot` retains the
bundle-owned `copilot` alias and unchanged policy file. Custom winners receive
`source_qualified_custom` disposition and unverified alias equivalence; their
requested and declared identities are not silently normalized. Custom metadata
may provide a string `catalog.label` and `catalog.strategy_note`; unsupported
fields produce warnings, never invented aliases.

Canonical/alias entries collapse only when every winning source is the same
bundle-owned public policy. A custom `github-copilot.yaml` alongside bundled
`copilot.yaml` withdraws alias equivalence in both directions: list, describe
and discovery retain distinct `github-copilot` and `copilot` IDs, with empty
alias lists and separate source lineage.

`describe()` adds `effective_policy`, identity invariants and `source` with
winning/shadowed paths, requested/canonical/declared IDs, source stem and ordered
override revisions. Classification follows effective candidate alias domains,
not filename. Unknown instance-domain policy remains unknown; templates remain
templates even with useful inventory. `delegation_preset_disabled` records the
explicit opt-out; the base preset is retained in `effective_policy` for lineage,
but is not applied to resolution when this flag is true.

`assess()` returns every required/optional role, its selection/evidence/reasons,
separate required compatibility/coverage and scope planning, and revision
provenance. Exact pins remain the runtime's selected pins even when absent
from fresh-complete catalogs; the plan is then **incompatible**, not silently
rewritten to a fallback. Fresh-complete empty inventories are authoritative.
Partial/stale inventories may select tentatively; failed/manual/unknown empty
inventories cannot verify a glob. Lower fallback does not erase a preferred
candidate's catalog/availability uncertainty. Missing config-choice schemas
retain unknown effective native-config evidence.

Required capabilities must be supported by model and native adapter evidence.
`vision` implicitly needs `vision`; `image-gen` implicitly needs
`image-generation`. A text-model role named image-gen does not prove native
image generation. Unknown metadata cannot establish capability support.
Optional gaps remain inspectable without invalidating required compatibility.
Coverage records role planning/evidence, not entitlement or dispatch admission.

Assessment reuses `resolve_model_role` against pure snapshot providers and
synthetic mount specs. Each role gets its **own initial** escalation allowance.
Repeated assessments do not mutate a live resolver, sink or cache. Reports say
`prediction_subject: model_role_resolution` and
`planning_state_mode: independent_initial_resolution`: this is not a prediction
of one future multi-role trajectory or an exhausted running session.

Provider-only discovery intersects the existing approval with the exact
requested module. It ranks verified before unknown before incompatible, then
exact dedicated profiles, natural policy domains and restriction-required
policies in stable display order. `dedicated_profile` requires a verified exact
module constraint; `natural_provider_only` requires the **policy** to admit only
that module without unsafe caller inheritance, not merely one configured
provider. Other candidates are `requires_provider_restriction`. All candidates
retain actual strategy IDs, descriptors, assessments and reasons.

## Runnable pure synthetic example

From the repository root, using an environment with the routing module or
`PYTHONPATH=modules/hooks-routing`, run the following. All models, connections,
bindings and revisions below are fabricated. Preparation reads public policy;
assessment/discovery perform no I/O or model calls.

```python
import asyncio
from pathlib import Path
from amplifier_module_hooks_routing.catalog import RoutingCatalogV1, prepare_catalog_sources
from amplifier_module_hooks_routing.catalog_types import (
    ApprovedScope, AssessmentInputs, CatalogSnapshot, ProviderSnapshot,
    ScopeBinding, Selection,
)

async def main():
    catalog = RoutingCatalogV1(prepare_catalog_sources(
        Path("routing"), source_revision="synthetic-public-policy-v1",
    ))
    provider = ProviderSnapshot(
        module="provider-openai", instance_id="synthetic-api",
        binding_id="synthetic-binding", binding_revision="binding-v1",
        availability="available", principal_assurance="host_connection_bound",
        config_choices={"reasoning_effort": ("low", "medium", "high", "xhigh", "max")},
    )
    inventory = CatalogSnapshot(
        module=provider.module, instance_id=provider.instance_id,
        binding_id=provider.binding_id, binding_revision=provider.binding_revision,
        revision="inventory-v1", state="fresh_complete",
        models=("gpt-6.1-sol", "gpt-6-luna"),  # Hypothetical membership, not a live claim.
    )
    inputs = AssessmentInputs(
        providers=(provider,), catalogs=(inventory,),
        approved_scope=ApprovedScope("approval-v1", (
            ScopeBinding(provider.module, provider.instance_id,
                         provider.binding_id, provider.binding_revision),
        )),
        topology_revision="topology-v1", catalog_revision="catalog-v1",
        required_roles=("general", "fast"), optional_roles=("image-gen",),
    )
    report = await catalog.assess(Selection("openai-api"), inputs)
    discovery = await catalog.discover_provider_only("provider-openai", inputs)
    assert report["compatibility"] == "verified"
    assert report["scope_planning"] == "contained"
    assert report["enforcement"]["status"] == "not_enforced"
    assert report["execution_ready"] is False
    print(report["matrix_id"], report["compatibility"], report["execution_ready"])
    print(discovery["candidates"][0]["matrix_id"])  # openai-api, never a fake balanced alias.

asyncio.run(main())
```

## Maintainer checks and outstanding boundaries

Run with installed real Core/Foundation dependencies; pre-import Core so module
test fixtures cannot install a stand-in:

```bash
PYTHONPATH=modules/hooks-routing python -c "import amplifier_core, amplifier_foundation.spawn_utils, pytest; raise SystemExit(pytest.main(['tests', 'modules/hooks-routing/tests', '-q', '--tb=short']))"
python .github/scripts/check_bundle_structure.py
# CI's pinned Ruff version is 0.15.11; do not install a different rule set silently.
ruff check .
```

`tests/test_catalog_v1.py` covers pure operations, source/custom alias lineage,
versions, immutability, scope exclusions, snapshot evidence, discovery labels and
mount/resolver/lifecycle parity. The later Haiku compatibility update changes
seven native selections and removes six unqualified Copilot budgets; only the
economy vision budget entry changes in the original fixed-roster golden file.
Model catalog audit honors exact profiles: an API-only
catalog check does not claim ChatGPT-profile coverage.

Independent isolation verification and source/privacy review are recorded in
[HANDOFF](HANDOFF.md). The composed smoke used real Core sessions and synthetic
transport boundaries; it did not call models or attest billing containment.
Keep those release gates distinct from unit results. Mandatory
portable dispatch/credential admission, revision fencing, root/direct/auxiliary/
foreign/provider-internal fallback containment, principal attestation, consumer
persistence/adoption and provider-specific dynamic/deployment discovery adapters
remain unimplemented here. No paid benchmarks, model quality claim or public
export pipeline is supplied.