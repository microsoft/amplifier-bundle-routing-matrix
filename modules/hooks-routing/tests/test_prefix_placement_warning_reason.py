"""Regression test for the prefix-placement warning misdiagnosis.

`_ensure_prefix_placement()` declines to wrap the system-prompt factory for
two distinct reasons: (a) the context module has no
`set_system_prompt_factory` surface at all, or (b) the surface exists but no
factory is registered yet (`_system_prompt_factory is None`). Before this
fix, the caller could not tell the two apart and always logged the (a)
message ("offers no system-prompt factory surface") -- which is a false
diagnosis for (b), the case that actually happens with the shipped
context-simple module.

See ISSUE-prefix-placement-warning-misdiagnoses-cause.md for the full
report. This test is adapted from that report's reproduction script.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from tests.test_prefix_placement import FakeContext, _mount_and_get_handler

NO_SURFACE_NEEDLE = "offers no system-prompt factory surface"
NO_FACTORY_NEEDLE = "no system-prompt factory registered"


class NoSurfaceContext:
    """Control: a context module with NO set_system_prompt_factory at all."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def add_message(self, message: dict) -> None:
        self.messages.append(message)

    async def get_messages(self) -> list[dict]:
        return list(self.messages)


async def _fire(tmp_path: Path, context, caplog: pytest.LogCaptureFixture):
    _coordinator, handler = await _mount_and_get_handler(
        tmp_path, context=context, config_extra={"placement": "prefix"}
    )
    with caplog.at_level(logging.WARNING):
        result = await handler("provider:request", {})
    return result, [r.message for r in caplog.records]


@pytest.mark.asyncio
async def test_A_control_surface_absent_names_no_surface(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """(a) No set_system_prompt_factory surface at all -> the "no surface"
    message is accurate here and must remain unchanged."""
    ctx = NoSurfaceContext()
    assert not hasattr(ctx, "set_system_prompt_factory")

    result, messages = await _fire(tmp_path, ctx, caplog)

    assert result.action == "inject_context"
    assert any(NO_SURFACE_NEEDLE in m for m in messages)
    assert not any(NO_FACTORY_NEEDLE in m for m in messages)


@pytest.mark.asyncio
async def test_B_surface_present_no_factory_names_real_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """(b) Surface exists, but nothing has registered a factory yet -- the
    real, common cause. Must NOT be misdiagnosed as "no surface"; must
    name "no factory registered" instead. The refusal-to-wrap behaviour
    (factory left None, fallback to inject_context) must be unchanged."""
    ctx = FakeContext()
    assert hasattr(ctx, "set_system_prompt_factory")  # surface EXISTS
    ctx._system_prompt_factory = None  # nothing registered it

    result, messages = await _fire(tmp_path, ctx, caplog)

    # This is the assertion that fails on unpatched main: main logs the
    # "no surface" text for this case even though the surface is present.
    assert any(NO_FACTORY_NEEDLE in m for m in messages), (
        f"expected a 'no factory registered' message, got: {messages!r}"
    )
    assert not any(NO_SURFACE_NEEDLE in m for m in messages), (
        "case (b) must not be misdiagnosed as 'no surface'"
    )

    # Refusal-to-wrap behaviour is unchanged: fallback fires, and the
    # factory slot is left untouched (still None).
    assert result.action == "inject_context"
    assert ctx._system_prompt_factory is None


@pytest.mark.asyncio
async def test_C_factory_registered_no_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """(c) Sanity: factory registered -> no warning, prefix wrapping
    succeeds, action is 'continue'."""
    ctx = FakeContext()  # helper registers a factory by default

    result, messages = await _fire(tmp_path, ctx, caplog)

    assert result.action == "continue"
    assert not any(NO_SURFACE_NEEDLE in m for m in messages)
    assert not any(NO_FACTORY_NEEDLE in m for m in messages)
