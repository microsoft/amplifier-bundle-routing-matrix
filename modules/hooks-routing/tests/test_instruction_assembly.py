"""hooks-routing's optional ``context.instructions.v1`` producer contract."""

from __future__ import annotations

import importlib
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from amplifier_module_hooks_routing import mount


class _Lease:
    def __init__(self) -> None:
        self.route = "pending"
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Assembly:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.lease = _Lease()
        self.callback: Any = None

    def register(self, source_id: str, callback: Any) -> _Lease:
        self.events.append(f"assembly:{source_id}")
        self.callback = callback
        return self.lease


class _Hooks:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.handlers: dict[str, Any] = {}

    def register(self, event: str, handler: Any, **_kwargs: Any) -> None:
        self.events.append(f"hook:{event}")
        self.handlers[event] = handler


class _Context:
    def __init__(self, prompt: str) -> None:
        async def base() -> str:
            return prompt

        self._system_prompt_factory = base

    async def set_system_prompt_factory(self, factory: Any) -> None:
        self._system_prompt_factory = factory


class _Coordinator:
    def __init__(
        self,
        assembly: _Assembly | None,
        context: _Context | None = None,
        providers: dict[str, Any] | None = None,
    ) -> None:
        self.events: list[str] = []
        self.assembly = assembly
        self.context = context
        self.hooks = _Hooks(self.events)
        self.providers = providers or {}
        self.config = {"agents": {}}
        self.session_state: dict[str, Any] = {}
        self.capabilities: dict[str, Any] = {}

    def get(self, name: str) -> Any:
        if name == "context":
            return self.context
        if name == "providers":
            return self.providers
        return None

    def get_capability(self, name: str) -> Any:
        if name == "context.instructions.v1":
            return self.assembly
        return self.capabilities.get(name)

    def register_capability(self, name: str, value: Any) -> None:
        self.capabilities[name] = value

    async def process_hook_result(self, result: Any, **_kwargs: Any) -> Any:
        return result


def _write_matrix(
    tmp_path: Path,
    general_description: str = "General purpose",
    *,
    general_provider: str = "anthropic",
    general_model: str = "claude-sonnet",
    general_config: str = "original",
) -> Path:
    bundle_root = tmp_path / "bundle"
    routing_dir = bundle_root / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)
    (routing_dir / "balanced.yaml").write_text(
        textwrap.dedent(
            f"""\
            name: balanced
            description: "Test matrix"
            updated: "2026-01-01"

            roles:
              general:
                description: "{general_description}"
                candidates:
                  - provider: {general_provider}
                    model: {general_model}
                    config:
                      marker: "{general_config}"
              fast:
                description: "Quick work"
                candidates:
                  - provider: openai
                    model: gpt-fast
            """
        )
    )
    return bundle_root


async def _mount(
    tmp_path: Path,
    coordinator: _Coordinator,
    *,
    general_description: str = "General purpose",
):
    return await mount(
        coordinator,
        {
            "default_matrix": "balanced",
            "_bundle_root": str(_write_matrix(tmp_path, general_description)),
        },
    )


@pytest.mark.asyncio
async def test_v1_catalog_registers_during_mount_and_is_a_detached_stable_head(
    tmp_path: Path,
) -> None:
    coordinator = _Coordinator(_Assembly([]))
    coordinator.assembly.events = coordinator.events

    cleanup = await _mount(tmp_path, coordinator)

    assert coordinator.events[:2] == [
        "assembly:routing-matrix",
        "hook:session:start",
    ]
    first = coordinator.assembly.callback({"request_id": "before-first-hook"})
    assert first == [
        {
            "key": "catalog",
            "content": first[0]["content"],
            "placement": "head",
        }
    ]
    assert first[0]["content"].count('<system-reminder source="routing-matrix">') == 1
    assert "General purpose" in first[0]["content"]

    coordinator.assembly.lease.route = "v1"
    handler = coordinator.hooks.handlers["provider:request"]
    snapshots = []
    for request_id in ("one", "two", "three"):
        result = await handler("provider:request", {"request_id": request_id})
        assert result.action == "continue"
        snapshots.append(coordinator.assembly.callback({"request_id": request_id}))

    assert snapshots[0] == snapshots[1] == snapshots[2] == first
    snapshots[0][0]["content"] = "mutated consumer copy"
    assert coordinator.assembly.callback({"request_id": "four"}) == first

    cleanup()
    assert coordinator.assembly.lease.closed is True
    assert coordinator.assembly.callback({"request_id": "after-cleanup"}) == []


@pytest.mark.asyncio
async def test_v1_stops_a_pending_prefix_wrapper_without_removing_peer_content(
    tmp_path: Path,
) -> None:
    context = _Context("BASE SYSTEM PROMPT\nPEER SYSTEM BLOCK")
    coordinator = _Coordinator(_Assembly([]), context)
    coordinator.assembly.events = coordinator.events
    await _mount(tmp_path, coordinator)
    handler = coordinator.hooks.handlers["provider:request"]

    pending = await handler("provider:request", {})
    assert pending.action == "continue"
    assert "routing-matrix" in await context._system_prompt_factory()

    coordinator.assembly.lease.route = "v1"
    active = await handler("provider:request", {})
    assert active.action == "continue"
    assert await context._system_prompt_factory() == "BASE SYSTEM PROMPT\nPEER SYSTEM BLOCK"

    records = coordinator.assembly.callback({"request_id": "v1"})
    assert len(records) == 1
    assert records[0]["placement"] == "head"
    assert records[0]["content"].count('<system-reminder source="routing-matrix">') == 1

    coordinator.assembly.lease.route = "legacy"
    legacy = await handler("provider:request", {})
    assert legacy.action == "continue"
    assert "routing-matrix" in await context._system_prompt_factory()


@pytest.mark.asyncio
async def test_fresh_mount_uses_the_current_catalog_not_a_prior_mount_snapshot(
    tmp_path: Path,
) -> None:
    first = _Coordinator(_Assembly([]))
    first.assembly.events = first.events
    await _mount(tmp_path / "first", first, general_description="First catalog")
    first_snapshot = first.assembly.callback({"request_id": "first"})

    second = _Coordinator(_Assembly([]))
    second.assembly.events = second.events
    await _mount(tmp_path / "second", second, general_description="Changed catalog")
    second_snapshot = second.assembly.callback({"request_id": "second"})

    assert "First catalog" in first_snapshot[0]["content"]
    assert "Changed catalog" in second_snapshot[0]["content"]
    assert first_snapshot != second_snapshot


@pytest.mark.asyncio
async def test_v1_banner_and_resolver_keep_the_mount_time_matrix_after_changes(
    tmp_path: Path,
) -> None:
    bundle_root = _write_matrix(
        tmp_path,
        general_description="Before change",
        general_provider="original-provider",
        general_model="original-model",
        general_config="original-config",
    )
    coordinator = _Coordinator(
        _Assembly([]), providers={"original-provider": object()}
    )
    coordinator.assembly.events = coordinator.events
    config = {"default_matrix": "balanced", "_bundle_root": str(bundle_root)}
    await mount(coordinator, config)
    before = coordinator.assembly.callback({"request_id": "before"})
    assert "Before change" in before[0]["content"]
    resolver = coordinator.capabilities["model_role_resolver"]
    assert resolver.known_roles == ("general", "fast")
    original_candidates = await resolver.resolve("general")
    assert [
        (candidate.provider, candidate.model, candidate.config)
        for candidate in original_candidates
    ] == [("original-provider", "original-model", {"marker": "original-config"})]

    coordinator.assembly.lease.route = "v1"
    config["overrides"] = {
        "general": {
            "description": "Config change",
            "candidates": [
                {
                    "provider": "changed-provider",
                    "model": "changed-model",
                    "config": {"marker": "changed-config"},
                }
            ],
        }
    }
    result = await coordinator.hooks.handlers["provider:request"]("provider:request", {})
    after_config = coordinator.assembly.callback({"request_id": "after-config"})
    assert result.action == "continue"
    assert after_config == before
    assert resolver.known_roles == ("general", "fast")
    assert [
        (candidate.provider, candidate.model, candidate.config)
        for candidate in await resolver.resolve("general")
    ] == [
        ("original-provider", "original-model", {"marker": "original-config"})
    ]

    _write_matrix(
        tmp_path,
        general_description="After change",
        general_provider="file-provider",
        general_model="file-model",
        general_config="file-config",
    )
    config["overrides"] = {}
    result = await coordinator.hooks.handlers["provider:request"]("provider:request", {})
    after = coordinator.assembly.callback({"request_id": "after"})

    assert result.action == "continue"
    assert after == before
    assert resolver.known_roles == ("general", "fast")
    assert [
        (candidate.provider, candidate.model, candidate.config)
        for candidate in await resolver.resolve("general")
    ] == [
        ("original-provider", "original-model", {"marker": "original-config"})
    ]


@pytest.mark.asyncio
async def test_v1_banner_does_not_reload_a_broken_matrix_mid_session(
    tmp_path: Path,
) -> None:
    bundle_root = _write_matrix(tmp_path, general_description="Catalog A")
    coordinator = _Coordinator(_Assembly([]))
    coordinator.assembly.events = coordinator.events
    await mount(
        coordinator,
        {"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
    )
    coordinator.assembly.lease.route = "v1"
    handler = coordinator.hooks.handlers["provider:request"]

    assert (await handler("provider:request", {})).action == "continue"
    snapshot_a = coordinator.assembly.callback({"request_id": "success-a"})
    assert "Catalog A" in snapshot_a[0]["content"]

    (bundle_root / "routing" / "balanced.yaml").write_text("not: [valid")
    assert (await handler("provider:request", {})).action == "continue"
    assert coordinator.assembly.callback({"request_id": "after-broken-file"}) == snapshot_a


@pytest.mark.asyncio
async def test_optional_context_simple_source_places_one_catalog_record_at_head(
    tmp_path: Path,
) -> None:
    source = os.environ.get("AMPLIFIER_CONTEXT_SIMPLE_TEST_SOURCE")
    if not source:
        pytest.skip("set AMPLIFIER_CONTEXT_SIMPLE_TEST_SOURCE to run against context-simple")

    # The routing module suite normally supplies a deliberately tiny
    # amplifier_core stub.  Enrich it only for this optional cross-module
    # contract test; a real installed core already exposes these names.
    core = sys.modules["amplifier_core"]
    models = sys.modules["amplifier_core.models"]
    if not hasattr(core, "HookResult"):
        core.HookResult = models.HookResult
    if not hasattr(core, "ModuleCoordinator"):
        core.ModuleCoordinator = object
    if not hasattr(core, "TextBlock"):
        core.TextBlock = type("TextBlock", (), {})
    if not hasattr(core, "ToolResult"):
        class ToolResult:
            def __init__(self, success: bool, output: str) -> None:
                self.output = output

            def get_serialized_output(self) -> str:
                return self.output

        core.ToolResult = ToolResult

    sys.path.insert(0, source)
    try:
        context_module = importlib.import_module("amplifier_module_context_simple")
        instructions = importlib.import_module("amplifier_module_context_simple.instructions")
    finally:
        sys.path.remove(source)

    coordinator = _Coordinator(None)
    context = context_module.SimpleContextManager(
        max_tokens=2_000,
        compact_threshold=0.2,
        target_usage=0.1,
        compaction_notice_enabled=False,
    )
    assembly = instructions.InstructionAssembly(context, coordinator, session_id="routing-test")
    context._instruction_assembly = assembly
    coordinator.assembly = assembly

    await _mount(tmp_path, coordinator)
    handler = coordinator.hooks.handlers["provider:request"]

    class _V1Provider:
        instruction_layout_version = 1
        instruction_layout_authority_v1 = True

    rendered = []
    for request_id in ("one", "two", "three"):
        async with assembly.request({"request_id": request_id}, _V1Provider()):
            result = await handler("provider:request", {})
            assert result.action == "continue"
            rendered.append(await context.get_messages_for_request())

    for messages in rendered:
        heads = [
            message["content"]
            for message in messages
            if message["role"] == "system"
            and '<system-reminder source="routing-matrix">' in message["content"]
        ]
        assert len(heads) == 1
        assert heads[0].count('<system-reminder source="routing-matrix">') == 1
    assert rendered[0] == rendered[1] == rendered[2]