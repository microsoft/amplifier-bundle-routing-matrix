"""Tests for resolver module."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_hooks_routing.resolver import (
    _resolve_glob,
    find_provider_by_type,
    resolve_model_role,
)
from amplifier_module_hooks_routing.resolver_class import MatrixModelRoleResolver

# ---------------------------------------------------------------------------
# Helper to build mock providers dict
# ---------------------------------------------------------------------------


def _make_provider(
    models: list[str] | None = None,
    raises: bool = False,
) -> MagicMock:
    """Create a mock provider with optional list_models support."""
    provider = MagicMock()
    if models is not None:
        if raises:
            provider.list_models = AsyncMock(side_effect=RuntimeError("boom"))
        else:
            provider.list_models = AsyncMock(return_value=models)
    else:
        # No list_models attribute
        del provider.list_models
    return provider


# ---------------------------------------------------------------------------
# find_provider_by_type tests
# ---------------------------------------------------------------------------


class TestFindProviderByType:
    def test_exact_match(self) -> None:
        prov = MagicMock()
        providers = {"anthropic": prov}
        result = find_provider_by_type(providers, "anthropic")
        assert result == ("anthropic", prov)

    def test_provider_prefix_match(self) -> None:
        """'anthropic' matches key 'provider-anthropic'."""
        prov = MagicMock()
        providers = {"provider-anthropic": prov}
        result = find_provider_by_type(providers, "anthropic")
        assert result == ("provider-anthropic", prov)

    def test_no_match_returns_none(self) -> None:
        providers = {"provider-openai": MagicMock()}
        result = find_provider_by_type(providers, "anthropic")
        assert result is None


# ---------------------------------------------------------------------------
# resolve_model_role tests
# ---------------------------------------------------------------------------


class TestResolveModelRole:
    @pytest.mark.asyncio
    async def test_resolve_single_role_matches(self, sample_roles: dict) -> None:
        """Role in matrix, provider installed, returns match.

        ``result[0]["provider"]`` is the *matched mount key* (here
        "provider-anthropic", the actual providers-dict key), not the bare
        "anthropic" written in the matrix candidate -- see resolve_model_role's
        docstring on why the matched key must be returned.
        """
        providers = {"provider-anthropic": _make_provider()}

        result = await resolve_model_role(["general"], sample_roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "provider-anthropic"
        assert result[0]["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_second_role(self, sample_roles: dict) -> None:
        """First role not in matrix, second matches."""
        providers = {"provider-openai": _make_provider()}

        result = await resolve_model_role(
            ["nonexistent", "fast"], sample_roles, providers
        )

        assert len(result) == 1
        assert result[0]["provider"] == "provider-openai"
        assert result[0]["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_resolve_provider_not_installed_skips(
        self, sample_roles: dict
    ) -> None:
        """Candidate provider not installed, falls to next candidate."""
        # general has anthropic only; we only have openai installed
        # coding has anthropic then openai
        providers = {"provider-openai": _make_provider()}

        result = await resolve_model_role(["coding"], sample_roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "provider-openai"
        assert result[0]["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_resolve_glob_pattern(self) -> None:
        """claude-sonnet-* resolves against list_models()."""
        models = [
            "claude-sonnet-4-20250514",
            "claude-sonnet-3.5-20240620",
            "claude-haiku-3-20240307",
        ]
        providers = {"provider-anthropic": _make_provider(models=models)}
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},
                ],
            },
        }

        result = await resolve_model_role(["coding"], roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "provider-anthropic"
        # Sorted descending, sonnet-4 > sonnet-3.5
        assert result[0]["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_resolve_glob_pattern_case_insensitive(self) -> None:
        """Regression test: model glob matching must be case-insensitive and
        OS-independent. Raw fnmatch.filter() uses os.path.normcase, which is
        case-sensitive on Linux/Mac and case-insensitive on Windows -- so a
        real-world mixed-case model id (e.g. 'Qwen3.6-35B-A3B-UD-Q4_K_XL')
        would silently fail to match a lowercase pattern ('qwen3.6-*') on
        Linux/Mac while matching on Windows. Must be deterministic across
        platforms and consistent with amplifier_foundation.spawn_utils'
        agent-spawn model resolution semantics.
        """
        models = ["Qwen3.6-35B-A3B-UD-Q4_K_XL"]
        providers = {"provider-ornith": _make_provider(models=models)}
        roles = {
            "general": {
                "description": "General",
                "candidates": [
                    {"provider": "ornith", "model": "qwen3.6-*"},
                ],
            },
        }

        result = await resolve_model_role(["general"], roles, providers)

        assert len(result) == 1
        assert result[0]["model"] == "Qwen3.6-35B-A3B-UD-Q4_K_XL", (
            f"Expected case-insensitive glob match, got: {result}"
        )

    @pytest.mark.asyncio
    async def test_resolve_no_match_returns_empty(self) -> None:
        """No roles match anything → empty list."""
        providers = {"provider-openai": _make_provider()}
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                ],
            },
        }

        result = await resolve_model_role(["coding"], roles, providers)

        assert result == []

    @pytest.mark.asyncio
    async def test_resolve_config_passed_through(self) -> None:
        """Candidate with config has it in result."""
        providers = {"provider-anthropic": _make_provider()}
        roles = {
            "reasoning": {
                "description": "Reasoning",
                "candidates": [
                    {
                        "provider": "anthropic",
                        "model": "claude-opus-4-6",
                        "config": {"reasoning_effort": "high"},
                    },
                ],
            },
        }

        result = await resolve_model_role(["reasoning"], roles, providers)

        assert len(result) == 1
        assert result[0]["config"] == {"reasoning_effort": "high"}

    @pytest.mark.asyncio
    async def test_resolve_provider_type_flexible_matching(self) -> None:
        """'anthropic' matches 'provider-anthropic' key.

        The *matching* is flexible (bare "anthropic" finds the
        "provider-anthropic" key); the *returned* provider identifier is the
        matched key itself, not the bare candidate string -- downstream
        consumers re-match against the same providers dict / mount plan and
        need the exact key that was actually found.
        """
        providers = {"provider-anthropic": _make_provider()}
        roles = {
            "general": {
                "description": "General",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                ],
            },
        }

        result = await resolve_model_role(["general"], roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "provider-anthropic"

    @pytest.mark.asyncio
    async def test_resolve_list_models_failure_skips(self) -> None:
        """If list_models() raises, skip that candidate."""
        providers = {
            "provider-anthropic": _make_provider(models=[], raises=True),
            "provider-openai": _make_provider(),
        }
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},
                    {"provider": "openai", "model": "gpt-4o"},
                ],
            },
        }

        result = await resolve_model_role(["coding"], roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "provider-openai"
        assert result[0]["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_resolve_glob_no_match_skips(self) -> None:
        """Glob pattern that matches nothing skips to next candidate."""
        providers = {
            "provider-anthropic": _make_provider(models=["claude-haiku-3-20240307"]),
            "provider-openai": _make_provider(),
        }
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},
                    {"provider": "openai", "model": "gpt-4o"},
                ],
            },
        }

        result = await resolve_model_role(["coding"], roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "provider-openai"


# ---------------------------------------------------------------------------
# Gemini rename regression (bug 2026-04-22)
# ---------------------------------------------------------------------------


class TestGeminiProviderNameRegression:
    """Regression for the 'provider: google' vs 'provider: gemini' bug.

    The Gemini provider module mounts under the key 'gemini'. Every matrix
    previously used 'provider: google', which silently failed to resolve
    (resolver does exact match; 'google' never equals 'gemini'). Fixed by
    renaming all matrix candidates to 'provider: gemini'.
    """

    def test_gemini_provider_type_matches_gemini_key(self) -> None:
        """After rename, 'gemini' in matrix finds the mounted 'gemini' provider."""
        prov = MagicMock()
        providers = {"gemini": prov}
        result = find_provider_by_type(providers, "gemini")
        assert result == ("gemini", prov), (
            "After rename, provider: gemini in a matrix must find the mounted gemini provider"
        )

    def test_google_provider_type_does_not_match_gemini_key(self) -> None:
        """'google' in a matrix must NOT match a mounted 'gemini' provider.

        Prevents silent regression if someone reintroduces the old name.
        """
        prov = MagicMock()
        providers = {"gemini": prov}
        result = find_provider_by_type(providers, "google")
        assert result is None, (
            "provider: google must not resolve to a gemini-mounted provider "
            "(silent-failure regression from pre-2026-04-22)"
        )


# ---------------------------------------------------------------------------
# Multi-instance provider addressing
# ---------------------------------------------------------------------------


class TestMultiInstanceProviderResolution:
    """Users can run multiple instances of the same provider module by setting
    an 'id' in their settings.yaml. The kernel remaps them to instance-ID keys
    in coordinator.providers. Matrices can target a specific instance by putting
    the instance ID in the 'provider:' field.
    """

    def test_instance_id_exact_match(self) -> None:
        """provider: openai-internal finds the mounted openai-internal key."""
        internal = MagicMock()
        external = MagicMock()
        providers = {
            "openai-internal": internal,
            "openai-external": external,
        }
        result = find_provider_by_type(providers, "openai-internal")
        assert result == ("openai-internal", internal)

        result = find_provider_by_type(providers, "openai-external")
        assert result == ("openai-external", external)

    def test_instance_id_does_not_cross_match(self) -> None:
        """Asking for 'openai' when only instance IDs exist returns None."""
        providers = {
            "openai-internal": MagicMock(),
            "openai-external": MagicMock(),
        }
        # Neither instance is mounted under bare "openai", so type-name lookup fails.
        result = find_provider_by_type(providers, "openai")
        assert result is None


# ---------------------------------------------------------------------------
# Bare-type fallback against multi-instance providers (sibling bug to
# amplifier-foundation #267: `_find_provider_instance()` had the identical
# gap). Reproduces the exact production scenario: 3 named Anthropic
# instances (anthropic-sonnet priority 1/default, anthropic-opus priority 2,
# anthropic-haiku priority 9), none keyed bare "anthropic". A matrix
# candidate naming the bare type "anthropic" must still resolve -- to the
# highest-priority (lowest priority number) instance -- via a coordinator
# config fallback, mirroring the "default provider" convention.
# ---------------------------------------------------------------------------


def _make_coordinator_with_provider_specs(specs: list[dict]) -> MagicMock:
    """Build a minimal coordinator-like stub exposing `.config["providers"]`."""
    coordinator = MagicMock()
    coordinator.config = {"providers": specs}
    return coordinator


_ANTHROPIC_MULTI_INSTANCE_SPECS = [
    {
        "module": "provider-anthropic",
        "id": "anthropic-sonnet",
        "config": {"priority": 1},
    },
    {
        "module": "provider-anthropic",
        "id": "anthropic-opus",
        "config": {"priority": 2},
    },
    {
        "module": "provider-anthropic",
        "id": "anthropic-haiku",
        "config": {"priority": 9},
    },
]


class TestBareTypeFallbackAgainstMultiInstanceProviders:
    def test_find_provider_by_type_falls_back_to_default_instance(self) -> None:
        """No key is bare 'anthropic'; today this returns None. With the
        coordinator fallback it must return the priority-1/default instance.
        """
        sonnet = MagicMock()
        opus = MagicMock()
        haiku = MagicMock()
        providers = {
            "anthropic-sonnet": sonnet,
            "anthropic-opus": opus,
            "anthropic-haiku": haiku,
        }
        coordinator = _make_coordinator_with_provider_specs(
            _ANTHROPIC_MULTI_INSTANCE_SPECS
        )

        result = find_provider_by_type(providers, "anthropic", coordinator)

        assert result == ("anthropic-sonnet", sonnet), (
            "Bare type 'anthropic' must resolve to the lowest-priority-number "
            "(default) instance via the coordinator config fallback"
        )

    def test_find_provider_by_type_without_coordinator_still_returns_none(
        self,
    ) -> None:
        """Backward compatibility: omitting coordinator preserves old behaviour."""
        providers = {
            "anthropic-sonnet": MagicMock(),
            "anthropic-opus": MagicMock(),
        }
        result = find_provider_by_type(providers, "anthropic")
        assert result is None

    def test_find_provider_by_type_no_matching_specs_returns_none(self) -> None:
        """Coordinator present but no spec matches the requested type."""
        providers = {"anthropic-sonnet": MagicMock()}
        coordinator = _make_coordinator_with_provider_specs(
            [{"module": "provider-openai", "id": "openai-main", "config": {}}]
        )
        result = find_provider_by_type(providers, "anthropic", coordinator)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_model_role_fast_role_resolves_via_fallback(self) -> None:
        """End-to-end: 'fast' role -> provider: anthropic, model: claude-haiku-*
        must resolve against the multi-instance setup, exactly reproducing the
        production scenario (previously returned []).

        All three instances share one Anthropic account, so ``list_models()``
        returns the same full catalog regardless of which instance answers --
        matching the real, directly-verified API response (9 models,
        including multiple haiku/opus variants) rather than an artificially
        restricted per-instance list.
        """
        full_catalog = [
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
            "claude-haiku-3-20240307",
        ]
        providers = {
            "anthropic-sonnet": _make_provider(models=full_catalog),
            "anthropic-opus": _make_provider(models=full_catalog),
            "anthropic-haiku": _make_provider(models=full_catalog),
        }
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        coordinator = _make_coordinator_with_provider_specs(
            _ANTHROPIC_MULTI_INSTANCE_SPECS
        )

        result = await resolve_model_role(
            ["fast"], roles, providers, coordinator=coordinator
        )

        assert len(result) == 1, (
            "Expected 'fast' role to resolve to one candidate via the "
            "bare-type coordinator fallback, got: %r" % (result,)
        )
        # The returned "provider" is the matched mount key -- the priority-1
        # (default) instance the fallback selected -- not the matrix's bare
        # "anthropic" string. Downstream consumers (loop-streaming,
        # hooks-session-naming) re-match this exact key against the same
        # providers dict; a bare type here would never match "anthropic-sonnet".
        assert result[0]["provider"] == "anthropic-sonnet"
        assert result[0]["model"] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_resolve_model_role_without_coordinator_still_fails(self) -> None:
        """Without a coordinator, resolve_model_role preserves the old (buggy)
        behaviour of returning [] -- proving the coordinator param is what
        fixes it, not some other change.
        """
        full_catalog = ["claude-sonnet-5", "claude-haiku-4-5-20251001"]
        providers = {
            "anthropic-sonnet": _make_provider(models=full_catalog),
            "anthropic-haiku": _make_provider(models=full_catalog),
        }
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }

        result = await resolve_model_role(["fast"], roles, providers)

        assert result == []


# ---------------------------------------------------------------------------
# MatrixModelRoleResolver.resolve() must forward its own coordinator to
# resolve_model_role(). The constructor accepts and stores `coordinator`
# (see resolver_class.py's ``self._coordinator = coordinator``), but the
# resolve() method previously never passed it on to resolve_model_role(),
# leaving the bare-type-vs-multi-instance fallback (see
# TestBareTypeFallbackAgainstMultiInstanceProviders above) permanently dead
# for the *only* call path every real consumer (tool-delegate,
# hooks-session-naming, tool-recipes, tool-skills) actually uses. This is a
# regression test for that gap, not for find_provider_by_type/
# resolve_model_role themselves (already covered above).
# ---------------------------------------------------------------------------


class TestMatrixModelRoleResolverForwardsCoordinator:
    @pytest.mark.asyncio
    async def test_resolve_forwards_coordinator_for_bare_type_fallback(self) -> None:
        """A single anthropic instance mounted with an explicit `id:` (e.g. a
        user's settings.yaml sets `id: anthropic-opus`) is keyed
        'anthropic-opus' in coordinator.providers, not the bare module type
        'anthropic' a matrix candidate names. Resolution must still succeed
        via the coordinator config fallback -- but only if resolve() actually
        forwards the coordinator it was constructed with.
        """
        anthropic_opus = _make_provider(
            models=["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
        )
        providers = {"anthropic-opus": anthropic_opus}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        coordinator = _make_coordinator_with_provider_specs(
            [{"module": "provider-anthropic", "id": "anthropic-opus", "config": {}}]
        )

        resolver = MatrixModelRoleResolver(
            matrix_roles=roles,
            providers=providers,
            matrix_name="anthropic",
            coordinator=coordinator,
        )

        result = await resolver.resolve("fast")

        assert len(result) == 1, (
            "resolver.resolve('fast') must resolve via the coordinator "
            "fallback exactly like resolve_model_role(coordinator=...) does "
            "directly -- got: %r. If this is empty, resolve() is not "
            "forwarding self._coordinator to resolve_model_role()." % (result,)
        )
        # This is the crux of the still-unfixed downstream defect: the
        # returned provider must be "anthropic-opus" (the actual mounted
        # key), not the bare "anthropic" matrix type -- otherwise every
        # consumer's own exact/prefix-based provider lookup (loop-streaming,
        # hooks-session-naming) can never re-match it.
        assert result[0].provider == "anthropic-opus"
        assert result[0].model == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_resolve_without_coordinator_still_returns_empty(self) -> None:
        """Backward compatibility: a resolver built without a coordinator
        (e.g. in a test double) must still return [] rather than raising,
        for a bare-type candidate with no exact provider key match."""
        providers = {"anthropic-opus": _make_provider(models=["claude-haiku-4-5"])}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        resolver = MatrixModelRoleResolver(
            matrix_roles=roles,
            providers=providers,
            matrix_name="anthropic",
        )

        result = await resolver.resolve("fast")

        assert result == []


# ---------------------------------------------------------------------------
# End-to-end regression: the resolved "provider" identifier must be usable
# by a real consumer's own match loop, not just non-empty. Extends the
# TestBareTypeFallbackAgainstMultiInstanceProviders / ForwardsCoordinator
# coverage above (which only asserted resolution *succeeded*) with the
# actual downstream re-match every consumer performs -- reproducing
# amplifier-module-loop-streaming's _via_role_resolver() match loop
# verbatim (see repro_routing_defect.py Section D for the full harness).
# ---------------------------------------------------------------------------


def _consumer_match(pref_provider: str, providers: dict) -> tuple[str, Any] | None:
    """Verbatim consumer-side match loop.

    Copied from amplifier-module-loop-streaming's
    ``StreamingOrchestrator._resolve_goal_model._via_role_resolver()``
    (``amplifier_module_loop_streaming/__init__.py`` ~line 1500). Every
    ``ProviderPreference.provider`` this resolver produces must survive this
    exact re-match against the same ``providers`` dict it was resolved
    against, or the resolution is a phantom success: it reports a candidate
    but no consumer can ever act on it.
    """
    for name, provider in providers.items():
        if pref_provider in (
            name,
            name.replace("provider-", ""),
            f"provider-{pref_provider}",
        ):
            return (name, provider)
    return None


class TestResolvedProviderIsConsumerMatchable:
    """Regression coverage for the gap 903305d alone did not close: a
    resolved candidate whose "provider" a real consumer can't re-match is
    indistinguishable, from the caller's side, from no resolution at all.
    """

    @pytest.mark.asyncio
    async def test_id_bearing_single_instance_resolves_and_is_matchable(
        self,
    ) -> None:
        """Production scenario: one Anthropic instance, `id: anthropic-opus`
        in settings.yaml, keyed 'anthropic-opus' in coordinator.providers.
        Must both resolve AND be re-matchable by a downstream consumer.
        """
        anthropic_opus = _make_provider(
            models=["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
        )
        providers = {"anthropic-opus": anthropic_opus}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        coordinator = _make_coordinator_with_provider_specs(
            [{"module": "provider-anthropic", "id": "anthropic-opus", "config": {}}]
        )

        result = await resolve_model_role(
            ["fast"], roles, providers, coordinator=coordinator
        )

        assert len(result) == 1
        match = _consumer_match(result[0]["provider"], providers)
        assert match is not None, (
            f"Resolved provider {result[0]['provider']!r} could not be "
            f"re-matched by the consumer's own lookup against "
            f"providers={providers!r} -- this is the exact production "
            "defect (resolution succeeds, but no consumer can act on it)."
        )
        assert match == ("anthropic-opus", anthropic_opus)

    @pytest.mark.asyncio
    async def test_single_instance_no_id_unchanged(self) -> None:
        """No `id:` set -- single instance keyed by its own module type
        (the pre-existing, non-multi-instance case). Must resolve exactly
        as before this fix: matched name equals the bare type because
        that *is* the mount key, so the returned provider is unchanged
        and trivially matchable.
        """
        providers = {"anthropic": _make_provider(models=["claude-haiku-4-5"])}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }

        # No coordinator needed: first loop of find_provider_by_type finds
        # the exact key directly, bypassing the coordinator-spec fallback
        # entirely -- confirms this path is untouched by the fix.
        result = await resolve_model_role(["fast"], roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "anthropic"
        match = _consumer_match(result[0]["provider"], providers)
        assert match is not None
        assert match[0] == "anthropic"

    @pytest.mark.asyncio
    async def test_genuinely_absent_provider_still_returns_empty(self) -> None:
        """No installed provider serves the role at all (not an id-mismatch
        case -- the provider module itself isn't mounted). Must stay a loud,
        honest [] rather than fabricating a match.
        """
        providers = {"provider-openai": _make_provider()}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        coordinator = _make_coordinator_with_provider_specs(
            [{"module": "provider-openai", "id": "openai-main", "config": {}}]
        )

        result = await resolve_model_role(
            ["fast"], roles, providers, coordinator=coordinator
        )

        assert result == []


# ---------------------------------------------------------------------------
# Version-aware sort for glob resolution
# ---------------------------------------------------------------------------


class TestVersionAwareGlobSort:
    """The _resolve_glob sort must handle:

    1. Multi-digit versions: claude-opus-4-10 > claude-opus-4-7
       (lex sort would wrongly pick '-7' because '7' > '1').
    2. Date-stamped snapshots: claude-opus-4-7 > claude-opus-4-20250514
       (lex would correctly pick '-7' too, but strip proves the 20250514
       suffix is a date, not a version).
    3. Shorter aliases over pinned snapshots on ties: gpt-5.4 > gpt-5.4-2026-03-05.
    """

    @pytest.mark.asyncio
    async def test_natural_sort_picks_higher_multi_digit_version(self) -> None:
        """claude-opus-4-10 > claude-opus-4-7 under natural sort."""
        models = ["claude-opus-4-7", "claude-opus-4-10", "claude-opus-4-6"]
        providers = {"anthropic": _make_provider(models=models)}
        roles = {
            "reasoning": {
                "description": "Reasoning",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-opus-*"},
                ],
            },
        }

        result = await resolve_model_role(["reasoning"], roles, providers)

        assert result[0]["model"] == "claude-opus-4-10", (
            "Version-aware sort must pick 4-10 over 4-7 (lex sort picks 4-7)"
        )

    @pytest.mark.asyncio
    async def test_clean_version_beats_snapshot_date(self) -> None:
        """claude-opus-4-7 (clean) > claude-opus-4-20250514 (old 4.0 snapshot).

        Without the date-strip, the sort key would treat 20250514 as a large
        version number and wrongly prefer the old model.
        """
        models = [
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-opus-4-20250514",
            "claude-opus-4-5-20251101",
        ]
        providers = {"anthropic": _make_provider(models=models)}
        roles = {
            "reasoning": {
                "description": "Reasoning",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-opus-*"},
                ],
            },
        }

        result = await resolve_model_role(["reasoning"], roles, providers)

        assert result[0]["model"] == "claude-opus-4-7"

    @pytest.mark.asyncio
    async def test_hyphenated_date_suffix_stripped(self) -> None:
        """gpt-5.4-2026-03-05 (snapshot) and gpt-5.4 (alias) share sort key;
        alias wins as tie-breaker via shorter name preference."""
        models = ["gpt-5.4", "gpt-5.4-2026-03-05"]
        providers = {"openai": _make_provider(models=models)}
        roles = {
            "general": {
                "description": "General",
                "candidates": [
                    {"provider": "openai", "model": "gpt-5.*"},
                ],
            },
        }

        result = await resolve_model_role(["general"], roles, providers)

        assert result[0]["model"] == "gpt-5.4", (
            "gpt-5.4 alias must win over gpt-5.4-2026-03-05 snapshot on ties"
        )

    @pytest.mark.asyncio
    async def test_openai_tier_suffix_glob(self) -> None:
        """gpt-?.?-mini* matches only mini-tier OpenAI models, not base/pro/nano."""
        models = [
            "gpt-5.4",
            "gpt-5.4-pro",
            "gpt-5.4-mini",
            "gpt-5.4-mini-2026-03-17",
            "gpt-5.4-nano",
            "gpt-5-mini",  # no dot — must NOT match gpt-?.?-mini*
        ]
        providers = {"openai": _make_provider(models=models)}
        roles = {
            "fast": {
                "description": "Fast",
                "candidates": [
                    {"provider": "openai", "model": "gpt-?.?-mini*"},
                ],
            },
        }

        result = await resolve_model_role(["fast"], roles, providers)

        assert result[0]["model"] == "gpt-5.4-mini", (
            "gpt-?.?-mini* must pick gpt-5.4-mini (shorter alias, not dated snapshot)"
        )

    @pytest.mark.asyncio
    async def test_gemini_class_scoped_glob(self) -> None:
        """gemini-*-pro-preview matches only Pro-tier, not Flash/Flash-Lite/Image."""
        models = [
            "gemini-3-pro-preview",
            "gemini-3.1-pro-preview",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-3-pro-image-preview",
            "gemini-3.1-pro-preview-customtools",
        ]
        providers = {"gemini": _make_provider(models=models)}
        roles = {
            "general": {
                "description": "General",
                "candidates": [
                    {"provider": "gemini", "model": "gemini-*-pro-preview"},
                ],
            },
        }

        result = await resolve_model_role(["general"], roles, providers)

        assert result[0]["model"] == "gemini-3.1-pro-preview", (
            "gemini-*-pro-preview must pick 3.1 over 3, and not match flash/image/customtools"
        )


# ---------------------------------------------------------------------------
# Exact-name passthrough (nano-banana, *-latest aliases)
# ---------------------------------------------------------------------------


class TestExactNameBypassesListModels:
    """Exact model names (no glob characters) bypass list_models() entirely
    and pass directly to the provider's API. This is how we use:
    - nano-banana-pro-preview (filtered out of gemini list_models)
    - gemini-pro-latest, gemini-flash-latest (server-side aliases)
    """

    @pytest.mark.asyncio
    async def test_exact_name_does_not_call_list_models(self) -> None:
        """nano-banana-pro-preview is NOT a glob; list_models() must not be called."""
        provider = _make_provider(models=["gemini-3-pro-preview"])
        providers = {"gemini": provider}
        roles = {
            "image-gen": {
                "description": "Image generation",
                "candidates": [
                    {"provider": "gemini", "model": "nano-banana-pro-preview"},
                ],
            },
        }

        result = await resolve_model_role(["image-gen"], roles, providers)

        assert result[0]["model"] == "nano-banana-pro-preview"
        # The key assertion: list_models was NOT called, because the model is
        # an exact name, not a glob. This means the API gets the name directly
        # even if list_models would have filtered it out.
        provider.list_models.assert_not_called()


# ---------------------------------------------------------------------------
# preresolved_models — skip list_models() when models are already known
# ---------------------------------------------------------------------------


class TestPreresolvedModels:
    """When a parent session has already fetched model lists, child sessions
    pass those lists via preresolved_models to skip list_models() HTTP calls.
    """

    @pytest.mark.asyncio
    async def test_resolve_glob_uses_preresolved_list(self) -> None:
        """_resolve_glob does not call list_models() when provider_key is in dict."""
        provider = _make_provider(models=["claude-sonnet-4-20250514"])
        preresolved = {"anthropic": ["claude-sonnet-4-20250514", "claude-haiku-3"]}

        result = await _resolve_glob(
            "claude-sonnet-*",
            provider,
            provider_key="anthropic",
            preresolved_models=preresolved,
        )

        assert result == "claude-sonnet-4-20250514"
        provider.list_models.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_glob_populates_dict_on_fetch(self) -> None:
        """_resolve_glob writes the fetched list into preresolved_models."""
        models = ["claude-sonnet-4-20250514", "claude-haiku-3"]
        provider = _make_provider(models=models)
        preresolved: dict[str, list[str]] = {}

        await _resolve_glob(
            "claude-sonnet-*",
            provider,
            provider_key="anthropic",
            preresolved_models=preresolved,
        )

        assert "anthropic" in preresolved
        assert preresolved["anthropic"] == models
        assert provider.list_models.call_count == 1

    @pytest.mark.asyncio
    async def test_resolve_glob_skips_fetch_on_second_call(self) -> None:
        """Once preresolved_models is populated, subsequent calls skip list_models()."""
        models = ["claude-sonnet-4-20250514"]
        provider = _make_provider(models=models)
        preresolved: dict[str, list[str]] = {}

        # First call — fetches and populates
        await _resolve_glob("claude-sonnet-*", provider, "anthropic", preresolved)
        assert provider.list_models.call_count == 1

        # Second call — uses stored list, no HTTP
        await _resolve_glob("claude-sonnet-*", provider, "anthropic", preresolved)
        assert provider.list_models.call_count == 1  # still 1

    @pytest.mark.asyncio
    async def test_resolve_model_role_passes_preresolved_through(self) -> None:
        """resolve_model_role passes preresolved_models to _resolve_glob."""
        models = ["claude-sonnet-4-20250514"]
        provider = _make_provider(models=models)
        providers = {"provider-anthropic": provider}
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},
                ],
            },
        }
        preresolved = {"anthropic": models}

        result = await resolve_model_role(
            ["coding"], roles, providers, preresolved_models=preresolved
        )

        assert result[0]["model"] == "claude-sonnet-4-20250514"
        provider.list_models.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_model_role_without_preresolved_still_works(self) -> None:
        """Omitting preresolved_models preserves original behaviour."""
        models = ["claude-sonnet-4-20250514"]
        provider = _make_provider(models=models)
        providers = {"provider-anthropic": provider}
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},
                ],
            },
        }

        result = await resolve_model_role(["coding"], roles, providers)

        assert result[0]["model"] == "claude-sonnet-4-20250514"
        provider.list_models.assert_called_once()


# ---------------------------------------------------------------------------
# MatrixModelRoleResolver session-lifetime cache -- resolve() must reuse a
# single instance-level preresolved_models dict across calls so a resolver
# constructed once per session (see __init__.py's
# ``coordinator.register_capability("model_role_resolver", _resolver)``) does
# not re-fetch a provider's model list on every resolve() call. Regression
# coverage for the gap where resolve() called resolve_model_role() without
# ever passing preresolved_models, defeating the caching mechanism that
# already existed in resolve_model_role/_resolve_glob (see
# TestPreresolvedModels above, which covers that lower layer directly).
# ---------------------------------------------------------------------------


class TestMatrixModelRoleResolverCachesModelLists:
    @pytest.mark.asyncio
    async def test_second_resolve_reuses_cached_model_list(self) -> None:
        """Two consecutive resolve() calls for the same glob-based role must
        only hit list_models() once -- the load-bearing proof for this fix."""
        provider = _make_provider(
            models=["claude-haiku-4-5-20251001", "claude-haiku-3"]
        )
        providers = {"anthropic": provider}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        resolver = MatrixModelRoleResolver(
            matrix_roles=roles, providers=providers, matrix_name="anthropic"
        )

        first = await resolver.resolve("fast")
        second = await resolver.resolve("fast")

        assert first[0].model == "claude-haiku-4-5-20251001"
        assert second[0].model == "claude-haiku-4-5-20251001"
        assert provider.list_models.await_count == 1

    @pytest.mark.asyncio
    async def test_cached_list_survives_a_later_transient_failure(self) -> None:
        """Once a provider's model list has been fetched and cached, a
        subsequent list_models() failure must NOT demote the caller -- the
        cached list is used and the correct model still resolves. This is the
        actual defect: before this fix, resolve() never populated a durable
        cache, so every call re-hit list_models(), and a transient failure on
        any call silently returned no candidates (caller falls back to a
        different model)."""
        provider = _make_provider(
            models=["claude-haiku-4-5-20251001", "claude-haiku-3"]
        )
        providers = {"anthropic": provider}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        resolver = MatrixModelRoleResolver(
            matrix_roles=roles, providers=providers, matrix_name="anthropic"
        )

        first = await resolver.resolve("fast")
        assert first[0].model == "claude-haiku-4-5-20251001"

        # Simulate a transient network failure on any further list_models() call.
        provider.list_models.side_effect = RuntimeError("boom")

        second = await resolver.resolve("fast")

        assert len(second) == 1, (
            "second resolve() must still return the cached candidate rather "
            "than silently falling back to no candidates"
        )
        assert second[0].model == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_single_resolve_on_fresh_instance_still_resolves(self) -> None:
        """Regression guard: the empty-cache path (a single resolve() call)
        is unchanged -- it still fetches and resolves correctly."""
        provider = _make_provider(models=["claude-haiku-4-5-20251001"])
        providers = {"anthropic": provider}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
        }
        resolver = MatrixModelRoleResolver(
            matrix_roles=roles, providers=providers, matrix_name="anthropic"
        )

        result = await resolver.resolve("fast")

        assert result[0].model == "claude-haiku-4-5-20251001"
        provider.list_models.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_two_different_roles_sharing_a_provider_share_the_cache(
        self,
    ) -> None:
        """Two different roles that both glob-match against the same provider
        must share the one cached model list -- list_models() is still only
        awaited once across both role resolutions."""
        provider = _make_provider(
            models=["claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"]
        )
        providers = {"anthropic": provider}
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-haiku-*"},
                ],
            },
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},
                ],
            },
        }
        resolver = MatrixModelRoleResolver(
            matrix_roles=roles, providers=providers, matrix_name="anthropic"
        )

        fast_result = await resolver.resolve("fast")
        coding_result = await resolver.resolve("coding")

        assert fast_result[0].model == "claude-haiku-4-5-20251001"
        assert coding_result[0].model == "claude-sonnet-4-20250514"
        assert provider.list_models.await_count == 1


# ---------------------------------------------------------------------------
# MatrixModelRoleResolver.known_roles -- optional part of the
# model_role_resolver contract. Consumers (tool-delegate) turn this into a
# JSON-Schema enum, so order and immutability are load-bearing.
# ---------------------------------------------------------------------------


class TestKnownRoles:
    @staticmethod
    def _make(roles: dict) -> MatrixModelRoleResolver:
        return MatrixModelRoleResolver(
            matrix_roles=roles,
            providers={},
            matrix_name="balanced",
        )

    def test_exposes_matrix_role_names(self) -> None:
        resolver = self._make(
            {
                "general": {"candidates": []},
                "fast": {"candidates": []},
                "coding": {"candidates": []},
            }
        )
        assert set(resolver.known_roles) == {"general", "fast", "coding"}

    def test_preserves_declaration_order_not_sorted(self) -> None:
        """Matrix order is curated and is what hooks-routing injects into
        session context. Alphabetising here would desync the two surfaces."""
        resolver = self._make(
            {
                "general": {"candidates": []},
                "fast": {"candidates": []},
                "coding": {"candidates": []},
                "ui-coding": {"candidates": []},
            }
        )
        assert resolver.known_roles == ("general", "fast", "coding", "ui-coding")
        assert resolver.known_roles != tuple(sorted(resolver.known_roles))

    def test_reflects_composed_matrix_including_overrides(self) -> None:
        """mount() passes the *effective* matrix (base + config overrides), so a
        role added by an override must appear in known_roles."""
        resolver = self._make(
            {
                "general": {"candidates": []},
                "house-special": {"candidates": []},
            }
        )
        assert "house-special" in resolver.known_roles

    def test_is_a_tuple_snapshot_not_a_live_view(self) -> None:
        roles = {"general": {"candidates": []}}
        resolver = self._make(roles)
        roles["injected-later"] = {"candidates": []}
        assert isinstance(resolver.known_roles, tuple)
        assert resolver.known_roles == ("general",)

    def test_empty_matrix_yields_empty_tuple(self) -> None:
        assert self._make({}).known_roles == ()


# ---------------------------------------------------------------------------
# Model-intent instance selection.
#
# Regression for the production defect: a multi-instance Anthropic setup where
# every instance carries the knobs tuned for ITS OWN tier. `fast` asks for
# `provider: anthropic, model: claude-haiku-*`; the bare-type fallback picked
# the lowest-priority-NUMBER instance (opus, priority 1), and
# amplifier_foundation.spawn_utils._apply_single_override then cloned that
# instance's ENTIRE config while overriding only `default_model` -- mounting
# haiku with opus's `reasoning_effort: xhigh` and `fallback_on_overload: true`
# and producing the two `[PROVIDER]` warnings, while the purpose-built haiku
# instance sat unused.
#
# The provider KEY returned here is the thing whose config gets cloned, so
# these assertions are on the key, not merely on the resolved model name.
# ---------------------------------------------------------------------------


# Mirrors the reported settings.yaml: opus is priority 1 (so it wins any
# priority-only tie-break) and carries knobs haiku does not honour.
_TIERED_ANTHROPIC_SPECS = [
    {
        "module": "provider-anthropic",
        "id": "opus",
        "config": {
            "priority": 1,
            "default_model": "claude-opus-5",
            "reasoning_effort": "xhigh",
            "fallback_on_overload": "true",
            "enable_1m_context": "true",
        },
    },
    {
        "module": "provider-anthropic",
        "id": "opus-4.8",
        "config": {
            "priority": 4,
            "default_model": "claude-opus-4-8",
            "reasoning_effort": "xhigh",
            "fallback_on_overload": "true",
        },
    },
    {
        "module": "provider-anthropic",
        "id": "sonnet",
        "config": {
            "priority": 5,
            "default_model": "claude-sonnet-5",
            "reasoning_effort": "high",
        },
    },
    {
        "module": "provider-anthropic",
        "id": "haiku",
        "config": {
            "priority": 12,
            "default_model": "claude-haiku-4-5",
            "reasoning_effort": "high",
        },
    },
]


def _tiered_providers() -> dict[str, Any]:
    catalog = [
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
    ]
    return {
        spec["id"]: _make_provider(models=catalog) for spec in _TIERED_ANTHROPIC_SPECS
    }


class TestModelIntentInstanceSelection:
    def test_haiku_pattern_picks_haiku_instance_not_priority_1_opus(self) -> None:
        """THE defect. Priority alone hands `claude-haiku-*` to the opus
        instance, whose config is then cloned wholesale onto a haiku mount."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)

        result = find_provider_by_type(
            providers, "anthropic", coordinator, model_pattern="claude-haiku-*"
        )

        assert result is not None
        assert result[0] == "haiku", (
            "A candidate asking for claude-haiku-* must resolve to the instance "
            "configured FOR haiku, not to whichever instance holds priority 1 "
            "(opus) -- spawn_utils clones the WHOLE config of the instance "
            "returned here, so picking opus mounts haiku with xhigh + "
            "fallback_on_overload"
        )

    def test_sonnet_pattern_picks_sonnet_instance(self) -> None:
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)

        result = find_provider_by_type(
            providers, "anthropic", coordinator, model_pattern="claude-sonnet-*"
        )

        assert result is not None
        assert result[0] == "sonnet"

    def test_priority_still_breaks_ties_among_model_matches(self) -> None:
        """Two instances both serve claude-opus-*; priority decides between
        them, exactly as before."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)

        result = find_provider_by_type(
            providers, "anthropic", coordinator, model_pattern="claude-opus-*"
        )

        assert result is not None
        assert result[0] == "opus", "priority 1 beats priority 4 among opus matches"

    def test_exact_dated_pattern_matches_alias_instance(self) -> None:
        """A candidate pinned to a dated snapshot still selects the instance
        whose default_model is the clean alias of the same model."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)

        result = find_provider_by_type(
            providers,
            "anthropic",
            coordinator,
            model_pattern="claude-haiku-4-5-20251001",
        )

        assert result is not None
        assert result[0] == "haiku"

    def test_unmatched_pattern_falls_back_to_priority(self) -> None:
        """No instance declares a matching default_model -> unchanged
        priority-only behaviour, never an empty result."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)

        result = find_provider_by_type(
            providers, "anthropic", coordinator, model_pattern="claude-fable-*"
        )

        assert result is not None
        assert result[0] == "opus", "falls back to the priority-1 default instance"

    def test_omitted_pattern_preserves_priority_only_behaviour(self) -> None:
        """Backward compatibility: callers that pass no pattern get exactly
        what they got before this feature existed."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)

        result = find_provider_by_type(providers, "anthropic", coordinator)

        assert result is not None
        assert result[0] == "opus"

    def test_instances_without_default_model_use_priority(self) -> None:
        """Specs that declare no default_model express no model intent, so
        they can only ever be selected by priority (the pre-existing
        multi-instance fixture shape)."""
        providers = {
            "anthropic-sonnet": _make_provider(),
            "anthropic-opus": _make_provider(),
            "anthropic-haiku": _make_provider(),
        }
        coordinator = _make_coordinator_with_provider_specs(
            _ANTHROPIC_MULTI_INSTANCE_SPECS
        )

        result = find_provider_by_type(
            providers, "anthropic", coordinator, model_pattern="claude-haiku-*"
        )

        assert result is not None
        assert result[0] == "anthropic-sonnet"

    def test_exact_key_match_is_unaffected_by_model_pattern(self) -> None:
        """The single-instance path (a provider keyed by the bare type) never
        reaches the fallback, so the pattern must not perturb it."""
        anthropic = _make_provider()
        providers = {"anthropic": anthropic}

        result = find_provider_by_type(
            providers, "anthropic", None, model_pattern="claude-haiku-*"
        )

        assert result == ("anthropic", anthropic)

    @pytest.mark.asyncio
    async def test_resolve_model_role_fast_returns_haiku_instance_key(self) -> None:
        """End-to-end through resolve_model_role: the returned `provider` key
        is what tool-delegate/spawn_utils resolves the child mount against."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)
        roles = {
            "fast": {
                "description": "Fast tasks",
                "candidates": [{"provider": "anthropic", "model": "claude-haiku-*"}],
            },
        }

        result = await resolve_model_role(
            ["fast"], roles, providers, coordinator=coordinator
        )

        assert len(result) == 1
        assert result[0]["provider"] == "haiku"
        assert result[0]["model"] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_resolve_model_role_reasoning_still_returns_opus(self) -> None:
        """The opus-tier roles must be untouched by this change."""
        providers = _tiered_providers()
        coordinator = _make_coordinator_with_provider_specs(_TIERED_ANTHROPIC_SPECS)
        roles = {
            "reasoning": {
                "description": "Deep reasoning",
                "candidates": [
                    {
                        "provider": "anthropic",
                        "model": "claude-opus-*",
                        "config": {"reasoning_effort": "high"},
                    }
                ],
            },
        }

        result = await resolve_model_role(
            ["reasoning"], roles, providers, coordinator=coordinator
        )

        assert len(result) == 1
        assert result[0]["provider"] == "opus"
        assert result[0]["model"] == "claude-opus-5"
        assert result[0]["config"] == {"reasoning_effort": "high"}
