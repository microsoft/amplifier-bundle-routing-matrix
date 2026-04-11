"""Tests for task-9: economy.yaml + copilot.yaml updates for GPT-5.4."""

import yaml
from pathlib import Path

ROUTING_DIR = Path(__file__).parent.parent / "routing"


def load_yaml(name: str) -> dict:
    """Load and parse a YAML file from the routing directory."""
    path = ROUTING_DIR / name
    with open(path) as f:
        return yaml.safe_load(f)


def read_raw(name: str) -> str:
    """Read raw text of a YAML file from the routing directory."""
    path = ROUTING_DIR / name
    return path.read_text()


# =============================================================
# economy.yaml tests
# =============================================================


class TestEconomyYaml:
    def test_yaml_is_valid(self):
        """economy.yaml must parse without errors."""
        data = load_yaml("economy.yaml")
        assert data is not None
        assert "roles" in data

    def test_updated_date(self):
        """updated field must be 2026-03-06."""
        data = load_yaml("economy.yaml")
        assert data["updated"] == "2026-03-06"

    def test_no_gpt_5_2_remains(self):
        """gpt-5.2 must not appear anywhere in economy.yaml."""
        raw = read_raw("economy.yaml")
        assert "gpt-5.2" not in raw, "gpt-5.2 should be fully replaced in economy.yaml"

    def test_gpt_5_4_in_security_audit(self):
        """security-audit role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["security-audit"]["candidates"]]
        assert "gpt-5.4" in models

    def test_gpt_5_4_in_reasoning(self):
        """reasoning role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["reasoning"]["candidates"]]
        assert "gpt-5.4" in models

    def test_gpt_5_4_in_critique(self):
        """critique role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["critique"]["candidates"]]
        assert "gpt-5.4" in models

    def test_gpt_5_4_in_creative(self):
        """creative role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["creative"]["candidates"]]
        assert "gpt-5.4" in models

    def test_gpt_5_4_in_writing(self):
        """writing role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["writing"]["candidates"]]
        assert "gpt-5.4" in models

    def test_gpt_5_4_in_research(self):
        """research role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["research"]["candidates"]]
        assert "gpt-5.4" in models

    def test_gpt_5_4_in_critical_ops(self):
        """critical-ops role must have gpt-5.4 (was gpt-5.2)."""
        data = load_yaml("economy.yaml")
        models = [c["model"] for c in data["roles"]["critical-ops"]["candidates"]]
        assert "gpt-5.4" in models

    def test_critique_reasoning_effort_xhigh(self):
        """critique role must use xhigh (not extra_high) for all providers."""
        data = load_yaml("economy.yaml")
        for candidate in data["roles"]["critique"]["candidates"]:
            if "config" in candidate and "reasoning_effort" in candidate["config"]:
                assert candidate["config"]["reasoning_effort"] == "xhigh", (
                    f"Provider {candidate['provider']} in critique has "
                    f"reasoning_effort={candidate['config']['reasoning_effort']}, expected xhigh"
                )

    def test_no_extra_high_anywhere(self):
        """extra_high must not appear anywhere in economy.yaml."""
        raw = read_raw("economy.yaml")
        assert "extra_high" not in raw, "extra_high should be replaced with xhigh"

    def test_github_copilot_critique_uses_gpt_5_4(self):
        """GitHub Copilot candidate in critique must use gpt-5.4."""
        data = load_yaml("economy.yaml")
        copilot_candidates = [
            c
            for c in data["roles"]["critique"]["candidates"]
            if c["provider"] == "github-copilot"
        ]
        assert len(copilot_candidates) > 0, (
            "critique must have a github-copilot candidate"
        )
        assert copilot_candidates[0]["model"] == "gpt-5.4"

    def test_github_copilot_reasoning_uses_gpt_5_4(self):
        """GitHub Copilot gpt-5.x candidate in reasoning must use gpt-5.4."""
        data = load_yaml("economy.yaml")
        copilot_gpt_candidates = [
            c
            for c in data["roles"]["reasoning"]["candidates"]
            if c["provider"] == "github-copilot" and c["model"].startswith("gpt-5.")
        ]
        assert len(copilot_gpt_candidates) > 0
        assert copilot_gpt_candidates[0]["model"] == "gpt-5.4"

    def test_github_copilot_critical_ops_uses_gpt_5_4(self):
        """GitHub Copilot candidates in critical-ops do NOT have gpt-5.2."""
        data = load_yaml("economy.yaml")
        copilot_candidates = [
            c
            for c in data["roles"]["critical-ops"]["candidates"]
            if c["provider"] == "github-copilot"
        ]
        for c in copilot_candidates:
            assert c["model"] != "gpt-5.2"

    def test_non_gpt52_models_unchanged(self):
        """Models that were NOT gpt-5.2 must remain unchanged (e.g., gpt-5-mini, claude-*)."""
        data = load_yaml("economy.yaml")
        # general role should still have gpt-5-mini (not gpt-5.4)
        general_models = [c["model"] for c in data["roles"]["general"]["candidates"]]
        assert "gpt-5-mini" in general_models
        # fast role should still have gpt-5-mini
        fast_models = [c["model"] for c in data["roles"]["fast"]["candidates"]]
        assert "gpt-5-mini" in fast_models


# =============================================================
# copilot.yaml tests
# =============================================================


class TestCopilotYaml:
    def test_yaml_is_valid(self):
        """copilot.yaml must parse without errors."""
        data = load_yaml("copilot.yaml")
        assert data is not None
        assert "roles" in data

    def test_updated_date(self):
        """updated field must be 2026-03-06."""
        data = load_yaml("copilot.yaml")
        assert data["updated"] == "2026-03-06"

    def test_gpt_5_4_available_on_copilot(self):
        """gpt-5.4 is now available on Copilot (PR #4) and should be used in applicable roles."""
        data = load_yaml("copilot.yaml")
        all_models = []
        for role_data in data["roles"].values():
            all_models.extend(c["model"] for c in role_data["candidates"])
        assert "gpt-5.4" in all_models, "gpt-5.4 should be present in copilot.yaml"

    def test_no_stale_gpt_5_2_in_copilot(self):
        """gpt-5.2 has been replaced by gpt-5.4 (PR #4) and should not appear."""
        raw = read_raw("copilot.yaml")
        assert "gpt-5.2" not in raw, "gpt-5.2 should be fully replaced in copilot.yaml"

    def test_no_stale_gpt_5_3_codex_in_copilot(self):
        """gpt-5.3-codex has been replaced by gpt-5.4 (PR #4) and should not appear."""
        raw = read_raw("copilot.yaml")
        assert "gpt-5.3-codex" not in raw, (
            "gpt-5.3-codex should be fully replaced in copilot.yaml"
        )

    def test_critique_reasoning_effort_xhigh(self):
        """critique role must use xhigh (not extra_high)."""
        data = load_yaml("copilot.yaml")
        for candidate in data["roles"]["critique"]["candidates"]:
            if "config" in candidate and "reasoning_effort" in candidate["config"]:
                assert candidate["config"]["reasoning_effort"] == "xhigh", (
                    f"critique has reasoning_effort={candidate['config']['reasoning_effort']}, expected xhigh"
                )

    def test_no_extra_high_anywhere(self):
        """extra_high must not appear anywhere in copilot.yaml."""
        raw = read_raw("copilot.yaml")
        assert "extra_high" not in raw, "extra_high should be replaced with xhigh"

    def test_todo_comments_on_gpt_5_3_codex(self):
        """Every gpt-5.3-codex entry must have a TODO comment."""
        raw = read_raw("copilot.yaml")
        lines = raw.splitlines()
        for i, line in enumerate(lines):
            if "gpt-5.3-codex" in line:
                assert "TODO" in line, (
                    f"Line {i + 1} has gpt-5.3-codex but no TODO comment: {line.strip()}"
                )
                assert "Update to gpt-5.4 when available on Copilot" in line, (
                    f"Line {i + 1} TODO comment has wrong text: {line.strip()}"
                )

    def test_todo_comments_on_gpt_5_2(self):
        """Every gpt-5.2 entry must have a TODO comment."""
        raw = read_raw("copilot.yaml")
        lines = raw.splitlines()
        for i, line in enumerate(lines):
            if "gpt-5.2" in line:
                assert "TODO" in line, (
                    f"Line {i + 1} has gpt-5.2 but no TODO comment: {line.strip()}"
                )
                assert "Update to gpt-5.4 when available on Copilot" in line, (
                    f"Line {i + 1} TODO comment has wrong text: {line.strip()}"
                )

    def test_todo_count_matches_model_count(self):
        """Number of TODO comments must match number of gpt-5.3-codex + gpt-5.2 entries."""
        raw = read_raw("copilot.yaml")
        lines = raw.splitlines()
        model_lines = [
            line for line in lines if "gpt-5.3-codex" in line or "gpt-5.2" in line
        ]
        todo_lines = [line for line in model_lines if "TODO" in line]
        assert len(todo_lines) == len(model_lines), (
            f"Found {len(model_lines)} gpt-5.3-codex/gpt-5.2 entries "
            f"but only {len(todo_lines)} have TODO comments"
        )
