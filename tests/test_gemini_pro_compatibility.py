"""Stock Pro selector compatibility, not provider discovery or model quality.

Synthetic outputs are qualified against provider-gemini DEFAULT_FILTERS at
6669ea5a15affe6ab9ed9b4ef31b36a595b5c282 in isolated integration evidence.
No provider implementation is imported by the routing runtime or this suite.
"""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from amplifier_foundation import model_matches_pattern
from amplifier_module_hooks_routing.resolver import resolve_model_role

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests/fixtures/gemini_pro_default_vectors.json").read_text())
PRO_PATTERNS = [
    "gemini-[3-9]*-pro-preview",
    "gemini-[3-9]*-pro-preview-[0-9][0-9]-[0-9][0-9][0-9][0-9]",
    "gemini-[3-9]*-pro-preview-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]",
    "gemini-[3-9]*-pro-preview-[0-9][0-9]-[0-9][0-9]",
    "gemini-[3-9]*-pro-preview-[0-9][0-9][0-9]",
    "gemini-[3-9]*-pro",
]


def pro_groups():
    groups = []
    for matrix in ("balanced", "quality", "economy", "gemini"):
        data = yaml.safe_load((ROOT / "routing" / (matrix + ".yaml")).read_text())
        for role, definition in data["roles"].items():
            candidates = definition["candidates"]
            for index, candidate in enumerate(candidates):
                if candidate["provider"] == "gemini" and candidate["model"] == PRO_PATTERNS[0]:
                    group = candidates[index:index + len(PRO_PATTERNS)]
                    groups.append(pytest.param(matrix, role, group, id=f"{matrix}-{role}"))
    return groups


GROUPS = pro_groups()


def test_all_42_stock_pro_groups_are_covered():
    assert len(GROUPS) == 42


@pytest.mark.parametrize("matrix,role,group", GROUPS)
def test_order_and_same_config(matrix, role, group):
    assert [c["model"] for c in group] == PRO_PATTERNS
    assert all(c["provider"] == "gemini" for c in group)
    assert all(c["config"] == group[0]["config"] for c in group)


@pytest.mark.asyncio
@pytest.mark.parametrize("matrix,role,group", GROUPS)
@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
async def test_recommended_inventory_resolves_exact_id(matrix, role, group, vector):
    provider = Mock(list_models=AsyncMock(return_value=vector["defaults"]))
    roles = {role: {"candidates": copy.deepcopy(group)}}
    result = await resolve_model_role([role], roles, {"gemini": provider})
    if vector["winner"] is None:
        assert result == []
    else:
        assert result[0]["model"] == vector["winner"]
        assert result[0]["model"] in vector["defaults"]
        assert result[0]["provider"] == "gemini"
        assert result[0]["config"] == group[0]["config"]


@pytest.mark.parametrize("model", [
    "gemini-4-pro-image", "gemini-4-pro-image-preview",
    "gemini-4-pro-preview-tts", "gemini-4-pro-preview-tts-001",
    "gemini-4-pro-preview-01-2027-tts", "gemini-4-pro-preview-01-tts-2027",
    "gemini-4-pro-audio", "gemini-4-pro-preview-image-001",
    "gemini-2.5-pro", "gemini-2.5-pro-preview-01-2027",
    "gemini-4-flash", "gemini-4-flash-lite",
])
def test_patterns_do_not_admit_other_tiers_media_or_below_floor(model):
    assert not any(model_matches_pattern(model, pattern) for pattern in PRO_PATTERNS)