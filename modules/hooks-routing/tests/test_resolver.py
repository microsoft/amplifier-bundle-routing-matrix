"""Tests for resolver module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifier_module_hooks_routing.resolver import (
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
