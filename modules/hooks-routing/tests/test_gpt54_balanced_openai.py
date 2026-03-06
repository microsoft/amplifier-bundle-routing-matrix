"""Tests for GPT-5.4 model updates in balanced.yaml and openai.yaml.

Verifies the model swaps, date updates, and reasoning effort changes
specified in the GPT-5.4 ecosystem update (Strategy A — Conservative).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ROUTING_DIR = BUNDLE_ROOT / "routing"


def _load(name: str) -> dict:
    return yaml.safe_load((ROUTING_DIR / name).read_text())


def _find_candidate(candidates: list[dict], provider: str) -> dict | None:
    """Return the first candidate matching *provider*."""
    for c in candidates:
        if c["provider"] == provider:
            return c
    return None


def _find_all_candidates(candidates: list[dict], provider: str) -> list[dict]:
    """Return all candidates matching *provider*."""
    return [c for c in candidates if c["provider"] == provider]


# ===========================================================================
# balanced.yaml tests
# ===========================================================================


class TestBalancedDate:
    def test_updated_date_is_2026_03_06(self) -> None:
        data = _load("balanced.yaml")
        assert data["updated"] == "2026-03-06"


class TestBalancedOpenAIModels:
    """Verify every OpenAI candidate matches the target state table."""

    @pytest.mark.parametrize(
        "role,expected_model",
        [
            ("general", "gpt-5.4"),
            ("coding", "gpt-5.4"),
            ("ui-coding", "gpt-5.4"),
            ("security-audit", "gpt-5.4"),
            ("reasoning", "gpt-5.4-pro"),
            ("critique", "gpt-5.4"),
            ("creative", "gpt-5.4"),
            ("writing", "gpt-5.4"),
            ("research", "gpt-5.4-pro"),
            ("vision", "gpt-5.4"),
            ("critical-ops", "gpt-5.4-pro"),
        ],
    )
    def test_openai_model(self, role: str, expected_model: str) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"][role]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None, f"No OpenAI candidate for {role}"
        assert openai_candidate["model"] == expected_model, (
            f"{role}: expected OpenAI model '{expected_model}', "
            f"got '{openai_candidate['model']}'"
        )

    def test_fast_unchanged(self) -> None:
        """fast role should still use gpt-5-mini."""
        data = _load("balanced.yaml")
        candidates = data["roles"]["fast"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate["model"] == "gpt-5-mini"


class TestBalancedReasoningEffort:
    """Verify reasoning_effort config per role."""

    @pytest.mark.parametrize(
        "role",
        ["general", "coding", "ui-coding", "creative", "writing", "vision"],
    )
    def test_no_config_roles(self, role: str) -> None:
        """These roles should have no config on the OpenAI candidate."""
        data = _load("balanced.yaml")
        candidates = data["roles"][role]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert "config" not in openai_candidate, (
            f"{role}: OpenAI candidate should not have config"
        )

    def test_security_audit_reasoning_effort_high(self) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"]["security-audit"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_reasoning_effort_high(self) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"]["reasoning"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_research_effort_high(self) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"]["research"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_critique_effort_xhigh(self) -> None:
        """critique must use xhigh (not extra_high) for ALL providers."""
        data = _load("balanced.yaml")
        candidates = data["roles"]["critique"]["candidates"]
        for candidate in candidates:
            effort = candidate.get("config", {}).get("reasoning_effort")
            assert effort == "xhigh", (
                f"critique/{candidate['provider']}: expected reasoning_effort 'xhigh', "
                f"got '{effort}'"
            )

    def test_no_extra_high_anywhere(self) -> None:
        """extra_high must not appear anywhere in balanced.yaml."""
        data = _load("balanced.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                effort = candidate.get("config", {}).get("reasoning_effort")
                assert effort != "extra_high", (
                    f"{role_name}/{candidate['provider']}: "
                    f"found deprecated 'extra_high' reasoning_effort"
                )


class TestBalancedReasoningFallback:
    """The reasoning role's OpenAI fallback line should be gpt-5.4."""

    def test_reasoning_openai_fallback_is_gpt_5_4(self) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"]["reasoning"]["candidates"]
        openai_candidates = _find_all_candidates(candidates, "openai")
        assert len(openai_candidates) == 2, (
            f"Expected 2 OpenAI candidates in reasoning, got {len(openai_candidates)}"
        )
        # First is the primary (gpt-5.4-pro), second is the fallback (gpt-5.4)
        assert openai_candidates[0]["model"] == "gpt-5.4-pro"
        assert openai_candidates[1]["model"] == "gpt-5.4"


class TestBalancedGitHubCopilotMirror:
    """GitHub Copilot candidates mirror OpenAI model swaps."""

    @pytest.mark.parametrize(
        "role,expected_model",
        [
            ("general", "gpt-5.4"),
            ("fast", "gpt-5-mini"),  # unchanged
            ("coding", "gpt-5.4"),
            ("ui-coding", "gpt-5.4"),
            ("security-audit", "gpt-5.4"),
            ("critique", "gpt-5.4"),
            ("vision", "gpt-5.4"),
        ],
    )
    def test_copilot_gpt_model(self, role: str, expected_model: str) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"][role]["candidates"]
        # Find the github-copilot candidate that uses a GPT model (not claude)
        copilot_gpt = [
            c
            for c in candidates
            if c["provider"] == "github-copilot" and c["model"].startswith("gpt-")
        ]
        assert len(copilot_gpt) == 1, (
            f"{role}: expected 1 github-copilot GPT candidate, got {len(copilot_gpt)}"
        )
        assert copilot_gpt[0]["model"] == expected_model


class TestBalancedCriticalOpsNoConfig:
    """critical-ops OpenAI candidate should have no config (just model upgrade)."""

    def test_critical_ops_no_config(self) -> None:
        data = _load("balanced.yaml")
        candidates = data["roles"]["critical-ops"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert "config" not in openai_candidate


class TestBalancedNoStaleModels:
    """Old model strings must not appear anywhere."""

    def test_no_gpt_5_2_in_balanced(self) -> None:
        """gpt-5.2 (exact) should not appear — all replaced by gpt-5.4 or gpt-5.4-pro."""
        data = _load("balanced.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.2", (
                    f"{role_name}/{candidate['provider']}: stale model gpt-5.2"
                )

    def test_no_gpt_5_3_codex_in_balanced(self) -> None:
        """gpt-5.3-codex should not appear — all replaced by gpt-5.4."""
        data = _load("balanced.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.3-codex", (
                    f"{role_name}/{candidate['provider']}: stale model gpt-5.3-codex"
                )

    def test_no_gpt_5_2_pro_in_balanced(self) -> None:
        """gpt-5.2-pro should not appear — replaced by gpt-5.4-pro."""
        data = _load("balanced.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.2-pro", (
                    f"{role_name}/{candidate['provider']}: stale model gpt-5.2-pro"
                )


# ===========================================================================
# openai.yaml tests
# ===========================================================================


class TestOpenAIDate:
    def test_updated_date_is_2026_03_06(self) -> None:
        data = _load("openai.yaml")
        assert data["updated"] == "2026-03-06"


class TestOpenAIModels:
    """Verify every role's model in openai.yaml."""

    @pytest.mark.parametrize(
        "role,expected_model",
        [
            ("general", "gpt-5.4"),
            ("fast", "gpt-5-mini"),  # unchanged
            ("coding", "gpt-5.4"),
            ("ui-coding", "gpt-5.4"),
            ("security-audit", "gpt-5.4"),
            ("reasoning", "gpt-5.4-pro"),
            ("critique", "gpt-5.4"),
            ("creative", "gpt-5.4"),
            ("writing", "gpt-5.4"),
            ("research", "gpt-5.4-pro"),
            ("vision", "gpt-5.4"),
            ("image-gen", "gpt-5.4-pro"),
            ("critical-ops", "gpt-5.4-pro"),
        ],
    )
    def test_openai_model(self, role: str, expected_model: str) -> None:
        data = _load("openai.yaml")
        candidates = data["roles"][role]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None, f"No OpenAI candidate for {role}"
        assert openai_candidate["model"] == expected_model


class TestOpenAIReasoningEffort:
    def test_critique_xhigh(self) -> None:
        data = _load("openai.yaml")
        candidates = data["roles"]["critique"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "xhigh"

    def test_no_extra_high_anywhere(self) -> None:
        data = _load("openai.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                effort = candidate.get("config", {}).get("reasoning_effort")
                assert effort != "extra_high", (
                    f"{role_name}: found deprecated 'extra_high'"
                )

    def test_security_audit_effort_high(self) -> None:
        data = _load("openai.yaml")
        candidates = data["roles"]["security-audit"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_reasoning_effort_high(self) -> None:
        data = _load("openai.yaml")
        candidates = data["roles"]["reasoning"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_research_effort_high(self) -> None:
        data = _load("openai.yaml")
        candidates = data["roles"]["research"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"


class TestOpenAINoStaleModels:
    def test_no_gpt_5_2(self) -> None:
        data = _load("openai.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.2", (
                    f"{role_name}: stale model gpt-5.2"
                )

    def test_no_gpt_5_3_codex(self) -> None:
        data = _load("openai.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.3-codex", (
                    f"{role_name}: stale model gpt-5.3-codex"
                )

    def test_no_gpt_5_2_pro(self) -> None:
        data = _load("openai.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.2-pro", (
                    f"{role_name}: stale model gpt-5.2-pro"
                )


class TestYAMLValidity:
    """Both files must be valid YAML."""

    @pytest.mark.parametrize("filename", ["balanced.yaml", "openai.yaml"])
    def test_yaml_loads_without_error(self, filename: str) -> None:
        data = _load(filename)
        assert data is not None
        assert "roles" in data
        assert "name" in data
