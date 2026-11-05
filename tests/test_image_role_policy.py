"""Offline checks of image-role YAML policy, not model-quality measurements.

The representative mainline IDs below check the declared agent-model families.
They are not fetched catalogs, entitlement evidence, or provider capability probes.
Runtime selection, custom-file precedence, and operation qualification require
separate resolver/integration checks; this file does not call a provider.
"""

from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml


ROUTING_DIR = Path(__file__).resolve().parents[1] / "routing"
IMAGE_MATRICES = ("balanced", "quality", "economy", "gemini", "openai", "openai-api")

# Ordinary tool-using model families, separate from native image-only models.
MAINLINE_MODELS = {
    "openai": {"gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"},
    "gemini": {"gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.1-flash-lite"},
}
IMAGE_ONLY_MODELS = {
    "gpt-image-2.5-flare",
    "gpt-image-2.5-sunburst",
    "gemini-nano-banana-2.1",
    "gemini-3-pro-image",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-lite-image",
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image",
}


def matrix(name):
    return yaml.safe_load((ROUTING_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def image_candidates(name):
    return matrix(name)["roles"]["image-gen"]["candidates"]


@pytest.mark.parametrize(
    "name,controller,image_model,providers",
    [
        ("balanced", "gpt-6.1-sol", "gpt-image-2.5-flare", ["openai", "gemini"]),
        ("quality", "gpt-6-astra", "gpt-image-2.5-sunburst", ["openai", "gemini"]),
        ("economy", "gpt-6-luna", "gpt-image-2.5-flare", ["openai", "gemini", "gemini"]),
    ],
)
def test_shared_image_policy_is_openai_first(name, controller, image_model, providers):
    candidates = image_candidates(name)
    assert [candidate["provider"] for candidate in candidates] == providers
    assert candidates[0]["model"] == controller
    assert candidates[0]["config"]["image_generation"] == {
        "model": image_model,
        "transport": "responses",
    }
    # Updating one role must not turn a shared strategy into an API-only profile.
    assert "provider_module_allowlist" not in matrix(name)
    assert "preset" not in matrix(name)


@pytest.mark.parametrize(
    "name,agent_model,image_models",
    [
        ("balanced", "gemini-[3-9]*-pro-preview", ["gemini-nano-banana-2.1"]),
        ("quality", "gemini-[3-9]*-pro-preview", ["gemini-3-pro-image"]),
        (
            "economy",
            "gemini-[3-9]*-flash-lite",
            ["gemini-3.1-flash-lite-image", "gemini-nano-banana-2.1"],
        ),
        ("gemini", "gemini-[3-9]*-pro-preview", ["gemini-nano-banana-2.1"]),
    ],
)
def test_gemini_native_image_preferences_remain_separate(name, agent_model, image_models):
    candidates = [row for row in image_candidates(name) if row["provider"] == "gemini"]
    assert [row["model"] for row in candidates] == [agent_model] * len(image_models)
    assert [row["config"]["image_generation"] for row in candidates] == [
        {"model": model, "transport": "interactions"} for model in image_models
    ]
    # Economy's second image model is a pre-dispatch compatibility alternative
    # for reference/control limits, not permission to replay a failed effect.


@pytest.mark.parametrize("name", IMAGE_MATRICES)
def test_agent_model_selectors_do_not_promote_image_only_models(name):
    candidates = image_candidates(name)
    assert candidates
    for candidate in candidates:
        selector = candidate["model"]
        native_model = candidate["config"]["image_generation"]["model"]
        assert any(fnmatchcase(model, selector) for model in MAINLINE_MODELS[candidate["provider"]])
        assert not any(fnmatchcase(model, selector) for model in IMAGE_ONLY_MODELS)
        assert selector != native_model
        assert native_model in IMAGE_ONLY_MODELS


@pytest.mark.parametrize("name", IMAGE_MATRICES)
def test_image_operation_config_is_closed_and_has_no_effort_or_credentials(name):
    for candidate in image_candidates(name):
        assert set(candidate) == {"provider", "model", "config"}
        config = candidate["config"]
        # Preserve existing ordinary-agent effort in the OpenAI profiles only.
        # It is not image quality and must not leak into the native-image schema.
        expected_agent_config = (
            {"reasoning_effort": "high"} if name in {"openai", "openai-api"} else {}
        )
        assert {key: value for key, value in config.items() if key != "image_generation"} == (
            expected_agent_config
        )
        image_config = config["image_generation"]
        assert set(image_config) == {"model", "transport"}
        assert isinstance(image_config["model"], str)
        assert not any(character in image_config["model"] for character in "*?[")
        assert image_config["transport"] == {
            "openai": "responses",
            "gemini": "interactions",
        }[candidate["provider"]]
        # Exact key sets also reject enabled, secret/endpoint settings, and
        # inherited effort/thinking dictionaries masquerading as image controls.


def test_gemini_strategy_stays_gemini_only():
    data = matrix("gemini")
    assert data["name"] == "gemini"
    assert "preset" not in data
    for role in data["roles"].values():
        assert role["candidates"]
        assert all(candidate["provider"] == "gemini" for candidate in role["candidates"])


def test_openai_profiles_preserve_scope_presets_and_non_image_roles():
    legacy = matrix("openai")
    api = matrix("openai-api")
    subscription = matrix("openai-chatgpt")
    assert "provider_module_allowlist" not in legacy
    assert api["provider_module_allowlist"] == ["provider-openai"]
    assert subscription["provider_module_allowlist"] == ["provider-openai-chatgpt"]
    assert legacy["preset"] == api["preset"] == subscription["preset"]
    assert legacy["preset"]["delegation"] == {"inherit": "strict", "report_unhonored": True}
    assert legacy["roles"].keys() == api["roles"].keys() == subscription["roles"].keys()
    for role in legacy["roles"]:
        if role != "image-gen":
            assert legacy["roles"][role] == api["roles"][role] == subscription["roles"][role]
    assert legacy["roles"]["image-gen"] == api["roles"]["image-gen"]
    assert image_candidates("openai") == [
        {
            "provider": "openai",
            "model": "gpt-6.1-sol",
            "config": {
                "reasoning_effort": "high",
                "image_generation": {"model": "gpt-image-2.5-flare", "transport": "responses"},
            },
        }
    ]


def test_subscription_profile_does_not_gain_native_api_image_config():
    assert image_candidates("openai-chatgpt") == [
        {"provider": "openai", "model": "gpt-6.1-sol", "config": {"reasoning_effort": "high"}}
    ]


@pytest.mark.parametrize("name", IMAGE_MATRICES)
def test_image_operation_config_is_not_added_to_other_roles(name):
    roles = matrix(name)["roles"]
    assert {"general", "fast", "image-gen"} <= roles.keys()
    for role, definition in roles.items():
        if role != "image-gen":
            for candidate in definition["candidates"]:
                assert "image_generation" not in candidate.get("config", {})
