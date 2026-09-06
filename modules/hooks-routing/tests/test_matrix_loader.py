"""Tests for matrix_loader module."""

from __future__ import annotations

from pathlib import Path

import pytest

from amplifier_module_hooks_routing.matrix_loader import (
    compose_matrix,
    load_matrix,
    validate_matrix,
)


# ---------------------------------------------------------------------------
# load_matrix tests
# ---------------------------------------------------------------------------


class TestLoadMatrix:
    def test_load_matrix_basic(self, tmp_matrix: Path) -> None:
        """Loads a valid YAML, checks name/roles parsed."""
        result = load_matrix(tmp_matrix)

        assert result["name"] == "test-matrix"
        assert result["description"] == "Test matrix for unit tests"
        assert result["updated"] == "2026-01-01"
        assert "general" in result["roles"]
        assert "fast" in result["roles"]
        assert result["roles"]["general"]["description"] == "General purpose"
        assert len(result["roles"]["general"]["candidates"]) == 1
        assert result["roles"]["general"]["candidates"][0]["provider"] == "anthropic"

    def test_load_matrix_missing_file_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError when file does not exist."""
        with pytest.raises(FileNotFoundError):
            load_matrix(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# compose_matrix tests
# ---------------------------------------------------------------------------


class TestComposeMatrix:
    def test_compose_full_replacement(self, sample_roles: dict) -> None:
        """Override without 'base' keyword replaces the role entirely."""
        overrides = {
            "coding": {
                "description": "Custom coding",
                "candidates": [
                    {"provider": "ollama", "model": "codellama"},
                ],
            },
        }
        result = compose_matrix(sample_roles, overrides)

        assert result["coding"]["description"] == "Custom coding"
        assert len(result["coding"]["candidates"]) == 1
        assert result["coding"]["candidates"][0]["provider"] == "ollama"

    def test_compose_with_base_prepend(self, sample_roles: dict) -> None:
        """User entry before 'base' prepends to base candidates."""
        overrides = {
            "coding": {
                "description": "Code generation",
                "candidates": [
                    {"provider": "ollama", "model": "codellama"},
                    "base",
                ],
            },
        }
        result = compose_matrix(sample_roles, overrides)

        candidates = result["coding"]["candidates"]
        assert candidates[0]["provider"] == "ollama"
        assert candidates[0]["model"] == "codellama"
        # base candidates follow
        assert candidates[1]["provider"] == "anthropic"
        assert candidates[2]["provider"] == "openai"

    def test_compose_with_base_append(self, sample_roles: dict) -> None:
        """'base' before user entry appends user candidates after base."""
        overrides = {
            "coding": {
                "description": "Code generation",
                "candidates": [
                    "base",
                    {"provider": "ollama", "model": "codellama"},
                ],
            },
        }
        result = compose_matrix(sample_roles, overrides)

        candidates = result["coding"]["candidates"]
        # base candidates first
        assert candidates[0]["provider"] == "anthropic"
        assert candidates[1]["provider"] == "openai"
        # then user
        assert candidates[2]["provider"] == "ollama"

    def test_compose_with_base_sandwich(self, sample_roles: dict) -> None:
        """User + base + user creates a sandwich."""
        overrides = {
            "coding": {
                "description": "Code generation",
                "candidates": [
                    {"provider": "local", "model": "top-pick"},
                    "base",
                    {"provider": "ollama", "model": "fallback"},
                ],
            },
        }
        result = compose_matrix(sample_roles, overrides)

        candidates = result["coding"]["candidates"]
        assert candidates[0] == {"provider": "local", "model": "top-pick"}
        assert candidates[1]["provider"] == "anthropic"  # from base
        assert candidates[2]["provider"] == "openai"  # from base
        assert candidates[3] == {"provider": "ollama", "model": "fallback"}

    def test_compose_multiple_base_raises(self, sample_roles: dict) -> None:
        """Two 'base' keywords in candidates list raises ValueError."""
        overrides = {
            "coding": {
                "description": "Code generation",
                "candidates": [
                    "base",
                    {"provider": "local", "model": "middle"},
                    "base",
                ],
            },
        }
        with pytest.raises(ValueError, match="multiple.*base"):
            compose_matrix(sample_roles, overrides)

    def test_compose_new_role_added(self, sample_roles: dict) -> None:
        """Override adds a role not present in base."""
        overrides = {
            "research": {
                "description": "Deep research",
                "candidates": [
                    {"provider": "openai", "model": "gpt-5-pro"},
                ],
            },
        }
        result = compose_matrix(sample_roles, overrides)

        assert "research" in result
        assert result["research"]["description"] == "Deep research"
        assert len(result["research"]["candidates"]) == 1

    def test_compose_unmentioned_roles_inherited(self, sample_roles: dict) -> None:
        """Roles not mentioned in overrides stay from base unchanged."""
        overrides = {
            "coding": {
                "description": "Custom coding",
                "candidates": [
                    {"provider": "ollama", "model": "codellama"},
                ],
            },
        }
        result = compose_matrix(sample_roles, overrides)

        # general and fast should be inherited unchanged
        assert result["general"] == sample_roles["general"]
        assert result["fast"] == sample_roles["fast"]

    def test_compose_does_not_mutate_inputs(self, sample_roles: dict) -> None:
        """Composition creates a NEW dict without mutating inputs."""
        import copy

        original_base = copy.deepcopy(sample_roles)
        overrides = {
            "coding": {
                "description": "Custom",
                "candidates": [{"provider": "x", "model": "y"}],
            },
        }
        original_overrides = copy.deepcopy(overrides)

        compose_matrix(sample_roles, overrides)

        assert sample_roles == original_base
        assert overrides == original_overrides


# ---------------------------------------------------------------------------
# validate_matrix tests
# ---------------------------------------------------------------------------


class TestValidateMatrix:
    def test_validate_valid_matrix(self, tmp_matrix: Path) -> None:
        """A valid matrix produces no errors."""
        matrix = load_matrix(tmp_matrix)
        errors = validate_matrix(matrix)
        assert errors == []

    def test_validate_missing_general_role(self) -> None:
        """Error if no 'general' role."""
        matrix = {
            "name": "bad",
            "roles": {
                "fast": {
                    "description": "Quick",
                    "candidates": [{"provider": "a", "model": "b"}],
                },
            },
        }
        errors = validate_matrix(matrix)
        assert any("general" in e for e in errors)

    def test_validate_missing_fast_role(self) -> None:
        """Error if no 'fast' role."""
        matrix = {
            "name": "bad",
            "roles": {
                "general": {
                    "description": "General",
                    "candidates": [{"provider": "a", "model": "b"}],
                },
            },
        }
        errors = validate_matrix(matrix)
        assert any("fast" in e for e in errors)

    def test_validate_role_missing_description(self) -> None:
        """Error if a role has no description."""
        matrix = {
            "name": "bad",
            "roles": {
                "general": {
                    "candidates": [{"provider": "a", "model": "b"}],
                },
                "fast": {
                    "description": "Quick",
                    "candidates": [{"provider": "a", "model": "b"}],
                },
            },
        }
        errors = validate_matrix(matrix)
        assert any("description" in e for e in errors)

    def test_validate_role_missing_candidates(self) -> None:
        """Error if a role has no candidates."""
        matrix = {
            "name": "bad",
            "roles": {
                "general": {
                    "description": "General purpose",
                },
                "fast": {
                    "description": "Quick",
                    "candidates": [{"provider": "a", "model": "b"}],
                },
            },
        }
        errors = validate_matrix(matrix)
        assert any("candidates" in e for e in errors)

    def test_validate_base_keyword_in_matrix(self) -> None:
        """Error if 'base' keyword appears in a matrix file's candidates."""
        matrix = {
            "name": "bad",
            "roles": {
                "general": {
                    "description": "General",
                    "candidates": [
                        {"provider": "a", "model": "b"},
                        "base",
                    ],
                },
                "fast": {
                    "description": "Quick",
                    "candidates": [{"provider": "a", "model": "b"}],
                },
            },
        }
        errors = validate_matrix(matrix)
        assert any("base" in e.lower() for e in errors)
