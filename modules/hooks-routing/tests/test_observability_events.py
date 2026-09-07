"""This module's `routing:*` events must actually reach events.jsonl.

hooks-logging persists an event ONLY if it registered a handler for that name,
and it learns custom names from the `observability.events` capability (plus
`collect_contributions`) at on_session_ready. A module that emits without
declaring emits into a room hooks-logging never entered: the emit succeeds,
nothing is written, nobody is told.

Measured 2026-09-07 in a DTU: a session whose `delegate:agent_spawned` proved
routing had resolved (full provider_preferences) had ZERO `routing:*` lines in
its events.jsonl, while `skills:discovered` / `delegate:agent_spawned` /
`mentions:resolved` -- all declared by their modules -- landed fine.

Three properties are pinned here:
  1. mount() declares OBSERVABILITY_EVENTS on the capability, aggregating with
     (never clobbering) what other modules already declared.
  2. OBSERVABILITY_EVENTS is exactly the set of event names this module's
     source emits -- a new `.emit("routing:...")` without a matching entry
     fails, and a stale entry with no emitter fails.
  3. A coordinator without the capability API still mounts: observability
     never breaks the thing it observes.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from amplifier_module_hooks_routing import (
    OBSERVABILITY_EVENTS,
    _declare_observability_events,
    mount,
)

MODULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "amplifier_module_hooks_routing"
    / "__init__.py"
).read_text(encoding="utf-8")

# Every literal event name passed to an `.emit(` in this module's source.
_EMITTED = set(re.findall(r'\.emit\(\s*"(routing:[a-z0-9_:-]+)"', MODULE_SOURCE))


def _coordinator(*, declared_already: list[str] | None = None) -> MagicMock:
    """A coordinator that follows the real capability API, with an optional
    pre-existing `observability.events` list from an earlier module."""
    c = MagicMock()
    c.session_state = {}
    c.get = MagicMock(return_value={})
    c.config = {"agents": {}}
    caps: dict[str, object] = {}
    if declared_already is not None:
        caps["observability.events"] = list(declared_already)
    c.get_capability = MagicMock(side_effect=lambda name: caps.get(name))
    c.register_capability = MagicMock(side_effect=caps.__setitem__)
    c.hooks = MagicMock()
    c.hooks.register = MagicMock()
    c._caps = caps
    return c


def test_catalogue_matches_every_emit_in_the_source() -> None:
    """Both directions: no undeclared emit, no declared-but-never-emitted name."""
    assert _EMITTED, "regex found no .emit(\"routing:...\") calls -- check the pattern"
    assert set(OBSERVABILITY_EVENTS) == _EMITTED, (
        f"OBSERVABILITY_EVENTS {sorted(OBSERVABILITY_EVENTS)} != emitted "
        f"{sorted(_EMITTED)}. Add the new event to the tuple (or remove the "
        "stale one) -- an undeclared event is emitted but never persisted."
    )


def test_mount_declares_the_catalogue_on_the_capability() -> None:
    c = _coordinator()
    asyncio.run(mount(c, {}))
    declared = c._caps.get("observability.events")
    assert declared is not None, "mount() never registered observability.events"
    for event in OBSERVABILITY_EVENTS:
        assert event in declared


def test_declaration_aggregates_and_never_clobbers_other_modules() -> None:
    """tool-task / tool-skills declared first; ours must be ADDED to theirs.

    `register_capability` REPLACES the value, so a module that registers only
    its own list silently deletes every other module's events from the
    channel -- and hooks-logging would then stop persisting THEIR telemetry.
    """
    others = ["task:agent_spawned", "skills:discovered"]
    c = _coordinator(declared_already=others)
    _declare_observability_events(c)
    declared = c._caps["observability.events"]
    for event in others:
        assert event in declared, f"clobbered another module's event {event!r}"
    for event in OBSERVABILITY_EVENTS:
        assert event in declared


def test_declaration_is_idempotent() -> None:
    """Mounting twice (or another instance of this module) must not duplicate
    names -- hooks-logging dedupes, but the channel itself should stay clean."""
    c = _coordinator()
    _declare_observability_events(c)
    _declare_observability_events(c)
    declared = c._caps["observability.events"]
    assert len(declared) == len(set(declared))
    assert sorted(declared) == sorted(OBSERVABILITY_EVENTS)


def test_coordinator_without_capability_api_still_mounts() -> None:
    """Observability must never break routing on an older kernel."""
    c = MagicMock(spec=["session_state", "get", "config", "hooks"])
    c.session_state = {}
    c.get = MagicMock(return_value={})
    c.config = {"agents": {}}
    c.hooks = MagicMock()
    c.hooks.register = MagicMock()
    assert not hasattr(c, "register_capability")
    asyncio.run(mount(c, {}))  # must not raise
    assert c.hooks.register.called, "routing hooks were not registered"


@pytest.mark.parametrize("event", OBSERVABILITY_EVENTS)
def test_every_declared_event_is_namespaced_under_routing(event: str) -> None:
    """The `routing:` prefix is how the CLI's log tooling and the DTU probes
    find this module's telemetry; a stray name would be persisted but lost."""
    assert event.startswith("routing:")
