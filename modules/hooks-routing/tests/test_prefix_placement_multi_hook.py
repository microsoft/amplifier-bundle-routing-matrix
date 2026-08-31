"""Tests for the D1 fix (rr wave 20260831 -- anthropic prompt-cache collapse).

Background: the `20260831-rr` treatment-validation wave found the anthropic
system prompt growing ~22K chars EVERY REQUEST (44,525 -> 66,268 -> 88,011 ->
...), collapsing prompt-cache read share from ~90% to ~8% (~14x cost). Traced
on the wire: EVERY hook that wraps `context.set_system_prompt_factory` (this
module, hooks-status-context, and tool-skills) gained one MORE copy of its
own block on every single request -- 1 copy after request 1, 2 after
request 2, 3 after request 3, etc. -- in lockstep with the request index.

Root cause: `_ensure_prefix_placement`'s original re-wrap check was pure
object identity (`current is _prefix_factory`). That check is safe ONLY
while this hook is the SOLE wrapper of the system-prompt-factory slot
(tool-skills' own solo production history). Once a SECOND independent hook
ALSO wraps the SAME slot with the same pattern, the slot's value changes
out from under whichever hook isn't the outermost wrapper on any given
request -- so on the NEXT request, that hook's own identity check fails, it
concludes "not wrapped yet", and wraps AGAIN around a chain that ALREADY
contains its own prior contribution. With N such hooks sharing the slot,
this compounds every single request, regardless of hook ordering.

These tests simulate a PEER hook also wrapping the SAME `FakeContext`'s
system-prompt-factory slot (exactly what hooks-status-context / tool-skills
also do in production), and assert this module's own banner/marker never
duplicates -- the property the wave's own unit suite (never exercised
multi-hook composition) never caught.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from amplifier_module_hooks_routing import mount

_ROUTING_MARKER = '<system-reminder source="routing-matrix">'


def _write_matrix(tmp_path: Path, name: str = "balanced") -> Path:
    import textwrap

    bundle_root = tmp_path / "bundle"
    routing_dir = bundle_root / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)
    content = textwrap.dedent("""\
        name: balanced
        description: "Test balanced matrix"
        updated: "2026-01-01"

        roles:
          general:
            description: "General purpose"
            candidates:
              - provider: anthropic
                model: claude-sonnet-4-20250514
    """)
    (routing_dir / f"{name}.yaml").write_text(content)
    return bundle_root


class FakeContext:
    """Same shape as tests/test_prefix_placement.py's FakeContext."""

    def __init__(self, base_prompt: str = "BASE SYSTEM PROMPT") -> None:
        self._system_prompt_factory = self._make_base(base_prompt)

    @staticmethod
    def _make_base(text: str) -> Any:
        async def _base() -> str:
            return text

        return _base

    async def set_system_prompt_factory(self, factory: Any) -> None:
        self._system_prompt_factory = factory


class FakeCoordinator:
    """Plain duck-typed coordinator exposing exactly the surface mount()
    uses. Mirrors amplifier-bundle-skills modules/tool-skills/tests/
    test_prefix_placement.py's own FakeCoordinator shape."""

    def __init__(self, context: Any = None, providers: Any = None) -> None:
        self._context = context
        self._providers = providers
        self.session_state: dict = {}
        self.config = {"agents": {}}
        self._registered: list[tuple[str, Any]] = []

        class _Hooks:
            def __init__(self, outer: "FakeCoordinator") -> None:
                self._outer = outer

            def register(self, event_name: str, handler: Any, **kwargs: Any) -> None:
                self._outer._registered.append((event_name, handler))

        self.hooks = _Hooks(self)

    def get(self, name: str) -> Any:
        if name == "context":
            return self._context
        if name == "providers":
            return self._providers
        return None

    def get_capability(self, name: str) -> Any:
        return None

    def register_capability(self, name: str, value: Any) -> None:
        pass


def _provider_request_handler_of(coordinator: FakeCoordinator) -> Any:
    for event_name, handler in coordinator._registered:
        if event_name == "provider:request":
            return handler
    return None


async def _mount_and_get_handler(
    tmp_path: Path, *, context: Any = None, config_extra: dict[str, Any] | None = None
) -> tuple[FakeCoordinator, Any]:
    bundle_root = _write_matrix(tmp_path)
    coordinator = FakeCoordinator(context=context)
    config: dict[str, Any] = {
        "default_matrix": "balanced",
        "_bundle_root": str(bundle_root),
        **(config_extra or {}),
    }
    await mount(coordinator, config=config)
    handler = _provider_request_handler_of(coordinator)
    assert handler is not None
    return coordinator, handler


async def _peer_rewrap_unconditionally(context: FakeContext, marker: str) -> None:
    """Simulates ANY other hook sharing the system-prompt-factory slot with
    NO idempotency guard at all -- the worst realistic case. Always wraps
    the CURRENT factory, unconditionally, adding one more copy of its own
    marker every call. This module's own fix must hold regardless."""
    base_factory = context._system_prompt_factory

    async def _peer_factory() -> str:
        base = await base_factory()
        return f'{base}\n\n<system-reminder source="{marker}">peer content</system-reminder>'

    await context.set_system_prompt_factory(_peer_factory)


# ---------------------------------------------------------------------------
# D1-01 -- our own marker never duplicates under a chaotically-rewrapping peer.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d1_01_own_marker_never_duplicates_under_a_rewrapping_peer(
    tmp_path: Path,
) -> None:
    """Six simulated requests, a PEER hook re-wrapping the slot before each
    one. Our OWN banner must appear EXACTLY ONCE in the composed system
    prompt regardless.

    FAILS BEFORE the fix: our own marker count grows 1 -> 2 -> ... -> 6.
    """
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(tmp_path, context=context)

    for _ in range(6):
        await _peer_rewrap_unconditionally(context, "peer-hook")
        result = await handler("provider:request", {})
        assert result.action == "continue"  # all content moved to the prefix

    rendered = await context._system_prompt_factory()
    own_marker_count = rendered.count(_ROUTING_MARKER)
    assert own_marker_count == 1, (
        "Our own banner must appear EXACTLY ONCE in the system prompt no "
        "matter how many times a peer hook also wraps the slot between our "
        f"own checks; found {own_marker_count} copies. Rendered length: "
        f"{len(rendered)} chars."
    )


# ---------------------------------------------------------------------------
# D1-02 -- the composed system prompt is BYTE-STABLE across many requests
# once both this hook and a well-behaved peer have each wrapped once.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d1_02_system_prompt_byte_stable_across_many_requests(
    tmp_path: Path,
) -> None:
    """A well-behaved peer wraps the slot exactly once, then this hook's
    provider:request handler is called repeatedly (simulating N iterations
    across turns). The composed system-prompt TEXT must be byte-identical
    across all of them -- the exact property whose absence collapsed
    anthropic's prompt-cache read share from ~90% to ~8% in the
    20260831-rr wave.

    FAILS BEFORE the fix: length grows every call.
    """
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(tmp_path, context=context)

    await _peer_rewrap_unconditionally(context, "hooks-status-context")

    lengths: list[int] = []
    texts: list[str] = []
    for _ in range(6):
        result = await handler("provider:request", {})
        assert result.action == "continue"
        rendered = await context._system_prompt_factory()
        lengths.append(len(rendered))
        texts.append(rendered)

    assert len(set(lengths)) == 1, (
        f"System prompt length must be BYTE-STABLE across requests once "
        f"established; got growing lengths: {lengths!r}"
    )
    assert len(set(texts)) == 1, (
        "System prompt TEXT must be byte-identical across requests"
    )
