"""The re-asserted pin must be the SAME pin spawn applied (model_performance-j8v).

74w established that a session's own ``model_role`` pin is lost across a RESUME
and can be restored at ``session:start``. Reviewing that fix for publication
(lane e6e) found it restored only PART of what spawn applied, so a restored
session could come back on the right provider with the wrong model, or not come
back at all:

GAP 1 -- ``_apply_single_override`` enforces TWO invariants on the promoted
provider, ``config["priority"] = 0`` (spawn_utils.py:772) AND
``config["default_model"] = model`` (spawn_utils.py:773), plus the preference's
own ``config`` block minus ``PROTECTED_CONFIG_KEYS`` (spawn_utils.py:767-770).
role_pin restored only ``priority``. A pin naming a non-default model of a
mounted provider therefore resolved to the right provider at the WRONG model,
silently.

GAP 2 -- ``apply_provider_preferences`` walks the whole ordered preference list
and applies the FIRST entry that is mounted (spawn_utils.py:713-718). role_pin
read ``provider_preferences[0]`` unconditionally, so a spawn whose entry 0 was
unmounted and entry 1 was mounted got a loud no-op where spawn would have
promoted entry 1.

GAP 3 (same class, found while closing gap 2) -- a preference names a provider
by module id, with ``provider-`` stripped, or with it added
(``_build_provider_lookup``, spawn_utils.py:649-675). role_pin tested ``target
not in providers``, so a pin saying ``"openai"`` missed a provider mounted as
``"provider-openai"`` entirely.

Every test below marked GATE fails on ``lane/74w-fast-role-fallthrough`` @
88a62eb and passes after. This remains defense in depth: the root cause is the
resume path re-imposing settings priority over a child's promoted mount plan,
owned upstream in amplifier-app-cli (lane n1i, PR #292; model_performance-rc0).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from amplifier_module_hooks_routing import mount
from amplifier_module_hooks_routing.role_pin import (
    _PROTECTED_CONFIG_KEYS_FALLBACK,
    _match_mounted,
    _protected_config_keys,
    reassert_own_role_pin,
)


class FakeProvider:
    """Provider shaped the way ``_select_provider`` reads one: config only.

    Deliberately NOT a MagicMock: the module probes ``hasattr(provider, ...)``
    to find its read surface, and a MagicMock answers True to every attribute,
    which would make the surface distinction untestable.
    """

    def __init__(self, name: str, priority: int, model: str, **config: Any) -> None:
        self.name = name
        self.config: dict[str, Any] = {
            "priority": priority,
            "default_model": model,
            **config,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FakeProvider({self.name!r}, priority={self.config['priority']})"


class FakeAttrProvider(FakeProvider):
    """A live provider: the attribute is what a request actually reads.

    ``provider-openai/__init__.py:1026`` snapshots ``config["default_model"]``
    into ``self.default_model`` at construction, and serves every request from
    ``kwargs.get("model", self.default_model)`` (``:2040``). Restoring only the
    config dict on an object like this changes nothing that gets sent.
    """

    def __init__(self, name: str, priority: int, model: str, **config: Any) -> None:
        super().__init__(name, priority, model, **config)
        self.priority = priority
        self.default_model = model


def _coordinator(providers: dict[str, Any], prefs: list | None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.session_state = {}

    def _get(key: str) -> Any:
        if key == "context":
            return None
        return providers

    coordinator.get = MagicMock(side_effect=_get)
    coordinator.config = {"agents": {}}
    if prefs is not None:
        coordinator.config["provider_preferences"] = prefs
    coordinator.get_capability = MagicMock(return_value=None)
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    coordinator.hooks.emit = MagicMock()
    return coordinator


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


async def _fire_session_start(coordinator: MagicMock, tmp_path: Path) -> None:
    """Drive the real hook, not the helper -- the wiring is part of the claim."""
    await mount(coordinator, {"routing_dirs": [str(_write_matrix(tmp_path))]})
    handlers = [
        call.args[1]
        for call in coordinator.hooks.register.call_args_list
        if call.args[0] == "session:start"
    ]
    assert handlers, "hooks-routing must register a session:start handler"
    await handlers[0]("session:start", {})


def _priorities(providers: dict[str, FakeProvider]) -> dict[str, int]:
    return {n: p.config["priority"] for n, p in providers.items()}


def _priority_winner(providers: dict[str, FakeProvider]) -> str:
    """Mirror of loop-streaming._select_provider's unpinned ordering."""
    return min(providers.items(), key=lambda kv: kv[1].config.get("priority", 100))[0]


# ---------------------------------------------------------------------------
# GAP 1 -- the pin is more than `priority`.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_pinned_model_is_restored_when_provider_already_wins(
    tmp_path: Path,
) -> None:
    """GATE. Right provider, wrong model is the silent half-restore.

    This is the acceptance criterion verbatim: a mounted provider whose
    ``default_model`` is NOT the pinned model. Pre-j8v role_pin returned early
    on ``winner == target`` and never looked at the model at all.
    """
    providers = {
        "sol": FakeAttrProvider("sol", 5, "gpt-5.6-sol"),
        "luna": FakeAttrProvider("luna", 0, "gpt-5.6-luna"),
    }
    coordinator = _coordinator(
        providers,
        [{"provider": "luna", "model": "gpt-5.6-luna-preview"}],
    )

    # Precondition: the provider ordering is already correct...
    assert _priority_winner(providers) == "luna"
    # ...and the model is not.
    assert providers["luna"].default_model == "gpt-5.6-luna"

    await _fire_session_start(coordinator, tmp_path)

    assert providers["luna"].default_model == "gpt-5.6-luna-preview", (
        "session:start restored the pinned PROVIDER but left it serving "
        f"{providers['luna'].default_model!r}; the session pinned "
        "'gpt-5.6-luna-preview'."
    )
    # Both surfaces agree afterwards -- config is what a mount inspection reads.
    assert providers["luna"].config["default_model"] == "gpt-5.6-luna-preview"
    # And the correct ordering was not disturbed to get there.
    assert _priorities(providers) == {"sol": 5, "luna": 0}


@pytest.mark.asyncio
async def test_gate_priority_and_model_restored_together(tmp_path: Path) -> None:
    """GATE. The 74w capture, with a pin whose model also drifted."""
    providers = {
        "sol": FakeAttrProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeAttrProvider("terra", 2, "gpt-5.6-terra"),
        "luna": FakeAttrProvider("luna", 14, "gpt-5.6-luna"),
    }
    coordinator = _coordinator(
        providers, [{"provider": "luna", "model": "gpt-5.6-luna-preview"}]
    )

    await _fire_session_start(coordinator, tmp_path)

    assert _priority_winner(providers) == "luna"
    assert providers["luna"].default_model == "gpt-5.6-luna-preview"
    # Ties are pushed strictly below, exactly as _apply_single_override does.
    assert providers["sol"].config["priority"] == 1
    # A non-tying provider is left alone.
    assert providers["terra"].config["priority"] == 2
    # Nobody else's model is touched -- _apply_single_override sets
    # default_model on the TARGET only (spawn_utils.py:773).
    assert providers["sol"].default_model == "gpt-5.6-sol"
    assert providers["terra"].default_model == "gpt-5.6-terra"


def test_gate_model_restored_on_the_surface_a_request_reads() -> None:
    """GATE. A config-only write does not change what a live provider sends."""
    providers = {"luna": FakeAttrProvider("luna", 0, "gpt-5.6-luna")}
    coordinator = _coordinator(
        providers, [{"provider": "luna", "model": "gpt-5.6-luna-preview"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None and record["model_reasserted"] is True
    assert record["model_before"] == "gpt-5.6-luna"
    assert record["model_after"] == "gpt-5.6-luna-preview"
    # The attribute is the surface `kwargs.get("model", self.default_model)`
    # reads. If only the dict moved, this assertion is the one that catches it.
    assert providers["luna"].default_model == "gpt-5.6-luna-preview"


def test_gate_preference_config_keys_are_restored() -> None:
    """GATE. `_apply_single_override` merges pref.config (spawn_utils.py:767)."""
    providers = {"luna": FakeProvider("luna", 0, "gpt-5.6-luna", reasoning_effort="low")}
    coordinator = _coordinator(
        providers,
        [
            {
                "provider": "luna",
                "model": "gpt-5.6-luna",
                "config": {"reasoning_effort": "high", "temperature": 0.3},
            }
        ],
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert providers["luna"].config["reasoning_effort"] == "high"
    assert providers["luna"].config["temperature"] == 0.3
    assert record["config_keys_reasserted"] == ["reasoning_effort", "temperature"]


def test_protected_config_keys_are_never_restored() -> None:
    """Credentials and endpoints are the one thing a preference may not move."""
    providers = {
        "luna": FakeProvider("luna", 0, "gpt-5.6-luna", base_url="https://real.invalid")
    }
    coordinator = _coordinator(
        providers,
        [
            {
                "provider": "luna",
                "model": "gpt-5.6-luna",
                "config": {
                    "base_url": "https://attacker.invalid",
                    "api_key": "leaked",
                    "reasoning_effort": "high",
                },
            }
        ],
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert providers["luna"].config["base_url"] == "https://real.invalid"
    assert "api_key" not in providers["luna"].config
    assert record["config_keys_reasserted"] == ["reasoning_effort"]


def test_config_key_the_provider_baked_into_an_attribute_is_reported() -> None:
    """A restored key that cannot take must be named, not silently written.

    ``provider-openai`` runs ``config["reasoning_effort"]`` through a validator
    into ``self.reasoning_effort`` at ``__init__`` (``__init__.py:1046``).
    Re-running that validation would mean re-entering provider construction, so
    this layer restores the config and REPORTS the disagreement -- the same rule
    as the repo's "reject inert effort keys instead of dropping them silently".
    """
    provider = FakeProvider("luna", 0, "gpt-5.6-luna")
    provider.reasoning_effort = "low"  # type: ignore[attr-defined]
    providers = {"luna": provider}
    coordinator = _coordinator(
        providers,
        [
            {
                "provider": "luna",
                "model": "gpt-5.6-luna",
                "config": {"reasoning_effort": "high"},
            }
        ],
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["inert_config_keys"] == ["reasoning_effort"]
    # Config restored; the validated attribute left exactly as the provider set it.
    assert providers["luna"].config["reasoning_effort"] == "high"
    assert providers["luna"].reasoning_effort == "low"  # type: ignore[attr-defined]


def test_unresolved_glob_model_is_refused_not_written() -> None:
    """A pattern is not a model name; writing it would send the glob literally.

    ``apply_provider_preferences`` (no ``_with_resolution``) never resolves
    globs, so a persisted preference can still carry ``claude-haiku-*``.
    ``ModelResolutionResult`` (spawn_utils.py:342) exists specifically to warn
    that such a string must never be substituted for a real model.
    """
    providers = {
        "sol": FakeAttrProvider("sol", 0, "gpt-5.6-sol"),
        "luna": FakeAttrProvider("luna", 14, "gpt-5.6-luna"),
    }
    coordinator = _coordinator(providers, [{"provider": "luna", "model": "gpt-5.6-*"}])

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    # The provider promotion still happens -- that part is unambiguous.
    assert _priority_winner(providers) == "luna"
    # The model does not.
    assert providers["luna"].default_model == "gpt-5.6-luna"
    assert record["model_reasserted"] is False
    assert record["model_not_reasserted_reason"] == "model_is_unresolved_pattern"


# ---------------------------------------------------------------------------
# GAP 2 -- the whole preference list, not element 0.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_promotion_follows_the_first_mounted_preference(
    tmp_path: Path,
) -> None:
    """GATE. Acceptance criterion: entry 0 unmounted, entry 1 mounted.

    ``apply_provider_preferences`` would have promoted entry 1
    (spawn_utils.py:713-718). Pre-j8v role_pin read entry 0, found it unmounted,
    logged ``pinned_provider_not_mounted`` and did nothing.
    """
    providers = {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
        "luna": FakeProvider("luna", 14, "gpt-5.6-luna"),
    }
    coordinator = _coordinator(
        providers,
        [
            {"provider": "vertex", "model": "gemini-3-pro"},  # not mounted
            {"provider": "luna", "model": "gpt-5.6-luna"},  # mounted
        ],
    )

    assert _priority_winner(providers) == "sol"

    await _fire_session_start(coordinator, tmp_path)

    assert _priority_winner(providers) == "luna", (
        "entry 0 was unmounted, so the whole preference list was abandoned; "
        f"priorities: {_priorities(providers)}"
    )


def test_first_mounted_preference_wins_when_several_are_mounted() -> None:
    """Order still decides: the FIRST mounted entry, not the best-ranked one."""
    providers = {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
        "luna": FakeProvider("luna", 14, "gpt-5.6-luna"),
    }
    coordinator = _coordinator(
        providers,
        [
            {"provider": "luna", "model": "gpt-5.6-luna"},
            {"provider": "terra", "model": "gpt-5.6-terra"},
        ],
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "luna"
    assert record["preference_index"] == 0
    assert _priority_winner(providers) == "luna"


def test_no_mounted_preference_is_a_loud_no_op_naming_every_entry() -> None:
    """Fail safe AND fail loud: the record must name what was tried."""
    providers = {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "terra": FakeProvider("terra", 2, "gpt-5.6-terra"),
    }
    before = _priorities(providers)
    coordinator = _coordinator(
        providers,
        [
            {"provider": "vertex", "model": "gemini-3-pro"},
            {"provider": "luna", "model": "gpt-5.6-luna"},
        ],
    )

    record = reassert_own_role_pin(coordinator)

    assert record == {
        "reasserted": False,
        "reason": "pinned_provider_not_mounted",
        "pinned_provider": "vertex",
        "tried_providers": ["vertex", "luna"],
        "mounted": ["sol", "terra"],
    }
    assert _priorities(providers) == before


# ---------------------------------------------------------------------------
# GAP 3 -- a preference names a provider the way spawn's lookup indexes it.
# ---------------------------------------------------------------------------


def test_gate_preference_matches_a_provider_dash_prefixed_mount() -> None:
    """GATE. ``"openai"`` must reach ``"provider-openai"``, as it does at spawn."""
    providers = {
        "provider-anthropic": FakeProvider("provider-anthropic", 0, "claude-sonnet-5"),
        "provider-openai": FakeProvider("provider-openai", 3, "gpt-5.6-sol"),
    }
    coordinator = _coordinator(
        providers, [{"provider": "openai", "model": "gpt-5.6-sol"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None, (
        "a pin naming 'openai' found no mounted match, so a provider mounted "
        "as 'provider-openai' was unreachable -- spawn's own lookup indexes "
        "both spellings (spawn_utils.py:649-675)"
    )
    assert record["pinned_provider"] == "provider-openai"
    assert _priority_winner(providers) == "provider-openai"


def test_exact_key_wins_over_a_variant_match() -> None:
    """An explicit ``id:`` mounted beside the module keeps its exact meaning.

    Keys ``"openai"`` and ``"provider-openai"`` normalise to the same short
    name, so variant matching alone would be ambiguous. Exact match is tried
    first, which makes both spellings mean precisely what they say.
    """
    providers = {
        "openai": FakeProvider("openai", 5, "gpt-5.6-sol"),
        "provider-openai": FakeProvider("provider-openai", 6, "gpt-5.6-luna"),
        "anthropic": FakeProvider("anthropic", 0, "claude-sonnet-5"),
    }
    coordinator = _coordinator(
        providers, [{"provider": "provider-openai", "model": "gpt-5.6-luna"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "provider-openai"
    assert _priority_winner(providers) == "provider-openai"


def test_match_mounted_resolves_an_ambiguous_spelling_instead_of_refusing() -> None:
    """SUPERSEDED by recipes-0ac: this used to assert refusal, and refusal is the bug.

    Until recipes-0ac this returned the candidate LIST, on the reasoning that
    upstream's own two helpers disagreed on which instance wins
    (``_find_provider_index`` takes the first, ``_build_provider_lookup``'s
    dict build leaves the last), so picking a side would have been inventing a
    rule. Upstream has since picked one -- ``spawn_utils._find_provider_instance``
    resolves to the instance whose ``default_model`` matches, else the
    highest-priority one -- so this layer now applies THAT rule rather than
    abandoning the preference and falling through to a later, worse one.

    With bare ``object()`` values there is no model and no priority to read, so
    only the deterministic tail of the rule is left: lowest priority number
    (both default to 100), then key name.
    """
    keys = {"provider-openai": object(), "provider-provider-openai": object()}

    assert _match_mounted(keys, "provider-openai") == "provider-openai"  # exact
    assert _match_mounted(keys, "vertex") is None  # no match
    assert _match_mounted(keys, "openai") == "provider-openai"  # resolved, not a list


def test_ambiguous_pin_is_resolved_by_model_intent() -> None:
    """The caller's half of the same rule: resolve, report, promote.

    The preference names a model, and exactly one of the two instances
    answering to ``openai`` is configured for it -- so that instance is what
    the preference means, and it is promoted. Pre-recipes-0ac this returned
    ``pinned_provider_ambiguous`` and changed nothing, leaving selection on
    ``anthropic``.
    """
    providers = {
        "provider-openai": FakeProvider("provider-openai", 5, "gpt-5.6-sol"),
        "provider-provider-openai": FakeProvider(
            "provider-provider-openai", 6, "gpt-5.6-luna"
        ),
        "anthropic": FakeProvider("anthropic", 0, "claude-sonnet-5"),
    }
    coordinator = _coordinator(
        providers, [{"provider": "openai", "model": "gpt-5.6-luna"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["reason"] == "mount_state_disagreed_with_declared_pin"
    assert record["pinned_provider"] == "provider-provider-openai"
    assert record["pinned_provider_declared"] == "openai"
    assert record["provider_resolution"] == "name_variant_default_model"
    assert record["resolution_candidates"] == [
        "provider-openai",
        "provider-provider-openai",
    ]
    assert _priority_winner(providers) == "provider-provider-openai"
    # The demotion half of _apply_single_override still applies to the loser.
    assert _priorities(providers)["anthropic"] == 1


# ---------------------------------------------------------------------------
# Default safety -- the fully-agreeing session stays byte-identical.
# ---------------------------------------------------------------------------


def test_session_agreeing_on_every_field_is_untouched() -> None:
    """Priority, model and config all already correct -> no record, no writes."""
    providers = {
        "sol": FakeAttrProvider("sol", 1, "gpt-5.6-sol"),
        "luna": FakeAttrProvider("luna", 0, "gpt-5.6-luna", reasoning_effort="high"),
    }
    snapshot = {n: dict(p.config) for n, p in providers.items()}
    coordinator = _coordinator(
        providers,
        [
            {
                "provider": "luna",
                "model": "gpt-5.6-luna",
                "config": {"reasoning_effort": "high"},
            }
        ],
    )

    assert reassert_own_role_pin(coordinator) is None
    assert {n: dict(p.config) for n, p in providers.items()} == snapshot


def test_preference_entry_without_a_provider_name_is_skipped() -> None:
    """A malformed entry must not abort the list, nor match anything."""
    providers = {
        "sol": FakeProvider("sol", 0, "gpt-5.6-sol"),
        "luna": FakeProvider("luna", 14, "gpt-5.6-luna"),
    }
    coordinator = _coordinator(
        providers,
        [
            {"model": "gpt-5.6-nano"},  # no provider key at all
            {"provider": "", "model": "gpt-5.6-nano"},  # empty name
            {"provider": "luna", "model": "gpt-5.6-luna"},
        ],
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "luna"
    # Both malformed entries were dropped, so exactly one usable preference
    # remains -- and a single-preference record carries no list to report.
    assert "tried_providers" not in record
    assert _priority_winner(providers) == "luna"


# ---------------------------------------------------------------------------
# Drift tripwire -- this module mirrors upstream, so prove the mirror is true.
# ---------------------------------------------------------------------------


def test_vendored_protected_keys_match_upstream() -> None:
    """The vendored fallback must equal the real ``PROTECTED_CONFIG_KEYS``.

    The live set is imported when amplifier-foundation is importable; the
    vendored copy only covers the case where it is not. If upstream adds a
    protected key, this fails instead of the two silently diverging.
    """
    spawn_utils = pytest.importorskip("amplifier_foundation.spawn_utils")

    assert _PROTECTED_CONFIG_KEYS_FALLBACK == frozenset(
        spawn_utils.PROTECTED_CONFIG_KEYS
    )
    assert _protected_config_keys() == frozenset(spawn_utils.PROTECTED_CONFIG_KEYS)
