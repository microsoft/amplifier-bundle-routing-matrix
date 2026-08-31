"""Tests for placement -- routing-matrix banner in the stable system-prompt prefix.

placement="prefix" (default) wraps the context module's system-prompt
factory (the surface amplifier-foundation _prepared.py registers via
context.set_system_prompt_factory) so the banner rides the provider-cached
system block instead of being re-sent as fresh input tokens every request.
placement="inject" is the fully supported explicit opt-out / rollback lever
(pre-redesign `1e329ce` behavior, restores exactly).

Mirrors amplifier-bundle-skills modules/tool-skills/tests/test_prefix_placement.py
1:1 in structure (FakeContext/FakeCoordinator shapes and the test set), adapted
to this module's mount()-function style (no hook class to instantiate --
handlers are extracted from coordinator.hooks.register.call_args_list).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from amplifier_module_hooks_routing import mount

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_matrix(tmp_path: Path, name: str = "balanced") -> Path:
    """Write a minimal matrix YAML; returns the bundle root."""
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
          fast:
            description: "Fast tasks"
            candidates:
              - provider: openai
                model: gpt-4o-mini
    """)
    (routing_dir / f"{name}.yaml").write_text(content)
    return bundle_root


class FakeContext:
    """Context module exposing the system-prompt-factory surface
    (context-simple shape: public async setter, private attribute)."""

    def __init__(self, base_prompt: str = "BASE SYSTEM PROMPT") -> None:
        self._system_prompt_factory = self._make_base(base_prompt)

    @staticmethod
    def _make_base(text: str) -> Any:
        async def _base() -> str:
            return text

        return _base

    async def set_system_prompt_factory(self, factory: Any) -> None:
        self._system_prompt_factory = factory


def _make_coordinator(*, context: Any = None, providers: Any = None) -> MagicMock:
    """Mock coordinator exposing .get('context'|'providers'), .config,
    .get_capability, and .hooks.register -- the only surface mount() uses."""
    coordinator = MagicMock()
    coordinator.session_state = {}
    coordinator.config = {"agents": {}}
    coordinator.get_capability = MagicMock(return_value=None)

    def _get(key: str) -> Any:
        if key == "context":
            return context
        if key == "providers":
            return providers
        return None

    coordinator.get = MagicMock(side_effect=_get)
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    return coordinator


def _provider_request_handler_of(coordinator: MagicMock) -> Any:
    """Extract the provider:request handler mount() registered, or None."""
    for call in coordinator.hooks.register.call_args_list:
        if call.args and call.args[0] == "provider:request":
            return call.args[1]
    return None


async def _mount_and_get_handler(
    tmp_path: Path, *, context: Any = None, config_extra: dict[str, Any] | None = None
) -> tuple[MagicMock, Any]:
    bundle_root = _write_matrix(tmp_path)
    coordinator = _make_coordinator(context=context)
    config: dict[str, Any] = {
        "default_matrix": "balanced",
        "_bundle_root": str(bundle_root),
        **(config_extra or {}),
    }
    await mount(coordinator, config=config)
    handler = _provider_request_handler_of(coordinator)
    assert handler is not None
    return coordinator, handler


# ---------------------------------------------------------------------------
# Default mode -- prefix is the default. The wrapper and role pin are
# unconditional defect fixes (not behind this flag); only PLACEMENT is a
# preference (reminder-redesign-spec.md section 9).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_is_prefix(tmp_path: Path) -> None:
    """No placement key -> prefix placement: banner lands in the system
    prompt via the wrapped factory; no per-request injection."""
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(tmp_path, context=context)

    result = await handler("provider:request", {})
    assert result.action == "continue"  # never a per-request injection

    rendered = await context._system_prompt_factory()
    assert rendered.startswith("BASE SYSTEM PROMPT")
    assert '<system-reminder source="routing-matrix">' in rendered
    assert "general" in rendered


@pytest.mark.asyncio
async def test_default_without_surface_warns_and_falls_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Default (prefix) with no factory surface -> ONE WARNING (not ERROR)
    + inject-mode fallback so the banner stays visible."""
    _coordinator, handler = await _mount_and_get_handler(tmp_path, context=None)

    with caplog.at_level("WARNING"):
        r1 = await handler("provider:request", {})
        r2 = await handler("provider:request", {})

    assert r1.action == r2.action == "inject_context"  # fallback, not silence
    assert '<system-reminder source="routing-matrix">' in (r1.context_injection or "")
    warnings = [
        r for r in caplog.records if r.levelname == "WARNING" and "prefix" in r.message
    ]
    assert len(warnings) == 1  # once per instance, not per request
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.asyncio
async def test_explicit_inject_optout(tmp_path: Path) -> None:
    """placement='inject' opt-out: per-request inject_context with the
    pre-redesign shape (`1e329ce`), even when a factory surface IS
    available (and the factory is left untouched)."""
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=context, config_extra={"placement": "inject"}
    )

    result = await handler("provider:request", {})

    assert result.action == "inject_context"
    assert result.context_injection is not None
    assert '<system-reminder source="routing-matrix">' in result.context_injection
    assert "general" in result.context_injection
    assert result.context_injection_role == "user"
    assert result.ephemeral is True
    # The system prompt is untouched -- no double-inject in opt-out mode.
    rendered = await context._system_prompt_factory()
    assert "routing-matrix" not in rendered


@pytest.mark.asyncio
async def test_invalid_placement_rejected(tmp_path: Path) -> None:
    """Unknown placement value fails loudly at mount time, not mid-session."""
    bundle_root = _write_matrix(tmp_path)
    coordinator = _make_coordinator()
    with pytest.raises(ValueError, match="placement"):
        await mount(
            coordinator,
            config={
                "default_matrix": "balanced",
                "_bundle_root": str(bundle_root),
                "placement": "sideways",
            },
        )


# ---------------------------------------------------------------------------
# Prefix mode -- placement, refresh behavior, no-double-inject, fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefix_mode_places_banner_in_system_prompt(tmp_path: Path) -> None:
    """Prefix mode: factory output = base + banner block; hook injects
    nothing per-request."""
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=context, config_extra={"placement": "prefix"}
    )

    result = await handler("provider:request", {})
    assert result.action == "continue"

    rendered = await context._system_prompt_factory()
    assert rendered.startswith("BASE SYSTEM PROMPT")
    assert '<system-reminder source="routing-matrix">' in rendered
    assert "general" in rendered
    assert "fast" in rendered


@pytest.mark.asyncio
async def test_prefix_mode_stable_across_requests(tmp_path: Path) -> None:
    """Unchanged matrix -> byte-identical system prompt across requests
    (cacheable prefix)."""
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=context, config_extra={"placement": "prefix"}
    )

    await handler("provider:request", {})
    first = await context._system_prompt_factory()
    await handler("provider:request", {})
    second = await context._system_prompt_factory()
    assert first == second
    # Exactly one copy of the banner in the prompt -- no double-wrap.
    assert first.count('<system-reminder source="routing-matrix">') == 1


@pytest.mark.asyncio
async def test_prefix_mode_rewraps_after_factory_rereg(tmp_path: Path) -> None:
    """If someone re-registers a new base factory after our wrap, the next
    request re-wraps around it -- the banner never silently disappears."""
    context = FakeContext()
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=context, config_extra={"placement": "prefix"}
    )
    await handler("provider:request", {})

    async def new_base() -> str:
        return "REPLACED BASE"

    await context.set_system_prompt_factory(new_base)  # clobbers our wrap
    await handler("provider:request", {})
    rendered = await context._system_prompt_factory()
    assert rendered.startswith("REPLACED BASE")
    assert "general" in rendered
    assert rendered.count('<system-reminder source="routing-matrix">') == 1


@pytest.mark.asyncio
async def test_prefix_mode_falls_back_with_warning_without_surface(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No context module at all -> WARNING (not ERROR) + inject-mode
    fallback (agent never silently loses the banner)."""
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=None, config_extra={"placement": "prefix"}
    )
    with caplog.at_level("WARNING"):
        result = await handler("provider:request", {})
    assert result.action == "inject_context"
    assert any(
        r.levelname == "WARNING" and "prefix" in r.message for r in caplog.records
    )
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.asyncio
async def test_prefix_mode_refuses_to_replace_static_prompt(tmp_path: Path) -> None:
    """A session with NO registered factory (static system messages) must
    not have its prompt replaced by a routing-only factory -- falls back."""
    context = FakeContext()
    context._system_prompt_factory = None
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=context, config_extra={"placement": "prefix"}
    )
    result = await handler("provider:request", {})
    assert result.action == "inject_context"  # inject-mode fallback
    assert context._system_prompt_factory is None  # untouched


# ---------------------------------------------------------------------------
# The exact defect from session 0629f373 -- fails before the redesign.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrapped_injection_matches_envelope_shape(tmp_path: Path) -> None:
    """Injection content starts with `<system-reminder source="routing-matrix"`
    and ends with `</system-reminder>` -- the exact defect from session
    0629f373 (a bare banner with no wrapper at all). Fails before."""
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=None, config_extra={"placement": "inject"}
    )
    result = await handler("provider:request", {})
    assert result.context_injection.startswith(
        '<system-reminder source="routing-matrix"'
    )
    assert result.context_injection.endswith("</system-reminder>")
