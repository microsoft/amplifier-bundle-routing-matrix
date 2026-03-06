"""Validation tests for real matrix YAML files on disk.

These tests load the actual matrix files from routing/ and verify
structural properties: role coverage, no duplicates, no stale roles.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Walk up from tests/ → hooks-routing/ → modules/ → bundle root → routing/
BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ROUTING_DIR = BUNDLE_ROOT / "routing"

# All 13 roles that must be present in balanced.yaml
ALL_ROLES = frozenset(
    {
        "general",
        "fast",
        "coding",
        "ui-coding",
        "security-audit",
        "reasoning",
        "critique",
        "creative",
        "writing",
        "research",
        "vision",
        "image-gen",
        "critical-ops",
    }
)

# Roles that were removed and must NOT appear
REMOVED_ROLES = frozenset({"agentic", "planning", "coding-image"})

# Required in every matrix
REQUIRED_ROLES = frozenset({"general", "fast"})

# Models that must never appear in any matrix
BLACKLISTED_MODELS = frozenset(
    {"gpt-4.1", "claude-opus-4.6-fast", "claude-opus-4-6-fast"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matrix_ids() -> list[str]:
    """Return matrix filenames for parametrize IDs."""
    return [f.name for f in sorted(ROUTING_DIR.glob("*.yaml"))]


def _load(matrix_file: str) -> dict:
    """Load and parse a matrix YAML file from routing/."""
    return yaml.safe_load((ROUTING_DIR / matrix_file).read_text())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBalancedCompleteness:
    """balanced.yaml is the reference matrix — it must define all 13 roles."""

    def test_balanced_has_all_13_roles(self) -> None:
        balanced = ROUTING_DIR / "balanced.yaml"
        assert balanced.exists(), "balanced.yaml not found"
        data = _load("balanced.yaml")
        actual_roles = set(data["roles"].keys())
        missing = ALL_ROLES - actual_roles
        assert not missing, f"balanced.yaml missing roles: {missing}"

    def test_balanced_has_no_extra_roles(self) -> None:
        balanced = ROUTING_DIR / "balanced.yaml"
        assert balanced.exists(), "balanced.yaml not found"
        data = _load("balanced.yaml")
        actual_roles = set(data["roles"].keys())
        extra = actual_roles - ALL_ROLES
        assert not extra, f"balanced.yaml has unexpected roles: {extra}"


class TestAllMatrices:
    """Tests that apply to every matrix file in routing/."""

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_valid_yaml(self, matrix_file: str) -> None:
        data = _load(matrix_file)
        assert data is not None, f"{matrix_file}: failed to parse YAML"
        assert "roles" in data, f"{matrix_file}: missing 'roles' key"

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_updated_date(self, matrix_file: str) -> None:
        data = _load(matrix_file)
        assert data.get("updated") == "2026-03-06", (
            f"{matrix_file}: updated field is '{data.get('updated')}', expected '2026-03-06'"
        )

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_required_roles_present(self, matrix_file: str) -> None:
        data = _load(matrix_file)
        actual_roles = set(data["roles"].keys())
        missing = REQUIRED_ROLES - actual_roles
        assert not missing, f"{matrix_file} missing required roles: {missing}"

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_no_removed_roles(self, matrix_file: str) -> None:
        data = _load(matrix_file)
        actual_roles = set(data["roles"].keys())
        stale = REMOVED_ROLES & actual_roles
        assert not stale, f"{matrix_file} still has removed roles: {stale}"

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_no_duplicate_candidates(self, matrix_file: str) -> None:
        """No role should have the same provider+model pair listed twice."""
        data = _load(matrix_file)
        for role_name, role_def in data["roles"].items():
            seen = set()
            for candidate in role_def["candidates"]:
                key = (candidate["provider"], candidate["model"])
                assert key not in seen, (
                    f"{matrix_file}/{role_name}: duplicate candidate "
                    f"{candidate['provider']}/{candidate['model']}"
                )
                seen.add(key)

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_every_role_has_description_and_candidates(self, matrix_file: str) -> None:
        data = _load(matrix_file)
        for role_name, role_def in data["roles"].items():
            assert "description" in role_def, (
                f"{matrix_file}/{role_name}: missing description"
            )
            assert "candidates" in role_def, (
                f"{matrix_file}/{role_name}: missing candidates"
            )
            assert len(role_def["candidates"]) > 0, (
                f"{matrix_file}/{role_name}: empty candidates list"
            )

    @pytest.mark.parametrize("matrix_file", _matrix_ids())
    def test_no_blacklisted_models(self, matrix_file: str) -> None:
        """Ensure purged models never sneak back in."""
        data = _load(matrix_file)
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] not in BLACKLISTED_MODELS, (
                    f"{matrix_file}/{role_name}: blacklisted model {candidate['model']}"
                )
