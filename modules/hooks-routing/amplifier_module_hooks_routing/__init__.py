"""Routing matrix hook module.

Provides model routing based on curated role-to-provider matrices.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the routing matrix hook.

    Loads the default matrix, composes with user overrides, registers
    ``session:start`` and ``provider:request`` hooks.
    """
    config = config or {}

    from .matrix_loader import compose_matrix, load_matrix, validate_matrix_config

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
    search_dirs = [*custom_routing_dirs, routing_dir]
    matrix_path = next(
        (
            candidate
            for search_dir in search_dirs
            if (candidate := search_dir / f"{default_matrix_name}.yaml").exists()
        ),
        None,
    )

    base_matrix: dict[str, Any] = {}
    if matrix_path is not None:
        base_matrix = load_matrix(matrix_path)
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
            logger.warning("[ROUTING] Invalid config in matrix %s:", matrix_path)
            for err in config_errors:
                logger.warning("[ROUTING]   %s", err)
            logger.warning(
                "[ROUTING]   These settings are IGNORED by the provider. "
                "Fix with: amplifier routing edit %s",
                default_matrix_name,
            )

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
        )
        coordinator.register_capability("model_role_resolver", _resolver)

    # ------------------------------------------------------------------
    # Hook 1: session:start — resolve model_role for all agents
    # ------------------------------------------------------------------
    async def on_session_start(event: str, data: dict[str, Any]) -> Any:
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

        async def _resolve_one(agent_cfg: dict[str, Any]) -> None:
            """Resolve model_role for a single agent and patch agent_cfg in-place."""
            model_role = agent_cfg.get("model_role")
            if not model_role:
                return
            # Normalise to list
            if isinstance(model_role, str):
                model_role = [model_role]
            resolved = await resolve_model_role(
                model_role,
                effective_matrix,
                providers,
                preresolved_models=preresolved_models,
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
    # Hook 2: provider:request — inject available roles into context
    # ------------------------------------------------------------------
    async def on_provider_request(event: str, data: dict[str, Any]) -> Any:
        if not effective_matrix:
            return None

        from amplifier_core.models import HookResult

        lines = ["Active routing matrix: " + base_matrix.get("name", "unknown")]
        lines.append(
            "Available model roles (use model_role parameter when delegating):"
        )
        for role_name, role_data in effective_matrix.items():
            desc = (
                role_data.get("description", "") if isinstance(role_data, dict) else ""
            )
            lines.append(f"  {role_name:16s} — {desc}")

        return HookResult(
            action="inject_context",
            context_injection="\n".join(lines),
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
