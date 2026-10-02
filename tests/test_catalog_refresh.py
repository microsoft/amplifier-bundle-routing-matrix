"""October catalog refresh: test outcomes, not just model-pattern spelling."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing.knob_consistency import (  # noqa: E402
    CallerContext,
    parse_preset,
    rung_of,
)
from amplifier_module_hooks_routing.resolver import resolve_model_role  # noqa: E402
from amplifier_module_hooks_routing.resolver_class import MatrixModelRoleResolver  # noqa: E402


def matrix(name):
    return yaml.safe_load((ROOT / "routing" / f"{name}.yaml").read_text())


def provider(ids):
    return SimpleNamespace(list_models=AsyncMock(return_value=[SimpleNamespace(id=i) for i in ids]))


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["openai", "openai-chatgpt"])
@pytest.mark.parametrize("name", ["balanced", "quality", "economy", "openai"])
async def test_luna_selection_tracks_gpt6_without_selecting_fast(name, backend):
    data = matrix(name)
    mounted = {backend: provider(["gpt-5.6-luna", "gpt-6-luna", "gpt-6-luna-fast"])}
    checked = 0
    for role, definition in data["roles"].items():
        for candidate in definition["candidates"]:
            if candidate["provider"] == "openai" and candidate["model"].endswith("-luna"):
                result = await resolve_model_role(
                    [role], {role: {"candidates": [candidate]}}, mounted
                )
                assert result[0]["model"] == "gpt-6-luna"
                checked += 1
    assert checked > 0


@pytest.mark.parametrize("model,rung", [
    ("gpt-6-luna", 0), ("gpt-6-luna-fast", 0),
    ("gpt-6-sol", 2), ("gpt-6-astra", 2), ("gpt-6-astra-fast", 2),
    ("gpt-6.1-sol", 2), ("gpt-5.6-terra", 1),
])
def test_current_gpt6_models_are_classified(model, rung):
    preset = parse_preset(matrix("openai"))
    assert rung_of(model, preset.tier_ladder["openai"]) == rung


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["openai", "openai-chatgpt"])
@pytest.mark.parametrize("model", ["gpt-5.6-luna", "gpt-6-luna", "gpt-6-luna-fast"])
async def test_default_derived_strict_context_keeps_exact_caller_model(backend, model):
    pytest.importorskip("amplifier_foundation.spawn_utils")
    data = matrix("openai")
    mounted = {backend: provider([
        "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-luna-fast", "gpt-6-luna", "gpt-6-luna-fast",
    ])}
    plan = {"providers": [{
        "module": f"provider-{backend}", "id": backend,
        "config": {"priority": 0, "default_model": model, "reasoning_effort": "medium"},
    }]}
    coordinator = SimpleNamespace(config=plan)
    resolver = MatrixModelRoleResolver(
        data["roles"], mounted, "openai", coordinator, preset=parse_preset(data)
    )
    prefs = await resolver.resolve("reasoning")  # No manufactured canonical caller.
    assert prefs[0].provider == backend
    assert prefs[0].model == model
    assert prefs[0].config["reasoning_effort"] == "medium"
    assert resolver.clamp_records[-1].honored


@pytest.mark.asyncio
async def test_explicit_context_does_not_substitute_fast_sibling():
    data = matrix("openai")
    result = await resolve_model_role(
        ["reasoning"], data["roles"],
        {"openai-chatgpt": provider(["gpt-5.6-luna", "gpt-5.6-luna-fast"])},
        caller_context=CallerContext("openai", "gpt-5.6-luna", "medium"),
        preset=parse_preset(data),
    )
    assert result[0]["model"] == "gpt-5.6-luna"


def test_copilot_pins_refresh_all_matrices():
    forbidden = {"claude-sonnet-5", "claude-opus-5", "gpt-5.6-luna", "gpt-5.6-sol", "gemini-3.5-flash"}
    for path in (ROOT / "routing").glob("*.yaml"):
        data = yaml.safe_load(path.read_text())
        for role in data["roles"].values():
            for candidate in role["candidates"]:
                if candidate["provider"] == "github-copilot":
                    assert candidate["model"] not in forbidden, path.name
    vision = matrix("copilot")["roles"]["vision"]["candidates"][0]
    assert vision["model"] == "claude-sonnet-5.5"


def test_sol_pause_stays_in_place():
    for name in ["balanced", "quality", "economy", "openai"]:
        for role in matrix(name)["roles"].values():
            assert all("-sol" not in c["model"] and "-astra" not in c["model"]
                       for c in role["candidates"] if c["provider"] == "openai")


@pytest.mark.asyncio
async def test_exact_chatgpt_fallback_preserves_origin_with_both_backends():
    data = matrix("openai")
    result = await resolve_model_role(
        ["reasoning"], data["roles"],
        {"openai": provider(["gpt-6-luna"]), "subscription": provider(["gpt-6-luna-fast"])},
        caller_context=CallerContext("openai", "gpt-6-luna-fast", "medium", "subscription"),
        preset=parse_preset(data),
    )
    assert result[0]["provider"] == "subscription"
    assert result[0]["model"] == "gpt-6-luna-fast"


def test_explicit_backend_ladder_is_not_normalized():
    from amplifier_module_hooks_routing.knob_consistency import derive_caller_context
    data = matrix("openai")
    data["preset"]["tier_ladder"]["openai-chatgpt"] = [["gpt-6-luna*"]]
    coordinator = SimpleNamespace(config={"providers": [{
        "module": "provider-openai-chatgpt", "id": "subscription",
        "config": {"default_model": "gpt-6-luna"},
    }]})
    caller = derive_caller_context(coordinator, parse_preset(data))
    assert caller.family == "openai-chatgpt" and caller.provider_key == "subscription"


@pytest.mark.asyncio
async def test_derived_exact_fallback_prefers_instance_id_over_conflicting_id():
    pytest.importorskip("amplifier_foundation.spawn_utils")
    data = matrix("openai")
    mounted = {"openai": provider(["gpt-6-luna"]),
               "subscription": provider(["gpt-6-luna-fast"])}
    coordinator = SimpleNamespace(config={"providers": [
        {"module": "provider-openai", "id": "openai",
         "config": {"priority": 1, "default_model": "gpt-5.6-terra"}},
        {"module": "provider-openai-chatgpt", "instance_id": "subscription", "id": "openai",
         "config": {"priority": 0, "default_model": "gpt-6-luna-fast", "reasoning_effort": "medium"}},
    ]})
    resolver = MatrixModelRoleResolver(data["roles"], mounted, "openai", coordinator,
                                      preset=parse_preset(data))
    preferences = await resolver.resolve("reasoning")
    assert preferences[0].provider == "subscription"
    assert preferences[0].model == "gpt-6-luna-fast"
    from amplifier_foundation.spawn_utils import apply_provider_preferences_with_resolution
    coordinator.get = lambda key: mounted if key == "providers" else None
    child = await apply_provider_preferences_with_resolution(coordinator.config, preferences, coordinator)
    assert child["providers"][1]["config"]["default_model"] == "gpt-6-luna-fast"
    assert child["providers"][1]["config"]["priority"] == 0
    assert child["providers"][0]["config"]["priority"] > 0