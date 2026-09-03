"""hooks-routing must run on a RESUMED ROOT session (model_performance-fde).

The kernel picks ONE lifecycle event per process, mutually exclusively
(``amplifier_core/session.py:151``)::

    event_base = SESSION_RESUME if self._is_resumed else SESSION_START

hooks-routing registered only on ``session:start``. So on a resumed ROOT session
-- every interactive ``amplifier`` resume and every multi-turn eval driver -- the
handler never fired, and with it went layer-B ``model_role`` resolution, the 74w
role-pin reassert and the ``routing:matrix-loaded`` telemetry.

MEASURED, committed captures, no new spend
------------------------------------------
``treatment-validation/20260903-h7n-knobanth/runs/h7n-armA-s3-01/.../sessions/
8e7ff193-2e16-4f8e-a1d5-d37bf9bfb7c1/events.jsonl`` -- a ROOT session driven over
five executions as separate resuming processes::

    session:start x1, session:resume x4, session:config x5, session:end x5

Corpus-wide (1462 ``events.jsonl`` files): 212 root sessions resumed across 1238
lifecycle legs; only 212 fired ``session:start``. **1026 legs (82.9%) ran with
this handler never invoked.**

THE TRAP THIS FILE ALSO PINS
----------------------------
"Register on both events, they are mutually exclusive" is TRUE of the kernel and
FALSE of production. A resumed DELEGATE child receives BOTH on the same bus,
~5ms apart: ``amplifier_app_cli/session_spawner.py:1763-1774`` emits its own
observability ``session:resume`` on the child coordinator's hooks bus, and the
reconstructed child session (``is_resumed=False``) then emits the kernel
``session:start``. Measured order, capture ``20260830-dialin/runs/
val-dial-oai-budget-s1-02/.../0000000000000000-dc081e8b5a0b43c3_anchors-amp-dev-git-ops``::

    fork, start, config, end, fork, resume, START, config, end, fork, resume, START, ...

So the naive fix would have double-resolved and double-emitted
``routing:matrix-loaded`` on every delegate resume leg. The discriminator is the
``turn_count`` key, which only the spawner's payload carries: 102/102 delegate
resume payloads have it, 1029/1029 kernel root-resume payloads do not (n=1131,
100% separation).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_hooks_routing import mount

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeProvider:
    """Provider shaped the way ``_select_provider`` reads one.

    Deliberately not a MagicMock: ``_select_provider`` probes
    ``hasattr(provider, "priority")`` first and a MagicMock answers True to
    everything, which would make the priority surface untestable.
    """

    def __init__(self, name: str, priority: int, model: str) -> None:
        self.name = name
        self.config: dict[str, Any] = {"priority": priority, "default_model": model}
        # resolve_model_role() asks each candidate provider what it can serve.
        self.list_models = AsyncMock(return_value=[model])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FakeProvider({self.name!r}, priority={self.config['priority']})"


def _priority_winner(providers: dict[str, FakeProvider]) -> str:
    """Mirror of loop-streaming._select_provider's unpinned ordering."""
    return min(providers.items(), key=lambda kv: kv[1].config.get("priority", 100))[0]


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


def _make_coordinator(
    providers: dict[str, Any],
    *,
    own_prefs: list | None = None,
    agents: dict[str, Any] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Coordinator plus the hooks bus ``coordinator.get("hooks")`` resolves to."""
    coordinator = MagicMock()
    coordinator.session_state = {}

    bus = MagicMock()
    bus.emit = AsyncMock()

    def _get(key: str) -> Any:
        if key == "hooks":
            return bus
        if key == "context":
            return None
        return providers

    coordinator.get = MagicMock(side_effect=_get)
    coordinator.config = {"agents": agents if agents is not None else {}}
    if own_prefs is not None:
        coordinator.config["provider_preferences"] = own_prefs
    coordinator.get_capability = MagicMock(return_value=None)
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    return coordinator, bus


def _captured_providers() -> dict[str, FakeProvider]:
    """The 74w capture's RESUMED-leg mount plan, priorities verbatim."""
    return {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
        "luna": FakeProvider("luna", 14, "gpt-5.6-luna"),
    }


def _handler_for(coordinator: MagicMock, event: str) -> Any:
    """The handler hooks-routing registered for ``event``.

    Fails with a readable message rather than a bare StopIteration when the
    event was never registered -- which is exactly the pre-fix state.
    """
    for call in coordinator.hooks.register.call_args_list:
        if call.args[0] == event:
            return call.args[1]
    registered = sorted({c.args[0] for c in coordinator.hooks.register.call_args_list})
    raise AssertionError(
        f"hooks-routing registered no handler for {event!r}. Registered: {registered}. "
        "A resumed ROOT session emits session:resume INSTEAD of session:start "
        "(amplifier_core/session.py:151), so nothing in on_session_start runs."
    )


async def _mount(coordinator: MagicMock, tmp_path: Path) -> None:
    # `custom_routing_dirs` is the key mount() actually reads (__init__.py:94).
    await mount(coordinator, {"custom_routing_dirs": [str(_write_matrix(tmp_path))]})


# ---------------------------------------------------------------------------
# THE GATE -- these fail before the fix, pass after.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mount_registers_the_resume_lifecycle_event(tmp_path: Path) -> None:
    """Without a session:resume registration, a root resume routes on nothing."""
    coordinator, _bus = _make_coordinator(_captured_providers())
    await _mount(coordinator, tmp_path)

    registered = {c.args[0] for c in coordinator.hooks.register.call_args_list}
    assert "session:resume" in registered, (
        "hooks-routing must handle the lifecycle event a RESUMED ROOT session "
        f"actually emits. Registered: {sorted(registered)}"
    )
    # Same callable on both legs on purpose -- they must not drift apart.
    assert _handler_for(coordinator, "session:resume") is _handler_for(
        coordinator, "session:start"
    )


@pytest.mark.asyncio
async def test_resume_only_lifecycle_resolves_agent_model_role(
    tmp_path: Path,
) -> None:
    """Layer B on a resume-only leg: the deliverable's decisive assertion."""
    agents = {"scout": {"model_role": "fast"}}
    coordinator, _bus = _make_coordinator(_captured_providers(), agents=agents)
    await _mount(coordinator, tmp_path)

    # A resumed ROOT session's ONLY lifecycle event. No session:start ever fires.
    await _handler_for(coordinator, "session:resume")("session:resume", {})

    assert "provider_preferences" in agents["scout"], (
        "a resumed root session left every agent's declared model_role "
        "unresolved (n_prefs: 0), so each was routed by session default"
    )
    assert agents["scout"]["provider_preferences"][0]["provider"] == "luna"
    assert agents["scout"]["provider_preferences"][0]["model"] == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_resume_only_lifecycle_reasserts_role_pin(tmp_path: Path) -> None:
    """The 74w reassert on the leg its own docstring claimed to cover."""
    providers = _captured_providers()
    coordinator, bus = _make_coordinator(
        providers,
        own_prefs=[
            {
                "provider": "luna",
                "model": "gpt-5.6-luna",
                "config": {"reasoning_effort": "high"},
            }
        ],
    )
    await _mount(coordinator, tmp_path)

    # Precondition: this IS the captured broken state.
    assert _priority_winner(providers) == "sol"

    await _handler_for(coordinator, "session:resume")("session:resume", {})

    assert _priority_winner(providers) == "luna", (
        "a resumed root session resolved to "
        f"{_priority_winner(providers)!r} despite its own config pinning 'luna'. "
        f"priorities: { {n: p.config['priority'] for n, p in providers.items()} }"
    )
    # A silent correction would repeat the defect's own failure mode.
    assert "routing:role-pin-reasserted" in [c.args[0] for c in bus.emit.call_args_list]


@pytest.mark.asyncio
async def test_resume_only_lifecycle_emits_matrix_source_telemetry(
    tmp_path: Path,
) -> None:
    """routing:matrix-loaded is the forensic record; a resume must not lose it."""
    coordinator, bus = _make_coordinator(_captured_providers())
    await _mount(coordinator, tmp_path)

    await _handler_for(coordinator, "session:resume")("session:resume", {})

    emitted = [c.args[0] for c in bus.emit.call_args_list]
    assert emitted.count("routing:matrix-loaded") == 1, emitted


# ---------------------------------------------------------------------------
# The session:start leg must stay byte-identical -- proven, not asserted.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kernel_emits_exactly_one_lifecycle_event_per_process() -> None:
    """The kernel's either/or, exercised against the SHIPPED code -- not mocked.

    ``amplifier_core/session.py:151`` picks SESSION_RESUME xor SESSION_START, and
    ``_lifecycle_event_emitted`` fires it once per session object rather than once
    per ``execute()``. Both properties are load-bearing for "no double run", so
    both are executed here rather than taken on trust. ``execute()`` raises
    ``RuntimeError('No orchestrator module mounted')`` immediately AFTER the
    lifecycle emit, which is what makes this observable without mounting a
    provider or spending anything.
    """
    session_mod = pytest.importorskip("amplifier_core.session")
    AmplifierSession = session_mod.AmplifierSession

    config = {"session": {"orchestrator": {"module": "x"}, "context": {"module": "y"}}}

    async def _observe(is_resumed: bool) -> list[str]:
        session = AmplifierSession(config=dict(config), is_resumed=is_resumed)
        seen: list[str] = []

        async def handler(event: str, data: dict[str, Any]) -> None:
            seen.append(event)
            return None

        session.coordinator.hooks.register(
            "session:start", handler, priority=5, name="probe-start"
        )
        session.coordinator.hooks.register(
            "session:resume", handler, priority=5, name="probe-resume"
        )
        # Skip real module loading; the lifecycle emit does not depend on it.
        session._initialized = True
        for _ in range(3):  # three turns on one process
            with pytest.raises(RuntimeError):
                await session.execute("hi")
        return seen

    assert await _observe(is_resumed=False) == ["session:start"]
    assert await _observe(is_resumed=True) == ["session:resume"]


@pytest.mark.asyncio
async def test_session_start_leg_is_unchanged(tmp_path: Path) -> None:
    """A new (non-resumed) session: one resolution, one telemetry emit."""
    agents = {"scout": {"model_role": "fast"}}
    providers = _captured_providers()
    coordinator, bus = _make_coordinator(
        providers,
        agents=agents,
        own_prefs=[{"provider": "luna", "model": "gpt-5.6-luna"}],
    )
    await _mount(coordinator, tmp_path)

    await _handler_for(coordinator, "session:start")("session:start", {})

    emitted = [c.args[0] for c in bus.emit.call_args_list]
    assert emitted.count("routing:matrix-loaded") == 1, emitted
    assert agents["scout"]["provider_preferences"] == [
        {"provider": "luna", "model": "gpt-5.6-luna"}
    ]
    assert _priority_winner(providers) == "luna"


@pytest.mark.asyncio
async def test_delegate_resume_leg_runs_once_and_still_at_session_start(
    tmp_path: Path,
) -> None:
    """The production sequence that the naive fix would have double-run.

    ``fork -> resume(turn_count) -> START`` -- both events reach the same bus.
    The spawner's observability emit must be ignored, so the delegate leg runs at
    ``session:start`` exactly where it ran before this change, exactly once.
    """
    agents = {"scout": {"model_role": "fast"}}
    coordinator, bus = _make_coordinator(_captured_providers(), agents=agents)
    await _mount(coordinator, tmp_path)

    spawner_payload = {
        "session_id": "0000000000000000-dc081e8b5a0b43c3_anchors-amp-dev-git-ops",
        "parent_id": "20d86f3e-444a-4f5c-9632-18318304faba",
        "agent_name": "anchors-amp-dev:git-ops",
        "turn_count": 25,
    }

    await _handler_for(coordinator, "session:resume")("session:resume", spawner_payload)

    assert "provider_preferences" not in agents["scout"], (
        "the spawner's observability session:resume must not trigger resolution "
        "-- the kernel's session:start follows ~5ms later on this same leg"
    )
    assert [c.args[0] for c in bus.emit.call_args_list] == []

    # ... and then the kernel event arrives, doing the work exactly as before.
    await _handler_for(coordinator, "session:start")("session:start", {})

    emitted = [c.args[0] for c in bus.emit.call_args_list]
    assert emitted.count("routing:matrix-loaded") == 1, emitted
    assert agents["scout"]["provider_preferences"][0]["provider"] == "luna"


@pytest.mark.asyncio
async def test_two_kernel_shaped_lifecycle_events_cannot_double_resolve(
    tmp_path: Path,
) -> None:
    """Hard latch: correctness must not rest on another package's emit count.

    The ``turn_count`` discriminator covers today's known second emitter. The
    latch covers the one nobody has written yet.
    """
    agents = {"scout": {"model_role": "fast"}}
    coordinator, bus = _make_coordinator(_captured_providers(), agents=agents)
    await _mount(coordinator, tmp_path)

    await _handler_for(coordinator, "session:resume")("session:resume", {})
    await _handler_for(coordinator, "session:start")("session:start", {})
    await _handler_for(coordinator, "session:resume")("session:resume", {})

    emitted = [c.args[0] for c in bus.emit.call_args_list]
    assert emitted.count("routing:matrix-loaded") == 1, (
        f"duplicate routing:matrix-loaded telemetry: {emitted}"
    )
    assert agents["scout"]["provider_preferences"] == [
        {"provider": "luna", "model": "gpt-5.6-luna"}
    ]
