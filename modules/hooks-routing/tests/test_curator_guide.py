"""Validation tests for docs/MATRIX_CURATOR_GUIDE.md.

Verifies the curator guide contains:
- Updated Required Roles section with all 13 role names
- Complete Role Taxonomy table with all 13 roles
- Sourcing Methodology section (Artificial Analysis, StrongDM mapping, Curated Selection)
- Curation Principles section (Pin Model Names, Provider-Specific Naming, Model Blacklist,
  Required Roles, balanced.yaml reference)
- Deriving Per-Provider Matrices section (5-step process)
- When to Refresh section (triggers and 6-step process)
- Expanded 10-item checklist
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Walk up from tests/ -> hooks-routing/ -> modules/ -> bundle root -> docs/
BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GUIDE_PATH = BUNDLE_ROOT / "docs" / "MATRIX_CURATOR_GUIDE.md"

# All 13 roles
ALL_ROLES = [
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
]

# The 5 role categories
ROLE_CATEGORIES = [
    "Foundation",
    "Coding",
    "Cognitive",
    "Capability",
    "Operational",
]

# Blacklisted models
BLACKLISTED_MODELS = [
    "gpt-4.1",
    "claude-opus-4.6-fast",
    "claude-opus-4-6-fast",
]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def guide_content() -> str:
    """Load the MATRIX_CURATOR_GUIDE.md content once for all tests."""
    assert GUIDE_PATH.exists(), f"MATRIX_CURATOR_GUIDE.md not found at {GUIDE_PATH}"
    return GUIDE_PATH.read_text()


def _extract_section(content: str, heading: str) -> str:
    """Extract content between a heading and the next same-level or higher heading."""
    # Determine heading level
    level = 0
    for ch in heading:
        if ch == "#":
            level += 1
        else:
            break

    try:
        start = content.index(heading)
    except ValueError:
        msg = f"Heading '{heading}' not found in guide"
        raise ValueError(msg) from None
    # Find the next heading at the same or higher level
    search_from = start + len(heading)
    end = len(content)
    for i, line in enumerate(content[search_from:].split("\n")):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            line_level = 0
            for ch in stripped:
                if ch == "#":
                    line_level += 1
                else:
                    break
            if line_level <= level:
                # Sum byte-lengths of preceding lines + their newline characters
                # to convert the line index back to a character offset
                end = search_from + sum(
                    len(part) + 1 for part in content[search_from:].split("\n")[:i]
                )
                break

    return content[start:end]


# ---------------------------------------------------------------------------
# Tests: Required Roles Section Updated
# ---------------------------------------------------------------------------


class TestRequiredRolesUpdated:
    """The Required Roles section must list all 13 role names."""

    def test_required_roles_section_exists(self, guide_content: str) -> None:
        assert "## Required Roles" in guide_content

    def test_no_stale_role_list(self, guide_content: str) -> None:
        """Should NOT contain the old text listing only 5 optional roles."""
        assert (
            "(`coding`, `coding-image`, `planning`, `research`, `agentic`)"
            not in guide_content
        ), "Old role list still present — should be updated to 13 roles"

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_required_roles_mentions_role(self, guide_content: str, role: str) -> None:
        """Each of the 13 roles should be mentioned in the Required Roles section."""
        section = _extract_section(guide_content, "## Required Roles")
        assert f"`{role}`" in section, (
            f"Role '{role}' not mentioned in Required Roles section"
        )


# ---------------------------------------------------------------------------
# Tests: Complete Role Taxonomy Table
# ---------------------------------------------------------------------------


class TestRoleTaxonomyTable:
    """Must have a Complete Role Taxonomy table with all 13 roles."""

    def test_taxonomy_heading_exists(self, guide_content: str) -> None:
        assert "## Complete Role Taxonomy (13 Roles)" in guide_content

    def test_references_role_definitions(self, guide_content: str) -> None:
        """Should reference context/role-definitions.md."""
        section = _extract_section(
            guide_content, "## Complete Role Taxonomy (13 Roles)"
        )
        assert "role-definitions.md" in section

    def test_table_has_required_columns(self, guide_content: str) -> None:
        """Table must have columns: #, Role, Category, Model Tier, Reasoning, Description."""
        section = _extract_section(
            guide_content, "## Complete Role Taxonomy (13 Roles)"
        )
        # Check header row has all required columns
        for col in ["#", "Role", "Category", "Model Tier", "Reasoning", "Description"]:
            assert col in section, f"Table missing column: {col}"

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_table_contains_role(self, guide_content: str, role: str) -> None:
        """Each of the 13 roles must appear in the taxonomy table."""
        section = _extract_section(
            guide_content, "## Complete Role Taxonomy (13 Roles)"
        )
        assert f"`{role}`" in section, f"Role '{role}' not found in taxonomy table"

    def test_table_has_13_role_rows(self, guide_content: str) -> None:
        """The taxonomy table should have exactly 13 data rows."""
        section = _extract_section(
            guide_content, "## Complete Role Taxonomy (13 Roles)"
        )
        # Count rows containing backtick-quoted role names (data rows)
        role_rows = [
            line
            for line in section.split("\n")
            if line.strip().startswith("|")
            and "`" in line
            and "---" not in line
            and "Role" not in line  # skip header
        ]
        assert len(role_rows) == 13, (
            f"Expected 13 role rows in taxonomy table, found {len(role_rows)}"
        )

    @pytest.mark.parametrize("category", ROLE_CATEGORIES)
    def test_table_has_category(self, guide_content: str, category: str) -> None:
        """Each role category should appear in the table."""
        section = _extract_section(
            guide_content, "## Complete Role Taxonomy (13 Roles)"
        )
        assert category in section, f"Category '{category}' not in taxonomy table"


# ---------------------------------------------------------------------------
# Tests: Sourcing Methodology
# ---------------------------------------------------------------------------


class TestSourcingMethodology:
    """Must have a Sourcing Methodology section with 3 subsections."""

    def test_sourcing_methodology_heading(self, guide_content: str) -> None:
        assert "## Sourcing Methodology" in guide_content

    def test_artificial_analysis_subsection(self, guide_content: str) -> None:
        assert "### Artificial Analysis Benchmarks" in guide_content

    def test_strongdm_weather_report_subsection(self, guide_content: str) -> None:
        assert "### StrongDM Weather Report Alignment" in guide_content

    def test_weather_report_mapping_table(self, guide_content: str) -> None:
        """Must have a mapping table with 14 Weather Report categories."""
        section = _extract_section(
            guide_content, "### StrongDM Weather Report Alignment"
        )
        # The table should have Weather Report Category and Our Role columns
        assert "Weather Report Category" in section
        assert "Our Role" in section

    def test_weather_report_has_14_categories(self, guide_content: str) -> None:
        """The mapping table should have 14 data rows."""
        section = _extract_section(
            guide_content, "### StrongDM Weather Report Alignment"
        )
        # Count table data rows (skip header and separator)
        table_rows = [
            line
            for line in section.split("\n")
            if line.strip().startswith("|")
            and "---" not in line
            and "Weather Report" not in line
            and line.strip() != "|"
        ]
        assert len(table_rows) >= 14, (
            f"Expected at least 14 mapping rows, found {len(table_rows)}"
        )

    def test_curated_selection_subsection(self, guide_content: str) -> None:
        assert "### Curated Selection" in guide_content

    def test_curated_selection_has_3_steps(self, guide_content: str) -> None:
        """Curated Selection must describe a 3-step process."""
        section = _extract_section(guide_content, "### Curated Selection")
        for i in range(1, 4):
            assert f"{i}." in section, f"Curated Selection missing step {i}"


# ---------------------------------------------------------------------------
# Tests: Curation Principles
# ---------------------------------------------------------------------------


class TestCurationPrinciples:
    """Must have a Curation Principles section with subsections."""

    def test_curation_principles_heading(self, guide_content: str) -> None:
        assert "## Curation Principles" in guide_content

    def test_pin_model_names_subsection(self, guide_content: str) -> None:
        assert "### Pin Model Names" in guide_content

    def test_pin_model_names_has_good_bad_examples(self, guide_content: str) -> None:
        """Should have good and bad examples for model pinning."""
        section = _extract_section(guide_content, "### Pin Model Names")
        # Should show both good and bad patterns
        assert (
            "Good" in section or "good" in section or "✅" in section or "Do" in section
        )
        assert (
            "Bad" in section
            or "bad" in section
            or "❌" in section
            or "Don't" in section
            or "Avoid" in section
        )

    def test_provider_specific_naming_subsection(self, guide_content: str) -> None:
        assert "### Provider-Specific Naming" in guide_content

    def test_provider_naming_has_table(self, guide_content: str) -> None:
        """Should have a table showing provider format differences."""
        section = _extract_section(guide_content, "### Provider-Specific Naming")
        # Must contain a table with provider differences
        assert "|" in section, "Provider-Specific Naming should contain a table"
        # Must mention anthropic hyphens vs copilot dots
        assert "anthropic" in section.lower()
        assert "copilot" in section.lower() or "github" in section.lower()

    def test_provider_naming_has_critical_warning(self, guide_content: str) -> None:
        """Must have a critical warning about anthropic hyphens vs copilot dots."""
        section = _extract_section(guide_content, "### Provider-Specific Naming")
        # Should warn about the hyphen vs dot distinction using explicit terms
        assert "hyphen" in section.lower(), (
            "Provider-Specific Naming should mention 'hyphen'"
        )
        assert "dot" in section.lower(), "Provider-Specific Naming should mention 'dot'"

    def test_model_blacklist_subsection(self, guide_content: str) -> None:
        assert "### Model Blacklist" in guide_content

    @pytest.mark.parametrize("model", BLACKLISTED_MODELS)
    def test_blacklist_contains_model(self, guide_content: str, model: str) -> None:
        """Each blacklisted model must be listed."""
        section = _extract_section(guide_content, "### Model Blacklist")
        assert model in section, (
            f"Blacklisted model '{model}' not found in Model Blacklist section"
        )

    def test_blacklist_has_reasons(self, guide_content: str) -> None:
        """Blacklisted models should have reasons."""
        section = _extract_section(guide_content, "### Model Blacklist")
        # Should have a table or list with reason column
        assert "Reason" in section or "reason" in section or "Why" in section

    def test_required_roles_subsection(self, guide_content: str) -> None:
        """Curation Principles must have a Required Roles subsection."""
        section = _extract_section(guide_content, "## Curation Principles")
        assert "Required Roles" in section

    def test_balanced_yaml_reference(self, guide_content: str) -> None:
        """Curation Principles must reference balanced.yaml."""
        section = _extract_section(guide_content, "## Curation Principles")
        assert "balanced.yaml" in section


# ---------------------------------------------------------------------------
# Tests: Deriving Per-Provider Matrices
# ---------------------------------------------------------------------------


class TestDerivingPerProviderMatrices:
    """Must have a Deriving Per-Provider Matrices section with 5-step process."""

    def test_deriving_heading(self, guide_content: str) -> None:
        assert "## Deriving Per-Provider Matrices" in guide_content

    def test_has_5_steps(self, guide_content: str) -> None:
        """Should describe a 5-step process."""
        section = _extract_section(guide_content, "## Deriving Per-Provider Matrices")
        for i in range(1, 6):
            assert f"{i}." in section, (
                f"Deriving Per-Provider Matrices missing step {i}"
            )


# ---------------------------------------------------------------------------
# Tests: When to Refresh
# ---------------------------------------------------------------------------


class TestWhenToRefresh:
    """Must have a When to Refresh section with triggers and 6-step process."""

    def test_when_to_refresh_heading(self, guide_content: str) -> None:
        assert "## When to Refresh" in guide_content

    def test_has_triggers(self, guide_content: str) -> None:
        """Should list triggers for when to refresh."""
        section = _extract_section(guide_content, "## When to Refresh")
        # Strip the heading itself so we test body content, not the title
        body = section.split("\n", 1)[1] if "\n" in section else ""
        assert "trigger" in body.lower(), (
            "When to Refresh section body should describe triggers"
        )

    def test_has_6_step_process(self, guide_content: str) -> None:
        """Should describe a 6-step refresh process."""
        section = _extract_section(guide_content, "## When to Refresh")
        for i in range(1, 7):
            assert f"{i}." in section, f"When to Refresh missing step {i}"


# ---------------------------------------------------------------------------
# Tests: Expanded Checklist (10 items)
# ---------------------------------------------------------------------------


class TestExpandedChecklist:
    """The checklist must be expanded to 10 items."""

    def test_checklist_heading_exists(self, guide_content: str) -> None:
        assert "## Checklist for Matrix Updates" in guide_content

    def test_checklist_has_10_items(self, guide_content: str) -> None:
        """Checklist should have exactly 10 checkbox items."""
        section = _extract_section(guide_content, "## Checklist for Matrix Updates")
        checkbox_items = [line for line in section.split("\n") if "- [ ]" in line]
        assert len(checkbox_items) == 10, (
            f"Expected 10 checklist items, found {len(checkbox_items)}"
        )

    def test_checklist_has_blacklist_check(self, guide_content: str) -> None:
        """Checklist must include a blacklisted models check."""
        section = _extract_section(guide_content, "## Checklist for Matrix Updates")
        assert "blacklist" in section.lower(), (
            "Checklist missing blacklisted models check"
        )

    def test_checklist_has_duplicate_check(self, guide_content: str) -> None:
        """Checklist must include a duplicate candidates check."""
        section = _extract_section(guide_content, "## Checklist for Matrix Updates")
        assert "duplicate" in section.lower(), (
            "Checklist missing duplicate candidates check"
        )

    def test_checklist_has_naming_check(self, guide_content: str) -> None:
        """Checklist must include provider-specific naming check."""
        section = _extract_section(guide_content, "## Checklist for Matrix Updates")
        assert "naming" in section.lower(), (
            "Checklist missing provider-specific naming check"
        )

    def test_checklist_has_test_command(self, guide_content: str) -> None:
        """Checklist must include a test command."""
        section = _extract_section(guide_content, "## Checklist for Matrix Updates")
        assert "test" in section.lower() or "pytest" in section.lower(), (
            "Checklist missing test command"
        )

    def test_checklist_retains_original_items(self, guide_content: str) -> None:
        """Original checklist items should still be present."""
        section = _extract_section(guide_content, "## Checklist for Matrix Updates")
        assert "general" in section and "fast" in section
        assert "updated" in section.lower()
        assert "provider" in section.lower()
        assert (
            "candidates" in section.lower()
            or "preference" in section.lower()
            or "ordered" in section.lower()
        )
        assert "config" in section.lower()


# ---------------------------------------------------------------------------
# Tests: Section ordering
# ---------------------------------------------------------------------------


class TestSectionOrdering:
    """New sections must appear BEFORE the checklist."""

    def test_taxonomy_before_checklist(self, guide_content: str) -> None:
        taxonomy_pos = guide_content.index("## Complete Role Taxonomy")
        checklist_pos = guide_content.index("## Checklist for Matrix Updates")
        assert taxonomy_pos < checklist_pos, (
            f"Taxonomy ({taxonomy_pos}) should appear before Checklist ({checklist_pos})"
        )

    def test_sourcing_before_checklist(self, guide_content: str) -> None:
        sourcing_pos = guide_content.index("## Sourcing Methodology")
        checklist_pos = guide_content.index("## Checklist for Matrix Updates")
        assert sourcing_pos < checklist_pos, (
            f"Sourcing ({sourcing_pos}) should appear before Checklist ({checklist_pos})"
        )

    def test_curation_before_checklist(self, guide_content: str) -> None:
        curation_pos = guide_content.index("## Curation Principles")
        checklist_pos = guide_content.index("## Checklist for Matrix Updates")
        assert curation_pos < checklist_pos, (
            f"Curation ({curation_pos}) should appear before Checklist ({checklist_pos})"
        )

    def test_deriving_before_checklist(self, guide_content: str) -> None:
        deriving_pos = guide_content.index("## Deriving Per-Provider Matrices")
        checklist_pos = guide_content.index("## Checklist for Matrix Updates")
        assert deriving_pos < checklist_pos, (
            f"Deriving ({deriving_pos}) should appear before Checklist ({checklist_pos})"
        )

    def test_refresh_before_checklist(self, guide_content: str) -> None:
        refresh_pos = guide_content.index("## When to Refresh")
        checklist_pos = guide_content.index("## Checklist for Matrix Updates")
        assert refresh_pos < checklist_pos, (
            f"Refresh ({refresh_pos}) should appear before Checklist ({checklist_pos})"
        )
