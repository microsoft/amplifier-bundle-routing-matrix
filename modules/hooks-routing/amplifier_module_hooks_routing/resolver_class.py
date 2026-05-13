"""Matrix-strategy implementation of the ``model_role_resolver`` capability.

The ``model_role_resolver`` capability is a generic, duck-typed contract that
consumers (tool-delegate, hooks-session-naming, tool-recipes, tool-skills) use
to translate a ``model_role`` string into ordered provider preferences.

This module ships the matrix-based implementation. Other routing bundles
(e.g. cost-aware, latency-aware, availability-aware) may register their own
implementation under the same capability name; only one is active per session.

Contract (duck-typed, no Protocol class by design):

    class _Resolver:
        async def resolve(self, model_role: str | list[str]) -> list[ProviderPreference]:
            ...

Returning an empty list means "role known but no installed provider matches";
returning a list with one or more ``ProviderPreference`` is the success path.
The resolver honours fallback order encoded by the active strategy (matrix
candidate order, cost ranking, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from amplifier_foundation.spawn_utils import ProviderPreference


class MatrixModelRoleResolver:
    """Matrix-strategy implementation of the ``model_role_resolver`` capability.

    Wraps :func:`amplifier_module_hooks_routing.resolver.resolve_model_role`
    so consumers don't need to know which strategy is active or where the
    matrix lives.

    Args:
        matrix_roles: Composed matrix ``roles`` dict (from :mod:`matrix_loader`).
        providers: Installed providers dict from ``coordinator.get("providers")``.
        matrix_name: Human-readable matrix name, exposed via ``self.name`` for
            diagnostics (``logger.debug("resolver=%s", resolver.name)``).
    """

    def __init__(
        self,
        matrix_roles: dict[str, Any],
        providers: dict[str, Any],
        matrix_name: str,
    ) -> None:
        self._matrix_roles = matrix_roles
        self._providers = providers
        self.name = matrix_name

    async def resolve(self, model_role: str | list[str]) -> list[ProviderPreference]:
        """Resolve a model role (or ordered fallback list) to provider preferences.

        Args:
            model_role: Either a single role name (``"reasoning"``) or an
                ordered fallback list (``["reasoning", "general"]``). The first
                role with at least one installed-provider candidate wins.

        Returns:
            ``list[ProviderPreference]`` — one entry per resolved candidate.
            Empty list when no role resolves to an installed provider.

        Raises:
            ImportError: If ``amplifier_foundation`` is not importable. The
                resolver only exists to feed sub-session spawn pipelines, and
                those pipelines always ship foundation; fail-forward rather
                than silently returning a different shape.
        """
        # Lazy imports keep this module's pyproject self-contained
        # (declares only pyyaml). At every runtime call site, foundation is
        # present because that is where session spawning lives.
        from amplifier_foundation.spawn_utils import ProviderPreference

        from .resolver import resolve_model_role

        roles = [model_role] if isinstance(model_role, str) else list(model_role)
        resolved = await resolve_model_role(roles, self._matrix_roles, self._providers)
        return [
            ProviderPreference(
                provider=r["provider"],
                model=r["model"],
                config=r.get("config", {}),
            )
            for r in resolved
        ]
