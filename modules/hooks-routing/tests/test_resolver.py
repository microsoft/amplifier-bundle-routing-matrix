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

    @pytest.mark.asyncio
    async def test_resolve_returns_full_candidate_chain(self) -> None:
        """All resolvable candidates are returned for failover, not just the first."""
        providers = {
            "provider-anthropic": _make_provider(),
            "provider-openai": _make_provider(),
        }
        roles = {
            "general": {
                "description": "General purpose",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "google", "model": "gemini-pro"},  # not installed
                ],
            },
        }

        result = await resolve_model_role(["general"], roles, providers)

        # Should return both installed providers, skip google (not installed)
        assert len(result) == 2
        assert result[0]["provider"] == "anthropic"
        assert result[0]["model"] == "claude-sonnet-4-20250514"
        assert result[1]["provider"] == "openai"
        assert result[1]["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_resolve_chain_preserves_config(self) -> None:
        """Config is preserved for each candidate in the chain."""
        providers = {
            "provider-anthropic": _make_provider(),
            "provider-openai": _make_provider(),
        }
        roles = {
            "reasoning": {
                "description": "Deep reasoning",
                "candidates": [
                    {
                        "provider": "anthropic",
                        "model": "claude-opus-4-6",
                        "config": {"reasoning_effort": "high"},
                    },
                    {
                        "provider": "openai",
                        "model": "gpt-5.4-pro",
                        "config": {"reasoning_effort": "high"},
                    },
                ],
            },
        }

        result = await resolve_model_role(["reasoning"], roles, providers)

        assert len(result) == 2
        assert result[0]["config"] == {"reasoning_effort": "high"}
        assert result[1]["config"] == {"reasoning_effort": "high"}

    @pytest.mark.asyncio
    async def test_resolve_chain_with_partial_glob_failure(self) -> None:
        """Glob failure for one candidate doesn't block others."""
        providers = {
            "provider-anthropic": _make_provider(models=[], raises=True),
            "provider-openai": _make_provider(),
            "provider-google": _make_provider(),
        }
        roles = {
            "coding": {
                "description": "Code gen",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-*"},  # glob fails
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "google", "model": "gemini-pro"},
                ],
            },
        }

        result = await resolve_model_role(["coding"], roles, providers)

        # Anthropic skipped (glob failure), openai + google returned
        assert len(result) == 2
        assert result[0]["provider"] == "openai"
        assert result[1]["provider"] == "google"
