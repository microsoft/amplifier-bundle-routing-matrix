"""Routing matrix hook module.

Provides model routing based on curated role-to-provider matrices.
"""

from __future__ import annotations

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

    from .matrix_loader import compose_matrix, load_matrix

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

    # --- Load default matrix ---
    default_matrix_name = config.get("default_matrix", "balanced")

    # Project-scoped matrices (<cwd>/.amplifier/routing/) have the highest
    # runtime priority, after the _bundle_root escape hatch.  This matches the
    # convention documented at amplifier-app-cli/amplifier_app_cli/paths.py:72
    # where _get_user_and_project_paths() uses project > user-global for
    # bundles, agents, and skills.  Routing follows the same rule so that a
    # project-local matrix is picked up automatically when amplifier is launched
    # from the project root — no ~/.amplifier symlink required.
    #
    # Discovery is flat (no walk-up): cwd must be exactly the project root.
    # Running from a subdirectory will miss the project matrix and fall through
    # to the next level — consistent with paths.py:72-75 and intentional.
    #
    # User custom matrices (~/.amplifier/routing/) take priority over bundled
    # matrices in the cache.  The CLI matrix editor saves customizations here,
    # so runtime must honour them first to stay consistent with what the user
    # sees in `amplifier routing manage`.
    project_matrix_path = Path.cwd() / ".amplifier" / "routing" / f"{default_matrix_name}.yaml"
    custom_routing_dir = Path.home() / ".amplifier" / "routing"
    custom_matrix_path = custom_routing_dir / f"{default_matrix_name}.yaml"
    if project_matrix_path.exists():
        matrix_path = project_matrix_path
    elif custom_matrix_path.exists():
        matrix_path = custom_matrix_path
    else:
        matrix_path = routing_dir / f"{default_matrix_name}.yaml"

    base_matrix: dict[str, Any] = {}
    if matrix_path.exists():
        base_matrix = load_matrix(matrix_path)
    else:
        logger.warning("Matrix file not found: %s — routing disabled", matrix_path)

    # --- Config-driven overrides (injected by CLI via _apply_hook_overrides) ---
    config_overrides: dict[str, Any] = config.get("overrides", {})

    # --- User overrides from routing capability (if any) ---
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

    # --- Store in session state (modes pattern) ---
    if hasattr(coordinator, "session_state"):
        coordinator.session_state["routing_matrix"] = {
            "name": base_matrix.get("name", default_matrix_name),
            "roles": effective_matrix,
        }

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

        for _agent_name, agent_cfg in agents.items():
            model_role = agent_cfg.get("model_role")
            if not model_role:
                continue

            # Normalise to list
            if isinstance(model_role, str):
                model_role = [model_role]

            resolved = await resolve_model_role(model_role, effective_matrix, providers)
            if resolved:
                agent_cfg["provider_preferences"] = [
                    {
                        "provider": r["provider"],
                        "model": r["model"],
                        "config": r.get("config", {}),
                    }
                    for r in resolved
                ]

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
