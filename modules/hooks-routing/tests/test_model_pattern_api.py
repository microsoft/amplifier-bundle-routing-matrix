"""Routing consumes the installed Foundation API, not a private sort copy."""

from unittest.mock import AsyncMock, Mock

import pytest

from amplifier_foundation.model_patterns import select_model_pattern
from amplifier_module_hooks_routing.resolver import resolve_model_role, select_glob_model
from amplifier_module_hooks_routing.catalog_audit import audit_matrix_catalogs


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory,expected", [
    (["model-9", "model-10"], "model-10"),
    (["model-10-20260101", "model-10-2026-11-01"], "model-10-2026-11-01"),
    (["Model-10-20261101", "MODEL-10"], "MODEL-10"),
])
async def test_role_and_compatibility_entry_point_use_foundation(inventory, expected):
    provider = Mock(list_models=AsyncMock(return_value=inventory))
    roles = {"general": {"candidates": [{"provider": "fixture", "model": "model-*"}]}}
    result = await resolve_model_role(["general"], roles, {"fixture": provider})
    assert result[0]["model"] == expected
    assert select_glob_model("model-*", inventory) == select_model_pattern("model-*", inventory)


def test_audit_checks_the_same_winner():
    # Only the newest snapshot advertises vision. Selecting the first API
    # entry would produce a false vision failure.
    matrices = {"fixture": {"roles": {"vision": {"candidates": [
        {"provider": "fixture", "model": "model-*"}
    ]}}}}
    catalogs = {"fixture": {"status": "ok", "models": [
        {"id": "model-10-20260101", "capabilities": []},
        {"id": "model-10-20261101", "capabilities": ["vision"]},
    ]}}
    assert audit_matrix_catalogs(matrices, catalogs)["issues"] == []