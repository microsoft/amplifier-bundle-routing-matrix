"""Behavioral integration tests for the built-in openai-chatgpt matrix."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_hooks_routing.matrix_loader import load_matrix
from amplifier_module_hooks_routing.resolver import resolve_model_role

MATRIX_PATH = Path(__file__).parents[3] / "routing" / "openai-chatgpt.yaml"


def _provider_with_models(models: list[str]) -> MagicMock:
    """Build a provider double exposing a real resolver-compatible catalog."""
    provider = MagicMock()
    provider.list_models = AsyncMock(return_value=models)
    return provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "models", "expected_model", "expected_config"),
    [
        pytest.param(
            "coding",
            ["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-mini"],
            "gpt-5.6-terra",
            {"reasoning_effort": "high"},
            id="coding-prefers-terra",
        ),
        pytest.param(
            "coding",
            ["gpt-5.6", "gpt-5.6-mini"],
            "gpt-5.6",
            {"reasoning_effort": "high"},
            id="coding-falls-back-to-base",
        ),
        pytest.param(
            "fast",
            ["gpt-5.6-mini", "gpt-5.6-luna"],
            "gpt-5.6-luna",
            {},
            id="fast-prefers-luna-over-mini",
        ),
    ],
)
async def test_real_openai_chatgpt_matrix_resolves_catalog_in_candidate_order(
    role: str,
    models: list[str],
    expected_model: str,
    expected_config: dict[str, str],
) -> None:
    """The real matrix drives tier preference, fallback, and effort config."""
    matrix = load_matrix(MATRIX_PATH)
    providers = {"openai-chatgpt": _provider_with_models(models)}

    result = await resolve_model_role([role], matrix["roles"], providers)

    assert result == [
        {
            "provider": "openai-chatgpt",
            "model": expected_model,
            "config": expected_config,
        }
    ]
