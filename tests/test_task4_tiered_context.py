"""Tests for task-4: convert role-definitions to on-demand skill.

Encodes the 5 verification checks from task-4 so future regressions
are caught automatically rather than only at review time.
"""

import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
BEHAVIORS_DIR = REPO_ROOT / "behaviors"
CONTEXT_DIR = REPO_ROOT / "context"


class TestTask4TieredContext:
    """Verify the role-definitions context was converted to an on-demand skill."""

    def test_skill_file_exists(self):
        """Check 1: skill file exists at skills/role-definitions/SKILL.md."""
        skill_path = SKILLS_DIR / "role-definitions" / "SKILL.md"
        assert skill_path.exists(), (
            f"SKILL.md not found at {skill_path}. Run task-1 to create the skill file."
        )

    def test_skill_frontmatter_name(self):
        """Check 2: skill frontmatter has name: role-definitions."""
        skill_path = SKILLS_DIR / "role-definitions" / "SKILL.md"
        raw = skill_path.read_text()

        # Extract YAML frontmatter between --- delimiters
        parts = raw.split("---", 2)
        assert len(parts) >= 3, (
            "SKILL.md missing YAML frontmatter (expected --- delimiters)"
        )

        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter is not None, "SKILL.md frontmatter is empty"
        assert frontmatter.get("name") == "role-definitions", (
            f"SKILL.md frontmatter has name={frontmatter.get('name')!r}, "
            "expected 'role-definitions'"
        )

    def test_routing_yaml_no_role_definitions_context(self):
        """Check 3: routing.yaml does not reference context/role-definitions."""
        routing_yaml = BEHAVIORS_DIR / "routing.yaml"
        raw = routing_yaml.read_text()
        assert "role-definitions" not in raw or "tool-skills" in raw, (
            "routing.yaml still references role-definitions in context (not via tool-skills)"
        )
        # Specifically check it's not in the context include section
        data = yaml.safe_load(raw)
        context_includes = (
            data.get("context", {}).get("include", [])
            if data and isinstance(data.get("context"), dict)
            else []
        )
        for entry in context_includes:
            assert "role-definitions" not in str(entry), (
                f"routing.yaml context.include still contains role-definitions: {entry}"
            )

    def test_routing_yaml_has_tool_skills(self):
        """Check 4: routing.yaml has tool-skills in the tools section."""
        routing_yaml = BEHAVIORS_DIR / "routing.yaml"
        raw = routing_yaml.read_text()
        assert "tool-skills" in raw, (
            "routing.yaml is missing 'tool-skills' in the tools section. "
            "Run task-3 to register the skill."
        )

    def test_routing_instructions_has_load_skill_pointer(self):
        """Check 5: routing-instructions.md has a load_skill pointer."""
        instructions = CONTEXT_DIR / "routing-instructions.md"
        raw = instructions.read_text()
        assert "load_skill" in raw, (
            "routing-instructions.md is missing a load_skill pointer. "
            "Run task-2 to add the pointer."
        )
        assert "role-definitions" in raw, (
            "routing-instructions.md load_skill pointer does not reference 'role-definitions'"
        )
