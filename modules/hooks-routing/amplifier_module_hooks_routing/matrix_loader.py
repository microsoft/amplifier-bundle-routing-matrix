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
