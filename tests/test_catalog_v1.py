"""Newly authored synthetic cases: no accounts, credentials or model transport."""

from __future__ import annotations

import copy
import json
import logging
import socket
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROUTING = ROOT / "routing"
sys.path.insert(0, str(ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing import mount  # noqa: E402
from amplifier_module_hooks_routing.catalog import (  # noqa: E402
    RoutingCatalogV1, prepare_catalog_sources,
)
from amplifier_module_hooks_routing.catalog_audit import audit_matrix_catalogs  # noqa: E402
from amplifier_module_hooks_routing.catalog_types import (  # noqa: E402
    ApprovedScope, AssessmentInputs, CatalogSnapshot, ProviderSnapshot, ScopeBinding,
    Selection, UnsupportedPredictionError, UnsupportedVersionError,
)
from amplifier_module_hooks_routing.knob_consistency import CallerContext, parse_preset  # noqa: E402
from amplifier_module_hooks_routing.matrix_loader import (  # noqa: E402
    compose_effective_matrix, load_matrix, provider_module_allowlist, resolve_matrix_source,
    validate_matrix_config,
)
from amplifier_module_hooks_routing.resolver import (  # noqa: E402
    NoScopedRouteError, _resolve_glob, resolve_model_role,
)
from amplifier_module_hooks_routing.resolver_class import MatrixModelRoleResolver  # noqa: E402


@pytest.fixture(autouse=True)
def no_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Catalog tests must never open transport")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def catalog():
    return RoutingCatalogV1(prepare_catalog_sources(ROUTING, source_revision="synthetic-source"))


def provider(module="provider-openai", instance="synthetic-a", **kwargs):
    return ProviderSnapshot(module, instance, "synthetic-binding-" + instance, "binding-v1",
                            availability="available", **kwargs)


def inventory(p, models=("gpt-6.1-sol", "gpt-6-luna"), **kwargs):
    return CatalogSnapshot(p.module, p.instance_id, p.binding_id, p.binding_revision,
                           "inventory-v1", models=models, **kwargs)


def inputs(providers=None, catalogs=None, approved=None, **kwargs):
    providers = tuple(providers or [provider(config_choices={"reasoning_effort": ["low", "medium", "high", "xhigh", "max"]})])
    catalogs = tuple(catalogs if catalogs is not None else [inventory(p, state="fresh_complete") for p in providers])
    approved = tuple(approved if approved is not None else [
        ScopeBinding(p.module, p.instance_id, p.binding_id, p.binding_revision) for p in providers
    ])
    return AssessmentInputs(providers, catalogs, ApprovedScope("approval-v1", approved),
                            "topology-v1", "catalog-v1", **{"required_roles": ("general",), **kwargs})


def role(report, name="general"):
    return next(r for r in report["roles"] if r["role"] == name)


def synthetic_policy(candidates=None, **kwargs):
    candidates = candidates or [{"provider": "openai", "model": "synthetic-model"}]
    return {"name": "synthetic-policy", "description": "Fabricated routing policy",
            "updated": "2026-10-02",
            "roles": {r: {"description": r, "candidates": copy.deepcopy(candidates)}
                      for r in ("general", "fast")}, **kwargs}


def custom_catalog(tmp_path, policy, stem="synthetic", **kwargs):
    (tmp_path / f"{stem}.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    return RoutingCatalogV1(prepare_catalog_sources(ROUTING, [tmp_path], **kwargs))


def runtime(providers, agents=None, capabilities=None, own_prefs=None):
    """Minimal lifecycle host; provider objects contain only fabricated fields."""
    caps = dict(capabilities or {})
    handlers = {}
    specs = [{"module": p.module, "instance_id": p.instance_id,
              "config": {"default_model": p.default_model, "priority": p.priority}}
             for p in providers]
    mounted = {
        p.instance_id: SimpleNamespace(
            config={"priority": p.priority, "default_model": p.default_model},
            list_models=AsyncMock(return_value=["gpt-6.1-sol", "gpt-6-luna", "synthetic-model"]),
            get_info=lambda: {"config_fields": []},
        ) for p in providers
    }
    bus = SimpleNamespace(
        register=lambda event, handler, **kw: handlers.__setitem__(event, handler),
        emit=AsyncMock(),
    )
    config = {"providers": specs, "agents": agents or {}}
    if own_prefs is not None:
        config["provider_preferences"] = own_prefs
    coord = SimpleNamespace(config=config, hooks=bus,
                            get=lambda key: mounted if key == "providers" else bus if key == "hooks" else None,
                            get_capability=caps.get,
                            register_capability=lambda key, value: caps.__setitem__(key, value))
    return coord, mounted, handlers, caps


@pytest.mark.parametrize("name,module", [
    ("openai-api", "provider-openai"), ("openai-chatgpt", "provider-openai-chatgpt"),
])
def test_additive_profiles_clone_policy_without_family_or_effort_changes(name, module):
    base = load_matrix(ROUTING / "openai.yaml")
    new = load_matrix(ROUTING / f"{name}.yaml")
    assert new["roles"] == base["roles"]
    assert new["preset"] == base["preset"]
    assert provider_module_allowlist(new) == (module,)
    assert "provider_module_allowlist" not in base


def test_catalog_has_ten_canonical_strategies_and_explicit_alias(catalog):
    descriptors = catalog.list()["strategies"]
    assert len(descriptors) == 10
    assert {d["matrix_id"] for d in descriptors} == {
        "balanced", "quality", "economy", "anthropic", "openai", "openai-api",
        "openai-chatgpt", "gemini", "github-copilot", "ollama",
    }
    canonical = catalog.describe(Selection("github-copilot"))
    alias = catalog.describe(Selection("copilot"))
    assert canonical["matrix_id"] == alias["matrix_id"] == "github-copilot"
    assert canonical["requested_id"] == "github-copilot"
    assert alias["requested_id"] == alias["declared_name"] == "copilot"
    assert canonical["source"]["source_stem"] == "copilot"
    assert canonical["aliases"] == ["copilot"]


@pytest.mark.parametrize("allowlist", [[], "", ["openai"], ["provider-*"], [None], ["provider-openai", "provider-openai"]])
def test_malformed_exact_constraints_rejected(tmp_path, allowlist):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(synthetic_policy(provider_module_allowlist=allowlist)))
    with pytest.raises(ValueError, match="allowlist"):
        load_matrix(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,expected", [("openai-api", "api-account"), ("openai-chatgpt", "openai")])
async def test_module_filter_precedes_misleading_keys_and_named_accounts(name, expected):
    data = load_matrix(ROUTING / f"{name}.yaml")
    coord, mounted, _, _ = runtime([
        provider("provider-openai-chatgpt", "openai", priority=-100),
        provider("provider-openai", "api-account", priority=5),
    ])
    resolved = await resolve_model_role(["general"], data["roles"], mounted, coordinator=coord,
                                        provider_module_allowlist=provider_module_allowlist(data))
    assert resolved[0]["provider"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("name,backend", [
    ("openai-api", "provider-openai-chatgpt"), ("openai-chatgpt", "provider-openai"),
])
async def test_excluded_default_cannot_hide_constrained_no_match(name, backend):
    data = load_matrix(ROUTING / f"{name}.yaml")
    coord, mounted, _, _ = runtime([provider(backend, "openai")])
    with pytest.raises(NoScopedRouteError):
        await resolve_model_role(["nonexistent", "general"], data["roles"], mounted, coordinator=coord,
                                 provider_module_allowlist=provider_module_allowlist(data))
    mounted["openai"].list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_mount_provenance_cannot_be_inferred_from_key():
    data = load_matrix(ROUTING / "openai-api.yaml")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["gpt-6-luna"]))
    with pytest.raises(NoScopedRouteError):
        await resolve_model_role(["fast"], data["roles"], {"provider-openai": fake},
                                 provider_module_allowlist=("provider-openai",))
    fake.list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_openai_alias_keeps_chatgpt_without_mount_metadata():
    data = load_matrix(ROUTING / "openai.yaml")
    result = await resolve_model_role(["general"], data["roles"], {"openai-chatgpt": object()})
    assert result[0]["provider"] == "openai-chatgpt"


@pytest.mark.asyncio
async def test_instance_id_beats_legacy_id_under_constraint():
    data = load_matrix(ROUTING / "openai-api.yaml")
    coord = SimpleNamespace(config={"providers": [
        {"module": "provider-openai", "id": "wrong-id", "instance_id": "actual-id", "config": {}},
    ]})
    result = await resolve_model_role(["general"], data["roles"], {"actual-id": object()}, coordinator=coord,
                                     provider_module_allowlist=("provider-openai",))
    assert result[0]["provider"] == "actual-id"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,allowed,excluded", [
    ("openai-api", "provider-openai", "provider-openai-chatgpt"),
    ("openai-chatgpt", "provider-openai-chatgpt", "provider-openai"),
])
async def test_strict_caller_substitution_cannot_escape_profile(name, allowed, excluded):
    data = load_matrix(ROUTING / f"{name}.yaml")
    coord, mounted, _, _ = runtime([provider(allowed, "allowed"), provider(excluded, "outside")])
    with pytest.raises(NoScopedRouteError):
        await resolve_model_role(["general"], data["roles"], mounted, coordinator=coord,
                                 caller_context=CallerContext("openai", "gpt-6-luna", "low", "outside"),
                                 preset=parse_preset(data),
                                 provider_module_allowlist=provider_module_allowlist(data))


@pytest.mark.asyncio
async def test_scope_filter_precedes_priority_default_model_and_account_intent(catalog):
    unapproved = provider(instance="preferred", priority=-100, default_model="gpt-6.1-sol")
    approved = provider(instance="approved", priority=50, config_choices={"reasoning_effort": ["high"]})
    approved_binding = ScopeBinding(approved.module, approved.instance_id, approved.binding_id, approved.binding_revision)
    report = await catalog.assess(Selection("openai-api"), inputs(
        [unapproved, approved], approved=[approved_binding],
    ))
    assert role(report)["selection"]["instance_id"] == "approved"
    assert report["scope_planning"] == "contained"
    assert report["compatibility"] == "verified"


@pytest.mark.asyncio
async def test_later_account_is_not_ambiently_approved(catalog):
    original = inputs()
    extra = provider(instance="new-account", priority=-500, default_model="gpt-6.1-sol")
    changed = replace(original, providers=original.providers + (extra,),
                      catalogs=original.catalogs + (inventory(extra, state="fresh_complete"),))
    a = await catalog.assess(Selection("openai-api"), original)
    b = await catalog.assess(Selection("openai-api"), changed)
    assert role(a)["selection"] == role(b)["selection"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("binding_id", "rebound"), ("binding_revision", "binding-v2"), ("module", "provider-openai-chatgpt"),
])
async def test_rebound_approval_is_known_blocked(catalog, field, value):
    original = inputs()
    changed_provider = replace(original.providers[0], **{field: value})
    changed = replace(original, providers=(changed_provider,),
                      catalogs=(inventory(changed_provider, state="fresh_complete"),))
    report = await catalog.assess(Selection("openai-api"), changed)
    assert report["scope_planning"] == "blocked"
    assert role(report)["selection"] is None
    assert role(report)["reasons"] == ["scope_binding_changed_or_missing"]


def test_duplicate_topology_scope_and_catalog_identities_rejected():
    p = provider()
    b = ScopeBinding(p.module, p.instance_id, p.binding_id, p.binding_revision)
    with pytest.raises(ValueError, match="Duplicate"):
        ApprovedScope("approval", (b, b))
    with pytest.raises(ValueError, match="Duplicate"):
        inputs([p, p])
    with pytest.raises(ValueError, match="Duplicate"):
        inputs([p], [inventory(p), inventory(p)])


def test_catalog_binding_mismatch_is_not_family_equivalence():
    p = provider()
    with pytest.raises(ValueError, match="correspondence"):
        inputs([p], [replace(inventory(p), binding_revision="other-revision")])


@pytest.mark.asyncio
@pytest.mark.parametrize("state,compatibility", [
    ("fresh_complete", "incompatible"), ("fresh_partial", "unknown"),
    ("stale", "unknown"), ("failed", "unknown"), ("built_in_fallback", "unknown"),
    ("manual", "unknown"), ("unknown", "unknown"),
])
async def test_exact_pin_preserved_but_catalog_evidence_not_invented(catalog, state, compatibility):
    p = provider(config_choices={"reasoning_effort": ["high"]})
    report = await catalog.assess(Selection("openai-api"), inputs([p], [inventory(p, models=(), state=state)]))
    assert role(report)["selection"]["model"] == "gpt-6.1-sol"
    assert report["compatibility"] == compatibility
    assert report["execution_ready"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("state,status,compatibility", [
    ("fresh_complete", "blocked", "incompatible"), ("fresh_partial", "unknown", "unknown"),
    ("stale", "unknown", "unknown"), ("failed", "unknown", "unknown"),
    ("manual", "unknown", "unknown"), ("built_in_fallback", "unknown", "unknown"),
])
async def test_authoritative_empty_glob_distinguished_from_uncertain_empty(catalog, state, status, compatibility):
    p = provider()
    report = await catalog.assess(Selection("openai-api"), inputs(
        [p], [inventory(p, models=(), state=state)], required_roles=("fast",),
    ))
    assert role(report, "fast")["status"] == status
    assert report["compatibility"] == compatibility


@pytest.mark.asyncio
async def test_stale_partial_inventory_can_select_tentatively(catalog):
    p = provider(config_choices={"reasoning_effort": ["medium"]})
    report = await catalog.assess(Selection("openai-api"), inputs(
        [p], [inventory(p, models=("gpt-6-luna",), state="stale")], required_roles=("fast",),
    ))
    assert role(report, "fast")["selection"]["model"] == "gpt-6-luna"
    assert report["compatibility"] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("state,availability,expected", [
    ("failed", "available", "unknown"), ("fresh_complete", "available", "verified"),
    ("fresh_complete", "unavailable", "unknown"),
])
async def test_preferred_glob_uncertainty_not_hidden_by_lower_pin(tmp_path, state, availability, expected):
    cat = custom_catalog(tmp_path, synthetic_policy([
        {"provider": "anthropic", "model": "synthetic-*"},
        {"provider": "openai", "model": "synthetic-model"},
    ]))
    first = replace(provider("provider-anthropic", "first"), availability=availability)
    second = provider(instance="second")
    report = await cat.assess(Selection("synthetic"), inputs(
        [first, second], [inventory(first, models=(), state=state),
                          inventory(second, models=("synthetic-model",), state="fresh_complete")],
    ))
    assert role(report)["selection"]["instance_id"] == "second"
    assert report["compatibility"] == expected
    assert ("preferred_candidate_uncertain" in role(report)["reasons"]) == (expected == "unknown")


@pytest.mark.asyncio
async def test_required_and_optional_missing_roles_are_returned(catalog):
    report = await catalog.assess(Selection("ollama"), inputs(
        required_roles=("general", "coding"), optional_roles=("writing",),
    ))
    assert [r["role"] for r in report["roles"]] == ["general", "coding", "writing"]
    assert role(report, "coding")["status"] == "missing"
    assert role(report, "writing")["required"] is False
    assert report["required_role_coverage"] == "incomplete"


@pytest.mark.asyncio
async def test_optional_gap_does_not_poison_required_compatibility(catalog):
    p = provider("provider-ollama")
    report = await catalog.assess(Selection("ollama"), inputs(
        [p], [inventory(p, models=("synthetic-10", "synthetic-9"), state="fresh_complete")],
        optional_roles=("image-gen",),
    ))
    assert role(report)["selection"]["model"] == "synthetic-10"  # Natural sorting.
    assert report["compatibility"] == "verified"
    assert role(report, "image-gen")["status"] == "missing"
    assert catalog.describe(Selection("ollama"))["kind"] == "template"


@pytest.mark.asyncio
async def test_native_image_generation_not_inferred_from_role_or_text_model(catalog):
    p = provider(config_choices={"reasoning_effort": ["high"]}, native_capabilities=["text"])
    report = await catalog.assess(Selection("openai-api"), inputs(
        [p], [inventory(p, state="fresh_complete", model_capabilities={"gpt-6.1-sol": ["text"]})],
        required_roles=("image-gen",),
    ))
    assert report["compatibility"] == "incompatible"
    assert "required_native_capability_unsupported" in role(report, "image-gen")["reasons"]


@pytest.mark.asyncio
async def test_required_capability_with_missing_metadata_is_unknown(catalog):
    report = await catalog.assess(Selection("openai-api"), inputs(
        required_roles=("general",), role_capability_needs={"general": ["tool-use"]},
    ))
    assert report["compatibility"] == "unknown"
    assert "required_native_capability_unknown" in role(report)["reasons"]


@pytest.mark.asyncio
async def test_manual_deployment_snapshot_cannot_prove_azure_compatibility(tmp_path):
    cat = custom_catalog(tmp_path, synthetic_policy([{"provider": "azure", "model": "synthetic-deployment"}]))
    p = provider("provider-azure", "azure")
    report = await cat.assess(Selection("synthetic"), inputs(
        [p], [inventory(p, models=("synthetic-deployment",), state="manual")],
    ))
    assert report["compatibility"] == "unknown"
    assert cat.describe(Selection("synthetic"))["provider_domain_complete"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("choices,expected", [(None, "unknown"), ({"reasoning_effort": ["low"]}, "incompatible")])
async def test_native_config_schema_missing_or_invalid_is_not_verified(catalog, choices, expected):
    p = provider(config_choices=choices)
    report = await catalog.assess(Selection("openai-api"), inputs([p]))
    assert report["compatibility"] == expected
    assert role(report)["native_config_evidence"] == expected


def test_explicit_preferences_rejected_instead_of_ignored():
    with pytest.raises(NotImplementedError, match="Explicit"):
        inputs(explicit_preferences={"general": [{"provider": "outside", "model": "outside"}]})


@pytest.mark.asyncio
async def test_next_dispatch_rejected_before_any_resolution(catalog, monkeypatch):
    monkeypatch.setattr(catalog, "describe", lambda *args: pytest.fail("must reject before describing"))
    with pytest.raises(UnsupportedPredictionError):
        await catalog.assess(Selection("openai-api"), inputs(), prediction_mode="next_dispatch")


@pytest.mark.parametrize("value", [0, 2, True, "1"])
def test_api_and_generation_validation_no_fallback(catalog, value):
    with pytest.raises(UnsupportedVersionError):
        RoutingCatalogV1(catalog.prepared, api_version=value)
    with pytest.raises(UnsupportedVersionError):
        Selection("openai", value)


@pytest.mark.parametrize("name", ["../openai", "/tmp/policy", "OpenAI", "", "openai.yaml"])
def test_selection_name_validation_prevents_path_lookup(name):
    with pytest.raises(ValueError):
        Selection(name)
    with pytest.raises(ValueError):
        resolve_matrix_source(name, (), ROUTING)


def test_unknown_selection_and_deleted_alias_do_not_fallback(catalog):
    for name in ("nonexistent", "openai-knob-consistent"):
        with pytest.raises(KeyError):
            catalog.describe(Selection(name))
    assert resolve_matrix_source("openai-knob-consistent", (), ROUTING).path is None


@pytest.mark.parametrize("change", ["schema", "generation", "duplicate", "cycle"])
def test_metadata_validation_rejects_unsupported_versions_and_alias_graphs(tmp_path, change):
    metadata = json.loads((ROUTING / "catalog.v1.json").read_text())
    if change == "schema":
        metadata["schema_version"] = 2
    elif change == "generation":
        metadata["strategies"][0]["semantic_generation"] = 2
    elif change == "duplicate":
        metadata["strategies"][0]["aliases"] = ["openai"]
    else:
        metadata["strategies"][0]["aliases"] = ["quality"]
        metadata["strategies"][1]["aliases"] = ["balanced"]
    (tmp_path / "catalog.v1.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        prepare_catalog_sources(tmp_path)


def test_custom_requested_stem_wins_before_mapped_stem_and_keeps_identity(tmp_path):
    custom_catalog(tmp_path, synthetic_policy(), stem="copilot")
    policy = synthetic_policy(name="declared-custom")
    cat = custom_catalog(tmp_path, policy, stem="github-copilot", custom_revisions={"github-copilot": "custom-v1"})
    requested = cat.describe(Selection("github-copilot"))
    alias = cat.describe(Selection("copilot"))
    assert requested["declared_name"] == "declared-custom"
    assert requested["source"]["source_stem"] == "github-copilot"
    assert requested["alias_equivalence"] == "unverified"
    assert alias["matrix_id"] == "copilot"
    assert alias["source_disposition"] == "source_qualified_custom"
    assert requested["policy_revision"] == "custom-v1"
    assert alias["policy_revision"] == "unknown"
    assert cat.list()["warnings"]


def test_custom_mapped_stem_does_not_get_bundle_equivalence(tmp_path):
    cat = custom_catalog(tmp_path, synthetic_policy(name="custom-copilot"), stem="copilot")
    described = cat.describe(Selection("github-copilot"))
    assert described["source"]["source_stem"] == "copilot"
    assert described["declared_name"] == "custom-copilot"
    assert described["alias_equivalence"] == "unverified"
    assert described["aliases"] == []


def test_malformed_winning_source_fails_not_bundle_fallback(tmp_path):
    (tmp_path / "openai.yaml").write_text("not-a-mapping")
    with pytest.raises(ValueError):
        prepare_catalog_sources(ROUTING, [tmp_path])


def test_deleted_alias_only_available_when_actual_custom_file_exists(tmp_path):
    cat = custom_catalog(tmp_path, synthetic_policy(), stem="openai-knob-consistent")
    description = cat.describe(Selection("openai-knob-consistent"))
    assert description["matrix_id"] == "openai-knob-consistent"
    assert description["canonical_id"] == "openai-knob-consistent"
    assert description["aliases"] == []


def test_unsupported_custom_metadata_warns_without_inventing_aliases(tmp_path):
    cat = custom_catalog(tmp_path, synthetic_policy(catalog={"aliases": ["invented"], "label": "Custom"}))
    assert "invented" not in {d["matrix_id"] for d in cat.list()["strategies"]}
    assert any("unsupported custom metadata" in warning for warning in cat.list()["warnings"])


def test_preparation_freezes_nested_inputs_and_detached_outputs(tmp_path):
    override = {"general": {"description": "custom", "candidates": [
        {"provider": "gemini", "model": "synthetic-model", "config": {
            "reasoning_effort": "high", "extra_request_params": {"thinking_config": {"thinking_level": "high"}},
        }},
    ]}}
    cat = custom_catalog(tmp_path, synthetic_policy(), config_overrides=override,
                         config_override_revision="opaque-override-v1")
    override["general"]["candidates"][0]["config"]["extra_request_params"]["thinking_config"]["thinking_level"] = "low"
    first = cat.describe(Selection("synthetic"))
    cfg = first["effective_policy"]["roles"]["general"]["candidates"][0]["config"]
    assert "reasoning_effort" not in cfg  # Same inert strip as mount.
    assert cfg["extra_request_params"]["thinking_config"]["thinking_level"] == "high"
    first["effective_policy"]["roles"].clear()
    assert cat.describe(Selection("synthetic"))["effective_policy"]["roles"]
    assert cat.describe(Selection("synthetic"))["source"]["override_chain"][0]["revision"] == "opaque-override-v1"
    with pytest.raises(TypeError):
        cat.prepared.entries["synthetic"]["matrix"]["roles"]["general"]["description"] = "mutated"


def test_snapshot_nested_choice_and_capability_data_is_immutable():
    choices = {"reasoning_effort": ["high"]}
    capabilities = {"gpt-6.1-sol": ["text"]}
    p = provider(config_choices=choices)
    snapshot = inventory(p, model_capabilities=capabilities)
    choices["reasoning_effort"].append("invalid")
    capabilities["gpt-6.1-sol"].append("image-generation")
    assert p.config_choices["reasoning_effort"] == ("high",)
    assert snapshot.model_capabilities["gpt-6.1-sol"] == ("text",)
    with pytest.raises(TypeError):
        p.config_choices["new"] = ()


@pytest.mark.asyncio
async def test_all_operations_inert_after_prepare(catalog, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No filesystem IO after preparation")
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    assert catalog.list()["strategies"]
    assert catalog.describe(Selection("openai-api"))["source"]["local_only"]
    report = await catalog.assess(Selection("openai-api"), inputs())
    discovery = await catalog.discover_provider_only("provider-openai", inputs())
    assert report["enforcement"]["status"] == discovery["enforcement"]["status"] == "not_enforced"
    assert not report["execution_ready"] and not discovery["execution_ready"]
    assert role(report)["selection"]["local_only"]


def test_live_provider_objects_and_enforcement_flags_cannot_enter_assessment():
    with pytest.raises(ValueError, match="snapshot"):
        inputs([SimpleNamespace(module="provider-openai")], catalogs=[], approved=[])
    with pytest.raises(TypeError):
        inputs(enforced=True)


@pytest.mark.asyncio
async def test_dedicated_verified_first_natural_vs_restricted_real_identity(catalog):
    result = await catalog.discover_provider_only("provider-openai", inputs())
    assert result["candidates"][0]["matrix_id"] == "openai-api"
    assert result["candidates"][0]["discovery_kind"] == "dedicated_profile"
    balanced = next(c for c in result["candidates"] if c["matrix_id"] == "balanced")
    legacy = next(c for c in result["candidates"] if c["matrix_id"] == "openai")
    assert balanced["discovery_kind"] == legacy["discovery_kind"] == "requires_provider_restriction"
    assert balanced["assessment"]["matrix_id"] == "balanced"
    p = provider("provider-ollama")
    dynamic = await catalog.discover_provider_only("provider-ollama", inputs(
        [p], [inventory(p, models=("synthetic-model",), state="fresh_complete")],
    ))
    assert dynamic["candidates"][0]["matrix_id"] == "ollama"
    assert dynamic["candidates"][0]["discovery_kind"] == "natural_provider_only"


@pytest.mark.asyncio
async def test_discovery_verified_alternative_outranks_unknown_dedicated(catalog, tmp_path):
    policy = load_matrix(ROUTING / "openai-api.yaml")
    policy["roles"]["general"]["candidates"][0]["config"] = {"unadvertised-knob": 1}
    cat = custom_catalog(tmp_path, policy, stem="openai-api")
    result = await cat.discover_provider_only("provider-openai", inputs())
    dedicated = next(c for c in result["candidates"] if c["matrix_id"] == "openai-api")
    assert dedicated["assessment"]["compatibility"] == "unknown"
    assert dedicated["discovery_kind"] != "dedicated_profile"
    assert result["candidates"][0]["assessment"]["compatibility"] == "verified"


@pytest.mark.asyncio
async def test_scope_exhaustion_discovery_does_not_approve_other_backend(catalog):
    result = await catalog.discover_provider_only("provider-openai-chatgpt", inputs())
    assert all(c["assessment"]["scope_planning"] == "blocked" for c in result["candidates"])
    assert not result["execution_ready"]


@pytest.mark.asyncio
async def test_repeated_assessment_has_independent_fresh_escalation_state(tmp_path):
    policy = synthetic_policy([{"provider": "openai", "model": "synthetic-high"}], preset={
        "tier_ladder": {"openai": ["synthetic-low", "synthetic-high"]},
        "delegation": {"inherit": "tier-and-effort", "escalate": {"allow_roles": ["general", "fast"], "max_uses": 1}},
    })
    cat = custom_catalog(tmp_path, policy)
    p = provider()
    data = inputs([p], [inventory(p, models=("synthetic-low", "synthetic-high"), state="fresh_complete")],
                  required_roles=("general", "fast"),
                  caller_context=CallerContext("openai", "synthetic-low"))
    a = await cat.assess(Selection("synthetic"), data)
    b = await cat.assess(Selection("synthetic"), data)
    assert a == b
    assert all(r["selection"]["model"] == "synthetic-high" for r in a["roles"])
    assert a["planning_state_mode"] == "independent_initial_resolution"


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["session:start", "session:resume"])
@pytest.mark.parametrize("name,expected", [("openai-api", "api"), ("openai-chatgpt", "subscription")])
async def test_mount_lifecycle_and_capability_and_assessment_share_constraints(catalog, event, name, expected):
    providers = [provider(instance="api"), provider("provider-openai-chatgpt", "subscription")]
    agents = {"synthetic-agent": {"model_role": "general", "provider_preferences": []}}
    coord, _, handlers, caps = runtime(providers, agents)
    await mount(coord, {"_bundle_root": str(ROOT), "default_matrix": name})
    await handlers[event](event, {})
    result = await caps["model_role_resolver"].resolve("general")
    report = await catalog.assess(Selection(name), inputs(providers))
    assert agents["synthetic-agent"]["provider_preferences"][0]["provider"] == expected
    assert result[0].provider == role(report)["selection"]["instance_id"] == expected
    assert result[0].model == role(report)["selection"]["model"]
    assert result[0].config == role(report)["selection"]["config"]


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["session:start", "session:resume"])
async def test_lifecycle_excluded_role_pin_fails_before_promotion(event):
    p = provider("provider-openai-chatgpt", "subscription")
    coord, mounted, handlers, _ = runtime([p], own_prefs=[{"provider": "subscription", "model": "gpt-6.1-sol"}])
    await mount(coord, {"_bundle_root": str(ROOT), "default_matrix": "openai-api"})
    before = copy.deepcopy(mounted["subscription"].config)
    with pytest.raises(NoScopedRouteError):
        await handlers[event](event, {})
    assert mounted["subscription"].config == before


@pytest.mark.asyncio
async def test_override_order_disable_preset_and_inert_strip_parity(tmp_path):
    config = {"general": {"description": "config", "candidates": [{"provider": "gemini", "model": "synthetic-model", "config": {"reasoning_effort": "high"}}]}}
    capability = {"general": {"description": "capability", "candidates": ["base", {"provider": "openai", "model": "gpt-6.1-sol"}]}}
    cat = RoutingCatalogV1(prepare_catalog_sources(ROUTING, config_overrides=config,
                                                  capability_overrides=capability,
                                                  disable_delegation_preset=True))
    coord, _, _, caps = runtime([provider("provider-gemini", "gemini")],
                                capabilities={"session.routing": {"overrides": capability}})
    await mount(coord, {"_bundle_root": str(ROOT), "default_matrix": "openai", "overrides": config,
                       "disable_delegation_preset": True})
    resolved = await caps["model_role_resolver"].resolve("general")
    snapshot = provider("provider-gemini", "gemini")
    report = await cat.assess(Selection("openai"), inputs(
        [snapshot], [inventory(snapshot, models=("synthetic-model",), state="fresh_complete")],
    ))
    assert resolved[0].provider == role(report)["selection"]["instance_id"] == "gemini"
    assert resolved[0].config == role(report)["selection"]["config"] == {}
    assert cat.describe(Selection("openai"))["effective_policy"]["roles"]["general"]["description"] == "capability"
    composed, preset, diagnostics = compose_effective_matrix(load_matrix(ROUTING / "openai.yaml"), config, capability, True)
    assert composed == cat.describe(Selection("openai"))["effective_policy"]
    assert preset is None and diagnostics


def test_catalog_audit_respects_backend_constraint():
    api = load_matrix(ROUTING / "openai-api.yaml")
    subscription = load_matrix(ROUTING / "openai-chatgpt.yaml")
    catalogs = {"openai": {"status": "ok", "models": [
        {"id": "gpt-6.1-sol", "capabilities": ["vision"]},
        {"id": "gpt-6-luna", "capabilities": ["vision"]},
    ]}}
    only_subscription = audit_matrix_catalogs({"openai-chatgpt": subscription}, catalogs)
    assert only_subscription["checked_candidates"] == 0
    both = audit_matrix_catalogs({"openai-api": api, "openai-chatgpt": subscription}, catalogs)
    assert both["checked_candidates"] == 13


@pytest.mark.asyncio
async def test_direct_resolver_parity_inherited_caller_without_mutating_live_state(catalog):
    p = provider(default_model="gpt-6-luna", config_choices={"reasoning_effort": ["medium"]})
    coord, mounted, _, _ = runtime([p])
    policy = load_matrix(ROUTING / "openai-api.yaml")
    resolver = MatrixModelRoleResolver(policy["roles"], mounted, "openai-api", coordinator=coord,
                                      preset=parse_preset(policy),
                                      provider_module_allowlist=("provider-openai",))
    caller = CallerContext("openai", "gpt-6-luna", "medium", p.instance_id)
    actual = await resolver.resolve("general", caller_context=caller)
    before = (resolver._escalations.used, list(resolver.clamp_records),
              copy.deepcopy(resolver._preresolved_models))
    data = inputs([p], caller_context=caller)
    preview = await catalog.assess(Selection("openai-api"), data)
    repeat = await catalog.assess(Selection("openai-api"), data)
    assert actual[0].provider == role(preview)["selection"]["instance_id"]
    assert actual[0].model == role(preview)["selection"]["model"] == "gpt-6-luna"
    assert actual[0].config == role(preview)["selection"]["config"] == {"reasoning_effort": "medium"}
    assert preview == repeat
    assert (resolver._escalations.used, resolver.clamp_records, resolver._preresolved_models) == before


@pytest.mark.asyncio
async def test_role_override_cannot_drop_profile_constraint(catalog):
    override = {"general": {"description": "outside", "candidates": [
        {"provider": "outside", "model": "synthetic-model"},
    ]}}
    cat = RoutingCatalogV1(prepare_catalog_sources(ROUTING, config_overrides=override))
    allowed = provider(instance="allowed")
    outside = provider("provider-openai-chatgpt", "outside")
    report = await cat.assess(Selection("openai-api"), inputs([allowed, outside]))
    assert role(report)["status"] == "blocked"
    assert cat.describe(Selection("openai-api"))["provider_module_allowlist"] == ["provider-openai"]
    coord, _, _, caps = runtime([allowed, outside])
    await mount(coord, {"_bundle_root": str(ROOT), "default_matrix": "openai-api", "overrides": override})
    with pytest.raises(NoScopedRouteError):
        await caps["model_role_resolver"].resolve("general")


@pytest.mark.asyncio
async def test_config_choice_validation_uses_same_constrained_instance_as_selection(catalog):
    api = provider(instance="api", config_choices={"reasoning_effort": ["high"]})
    subscription = provider("provider-openai-chatgpt", "openai", config_choices={"reasoning_effort": ["low"]})
    coord, mounted, _, _ = runtime([subscription, api])
    def info(choices):
        return {"config_fields": [{"id": "reasoning_effort", "field_type": "choice", "choices": choices}]}
    mounted["api"].get_info = lambda: info(["high"])
    mounted["openai"].get_info = lambda: info(["low"])
    matrix = load_matrix(ROUTING / "openai-api.yaml")
    general_only = {"roles": {"general": matrix["roles"]["general"]}}
    assert validate_matrix_config(general_only, mounted, coord, ("provider-openai",)) == []
    assert validate_matrix_config(general_only, mounted, coord, ("provider-openai-chatgpt",))
    report = await catalog.assess(Selection("openai-api"), inputs([subscription, api]))
    assert role(report)["native_config_evidence"] == "verified"
    # Mount's existing preset-bearing rule still raises for an invalid choice.
    mounted["api"].get_info = lambda: info(["low"])
    with pytest.raises(ValueError, match="Invalid config"):
        await mount(coord, {"_bundle_root": str(ROOT), "default_matrix": "openai-api"})


@pytest.mark.asyncio
async def test_executable_canonical_copilot_source_alias_mounts(catalog):
    p = provider("provider-github-copilot", "copilot-account")
    coord, _, _, caps = runtime([p])
    await mount(coord, {"_bundle_root": str(ROOT), "default_matrix": "github-copilot"})
    prefs = await caps["model_role_resolver"].resolve("general")
    assert prefs[0].provider == "copilot-account"
    assert caps["model_role_resolver"].matrix_path.endswith("/copilot.yaml")


@pytest.mark.asyncio
async def test_natural_discovery_does_not_claim_safe_caller_inheritance(tmp_path):
    policy = synthetic_policy([{"provider": "anthropic", "model": "synthetic-model"}], preset={
        "tier_ladder": {"anthropic": ["synthetic-model"]},
        "delegation": {"inherit": "strict"},
    })
    cat = custom_catalog(tmp_path, policy)
    p = provider("provider-anthropic", "anthropic")
    discovered = await cat.discover_provider_only("provider-anthropic", inputs(
        [p], [inventory(p, models=("synthetic-model",), state="fresh_complete")],
    ))
    custom = next(c for c in discovered["candidates"] if c["matrix_id"] == "synthetic")
    assert custom["discovery_kind"] == "requires_provider_restriction"


def test_documented_synthetic_api_example_runs(monkeypatch, capsys):
    example = (ROOT / "docs" / "catalog-api.md").read_text().split("## Runnable pure synthetic example", 1)[1]
    code = example.split("```python\n", 1)[1].split("```", 1)[0]
    monkeypatch.chdir(ROOT)
    exec(compile(code, "catalog-api-example", "exec"), {})
    assert capsys.readouterr().out == "openai-api verified False\nopenai-api\n"


def test_caller_snapshot_rejects_mutable_fields():
    with pytest.raises(ValueError):
        inputs(caller_context=CallerContext("openai", ["mutable-model"]))


@pytest.mark.asyncio
async def test_final_module_provenance_revalidated_after_glob_resolution():
    data = load_matrix(ROUTING / "openai-api.yaml")
    p = provider(instance="changing")
    coord, mounted, _, _ = runtime([p])
    async def changed_during_catalog_read():
        coord.config["providers"][0]["module"] = "provider-openai-chatgpt"
        return ["gpt-6-luna"]
    mounted["changing"].list_models = changed_during_catalog_read
    with pytest.raises(NoScopedRouteError, match="provenance changed"):
        await resolve_model_role(["fast"], data["roles"], mounted, coordinator=coord,
                                 provider_module_allowlist=("provider-openai",))


def test_describe_discloses_disabled_preset():
    cat = RoutingCatalogV1(prepare_catalog_sources(ROUTING, disable_delegation_preset=True))
    assert cat.describe(Selection("openai-api"))["delegation_preset_disabled"] is True


@pytest.mark.asyncio
async def test_known_unavailable_without_fallback_is_blocked_not_unknown(catalog):
    p = replace(provider(), availability="unavailable")
    report = await catalog.assess(Selection("openai-api"), inputs([p]))
    assert role(report)["status"] == "blocked"
    assert role(report)["reasons"] == ["provider_unavailable"]
    assert report["compatibility"] == "incompatible"


@pytest.mark.asyncio
async def test_native_adapter_negative_evidence_not_softened_by_stale_catalog(catalog):
    p = provider(config_choices={"reasoning_effort": ["high"]}, native_capabilities=("text",))
    report = await catalog.assess(Selection("openai-api"), inputs(
        [p], [inventory(p, state="stale", model_capabilities={"gpt-6.1-sol": ["image-generation"]})],
        required_roles=("image-gen",),
    ))
    assert report["compatibility"] == "incompatible"
    assert "required_native_capability_unsupported" in role(report, "image-gen")["reasons"]


def test_custom_canonical_with_bundled_alias_keeps_both_winning_sources(tmp_path):
    cat = custom_catalog(tmp_path, synthetic_policy(name="custom-openai"), stem="github-copilot")
    canonical = cat.describe(Selection("github-copilot"))
    alias = cat.describe(Selection("copilot"))
    assert canonical["matrix_id"] == "github-copilot"
    assert canonical["effective_policy"]["roles"]["general"]["candidates"][0]["provider"] == "openai"
    assert alias["matrix_id"] == "copilot"
    assert alias["effective_policy"]["roles"]["general"]["candidates"][0]["provider"] == "github-copilot"
    assert canonical["canonical_id"] == alias["canonical_id"] == "github-copilot"
    assert canonical["source_disposition"] == "source_qualified_custom"
    assert alias["source_disposition"] == "bundle_policy"
    assert canonical["aliases"] == alias["aliases"] == []
    assert canonical["alias_equivalence"] == alias["alias_equivalence"] == "unverified"
    listed = {item["matrix_id"]: item for item in cat.list()["strategies"]}
    assert len(listed) == 11
    assert listed["github-copilot"]["requested_id"] == "github-copilot"
    assert listed["copilot"]["requested_id"] == "copilot"


@pytest.mark.asyncio
async def test_custom_canonical_with_bundled_alias_discovery_retains_both(tmp_path):
    cat = custom_catalog(tmp_path, synthetic_policy(name="custom-openai"), stem="github-copilot")
    p = provider("provider-github-copilot", "synthetic-copilot")
    discovered = await cat.discover_provider_only("provider-github-copilot", inputs(
        [p], [inventory(p, models=("claude-sonnet-5.5",), state="fresh_complete")],
    ))
    candidates = {item["matrix_id"]: item for item in discovered["candidates"]}
    assert len(candidates) == 11
    assert {"github-copilot", "copilot"}.issubset(candidates)
    assert candidates["github-copilot"]["assessment"]["matrix_id"] == "github-copilot"
    assert candidates["copilot"]["assessment"]["matrix_id"] == "copilot"
    assert candidates["copilot"]["assessment"]["roles"][0]["selection"]["instance_id"] == p.instance_id
    assert candidates["github-copilot"]["assessment"]["roles"][0]["selection"] is None
    assert candidates["github-copilot"]["descriptor"]["aliases"] == []
    assert candidates["copilot"]["descriptor"]["aliases"] == []


def test_ci_root_matrix_requires_real_runtime_in_same_pytest_process():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    job = workflow["jobs"]["test-root"]
    assert job["strategy"]["matrix"]["python-version"] == ["3.11", "3.12", "3.13"]
    command = next(step["run"] for step in job["steps"] if step.get("name") == "Run root tests")
    assert "--with git+https://github.com/microsoft/amplifier-foundation" in command
    assert "import amplifier_core" in command
    assert "amplifier_core.models" in command
    assert "amplifier_foundation.spawn_utils" in command
    assert "pytest.main(['tests', '-q', '--tb=short'])" in command
    assert command.index("import amplifier_core") < command.index("pytest.main")
    assert "importorskip" not in command


def test_ci_module_tests_preimport_core_before_fixture_stub():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    command = next(step["run"] for step in workflow["jobs"]["test-modules"]["steps"]
                   if step.get("name") == "Run module tests")
    assert "import amplifier_core" in command
    assert "amplifier_foundation.spawn_utils" in command
    assert "pytest.main(['-q', '--tb=short'])" in command
    assert command.index("import amplifier_core") < command.index("pytest.main")


class _ReportingSpy(logging.Handler):
    def __init__(self, raising=False):
        super().__init__()
        self.records = []
        self.raising = raising

    def emit(self, record):
        self.records.append(record)
        if self.raising:
            raise AssertionError("Snapshot planning reached an external logging handler")


def _model_intent_providers():
    choices = {"reasoning_effort": ["low", "medium", "high", "xhigh", "max"]}
    return [
        provider(instance="synthetic-luna", priority=0, default_model="gpt-6-luna", config_choices=choices),
        provider(instance="synthetic-sol", priority=10, default_model="gpt-6.1-sol", config_choices=choices),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["assess", "discover"])
@pytest.mark.parametrize("raising", [False, True])
async def test_snapshot_model_intent_never_reaches_external_log_handler(catalog, caplog, operation, raising):
    logger = logging.getLogger("amplifier_module_hooks_routing.resolver")
    caplog.set_level(logging.INFO, logger=logger.name)
    spy = _ReportingSpy(raising)
    logger.addHandler(spy)
    try:
        data = inputs(_model_intent_providers())
        if operation == "assess":
            report = await catalog.assess(Selection("openai-api"), data)
        else:
            discovered = await catalog.discover_provider_only("provider-openai", data)
            report = next(c["assessment"] for c in discovered["candidates"] if c["matrix_id"] == "openai-api")
        assert role(report)["selection"]["instance_id"] == "synthetic-sol"
        assert spy.records == []
    finally:
        logger.removeHandler(spy)


@pytest.mark.asyncio
async def test_runtime_model_intent_preserves_default_reporting(caplog):
    logger = logging.getLogger("amplifier_module_hooks_routing.resolver")
    caplog.set_level(logging.INFO, logger=logger.name)
    spy = _ReportingSpy()
    logger.addHandler(spy)
    try:
        coord, mounted, _, _ = runtime(_model_intent_providers())
        data = load_matrix(ROUTING / "openai-api.yaml")
        resolved = await resolve_model_role(["general"], data["roles"], mounted,
                                            coordinator=coord, provider_module_allowlist=("provider-openai",))
        assert resolved[0]["provider"] == "synthetic-sol"
        assert len(spy.records) == 1
        assert "resolved by model intent" in spy.records[0].getMessage()
        assert "synthetic-sol" in spy.records[0].getMessage()
        assert "synthetic-luna" in spy.records[0].getMessage()
    finally:
        logger.removeHandler(spy)


@pytest.mark.asyncio
async def test_injected_silent_reporting_preserves_glob_failure_semantics(caplog):
    failed = SimpleNamespace(list_models=AsyncMock(side_effect=ValueError("synthetic failure")))
    caplog.set_level(logging.INFO, logger="amplifier_module_hooks_routing.resolver")
    assert await _resolve_glob("*", failed, report_logs=False) is None
    assert caplog.records == []
    with pytest.raises(ValueError, match="synthetic failure"):
        await _resolve_glob("*", failed, propagate_failure=True, report_logs=False)
    assert caplog.records == []
    assert await _resolve_glob("*", failed) is None
    assert any("Failed to list models" in record.getMessage() for record in caplog.records)