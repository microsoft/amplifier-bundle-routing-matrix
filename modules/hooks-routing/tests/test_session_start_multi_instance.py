"""Layer B (agent-frontmatter ``model_role``) on a MULTI-INSTANCE provider install.

Background (model_performance-cly). Routing has two layers:

* **Layer A** -- a caller-supplied ``model_role`` on the delegate tool call,
  resolved parent-side through the ``model_role_resolver`` capability
  (:class:`resolver_class.MatrixModelRoleResolver`).
* **Layer B** -- an agent's OWN ``model_role`` declared in its frontmatter,
  resolved by this module's ``session:start`` handler, which writes
  ``provider_preferences`` back into ``coordinator.config["agents"][name]``
  for ``tool-delegate`` / ``session_spawner`` to read at spawn time
  (``amplifier-app-cli session_spawner.py:568-575``).

Both layers call :func:`resolver.resolve_model_role`, which asks
:func:`resolver.find_provider_by_type` whether a matrix candidate's bare
``provider:`` type (e.g. ``"anthropic"``) is installed. That function has two
strategies:

1. direct key match against the mounted ``providers`` dict, and
2. a **coordinator-backed fallback** for the multi-instance case, where every
   instance of a module is mounted under its own explicit ``id:`` and NONE is
   keyed by the bare type -- it reads ``coordinator.config["providers"]`` to
   map instance ids back to their module type.

Strategy 2 requires the ``coordinator`` argument. Layer A passes it
(``resolver_class.py:220``). Layer B did **not**, so on a multi-instance
install every candidate failed to match, ``resolve_model_role`` returned
``[]``, and no ``provider_preferences`` was ever written -- agent-declared
``model_role`` was silently ignored and every spawned child fell back to the
session's default provider ordering.

Every pre-existing ``session:start`` test mounts providers keyed by the bare
type name (``{"openai": ...}``), which is exactly the case strategy 1 already
handles -- which is why this went unmeasured. These tests pin the
multi-instance case, and the single-instance case as an unchanged control.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_module_hooks_routing import mount

_MATRIX_YAML = """\
name: multi-instance-test
description: "Bare provider types, as every shipped matrix writes them"
updated: "2026-09-03"

roles:
  fast:
    description: "Fast tasks"
    candidates:
      - provider: anthropic
        model: claude-haiku-4-5
  reasoning:
    description: "Deep reasoning"
    candidates:
      - provider: anthropic
        model: claude-opus-5
        config:
          reasoning_effort: high
"""


def _write_matrix(tmp_path: Path) -> Path:
    routing = tmp_path / "routing"
    routing.mkdir(exist_ok=True)
    (routing / "mi.yaml").write_text(_MATRIX_YAML, encoding="utf-8")
    return tmp_path


def _provider() -> MagicMock:
    provider = MagicMock()
    provider.list_models = AsyncMock(
        return_value=["claude-opus-5", "claude-haiku-4-5"]
    )
    return provider


def _coordinator(
    agents: dict[str, Any],
    providers: dict[str, Any],
    provider_specs: list[dict[str, Any]],
) -> MagicMock:
    hooks_bus = MagicMock()
    hooks_bus.emit = AsyncMock()

    coordinator = MagicMock()

    def _get(key: str) -> Any:
        if key == "context":
            return None
        if key == "hooks":
            return hooks_bus
        return providers

    coordinator.get = MagicMock(side_effect=_get)
    coordinator.config = {"agents": agents, "providers": provider_specs}
    coordinator.get_capability = MagicMock(return_value=None)
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    coordinator.event_bus = hooks_bus
    return coordinator


async def _run_session_start(coordinator: MagicMock) -> None:
    handlers = [
        call.args[1]
        for call in coordinator.hooks.register.call_args_list
        if call.args[0] == "session:start"
    ]
    assert handlers, "session:start handler was not registered"
    await handlers[0]("session:start", {})


async def _mount_and_start(coordinator: MagicMock, root: Path) -> None:
    await mount(coordinator, {"default_matrix": "mi", "_bundle_root": str(root)})
    await _run_session_start(coordinator)


# ---------------------------------------------------------------------------
# The defect: multi-instance install, no provider keyed by the bare type
# ---------------------------------------------------------------------------


class TestMultiInstanceProviders:
    """Every instance mounted under its own ``id:``; none keyed "anthropic"."""

    @staticmethod
    def _specs() -> list[dict[str, Any]]:
        # Shape taken verbatim from the h7n arm-A capture's session:config
        # (treatment-validation/20260903-h7n-knobanth): provider-anthropic
        # mounted three times, each with an explicit id and default_model.
        return [
            {
                "module": "provider-anthropic",
                "id": "opus",
                "config": {"priority": 0, "default_model": "claude-opus-5"},
            },
            {
                "module": "provider-anthropic",
                "id": "haiku",
                "config": {"priority": 1, "default_model": "claude-haiku-4-5"},
            },
        ]

    @pytest.mark.asyncio
    async def test_agent_frontmatter_model_role_is_resolved(
        self, tmp_path: Path
    ) -> None:
        """The regression this test exists for.

        Before the fix this asserted-on key was absent entirely -- the exact
        ``n_prefs: 0`` seen for 11 of 13 agents in the h7n arm-A capture.
        """
        root = _write_matrix(tmp_path)
        agents = {"explorer": {"model_role": ["fast", "general"]}}
        providers = {"opus": _provider(), "haiku": _provider()}
        coordinator = _coordinator(agents, providers, self._specs())

        await _mount_and_start(coordinator, root)

        assert agents["explorer"]["provider_preferences"] == [
            {"provider": "haiku", "model": "claude-haiku-4-5"}
        ]

    @pytest.mark.asyncio
    async def test_every_declaring_agent_resolves_not_just_one(
        self, tmp_path: Path
    ) -> None:
        """Mirrors the capture's shape: many agents, all declaring roles."""
        root = _write_matrix(tmp_path)
        agents = {
            "architect": {"model_role": ["reasoning", "general"]},
            "explorer": {"model_role": ["fast", "general"]},
            "git-ops": {"model_role": "fast"},
        }
        providers = {"opus": _provider(), "haiku": _provider()}
        coordinator = _coordinator(agents, providers, self._specs())

        await _mount_and_start(coordinator, root)

        unresolved = [
            name for name, cfg in agents.items() if not cfg.get("provider_preferences")
        ]
        assert unresolved == [], (
            f"agents declared a model_role but resolved to nothing: {unresolved}"
        )
        assert agents["architect"]["provider_preferences"] == [
            {
                "provider": "opus",
                "model": "claude-opus-5",
                "config": {"reasoning_effort": "high"},
            }
        ]

    @pytest.mark.asyncio
    async def test_candidate_config_block_survives(self, tmp_path: Path) -> None:
        """The matrix candidate's ``config:`` still rides the resolved pref."""
        root = _write_matrix(tmp_path)
        agents = {"architect": {"model_role": "reasoning"}}
        providers = {"opus": _provider(), "haiku": _provider()}
        coordinator = _coordinator(agents, providers, self._specs())

        await _mount_and_start(coordinator, root)

        pref = agents["architect"]["provider_preferences"][0]
        assert pref["config"] == {"reasoning_effort": "high"}


# ---------------------------------------------------------------------------
# Control: the single-instance (default) install is unchanged
# ---------------------------------------------------------------------------


class TestSingleInstanceUnchanged:
    """A provider keyed by its bare type resolves via strategy 1 as before."""

    @pytest.mark.asyncio
    async def test_bare_type_key_still_resolves(self, tmp_path: Path) -> None:
        root = _write_matrix(tmp_path)
        agents = {"explorer": {"model_role": ["fast", "general"]}}
        providers = {"anthropic": _provider()}
        coordinator = _coordinator(
            agents,
            providers,
            [{"module": "provider-anthropic", "config": {"priority": 0}}],
        )

        await _mount_and_start(coordinator, root)

        assert agents["explorer"]["provider_preferences"] == [
            {"provider": "anthropic", "model": "claude-haiku-4-5"}
        ]

    @pytest.mark.asyncio
    async def test_agent_without_model_role_is_untouched(self, tmp_path: Path) -> None:
        root = _write_matrix(tmp_path)
        agents: dict[str, Any] = {"plain": {}}
        providers = {"anthropic": _provider()}
        coordinator = _coordinator(
            agents,
            providers,
            [{"module": "provider-anthropic", "config": {"priority": 0}}],
        )

        await _mount_and_start(coordinator, root)

        assert agents["plain"] == {}

    @pytest.mark.asyncio
    async def test_unknown_role_resolves_to_nothing(self, tmp_path: Path) -> None:
        """A role absent from the matrix still writes no key (unchanged)."""
        root = _write_matrix(tmp_path)
        agents = {"odd": {"model_role": "not-a-role"}}
        providers = {"anthropic": _provider()}
        coordinator = _coordinator(
            agents,
            providers,
            [{"module": "provider-anthropic", "config": {"priority": 0}}],
        )

        await _mount_and_start(coordinator, root)

        assert "provider_preferences" not in agents["odd"]


# ---------------------------------------------------------------------------
# Layer A / Layer B parity -- the asymmetry that produced the defect
# ---------------------------------------------------------------------------


class TestLayerParity:
    @pytest.mark.asyncio
    async def test_capability_and_session_start_agree(self, tmp_path: Path) -> None:
        """Same matrix, same providers, same role -> same answer.

        Layer A (the ``model_role_resolver`` capability, used by tool-delegate
        when a CALLER passes ``model_role``) and layer B (this module's
        ``session:start`` handler, used for an agent's OWN declared role) must
        not disagree. They did: layer A forwarded the coordinator to
        ``find_provider_by_type`` and layer B did not, so on a multi-instance
        install layer A resolved and layer B returned nothing.
        """
        root = _write_matrix(tmp_path)
        agents = {"explorer": {"model_role": "fast"}}
        providers = {"opus": _provider(), "haiku": _provider()}
        coordinator = _coordinator(
            agents, providers, TestMultiInstanceProviders._specs()
        )

        await _mount_and_start(coordinator, root)

        resolver = None
        for call in coordinator.register_capability.call_args_list:
            if call.args and call.args[0] == "model_role_resolver":
                resolver = call.args[1]
        assert resolver is not None, "model_role_resolver capability not registered"

        layer_a = await resolver.resolve(["fast"])
        layer_b = agents["explorer"]["provider_preferences"]

        assert [(p.provider, p.model) for p in layer_a] == [
            (p["provider"], p["model"]) for p in layer_b
        ]
