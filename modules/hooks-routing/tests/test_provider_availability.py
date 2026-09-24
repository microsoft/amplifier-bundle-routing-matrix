"""Opt-in host availability is not an empty catalog or a default fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_module_hooks_routing.resolver import resolve_model_role


def host(broken=()):
    def check(name):
        if name in broken:
            raise ValueError("Configured account unavailable: " + name)

    return SimpleNamespace(
        config={
            "providers": [
                {
                    "module": "provider-openai",
                    "instance_id": "work",
                    "config": {"default_model": "work-model", "priority": 1},
                },
                {
                    "module": "provider-openai",
                    "instance_id": "personal",
                    "config": {"default_model": "personal-model", "priority": 2},
                },
            ]
        },
        get_capability=lambda name: check if name == "provider.check_available" else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["work-model", "work-*"])
async def test_unavailable_exact_or_cached_glob_never_inherits_default(model):
    broken = SimpleNamespace(list_models=AsyncMock())
    matrix = {"coding": {"candidates": [{"provider": "work", "model": model}]}}
    with pytest.raises(ValueError, match="account unavailable: work"):
        await resolve_model_role(
            ["coding"],
            matrix,
            {"work": broken},
            coordinator=host({"work"}),
            preresolved_models={"work": ["work-model"]},
        )
    broken.list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_declared_candidate_fallback_can_select_healthy_account():
    providers = {
        name: SimpleNamespace(list_models=AsyncMock(return_value=[name + "-model"]))
        for name in ("work", "personal")
    }
    matrix = {
        "coding": {
            "candidates": [
                {"provider": "work", "model": "work-*"},
                {"provider": "personal", "model": "personal-*"},
            ]
        }
    }
    resolved = await resolve_model_role(["coding"], matrix, providers, coordinator=host({"work"}))
    assert resolved[0]["provider"] == "personal"
    providers["work"].list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_failure_keeps_its_error_when_declared_candidates_exhausted():
    failed = SimpleNamespace(list_models=AsyncMock(side_effect=RuntimeError("catalog unavailable")))
    matrix = {"coding": {"candidates": [{"provider": "work", "model": "work-*"}]}}
    with pytest.raises(RuntimeError, match="catalog unavailable"):
        await resolve_model_role(["coding"], matrix, {"work": failed}, coordinator=host())


@pytest.mark.asyncio
async def test_core_instance_ids_select_model_intent_and_keep_catalogs_separate():
    providers = {
        name: SimpleNamespace(list_models=AsyncMock(return_value=[name + "-model"]))
        for name in ("work", "personal")
    }
    matrix = {
        name: {"candidates": [{"provider": "openai", "model": name + "-*"}]} for name in providers
    }
    cache = {}
    for name in providers:
        resolved = await resolve_model_role(
            [name], matrix, providers, coordinator=host(), preresolved_models=cache
        )
        assert resolved[0]["provider"] == name
        providers[name].list_models.assert_awaited_once()
    assert cache == {"work": ["work-model"], "personal": ["personal-model"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["session:start", "session:resume"])
async def test_opted_in_host_defers_unused_agent_resolution_on_both_lifecycles(tmp_path, event):
    from .test_resume_lifecycle import _captured_providers, _make_coordinator, _handler_for, _mount

    providers = _captured_providers()
    coordinator, _ = _make_coordinator(providers, agents={"worker": {"model_role": "fast"}})
    coordinator.get_capability.side_effect = lambda key: (
        True if key == "routing.defer_agent_resolution" else None
    )
    original = dict(coordinator.config["agents"]["worker"])
    await _mount(coordinator, tmp_path)
    result = await _handler_for(coordinator, event)(event, {"session_id": "root"})
    assert result.action == "continue"
    assert coordinator.config["agents"]["worker"] == original
    for provider in providers.values():
        provider.list_models.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["unknown-role", "absent-provider", "empty-catalog", "no-model-match"]
)
async def test_genuine_no_match_still_allows_callers_default(case):
    provider = SimpleNamespace(
        list_models=AsyncMock(return_value=["other-model"] if case == "no-model-match" else [])
    )
    matrix = {"coding": {"candidates": [{"provider": "work", "model": "work-*"}]}}
    result = await resolve_model_role(
        ["unknown" if case == "unknown-role" else "coding"],
        matrix,
        {} if case == "absent-provider" else {"work": provider},
        coordinator=host(),
    )
    assert result == []


@pytest.mark.asyncio
@pytest.mark.parametrize("healthy_fallback", [False, True])
async def test_ordered_roles_preserve_failure_unless_declared_fallback_resolves(healthy_fallback):
    providers = {
        name: SimpleNamespace(list_models=AsyncMock(return_value=[name + "-model"]))
        for name in ("work", "personal")
    }
    matrix = {
        "coding": {"candidates": [{"provider": "work", "model": "work-*"}]},
        "fallback": {
            "candidates": [
                {
                    "provider": "personal",
                    "model": "personal-*" if healthy_fallback else "no-match-*",
                }
            ]
        },
    }
    resolution = resolve_model_role(
        ["coding", "missing-role", "fallback"], matrix, providers, coordinator=host({"work"})
    )
    if healthy_fallback:
        assert (await resolution)[0]["provider"] == "personal"
    else:
        with pytest.raises(ValueError, match="account unavailable: work"):
            await resolution


@pytest.mark.asyncio
async def test_bare_family_does_not_implicitly_try_another_healthy_account():
    providers = {
        name: SimpleNamespace(list_models=AsyncMock(return_value=[name + "-model"]))
        for name in ("work", "personal")
    }
    matrix = {"coding": {"candidates": [{"provider": "openai", "model": "work-*"}]}}
    with pytest.raises(ValueError, match="account unavailable: work"):
        await resolve_model_role(["coding"], matrix, providers, coordinator=host({"work"}))
    for provider in providers.values():
        provider.list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_unregistered_availability_retains_legacy_catalog_failure_handling():
    provider = SimpleNamespace(list_models=AsyncMock(side_effect=RuntimeError("offline")))
    matrix = {"coding": {"candidates": [{"provider": "work", "model": "work-*"}]}}
    coordinator = SimpleNamespace(get_capability=lambda key: None)
    assert (
        await resolve_model_role(["coding"], matrix, {"work": provider}, coordinator=coordinator)
        == []
    )


@pytest.mark.asyncio
async def test_async_availability_is_a_contract_error_not_an_account_fallback():
    import inspect
    from unittest.mock import Mock

    async def check_async(name):
        raise ValueError("unavailable")

    pending = check_async("work")
    check = Mock(return_value=pending)
    coordinator = SimpleNamespace(
        get_capability=lambda key: check if key == "provider.check_available" else None
    )
    providers = {name: SimpleNamespace(list_models=AsyncMock()) for name in ("work", "personal")}
    matrix = {
        "coding": {
            "candidates": [{"provider": name, "model": name + "-model"} for name in providers]
        }
    }
    with pytest.raises(TypeError, match="must be synchronous"):
        await resolve_model_role(["coding"], matrix, providers, coordinator=coordinator)
    check.assert_called_once_with("work")
    assert inspect.getcoroutinestate(pending) == inspect.CORO_CLOSED
    for provider in providers.values():
        provider.list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_rechecks_unavailable_account_even_after_catalog_is_cached():
    from amplifier_module_hooks_routing.resolver_class import MatrixModelRoleResolver

    broken = set()
    provider = SimpleNamespace(list_models=AsyncMock(return_value=["work-model"]))
    matrix = {"coding": {"candidates": [{"provider": "work", "model": "work-*"}]}}
    resolver = MatrixModelRoleResolver(matrix, {"work": provider}, "test", coordinator=host(broken))
    assert (await resolver.resolve("coding"))[0].provider == "work"
    broken.add("work")
    with pytest.raises(ValueError, match="account unavailable: work"):
        await resolver.resolve("coding")
    provider.list_models.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_catalog_fetches_are_separate_for_each_mounted_account():
    import asyncio

    async def catalog(name):
        await asyncio.sleep(0)
        return [name + "-model"]

    providers = {name: SimpleNamespace(list_models=AsyncMock()) for name in ("work", "personal")}
    for name, provider in providers.items():

        async def list_models(n=name):
            return await catalog(n)

        provider.list_models.side_effect = list_models
    matrix = {
        name: {"candidates": [{"provider": "openai", "model": name + "-*"}]} for name in providers
    }
    cache, inflight = {}, {}
    results = await asyncio.gather(
        *(
            resolve_model_role(
                [name],
                matrix,
                providers,
                coordinator=host(),
                preresolved_models=cache,
                inflight_model_lists=inflight,
            )
            for name in ("work", "personal", "work", "personal")
        )
    )
    assert [rows[0]["model"] for rows in results] == [
        "work-model",
        "personal-model",
        "work-model",
        "personal-model",
    ]
    for provider in providers.values():
        provider.list_models.assert_awaited_once()
    assert not inflight


@pytest.mark.asyncio
async def test_core_instance_id_takes_precedence_over_legacy_id():
    coordinator = host()
    coordinator.config["providers"][0]["id"] = "personal"
    providers = {name: SimpleNamespace(list_models=AsyncMock()) for name in ("work", "personal")}
    matrix = {"coding": {"candidates": [{"provider": "openai", "model": "work-model"}]}}
    assert (await resolve_model_role(["coding"], matrix, providers, coordinator=coordinator))[0][
        "provider"
    ] == "work"


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_field", ["preresolved_models", "preresolved_models_by_instance"])
async def test_lifecycle_only_trusts_instance_scoped_inherited_catalogs(tmp_path, cache_field):
    from amplifier_module_hooks_routing import mount
    from .test_resume_lifecycle import _make_coordinator, _handler_for

    (tmp_path / "balanced.yaml").write_text("""name: balanced
roles:
  coding:
    candidates:
      - provider: openai
        model: model-*
""")
    provider = SimpleNamespace(list_models=AsyncMock(return_value=["model-1"]))
    agents = {"worker": {"model_role": "coding"}}
    coordinator, _ = _make_coordinator({"openai": provider}, agents=agents)
    inherited = {cache_field: {"openai": ["model-9"]}, "keep": "caller-state"}
    coordinator.get_capability.side_effect = lambda key: (
        inherited if key == "session.routing" else None
    )
    await mount(coordinator, {"custom_routing_dirs": [str(tmp_path)]})
    await _handler_for(coordinator, "session:start")("session:start", {})
    expected = "model-1" if cache_field == "preresolved_models" else "model-9"
    assert agents["worker"]["provider_preferences"][0]["model"] == expected
    assert provider.list_models.await_count == (cache_field == "preresolved_models")
    written = [
        c.args[1]
        for c in coordinator.register_capability.call_args_list
        if c.args[0] == "session.routing"
    ][-1]
    assert written["preresolved_models_by_instance"] == {"openai": [expected]}
    assert written["keep"] == "caller-state"
    assert inherited[cache_field] == {"openai": ["model-9"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("defer", [None, False, 1, "true", SimpleNamespace(), MagicMock()])
async def test_only_literal_true_defers_eager_agent_resolution(tmp_path, defer):
    from .test_resume_lifecycle import _captured_providers, _make_coordinator, _handler_for, _mount

    agents = {"worker": {"model_role": "fast"}}
    coordinator, _ = _make_coordinator(_captured_providers(), agents=agents)
    coordinator.get_capability.side_effect = lambda key: (
        defer if key == "routing.defer_agent_resolution" else None
    )
    await _mount(coordinator, tmp_path)
    await _handler_for(coordinator, "session:start")("session:start", {})
    assert agents["worker"]["provider_preferences"][0]["provider"] == "luna"
