"""Tests for resolver module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_module_hooks_routing.resolver import (
    _resolve_glob,
    find_provider_by_type,
    resolve_model_role,
)


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
        """Role in matrix, provider installed, returns match."""
        providers = {"provider-anthropic": _make_provider()}

        result = await resolve_model_role(["general"], sample_roles, providers)

        assert len(result) == 1
        assert result[0]["provider"] == "anthropic"
        assert result[0]["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_second_role(self, sample_roles: dict) -> None:
        """First role not in matrix, second matches."""
        providers = {"provider-openai": _make_provider()}

        result = await resolve_model_role(
            ["nonexistent", "fast"], sample_roles, providers
        )

        assert len(result) == 1
        assert result[0]["provider"] == "openai"
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
        assert result[0]["provider"] == "openai"
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
        assert result[0]["provider"] == "anthropic"
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
        """'anthropic' matches 'provider-anthropic' key."""
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
        assert result[0]["provider"] == "anthropic"

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
        assert result[0]["provider"] == "openai"
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
        assert result[0]["provider"] == "openai"


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
        assert result[0]["provider"] == "anthropic"
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
