"""Matrix loader - loads and composes routing matrix YAML files."""

from __future__ import annotations

import copy
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, NamedTuple

import yaml

# ---------------------------------------------------------------------------
# Where a matrix actually came from (shadowing observability)
# ---------------------------------------------------------------------------
#
# The search order is `[*custom_routing_dirs, bundle routing/]`, first hit wins
# (``mount()`` in __init__.py). That precedence is DELIBERATE -- a user file is
# meant to beat the shipped default -- and this module does not change it.
#
# What it does change is that the outcome used to be invisible. A same-named
# file in ~/.amplifier/routing/ made the shipped matrix dead, and nothing
# logged, warned about, or exposed that fact; the winning path appeared only
# inside the "Matrix file not found" warning, i.e. only when loading FAILED.
# Every matrix change shipped in the bundle is inert on such a host, and the
# operator has no way to tell. `resolve_matrix_source` returns the whole
# picture -- winner, source, and everything the winner shadowed -- so the
# caller can say so out loud.

USER_SOURCE = "user"
BUNDLE_SOURCE = "bundle"


@dataclass(frozen=True)
class MatrixSource:
    """The resolved provenance of one named matrix.

    Attributes:
        name: The REQUESTED matrix name (the file stem, e.g. ``"openai"``),
            which is what ``amplifier routing edit <name>`` takes. This is not
            necessarily the ``name:`` field declared inside the YAML.
        path: The file that won, or ``None`` when no candidate exists.
        source: ``"user"`` or ``"bundle"`` for the winner; ``None`` when
            nothing was found.
        shadowed: ``(path, source)`` for every same-named file that exists but
            lost, in search order. Empty when nothing is shadowed.
        searched: Every candidate path considered, in precedence order.
    """

    name: str
    path: Path | None = None
    source: str | None = None
    shadowed: tuple[tuple[Path, str], ...] = ()
    searched: tuple[Path, ...] = field(default=())

    @property
    def is_shadowed(self) -> bool:
        """True when the winner suppressed at least one same-named file."""
        return bool(self.shadowed)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe telemetry payload (paths stringified)."""
        return {
            "matrix_name": self.name,
            "matrix_path": str(self.path) if self.path is not None else None,
            "matrix_source": self.source,
            "matrix_shadowed": self.is_shadowed,
            "shadowed_paths": [str(p) for p, _ in self.shadowed],
        }


def resolve_matrix_source(
    name: str,
    custom_routing_dirs: Sequence[Path],
    bundle_routing_dir: Path,
) -> MatrixSource:
    """Resolve which ``<name>.yaml`` wins, and what it shadows.

    **Precedence is unchanged** and is the single rule implemented here: the
    first existing ``<name>.yaml`` in ``[*custom_routing_dirs,
    bundle_routing_dir]`` wins. The extra return values describe that outcome;
    they never influence it.

    Two aliasing details, both of which would otherwise produce a FALSE
    shadowing report:

    * A custom dir that IS the bundle's own routing dir (or a symlink/relative
      path to it) is labelled ``"bundle"``, not ``"user"`` -- provenance is
      decided by where the file actually lives, not by which argument carried
      the directory.
    * The same file reached twice (duplicate entry, symlink, ``.`` segments)
      is counted once. A file cannot shadow itself.

    Args:
        name: Matrix name without the ``.yaml`` suffix.
        custom_routing_dirs: User routing dirs, highest priority first.
        bundle_routing_dir: The bundle's own ``routing/`` dir (lowest priority).

    Returns:
        A :class:`MatrixSource`. ``path`` is ``None`` when no candidate exists.
    """
    filename = f"{name}.yaml"

    def _key(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:  # pragma: no cover - exotic filesystem states
            return path

    bundle_key = _key(bundle_routing_dir)

    candidates: list[tuple[Path, str]] = [
        (
            Path(d) / filename,
            BUNDLE_SOURCE if _key(Path(d)) == bundle_key else USER_SOURCE,
        )
        for d in custom_routing_dirs
    ]
    candidates.append((bundle_routing_dir / filename, BUNDLE_SOURCE))

    searched: list[Path] = []
    present: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for candidate, origin in candidates:
        candidate_key = _key(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        searched.append(candidate)
        if candidate.exists():
            present.append((candidate, origin))

    if not present:
        return MatrixSource(name=name, searched=tuple(searched))

    winner, winner_source = present[0]
    return MatrixSource(
        name=name,
        path=winner,
        source=winner_source,
        shadowed=tuple(present[1:]),
        searched=tuple(searched),
    )


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
# Inert config keys: settings the target will never act on
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS, AND WHY validate_matrix_config CANNOT DO IT
#
# `validate_matrix_config` above is closed on VALUES and OPEN on KEYS: it flags
# a config value only when the provider DECLARES that key as a `choice` field
# and the value is not among the declared choices (:217-238). A key the
# provider does not declare at all takes the explicit "undeclared key -- the
# open-key rule. Pass silently" branch (:219-221).
#
# That branch is exactly where `reasoning_effort` on a `gemini` candidate
# lands. provider-gemini declares ONE ConfigField (`api_key`) and consumes a
# closed set of 15 mount-config keys, none of which is an effort key -- so the
# key passes validation, is merged into the child provider's mount config, and
# is then read by nobody. The value is irrelevant: `low`, `high`, `xhigh` and
# `max` are equally inert, because the read never happens.
#
# This is a THIRD check asking a different question from the other two: not
# "is this value legal for this provider?" but "will this target act on this
# KEY at all?"
#
# WHY THE TABLE IS KEYED ON (provider, model) AND NOT ON MODEL ALONE
#
# Two distinct shapes of this defect exist, and they key differently:
#
#   * PROVIDER-keyed (gemini): the provider never reads the key from mount
#     config, so EVERY model it serves is affected. Keying on the model would
#     need one row per model id and would silently miss the next one Google
#     ships.
#   * MODEL-keyed (haiku): the provider DOES read the key, but one model
#     collapses every level above `low` into one identical request. The
#     provider is fine; one model is not. Keying on the provider would reject
#     effort on every Anthropic model, most of which honour it.
#
# BOTH shapes are now enforced here, in ONE table. Neither special case
# generalises to the other -- a model-keyed table cannot express gemini
# without one row per model id, and a provider-keyed table cannot express
# haiku at all, since anthropic-the-provider is fine. A single table with a
# provider field and a model-substring field expresses both, so a third
# finding is a new ROW rather than a third mechanism. Two mechanisms would
# mean two places to look, two chances to strip the wrong key, and -- the real
# hazard -- two possible answers to "is this key live on this candidate?"
# that can disagree.
#
# The per-row `remediation` callable is what makes one table possible without
# losing precision: haiku's exact replacement is a `thinking_budget_tokens`
# number, gemini's is an `extra_request_params.thinking_config` block. One
# shared remediation sentence structurally could not name both.
#
# SCOPE, STATED HONESTLY: this table is not a general capability model. It
# carries only rules backed by a cited provider code path or a named
# measurement. A (provider, model) pair absent from it is NOT asserted to
# honour anything -- it is simply a pair this guard has no evidence about.

# Both spellings a matrix candidate can use for the portable effort knob.
# provider-anthropic consumes the canonical `reasoning_effort` and the legacy
# `effort` alias (provider-anthropic __init__.py:892-897, :3452-3455), so a
# curator can reasonably write either; a guard covering only one spelling
# leaves the other silently dropping.
EFFORT_KEYS: tuple[str, ...] = ("effort", "reasoning_effort")

# provider-gemini's effort -> thinking_level ladder, mirrored here so the
# remediation can name the EXACT level a given effort value targets rather
# than offering generic advice (provider-gemini __init__.py:348-355).
_GEMINI_EFFORT_TO_LEVEL: dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}

_GEMINI_EFFORT_REASON = (
    "provider-gemini never reads an effort key from mount config, so this "
    "setting is inert at EVERY value -- not collapsed, not clamped, simply "
    "never read. VERIFIED against the installed provider "
    "(amplifier-module-provider-gemini, cache 06d1437d03d6b064): the closed "
    "set of mount-config keys it consumes is _CONSUMED_CONFIG_KEYS "
    "(__init__.py:551-566) and contains neither 'reasoning_effort' nor "
    "'effort'; there is no `self.config.get(\"reasoning_effort\")` call site "
    "anywhere in the module; and its only declared ConfigField is `api_key` "
    "(__init__.py:832-840). The provider's single effort read is "
    "`request.reasoning_effort` (__init__.py:1325) -- a ChatRequest field, "
    "which amplifier_core only DECLARES (message_models.py:212) and never "
    "populates from mount config. Bridging config -> request is each "
    "provider's own job (anthropic does it at __init__.py:892-897, openai at "
    "__init__.py:1046-1049); gemini has no such bridge, so a matrix `config:` "
    "block cannot reach the effort ladder at all."
)


def _gemini_effort_remediation(model: str, value: Any) -> str:
    """Return the exact replacement setting for an inert gemini effort value.

    Naming the replacement knob without its value is not actionable; naming
    the WRONG value silently changes behaviour. Gemini's thinking control is
    also split by model generation, and getting that wrong turns an inert key
    into a hard 400 -- so the split is named here rather than left for the
    curator to discover in production.
    """
    level = _GEMINI_EFFORT_TO_LEVEL.get(str(value).strip().lower())
    target = (
        f"`extra_request_params: {{thinking_config: {{thinking_level: {level}}}}}`"
        if level is not None
        else "`extra_request_params: {thinking_config: {...}}`"
    )
    return (
        f"Use {target} instead -- `extra_request_params` is the only "
        f"mount-config key gemini merges into the outgoing request "
        f"(provider-gemini __init__.py:571-611, read at :752), and "
        f"thinking_level is what the effort ladder targets (:348-355). "
        f"CAUTION: gemini-2.x models REJECT thinking_level outright with a "
        f"400 and accept only the legacy `thinking_budget` "
        f"(_THINKING_LEVEL_TABLE, :318-336), so a class glob like "
        f"`gemini-*-pro-preview` that can resolve to a 2.x id must pin an "
        f"exact 3.x model before using thinking_level."
    )


# --- MODEL-keyed row: anthropic haiku ---------------------------------
#
# Carried over VERBATIM from the haiku guard this table subsumes (PR #48,
# commit 68bba65). That lane made the wire measurement; this one only
# re-homes the rule into the generic table, so the reason string and the
# per-value remediation are unchanged from the measurement that earned
# them.
#
# `provider="*"` deliberately, NOT `provider="anthropic"`: the guard on
# main matched the model substring under ANY provider name, and narrowing
# it here would silently stop rejecting an inert effort key on a haiku
# model served under some other provider id. The wildcard preserves the
# shipped matching semantics exactly.
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


def _haiku_remediation(model: str, value: Any) -> str:
    """Return the exact replacement setting for an inert haiku effort value.

    Naming the replacement knob without its value is not actionable; naming
    the WRONG value silently changes behaviour. On Haiku ``low`` and the
    collapsed tiers have genuinely different equivalents, so the remediation
    is resolved per value rather than as one fixed sentence.

    This is PR #48's ``effort_remediation`` unchanged apart from its name:
    its ``(model, value) -> str`` signature already matches this table's
    ``remediation`` field.
    """
    normalized = str(value).strip().lower()
    budget = _HAIKU_BUDGETS.get(normalized, _HAIKU_DEFAULT_BUDGET)
    return (
        f"Use `thinking_budget_tokens: {budget}` instead -- that is the exact "
        f"request this effort level already resolves to, made explicit."
    )


class InertKeyRule(NamedTuple):
    """One (provider, model) -> inert-keys rule.

    Attributes:
        provider: Exact provider name to match, or ``"*"`` for any provider.
        model_marker: Lowercase substring the candidate's ``model`` must
            contain, or ``""`` to match any model of that provider. Substring
            matching catches every spelling a candidate can use -- globs
            (``gemini-*-pro-preview``), exact ids, and provider-qualified
            forms alike.
        keys: The config keys this rule rejects.
        reason: Named, evidence-carrying reason the keys are inert.
        remediation: ``(model, value) -> sentence`` naming the exact
            replacement setting.
    """

    provider: str
    model_marker: str
    keys: tuple[str, ...]
    reason: str
    remediation: Callable[[str, Any], str]


# The enforced rules. One row per (provider, model) pair with evidence.
#
# ORDER MATTERS: the first matching row wins. The provider-specific gemini row
# is listed before the `provider="*"` haiku row so a wildcard row can never
# shadow a narrower one.
INERT_CONFIG_RULES: tuple[InertKeyRule, ...] = (
    InertKeyRule(
        provider="gemini",
        model_marker="",  # every model this provider serves
        keys=EFFORT_KEYS,
        reason=_GEMINI_EFFORT_REASON,
        remediation=_gemini_effort_remediation,
    ),
    InertKeyRule(
        provider="*",  # matched on the MODEL substring, under any provider
        model_marker="haiku",
        keys=EFFORT_KEYS,
        reason=_HAIKU_REASON,
        remediation=_haiku_remediation,
    ),
)


def inert_config_rule(provider: str, model: str, key: str) -> InertKeyRule | None:
    """Return the rule making ``key`` inert for this candidate, or ``None``.

    Args:
        provider: The candidate's ``provider`` value.
        model: The candidate's ``model`` value. May be a glob, an exact id,
            or provider-qualified.
        key: The config key being checked.

    Returns:
        The matching :class:`InertKeyRule`, or ``None`` when this guard has
        no evidence that the key is inert for this candidate.
    """
    if not isinstance(provider, str) or not isinstance(key, str):
        return None
    model_needle = model.lower() if isinstance(model, str) else ""
    provider_needle = provider.lower()
    for rule in INERT_CONFIG_RULES:
        if rule.provider != "*" and rule.provider.lower() != provider_needle:
            continue
        if rule.model_marker and rule.model_marker not in model_needle:
            continue
        if key in rule.keys:
            return rule
    return None


def validate_matrix_inert_config(matrix: dict[str, Any]) -> list[str]:
    """Reject config keys the candidate's target will never act on.

    Complements :func:`validate_matrix_config`, which structurally cannot
    catch this class: the key is undeclared, so the open-key rule passes it
    silently, and the value is irrelevant because the read never happens.

    Unlike :func:`validate_matrix_config` this needs no provider instances and
    no coordinator -- it is a pure function of the composed matrix, so it runs
    even when providers are not installed or not resolvable.

    Args:
        matrix: Composed matrix dict with a ``roles`` key (the same shape
            :func:`validate_matrix_config` takes).

    Returns:
        List of named error strings. Empty list means no inert keys found.
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

            provider = candidate.get("provider", "")
            model = candidate.get("model", "")
            for key in cfg:
                rule = inert_config_rule(provider, model, key)
                if rule is None:
                    continue
                errors.append(
                    f"Role '{role_name}' candidate {i} ({provider}/{model}): "
                    f"{key}={cfg[key]!r} is REJECTED — {rule.reason} "
                    f"{rule.remediation(model, cfg[key])}"
                )

    return errors


def strip_inert_config(
    matrix: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Return a copy of ``matrix`` with inert config keys removed.

    Rejection is enforced structurally, not merely reported. Once
    :func:`validate_matrix_inert_config` has named the offending keys they are
    removed from the effective matrix, so no downstream consumer (resolver,
    delegate, session naming) can carry a setting the target will never act on
    and report it as applied. Logging alone would leave the dead setting in
    place -- which is the state that let 14 shipped candidates carry an inert
    effort knob.

    Removing the key changes NO wire behaviour: it was never read.

    Args:
        matrix: Composed matrix dict with a ``roles`` key. Not mutated.

    Returns:
        ``(cleaned_matrix, errors)`` -- the cleaned copy and the same named
        errors :func:`validate_matrix_inert_config` would return. When there
        is nothing to strip the ORIGINAL object is returned, so a clean matrix
        costs no copy.
    """
    errors = validate_matrix_inert_config(matrix)
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
            provider = candidate.get("provider", "")
            model = candidate.get("model", "")
            for key in list(cfg):
                if inert_config_rule(provider, model, key) is not None:
                    cfg.pop(key, None)
    return cleaned, errors
