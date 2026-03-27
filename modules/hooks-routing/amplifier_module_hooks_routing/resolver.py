"""Resolver - resolves model roles against routing matrix and installed providers."""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _is_glob(pattern: str) -> bool:
    """Check whether *pattern* contains glob wildcard characters."""
    return any(c in pattern for c in "*?[")


def find_provider_by_type(
    providers: dict[str, Any],
    type_name: str,
) -> tuple[str, Any] | None:
    """Find an installed provider by module type name.

    ``'anthropic'`` matches ``'provider-anthropic'``, ``'anthropic'``, etc.

    Args:
        providers: Dict of mounted providers keyed by module id.
        type_name: Short provider type name (e.g. ``"anthropic"``).

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

    Iterates through roles in priority order.  For the first role that has
    at least one resolvable candidate, returns **all** resolvable candidates
    for that role (preserving the matrix ordering).  This gives downstream
    consumers (orchestrators, the CLI provider-selector) a full failover
    chain rather than a single provider.

    Args:
        roles: Prioritised list of role names to try.
        matrix: Composed matrix ``roles`` dict (from :mod:`matrix_loader`).
        providers: Installed providers dict from ``coordinator.get("providers")``.

    Returns:
        List of ``{provider, model, config}`` dicts representing resolved
        preferences in priority order.  Empty if no role resolves.
    """
    for role in roles:
        role_data = matrix.get(role)
        if role_data is None:
            continue

        candidates = role_data.get("candidates", [])
        resolved: list[dict[str, Any]] = []

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
                resolved_model = await _resolve_glob(
                    model_pattern, provider_instance
                )
                if resolved_model is None:
                    continue
            else:
                resolved_model = model_pattern

            resolved.append(
                {
                    "provider": provider_type,
                    "model": resolved_model,
                    "config": config,
                }
            )

        if resolved:
            return resolved

    return []


async def _resolve_glob(pattern: str, provider: Any) -> str | None:
    """Resolve a glob model pattern against a provider's model list.

    Returns the best matching model name (sorted descending) or ``None``.
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

    matched.sort(reverse=True)
    return matched[0]
