"""Regression guard for the temporary Sonnet 5.5 rollout gate.

The live Anthropic roster contains both Sonnet 5 and Sonnet 5.5. Until live
tool-action and signed-history validation are reviewed, shipped matrices must
continue routing their Anthropic Sonnet candidates to the proven Sonnet 5 ID.
An explicit Sonnet 5.5 candidate remains a valid provider request for further
validation; this gate limits only the shipped default routing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTING_DIR = REPO_ROOT / "routing"
MATRIX_NAMES = ("anthropic", "balanced", "economy", "quality")
SONNET_5 = "claude-sonnet-5"
SONNET_5_5 = "claude-sonnet-5-5"
ANTHROPIC_ROSTER = [SONNET_5, SONNET_5_5]

sys.path.insert(0, str(REPO_ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing.resolver import (  # noqa: E402
    resolve_model_role,
)


def _sonnet_candidates(matrix_name: str) -> list[tuple[str, dict[str, Any]]]:
    """Return Anthropic Sonnet candidates from one shipped matrix."""
    data = yaml.safe_load(
        (ROUTING_DIR / f"{matrix_name}.yaml").read_text(encoding="utf-8")
    )
    return [
        (role, candidate)
        for role, definition in data["roles"].items()
        for candidate in definition["candidates"]
        if candidate.get("provider") == "anthropic"
        and candidate.get("model", "").startswith("claude-sonnet-")
    ]


def _provider() -> MagicMock:
    provider = MagicMock()
    provider.list_models = AsyncMock(return_value=ANTHROPIC_ROSTER)
    return provider


@pytest.mark.parametrize("matrix_name", MATRIX_NAMES)
def test_shipped_sonnet_candidates_are_pinned_to_five(matrix_name: str) -> None:
    """The temporary gate must be explicit, not a glob that selects 5.5."""
    candidates = _sonnet_candidates(matrix_name)
    assert candidates, f"{matrix_name}.yaml has no Anthropic Sonnet candidates"
    assert all(candidate["model"] == SONNET_5 for _, candidate in candidates), (
        f"{matrix_name}.yaml has a Sonnet candidate outside the temporary "
        f"{SONNET_5!r} gate: {candidates}"
    )


@pytest.mark.asyncio
async def test_sonnet_roles_resolve_to_five_when_the_roster_also_has_five_five() -> None:
    """Every shipped Sonnet candidate resolves to 5 against the live roster shape."""
    for matrix_name in MATRIX_NAMES:
        for role, candidate in _sonnet_candidates(matrix_name):
            provider = _provider()
            roles = {
                role: {
                    "description": "Temporary Sonnet rollout-gate regression fixture",
                    "candidates": [candidate],
                }
            }

            resolved = await resolve_model_role([role], roles, {"anthropic": provider})

            assert resolved == [
                {
                    "provider": "anthropic",
                    "model": SONNET_5,
                    "config": candidate.get("config", {}),
                }
            ]
            provider.list_models.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_sonnet_five_five_provider_request_remains_possible() -> None:
    """The temporary default gate does not prevent an explicit 5.5 validation run."""
    provider = _provider()
    roles = {
        "explicit-validation": {
            "description": "Explicit Sonnet 5.5 validation",
            "candidates": [{"provider": "anthropic", "model": SONNET_5_5}],
        }
    }

    resolved = await resolve_model_role(
        ["explicit-validation"], roles, {"anthropic": provider}
    )

    assert resolved == [
        {"provider": "anthropic", "model": SONNET_5_5, "config": {}}
    ]
    provider.list_models.assert_not_called()