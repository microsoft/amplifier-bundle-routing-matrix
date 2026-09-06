"""Mount-time fan-out bound, and de-duplication of concurrent list_models().

WHAT THIS PROTECTS (the fail-before):

``on_session_start`` resolved every agent's ``model_role`` in ONE unbounded
``asyncio.gather``, and every glob candidate issued its own ``list_models()``
HTTPS request. On the measured 41-agent ``-b recipes`` bundle that is up to 41
simultaneous TLS handshakes, on EVERY session mount -- the CLI's own and every
spawned agent's.

That burst is the documented trigger for a native abort: 20-37 threads at a
time inside ``truststore`` 0.10.4's ``wrap_bio``, which calls
``_configure_context`` WITHOUT taking ``self._ctx_lock`` (its own
``wrap_socket`` does, ``_api.py:113-119``), so tens of threads run
``ctx.set_default_verify_paths()`` on one shared ``ssl.SSLContext`` and glibc
aborts the process -- ``double free or corruption``, exit 134 (sometimes
SIGSEGV, exit 139), with no Python traceback and no result envelope.

The missing lock is the defect and belongs upstream. These tests pin the
amplifier-side change that removes the TRIGGER regardless of which truststore
version is installed:

  1. at most ``max_concurrent_role_resolutions`` (default 4) resolutions in
     flight at once, and
  2. one ``list_models()`` call per PROVIDER per burst, not one per agent.

Both assertions are guarded against vacuity: each bounded case is paired with
a case that raises the bound and observes the concurrency the harness is
actually capable of producing.
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from amplifier_module_hooks_routing import mount
from amplifier_module_hooks_routing.resolver import _resolve_glob

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ConcurrencyTracker:
    """Shared counter recording peak simultaneous list_models() calls."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    def enter(self) -> None:
        self.calls += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)

    def exit(self) -> None:
        self.in_flight -= 1


class TrackingProvider:
    """Provider double whose list_models() takes real (awaited) time.

    The sleep matters: without an await inside list_models() every coroutine
    would run to completion before the next one started, and the test could
    not observe concurrency at all -- it would pass whether or not the
    semaphore existed.
    """

    def __init__(
        self,
        models: list[str],
        tracker: ConcurrencyTracker,
        delay: float = 0.01,
        fail: bool = False,
    ) -> None:
        self._models = models
        self._tracker = tracker
        self._delay = delay
        self._fail = fail

    async def list_models(self) -> list[str]:
        self._tracker.enter()
        try:
            await asyncio.sleep(self._delay)
            if self._fail:
                raise RuntimeError("provider unreachable")
            return list(self._models)
        finally:
            self._tracker.exit()


def _make_coordinator(
    *,
    providers: dict[str, Any],
    agents: dict[str, Any],
) -> MagicMock:
    """Minimal coordinator double: same shape test_init.py's helper builds."""
    coordinator = MagicMock()
    coordinator.session_state = {}
    coordinator.get = MagicMock(
        side_effect=lambda key: None if key == "context" else providers
    )
    coordinator.config = {"agents": agents}
    coordinator.get_capability = MagicMock(return_value=None)
    coordinator.hooks = MagicMock()
    coordinator.hooks.register = MagicMock()
    return coordinator


def _write_multi_provider_matrix(tmp_path: Path, provider_count: int) -> Path:
    """Matrix with one glob-bearing role per provider, and return the bundle root.

    Distinct providers on purpose: this isolates the SEMAPHORE. With every
    agent pointed at one provider, the coalescing in _fetch_model_names would
    collapse the burst to a single call and the concurrency bound would be
    untestable (and untested).
    """
    bundle_root = tmp_path / "bundle"
    routing_dir = bundle_root / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)

    roles = "\n".join(
        f"  role{i}:\n"
        f'    description: "Role {i}"\n'
        f"    candidates:\n"
        f"      - provider: p{i}\n"
        f"        model: model-*"
        for i in range(provider_count)
    )
    (routing_dir / "balanced.yaml").write_text(
        f'name: balanced\ndescription: "Fan-out test"\nupdated: "2026-01-01"\n\nroles:\n{roles}\n'
    )
    return bundle_root


def _write_single_provider_matrix(tmp_path: Path) -> Path:
    """Matrix where every agent resolves a glob against ONE provider."""
    bundle_root = tmp_path / "bundle"
    routing_dir = bundle_root / "routing"
    routing_dir.mkdir(parents=True, exist_ok=True)
    (routing_dir / "balanced.yaml").write_text(
        textwrap.dedent("""\
            name: balanced
            description: "Dedup test"
            updated: "2026-01-01"

            roles:
              coding:
                description: "Code"
                candidates:
                  - provider: anthropic
                    model: claude-sonnet-*
        """)
    )
    return bundle_root


def _session_start_handler(coordinator: MagicMock) -> Any:
    return next(
        call.args[1]
        for call in coordinator.hooks.register.call_args_list
        if call.args[0] == "session:start"
    )


async def _run_fanout(
    tmp_path: Path,
    *,
    agent_count: int,
    config_extra: dict[str, Any] | None = None,
) -> tuple[ConcurrencyTracker, dict[str, Any]]:
    """Mount + fire session:start over `agent_count` agents, one provider each."""
    bundle_root = _write_multi_provider_matrix(tmp_path, agent_count)
    tracker = ConcurrencyTracker()
    providers = {
        f"p{i}": TrackingProvider([f"model-{i}"], tracker) for i in range(agent_count)
    }
    agents = {f"agent{i}": {"model_role": f"role{i}"} for i in range(agent_count)}

    coordinator = _make_coordinator(providers=providers, agents=agents)
    await mount(
        coordinator,
        config={
            "default_matrix": "balanced",
            "_bundle_root": str(bundle_root),
            **(config_extra or {}),
        },
    )
    await _session_start_handler(coordinator)("session:start", {})
    return tracker, agents


# ---------------------------------------------------------------------------
# 1. The fan-out bound
# ---------------------------------------------------------------------------


class TestResolutionFanOutBound:
    """At most N model_role resolutions may be in flight at session:start."""

    AGENTS = 20

    @pytest.mark.asyncio
    async def test_unbounded_config_reaches_full_concurrency(
        self, tmp_path: Path
    ) -> None:
        """ANTI-VACUITY GUARD, and the fail-before in one test.

        Raising the ceiling to the agent count restores the pre-fix behaviour
        exactly: all 20 resolutions in flight at the same instant. If this
        did NOT hold, every bounded assertion below would be trivially true
        for the wrong reason (a harness that never produces concurrency at
        all), and the semaphore would be untested.
        """
        tracker, agents = await _run_fanout(
            tmp_path,
            agent_count=self.AGENTS,
            config_extra={"max_concurrent_role_resolutions": self.AGENTS},
        )

        assert tracker.peak == self.AGENTS, (
            f"harness produced only {tracker.peak}-way concurrency; the bounded "
            "assertions below would be vacuous"
        )
        assert all("provider_preferences" in cfg for cfg in agents.values())

    @pytest.mark.asyncio
    async def test_default_bound_caps_in_flight_resolutions(
        self, tmp_path: Path
    ) -> None:
        """With no config, at most 4 (the shipped default) run at once."""
        tracker, agents = await _run_fanout(tmp_path, agent_count=self.AGENTS)

        assert tracker.peak <= 4, (
            f"peak in-flight list_models() was {tracker.peak}, expected <= 4"
        )
        # Bounded, not dropped: every agent is still resolved.
        assert len(agents) == self.AGENTS
        for i, cfg in enumerate(agents.values()):
            assert cfg["provider_preferences"] == [
                {"provider": f"p{i}", "model": f"model-{i}"}
            ]
        assert tracker.calls == self.AGENTS  # distinct providers: no dedup here

    @pytest.mark.asyncio
    async def test_bound_is_config_overridable(self, tmp_path: Path) -> None:
        """max_concurrent_role_resolutions moves the ceiling, both directions."""
        strict, _ = await _run_fanout(
            tmp_path / "strict",
            agent_count=self.AGENTS,
            config_extra={"max_concurrent_role_resolutions": 1},
        )
        assert strict.peak == 1, f"serial config still ran {strict.peak} at once"

        loose, _ = await _run_fanout(
            tmp_path / "loose",
            agent_count=self.AGENTS,
            config_extra={"max_concurrent_role_resolutions": 8},
        )
        assert loose.peak <= 8
        # Proves the value is read, not just clamped to the default of 4.
        assert loose.peak > 4

    @pytest.mark.asyncio
    async def test_agents_without_model_role_are_untouched(
        self, tmp_path: Path
    ) -> None:
        """The semaphore does not change which agents get resolved."""
        bundle_root = _write_multi_provider_matrix(tmp_path, 2)
        tracker = ConcurrencyTracker()
        providers = {f"p{i}": TrackingProvider([f"model-{i}"], tracker) for i in range(2)}
        agents = {
            "resolved": {"model_role": "role0"},
            "plain": {"description": "no model_role"},
        }
        coordinator = _make_coordinator(providers=providers, agents=agents)
        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )
        await _session_start_handler(coordinator)("session:start", {})

        assert "provider_preferences" in agents["resolved"]
        assert "provider_preferences" not in agents["plain"]

    @pytest.mark.parametrize("bad", [0, -1, "four", 4.5, None, True])
    @pytest.mark.asyncio
    async def test_invalid_bound_rejected_at_mount(
        self, tmp_path: Path, bad: Any
    ) -> None:
        """Fail loud at mount, like `placement` does.

        A typo here silently removes the protection this exists to provide,
        and mount time is the cheapest possible place to find out. ``True``
        is in the list on purpose: bool is an int subclass, so a naive
        isinstance check would accept ``max_concurrent_role_resolutions:
        true`` and quietly run a fan-out of 1.
        """
        bundle_root = _write_multi_provider_matrix(tmp_path, 1)
        coordinator = _make_coordinator(providers={}, agents={})
        with pytest.raises(ValueError, match="max_concurrent_role_resolutions"):
            await mount(
                coordinator,
                config={
                    "default_matrix": "balanced",
                    "_bundle_root": str(bundle_root),
                    "max_concurrent_role_resolutions": bad,
                },
            )


# ---------------------------------------------------------------------------
# 2. De-duplication of simultaneous list_models() calls
# ---------------------------------------------------------------------------


class TestConcurrentListModelsDedup:
    """N agents globbing against ONE provider produce ONE list_models() call.

    ``preresolved_models`` alone cannot achieve this: it is only consulted
    after a fetch has RETURNED, and every member of a concurrent burst reads
    it before any of them has.
    """

    @pytest.mark.asyncio
    async def test_concurrent_globs_share_one_fetch(self) -> None:
        tracker = ConcurrencyTracker()
        provider = TrackingProvider(["claude-sonnet-4-5", "claude-haiku-3"], tracker)
        preresolved: dict[str, list[str]] = {}
        inflight: dict[str, Any] = {}

        results = await asyncio.gather(
            *(
                _resolve_glob(
                    "claude-sonnet-*",
                    provider,
                    "anthropic",
                    preresolved,
                    inflight,
                )
                for _ in range(20)
            )
        )

        assert tracker.calls == 1, (
            f"20 concurrent glob resolutions issued {tracker.calls} list_models() "
            "calls; expected 1"
        )
        assert results == ["claude-sonnet-4-5"] * 20
        # The winner still populates the durable cache for later callers...
        assert preresolved["anthropic"] == ["claude-sonnet-4-5", "claude-haiku-3"]
        # ...and the in-flight slot is released, never leaked.
        assert inflight == {}

    @pytest.mark.asyncio
    async def test_without_inflight_map_every_caller_fetches(self) -> None:
        """The fail-before, and proof the default is byte-compatible.

        Omitting `inflight_model_lists` preserves the exact pre-existing call
        pattern -- which is also what the burst used to look like.
        """
        tracker = ConcurrencyTracker()
        provider = TrackingProvider(["claude-sonnet-4-5"], tracker)

        await asyncio.gather(
            *(
                _resolve_glob("claude-sonnet-*", provider, "anthropic", {})
                for _ in range(20)
            )
        )

        assert tracker.calls == 20

    @pytest.mark.asyncio
    async def test_failure_is_shared_and_reported_per_caller(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing provider also costs one request -- with warnings unchanged.

        Every caller still handles and logs its own failure and returns None,
        exactly as before; only the duplicate HTTP calls are removed.
        """
        tracker = ConcurrencyTracker()
        provider = TrackingProvider([], tracker, fail=True)
        inflight: dict[str, Any] = {}

        with caplog.at_level("WARNING"):
            results = await asyncio.gather(
                *(
                    _resolve_glob("claude-sonnet-*", provider, "anthropic", {}, inflight)
                    for _ in range(5)
                )
            )

        assert tracker.calls == 1
        assert results == [None] * 5
        warnings = [r for r in caplog.records if "Failed to list models" in r.message]
        assert len(warnings) == 5, "each caller must still report its own failure"
        assert inflight == {}

    @pytest.mark.asyncio
    async def test_failed_fetch_may_be_retried_later(self) -> None:
        """Coalescing is per-burst, not a negative cache.

        A later call re-attempts a provider whose earlier fetch failed --
        the same retry behaviour that existed before coalescing.
        """
        tracker = ConcurrencyTracker()
        failing = TrackingProvider([], tracker, fail=True)
        inflight: dict[str, Any] = {}

        assert (
            await _resolve_glob("claude-*", failing, "anthropic", {}, inflight) is None
        )
        assert tracker.calls == 1

        recovered = TrackingProvider(["claude-sonnet-4-5"], tracker)
        assert (
            await _resolve_glob("claude-*", recovered, "anthropic", {}, inflight)
            == "claude-sonnet-4-5"
        )
        assert tracker.calls == 2

    @pytest.mark.asyncio
    async def test_distinct_providers_are_not_coalesced_together(self) -> None:
        """Coalescing is per provider key -- never across providers."""
        tracker = ConcurrencyTracker()
        anthropic = TrackingProvider(["claude-sonnet-4-5"], tracker)
        openai = TrackingProvider(["gpt-5.4"], tracker)
        inflight: dict[str, Any] = {}

        results = await asyncio.gather(
            _resolve_glob("claude-*", anthropic, "anthropic", {}, inflight),
            _resolve_glob("claude-*", anthropic, "anthropic", {}, inflight),
            _resolve_glob("gpt-*", openai, "openai", {}, inflight),
            _resolve_glob("gpt-*", openai, "openai", {}, inflight),
        )

        assert tracker.calls == 2
        assert results == ["claude-sonnet-4-5", "claude-sonnet-4-5", "gpt-5.4", "gpt-5.4"]


# ---------------------------------------------------------------------------
# 3. End to end: the 41-agent bundle from the report
# ---------------------------------------------------------------------------


class TestMountTimeHttpCallCount:
    """The number the report measures: HTTPS calls at one session mount."""

    @pytest.mark.asyncio
    async def test_41_agents_one_provider_make_one_call(self, tmp_path: Path) -> None:
        """41 agents (the measured `-b recipes` bundle) -> 1 list_models() call.

        Before: 41 concurrent calls, i.e. 41 simultaneous TLS handshakes.
        The semaphore alone would still leave 4 (one per initial slot, all
        missing the not-yet-populated cache); the coalescing takes it to 1.
        """
        bundle_root = _write_single_provider_matrix(tmp_path)
        tracker = ConcurrencyTracker()
        provider = TrackingProvider(
            ["claude-sonnet-4-5-20260101", "claude-haiku-4-5"], tracker
        )
        providers = {"provider-anthropic": provider}
        agents = {f"agent{i}": {"model_role": "coding"} for i in range(41)}

        coordinator = _make_coordinator(providers=providers, agents=agents)
        await mount(
            coordinator,
            config={"default_matrix": "balanced", "_bundle_root": str(bundle_root)},
        )
        await _session_start_handler(coordinator)("session:start", {})

        assert tracker.calls == 1, (
            f"41-agent mount issued {tracker.calls} list_models() calls; expected 1"
        )
        assert tracker.peak == 1
        # Same resolution result for every agent -- unchanged by either fix.
        for cfg in agents.values():
            assert cfg["provider_preferences"] == [
                {
                    "provider": "provider-anthropic",
                    "model": "claude-sonnet-4-5-20260101",
                }
            ]
