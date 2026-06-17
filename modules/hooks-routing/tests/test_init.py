"""Tests for hooks-routing mount() and hook handlers."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amplifier_module_hooks_routing import mount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(
    *,
    session_state: dict[str, Any] | None = None,
    providers: dict[str, Any] | None = None,
    agents: dict[str, Any] | None = None,
    has_hooks: bool = True,
) -> MagicMock:
    """Build a mock coordinator that follows the real API."""
    coordinator = MagicMock()
    coordinator.session_state = session_state if session_state is not None else {}
    coordinator.get = MagicMock(return_value=providers)

    if agents is not None:
        coordinator.config = {"agents": agents}
    else:
        coordinator.config = {"agents": {}}

    coordinator.get_capability = MagicMock(return_value=None)

    if has_hooks:
        coordinator.hooks = MagicMock()
        coordinator.hooks.register = MagicMock()
    else:
        del coordinator.hooks

    return coordinator


def _write_matrix(tmp_path: Path, name: str = "balanced") -> Path:
    """Write a minimal matrix YAML and return the routing dir."""
    routing_dir = tmp_path / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)
    content = textwrap.dedent("""\
        name: balanced
        description: "Test balanced matrix"
        updated: "2026-01-01"

        roles:
          general:
            description: "General purpose"
            candidates:
              - provider: anthropic
                model: claude-sonnet-4-20250514
          fast:
            description: "Fast tasks"
            candidates:
              - provider: openai
                model: gpt-4o-mini
          coding:
            description: "Code generation"
            candidates:
              - provider: anthropic
                model: claude-sonnet-*
              - provider: openai
                model: gpt-4o
    """)
    (routing_dir / f"{name}.yaml").write_text(content)
    return routing_dir


# ---------------------------------------------------------------------------
# mount() tests
# ---------------------------------------------------------------------------


class TestMount:
    @pytest.mark.asyncio
    async def test_mount_registers_hooks(self, tmp_path: Path) -> None:
        """Verify two hooks are registered on mount."""
        _write_matrix(tmp_path)
        coordinator = _make_coordinator()

        # Patch __file__ so bundle_root resolves to tmp_path
        with patch(
            "amplifier_module_hooks_routing.Path",
            return_value=tmp_path
            / "modules"
            / "hooks-routing"
            / "amplifier_module_hooks_routing"
            / "__init__.py",
        ):
            # Instead of patching Path, let's directly pass config that
            # forces the matrix path. We'll need to mock the file traversal.
            pass

        # Simpler approach: set up the real directory structure
        bundle_root = tmp_path / "bundle"
        modules_dir = (
            bundle_root / "modules" / "hooks-routing" / "amplifier_module_hooks_routing"
        )
        modules_dir.mkdir(parents=True)
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir()

        content = textwrap.dedent("""\
            name: balanced
            description: "Test balanced matrix"
            updated: "2026-01-01"
            roles:
              general:
                description: "General purpose"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-20250514
              fast:
                description: "Fast tasks"
                candidates:
                  - provider: openai
                    model: gpt-4o-mini
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        # Patch __file__ to simulate the real directory layout
        fake_init = modules_dir / "__init__.py"
        fake_init.write_text("")

        with patch("amplifier_module_hooks_routing.Path") as MockPath:
            MockPath.return_value = fake_init
            MockPath.__call__ = lambda self, x: Path(x)
            # This is tricky — let's use a different approach

        # Better: just patch the path traversal result directly
        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Should have registered two hooks
        assert coordinator.hooks.register.call_count == 2

        # Check the event names
        calls = coordinator.hooks.register.call_args_list
        events_registered = {call.args[0] for call in calls}
        assert "session:start" in events_registered
        assert "provider:request" in events_registered

    @pytest.mark.asyncio
    async def test_mount_with_no_matrix_file(self) -> None:
        """Graceful degradation when matrix file doesn't exist."""
        coordinator = _make_coordinator()

        # No _bundle_root, and __file__ traversal will point at real package dir
        # which has no routing/ subdirectory
        await mount(coordinator, config={"default_matrix": "nonexistent"})

        # Should still register hooks (graceful degradation)
        if hasattr(coordinator, "hooks"):
            assert coordinator.hooks.register.call_count == 2

    @pytest.mark.asyncio
    async def test_mount_with_config_overrides(self, tmp_path: Path) -> None:
        """Config dict overrides are composed on top of the base matrix."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test balanced"
            updated: "2026-01-01"
            roles:
              general:
                description: "General purpose"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-20250514
              fast:
                description: "Fast tasks"
                candidates:
                  - provider: openai
                    model: gpt-4o-mini
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        coordinator = _make_coordinator()

        # Pass overrides in config dict — this is how the CLI injects user
        # routing preferences via _apply_hook_overrides().
        config_overrides = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-3"},
                ],
            },
        }
        await mount(
            coordinator,
            config={
                "default_matrix": "balanced",
                "_bundle_root": str(bundle_root),
                "overrides": config_overrides,
            },
        )

        # The effective matrix should have the override applied to "fast"
        stored = coordinator.session_state["routing_matrix"]
        assert stored["roles"]["fast"]["candidates"] == [
            {"provider": "anthropic", "model": "claude-haiku-3"},
        ]
        # "general" should remain unchanged from the base matrix
        assert stored["roles"]["general"]["candidates"] == [
            {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        ]

    @pytest.mark.asyncio
    async def test_mount_stores_session_state(self, tmp_path: Path) -> None:
        """Mount stores routing matrix info in session_state."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test balanced"
            updated: "2026-01-01"
            roles:
              general:
                description: "General"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-20250514
              fast:
                description: "Fast"
                candidates:
                  - provider: openai
                    model: gpt-4o-mini
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        coordinator = _make_coordinator()
        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        assert "routing_matrix" in coordinator.session_state
        assert coordinator.session_state["routing_matrix"]["name"] == "balanced"
        assert "general" in coordinator.session_state["routing_matrix"]["roles"]


# ---------------------------------------------------------------------------
# Hook handler tests
# ---------------------------------------------------------------------------


class TestSessionStartHook:
    @pytest.mark.asyncio
    async def test_session_start_resolves_model_role(self, tmp_path: Path) -> None:
        """Agent config gets patched with provider_preferences."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test"
            updated: "2026-01-01"
            roles:
              general:
                description: "General"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-20250514
              fast:
                description: "Fast"
                candidates:
                  - provider: openai
                    model: gpt-4o-mini
              coding:
                description: "Code"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-20250514
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        agents = {
            "coder": {"model_role": "coding"},
            "helper": {"model_role": ["fast", "general"]},
            "plain": {},  # no model_role
        }
        providers = {"provider-anthropic": MagicMock(), "provider-openai": MagicMock()}
        coordinator = _make_coordinator(providers=providers, agents=agents)

        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Extract the session:start handler
        calls = coordinator.hooks.register.call_args_list
        session_start_handler = None
        for call in calls:
            if call.args[0] == "session:start":
                session_start_handler = call.args[1]
                break
        assert session_start_handler is not None

        # Invoke the handler
        await session_start_handler("session:start", {})

        # coder should have provider_preferences set
        assert "provider_preferences" in agents["coder"]
        assert agents["coder"]["provider_preferences"][0]["provider"] == "anthropic"

        # helper should resolve fast → openai
        assert "provider_preferences" in agents["helper"]
        assert agents["helper"]["provider_preferences"][0]["provider"] == "openai"

        # plain should not have provider_preferences
        assert "provider_preferences" not in agents["plain"]


class TestProviderRequestHook:
    @pytest.mark.asyncio
    async def test_provider_request_injects_context(self, tmp_path: Path) -> None:
        """Returns HookResult with inject_context action."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test"
            updated: "2026-01-01"
            roles:
              general:
                description: "General purpose"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-20250514
              fast:
                description: "Fast tasks"
                candidates:
                  - provider: openai
                    model: gpt-4o-mini
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        coordinator = _make_coordinator()
        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Extract the provider:request handler
        calls = coordinator.hooks.register.call_args_list
        provider_request_handler = None
        for call in calls:
            if call.args[0] == "provider:request":
                provider_request_handler = call.args[1]
                break
        assert provider_request_handler is not None

        # Invoke the handler
        result = await provider_request_handler("provider:request", {})

        assert result is not None
        assert result.action == "inject_context"
        assert result.ephemeral is True
        assert "balanced" in result.context_injection
        assert "general" in result.context_injection
        assert "fast" in result.context_injection


class TestModelRoleResolverCapability:
    @pytest.mark.asyncio
    async def test_mount_registers_model_role_resolver_capability(
        self, tmp_path: Path
    ) -> None:
        """mount() must register 'model_role_resolver' via coordinator.register_capability.

        Regression test: MatrixModelRoleResolver was shipped but never wired into
        mount() -- coordinator.get_capability("model_role_resolver") returned None on
        every call, producing a spurious WARNING on every delegate(..., model_role=...)
        and silently discarding the caller's role in favour of the agent's declared role.
        """
        # _write_matrix() creates routing/balanced.yaml and returns the routing dir;
        # we need the bundle root (its parent).
        routing_dir = _write_matrix(tmp_path)
        bundle_root = routing_dir.parent

        # Coordinator with an installed openai provider so "fast" role resolves.
        # register_capability is declared explicitly to keep assertion messages clear.
        mock_openai = MagicMock()
        coordinator = _make_coordinator(providers={"provider-openai": mock_openai})
        coordinator.register_capability = MagicMock()

        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # PRIMARY ASSERTION: mount() must call register_capability("model_role_resolver", ...)
        registered_names = [
            call.args[0] for call in coordinator.register_capability.call_args_list
        ]
        assert "model_role_resolver" in registered_names, (
            "mount() never called coordinator.register_capability('model_role_resolver', ...)."
            f" Calls seen: {registered_names!r}."
            " Wire MatrixModelRoleResolver into mount() so tool-delegate can resolve roles."
        )

        # SECONDARY ASSERTION: the registered resolver must return ProviderPreferences for a role.
        resolver_call = next(
            c
            for c in coordinator.register_capability.call_args_list
            if c.args[0] == "model_role_resolver"
        )
        resolver = resolver_call.args[1]

        # ProviderPreference lives in amplifier_foundation which is not guaranteed
        # to be importable in this test environment -- inject a lightweight stand-in
        # so we can verify resolver behaviour without a hard foundation dependency.
        import sys
        import types as _types

        class _FakeProviderPreference:
            def __init__(
                self, *, provider: str, model: str, config: dict | None = None
            ) -> None:
                self.provider = provider
                self.model = model
                self.config = config or {}

        fake_spawn = _types.ModuleType("amplifier_foundation.spawn_utils")
        fake_spawn.ProviderPreference = _FakeProviderPreference  # type: ignore[attr-defined]
        fake_foundation = _types.ModuleType("amplifier_foundation")

        with patch.dict(
            sys.modules,
            {
                "amplifier_foundation": fake_foundation,
                "amplifier_foundation.spawn_utils": fake_spawn,
            },
        ):
            prefs = await resolver.resolve("fast")

        assert len(prefs) > 0, (
            "Resolver returned an empty list for 'fast' role -- "
            "verify MatrixModelRoleResolver receives effective_matrix and providers."
        )
        assert prefs[0].provider == "openai", (
            f"Expected provider 'openai' for 'fast' role, got {prefs[0].provider!r}"
        )
        assert prefs[0].model == "gpt-4o-mini", (
            f"Expected model 'gpt-4o-mini' for 'fast' role, got {prefs[0].model!r}"
        )

class TestSessionStartParallelism:
    @pytest.mark.asyncio
    async def test_session_start_resolves_agents_in_parallel(
        self, tmp_path: Path
    ) -> None:
        """on_session_start must resolve all agents concurrently, not sequentially.

        With N agents each requiring a provider.list_models() call that takes
        LATENCY seconds, sequential execution would take N × LATENCY.  Parallel
        execution via asyncio.gather() takes ≈ LATENCY (plus small overhead).

        The test asserts elapsed < LATENCY × 3 to prove parallelism, which
        gives a safe margin for scheduling overhead while clearly distinguishing
        from the sequential case (N × LATENCY = 1.2s vs ~0.15s parallel).
        """
        import asyncio
        import time

        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)

        # Use a glob pattern so _resolve_glob() → list_models() is called per agent
        content = textwrap.dedent("""\
            name: balanced
            description: "Parallelism test matrix"
            updated: "2026-01-01"
            roles:
              general:
                description: "General purpose"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-*
              fast:
                description: "Fast tasks"
                candidates:
                  - provider: openai
                    model: gpt-4o-mini
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        LATENCY = 0.15  # seconds per list_models() call
        AGENT_COUNT = 8
        SEQUENTIAL_FLOOR = AGENT_COUNT * LATENCY  # 1.2s — fail threshold

        async def slow_list_models() -> list[str]:
            await asyncio.sleep(LATENCY)
            return ["claude-sonnet-4-20250514", "claude-sonnet-3-5-20241022"]

        mock_provider = MagicMock()
        mock_provider.list_models = slow_list_models
        providers = {"provider-anthropic": mock_provider}

        agents = {
            f"agent-{i:02d}": {"model_role": "general"} for i in range(AGENT_COUNT)
        }

        coordinator = _make_coordinator(providers=providers, agents=agents)

        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Extract the registered session:start handler
        calls = coordinator.hooks.register.call_args_list
        handler = next(
            call.args[1] for call in calls if call.args[0] == "session:start"
        )

        t0 = time.perf_counter()
        await handler("session:start", {})
        elapsed = time.perf_counter() - t0

        # Parallel: ~LATENCY (0.15s).  Sequential: AGENT_COUNT × LATENCY (1.2s).
        assert elapsed < LATENCY * 3, (
            f"on_session_start appears sequential: took {elapsed:.2f}s "
            f"for {AGENT_COUNT} agents × {LATENCY}s latency "
            f"(sequential would be {SEQUENTIAL_FLOOR:.2f}s, "
            f"parallel should be <{LATENCY * 3:.2f}s)"
        )

        # Correctness: every agent must still get resolved
        for name, agent_cfg in agents.items():
            assert "provider_preferences" in agent_cfg, (
                f"Agent '{name}' missing provider_preferences after parallel resolution"
            )
            assert agent_cfg["provider_preferences"][0]["provider"] == "anthropic"


# ---------------------------------------------------------------------------
# preresolved_models — session.routing propagation between parent and child
# ---------------------------------------------------------------------------


class TestPreresolvedModelsFlow:
    """session.routing["preresolved_models"] is read at on_session_start time
    (not mount time) and written back afterward, so child sessions skip
    list_models() HTTP calls for providers the parent already resolved.
    """

    def _make_routing_coordinator(
        self,
        *,
        providers: dict | None = None,
        agents: dict | None = None,
        routing_capability: dict | None = None,
    ) -> MagicMock:
        """Coordinator that returns a routing capability from get_capability."""
        coordinator = _make_coordinator(providers=providers, agents=agents)
        coordinator.get_capability = MagicMock(return_value=routing_capability)
        # register_capability is a no-op mock by default on MagicMock
        return coordinator

    @pytest.mark.asyncio
    async def test_session_start_reads_preresolved_from_routing_capability(
        self, tmp_path: Path
    ) -> None:
        """When session.routing carries preresolved_models, list_models() is skipped."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test"
            updated: "2026-01-01"
            roles:
              coding:
                description: "Code"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-*
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        models = ["claude-sonnet-4-20250514", "claude-haiku-3"]
        mock_provider = MagicMock()
        mock_provider.list_models = AsyncMock(return_value=models)
        providers = {"provider-anthropic": mock_provider}

        agents = {"coder": {"model_role": "coding"}}

        # Simulate parent having already fetched models — stored in session.routing
        routing_cap = {"preresolved_models": {"anthropic": models}}
        coordinator = self._make_routing_coordinator(
            providers=providers, agents=agents, routing_capability=routing_cap
        )

        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Extract and invoke on_session_start
        calls = coordinator.hooks.register.call_args_list
        handler = next(
            call.args[1] for call in calls if call.args[0] == "session:start"
        )
        await handler("session:start", {})

        # Agent must be resolved
        assert "provider_preferences" in agents["coder"]
        assert agents["coder"]["provider_preferences"][0]["provider"] == "anthropic"
        assert (
            agents["coder"]["provider_preferences"][0]["model"]
            == "claude-sonnet-4-20250514"
        )

        # list_models() must NOT have been called — preresolved list was used
        mock_provider.list_models.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_start_writes_fetched_models_back_to_routing(
        self, tmp_path: Path
    ) -> None:
        """After on_session_start fetches model lists, they are written into
        session.routing so subsequent child spawns inherit them."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test"
            updated: "2026-01-01"
            roles:
              coding:
                description: "Code"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-*
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        models = ["claude-sonnet-4-20250514"]
        mock_provider = MagicMock()
        mock_provider.list_models = AsyncMock(return_value=models)
        providers = {"provider-anthropic": mock_provider}

        agents = {"coder": {"model_role": "coding"}}

        # No preresolved models — coordinator starts clean
        coordinator = self._make_routing_coordinator(
            providers=providers, agents=agents, routing_capability=None
        )

        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Extract and invoke on_session_start
        calls = coordinator.hooks.register.call_args_list
        handler = next(
            call.args[1] for call in calls if call.args[0] == "session:start"
        )
        await handler("session:start", {})

        # list_models() was called once (no preresolved data)
        mock_provider.list_models.assert_called_once()

        # register_capability must have been called with preresolved_models populated
        register_calls = coordinator.register_capability.call_args_list
        routing_updates = [c for c in register_calls if c.args[0] == "session.routing"]
        assert len(routing_updates) == 1, (
            "on_session_start must write preresolved_models back to session.routing"
        )
        written = routing_updates[0].args[1]
        assert "preresolved_models" in written
        assert "anthropic" in written["preresolved_models"]
        assert written["preresolved_models"]["anthropic"] == models
