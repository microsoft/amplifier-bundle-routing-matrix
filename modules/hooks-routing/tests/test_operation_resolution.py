"""The optional route filters before winner selection, never after dispatch."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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


def catalog_failure_fixture(availability=None):
    error = PermissionError("synthetic catalog denied")
    catalog = AsyncMock(side_effect=error)
    resolver = fixture()
    resolver._providers["openai"] = SimpleNamespace(list_models=catalog)
    resolver._matrix_roles["image-gen"]["candidates"][0]["model"] = "agent-*"
    resolver._coordinator.get_capability = (
        lambda name: availability if name == "provider.check_available" else None
    )
    return resolver, catalog, error


@pytest.mark.asyncio
@pytest.mark.parametrize("with_availability", [False, True], ids=["no-callback", "callback"])
async def test_operation_catalog_failure_propagates_before_accept(with_availability):
    availability = Mock() if with_availability else None
    resolver, catalog, error = catalog_failure_fixture(availability)
    accept = AsyncMock(return_value=True)

    with pytest.raises(PermissionError) as caught:
        await resolver.resolve_for("image-gen", requirements={"type": "image"}, accept=accept)

    assert caught.value is error
    catalog.assert_awaited_once_with()
    accept.assert_not_called()
    if availability is not None:
        availability.assert_called_once_with("openai")


@pytest.mark.asyncio
async def test_ordinary_catalog_failure_still_falls_back_without_callback():
    resolver, catalog, _ = catalog_failure_fixture()

    result = await resolver.resolve("image-gen")

    catalog.assert_awaited_once_with()
    assert len(result) == 1
    assert result[0].provider == "gemini"
    assert result[0].model == "agent-two"
    assert "image_generation" not in result[0].config
