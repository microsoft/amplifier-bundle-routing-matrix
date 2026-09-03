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


def _get_provider_specs(coordinator: Any) -> list[dict[str, Any]]:
    """Best-effort fetch of the mount plan's provider config list.

    ``coordinator.config`` is a stable, documented property of
    ``amplifier_core``'s coordinator, used elsewhere in the ecosystem to read
    back ``module``/``id`` metadata for mounted instances (see the sibling
    fix in ``amplifier_foundation.spawn_utils._find_provider_instance``).
    This helper degrades gracefully to an empty list for any coordinator-like
    object that doesn't expose it (e.g. ``None``, bare test doubles), rather
    than raising.
    """
    config = getattr(coordinator, "config", None)
    if not isinstance(config, dict):
        return []
    specs = config.get("providers", [])
    return specs if isinstance(specs, list) else []


def _spec_for_instance(
    provider_specs: list[dict[str, Any]], instance_id: str
) -> dict[str, Any] | None:
    """Find the mount plan config spec matching a runtime provider instance name."""
    for spec in provider_specs:
        if not isinstance(spec, dict):
            continue
        spec_id = spec.get("id") or spec.get("module", "")
        if spec_id == instance_id:
            return spec
    return None


def _module_type_of(spec: dict[str, Any] | None) -> str | None:
    """Extract the bare module type (e.g. "anthropic") from a provider spec."""
    if spec is None:
        return None
    module = spec.get("module", "")
    if not module:
        return None
    return module.replace("provider-", "")


def _instance_serves_model(spec: dict[str, Any] | None, model_pattern: str) -> bool:
    """Whether this instance's own ``default_model`` satisfies *model_pattern*.

    Used to break the bare-type fallback tie by INTENT rather than by
    priority alone. An instance whose ``default_model`` already matches the
    candidate's model pattern was configured *for that model*, so its
    remaining knobs (``reasoning_effort``, ``fallback_on_overload``,
    ``enable_1m_context``, ...) are the ones tuned for it.

    Returns False for any spec that declares no ``default_model`` -- such an
    instance expresses no model intent, so it can only be selected by the
    priority tie-break (preserving pre-existing behaviour exactly).
    """
    if spec is None or not model_pattern:
        return False
    default_model = spec.get("config", {}).get("default_model", "")
    if not isinstance(default_model, str) or not default_model:
        return False

    have = default_model.lower()
    want = model_pattern.lower()
    if _is_glob(model_pattern):
        return fnmatch.fnmatch(have, want)
    # Exact patterns: an instance pinned to a dated snapshot of the same
    # model still serves it (claude-haiku-4-5 vs claude-haiku-4-5-20251001).
    return have == want or _DATE_SUFFIX_RE.sub("", have) == _DATE_SUFFIX_RE.sub(
        "", want
    )


def find_provider_by_type(
    providers: dict[str, Any],
    type_name: str,
    coordinator: Any = None,
    model_pattern: str = "",
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
        coordinator: Optional coordinator, used as a fallback source of mount
            plan config (module/id/priority) when ``type_name`` is a bare
            module type that doesn't match any dict key directly (see
            fallback below).
        model_pattern: Optional model name or glob from the same matrix
            candidate (e.g. ``"claude-haiku-*"``). Used ONLY in the fallback
            below, to break the multi-instance tie by model intent before
            falling back to priority. Omitting it preserves the exact
            pre-existing priority-only behaviour.

    Returns:
        ``(module_id, provider_instance)`` or ``None``.

    Matching strategy:
        1. Exact key, "provider-" prefix stripped, or "provider-" prefix
           added — covers the single-instance case and any instance
           explicitly keyed by the bare type.
        2. Fallback: if ``type_name`` is a bare module type (e.g.
           "anthropic") and no provider is keyed by it directly, this
           happens when 2+ instances of that module each have a distinct
           explicit ``id:`` (needed for routing-matrix disambiguation) and
           none of them is the bare type itself. Search the mount plan's
           provider config list for every instance whose underlying module
           type matches. Among those, prefer any instance whose own
           ``default_model`` satisfies *model_pattern* — that instance was
           configured FOR this model, so its knobs
           (``reasoning_effort``, ``fallback_on_overload``, ...) are the
           ones tuned for it, and ``spawn_utils._apply_single_override``
           clones the WHOLE config of whichever instance is returned here.
           Only when no instance declares a matching ``default_model`` does
           this fall back to the one configured with the highest priority
           (lowest priority number) — mirroring the "default provider"
           convention used elsewhere in the ecosystem.
    """
    for name, provider in providers.items():
        if type_name in (
            name,
            name.replace("provider-", ""),
            f"provider-{type_name}",
        ):
            return (name, provider)

    provider_specs = _get_provider_specs(coordinator)
    if not provider_specs:
        return None

    candidates: list[tuple[int, str]] = []
    model_matched: list[tuple[int, str]] = []
    for name in providers:
        spec = _spec_for_instance(provider_specs, name)
        if _module_type_of(spec) == type_name:
            assert spec is not None  # narrowed by _module_type_of returning non-None
            priority = spec.get("config", {}).get("priority", 0)
            candidates.append((priority, name))
            if _instance_serves_model(spec, model_pattern):
                model_matched.append((priority, name))

    if not candidates:
        return None

    # Prefer an instance configured FOR this model over the bare
    # highest-priority one.
    #
    # The priority-only tie-break is correct while every instance of a module
    # type is interchangeable, but it is actively wrong once instances are
    # differentiated BY MODEL -- the common multi-instance Anthropic setup
    # (an opus instance, a sonnet instance, a haiku instance, each carrying
    # the knobs tuned for its own tier). There, a `fast` role asking for
    # `provider: anthropic, model: claude-haiku-*` resolved to whichever
    # instance held the lowest priority number -- typically the *opus*
    # instance -- and amplifier_foundation.spawn_utils._apply_single_override
    # then clones that instance's ENTIRE config, overriding only
    # `default_model`. The child provider mounted as haiku while still
    # carrying opus's `reasoning_effort: xhigh`, `fallback_on_overload: true`
    # and `enable_1m_context: true`, none of which haiku honours -- producing
    # the paired provider warnings:
    #
    #   [PROVIDER] fallback_on_overload is enabled for
    #     default_model='claude-haiku-4-5-20251001' (family 'haiku'), but
    #     'haiku' is the lowest tier on the Anthropic fallback ladder ...
    #   [PROVIDER] reasoning_effort='xhigh' has no effect on
    #     claude-haiku-4-5-20251001 (no output_config support) ...
    #
    # -- while the purpose-built haiku instance sat unused. Matching on the
    # instance's own `default_model` picks the instance whose configuration
    # was actually written for the requested model.
    #
    # Strictly narrowing: an instance is only preferred when it declares a
    # `default_model` that matches. When no instance declares one, or none
    # matches, `model_matched` is empty and the priority-only tie-break below
    # runs byte-identically to before.
    pool = model_matched or candidates
    pool.sort(key=lambda t: t[0])
    best_name = pool[0][1]

    if model_matched:
        candidates.sort(key=lambda t: t[0])
        priority_only_name = candidates[0][1]
        if priority_only_name != best_name:
            # Observable, not silent: this is a routing decision a curator
            # reading the matrix alone cannot see.
            logger.info(
                "Provider instance for bare type %r resolved by model intent: "
                "%r (default_model matches %r) instead of %r (priority-only "
                "pick)",
                type_name,
                best_name,
                model_pattern,
                priority_only_name,
            )

    return (best_name, providers[best_name])


async def resolve_model_role(
    roles: list[str],
    matrix: dict[str, Any],
    providers: dict[str, Any],
    preresolved_models: dict[str, list[str]] | None = None,
    coordinator: Any = None,
    caller_context: Any = None,
    preset: Any = None,
    escalations: Any = None,
    on_clamp: Any = None,
) -> list[dict[str, Any]]:
    """Resolve model role(s) against routing matrix.

    Args:
        roles: Prioritised list of role names to try.
        matrix: Composed matrix ``roles`` dict (from :mod:`matrix_loader`).
        providers: Installed providers dict from ``coordinator.get("providers")``.
        preresolved_models: Optional mutable dict of ``provider_type ->
            model_names``.  When provided, :func:`_resolve_glob` reads from it
            to skip ``list_models()`` HTTP calls for providers whose model list
            was already fetched (e.g. by the parent session).
            :func:`_resolve_glob` also writes newly-fetched lists back into the
            dict, so subsequent calls for the same provider within the same
            session are also free.

            **Asyncio safety:** the dict is shared across concurrently-running
            ``_resolve_one`` coroutines (via ``asyncio.gather``).  Because
            asyncio is cooperative and single-threaded, dict reads and writes
            never interleave — a coroutine only yields at explicit ``await``
            points, and dict mutation is a non-awaited operation.
        coordinator: Optional coordinator, forwarded to
            :func:`find_provider_by_type` as a fallback source of mount plan
            config when a matrix candidate's ``provider:`` is a bare module
            type (e.g. ``"anthropic"``) that isn't a key in ``providers``
            directly — the case where 2+ named instances of that module
            exist but none is keyed by the bare type itself.
        caller_context: Optional ``CallerContext`` (see
            :mod:`amplifier_module_hooks_routing.knob_consistency`) -- the
            calling session's own resolved (family, model, effort). This is
            the level-3 "inherited caller intent" slot of the precedence
            chain. **Default-off:** when this or *preset* is ``None``, or the
            preset's ``inherit`` mode is ``none``, the loop below runs exactly
            as it did before knob-consistent routing existed.
        preset: Optional parsed ``Preset``.
        escalations: Optional per-session ``EscalationState``.
        on_clamp: Optional callable invoked with the ``ClampRecord`` for the
            role that actually resolved. Emit-only: the record goes to the
            event log, never into the conversation.

    Returns:
        List of ``{provider, model, config}`` dicts representing resolved
        preferences.  Empty if no role resolves.

        The ``"provider"`` value is the *actual mounted key* that
        :func:`find_provider_by_type` matched in ``providers`` -- NOT
        necessarily the bare ``provider:`` string written in the matrix
        candidate. For the common case (a candidate's bare type is itself
        a key in ``providers``, or differs from one only by the
        "provider-" prefix) these are the same string, so this is a no-op.
        They diverge only when resolution went through the coordinator
        fallback (an instance mounted under an explicit ``id:`` that
        doesn't match the bare type via any of the three simple string
        forms, e.g. matrix says ``provider: anthropic`` but the only
        installed instance is mounted as ``anthropic-opus``). In that
        case, returning the bare type here would hand every downstream
        consumer (loop-streaming's goal-model resolution, hooks-session-
        naming) a string that can never re-match ``anthropic-opus`` via
        their own exact/prefix-based lookups -- reproducing the exact
        "resolved to provider 'anthropic', which is not mounted/installed"
        defect this fixes. Returning the matched key means every consumer
        that re-resolves this string against the same ``providers`` dict
        (or, for tool-delegate's mount-plan path,
        ``amplifier_foundation.spawn_utils._build_provider_lookup()``,
        which already indexes by ``id:``) finds an exact hit.
    """
    # Level 3 of the precedence chain. `plan_candidates` returns its input
    # unchanged, and a None record, whenever the feature is off -- so when no
    # preset is active this block is a no-op and the loop below is the one
    # that shipped before this feature existed.
    _knob_active = preset is not None and getattr(preset, "active", False)

    for role in roles:
        role_data = matrix.get(role)
        if role_data is None:
            continue

        candidates = role_data.get("candidates", [])
        clamp_record = None
        if _knob_active:
            from .knob_consistency import plan_candidates

            candidates, clamp_record = plan_candidates(
                role, candidates, caller_context, preset, escalations
            )

        for candidate in candidates:
            provider_type = candidate.get("provider", "")
            model_pattern = candidate.get("model", "")
            config = candidate.get("config", {})

            # Is this provider installed?
            match = find_provider_by_type(
                providers, provider_type, coordinator, model_pattern=model_pattern
            )
            if match is None:
                continue

            matched_name, provider_instance = match

            # Is the model pattern a glob?
            if _is_glob(model_pattern):
                resolved_model = await _resolve_glob(
                    model_pattern,
                    provider_instance,
                    provider_key=provider_type,
                    preresolved_models=preresolved_models,
                )
                if resolved_model is None:
                    continue
            else:
                resolved_model = model_pattern

            # Report only for the role that actually resolved -- a record for
            # a role that fell through would describe a decision nothing
            # acted on. Emit, never inject.
            if clamp_record is not None and on_clamp is not None:
                try:
                    await on_clamp(clamp_record)
                except Exception:  # pragma: no cover - reporting must not break routing
                    logger.warning("routing clamp reporting failed", exc_info=True)

            return [
                {
                    # The mounted key find_provider_by_type() actually
                    # matched -- see the docstring above for why this must
                    # not be provider_type (the matrix's bare type string).
                    "provider": matched_name,
                    "model": resolved_model,
                    "config": config,
                }
            ]

    return []


async def _resolve_glob(
    pattern: str,
    provider: Any,
    provider_key: str = "",
    preresolved_models: dict[str, list[str]] | None = None,
) -> str | None:
    """Resolve a glob model pattern against a provider's model list.

    Uses natural-sort ordering (see :func:`_version_sort_key`) so that:

    * Higher version numbers win (``claude-opus-4-10`` > ``claude-opus-4-7``).
    * Clean-versioned IDs outrank snapshot IDs with date suffixes
      (``claude-opus-4-7`` > ``claude-opus-4-20250514``).
    * Shorter aliases outrank pinned snapshots on equal primary keys
      (``gpt-5.4`` > ``gpt-5.4-2026-03-05``).

    When *preresolved_models* is provided and *provider_key* is already present
    in it, ``list_models()`` is skipped entirely — the stored list is used
    directly.  When the list must be fetched, it is written back into
    *preresolved_models* under *provider_key* so future calls are free.

    Returns the highest-ranked matching model name or ``None`` when no
    candidate matches or the provider's ``list_models()`` raises.
    """
    if preresolved_models is not None and provider_key in preresolved_models:
        model_names = preresolved_models[provider_key]
    else:
        try:
            available = await provider.list_models()
        except Exception:
            logger.warning(
                "Failed to list models for glob pattern '%s'", pattern, exc_info=True
            )
            return None

        # Normalise to list of strings
        model_names = [
            m if isinstance(m, str) else getattr(m, "id", str(m)) for m in available
        ]

        if preresolved_models is not None and provider_key:
            preresolved_models[provider_key] = model_names

    # Case-insensitive, OS-independent glob matching: lowercase both sides
    # before comparing (raw fnmatch.filter() uses os.path.normcase, which is
    # case-sensitive on Linux/Mac and case-insensitive on Windows -- an
    # OS-dependent inconsistency). This matches the canonical model-glob
    # semantics used by amplifier_foundation.spawn_utils (agent-spawn model
    # resolution) and the unified-llm-client reference implementation, so a
    # pattern like "Qwen3.6-*" deterministically matches "qwen3.6-35b-..."
    # on every platform. Original casing is preserved in the returned name.
    lowered_pattern = pattern.lower()
    matched = [m for m in model_names if fnmatch.fnmatch(m.lower(), lowered_pattern)]
    if not matched:
        return None

    matched.sort(key=_version_sort_key, reverse=True)
    return matched[0]
