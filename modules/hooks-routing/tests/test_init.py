"""Tests for hooks-routing mount() and hook handlers."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_on_session_start_includes_config_in_preferences(
        self, tmp_path: Path
    ) -> None:
        """Resolved preferences should include config from matrix candidates."""
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            name: balanced
            description: "Test"
            updated: "2026-01-01"
            roles:
              coding:
                description: "Code generation"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-6
                    config:
                      reasoning_effort: high
        """)
        (routing_dir / "balanced.yaml").write_text(content)

        agents: dict[str, Any] = {"coder": {"model_role": "coding"}}
        providers = {"provider-anthropic": MagicMock()}
        coordinator = _make_coordinator(providers=providers, agents=agents)

        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )

        # Extract and invoke the session:start handler
        calls = coordinator.hooks.register.call_args_list
        session_start_handler = None
        for call in calls:
            if call.args[0] == "session:start":
                session_start_handler = call.args[1]
                break
        assert session_start_handler is not None

        await session_start_handler("session:start", {})

        # provider_preferences must include config from the candidate
        prefs: list[Any] = agents["coder"]["provider_preferences"]
        assert len(prefs) == 1
        assert prefs[0]["provider"] == "anthropic"
        assert prefs[0]["model"] == "claude-sonnet-4-6"
        assert prefs[0]["config"] == {"reasoning_effort": "high"}


class TestCustomMatrixFallback:
    @pytest.mark.asyncio
    async def test_mount_loads_custom_matrix_from_user_dir(
        self, tmp_path: Path
    ) -> None:
        """mount() falls back to ~/.amplifier/routing/ for custom matrices not in bundle."""
        # Bundle root has no balanced-custom.yaml — simulates the cache dir
        bundle_root = tmp_path / "bundle"
        (bundle_root / "routing").mkdir(parents=True)
        # (intentionally do NOT write balanced-custom.yaml in bundle routing dir)

        # Custom matrix lives in the user's ~/.amplifier/routing/
        custom_dir = tmp_path / "home" / ".amplifier" / "routing"
        custom_dir.mkdir(parents=True)
        custom_content = textwrap.dedent("""\
            name: balanced-custom
            description: "My custom matrix"
            updated: "2026-03-07"
            roles:
              general:
                description: "Custom general"
                candidates:
                  - provider: anthropic
                    model: claude-opus-4-6
        """)
        (custom_dir / "balanced-custom.yaml").write_text(custom_content)

        coordinator = _make_coordinator()

        # Patch Path.home() so the module finds our fake home dir
        with patch(
            "amplifier_module_hooks_routing.Path.home",
            return_value=tmp_path / "home",
        ):
            await mount(
                coordinator,
                config={
                    "default_matrix": "balanced-custom",
                    "_bundle_root": str(bundle_root),
                },
            )

        # Session state must be populated — routing was NOT disabled
        assert "routing_matrix" in coordinator.session_state
        assert coordinator.session_state["routing_matrix"]["name"] == "balanced-custom"
        assert "general" in coordinator.session_state["routing_matrix"]["roles"]

    @pytest.mark.asyncio
    async def test_mount_prefers_user_dir_over_bundle_matrix(
        self, tmp_path: Path
    ) -> None:
        """User custom dir (~/.amplifier/routing/) takes priority over bundle cache."""
        # Bundle has the matrix
        bundle_root = tmp_path / "bundle"
        routing_dir = bundle_root / "routing"
        routing_dir.mkdir(parents=True)
        bundle_content = textwrap.dedent("""            name: balanced
            description: "Bundle balanced"
            updated: "2026-01-01"
            roles:
              general:
                description: "From bundle"
                candidates:
                  - provider: openai
                    model: gpt-4o
        """)
        (routing_dir / "balanced.yaml").write_text(bundle_content)

        # User dir also has a "balanced.yaml" — should be used (user wins)
        custom_dir = tmp_path / "home" / ".amplifier" / "routing"
        custom_dir.mkdir(parents=True)
        user_content = textwrap.dedent("""            name: balanced
            description: "User balanced"
            updated: "2026-01-01"
            roles:
              general:
                description: "From user dir"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-4-6
        """)
        (custom_dir / "balanced.yaml").write_text(user_content)

        coordinator = _make_coordinator()

        with patch(
            "amplifier_module_hooks_routing.Path.home",
            return_value=tmp_path / "home",
        ):
            await mount(
                coordinator,
                config={
                    "default_matrix": "balanced",
                    "_bundle_root": str(bundle_root),
                },
            )

        # User custom dir should win over bundle cache
        stored = coordinator.session_state["routing_matrix"]
        assert stored["roles"]["general"]["candidates"][0]["provider"] == "anthropic"

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
