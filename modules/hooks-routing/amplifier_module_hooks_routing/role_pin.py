"""Re-assert a session's OWN model_role provider pin at session:start.

Why this exists (model_performance-74w)
---------------------------------------
A delegate spawned with ``model_role: fast`` gets its child mount plan
promoted so the role's provider wins priority selection
(``amplifier-foundation/spawn_utils.py`` ``_apply_single_override``: target to
priority 0, ties demoted). That promotion does not survive a RESUME: the resume
path re-applies the settings-level provider overrides over the persisted child
plan, and settings speak in ``priority``, so the promotion is overwritten with
the root's ordering. Upstream defect: ``model_performance-rc0``.

Measured consequence, capture ``20260901-rebaseline/runs/val-rb-oai-sol-xhigh-s1-01``,
delegate ``0000000000000000-25443a97b60d4965_anchors-amp-dev-git-ops``:

    leg 1 (spawn)   luna pri=0, sol pri=1   -> 13 requests gpt-5.6-luna@high
    leg 2 (resume)  luna pri=14, sol pri=0  -> 25 requests gpt-5.6-sol@xhigh

Both legs still carried ``provider_preferences=[luna]`` and
``model_role=["fast","general"]``. The intent was present in config the whole
time and simply ignored by the mount plan.

Why hooks-routing can fix it here
---------------------------------
``loop-streaming._select_provider`` reads ``priority`` off the LIVE provider
objects on every request -- not from a frozen plan. ``session:start`` fires on
the resumed leg *before* the first ``provider:resolve``. So restoring the
promotion on those live objects at ``session:start`` is sufficient, and it is
squarely this module's business: hooks-routing owns model_role -> provider
intent.

THIS IS DEFENSE IN DEPTH, NOT THE ROOT CAUSE
--------------------------------------------
The root cause is the resume path itself re-imposing settings priority over a
child's promoted mount plan. That is owned upstream in ``amplifier-app-cli``
(lane n1i, PR #292) and tracked as ``model_performance-rc0``. Everything in
this file is a second line of defence in the routing layer: it repairs the
symptom on the live provider objects after the fact. It does not, and does not
claim to, fix the resume path.

Fidelity to ``_apply_single_override`` (model_performance-j8v)
--------------------------------------------------------------
The promotion this file restores must be the SAME promotion spawn applied, or
it silently half-restores. Measured field-by-field against
``spawn_utils.py`` (installed ``amplifier-foundation``)::

    spawn_utils.py:772   target config["priority"]      = 0
    spawn_utils.py:773   target config["default_model"] = pref.model
    spawn_utils.py:767-770  target config[k] = v for each pref.config key
                            not in PROTECTED_CONFIG_KEYS (spawn_utils.py:243)
    spawn_utils.py:800-806  every OTHER provider whose priority <= 0 -> 1
    spawn_utils.py:713-718  the applied preference is the FIRST entry in the
                            list whose provider is mounted -- not entry 0
    spawn_utils.py:649-675  a preference names a provider by module id, by the
                            id with "provider-" stripped, or with it added

All six are mirrored below. Two known residuals, named rather than hidden:

1. A provider snapshots some config into attributes at ``__init__`` through a
   *validator* (e.g. ``provider-openai``'s ``self.reasoning_effort =
   _resolve_config_reasoning_effort(...)``, ``__init__.py:1046``). Re-running
   that validation from here would mean re-entering provider construction,
   which this layer must not do. Such keys are restored to ``config`` and any
   disagreeing attribute is REPORTED in the record's ``inert_config_keys``
   rather than silently overwritten -- the same discipline as the repo's
   "reject inert effort keys instead of dropping them silently" rule.
2. ``provider-anthropic`` derives ``self._default_caps`` from ``default_model``
   at ``__init__`` (``__init__.py:882``). Restoring ``default_model`` here does
   not re-derive it, so capability *metadata* can lag the restored model even
   though request routing (``kwargs.get("model", self.default_model)``,
   ``__init__.py:2940``) is correct.

Default safety
--------------
This is a no-op unless the session's own declared pin *disagrees* with its live
mount state. A freshly spawned session already agrees (spawn applied the
override), a session with no pin has nothing to assert, and a pin naming an
unmounted provider is reported rather than forced. Routing matrices are not
read or modified here at all.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PRIORITY = 100
_TARGET_PRIORITY = 0

# Vendored fallback for spawn_utils.PROTECTED_CONFIG_KEYS (spawn_utils.py:243).
# The live set is imported when amplifier-foundation is importable, so this copy
# can only ever be used where the real one cannot be reached -- and
# tests/test_role_pin_fidelity.py fails if the two ever disagree.
_PROTECTED_CONFIG_KEYS_FALLBACK = frozenset(
    {
        # Credentials
        "api_key",
        "secret",
        "password",
        "token",
        "access_token",
        "bearer_token",
        "client_id",
        "client_secret",
        "tenant_id",
        # Endpoints / infrastructure
        "base_url",
        "host",
        "azure_endpoint",
        "api_version",
        "deployment_name",
        "organization",
        "project",
        # Azure auth control
        "managed_identity_client_id",
        "use_managed_identity",
        "use_default_credential",
        # Network control
        "proxy",
        "http_proxy",
        "https_proxy",
        "verify_ssl",
        "ssl_verify",
        "verify",
        "ca_bundle",
    }
)


def _protected_config_keys() -> frozenset[str]:
    """The live ``PROTECTED_CONFIG_KEYS``, or the vendored copy if unreachable.

    Preferring the import means this module cannot drift away from the set
    ``_apply_single_override`` actually enforces.
    """
    try:
        from amplifier_foundation.spawn_utils import (  # type: ignore[import-not-found]
            PROTECTED_CONFIG_KEYS,
        )
    except Exception:  # pragma: no cover - only where foundation is absent
        return _PROTECTED_CONFIG_KEYS_FALLBACK
    if isinstance(PROTECTED_CONFIG_KEYS, (set, frozenset)):
        return frozenset(PROTECTED_CONFIG_KEYS)
    return _PROTECTED_CONFIG_KEYS_FALLBACK  # pragma: no cover - defensive


def _is_glob_pattern(model_hint: str) -> bool:
    """Mirror of ``spawn_utils.is_glob_pattern`` (spawn_utils.py:364)."""
    return any(c in model_hint for c in "*?[")


def _priority_of(provider: Any) -> int:
    """Read a provider's effective priority.

    Mirrors ``loop-streaming._select_provider`` exactly, including its
    attribute-before-config precedence and its default of 100. If the two
    disagreed, this module would "fix" a value the orchestrator does not read.
    """
    if hasattr(provider, "priority"):
        try:
            return int(provider.priority)
        except (TypeError, ValueError):
            return _DEFAULT_PRIORITY
    if hasattr(provider, "config") and isinstance(provider.config, dict):
        try:
            return int(provider.config.get("priority", _DEFAULT_PRIORITY))
        except (TypeError, ValueError):
            return _DEFAULT_PRIORITY
    return _DEFAULT_PRIORITY


def _read_field(provider: Any, field: str) -> Any:
    """Read a provider field with the same attribute-before-config precedence.

    ``default_model`` is the field that matters here: a live provider serves a
    request from ``kwargs.get("model", self.default_model)`` -- the ATTRIBUTE
    (``provider-openai/__init__.py:2040``, ``provider-anthropic:2940``), which
    it snapshotted from ``config["default_model"]`` at ``__init__``. So the
    attribute is the surface that decides, and the config dict is the surface
    the mount plan carries.
    """
    if hasattr(provider, field):
        return getattr(provider, field)
    if hasattr(provider, "config") and isinstance(provider.config, dict):
        return provider.config.get(field)
    return None


def _write_field(provider: Any, field: str, value: Any) -> bool:
    """Write ``field`` to EVERY surface it can be read from. False if none took.

    Both surfaces, deliberately: writing only the attribute would leave
    ``config`` reporting the pre-drift value to anything that inspects the
    mount state, and writing only ``config`` would not change what the live
    provider actually sends. ``_apply_single_override`` writes ``config``
    because it operates on a mount plan; here the objects are already live.
    """
    wrote = False
    if hasattr(provider, field):
        try:
            setattr(provider, field, value)
            wrote = True
        except AttributeError:
            pass
    if hasattr(provider, "config") and isinstance(provider.config, dict):
        provider.config[field] = value
        wrote = True
    return wrote


def _set_priority(provider: Any, value: int) -> bool:
    """Write priority to the same surface ``_priority_of`` reads. False if none."""
    return _write_field(provider, "priority", value)


def _name_variants(name: str) -> set[str]:
    """Every spelling ``_build_provider_lookup`` indexes a provider under.

    Mirrors ``spawn_utils.py:649-675`` / ``:620-645``: the module id, the id
    with a leading ``provider-`` stripped, and the id with ``provider-``
    prepended. A preference saying ``"anthropic"`` therefore reaches a provider
    mounted as ``"provider-anthropic"``, exactly as it does at spawn time.
    """
    short = name.replace("provider-", "")
    return {name, short, f"provider-{short}"}


def _match_mounted(providers: dict[str, Any], wanted: str) -> str | list[str] | None:
    """The mounted key a preference names.

    Returns the key on an unambiguous match, a ``list`` of candidate keys when
    several mounted instances answer to the same spelling, or ``None`` when
    nothing matches. Ambiguity is returned rather than resolved: upstream's own
    two helpers disagree on which instance wins that case
    (``_find_provider_index`` takes the first, ``_build_provider_lookup``'s dict
    build leaves the last), so guessing here would be inventing a rule.
    """
    if wanted in providers:
        return wanted
    variants = _name_variants(wanted)
    matches = [key for key in providers if variants & _name_variants(key)]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return matches


def _declared_pins(coordinator: Any) -> list[dict[str, Any]]:
    """This session's OWN ``provider_preferences``, in order, normalised.

    This is the session-level key (what the spawner wrote from ``model_role``),
    NOT the per-agent key under ``config["agents"]`` -- those describe children
    this session may spawn, and are resolved separately.

    Each entry is ``{"provider": str, "model": str | None, "config": dict}``,
    matching ``ProviderPreference`` (spawn_utils.py:280). Entries without a
    usable provider name are dropped, exactly as a nameless preference would
    fail to match any lookup key at spawn time.
    """
    config = getattr(coordinator, "config", None)
    if not isinstance(config, dict):
        return []
    prefs = config.get("provider_preferences")
    if not isinstance(prefs, list) or not prefs:
        return []

    out: list[dict[str, Any]] = []
    for entry in prefs:
        if isinstance(entry, dict):
            name = entry.get("provider")
            model = entry.get("model")
            pref_config = entry.get("config")
        else:
            name = getattr(entry, "provider", None)
            model = getattr(entry, "model", None)
            pref_config = getattr(entry, "config", None)
        if not isinstance(name, str) or not name:
            continue
        out.append(
            {
                "provider": name,
                "model": model if isinstance(model, str) and model else None,
                "config": pref_config if isinstance(pref_config, dict) else {},
            }
        )
    return out


def _select_preference(
    providers: dict[str, Any], pins: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    """Pick the first preference whose provider is mounted.

    Mirrors ``apply_provider_preferences`` (spawn_utils.py:713-718), which walks
    the whole ordered list and applies the FIRST entry present in the mount
    plan. Taking entry 0 unconditionally -- the pre-j8v behaviour -- turned a
    legitimate fallback ordering into a loud no-op.

    Returns ``(pin, mounted_key, failure_record)``; exactly one of ``pin`` and
    ``failure_record`` is non-None.
    """
    ambiguous: list[str] = []
    for pin in pins:
        match = _match_mounted(providers, pin["provider"])
        if isinstance(match, str):
            return pin, match, None
        if isinstance(match, list):
            ambiguous = match
            logger.warning(
                "[ROUTING] this session pins %r, but %d mounted providers "
                "answer to that name (%s). Refusing to guess which instance "
                "was meant -- leaving ordering untouched.",
                pin["provider"],
                len(match),
                ", ".join(sorted(match)),
            )
            return (
                None,
                None,
                {
                    "reasserted": False,
                    "reason": "pinned_provider_ambiguous",
                    "pinned_provider": pin["provider"],
                    "candidates": sorted(ambiguous),
                    "mounted": sorted(providers),
                },
            )

    tried = [pin["provider"] for pin in pins]
    # Never invent a promotion for a provider this session cannot reach.
    # Reported, not forced, and not silent.
    logger.warning(
        "[ROUTING] this session declares provider_preferences pinning %s, "
        "but none of those providers is mounted (mounted: %s). Leaving "
        "priority ordering untouched -- selection will use the mounted "
        "ordering.",
        tried,
        ", ".join(sorted(providers)) or "(none)",
    )
    return (
        None,
        None,
        {
            "reasserted": False,
            "reason": "pinned_provider_not_mounted",
            # Entry 0 stays first-class in the record: it is what every
            # single-preference spawn declares, and what the 74w capture shows.
            "pinned_provider": tried[0],
            "tried_providers": tried,
            "mounted": sorted(providers),
        },
    )


def reassert_own_role_pin(coordinator: Any) -> dict[str, Any] | None:
    """Restore this session's role pin if the live mount state has drifted.

    Returns a record describing what was corrected (for event emission), or
    ``None`` when there was nothing to do -- which is the overwhelmingly common
    case and the byte-identical default path.
    """
    pins = _declared_pins(coordinator)
    if not pins:
        return None

    providers = (coordinator.get("providers") if hasattr(coordinator, "get") else None) or {}
    if not isinstance(providers, dict) or not providers:
        return None

    pin, target, failure = _select_preference(providers, pins)
    if pin is None or target is None:
        return failure

    ranked = sorted(providers.items(), key=lambda item: _priority_of(item[1]))
    winner = ranked[0][0]

    # --- Decide what has actually drifted -------------------------------
    # Each of the three field groups _apply_single_override writes is checked
    # independently. A pin can be honoured on provider and wrong on model:
    # that is precisely gap 1, and an early return on `winner == target`
    # (the pre-j8v behaviour) never noticed it.
    priority_drifted = winner != target
    protected = _protected_config_keys()

    pinned_model = pin["model"]
    model_drifted = False
    model_skip_reason: str | None = None
    if pinned_model is not None:
        if _is_glob_pattern(pinned_model):
            # An unresolved pattern is NOT a model name. Writing it would send
            # the literal glob to the provider's API -- the failure
            # ModelResolutionResult (spawn_utils.py:342) exists to warn about.
            model_skip_reason = "model_is_unresolved_pattern"
        elif _read_field(providers[target], "default_model") != pinned_model:
            model_drifted = True

    config_drift: dict[str, Any] = {}
    for pkey, pvalue in pin["config"].items():
        if pkey in protected:
            continue
        current = None
        provider_config = getattr(providers[target], "config", None)
        if isinstance(provider_config, dict):
            current = provider_config.get(pkey)
        if current != pvalue:
            config_drift[pkey] = pvalue

    if not (priority_drifted or model_drifted or config_drift):
        return None  # Already honoured -- every freshly spawned session.

    before = {name: _priority_of(p) for name, p in providers.items()}
    before_model = _read_field(providers[target], "default_model")

    # --- Apply -----------------------------------------------------------
    if priority_drifted:
        # Mirror _apply_single_override: promote the target, then push anything
        # that would tie or beat it strictly below it. Declaration order breaks
        # ties in the orchestrator, so a tie is not good enough.
        if not _set_priority(providers[target], _TARGET_PRIORITY):
            logger.warning(
                "[ROUTING] cannot restore the %r pin: that provider exposes no "
                "writable priority surface. Leaving ordering untouched.",
                target,
            )
            return {
                "reasserted": False,
                "reason": "no_writable_priority_surface",
                "pinned_provider": target,
            }

        for name, provider in providers.items():
            if name == target:
                continue
            if _priority_of(provider) <= _TARGET_PRIORITY:
                _set_priority(provider, _TARGET_PRIORITY + 1)

    if model_drifted:
        assert pinned_model is not None  # narrowed by model_drifted
        if not _write_field(providers[target], "default_model", pinned_model):
            model_drifted = False
            model_skip_reason = "no_writable_model_surface"
            logger.warning(
                "[ROUTING] cannot restore the pinned model %r on %r: that "
                "provider exposes no writable default_model surface.",
                pinned_model,
                target,
            )

    # Preference config keys go to `config` only. A provider that snapshotted a
    # key into an attribute through a validator at __init__ (provider-openai's
    # reasoning_effort, __init__.py:1046) will not pick this up -- so say so in
    # the record instead of writing an attribute past its own validation.
    inert_config_keys: list[str] = []
    if config_drift:
        provider_config = getattr(providers[target], "config", None)
        if isinstance(provider_config, dict):
            for ckey, cvalue in config_drift.items():
                provider_config[ckey] = cvalue
                if hasattr(providers[target], ckey) and getattr(providers[target], ckey) != cvalue:
                    inert_config_keys.append(ckey)
        else:  # pragma: no cover - defensive: no config dict to restore into
            inert_config_keys = sorted(config_drift)
            config_drift = {}

    after = {name: _priority_of(p) for name, p in providers.items()}
    after_model = _read_field(providers[target], "default_model")

    logger.info(
        "[ROUTING] restored this session's model_role pin on %r: selection was "
        "resolving to %r; model %r -> %r. This session's config pinned %r all "
        "along -- the live mount state had drifted (see model_performance-rc0: "
        "a RESUME re-imposes settings priority over a child's promotion). "
        "priorities %s -> %s; config keys restored: %s",
        target,
        winner,
        before_model,
        after_model,
        target,
        before,
        after,
        sorted(config_drift) or "(none)",
    )
    if inert_config_keys:
        logger.warning(
            "[ROUTING] config keys %s were restored to %r's config but that "
            "provider already snapshotted a different value into an attribute "
            "at mount; a config write cannot change what it sends. Reported, "
            "not silently forced. Root fix is upstream (model_performance-rc0).",
            sorted(inert_config_keys),
            target,
        )

    record: dict[str, Any] = {
        "reasserted": True,
        "reason": "mount_state_disagreed_with_declared_pin",
        "pinned_provider": target,
        "would_have_resolved_to": winner,
        "priorities_before": before,
        "priorities_after": after,
        "priority_reasserted": priority_drifted,
        "model_reasserted": model_drifted,
        "model_before": before_model,
        "model_after": after_model,
        "config_keys_reasserted": sorted(config_drift),
    }
    if len(pins) > 1:
        record["preference_index"] = pins.index(pin)
        record["tried_providers"] = [p["provider"] for p in pins]
    if model_skip_reason is not None:
        record["model_not_reasserted_reason"] = model_skip_reason
        record["pinned_model"] = pinned_model
    if inert_config_keys:
        record["inert_config_keys"] = sorted(inert_config_keys)
    return record
