"""Resolver - resolves model roles against routing matrix and installed providers."""

from __future__ import annotations

import fnmatch
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Matches trailing date suffixes on model snapshot IDs so clean-versioned model
# names sort above date-stamped snapshots under natural-sort ordering. Handles
# both compact (YYYYMMDD) and hyphenated (YYYY-MM-DD) forms:
#   claude-opus-4-20250514           -> claude-opus-4
#   claude-haiku-4-5-20251001        -> claude-haiku-4-5
#   gpt-5.4-pro-2026-03-05           -> gpt-5.4-pro
_DATE_SUFFIX_RE = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")

# Used by the natural-sort key to split model names into mixed text/integer parts.
_DIGIT_RUN_RE = re.compile(r"(\d+)")


def _is_glob(pattern: str) -> bool:
    """Check whether *pattern* contains glob wildcard characters."""
    return any(c in pattern for c in "*?[")


def _version_sort_key(name: str) -> tuple:
    """Natural-sort key that handles semver-like IDs correctly.

    Two refinements over pure lexicographic sort:

    1. **Date-suffix stripping.** A trailing ``-YYYYMMDD`` or ``-YYYY-MM-DD``
       is removed before sorting. This ensures clean-versioned IDs like
       ``claude-opus-4-7`` sort above snapshot IDs like
       ``claude-opus-4-20250514`` (which is actually Opus 4.0, not 4.2 billion).

    2. **Numeric-aware splitting.** Digit runs are compared as integers so
       ``claude-opus-4-10`` > ``claude-opus-4-7`` (the string sort would pick
       ``4-7`` because ``'7' > '1'`` lexicographically).

    Secondary key (``-len(name)``) is a tie-breaker that prefers shorter names
    when the primary key is equal — e.g. ``gpt-5.4`` wins over
    ``gpt-5.4-2026-03-05`` because aliases are preferred over pinned snapshots.
    """
    stripped = _DATE_SUFFIX_RE.sub("", name)
    primary: list[Any] = [
        int(p) if p.isdigit() else p for p in _DIGIT_RUN_RE.split(stripped)
    ]
    # Descending sort uses (primary, -len) so shorter names rank higher on ties.
    return (primary, -len(name))


def find_provider_by_type(
    providers: dict[str, Any],
    type_name: str,
) -> tuple[str, Any] | None:
    """Find an installed provider by module type name or instance ID.

    The matrix ``provider:`` field accepts any key present in
    ``coordinator.providers``. This supports two modes:

    * **Type-name mode** (the common case): ``'anthropic'``, ``'openai'``,
      ``'gemini'``, ``'github-copilot'``. Matches the short mount name the
      provider registers itself under.
    * **Instance-ID mode** (multi-instance providers): ``'openai-internal'``,
      ``'openai-reasoning'``. Matches the ``id:`` set in ``settings.yaml`` for
      a second instance of an already-installed provider module. See
      ``docs/MATRIX_CURATOR_GUIDE.md`` for the multi-instance pattern.

    Args:
        providers: Dict of mounted providers keyed by module id or instance id.
        type_name: Provider identifier from a matrix candidate's ``provider:``
            field (short type name or multi-instance id).

    Returns:
        ``(module_id, provider_instance)`` or ``None``.
    """
    for name, provider in providers.items():
        if type_name in (
            name,
            name.replace("provider-", ""),
            f"provider-{type_name}",
        ):
            return (name, provider)
    return None


async def resolve_model_role(
    roles: list[str],
    matrix: dict[str, Any],
    providers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve model role(s) against routing matrix.

    Args:
        roles: Prioritised list of role names to try.
        matrix: Composed matrix ``roles`` dict (from :mod:`matrix_loader`).
        providers: Installed providers dict from ``coordinator.get("providers")``.

    Returns:
        List of ``{provider, model, config}`` dicts representing resolved
        preferences.  Empty if no role resolves.
    """
    for role in roles:
        role_data = matrix.get(role)
        if role_data is None:
            continue

        candidates = role_data.get("candidates", [])
        for candidate in candidates:
            provider_type = candidate.get("provider", "")
            model_pattern = candidate.get("model", "")
            config = candidate.get("config", {})

            # Is this provider installed?
            match = find_provider_by_type(providers, provider_type)
            if match is None:
                continue

            _module_id, provider_instance = match

            # Is the model pattern a glob?
            if _is_glob(model_pattern):
                resolved_model = await _resolve_glob(model_pattern, provider_instance)
                if resolved_model is None:
                    continue
            else:
                resolved_model = model_pattern

            return [
                {
                    "provider": provider_type,
                    "model": resolved_model,
                    "config": config,
                }
            ]

    return []


async def _resolve_glob(pattern: str, provider: Any) -> str | None:
    """Resolve a glob model pattern against a provider's model list.

    Uses natural-sort ordering (see :func:`_version_sort_key`) so that:

    * Higher version numbers win (``claude-opus-4-10`` > ``claude-opus-4-7``).
    * Clean-versioned IDs outrank snapshot IDs with date suffixes
      (``claude-opus-4-7`` > ``claude-opus-4-20250514``).
    * Shorter aliases outrank pinned snapshots on equal primary keys
      (``gpt-5.4`` > ``gpt-5.4-2026-03-05``).

    Returns the highest-ranked matching model name or ``None`` when no
    candidate matches or the provider's ``list_models()`` raises.
    """
    try:
        available = await provider.list_models()
    except Exception:
        logger.warning(
            "Failed to list models for glob pattern '%s'", pattern, exc_info=True
        )
        return None

    # Normalise to list of strings
    model_names: list[str] = [
        m if isinstance(m, str) else getattr(m, "id", str(m)) for m in available
    ]

    matched = fnmatch.filter(model_names, pattern)
    if not matched:
        return None

    matched.sort(key=_version_sort_key, reverse=True)
    return matched[0]
