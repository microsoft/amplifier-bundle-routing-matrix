"""A pin names a MODULE; a host mounts INSTANCES (recipes-0ac).

Measured 2026-09-02 on a 14-provider host. Child session
``...a0a049acf77d43c7``, spawned for a ``reasoning``-role agent, shows the two
halves of the defect one after the other in its own event log:

    session:fork    opus   priority 0     (the spawner promoted the right one)
    session:config  gemini priority 0, opus demoted to 1   (this module)

The session's ``provider_preferences`` chain was, in order::

    [{anthropic, claude-opus-*}, {openai, ...}, {gemini, gemini-3-pro-*}]

and the host's mount plan keyed every provider by its own instance ``id:``::

    opus   p1 claude-opus-5                     module provider-anthropic
    sonnet p5 claude-sonnet-5                   module provider-anthropic
    fable  p6 claude-sonnet-4-5                 module provider-anthropic
    gemini p7 gemini-3.1-flash-image-preview    module provider-gemini
    sol    p2 gpt-5.6-sol                       module provider-openai-responses
    terra  p3 gpt-5.6-terra                     module provider-openai-responses

``_match_mounted`` compared each preference's ``provider`` string against those
KEYS by spelling. ``anthropic`` matched no key -- three instances of that module
were mounted, none *named* it -- so the first and correct preference was
skipped. ``gemini`` matched a key literally, purely because one instance
happened to be named after a module, and won on the third preference. Its
``model`` was an unresolved glob, so the instance kept its own default:
``gemini-3.1-flash-image-preview``, a 65K-token image model. The reasoning agent
400'd.

The rule these tests pin, identical to ``resolver.find_provider_by_type`` and to
``amplifier_foundation.spawn_utils._find_provider_instance`` (sibling PR): a
preference naming a MODULE resolves to the instance of that module whose
``default_model`` matches the preference's ``model``, else the highest-priority
instance -- and that question is answered BEFORE any match on key spelling.

Every test marked GATE fails at 452560b and passes after.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from amplifier_module_hooks_routing.role_pin import (
    _match_mounted,
    reassert_own_role_pin,
)


class FakeProvider:
    """A live provider: attribute AND config, the two surfaces role_pin reads."""

    def __init__(self, name: str, priority: int, model: str, **config: Any) -> None:
        self.name = name
        self.priority = priority
        self.default_model = model
        self.config: dict[str, Any] = {
            "priority": priority,
            "default_model": model,
            **config,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FakeProvider({self.name!r}, priority={self.priority})"


# (instance id, module, priority, default_model) -- the measured host, trimmed
# to the instances the chain can reach. Priorities are the settings-level
# ordering the resume path re-imposes.
_MEASURED_HOST: list[tuple[str, str, int, str]] = [
    ("opus", "provider-anthropic", 1, "claude-opus-5"),
    ("sonnet", "provider-anthropic", 5, "claude-sonnet-5"),
    ("fable", "provider-anthropic", 6, "claude-sonnet-4-5"),
    ("gemini", "provider-gemini", 7, "gemini-3.1-flash-image-preview"),
    ("sol", "provider-openai-responses", 2, "gpt-5.6-sol"),
    ("terra", "provider-openai-responses", 3, "gpt-5.6-terra"),
]

# The reasoning-role chain from the capture, verbatim in order.
_REASONING_CHAIN = [
    {"provider": "anthropic", "model": "claude-opus-*"},
    {"provider": "openai", "model": "gpt-5.6-*"},
    {"provider": "gemini", "model": "gemini-3-pro-*"},
]


def _host(
    shape: list[tuple[str, str, int, str]] = _MEASURED_HOST,
    **priority_overrides: int,
) -> tuple[dict[str, FakeProvider], list[dict[str, Any]]]:
    """Mounted providers plus the mount-plan specs that name their modules."""
    providers = {
        instance: FakeProvider(
            instance, priority_overrides.get(instance, priority), model
        )
        for instance, _module, priority, model in shape
    }
    specs = [
        {
            "module": module,
            "id": instance,
            "config": {
                "priority": priority_overrides.get(instance, priority),
                "default_model": model,
            },
        }
        for instance, module, priority, model in shape
    ]
    return providers, specs


def _coordinator(
    providers: dict[str, FakeProvider],
    specs: list[dict[str, Any]],
    prefs: list[dict[str, Any]],
) -> MagicMock:
    coordinator = MagicMock()
    coordinator.get = MagicMock(
        side_effect=lambda key: providers if key == "providers" else None
    )
    coordinator.config = {
        "agents": {},
        "providers": specs,
        "provider_preferences": prefs,
    }
    return coordinator


def _priorities(providers: dict[str, FakeProvider]) -> dict[str, int]:
    return {name: p.priority for name, p in providers.items()}


def _priority_winner(providers: dict[str, FakeProvider]) -> str:
    """Mirror of loop-streaming._select_provider's ordering."""
    return min(providers.items(), key=lambda kv: kv[1].priority)[0]


# ---------------------------------------------------------------------------
# The measured failure.
# ---------------------------------------------------------------------------


def test_gate_measured_host_promotes_opus_and_never_touches_gemini() -> None:
    """GATE. The capture, replayed: the drifted leg must land back on opus.

    Live state here is the post-drift one the capture shows at ``session:config``
    time -- ``gemini`` already at 0, ``opus`` at 1 -- which is precisely when
    this module is supposed to intervene. Pre-fix it *caused* that state; it now
    repairs it.
    """
    providers, specs = _host(gemini=0)
    coordinator = _coordinator(providers, specs, _REASONING_CHAIN)

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "opus", (
        "the FIRST preference names module 'anthropic' and asks for "
        "claude-opus-*; the opus instance is the one configured for it"
    )
    assert record["pinned_provider_declared"] == "anthropic"
    assert record["provider_resolution"] == "module_default_model"
    assert record["resolution_candidates"] == ["fable", "opus", "sonnet"]
    assert record["preference_index"] == 0
    assert _priority_winner(providers) == "opus"
    assert _priorities(providers)["opus"] == 0
    # gemini is demoted out of the way (the _apply_single_override mirror), but
    # its own model is never rewritten -- the image model stays where it lives.
    assert _priorities(providers)["gemini"] == 1
    assert providers["gemini"].default_model == "gemini-3.1-flash-image-preview"


def test_gate_measured_host_at_spawn_state_is_a_no_op() -> None:
    """GATE. Freshly spawned (opus already winning) -> nothing is touched at all.

    This is the leg the capture shows going WRONG: at ``session:fork`` the
    spawner had already put opus at 0, and this module then moved gemini to 0
    on top of it. The correct behaviour is a byte-identical no-op.
    """
    providers, specs = _host(opus=0)
    snapshot = {name: dict(p.config) for name, p in providers.items()}
    coordinator = _coordinator(providers, specs, _REASONING_CHAIN)

    assert reassert_own_role_pin(coordinator) is None
    assert {name: dict(p.config) for name, p in providers.items()} == snapshot
    assert providers["gemini"].priority == 7
    assert providers["gemini"].default_model == "gemini-3.1-flash-image-preview"


def test_gate_earlier_preference_never_falls_through_to_a_later_one() -> None:
    """GATE. The fall-through is the whole defect, asserted on its own.

    Even with the gemini instance sitting at priority 0 and spelling-matching
    the third preference exactly, the FIRST preference resolves, so the third
    is never reached.
    """
    providers, specs = _host(gemini=0)
    coordinator = _coordinator(providers, specs, _REASONING_CHAIN)

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] != "gemini"
    assert record["tried_providers"] == ["anthropic", "openai", "gemini"]


# ---------------------------------------------------------------------------
# The rule, isolated.
# ---------------------------------------------------------------------------


def test_module_named_preference_resolves_by_default_model() -> None:
    """Three anthropic instances, three different models, three right answers."""
    providers, specs = _host()
    coordinator = _coordinator(providers, specs, [])

    for model, expected in (
        ("claude-opus-*", "opus"),
        ("claude-sonnet-5", "sonnet"),
        ("claude-sonnet-4-5", "fable"),
    ):
        assert (
            _match_mounted(providers, "anthropic", model, coordinator) == expected
        ), model


def test_module_named_preference_falls_back_to_highest_priority() -> None:
    """No instance serves the model -> the highest-priority instance, not a skip.

    ``sonnet`` (p5) beats ``fable`` (p6) and both beat nothing: the preference
    still resolves. Priority is read from the MOUNT PLAN, not from the live
    objects, because the live ones are what drifted.
    """
    providers, specs = _host()
    providers["opus"].priority = 0  # live drift the plan does not know about
    coordinator = _coordinator(providers, specs, [])

    # A model no anthropic instance is configured for.
    assert _match_mounted(providers, "anthropic", "claude-haiku-*", coordinator) == (
        "opus"
    )

    # Same question with opus removed from the plan's reach: next best wins.
    trimmed = [entry for entry in specs if entry["id"] != "opus"]
    coordinator = _coordinator(providers, trimmed, [])
    assert _match_mounted(providers, "anthropic", "claude-haiku-*", coordinator) == (
        "sonnet"
    )


def test_module_name_that_is_also_a_key_keeps_its_literal_reading() -> None:
    """A host keying one instance by the bare module name is not disadvantaged.

    ``anthropic`` is simultaneously a module and a mounted key here. Model
    intent still decides when it can (``claude-opus-*`` means the opus
    instance, even though it is not the one named after the module); when it
    cannot, naming a key exactly beats "lowest priority number wins", which is
    what this resolved to before recipes-0ac.
    """
    shape = [
        ("anthropic", "provider-anthropic", 5, "claude-sonnet-5"),
        ("opus", "provider-anthropic", 1, "claude-opus-5"),
    ]
    providers, specs = _host(shape)
    coordinator = _coordinator(providers, specs, [])

    assert _match_mounted(providers, "anthropic", "claude-opus-*", coordinator) == (
        "opus"
    )
    assert _match_mounted(providers, "anthropic", None, coordinator) == "anthropic"
    assert _match_mounted(providers, "anthropic", "claude-haiku-*", coordinator) == (
        "anthropic"
    )


def test_exact_instance_id_preference_still_wins() -> None:
    """A pin naming an instance means that instance, model glob notwithstanding."""
    providers, specs = _host()
    coordinator = _coordinator(
        providers, specs, [{"provider": "fable", "model": "claude-sonnet-4-5"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "fable"
    assert record["provider_resolution"] == "instance_id"
    assert _priority_winner(providers) == "fable"


def test_single_instance_module_is_unchanged() -> None:
    """The ordinary one-instance-per-module host behaves exactly as before."""
    shape = [
        ("anthropic", "provider-anthropic", 5, "claude-sonnet-5"),
        ("openai", "provider-openai", 3, "gpt-5.6-sol"),
    ]
    providers, specs = _host(shape)
    coordinator = _coordinator(
        providers, specs, [{"provider": "anthropic", "model": "claude-sonnet-5"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "anthropic"
    assert record["provider_resolution"] == "module_single"
    assert "resolution_candidates" not in record
    assert _priority_winner(providers) == "anthropic"


def test_instance_named_after_another_module_does_not_match_it() -> None:
    """GATE. The spelling collision, inverted: name is not module.

    An instance keyed ``gemini`` whose module is ``provider-anthropic`` must not
    satisfy ``provider: gemini`` while a real gemini-module instance is mounted.
    Pre-fix the literal key match took it every time.
    """
    shape = [
        ("gemini", "provider-anthropic", 1, "claude-opus-5"),
        ("flash", "provider-gemini", 4, "gemini-3-pro-preview"),
    ]
    providers, specs = _host(shape)
    coordinator = _coordinator(
        providers, specs, [{"provider": "gemini", "model": "gemini-3-pro-preview"}]
    )

    assert (
        _match_mounted(providers, "gemini", "gemini-3-pro-preview", coordinator)
        == "flash"
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "flash"
    assert _priority_winner(providers) == "flash"
    # The misnamed anthropic instance keeps its own model, and loses the race.
    assert providers["gemini"].default_model == "claude-opus-5"


def test_legitimate_instance_named_after_its_own_module_still_matches() -> None:
    """The converse: instance ``gemini`` IS module provider-gemini -> it wins."""
    shape = [
        ("gemini", "provider-gemini", 7, "gemini-3-pro-preview"),
        ("opus", "provider-anthropic", 1, "claude-opus-5"),
    ]
    providers, specs = _host(shape)
    coordinator = _coordinator(
        providers, specs, [{"provider": "gemini", "model": "gemini-3-pro-preview"}]
    )

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "gemini"
    assert _priority_winner(providers) == "gemini"


def test_no_mount_plan_leaves_the_pre_existing_spelling_path_intact() -> None:
    """A coordinator with no ``config["providers"]`` still resolves by spelling.

    Mount-plan metadata is the signal that distinguishes module from instance;
    without it there is nothing new to know, and the module must degrade to
    exactly what it did before rather than fail.
    """
    providers, _specs = _host(gemini=0)
    coordinator = _coordinator(providers, [], [{"provider": "opus", "model": None}])

    record = reassert_own_role_pin(coordinator)

    assert record is not None
    assert record["pinned_provider"] == "opus"
    assert record["provider_resolution"] == "instance_id"
    assert _priority_winner(providers) == "opus"
