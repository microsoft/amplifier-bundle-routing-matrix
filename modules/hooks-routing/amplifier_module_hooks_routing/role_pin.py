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

Default safety
--------------
This is a no-op unless the session's own declared pin *disagrees* with its live
mount ordering. A freshly spawned session already agrees (spawn applied the
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


def _set_priority(provider: Any, value: int) -> bool:
    """Write priority to the same surface ``_priority_of`` reads. False if none."""
    if hasattr(provider, "priority"):
        try:
            provider.priority = value
            return True
        except AttributeError:
            return False
    if hasattr(provider, "config") and isinstance(provider.config, dict):
        provider.config["priority"] = value
        return True
    return False


def _declared_pin(coordinator: Any) -> str | None:
    """The provider named by this session's OWN provider_preferences, if any.

    This is the session-level key (what the spawner wrote from ``model_role``),
    NOT the per-agent key under ``config["agents"]`` -- those describe children
    this session may spawn, and are resolved separately.
    """
    config = getattr(coordinator, "config", None)
    if not isinstance(config, dict):
        return None
    prefs = config.get("provider_preferences")
    if not isinstance(prefs, list) or not prefs:
        return None
    first = prefs[0]
    if isinstance(first, dict):
        name = first.get("provider")
    else:
        name = getattr(first, "provider", None)
    return name if isinstance(name, str) and name else None


def reassert_own_role_pin(coordinator: Any) -> dict[str, Any] | None:
    """Restore this session's role pin if the live mount ordering has drifted.

    Returns a record describing what was corrected (for event emission), or
    ``None`` when there was nothing to do -- which is the overwhelmingly common
    case and the byte-identical default path.
    """
    target = _declared_pin(coordinator)
    if target is None:
        return None

    providers = (coordinator.get("providers") if hasattr(coordinator, "get") else None) or {}
    if not isinstance(providers, dict) or not providers:
        return None

    if target not in providers:
        # Never invent a promotion for a provider this session cannot reach.
        # Reported, not forced, and not silent.
        logger.warning(
            "[ROUTING] this session declares provider_preferences pinning %r, "
            "but %r is not mounted (mounted: %s). Leaving priority ordering "
            "untouched -- selection will use the mounted ordering.",
            target,
            target,
            ", ".join(sorted(providers)) or "(none)",
        )
        return {
            "reasserted": False,
            "reason": "pinned_provider_not_mounted",
            "pinned_provider": target,
            "mounted": sorted(providers),
        }

    ranked = sorted(providers.items(), key=lambda kv: _priority_of(kv[1]))
    winner = ranked[0][0]
    if winner == target:
        return None  # Already honoured -- every freshly spawned session.

    before = {name: _priority_of(p) for name, p in providers.items()}

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

    after = {name: _priority_of(p) for name, p in providers.items()}
    logger.info(
        "[ROUTING] restored this session's model_role pin: selection was "
        "resolving to %r, now %r. This session's config pinned %r all along "
        "-- the live mount ordering had drifted (see model_performance-rc0: "
        "a RESUME re-imposes settings priority over a child's promotion). "
        "priorities %s -> %s",
        winner,
        target,
        target,
        before,
        after,
    )
    return {
        "reasserted": True,
        "reason": "mount_ordering_disagreed_with_declared_pin",
        "pinned_provider": target,
        "would_have_resolved_to": winner,
        "priorities_before": before,
        "priorities_after": after,
    }
