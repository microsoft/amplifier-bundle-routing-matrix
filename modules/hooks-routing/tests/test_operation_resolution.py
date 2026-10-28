"""The optional route filters before winner selection, never after dispatch."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from amplifier_module_hooks_routing.resolver_class import MatrixModelRoleResolver


def fixture():
    providers = {"openai": object(), "gemini": object()}
    matrix = {"image-gen": {"candidates": [
        {"provider": "openai", "model": "agent-one", "config": {"image_generation": {"model": "image-one"}}},
        {"provider": "gemini", "model": "agent-two", "config": {"image_generation": {"model": "image-two"}}},
    ]}}
    coordinator = SimpleNamespace(get_capability=lambda name: None, get=lambda name: None,
                                  config={"providers": []})
    return MatrixModelRoleResolver(matrix, providers, "synthetic", coordinator=coordinator)


@pytest.mark.asyncio
async def test_filter_precedes_winner_and_ordinary_resolution_unchanged():
    resolver = fixture()
    assert (await resolver.resolve("image-gen"))[0].provider == "openai"
    assert "image_generation" not in (await resolver.resolve("image-gen"))[0].config
    accept = AsyncMock(side_effect=[False, True])
    result = await resolver.resolve_for("image-gen", requirements={"type": "image"}, accept=accept)
    assert result[0].provider == "gemini" and result[0].model == "agent-two"
    assert accept.call_args_list[0].args[0]["config"]["image_generation"]["model"] == "image-one"
    assert (await resolver.resolve("image-gen"))[0].provider == "openai"


@pytest.mark.asyncio
async def test_candidate_failures_are_not_authorized_fallback():
    resolver = fixture()
    accept = AsyncMock(side_effect=PermissionError("denied"))
    with pytest.raises(PermissionError):
        await resolver.resolve_for("image-gen", requirements={}, accept=accept)
    assert accept.await_count == 1


@pytest.mark.asyncio
async def test_no_match_and_malformed_acceptance_refuse():
    resolver = fixture()
    assert await resolver.resolve_for("image-gen", requirements={}, accept=AsyncMock(return_value=False)) == []
    with pytest.raises(ValueError, match="bool"):
        await resolver.resolve_for("image-gen", requirements={}, accept=AsyncMock(return_value={"accepted": True}))
