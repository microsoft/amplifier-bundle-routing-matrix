"""A session's own model_role pin must survive a RESUME (model_performance-74w).

Captured defect: a delegate spawned with ``model_role: fast`` resolved to
luna@high and ran 13 requests, then was resumed -- and the resumed leg ran 25
requests on sol@xhigh, the most expensive cell in the fleet. The session config
still carried ``provider_preferences=[luna]`` on BOTH legs; only the *mount
plan* lost the promotion, because the resume path re-imposes the settings-level
``priority`` over the child's promoted plan (upstream: model_performance-rc0).

``loop-streaming._select_provider`` reads ``priority`` off the LIVE provider
objects on every request, so hooks-routing can restore the promotion at
``session:start`` -- which fires on the resumed leg, before the first resolve.

Capture: 20260901-rebaseline/runs/val-rb-oai-sol-xhigh-s1-01
         .../0000000000000000-25443a97b60d4965_anchors-amp-dev-git-ops
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from amplifier_module_hooks_routing import mount


class FakeProvider:
    """Provider instance shaped the way ``_select_provider`` reads one.

    Deliberately NOT a MagicMock: ``_select_provider`` probes
    ``hasattr(provider, "priority")`` first, and a MagicMock answers True to
    every attribute, which would make the priority surface untestable.
    """

    def __init__(self, name: str, priority: int, model: str) -> None:
        self.name = name
        self.config: dict[str, Any] = {"priority": priority, "default_model": model}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FakeProvider({self.name!r}, priority={self.config['priority']})"


def _priority_winner(providers: dict[str, FakeProvider]) -> str:
    """Mirror of loop-streaming._select_provider's unpinned ordering."""
    return min(providers.items(), key=lambda kv: kv[1].config.get("priority", 100))[0]


def _captured_providers() -> dict[str, FakeProvider]:
    """The RESUMED leg's mount plan, priorities verbatim from the capture."""
    return {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
        "luna": FakeProvider("luna", 14, "gpt-5.6-luna"),
    }


def _write_matrix(tmp_path: Path) -> Path:
    routing_dir = tmp_path / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)
    (routing_dir / "balanced.yaml").write_text(
        textwrap.dedent("""\
        name: balanced
        description: "Test matrix"
        updated: "2026-01-01"

        roles:
          general:
            description: "General purpose"
            candidates:
              - provider: sol
                model: gpt-5.6-sol
          fast:
            description: "Fast tasks"
            candidates:
              - provider: luna
                model: gpt-5.6-luna
        """)
    )
    return routing_dir


def _make_coordinator(providers: dict[str, Any], own_prefs: list | None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.session_state = {}

    def _get(key: str) -> Any:
        if key == "context":
            return None
        return providers

    coordinator.get = MagicMock(side_effect=_get)
    coordinator.config = {"agents": {}}
    if own_prefs is not None:
        coordinator.config["provider_preferences"] = own_prefs
    coordinator.get_capability = MagicMock(return_value=None)
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    coordinator.hooks.emit = MagicMock()
    return coordinator


async def _fire_session_start(coordinator: MagicMock, tmp_path: Path) -> None:
    await mount(coordinator, {"routing_dirs": [str(_write_matrix(tmp_path))]})
    handlers = [
        call.args[1]
        for call in coordinator.hooks.register.call_args_list
        if call.args[0] == "session:start"
    ]
    assert handlers, "hooks-routing must register a session:start handler"
    await handlers[0]("session:start", {})


# ---------------------------------------------------------------------------
# THE GATE -- fails before the fix, passes after.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resumed_session_reasserts_its_own_role_pin(tmp_path: Path) -> None:
    """The captured 25/38 fall-through, reduced to its decisive assertion."""
    providers = _captured_providers()
    coordinator = _make_coordinator(
        providers,
        own_prefs=[{"provider": "luna", "model": "gpt-5.6-luna",
                    "config": {"reasoning_effort": "high"}}],
    )

    # Precondition: this IS the captured broken state.
    assert _priority_winner(providers) == "sol"

    await _fire_session_start(coordinator, tmp_path)

    assert _priority_winner(providers) == "luna", (
        "session:start left the resumed session resolving to "
        f"{_priority_winner(providers)!r} despite its own config pinning 'luna'. "
        f"priorities: { {n: p.config['priority'] for n, p in providers.items()} }"
    )


# ---------------------------------------------------------------------------
# Default-safety: the no-op paths must stay byte-identical.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_pin_declared_is_untouched(tmp_path: Path) -> None:
    """A session with no role pin of its own must not be reordered."""
    providers = _captured_providers()
    before = {n: p.config["priority"] for n, p in providers.items()}
    coordinator = _make_coordinator(providers, own_prefs=None)

    await _fire_session_start(coordinator, tmp_path)

    assert {n: p.config["priority"] for n, p in providers.items()} == before


@pytest.mark.asyncio
async def test_freshly_spawned_session_is_untouched(tmp_path: Path) -> None:
    """The spawn leg already agrees with its pin -- nothing to correct."""
    providers = {
        "sol": FakeProvider("sol", 1, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
        "luna": FakeProvider("luna", 0, "gpt-5.6-luna"),
    }
    before = {n: p.config["priority"] for n, p in providers.items()}
    coordinator = _make_coordinator(
        providers, own_prefs=[{"provider": "luna", "model": "gpt-5.6-luna"}]
    )

    await _fire_session_start(coordinator, tmp_path)

    assert {n: p.config["priority"] for n, p in providers.items()} == before


@pytest.mark.asyncio
async def test_pin_to_unmounted_provider_is_not_forced(tmp_path: Path) -> None:
    """Never invent a promotion for a provider this session cannot reach."""
    providers = {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
    }
    before = {n: p.config["priority"] for n, p in providers.items()}
    coordinator = _make_coordinator(
        providers, own_prefs=[{"provider": "luna", "model": "gpt-5.6-luna"}]
    )

    await _fire_session_start(coordinator, tmp_path)

    assert {n: p.config["priority"] for n, p in providers.items()} == before


@pytest.mark.asyncio
async def test_reassert_can_be_disabled(tmp_path: Path) -> None:
    """Operator escape hatch restores the pre-fix behaviour exactly."""
    providers = _captured_providers()
    before = {n: p.config["priority"] for n, p in providers.items()}
    coordinator = _make_coordinator(
        providers, own_prefs=[{"provider": "luna", "model": "gpt-5.6-luna"}]
    )

    await mount(
        coordinator,
        {"routing_dirs": [str(_write_matrix(tmp_path))], "reassert_role_pin": False},
    )
    handler = next(
        call.args[1]
        for call in coordinator.hooks.register.call_args_list
        if call.args[0] == "session:start"
    )
    await handler("session:start", {})

    assert {n: p.config["priority"] for n, p in providers.items()} == before


@pytest.mark.asyncio
async def test_correction_is_reported_not_silent(tmp_path: Path) -> None:
    """A silent correction would repeat the defect's own failure mode."""
    from unittest.mock import AsyncMock

    providers = _captured_providers()
    bus = MagicMock()
    bus.emit = AsyncMock()

    coordinator = _make_coordinator(
        providers, own_prefs=[{"provider": "luna", "model": "gpt-5.6-luna"}]
    )
    # Route coordinator.get("hooks") to a real bus; everything else unchanged.
    coordinator.get = MagicMock(
        side_effect=lambda key: bus
        if key == "hooks"
        else (None if key == "context" else providers)
    )

    await _fire_session_start(coordinator, tmp_path)

    events = [c.args[0] for c in bus.emit.call_args_list]
    assert "routing:role-pin-reasserted" in events, events
    record = next(
        c.args[1] for c in bus.emit.call_args_list
        if c.args[0] == "routing:role-pin-reasserted"
    )
    assert record["reasserted"] is True
    assert record["pinned_provider"] == "luna"
    assert record["would_have_resolved_to"] == "sol"
