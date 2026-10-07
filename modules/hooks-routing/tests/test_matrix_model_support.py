"""Concrete Haiku compatibility; fabricated config/catalogs, no transport."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from amplifier_module_hooks_routing.haiku_compatibility import (
    HAIKU_45,
    HAIKU_55,
    HAIKU_55_EFFORTS,
    HaikuCompatibilityError,
    haiku_config_errors,
)
from amplifier_module_hooks_routing.knob_consistency import (
    CallerContext,
    EscalationState,
    Preset,
)
from amplifier_module_hooks_routing.matrix_loader import (
    compose_effective_matrix,
    strip_inert_config,
    validate_matrix_inert_config,
)
from amplifier_module_hooks_routing.resolver import NoScopedRouteError, resolve_model_role

ROOT = Path(__file__).resolve().parents[3]


def matrix(model, config=None, provider="anthropic"):
    return {
        "roles": {
            role: {
                "description": role,
                "candidates": [
                    {"provider": provider, "model": model, "config": config or {}},
                ],
            }
            for role in ("general", "fast")
        }
    }


def host(module="provider-anthropic", instance="synthetic-native", config=None, models=None):
    specs = [{"module": module, "instance_id": instance, "config": config or {}}]
    coord = SimpleNamespace(config={"providers": specs}, get_capability=lambda _: None)
    mounted = {instance: SimpleNamespace(list_models=AsyncMock(return_value=models or [HAIKU_55]))}
    return coord, mounted


@pytest.mark.parametrize("effort", HAIKU_55_EFFORTS)
@pytest.mark.parametrize("key", ("reasoning_effort", "effort"))
def test_native_55_preserves_all_five_efforts(effort, key):
    policy = matrix(HAIKU_55, {key: effort, "temperature": 1.0})
    before = deepcopy(policy)
    assert validate_matrix_inert_config(policy) == []
    effective, _, errors = compose_effective_matrix(policy)
    assert effective == before and policy == before and errors == []


@pytest.mark.parametrize("model", HAIKU_45)
@pytest.mark.parametrize("effort", HAIKU_55_EFFORTS)
@pytest.mark.parametrize("key", ("reasoning_effort", "effort"))
def test_45_effort_is_refused_not_removed(model, effort, key):
    policy = matrix(model, {key: effort})
    before = deepcopy(policy)
    errors = validate_matrix_inert_config(policy)
    assert len(errors) == 2
    assert all("candidate 0" in e and key in e and "haiku_effort_unsupported" in e for e in errors)
    assert ("4096" if effort == "low" else "32000") in errors[0]
    with pytest.raises(HaikuCompatibilityError, match="haiku_effort_unsupported"):
        strip_inert_config(policy)
    assert policy == before


@pytest.mark.parametrize(
    "config",
    [
        {"thinking_budget_tokens": 32000},
        {"thinking_budget": 32000},
        {"thinking": {"type": "enabled", "budget_tokens": 32000}},
        {"thinking": {"type": "between_tools"}},
        {"thinking_mode": "between_tools"},
        {"between_tools": True},
        {"budget_tokens": 32000},
    ],
)
def test_native_55_manual_thinking_refused_at_loader(config):
    with pytest.raises(HaikuCompatibilityError, match="haiku_manual_thinking_forbidden"):
        compose_effective_matrix(matrix(HAIKU_55, config))


@pytest.mark.parametrize(
    "model", ["claude-haiku-6-1", "claude-haiku-latest", "claude-haiku-5-5-new"]
)
@pytest.mark.parametrize(
    "config", [{"reasoning_effort": "high"}, {"thinking_budget_tokens": 32000}]
)
def test_unknown_ids_fail_named_not_future_support(model, config):
    with pytest.raises(HaikuCompatibilityError, match="haiku_compatibility_unknown"):
        compose_effective_matrix(matrix(model, config))


@pytest.mark.parametrize("model", HAIKU_45)
def test_native_45_manual_budget_passes_unchanged(model):
    policy = matrix(model, {"thinking_budget_tokens": 32000})
    cleaned, errors = strip_inert_config(policy)
    assert cleaned is policy and errors == []


def test_glob_is_not_a_compatibility_claim():
    policy = matrix("claude-haiku-*", {"reasoning_effort": "max"})
    effective, _, errors = compose_effective_matrix(policy)
    assert effective == policy and errors == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,code",
    [
        (HAIKU_55, None),
        (HAIKU_45[0], "haiku_effort_unsupported"),
        ("claude-haiku-6-1", "haiku_compatibility_unknown"),
    ],
)
async def test_glob_checks_actual_concrete_model_no_fallback(model, code):
    policy = matrix("claude-haiku-*", {"reasoning_effort": "max"})
    policy["roles"]["fast"]["candidates"].append({"provider": "anthropic", "model": HAIKU_45[0]})
    coord, mounted = host(models=[model])
    kwargs = dict(coordinator=coord, provider_module_allowlist=("provider-anthropic",))
    if code:
        with pytest.raises(HaikuCompatibilityError, match=code):
            await resolve_model_role(["fast", "general"], policy["roles"], mounted, **kwargs)
    else:
        selected = await resolve_model_role(["fast"], policy["roles"], mounted, **kwargs)
        assert selected == [
            {"provider": "synthetic-native", "model": model, "config": {"reasoning_effort": "max"}}
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"thinking_budget_tokens": 32000},
        {"thinking": {"type": "enabled", "budget_tokens": 32000}},
    ],
)
async def test_postresolution_guard_checks_inherited_mount_budget(config):
    coord, mounted = host(config=config)
    with pytest.raises(HaikuCompatibilityError, match="haiku_manual_thinking_forbidden"):
        await resolve_model_role(
            ["fast"], matrix("claude-haiku-*")["roles"], mounted, coordinator=coord
        )
    assert coord.config["providers"][0]["config"] == config


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", [*HAIKU_55_EFFORTS, None])
@pytest.mark.parametrize("mode", ["effort", "strict", "tier-and-effort"])
async def test_caller_effort_and_exact_instance_survive_clamping(effort, mode):
    coord, mounted = host()
    preset = Preset(
        inherit=mode,
        tier_ladder={
            "anthropic": [
                ["claude-haiku-*"],
                ["claude-sonnet-*"],
            ]
        },
    )
    caller = CallerContext("anthropic", HAIKU_55, effort, "synthetic-native")
    target = HAIKU_55 if mode == "effort" else "claude-sonnet-5-5"
    records = []

    async def record(value):
        records.append(value)

    selected = await resolve_model_role(
        ["fast"],
        matrix(target)["roles"],
        mounted,
        coordinator=coord,
        caller_context=caller,
        preset=preset,
        escalations=EscalationState(1),
        on_clamp=record,
        provider_module_allowlist=("provider-anthropic",),
    )
    assert selected[0]["model"] == HAIKU_55
    assert selected[0]["provider"] == "synthetic-native"
    assert selected[0]["config"] == ({} if effort is None else {"reasoning_effort": effort})
    assert records[0].granted_model == HAIKU_55 and records[0].granted_effort == effort
    assert records[0].honored


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", ["default", "none", "minimal", "HIGH"])
async def test_explicit_default_is_not_unset(effort):
    coord, mounted = host()
    with pytest.raises(HaikuCompatibilityError, match="haiku_effort_invalid"):
        await resolve_model_role(
            ["fast"],
            matrix(HAIKU_55, {"reasoning_effort": effort})["roles"],
            mounted,
            coordinator=coord,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,model",
    [
        ("provider-github-copilot", HAIKU_55),
        ("provider-github-copilot", "claude-haiku-5.5"),
        ("provider-openai", HAIKU_55),
        ("provider-provider-anthropic", HAIKU_55),
        ("anthropic", HAIKU_55),
    ],
)
async def test_misleading_anthropic_instance_key_cannot_claim_native_protocol(module, model):
    coord, mounted = host(module, "anthropic")
    with pytest.raises(HaikuCompatibilityError, match="haiku_compatibility_unknown"):
        await resolve_model_role(
            ["fast"],
            matrix(model, {"reasoning_effort": "max"})["roles"],
            mounted,
            coordinator=coord,
        )


@pytest.mark.asyncio
async def test_unknown_provenance_not_inferred_from_key_and_scope_still_exhausts():
    coord, mounted = host()
    with pytest.raises(NoScopedRouteError):
        await resolve_model_role(
            ["fast"],
            matrix(HAIKU_55)["roles"],
            mounted,
            coordinator=coord,
            provider_module_allowlist=("provider-openai",),
        )
    with pytest.raises(HaikuCompatibilityError, match="haiku_compatibility_unknown"):
        await resolve_model_role(
            ["fast"], matrix(HAIKU_55, {"effort": "high"}, "synthetic-native")["roles"], mounted
        )


def test_no_haiku_rule_applies_to_other_models_or_empty_configs():
    for model in ("claude-sonnet-*", "claude-opus-5", "gpt-6.1-sol", None, ""):
        assert haiku_config_errors("anthropic", model, {"reasoning_effort": "xhigh"}) == []
    assert haiku_config_errors(None, "claude-haiku-latest", {}) == []


@pytest.mark.asyncio
async def test_effective_knobs_match_real_foundation_clone_and_explicit_clear():
    from amplifier_foundation.spawn_utils import ProviderPreference, apply_provider_preferences

    original = {"default_model": HAIKU_45[0], "priority": 5, "thinking_budget_tokens": 32000}
    overrides = {"thinking_budget_tokens": None, "reasoning_effort": "high"}
    coord, mounted = host(config=original)
    selected = await resolve_model_role(
        ["fast"],
        matrix(HAIKU_55, overrides)["roles"],
        mounted,
        coordinator=coord,
    )
    before = deepcopy(coord.config)
    child = apply_provider_preferences(coord.config, [ProviderPreference(**selected[0])])
    child_config = child["providers"][0]["config"]
    assert child_config == {**original, **overrides, "default_model": HAIKU_55, "priority": 0}
    assert haiku_config_errors("anthropic", HAIKU_55, child_config) == []
    assert coord.config == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,code",
    [
        ("provider-anthropic", None),
        ("provider-gemini", "haiku_compatibility_unknown"),
    ],
)
@pytest.mark.parametrize("pattern", ["claude-haiku-*", "claude-*", "*"])
async def test_haiku_glob_on_gemini_named_instance_preserves_intent(module, code, pattern):
    policy = matrix(pattern, {"reasoning_effort": "high"}, provider="gemini")
    effective, _, errors = compose_effective_matrix(policy)
    assert effective == policy and errors == []
    coord, mounted = host(module, "gemini", models=[HAIKU_55])
    if code:
        with pytest.raises(HaikuCompatibilityError, match=code):
            await resolve_model_role(["fast"], effective["roles"], mounted, coordinator=coord)
    else:
        selected = await resolve_model_role(
            ["fast"], effective["roles"], mounted, coordinator=coord
        )
        assert selected[0]["config"] == {"reasoning_effort": "high"}


@pytest.mark.asyncio
async def test_compatibility_does_not_claim_off_ladder_caller_was_honored():
    coord, mounted = host()
    records = []

    async def record(value):
        records.append(value)

    preset = Preset(inherit="strict", tier_ladder={"anthropic": [["claude-haiku-*"]]})
    await resolve_model_role(
        ["fast"],
        matrix(HAIKU_55)["roles"],
        mounted,
        coordinator=coord,
        preset=preset,
        caller_context=CallerContext("anthropic", "claude-sonnet-5-5", "high"),
        on_clamp=record,
    )
    assert records[0].honored is False and records[0].granted_effort is None
    assert "no ceiling could be derived" in records[0].reason


@pytest.mark.parametrize("path", sorted((ROOT / "routing").glob("*.yaml")), ids=lambda p: p.name)
def test_shipped_haiku_candidates_are_backend_qualified(path):
    policy = yaml.safe_load(path.read_text())
    assert validate_matrix_inert_config(policy) == []
    for data in policy["roles"].values():
        for candidate in data["candidates"]:
            model = candidate["model"]
            if "haiku" not in model:
                continue
            config = candidate.get("config", {})
            if candidate["provider"] == "anthropic":
                assert model == HAIKU_45[0] and config == {"thinking_budget_tokens": 32000}
            else:
                assert model == "claude-haiku-4.5" and not config
