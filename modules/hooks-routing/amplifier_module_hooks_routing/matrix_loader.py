"""Matrix loader - loads and composes routing matrix YAML files."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


def load_matrix(path: str | Path) -> dict[str, Any]:
    """Load a YAML matrix file.

    Args:
        path: Path to the matrix YAML file.

    Returns:
        Parsed dict with ``name``, ``description``, ``updated``, ``roles`` keys.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Matrix file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Matrix file must contain a YAML mapping: {path}")

    return data


def compose_matrix(
    base: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Compose a base matrix's roles with user overrides.

    The ``base`` keyword in an override role's candidates list gets replaced
    with the base matrix's candidates for that role.

    Args:
        base: Base matrix ``roles`` dict.
        overrides: User override ``roles`` dict.

    Returns:
        Composed ``roles`` dict (new dict, inputs not mutated).

    Raises:
        ValueError: If multiple ``base`` keywords appear in a single
            candidates list.
    """
    result: dict[str, Any] = copy.deepcopy(base)

    for role_name, override_data in overrides.items():
        override_data = copy.deepcopy(override_data)
        candidates = override_data.get("candidates", [])

        base_count = sum(1 for c in candidates if c == "base")
        if base_count > 1:
            raise ValueError(
                f"Role '{role_name}': multiple 'base' keywords found in candidates "
                f"list. Only one is allowed."
            )

        if base_count == 0:
            # Full replacement — no base keyword
            result[role_name] = override_data
        else:
            # Expand the base keyword
            base_candidates = (
                copy.deepcopy(result[role_name].get("candidates", []))
                if role_name in result
                else []
            )
            expanded: list[Any] = []
            for c in candidates:
                if c == "base":
                    expanded.extend(base_candidates)
                else:
                    expanded.append(c)
            override_data["candidates"] = expanded
            result[role_name] = override_data

    return result


def validate_matrix(matrix: dict[str, Any]) -> list[str]:
    """Validate a loaded matrix.

    Checks:
    - Required ``general`` and ``fast`` roles exist.
    - All roles have ``description`` and ``candidates``.
    - ``base`` keyword does not appear in matrix file candidates
      (only valid in user overrides).

    Args:
        matrix: Loaded matrix dict (from :func:`load_matrix`).

    Returns:
        List of error strings. Empty list means valid.
    """
    errors: list[str] = []
    roles = matrix.get("roles", {})

    for required_role in ("general", "fast"):
        if required_role not in roles:
            errors.append(
                f"Required role '{required_role}' is missing from the matrix."
            )

    for role_name, role_data in roles.items():
        if not isinstance(role_data, dict):
            errors.append(
                f"Role '{role_name}': expected a mapping, got {type(role_data).__name__}."
            )
            continue

        if "description" not in role_data:
            errors.append(f"Role '{role_name}': missing 'description'.")

        if "candidates" not in role_data:
            errors.append(f"Role '{role_name}': missing 'candidates'.")
        else:
            for candidate in role_data["candidates"]:
                if candidate == "base":
                    errors.append(
                        f"Role '{role_name}': 'base' keyword found in matrix file. "
                        f"The 'base' keyword is only valid in user overrides."
                    )

    return errors


def validate_matrix_config(
    matrix: dict[str, Any],
    providers: dict[str, Any] | None = None,
    coordinator: Any = None,
) -> list[str]:
    """Validate candidate ``config:`` values against installed provider fields.

    **Closed on values, OPEN on keys.** Providers consume many config keys
    they never declare as ``ConfigField``s (e.g. ``temperature``,
    ``max_tokens``, ``thinking_budget_tokens``, ``throttle_threshold``) --
    these are legitimate provider knobs and MUST pass through silently. This
    function only flags a value when the provider explicitly declares that
    key as a ``choice`` field with a non-empty ``choices`` list and the
    candidate's value is not among them (the ``reasoning_effort: extra_high``
    class of bug: an invalid value that a provider warns about and silently
    ignores, leaving the setting inert).

    Args:
        matrix: Composed matrix ``roles`` dict.
        providers: Installed providers dict from ``coordinator.get("providers")``.
            When falsy, there is nothing to validate against and this
            returns ``[]`` immediately.
        coordinator: Optional coordinator, forwarded to
            :func:`find_provider_by_type` as a fallback source of mount plan
            config.

    Returns:
        List of error strings. Empty list means valid (or unresolvable,
        which is treated as valid -- this function never blocks a session).
    """
    if not providers:
        return []

    from .resolver import find_provider_by_type

    errors: list[str] = []

    for role_name, role_data in matrix.get("roles", {}).items():
        if not isinstance(role_data, dict):
            continue
        candidates = role_data.get("candidates", [])
        for i, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                # e.g. the "base" string keyword, valid in overrides.
                continue

            cfg = candidate.get("config") or {}
            if not cfg:
                continue

            provider = candidate.get("provider", "")
            model = candidate.get("model", "")

            match = find_provider_by_type(providers, provider, coordinator)
            if match is None:
                # Provider not installed -- we cannot and must not judge it.
                continue

            _, provider_instance = match

            try:
                info = provider_instance.get_info()
                config_fields = getattr(info, "config_fields", None)
                if config_fields is None and isinstance(info, dict):
                    config_fields = info.get("config_fields")
                config_fields = config_fields or []
            except Exception:
                # Never let validation break a session.
                continue

            field_map: dict[str, Any] = {}
            for field in config_fields:
                field_id = getattr(field, "id", None)
                if field_id is None and isinstance(field, dict):
                    field_id = field.get("id")
                if field_id is not None:
                    field_map[field_id] = field

            for key, value in cfg.items():
                field = field_map.get(key)
                if field is None:
                    # Undeclared key -- the open-key rule. Pass silently.
                    continue

                field_type = getattr(field, "field_type", None)
                if field_type is None and isinstance(field, dict):
                    field_type = field.get("field_type")

                choices = getattr(field, "choices", None)
                if choices is None and isinstance(field, dict):
                    choices = field.get("choices")

                if field_type != "choice" or not choices:
                    continue

                if str(value) not in [str(c) for c in choices]:
                    errors.append(
                        f"Role '{role_name}' candidate {i} ({provider}/{model}): "
                        f"{key}={value!r} is not valid — allowed: {', '.join(choices)}"
                    )

    return errors
