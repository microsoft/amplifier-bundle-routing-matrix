"""Routing matrix hook module.

Provides model routing based on curated role-to-provider matrices.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Placement of the routing-matrix banner (system-reminder redesign, W3):
#   "prefix"  (default) -- wraps the context module's system-prompt factory
#       (the surface amplifier-foundation _prepared.py registers via
#       context.set_system_prompt_factory; context-simple calls it on EVERY
#       get_messages_for_request) so the banner rides the provider-cached
#       system block instead of being re-sent as fresh input tokens every
#       request. Sessions without a factory surface fall back to "inject"
#       with a one-time WARNING.
#   "inject" -- inject_context on every provider:request (pre-redesign
#       behavior, `1e329ce`). Explicit, fully supported rollback lever.
# The wrapper (<system-reminder source="routing-matrix">) and the pinned
# context_injection_role="user" are NOT behind this flag -- they are
# unconditional defects fixes, not preferences (reminder-redesign-spec.md
# section 9).
VALID_PLACEMENTS = ("prefix", "inject")

# The source-attributed marker this module's own banner always opens with
# (see _render_banner). Used as a CONTENT signal in _ensure_prefix_placement
# (rr wave 20260831, D1 cache-regression fix) -- see that function's
# docstring for why identity alone is not a safe re-wrap check once more
# than one hook wraps the same system-prompt-factory slot.
_PREFIX_MARKER = '<system-reminder source="routing-matrix">'


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the routing matrix hook.

    Loads the default matrix, composes with user overrides, registers
    ``session:start`` and ``provider:request`` hooks.
    """
    config = config or {}

    placement = config.get("placement", "prefix")
    if placement not in VALID_PLACEMENTS:
        raise ValueError(
            f"Invalid placement={placement!r}. "
            f"Valid values: {', '.join(VALID_PLACEMENTS)}."
        )

    # model_performance-74w: restore this session's own model_role pin at
    # session:start when the live mount ordering has drifted away from it
    # (a RESUME re-imposes settings priority over a child's promotion --
    # upstream defect model_performance-rc0). No-op unless there is a real
    # disagreement; see role_pin.reassert_own_role_pin. Escape hatch for an
    # operator who wants the pre-fix behaviour back.
    reassert_role_pin: bool = config.get("reassert_role_pin", True)

    from .matrix_loader import (
        compose_matrix,
        load_matrix,
        resolve_matrix_source,
        strip_inert_config,
        validate_matrix_config,
    )

    # --- Locate the routing directory ---
    # Accept an explicit override for testing; otherwise use __file__ traversal
    bundle_root_override = config.pop("_bundle_root", None)
    if bundle_root_override:
        bundle_root = Path(bundle_root_override)
    else:
        # Auto-discover via __file__ path traversal (modes pattern)
        #   __file__  = .../amplifier_module_hooks_routing/__init__.py
        #   parent    = .../amplifier_module_hooks_routing/
        #   parent x2 = .../hooks-routing/
        #   parent x3 = .../modules/
        #   parent x4 = bundle root
        module_file = Path(__file__)
        bundle_root = module_file.parent.parent.parent.parent

    routing_dir = bundle_root / "routing"

    # --- Locate custom user routing dir(s) (e.g. ~/.amplifier/routing/) ---
    # These are populated by app-cli's `amplifier routing save`/`amplifier init`
    # (see commands/routing.py `save_custom_matrix()`), which write user-authored
    # matrices OUTSIDE the bundle. Without this, a matrix that only exists in a
    # user's custom dir is invisible here even though `amplifier routing list`
    # shows it — the exact "Matrix file not found -- routing disabled" bug.
    # Searched with priority BEFORE the bundle dir so user overrides win.
    custom_routing_dirs = [
        Path(d) for d in (config.get("custom_routing_dirs") or []) if d
    ]

    # --- Load default matrix ---
    # Search custom dirs first (priority), then fall back to the bundle's own
    # routing/ dir so shipped matrices (balanced, anthropic, etc.) still work.
    default_matrix_name = config.get("default_matrix", "balanced")
    # PRECEDENCE IS UNCHANGED by this call: `resolve_matrix_source` implements
    # the same "first existing <name>.yaml in [*custom_routing_dirs,
    # routing_dir] wins" rule this line has always had. What it adds is the
    # REST of the picture -- which file won, whether it is a user file or the
    # shipped one, and every same-named file it suppressed -- so the outcome
    # can be reported instead of silently applied.
    matrix_origin = resolve_matrix_source(
        default_matrix_name, custom_routing_dirs, routing_dir
    )
    matrix_path = matrix_origin.path

    base_matrix: dict[str, Any] = {}
    if matrix_path is not None:
        base_matrix = load_matrix(matrix_path)
        # Unconditional, at INFO: before this, the winning path appeared ONLY
        # inside the not-found warning below -- i.e. the file that actually
        # decided this session's routing was named only when loading FAILED.
        # Forensics on a successful load had to guess, and did guess wrong.
        logger.info(
            "[ROUTING] matrix %r loaded from %s (source=%s)",
            default_matrix_name,
            matrix_path,
            matrix_origin.source,
        )
        if matrix_origin.is_shadowed:
            # WARNING, not INFO: a shipped matrix being dead is not a status
            # detail. Every bundle-side change to the shadowed file -- including
            # anything a bundle update delivers -- is inert on this host, and
            # nothing else anywhere says so. Report; do NOT change precedence:
            # the user file winning may be exactly what its author intended.
            logger.warning(
                "[ROUTING] matrix %r is SHADOWED — %s (source=%s) WINS and is "
                "the only file in effect; same-named matrix file(s) IGNORED: "
                "%s. Edits to the ignored file(s), including anything shipped "
                "in a bundle update, have NO effect on this session. To use a "
                "shadowed file instead, remove or rename %s.",
                default_matrix_name,
                matrix_path,
                matrix_origin.source,
                ", ".join(
                    f"{path} (source={origin})"
                    for path, origin in matrix_origin.shadowed
                ),
                matrix_path,
            )
    else:
        logger.warning(
            "Matrix file not found: %s — routing disabled",
            routing_dir / f"{default_matrix_name}.yaml",
        )

    # --- Config-driven overrides (injected by CLI via _apply_hook_overrides) ---
    config_overrides: dict[str, Any] = config.get("overrides", {})

    # --- User overrides from routing capability (if any) ---
    # NOTE: session.routing is registered by session_spawner.py AFTER initialize()
    # but BEFORE execute(), so it is NOT yet available here at mount() time.
    # Matrix overrides are read here for config-driven overrides only.
    # The preresolved_models key is read inside on_session_start where timing is
    # correct (session:start fires after session.routing is registered).
    capability_overrides: dict[str, Any] = {}
    routing_capability = (
        coordinator.get_capability("session.routing")
        if hasattr(coordinator, "get_capability")
        else None
    )
    if routing_capability and isinstance(routing_capability, dict):
        capability_overrides = routing_capability.get("overrides", {})

    # --- Compose effective matrix ---
    # Config overrides first, then capability overrides on top
    effective_matrix: dict[str, Any] = {}
    if base_matrix:
        effective_matrix = compose_matrix(
            base_matrix.get("roles", {}), config_overrides
        )
        if capability_overrides:
            effective_matrix = compose_matrix(effective_matrix, capability_overrides)

    # --- Knob-consistent routing: parse the optional `preset:` block ---
    # A matrix with no `preset:` key yields None here, and None is the
    # default-off signal every downstream branch checks. Every shipped matrix
    # in routing/ except `openai.yaml` (default ON, measured win -- see
    # README "Knob-consistent delegation") and `openai-knob-consistent.yaml`
    # (the same block, kept as an explicit-name pin) has no `preset:` key, so
    # this is None for all of them.
    from .knob_consistency import EscalationState, parse_preset, validate_preset

    preset = parse_preset(base_matrix)

    # Explicit opt-out: restores legacy (pre-knob-consistent) behaviour for
    # ANY matrix, including one that ships a `preset:` block by default
    # (`openai.yaml`). Treated identically to the matrix having no `preset:`
    # key at all -- no validation runs, no escalation budget is created, and
    # every downstream branch takes its `preset is None` path.
    disable_delegation_preset = bool(config.get("disable_delegation_preset", False))
    if disable_delegation_preset and preset is not None:
        logger.info(
            "[ROUTING] disable_delegation_preset=true: ignoring preset: "
            "block in matrix %s -- resolving as if it were absent (legacy "
            "behaviour restored).",
            matrix_path,
        )
        preset = None

    if preset is not None:
        preset_errors = validate_preset(base_matrix)
        if preset_errors:
            raise ValueError(
                f"Invalid preset: block in matrix {matrix_path}:\n  "
                + "\n  ".join(preset_errors)
            )
    escalations = (
        EscalationState(max_uses=preset.escalate_max_uses)
        if preset is not None and preset.active
        else None
    )

    # --- Reject config keys the target will never act on ---
    # A DIFFERENT class from the value validation below, which structurally
    # cannot catch EITHER shape of it. One table, two enforced rules:
    #
    #   * gemini (PROVIDER-keyed): `reasoning_effort` on a gemini candidate is
    #     an UNDECLARED key, so validate_matrix_config takes its explicit
    #     "undeclared key -- the open-key rule. Pass silently" branch
    #     (matrix_loader.py). The key rides into the effective matrix, is
    #     merged into the child provider's mount config, and is read by nobody
    #     -- gemini consumes a closed set of 15 mount-config keys and no effort
    #     key is among them. The VALUE is irrelevant: every level is equally
    #     inert, because the read never happens.
    #
    #   * claude-haiku-* (MODEL-keyed): `reasoning_effort: high` on a haiku
    #     candidate is a DECLARED key with a LEGAL value on an INSTALLED
    #     provider, so it passes -- and is then collapsed to nothing when the
    #     request is built, because Haiku resolves every effort above 'low' to
    #     the same thinking budget. Measured consequence: anth-haiku-high
    #     (n=702) and anth-haiku-medium (n=736) were byte-identical
    #     configurations for a whole evaluation wave.
    #
    # Name it, then REMOVE it, so nothing downstream can carry a setting the
    # target ignored and report it as applied.
    #
    # ERROR, not WARNING: the value-validation block below warns about a
    # mistyped value, which is a typo. This is a config that cannot work as
    # written on ANY value.
    #
    # Strip-and-continue rather than raise: a bad matrix must not take a
    # session down, and the offending key is dead data either way -- removing
    # it changes no wire behaviour, it only stops the lie.
    if effective_matrix:
        effective_matrix, inert_errors = strip_inert_config(
            {"roles": effective_matrix}
        )
        effective_matrix = effective_matrix.get("roles", {})
        if inert_errors:
            logger.error("[ROUTING] Inert config in matrix %s:", matrix_path)
            for err in inert_errors:
                logger.error("[ROUTING]   %s", err)
            logger.error(
                "[ROUTING]   Key REMOVED from the effective matrix. "
                "Fix with: amplifier routing edit %s",
                default_matrix_name,
            )

    # --- Validate composed matrix config values ---
    # Catches provider-declared `choice` fields (e.g. reasoning_effort) set to
    # invalid values that the provider would otherwise silently warn about and
    # ignore, leaving the setting inert (the historical `extra_high` bug).
    if effective_matrix:
        _validation_providers = coordinator.get("providers") or {}
        config_errors = validate_matrix_config(
            {"roles": effective_matrix}, _validation_providers, coordinator
        )
        if config_errors:
            # "Fail loud on an unknown effort value" (ROUTING-PROPOSAL.md
            # section 2.2). Today this validation only warns, because it has
            # always run against every legacy matrix and cannot start
            # rejecting them. A matrix that opts into `preset:` is new by
            # definition, so it can be held to the stricter bar without
            # breaking anyone -- and a preset whose effort values are inert is
            # a preset that silently does not do what it says.
            if preset is not None:
                raise ValueError(
                    f"Invalid config in preset-bearing matrix {matrix_path} "
                    f"(these values are IGNORED by the provider):\n  "
                    + "\n  ".join(config_errors)
                )
            logger.warning("[ROUTING] Invalid config in matrix %s:", matrix_path)
            for err in config_errors:
                logger.warning("[ROUTING]   %s", err)
            logger.warning(
                "[ROUTING]   These settings are IGNORED by the provider. "
                "Fix with: amplifier routing edit %s",
                default_matrix_name,
            )

    # --- Clamp reporting: emit, never inject ---
    # W2-S4 anti-pattern #6: injected telemetry becomes class-B context at
    # best and prefix mutation at worst. The record goes to the event log.
    async def _emit_clamp(record: Any) -> None:
        logger.info(
            "[ROUTING] intent-clamped role=%s mode=%s honored=%s "
            "requested=%s granted=%s reason=%s",
            record.role,
            record.mode,
            record.honored,
            record.requested_model,
            record.granted_model,
            record.reason,
        )
        hooks_bus = coordinator.get("hooks") if hasattr(coordinator, "get") else None
        # Duck-typed on purpose: a coordinator-like object without an event
        # bus must degrade to log-only, never raise into resolution. Routing
        # a delegate is the job; reporting on it is not allowed to break it.
        if hooks_bus is not None and hasattr(hooks_bus, "emit"):
            await hooks_bus.emit("routing:intent-clamped", record.to_dict())

    # --- Register the model_role_resolver capability ---
    # Consumers: tool-delegate, hooks-session-naming, tool-recipes, tool-skills.
    # Duck-typed contract: async def resolve(model_role) -> list[ProviderPreference]
    # Only register when we have a non-empty matrix to resolve against; skip when the
    # matrix file was missing so callers get the "no resolver" warning instead of a
    # resolver that always returns an empty list.
    if effective_matrix and hasattr(coordinator, "register_capability"):
        from .resolver_class import MatrixModelRoleResolver

        _resolver_providers = coordinator.get("providers") or {}
        _resolver = MatrixModelRoleResolver(
            matrix_roles=effective_matrix,
            providers=_resolver_providers,
            matrix_name=base_matrix.get("name", default_matrix_name),
            coordinator=coordinator,
            preset=preset,
            on_clamp=_emit_clamp,
            escalations=escalations,
            matrix_origin=matrix_origin,
        )
        coordinator.register_capability("model_role_resolver", _resolver)

    # ------------------------------------------------------------------
    # Hook 1: session:start — resolve model_role for all agents
    # ------------------------------------------------------------------
    async def on_session_start(event: str, data: dict[str, Any]) -> Any:
        # Effective-source telemetry, emitted ONCE per session on the same
        # event surface this module already uses for clamp records (never
        # injected -- W2-S4 anti-pattern #6). Emitted here rather than at
        # mount() because listeners are not registered yet at mount time, so a
        # mount-time emit would land in an empty room.
        #
        # This is what makes the shadowed-file class of forensic error
        # impossible to repeat: the file that decided routing is now IN the
        # event log, alongside what it shadowed, instead of having to be
        # inferred from a raw wire capture after the fact.
        if matrix_path is not None:
            try:
                _hooks_bus = (
                    coordinator.get("hooks") if hasattr(coordinator, "get") else None
                )
                if _hooks_bus is not None and hasattr(_hooks_bus, "emit"):
                    await _hooks_bus.emit(
                        "routing:matrix-loaded", matrix_origin.to_dict()
                    )
            except Exception:  # pragma: no cover - reporting must never break routing
                logger.warning("routing matrix-source reporting failed", exc_info=True)

        # Restore this session's OWN role pin before anything else reads the
        # provider ordering. Runs on every session:start -- including the one
        # a RESUME fires, which is the leg where the promotion has been lost.
        # Emits rather than staying silent: a corrected pin is exactly the
        # signal the 74w capture had no way to surface.
        if reassert_role_pin:
            from .role_pin import reassert_own_role_pin

            pin_record = reassert_own_role_pin(coordinator)
            if pin_record is not None:
                # Same emit shape as _emit_clamp above: resolve the bus from the
                # coordinator and duck-type it, so a session without a hooks bus
                # still gets the correction, just unreported.
                pin_bus = coordinator.get("hooks") if hasattr(coordinator, "get") else None
                if pin_bus is not None and hasattr(pin_bus, "emit"):
                    await pin_bus.emit("routing:role-pin-reasserted", pin_record)

        providers = coordinator.get("providers") or {}
        agents = (
            coordinator.config.get("agents", {})
            if hasattr(coordinator, "config")
            else {}
        )

        from .resolver import resolve_model_role

        # Read preresolved model lists from session.routing.  session_spawner.py
        # registers session.routing AFTER initialize() (so it is not available at
        # mount() time above) but BEFORE execute() — meaning it IS available when
        # session:start fires here.
        #
        # A parent session populates session.routing["preresolved_models"] at the
        # end of its own on_session_start (see below).  session_spawner.py then
        # forwards the parent's session.routing to the child coordinator before
        # execute() runs, so the child's on_session_start finds those lists here
        # and can skip list_models() HTTP calls for providers already resolved.
        routing_cap = (
            coordinator.get_capability("session.routing")
            if hasattr(coordinator, "get_capability")
            else None
        )
        # Shallow-copy so mutations below don't alias the registered capability dict.
        preresolved_models: dict[str, list[str]] = dict(
            (routing_cap or {}).get("preresolved_models", {})
        )

        # Knob-consistent routing, level 3. Derived ONCE per session:start from
        # this session's own provider mount config -- the caller's resolved
        # (family, model, effort) is already recorded there by whoever spawned
        # or configured this session. See knob_consistency.derive_caller_context.
        caller_context = None
        if preset is not None and preset.active:
            from .knob_consistency import derive_caller_context

            caller_context = derive_caller_context(coordinator, preset)
            if caller_context is None:
                logger.warning(
                    "[ROUTING] preset %r requests inherit=%s but this session's "
                    "own model could not be determined from its provider mount "
                    "config -- inheritance is INACTIVE for this session "
                    "(matrix candidates used as-is).",
                    base_matrix.get("name", default_matrix_name),
                    preset.inherit,
                )

        async def _resolve_one(agent_cfg: dict[str, Any]) -> None:
            """Resolve model_role for a single agent and patch agent_cfg in-place."""
            model_role = agent_cfg.get("model_role")
            if not model_role:
                return
            # Precedence: an agent whose frontmatter carries an explicit
            # `provider_preferences` pin is at level 2, ABOVE inherited caller
            # intent at level 3. Inheritance is a default, never a ceiling on
            # explicit intent -- so an author who deliberately asked for a
            # specialist model still gets one. (This does not change the
            # pre-existing behaviour of overwriting that key from model_role:
            # only the clamp is skipped, and only when a preset is active.)
            agent_caller_context = (
                None if "provider_preferences" in agent_cfg else caller_context
            )
            # Normalise to list
            if isinstance(model_role, str):
                model_role = [model_role]
            resolved = await resolve_model_role(
                model_role,
                effective_matrix,
                providers,
                preresolved_models=preresolved_models,
                caller_context=agent_caller_context,
                preset=preset if agent_caller_context is not None else None,
                escalations=escalations,
                on_clamp=_emit_clamp,
            )
            if resolved:
                # Preserve the per-candidate `config` block (e.g. reasoning_effort)
                # declared in the matrix. ProviderPreference.from_dict() reads this
                # key and merges it into the child provider's mount config, so
                # dropping it here made every `config:` block in the shipped
                # matrices dead data.
                prefs: list[dict[str, Any]] = []
                for r in resolved:
                    pref: dict[str, Any] = {
                        "provider": r["provider"],
                        "model": r["model"],
                    }
                    # Omitted when empty, matching ProviderPreference.to_dict(), so
                    # candidates with no config stay byte-identical to before.
                    if r.get("config"):
                        pref["config"] = r["config"]
                    prefs.append(pref)
                agent_cfg["provider_preferences"] = prefs

        # Resolve all agents concurrently — wall-time becomes single longest
        # latency rather than sum of all latencies.  Each coroutine writes only
        # its own agent_cfg dict, so there is no shared mutable state between
        # _resolve_one calls, except for preresolved_models which is asyncio-safe:
        # asyncio is cooperative and single-threaded, so dict reads/writes never
        # interleave (a coroutine only yields at explicit await points, and dict
        # mutation is not awaited).
        await asyncio.gather(*(_resolve_one(cfg) for cfg in agents.values()))

        # Write the now-populated model lists back into session.routing so child
        # sessions spawned from this one inherit them.  session_spawner.py already
        # forwards session.routing from parent to child coordinator before execute()
        # runs, so no spawner changes are needed — updating the capability here is
        # sufficient for the lists to flow to the next generation.
        if preresolved_models and hasattr(coordinator, "get_capability"):
            existing_routing = coordinator.get_capability("session.routing") or {}
            coordinator.register_capability(
                "session.routing",
                {**existing_routing, "preresolved_models": preresolved_models},
            )

        from amplifier_core.models import HookResult

        return HookResult(action="continue")

    # ------------------------------------------------------------------
    # Banner rendering + prefix-placement plumbing (system-reminder
    # redesign, W3). Mutable closure state lives in these names; nested
    # functions rebind them via `nonlocal`.
    # ------------------------------------------------------------------
    _prefix_factory: Any = None
    # rr wave 20260831 (D1 cache-regression fix): the last `current`
    # factory object we CONTENT-VERIFIED already carries our own marker
    # (see _ensure_prefix_placement below).
    _prefix_verified_factory: Any = None
    _prefix_unavailable_logged = False
    _prefix_unavailable_reason: str | None = None

    def _render_banner() -> str:
        """Render the routing-matrix banner, wrapped and source-attributed.

        Wrapping (<system-reminder source="routing-matrix">...</system-reminder>)
        is unconditional -- a bare banner is a defect with no legitimate
        configuration (reminder-redesign-spec.md section 9), independent of
        placement mode.
        """
        if not effective_matrix:
            return ""

        lines = ["Active routing matrix: " + base_matrix.get("name", "unknown")]
        lines.append(
            "Available model roles (use model_role parameter when delegating):"
        )
        for role_name, role_data in effective_matrix.items():
            desc = (
                role_data.get("description", "") if isinstance(role_data, dict) else ""
            )
            lines.append(f"  {role_name:16s} — {desc}")

        body = "\n".join(lines)
        return f'<system-reminder source="routing-matrix">\n{body}\n</system-reminder>'

    async def _ensure_prefix_placement() -> bool:
        """Ensure the banner rides the system prompt (stable prefix).

        Originally a near-verbatim port of tool-skills'
        ``_ensure_prefix_placement`` (amplifier-bundle-skills
        modules/tool-skills/hooks.py:232-290): defensive
        coordinator.get("context") lookup, refuse to replace a static
        system prompt (no factory registered), lazy wrap on first
        provider:request.

        rr wave 20260831 (D1 cache-regression fix): the ORIGINAL re-wrap
        check here was pure object identity -- ``current is _prefix_factory``.
        That is safe ONLY while this hook is the sole wrapper of the
        system-prompt-factory slot. Once a SECOND independent hook (e.g.
        hooks-status-context) ALSO wraps the same slot with the same
        pattern, identity breaks: every hook whose own wrap is not the
        OUTERMOST one sees ``current`` change out from under it on every
        subsequent request (a PEER hook's wrap moved the slot forward),
        concludes "not wrapped yet", and wraps AGAIN around a chain that
        already contains its own prior contribution. With N such hooks all
        doing this, the composed system prompt gains N NEW copies of every
        hook's block on every single request -- unbounded, per-request
        growth (confirmed on the wire: rr-anth-01's system prompt grew
        ~21.7K chars/request, every hook's block count incrementing
        1 -> 2 -> 3 -> ... in lockstep with the request index). This is what
        collapsed anthropic's prompt-cache read share from ~90% to ~8% in
        the 20260831-rr validation wave.

        The fix: keep the identity check as a fast path (nothing has
        touched the slot since we last verified/wrapped it -> cheap,
        no-op). When identity fails, do NOT assume "not yet wrapped" --
        render the CURRENT chain once and check whether our own
        source-attributed marker (_PREFIX_MARKER) is already present
        somewhere in it. If so, our content already rides the system
        prompt (just nested under a peer hook's OUTER wrap) and touching
        the slot again would only duplicate it -- return True without
        calling set_system_prompt_factory. Only wrap when our marker is
        genuinely absent. The verified factory object is cached
        (_prefix_verified_factory) so this content check runs at most once
        per distinct factory object, not every request.

        Returns True when the banner is (now) riding the system prompt;
        False when the surface is unavailable and the caller should fall
        back to per-request injection.
        """
        nonlocal _prefix_factory, _prefix_verified_factory, _prefix_unavailable_reason

        getter = getattr(coordinator, "get", None) if coordinator else None
        context: Any = getter("context") if callable(getter) else None
        if context is None or not hasattr(context, "set_system_prompt_factory"):
            _prefix_unavailable_reason = "no_surface"
            return False

        current = getattr(context, "_system_prompt_factory", None)
        if current is None:
            _prefix_unavailable_reason = "no_factory_registered"
            # No factory registered (static-system-message session).
            # Wrapping would DROP the static system prompt (factory takes
            # precedence over stored system messages in context-simple),
            # so refuse and let the caller fall back.
            return False
        if current is _prefix_factory or current is _prefix_verified_factory:
            return (
                True  # fast path -- nothing has touched the slot since we last checked
            )

        # Slow path: a peer hook has (re-)wrapped the slot since we last
        # looked. Render once and check CONTENT, not identity -- see
        # docstring above.
        current_text = await current()
        if _PREFIX_MARKER in current_text:
            _prefix_verified_factory = current
            return True

        base_factory = current

        async def _routing_prefixed_factory() -> str:
            base = await base_factory()
            block = _render_banner()
            return f"{base}\n\n{block}" if block else base

        await context.set_system_prompt_factory(_routing_prefixed_factory)
        _prefix_factory = _routing_prefixed_factory
        logger.info(
            "Routing matrix banner placement: system-prompt prefix (wrapped "
            "the registered system-prompt factory)"
        )
        return True

    # ------------------------------------------------------------------
    # Hook 2: provider:request — inject available roles into context
    # ------------------------------------------------------------------
    async def on_provider_request(event: str, data: dict[str, Any]) -> Any:
        nonlocal _prefix_unavailable_logged, _prefix_unavailable_reason

        if not effective_matrix:
            return None

        from amplifier_core.models import HookResult

        if placement == "prefix":
            # Prefix mode: the banner lives in the system prompt (via the
            # wrapped factory above), never as a per-request injection --
            # returning continue here is what guarantees the two modes can
            # never double-inject.
            if await _ensure_prefix_placement():
                return HookResult(action="continue")
            # Placement surface unavailable (no context module / no
            # factory support). Warn once, then fall back to per-request
            # injection so the banner is never silently dropped.
            if not _prefix_unavailable_logged:
                if _prefix_unavailable_reason == "no_factory_registered":
                    logger.warning(
                        "placement='prefix' (the default) but this session has "
                        "no system-prompt factory registered (static system "
                        "prompt, or no bundle instruction/context at all); "
                        "refusing to replace it. Falling back to per-request "
                        "injection -- the routing banner will not ride the "
                        "stable cached prefix. This is expected for a session "
                        "with no dynamic system prompt; set placement='inject' "
                        "to silence."
                    )
                else:
                    logger.warning(
                        "placement='prefix' (the default) but the context "
                        "module offers no system-prompt factory surface "
                        "(set_system_prompt_factory). Falling back to "
                        "per-request injection -- the routing banner will not "
                        "ride the stable cached prefix. Set placement='inject' "
                        "to silence this warning."
                    )
                _prefix_unavailable_logged = True

        banner = _render_banner()
        if not banner:
            return None

        # Role pinned to "user", explicitly, overriding the HookResult
        # default of "system" (amplifier-core/models.py:231-238). System-
        # role mid-conversation content is hoisted into the provider's
        # cached system prefix on anthropic/openai/gemini, so a per-turn-
        # changing block there rewrites the system cache every turn --
        # this is not behind a flag; see reminder-redesign-spec.md
        # section 1.2 / section 9.
        return HookResult(
            action="inject_context",
            context_injection=banner,
            context_injection_role="user",
            ephemeral=True,
        )

    # --- Register hooks ---
    hooks = coordinator.hooks if hasattr(coordinator, "hooks") else None
    if hooks:
        hooks.register(
            "session:start",
            on_session_start,
            priority=5,
            name="routing-resolve",
        )
        hooks.register(
            "provider:request",
            on_provider_request,
            priority=15,
            name="routing-context",
        )
