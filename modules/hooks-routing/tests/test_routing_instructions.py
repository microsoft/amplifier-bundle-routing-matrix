"""Validation tests for context/routing-instructions.md.

This file renders into the ALWAYS-ON HEAD: `context.include` content is paid for
on every request of every session, whether or not routing is ever used. So these
tests pin two things at once, and the second is the reason the first was
rewritten:

  1. FIDELITY -- every rule, constraint, command and pointer the stock file
     carried must still be here. Compression is only allowed to remove words,
     never instructions.

  2. THE LEAN BUDGET -- the verbose scaffolding the compression removed
     (section headings, fenced example blocks, the restatement sentence) must
     STAY removed. Without this, the file silently drifts back to 1,148 chars
     and the measured saving evaporates with nothing going red.

Provenance: `model_performance-smy5` applied `zc6t`'s measured lean-head patch
(amplifier-foundation main, PR #372, SHA 4384805,
docs/lanes/zc6t-lean-head-ship/patches/context-files/
08-amplifier-bundle-routing-matrix-routing-instructions.md.patch).
Stock 1,148 chars -> lean 735 chars, -413 (-35.98%). Fidelity re-verified at
today's head rather than inherited: 21 atoms, 0 undeclared drops -- see
docs/lanes/smy5-patch-routing-matrix/.

WHAT CHANGED IN THIS TEST FILE, AND WHY: the previous revision asserted on
markdown SCAFFOLDING -- `## Available Roles`, `## For Agent Authors`,
`## For Delegating Agents`, a ```yaml fence and a ```json fence. The lean
rewrite deletes exactly that scaffolding while keeping every instruction, so
those five assertions were inverted into the budget pins below (the scaffolding
must now be ABSENT). Every CONTENT assertion the old file made is preserved;
assertions that sliced the document by heading were rewritten to run against
the whole document, since the headings no longer exist.
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

# Measured on the applied patch. The ceiling is deliberately close to it: this
# file is head-resident, so a few hundred characters of "just one more
# paragraph" is a real, recurring, per-request cost.
MEASURED_LEAN_CHARS = 735
LEAN_CHAR_CEILING = 800
STOCK_CHARS_BEFORE_PATCH = 1148


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def instructions_content() -> str:
    """Load the routing-instructions.md content once for all tests."""
    assert INSTRUCTIONS_PATH.exists(), (
        f"routing-instructions.md not found at {INSTRUCTIONS_PATH}"
    )
    return INSTRUCTIONS_PATH.read_text(encoding="utf-8")


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
# Tests: the live, per-turn-injected role list
# ---------------------------------------------------------------------------


class TestLiveRoleList:
    """The file must point agents at the live, per-turn-injected role list
    rather than a fixed static table (role sets differ per routing matrix)."""

    def test_points_to_live_injection(self, instructions_content: str) -> None:
        """Must direct agents to the live per-turn routing injection."""
        assert "injected every turn" in instructions_content
        assert "Active routing matrix" in instructions_content
        assert "Available model roles" in instructions_content

    def test_live_list_is_declared_authoritative(
        self, instructions_content: str
    ) -> None:
        """The injected list -- not any written-down list -- is authoritative."""
        assert "authoritative" in instructions_content

    def test_warns_role_sets_differ_per_matrix(
        self, instructions_content: str
    ) -> None:
        assert "differ per matrix" in instructions_content
        assert "never rely on a list written down elsewhere" in instructions_content

    def test_no_static_role_table(self, instructions_content: str) -> None:
        """The static per-role table rows must stay gone."""
        role_rows = [
            line
            for line in instructions_content.split("\n")
            if line.startswith("| `")
        ]
        assert role_rows == [], f"Expected no static role rows, found {role_rows}"

    def test_no_stale_role_count(self, instructions_content: str) -> None:
        """Must not claim a fixed role count -- the live matrix decides."""
        assert "Available Roles (13)" not in instructions_content


# ---------------------------------------------------------------------------
# Tests: agent frontmatter forms
# ---------------------------------------------------------------------------


class TestForAgentAuthors:
    """All three `model_role` frontmatter forms, and the chain rule."""

    def test_has_single_role_example(self, instructions_content: str) -> None:
        assert "model_role: coding" in instructions_content

    def test_has_fallback_chain_example(self, instructions_content: str) -> None:
        assert "model_role: [ui-coding, coding, general]" in instructions_content

    def test_has_utility_agent_example(self, instructions_content: str) -> None:
        assert "model_role: fast" in instructions_content

    def test_states_chain_order(self, instructions_content: str) -> None:
        """Chains are tried left-to-right, specific -> general."""
        assert "left-to-right" in instructions_content
        assert "specific \u2192 general" in instructions_content

    def test_states_chain_terminator_rule(self, instructions_content: str) -> None:
        """Always end a chain with `general` or `fast`."""
        assert "`general` or `fast`" in instructions_content


# ---------------------------------------------------------------------------
# Tests: per-call delegation override
# ---------------------------------------------------------------------------


class TestForDelegatingAgents:
    """Delegators may override the model role on a per-call basis."""

    def test_states_override_is_available(self, instructions_content: str) -> None:
        assert "override" in instructions_content

    def test_has_model_role_override_example(
        self, instructions_content: str
    ) -> None:
        assert 'model_role="vision"' in instructions_content

    def test_has_vision_role_in_example(self, instructions_content: str) -> None:
        """The delegation example uses 'vision' (not the old 'coding-image')."""
        assert '"vision"' in instructions_content

    def test_example_names_a_real_agent(self, instructions_content: str) -> None:
        assert 'agent="foundation:explorer"' in instructions_content


# ---------------------------------------------------------------------------
# Tests: pointer to the on-demand detail
# ---------------------------------------------------------------------------


class TestReferencesRoleDefinitions:
    """The detail lives in an on-demand skill; the pointer must survive."""

    def test_references_role_definitions(self, instructions_content: str) -> None:
        assert "role-definitions" in instructions_content

    def test_pointer_is_a_loadable_command(self, instructions_content: str) -> None:
        assert "load_skill(skill_name='role-definitions')" in instructions_content

    def test_names_what_the_skill_contains(self, instructions_content: str) -> None:
        """All four things the pointer promises must still be named."""
        for promised in (
            "Role definitions",
            "decision flowchart",
            "model tier grid",
            "fallback guidance",
        ):
            assert promised in instructions_content, f"pointer dropped: {promised}"

    def test_no_stale_role_references(self, instructions_content: str) -> None:
        """Should not reference old removed roles."""
        assert "| `agentic`" not in instructions_content
        assert "| `planning`" not in instructions_content
        assert "| `coding-image`" not in instructions_content


# ---------------------------------------------------------------------------
# Tests: the lean-head budget (anti-drift)
# ---------------------------------------------------------------------------


class TestLeanHeadBudget:
    """Pins the measured saving so the file cannot quietly grow back.

    This file is `context.include` content: it is in the head of EVERY request
    of EVERY session. Re-expanding it is not a style regression, it is a
    recurring cost regression, and nothing else in this repo would catch it.
    """

    def test_char_count_within_budget(self, instructions_content: str) -> None:
        actual = len(instructions_content)
        assert actual <= LEAN_CHAR_CEILING, (
            f"routing-instructions.md is {actual} chars, over the "
            f"{LEAN_CHAR_CEILING}-char head budget (measured lean: "
            f"{MEASURED_LEAN_CHARS}; pre-patch stock: {STOCK_CHARS_BEFORE_PATCH}). "
            "This file is paid for on every request of every session -- if the "
            "growth is genuinely warranted, raise the ceiling deliberately and "
            "say why in the commit."
        )

    def test_did_not_revert_to_stock(self, instructions_content: str) -> None:
        """The stock restatement sentence must stay gone."""
        assert (
            "This session uses the routing matrix system for model selection."
            not in instructions_content
        )

    def test_section_headings_stay_collapsed(
        self, instructions_content: str
    ) -> None:
        """The three stock section headings were removed on purpose."""
        for heading in (
            "## Available Roles",
            "## For Agent Authors",
            "## For Delegating Agents",
        ):
            assert heading not in instructions_content, (
                f"{heading!r} is back -- the lean rewrite collapsed the sections "
                "into single sentences. Re-adding headings re-adds head cost."
            )

    def test_example_fences_stay_collapsed(self, instructions_content: str) -> None:
        """The yaml/json example fences were inlined on purpose."""
        assert "```" not in instructions_content, (
            "a fenced code block is back -- the lean rewrite inlined every "
            "example into prose. Fences cost head bytes on every request."
        )
