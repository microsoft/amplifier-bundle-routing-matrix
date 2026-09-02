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
        preset: Optional parsed ``preset:`` block (knob-consistent routing).
            ``None`` -- the default, and what every matrix without a
            ``preset:`` block yields -- means this resolver behaves exactly as
            it did before the feature existed.
        on_clamp: Optional async callable receiving each ``ClampRecord``.
    """

    def __init__(
        self,
        matrix_roles: dict[str, Any],
        providers: dict[str, Any],
        matrix_name: str,
        coordinator: Any = None,
        preset: Any = None,
        on_clamp: Any = None,
        escalations: Any = None,
    ) -> None:
        self._matrix_roles = matrix_roles
        self._providers = providers
        self.name = matrix_name
        self._coordinator = coordinator
        self._preset = preset
        self._on_clamp = on_clamp
        # Per-session escalation budget. `max_uses` is per session, so the SAME
        # counter object is shared with the session-start resolution path in
        # ``__init__.py`` -- two counters would silently double the budget.
        # Constructed here only when the caller did not supply one.
        self._escalations: Any = escalations
        if (
            self._escalations is None
            and preset is not None
            and getattr(preset, "active", False)
        ):
            from .knob_consistency import EscalationState

            self._escalations = EscalationState(
                max_uses=getattr(preset, "escalate_max_uses", 0)
            )
        # Diagnostics: every clamp decision this resolver made, newest last.
        # Read by tests and by anything that wants to surface routing intent
        # without parsing the event log.
        self.clamp_records: list[Any] = []
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

    async def resolve(
        self,
        model_role: str | list[str],
        caller_context: Any = None,
    ) -> list[ProviderPreference]:
        """Resolve a model role (or ordered fallback list) to provider preferences.

        Args:
            model_role: Either a single role name (``"reasoning"``) or an
                ordered fallback list (``["reasoning", "general"]``). The first
                role with at least one installed-provider candidate wins.
            caller_context: Optional explicit caller triple, for a consumer
                that knows it (a future tool-delegate could pass it directly).
                **Optional by design:** when omitted, and only when a preset
                is active, it is derived from this resolver's own coordinator
                -- the resolver is mounted in the *caller's* session, so the
                caller's resolved provider/model/effort is already recorded
                there. That is why knob-consistent routing needs no change in
                ``amplifier-foundation``. Every existing call site
                (``await resolver.resolve(role)``) keeps working unchanged.

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

        knob_active = self._preset is not None and getattr(
            self._preset, "active", False
        )
        if knob_active and caller_context is None:
            from .knob_consistency import derive_caller_context

            caller_context = derive_caller_context(self._coordinator, self._preset)

        resolved = await resolve_model_role(
            roles,
            self._matrix_roles,
            self._providers,
            preresolved_models=self._preresolved_models,
            coordinator=self._coordinator,
            caller_context=caller_context if knob_active else None,
            preset=self._preset if knob_active else None,
            escalations=self._escalations if knob_active else None,
            on_clamp=self._record_clamp if knob_active else None,
        )
        return [
            ProviderPreference(
                provider=r["provider"],
                model=r["model"],
                config=r.get("config", {}),
            )
            for r in resolved
        ]

    async def _record_clamp(self, record: Any) -> None:
        """Keep the record locally, then forward it to the mount-time sink.

        Local retention is what makes the decision inspectable without an
        event log; the sink is what puts it on the event bus. Neither is
        allowed to raise into the resolution path.
        """
        self.clamp_records.append(record)
        if self._on_clamp is not None:
            await self._on_clamp(record)
