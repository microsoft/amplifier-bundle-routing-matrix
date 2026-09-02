"""Shadowing must be OBSERVABLE — precedence itself is unchanged.

A same-named matrix in a user routing dir (``~/.amplifier/routing/``) outranks
the bundle's own shipped matrix. That is deliberate. What was NOT deliberate is
that it happened silently: no log named the winning file, no warning named the
suppressed one, and no surface exposed which file was in effect. On a host with
a user routing dir, every matrix change shipped in the bundle was inert and
nothing anywhere said so.

These tests pin the three halves of the fix and, just as importantly, pin that
the precedence rule did not move:

* shadow PRESENT  -> a WARNING naming BOTH the winner and the shadowed file
* shadow ABSENT   -> no WARNING/ERROR at all, and identical resolution
* effective source-> correct in both cases, on the capability and the event log
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_hooks_routing import mount
from amplifier_module_hooks_routing.matrix_loader import resolve_matrix_source

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUNDLE_MATRIX = textwrap.dedent("""\
    name: openai
    description: "Shipped matrix"
    updated: "2026-01-01"
    roles:
      general:
        description: "General purpose"
        candidates:
          - provider: openai
            model: gpt-5.6-terra
      fast:
        description: "Fast tasks"
        candidates:
          - provider: openai
            model: gpt-5.6-luna
      reasoning:
        description: "Deep reasoning"
        candidates:
          - provider: openai
            model: gpt-5.6-sol
            config:
              reasoning_effort: xhigh
""")

# The measured real-world divergence: the user's file pins a DIFFERENT effort
# on the exact role the bundle edited (max vs the shipped xhigh).
_USER_MATRIX = _BUNDLE_MATRIX.replace(
    'description: "Shipped matrix"', 'description: "Custom matrix: openai"'
).replace("reasoning_effort: xhigh", "reasoning_effort: max")


def _make_coordinator() -> MagicMock:
    """Coordinator mock with an event bus, matching this module's real API."""
    hooks_bus = MagicMock()
    hooks_bus.emit = AsyncMock()

    coordinator = MagicMock()

    def _get(key: str) -> Any:
        if key == "context":
            return None
        if key == "hooks":
            return hooks_bus
        return {}

    coordinator.get = MagicMock(side_effect=_get)
    coordinator.config = {"agents": {}}
    coordinator.get_capability = MagicMock(return_value=None)
    coordinator.register_capability = MagicMock()
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    coordinator.event_bus = hooks_bus
    return coordinator


def _bundle_root(tmp_path: Path, *, with_matrix: bool = True) -> Path:
    root = tmp_path / "bundle"
    routing = root / "routing"
    routing.mkdir(parents=True, exist_ok=True)
    if with_matrix:
        (routing / "openai.yaml").write_text(_BUNDLE_MATRIX, encoding="utf-8")
    return root


def _custom_dir(tmp_path: Path, *, with_matrix: bool = True) -> Path:
    custom = tmp_path / "user-routing"
    custom.mkdir(parents=True, exist_ok=True)
    if with_matrix:
        (custom / "openai.yaml").write_text(_USER_MATRIX, encoding="utf-8")
    return custom


async def _mount(
    coordinator: MagicMock,
    bundle_root: Path,
    custom_dirs: list[Path] | None = None,
) -> None:
    config: dict[str, Any] = {
        "default_matrix": "openai",
        "_bundle_root": str(bundle_root),
    }
    if custom_dirs is not None:
        config["custom_routing_dirs"] = [str(d) for d in custom_dirs]
    await mount(coordinator, config=config)


def _resolver_from(coordinator: MagicMock) -> Any:
    for call in coordinator.register_capability.call_args_list:
        if call.args and call.args[0] == "model_role_resolver":
            return call.args[1]
    return None


async def _run_session_start(coordinator: MagicMock) -> None:
    handlers = [
        call.args[1]
        for call in coordinator.hooks.register.call_args_list
        if call.args[0] == "session:start"
    ]
    assert handlers, "session:start handler was not registered"
    await handlers[0]("session:start", {})


def _events(coordinator: MagicMock, name: str) -> list[tuple[Any, ...]]:
    return [
        call.args
        for call in coordinator.event_bus.emit.call_args_list
        if call.args and call.args[0] == name
    ]


# ---------------------------------------------------------------------------
# resolve_matrix_source — the pure precedence + provenance function
# ---------------------------------------------------------------------------


class TestResolveMatrixSource:
    def test_user_file_wins_and_bundle_file_is_recorded_as_shadowed(
        self, tmp_path: Path
    ) -> None:
        bundle = _bundle_root(tmp_path) / "routing"
        custom = _custom_dir(tmp_path)

        origin = resolve_matrix_source("openai", [custom], bundle)

        assert origin.path == custom / "openai.yaml"
        assert origin.source == "user"
        assert origin.is_shadowed is True
        assert origin.shadowed == ((bundle / "openai.yaml", "bundle"),)

    def test_bundle_only_is_not_shadowed(self, tmp_path: Path) -> None:
        bundle = _bundle_root(tmp_path) / "routing"
        custom = _custom_dir(tmp_path, with_matrix=False)

        origin = resolve_matrix_source("openai", [custom], bundle)

        assert origin.path == bundle / "openai.yaml"
        assert origin.source == "bundle"
        assert origin.is_shadowed is False
        assert origin.shadowed == ()

    def test_missing_everywhere_reports_no_path_and_no_shadow(
        self, tmp_path: Path
    ) -> None:
        bundle = _bundle_root(tmp_path, with_matrix=False) / "routing"

        origin = resolve_matrix_source("openai", [], bundle)

        assert origin.path is None
        assert origin.source is None
        assert origin.is_shadowed is False
        assert origin.searched == (bundle / "openai.yaml",)

    def test_first_custom_dir_wins_over_later_custom_dirs(
        self, tmp_path: Path
    ) -> None:
        """Shadowing is not exclusively user-vs-bundle: user-vs-user counts."""
        bundle = _bundle_root(tmp_path) / "routing"
        first = tmp_path / "first"
        second = tmp_path / "second"
        for d in (first, second):
            d.mkdir()
            (d / "openai.yaml").write_text(_USER_MATRIX, encoding="utf-8")

        origin = resolve_matrix_source("openai", [first, second], bundle)

        assert origin.path == first / "openai.yaml"
        assert [p for p, _ in origin.shadowed] == [
            second / "openai.yaml",
            bundle / "openai.yaml",
        ]

    def test_same_dir_listed_twice_is_not_a_phantom_shadow(
        self, tmp_path: Path
    ) -> None:
        """A file cannot shadow itself — dedupe by resolved path."""
        bundle = _bundle_root(tmp_path) / "routing"
        custom = _custom_dir(tmp_path)

        origin = resolve_matrix_source(
            "openai", [custom, custom, Path(str(custom) + "/.")], bundle
        )

        assert origin.path == custom / "openai.yaml"
        assert origin.shadowed == ((bundle / "openai.yaml", "bundle"),)

    def test_bundle_dir_passed_as_custom_dir_is_labelled_bundle(
        self, tmp_path: Path
    ) -> None:
        """Provenance follows where the file LIVES, not which arg carried it.

        Labelling this "user" would report a bundle matrix as a user override
        and — worse — report the bundle file as shadowing itself.
        """
        bundle = _bundle_root(tmp_path) / "routing"

        origin = resolve_matrix_source("openai", [bundle], bundle)

        assert origin.path == bundle / "openai.yaml"
        assert origin.source == "bundle"
        assert origin.is_shadowed is False

    def test_to_dict_is_json_safe(self, tmp_path: Path) -> None:
        bundle = _bundle_root(tmp_path) / "routing"
        custom = _custom_dir(tmp_path)

        payload = resolve_matrix_source("openai", [custom], bundle).to_dict()

        assert payload == {
            "matrix_name": "openai",
            "matrix_path": str(custom / "openai.yaml"),
            "matrix_source": "user",
            "matrix_shadowed": True,
            "shadowed_paths": [str(bundle / "openai.yaml")],
        }


# ---------------------------------------------------------------------------
# Shadow PRESENT — the warning
# ---------------------------------------------------------------------------


class TestShadowPresentWarns:
    @pytest.mark.asyncio
    async def test_warning_names_both_the_winner_and_the_shadowed_file(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bundle_root = _bundle_root(tmp_path)
        custom = _custom_dir(tmp_path)
        coordinator = _make_coordinator()

        with caplog.at_level(
            logging.WARNING, logger="amplifier_module_hooks_routing"
        ):
            await _mount(coordinator, bundle_root, [custom])

        blob = "\n".join(r.getMessage() for r in caplog.records)
        assert "SHADOWED" in blob
        assert str(custom / "openai.yaml") in blob, "winning path must be named"
        assert str(bundle_root / "routing" / "openai.yaml") in blob, (
            "shadowed path must be named — naming only the winner leaves the "
            "operator unable to tell WHICH shipped file went dead"
        )
        assert "source=user" in blob

    @pytest.mark.asyncio
    async def test_warning_is_a_warning_not_an_info(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A dead shipped matrix must survive the default log level."""
        bundle_root = _bundle_root(tmp_path)
        custom = _custom_dir(tmp_path)
        coordinator = _make_coordinator()

        with caplog.at_level(
            logging.WARNING, logger="amplifier_module_hooks_routing"
        ):
            await _mount(coordinator, bundle_root, [custom])

        assert [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING and "SHADOWED" in r.getMessage()
        ]


# ---------------------------------------------------------------------------
# Shadow ABSENT — silence, and behaviour identical to before
# ---------------------------------------------------------------------------


class TestShadowAbsentIsSilent:
    @pytest.mark.asyncio
    async def test_bundle_only_emits_no_warning_or_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bundle_root = _bundle_root(tmp_path)
        coordinator = _make_coordinator()

        with caplog.at_level(logging.INFO, logger="amplifier_module_hooks_routing"):
            await _mount(coordinator, bundle_root, [])

        noisy = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not noisy, (
            "an unshadowed host must stay quiet — a warning here would train "
            f"operators to ignore the real one. Got: {[r.getMessage() for r in noisy]}"
        )

    @pytest.mark.asyncio
    async def test_custom_dir_without_that_matrix_emits_no_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Having a user routing dir is not itself shadowing."""
        bundle_root = _bundle_root(tmp_path)
        custom = _custom_dir(tmp_path, with_matrix=False)
        coordinator = _make_coordinator()

        with caplog.at_level(logging.INFO, logger="amplifier_module_hooks_routing"):
            await _mount(coordinator, bundle_root, [custom])

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    @pytest.mark.asyncio
    async def test_resolution_is_unchanged_when_unshadowed(
        self, tmp_path: Path
    ) -> None:
        """Observability must not touch what routing actually resolves."""
        bundle_root = _bundle_root(tmp_path)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [])

        roles = _resolver_from(coordinator)._matrix_roles
        assert roles["reasoning"]["candidates"] == [
            {
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "config": {"reasoning_effort": "xhigh"},
            }
        ]

    @pytest.mark.asyncio
    async def test_info_log_names_the_winning_path_even_when_unshadowed(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The winning path used to be named ONLY when loading failed."""
        bundle_root = _bundle_root(tmp_path)
        coordinator = _make_coordinator()

        with caplog.at_level(logging.INFO, logger="amplifier_module_hooks_routing"):
            await _mount(coordinator, bundle_root, [])

        blob = "\n".join(r.getMessage() for r in caplog.records)
        assert str(bundle_root / "routing" / "openai.yaml") in blob
        assert "source=bundle" in blob


# ---------------------------------------------------------------------------
# Precedence UNCHANGED — the deliberate non-fix
# ---------------------------------------------------------------------------


class TestPrecedenceUnchanged:
    @pytest.mark.asyncio
    async def test_user_file_still_wins(self, tmp_path: Path) -> None:
        """Making shadowing loud must not also make it stop happening.

        Reporting the shadowing is the fix; reversing it is a separate,
        unratified decision.
        """
        bundle_root = _bundle_root(tmp_path)
        custom = _custom_dir(tmp_path)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [custom])

        roles = _resolver_from(coordinator)._matrix_roles
        assert roles["reasoning"]["candidates"][0]["config"] == {
            "reasoning_effort": "max"
        }, "the user file must still win — precedence is unchanged by this fix"


# ---------------------------------------------------------------------------
# Effective source — exposed on the capability and in the event log
# ---------------------------------------------------------------------------


class TestEffectiveSourceExposure:
    @pytest.mark.asyncio
    async def test_resolver_reports_user_source_when_shadowed(
        self, tmp_path: Path
    ) -> None:
        bundle_root = _bundle_root(tmp_path)
        custom = _custom_dir(tmp_path)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [custom])

        resolver = _resolver_from(coordinator)
        assert resolver.matrix_path == str(custom / "openai.yaml")
        assert resolver.matrix_source == "user"
        assert resolver.shadowed_paths == (
            str(bundle_root / "routing" / "openai.yaml"),
        )

    @pytest.mark.asyncio
    async def test_resolver_reports_bundle_source_when_not_shadowed(
        self, tmp_path: Path
    ) -> None:
        bundle_root = _bundle_root(tmp_path)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [])

        resolver = _resolver_from(coordinator)
        assert resolver.matrix_path == str(bundle_root / "routing" / "openai.yaml")
        assert resolver.matrix_source == "bundle"
        assert resolver.shadowed_paths == ()

    @pytest.mark.asyncio
    async def test_matrix_loaded_event_carries_effective_source(
        self, tmp_path: Path
    ) -> None:
        bundle_root = _bundle_root(tmp_path)
        custom = _custom_dir(tmp_path)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [custom])
        await _run_session_start(coordinator)

        emitted = _events(coordinator, "routing:matrix-loaded")
        assert len(emitted) == 1, "exactly one effective-source record per session"
        payload = emitted[0][1]
        assert payload["matrix_path"] == str(custom / "openai.yaml")
        assert payload["matrix_source"] == "user"
        assert payload["matrix_shadowed"] is True
        assert payload["shadowed_paths"] == [
            str(bundle_root / "routing" / "openai.yaml")
        ]

    @pytest.mark.asyncio
    async def test_matrix_loaded_event_reports_unshadowed_bundle_source(
        self, tmp_path: Path
    ) -> None:
        bundle_root = _bundle_root(tmp_path)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [])
        await _run_session_start(coordinator)

        payload = _events(coordinator, "routing:matrix-loaded")[0][1]
        assert payload["matrix_source"] == "bundle"
        assert payload["matrix_shadowed"] is False
        assert payload["shadowed_paths"] == []

    @pytest.mark.asyncio
    async def test_no_event_when_no_matrix_was_loaded(self, tmp_path: Path) -> None:
        """Nothing loaded means nothing to attribute — the not-found warning
        already covers that case, and a record naming a null path would only
        look like a source."""
        bundle_root = _bundle_root(tmp_path, with_matrix=False)
        coordinator = _make_coordinator()

        await _mount(coordinator, bundle_root, [])
        await _run_session_start(coordinator)

        assert _events(coordinator, "routing:matrix-loaded") == []

    @pytest.mark.asyncio
    async def test_reporting_failure_never_breaks_routing(
        self, tmp_path: Path
    ) -> None:
        """Routing a session is the job; reporting on it is not allowed to
        break it."""
        bundle_root = _bundle_root(tmp_path)
        coordinator = _make_coordinator()
        coordinator.event_bus.emit = AsyncMock(side_effect=RuntimeError("bus down"))

        await _mount(coordinator, bundle_root, [])
        await _run_session_start(coordinator)  # must not raise

        assert _resolver_from(coordinator) is not None
