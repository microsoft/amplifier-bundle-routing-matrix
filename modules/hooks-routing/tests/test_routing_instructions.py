"""Validation tests for context/routing-instructions.md.

Verifies the routing instructions file points agents at the live,
per-turn-injected role list (rather than a fixed static table), and still
contains agent author examples, delegation examples, and a reference to
role-definitions.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Walk up from tests/ -> hooks-routing/ -> modules/ -> bundle root -> context/
BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INSTRUCTIONS_PATH = BUNDLE_ROOT / "context" / "routing-instructions.md"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def instructions_content() -> str:
    """Load the routing-instructions.md content once for all tests."""
    assert INSTRUCTIONS_PATH.exists(), (
        f"routing-instructions.md not found at {INSTRUCTIONS_PATH}"
    )
    return INSTRUCTIONS_PATH.read_text()


# ---------------------------------------------------------------------------
# Tests: File exists and has title
# ---------------------------------------------------------------------------


class TestFileStructure:
    """Basic file structure checks."""

    def test_file_exists(self) -> None:
        assert INSTRUCTIONS_PATH.exists()

    def test_has_model_routing_title(self, instructions_content: str) -> None:
        assert instructions_content.startswith("# Model Routing")


# ---------------------------------------------------------------------------
# Tests: Available Roles table with all 13 roles
# ---------------------------------------------------------------------------


class TestAvailableRolesSection:
    """The file must point agents at the live, per-turn-injected role list
    rather than a fixed static table (role sets differ per routing matrix)."""

    def test_has_available_roles_heading(self, instructions_content: str) -> None:
        assert "## Available Roles" in instructions_content

    def test_no_stale_role_count_in_heading(self, instructions_content: str) -> None:
        """The heading must not claim a fixed role count -- the live matrix decides."""
        assert "## Available Roles (13)" not in instructions_content

    def _available_roles_section(self, instructions_content: str) -> str:
        start = instructions_content.index("## Available Roles")
        try:
            next_section = instructions_content.index("\n## ", start + 1)
        except ValueError:
            next_section = len(instructions_content)
        return instructions_content[start:next_section]

    def test_no_static_role_table(self, instructions_content: str) -> None:
        """The static per-role table rows must be gone -- replaced by a pointer paragraph."""
        section = self._available_roles_section(instructions_content)
        role_rows = [line for line in section.split("\n") if line.startswith("| `")]
        assert role_rows == [], f"Expected no static role rows, found {role_rows}"

    def test_points_to_live_injection(self, instructions_content: str) -> None:
        """The section must direct agents to the live per-turn routing injection."""
        section = self._available_roles_section(instructions_content)
        assert "injected into your context every turn" in section
        assert "Active routing matrix" in section
        assert "Available model roles" in section


# ---------------------------------------------------------------------------
# Tests: For Agent Authors section
# ---------------------------------------------------------------------------


class TestForAgentAuthors:
    """The file must have a 'For Agent Authors' section with frontmatter examples."""

    def test_has_agent_authors_heading(self, instructions_content: str) -> None:
        assert "## For Agent Authors" in instructions_content

    def test_has_single_role_example(self, instructions_content: str) -> None:
        """Shows a single model_role example."""
        assert "model_role: coding" in instructions_content

    def test_has_fallback_chain_example(self, instructions_content: str) -> None:
        """Shows a fallback chain example."""
        assert "model_role: [ui-coding, coding, general]" in instructions_content

    def test_has_utility_agent_example(self, instructions_content: str) -> None:
        """Shows a fast/utility agent example."""
        assert "model_role: fast" in instructions_content

    def test_has_yaml_code_block(self, instructions_content: str) -> None:
        """The section should contain a yaml code block."""
        start = instructions_content.index("## For Agent Authors")
        try:
            next_section = instructions_content.index("\n## ", start + 1)
        except ValueError:
            next_section = len(instructions_content)
        section = instructions_content[start:next_section]
        assert "```yaml" in section


# ---------------------------------------------------------------------------
# Tests: For Delegating Agents section
# ---------------------------------------------------------------------------


class TestForDelegatingAgents:
    """The file must have a 'For Delegating Agents' section with override example."""

    def test_has_delegating_agents_heading(self, instructions_content: str) -> None:
        assert "## For Delegating Agents" in instructions_content

    def test_has_model_role_override_example(self, instructions_content: str) -> None:
        """Shows model_role override in a delegation JSON example."""
        start = instructions_content.index("## For Delegating Agents")
        section = instructions_content[start:]
        assert '"model_role"' in section or "model_role" in section

    def test_has_json_code_block(self, instructions_content: str) -> None:
        """The section should contain a json code block."""
        start = instructions_content.index("## For Delegating Agents")
        section = instructions_content[start:]
        assert "```json" in section

    def test_has_vision_role_in_example(self, instructions_content: str) -> None:
        """The delegation example should use the 'vision' role (not old 'coding-image')."""
        start = instructions_content.index("## For Delegating Agents")
        section = instructions_content[start:]
        assert '"vision"' in section


# ---------------------------------------------------------------------------
# Tests: References role-definitions context file
# ---------------------------------------------------------------------------


class TestReferencesRoleDefinitions:
    """The file must reference role-definitions for detailed descriptions."""

    def test_references_role_definitions(self, instructions_content: str) -> None:
        assert "role-definitions" in instructions_content

    def test_no_stale_role_references(self, instructions_content: str) -> None:
        """Should not reference old removed roles."""
        # Check that old roles are not in the table
        assert "| `agentic`" not in instructions_content
        assert "| `planning`" not in instructions_content
        assert "| `coding-image`" not in instructions_content
