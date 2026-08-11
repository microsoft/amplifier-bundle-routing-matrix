"""Matrix-strategy implementation of the ``model_role_resolver`` capability.

The ``model_role_resolver`` capability is a generic, duck-typed contract that
consumers (tool-delegate, hooks-session-naming, tool-recipes, tool-skills) use
to translate a ``model_role`` string into ordered provider preferences.

This module ships the matrix-based implementation. Other routing bundles
(e.g. cost-aware, latency-aware, availability-aware) may register their own
implementation under the same capability name; only one is active per session.

Contract (duck-typed, no Protocol class by design):

    class _Resolver:
        # Required.
        async def resolve(self, model_role: str | list[str]) -> list[ProviderPreference]:
            ...

        # Optional. Role names this strategy recognises, in the order it wants
        # them presented. Omit when the strategy cannot enumerate its roles.
        known_roles: tuple[str, ...]

Returning an empty list means "role known but no installed provider matches";
returning a list with one or more ``ProviderPreference`` is the success path.
The resolver honours fallback order encoded by the active strategy (matrix
candidate order, cost ranking, etc.).

``known_roles`` is advisory metadata, not a resolution guarantee: a role may be
listed and still resolve to ``[]`` when no installed provider serves it. That is
why it is named "known" rather than "available". Consumers use it to constrain
their own surfaces -- tool-delegate turns it into a JSON-Schema ``enum`` on its
``model_role`` parameter so models cannot invent role names. It is *optional*,
so every consumer MUST degrade gracefully when a resolver does not expose it:
absent means "cannot enumerate", which is NOT the same as "no resolver
registered" and must not be treated as such. Consumers should also type-guard
the value (sequence of ``str``) rather than trusting it blindly.
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
        coordinator: Optional coordinator, forwarded to
            :func:`amplifier_module_hooks_routing.resolver.resolve_model_role`
            as a fallback source of mount plan config (module/id/priority).
            Needed to resolve a matrix candidate's bare ``provider:`` type
            (e.g. ``"anthropic"``) when 2+ named instances of that module
            exist but none is keyed by the bare type itself.
    """

    def __init__(
        self,
        matrix_roles: dict[str, Any],
        providers: dict[str, Any],
        matrix_name: str,
        coordinator: Any = None,
    ) -> None:
        self._matrix_roles = matrix_roles
        self._providers = providers
        self.name = matrix_name
        self._coordinator = coordinator
        # Optional part of the model_role_resolver contract. Snapshot in matrix
        # declaration order -- the same order hooks-routing injects into session
        # context -- so consumers that surface these to a model agree with it.
        # Not sorted: the matrix order is curated (general, fast, coding, ...).
        self.known_roles: tuple[str, ...] = tuple(matrix_roles)
        # Session-lifetime cache of provider_type -> fetched model names, shared
        # across every resolve() call this instance ever makes. A resolver
        # instance is constructed once per mount() (see __init__.py's
        # ``coordinator.register_capability("model_role_resolver", _resolver)``)
        # and lives for the session, and a provider's model list does not
        # change mid-session -- so the first successful list_models() per
        # provider serves every later role resolution here. Without this,
        # resolve() re-fetched the full model list on every call (see
        # resolve_model_role's own ``preresolved_models`` parameter, which
        # exists precisely to avoid this and was simply never wired in here),
        # costing a redundant HTTP round-trip per call and -- worse -- turning
        # any single transient list_models() failure into a silent demotion to
        # a different model for that call.
        self._preresolved_models: dict[str, list[str]] = {}

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
        resolved = await resolve_model_role(
            roles,
            self._matrix_roles,
            self._providers,
            preresolved_models=self._preresolved_models,
            coordinator=self._coordinator,
        )
        return [
            ProviderPreference(
                provider=r["provider"],
                model=r["model"],
                config=r.get("config", {}),
            )
            for r in resolved
        ]
