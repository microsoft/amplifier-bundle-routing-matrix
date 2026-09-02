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


# ---------------------------------------------------------------------------
# Model-aware effort support
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS, AND WHY validate_matrix_config CANNOT DO IT
#
# `validate_matrix_config` above is closed on VALUES and OPEN on KEYS: it flags
# a config value only when the provider declares that key as a `choice` field
# and the value is not among the declared choices (see :219-221). That is
# exactly the wrong shape for this defect.
#
# `reasoning_effort: high` on a `claude-haiku-*` candidate is a DECLARED key
# (provider-anthropic declares it, __init__.py:1017) carrying a LEGAL value on
# an INSTALLED provider -- so it sails through. It then rides all the way into
# the effective matrix, is handed to the child provider as mount config, and is
# collapsed to nothing at request-build time. Nothing logs anything. The
# operator is told the effort was applied; the wire says otherwise.
#
# This function is a THIRD check with a different question: not "is this value
# legal for this provider?" but "will this MODEL do anything with it?"
#
# SCOPE, STATED HONESTLY: this table is not a general capability model. It
# carries only rules backed by a named measurement or a cited provider code
# path. A model absent from the table is not asserted to honour effort -- it is
# simply not something this guard has evidence about. See the PR body for the
# gemini finding, which is real but not enforced here.

# Both spellings a matrix candidate can use. provider-anthropic consumes the
# canonical `reasoning_effort` and the legacy `effort` alias
# (provider-anthropic __init__.py:641-654, :2926-2936); a guard covering only
# one spelling leaves the other silently dropping.
EFFORT_KEYS: tuple[str, ...] = ("effort", "reasoning_effort")

_HAIKU_REASON = (
    "Anthropic Haiku collapses every effort level above 'low' into one "
    "identical request, so the knob measures nothing. MEASURED on the wire "
    "(20260901-threeknob capture root, effort attributed per request by "
    "joining to that request's own `model` field): across 1,438 "
    "claude-haiku-4-5 requests the effort parameter was ABSENT and "
    "thinking.budget_tokens was pinned at 32000 regardless of the effort the "
    "cell asked for -- anth-haiku-high (n=702) and anth-haiku-medium (n=736) "
    "were byte-identical configurations, making two of sixteen cells "
    "duplicates. MECHANISM: haiku has supports_output_config=False and "
    "supports_adaptive_thinking=False (provider-anthropic "
    "__init__.py:1541-1550), so the effort ladder resolves medium/high/xhigh/"
    "max to the same default_thinking_budget=32000 and the adaptive branch "
    "falls back to type='enabled' (provider-anthropic __init__.py:3024-3046)."
)

# Models that do NOT honour a reasoning-effort parameter as a gradient.
# Each entry is (lowercase model-name substring, named reason).
# Matching is substring-on-lowercase so it catches every spelling a candidate
# can use: `claude-haiku-*`, `claude-haiku-4.5`, `claude-haiku-4-5-20251001`,
# and any provider-qualified form.
EFFORT_UNSUPPORTED_MODELS: tuple[tuple[str, str], ...] = (("haiku", _HAIKU_REASON),)

# The exact `thinking_budget_tokens` value that reproduces each effort level on
# an affected model, so the error can name a lossless replacement rather than
# generic advice. Haiku's ladder: 'low' -> 4096, everything above -> the model
# default 32000 (provider-anthropic __init__.py:3026-3046).
_HAIKU_BUDGETS: dict[str, int] = {
    "low": 4096,
    "medium": 32000,
    "high": 32000,
    "xhigh": 32000,
    "max": 32000,
}
_HAIKU_DEFAULT_BUDGET = 32000


def model_ignores_effort(model: str) -> str | None:
    """Return the named reason a model ignores effort, or ``None``.

    Args:
        model: The candidate's ``model`` value. May be a glob
            (``claude-haiku-*``), an exact id, or provider-qualified.

    Returns:
        The named reason string when the model does not honour a
        reasoning-effort parameter, otherwise ``None``.
    """
    if not isinstance(model, str) or not model:
        return None
    needle = model.lower()
    for marker, reason in EFFORT_UNSUPPORTED_MODELS:
        if marker in needle:
            return reason
    return None


def effort_remediation(model: str, value: Any) -> str | None:
    """Return the exact replacement setting for an inert effort value.

    Naming the replacement knob without its value is not actionable; naming the
    WRONG value silently changes behaviour. On Haiku ``low`` and the collapsed
    tiers have genuinely different equivalents, so the remediation is resolved
    per value rather than as one fixed sentence.

    Args:
        model: The candidate's ``model`` value.
        value: The effort value the candidate set.

    Returns:
        A remediation sentence, or ``None`` when the model honours effort.
    """
    if model_ignores_effort(model) is None:
        return None
    normalized = str(value).strip().lower()
    budget = _HAIKU_BUDGETS.get(normalized, _HAIKU_DEFAULT_BUDGET)
    return (
        f"Use `thinking_budget_tokens: {budget}` instead -- that is the exact "
        f"request this effort level already resolves to, made explicit."
    )


def validate_matrix_model_support(matrix: dict[str, Any]) -> list[str]:
    """Reject effort keys on candidates whose model will not honour them.

    Complements :func:`validate_matrix_config`, which cannot catch this class:
    the key is declared, the value is legal, the provider is installed -- and
    the parameter still does nothing, because the *model* collapses it.

    Unlike :func:`validate_matrix_config` this needs no provider instances and
    no coordinator: it is a pure function of the composed matrix, so it runs
    even when providers are not resolvable.

    Args:
        matrix: Composed matrix dict with a ``roles`` key (the same shape
            :func:`validate_matrix_config` takes).

    Returns:
        List of named error strings. Empty list means no inert effort keys
        were found.
    """
    errors: list[str] = []

    for role_name, role_data in (matrix.get("roles") or {}).items():
        if not isinstance(role_data, dict):
            continue
        for i, candidate in enumerate(role_data.get("candidates") or []):
            if not isinstance(candidate, dict):
                # e.g. the "base" string keyword, valid in overrides.
                continue
            cfg = candidate.get("config") or {}
            if not isinstance(cfg, dict) or not cfg:
                continue

            model = candidate.get("model", "")
            reason = model_ignores_effort(model)
            if reason is None:
                continue

            provider = candidate.get("provider", "")
            for key in EFFORT_KEYS:
                if key not in cfg:
                    continue
                errors.append(
                    f"Role '{role_name}' candidate {i} ({provider}/{model}): "
                    f"{key}={cfg[key]!r} is REJECTED — {reason} "
                    f"{effort_remediation(model, cfg[key])}"
                )

    return errors


def strip_unsupported_effort(
    matrix: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Return a copy of ``matrix`` with inert effort keys removed.

    Rejection is enforced structurally, not merely reported. Once
    :func:`validate_matrix_model_support` has named the offending keys they are
    removed from the effective matrix, so no downstream consumer (resolver,
    delegate, session naming) can carry an effort the model will never honour
    and report it as applied. Logging alone would leave the dead setting in
    place -- which is the state that let two byte-identical cells run for a
    whole wave.

    Args:
        matrix: Composed matrix dict with a ``roles`` key. Not mutated.

    Returns:
        ``(cleaned_matrix, errors)`` -- the cleaned copy and the same named
        errors :func:`validate_matrix_model_support` would return. When there
        is nothing to strip the ORIGINAL object is returned, so a clean matrix
        costs no copy.
    """
    errors = validate_matrix_model_support(matrix)
    if not errors:
        return matrix, errors

    cleaned = copy.deepcopy(matrix)
    for role_data in (cleaned.get("roles") or {}).values():
        if not isinstance(role_data, dict):
            continue
        for candidate in role_data.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            cfg = candidate.get("config")
            if not isinstance(cfg, dict) or not cfg:
                continue
            if model_ignores_effort(candidate.get("model", "")) is None:
                continue
            for key in EFFORT_KEYS:
                cfg.pop(key, None)
    return cleaned, errors
