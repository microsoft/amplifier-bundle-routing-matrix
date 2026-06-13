"""Shared fixtures for routing hook tests."""

from __future__ import annotations

import sys
import textwrap
import types
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# amplifier_core stub — hooks-routing imports HookResult at runtime inside
# handler functions. amplifier_core is a runtime dep resolved by amplifier's
# module system, not a pyproject.toml dev dep, so it is not installed in the
# local test venv. Provide a minimal stub so handler tests can run standalone.
# ---------------------------------------------------------------------------


def _install_amplifier_core_stub() -> None:
    """Insert a lightweight amplifier_core stub into sys.modules."""
    if "amplifier_core" in sys.modules:
        return  # Real package already available — don't replace it

    class HookResult:  # noqa: D101
        def __init__(self, action: str = "continue", **kwargs: Any) -> None:
            self.action = action
            for k, v in kwargs.items():
                setattr(self, k, v)

    models_mod = types.ModuleType("amplifier_core.models")
    models_mod.HookResult = HookResult  # type: ignore[attr-defined]

    core_mod = types.ModuleType("amplifier_core")
    core_mod.models = models_mod  # type: ignore[attr-defined]

    sys.modules["amplifier_core"] = core_mod
    sys.modules["amplifier_core.models"] = models_mod


_install_amplifier_core_stub()


@pytest.fixture()
def tmp_matrix(tmp_path: Path) -> Path:
    """Create a minimal valid matrix YAML file and return its path."""
    content = textwrap.dedent("""\
        name: test-matrix
        description: "Test matrix for unit tests"
        updated: "2026-01-01"

        roles:
          general:
            description: "General purpose"
            candidates:
              - provider: anthropic
                model: claude-sonnet-4-20250514
          fast:
            description: "Fast tasks"
            candidates:
              - provider: openai
                model: gpt-4o-mini
    """)
    matrix_file = tmp_path / "test.yaml"
    matrix_file.write_text(content)
    return matrix_file


@pytest.fixture()
def sample_roles() -> dict[str, Any]:
    """Return a sample roles dict (as returned by load_matrix)."""
    return {
        "general": {
            "description": "General purpose",
            "candidates": [
                {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            ],
        },
        "fast": {
            "description": "Fast tasks",
            "candidates": [
                {"provider": "openai", "model": "gpt-4o-mini"},
            ],
        },
        "coding": {
            "description": "Code generation",
            "candidates": [
                {"provider": "anthropic", "model": "claude-sonnet-*"},
                {"provider": "openai", "model": "gpt-4o"},
            ],
        },
    }
