"""Tests for GPT-5.4 model updates in quality.yaml.

Verifies the model swaps, date updates, and reasoning effort changes
specified in the GPT-5.4 ecosystem update (Strategy B — Compensating).

Strategy B adds explicit reasoning_effort on nearly every role to compensate
for GPT-5.4's `none` default.
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


# ===========================================================================
# Date
# ===========================================================================


class TestQualityDate:
    def test_updated_date_is_2026_03_06(self) -> None:
        data = _load("quality.yaml")
        assert data["updated"] == "2026-03-06"


# ===========================================================================
# Model swaps
# ===========================================================================


class TestQualityOpenAIModels:
    """Verify every OpenAI candidate matches the target model."""

    @pytest.mark.parametrize(
        "role,expected_model",
        [
            ("general", "gpt-5.4"),
            ("fast", "gpt-5.4"),
            ("coding", "gpt-5.4"),
            ("ui-coding", "gpt-5.4"),
            ("security-audit", "gpt-5.4"),
            ("reasoning", "gpt-5.4-pro"),
            ("critique", "gpt-5.4-pro"),
            ("creative", "gpt-5.4-pro"),
            ("writing", "gpt-5.4-pro"),
            ("research", "gpt-5.4-pro"),
            ("vision", "gpt-5.4"),
            ("critical-ops", "gpt-5.4-pro"),
        ],
    )
    def test_openai_model(self, role: str, expected_model: str) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"][role]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None, f"No OpenAI candidate for {role}"
        assert openai_candidate["model"] == expected_model, (
            f"{role}: expected OpenAI model '{expected_model}', "
            f"got '{openai_candidate['model']}'"
        )


class TestQualityNoStaleModels:
    """Old model strings must not appear anywhere in quality.yaml."""

    def test_no_gpt_5_2(self) -> None:
        data = _load("quality.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.2", (
                    f"{role_name}/{candidate['provider']}: stale model gpt-5.2"
                )

    def test_no_gpt_5_3_codex(self) -> None:
        data = _load("quality.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.3-codex", (
                    f"{role_name}/{candidate['provider']}: stale model gpt-5.3-codex"
                )

    def test_no_gpt_5_2_pro(self) -> None:
        data = _load("quality.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                assert candidate["model"] != "gpt-5.2-pro", (
                    f"{role_name}/{candidate['provider']}: stale model gpt-5.2-pro"
                )


# ===========================================================================
# Reasoning effort — Strategy B (Compensating)
# ===========================================================================


class TestQualityReasoningEffort:
    """Strategy B: explicit reasoning_effort on nearly every role."""

    def test_general_reasoning_effort_low(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["general"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "low"

    def test_fast_no_reasoning(self) -> None:
        """fast shouldn't reason — no config at all."""
        data = _load("quality.yaml")
        candidates = data["roles"]["fast"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert "config" not in openai_candidate, (
            "fast: OpenAI candidate should not have config (no reasoning)"
        )

    def test_coding_reasoning_effort_medium(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["coding"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "medium"

    def test_ui_coding_reasoning_effort_medium(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["ui-coding"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "medium"

    def test_security_audit_reasoning_effort_high(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["security-audit"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_reasoning_effort_high(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["reasoning"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_critique_effort_xhigh(self) -> None:
        """critique must use xhigh (not extra_high) for ALL providers."""
        data = _load("quality.yaml")
        candidates = data["roles"]["critique"]["candidates"]
        for candidate in candidates:
            effort = candidate.get("config", {}).get("reasoning_effort")
            assert effort == "xhigh", (
                f"critique/{candidate['provider']}: expected reasoning_effort 'xhigh', "
                f"got '{effort}'"
            )

    def test_creative_reasoning_effort_low(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["creative"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "low"

    def test_writing_reasoning_effort_low(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["writing"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "low"

    def test_research_reasoning_effort_high(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["research"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "high"

    def test_vision_no_reasoning(self) -> None:
        """vision is perception, not reasoning — no config."""
        data = _load("quality.yaml")
        candidates = data["roles"]["vision"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert "config" not in openai_candidate, (
            "vision: OpenAI candidate should not have config (perception, not reasoning)"
        )

    def test_critical_ops_reasoning_effort_medium(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["critical-ops"]["candidates"]
        openai_candidate = _find_candidate(candidates, "openai")
        assert openai_candidate is not None
        assert openai_candidate.get("config", {}).get("reasoning_effort") == "medium"


class TestQualityNoExtraHigh:
    """extra_high must not appear anywhere in quality.yaml."""

    def test_no_extra_high_anywhere(self) -> None:
        data = _load("quality.yaml")
        for role_name, role_def in data["roles"].items():
            for candidate in role_def["candidates"]:
                effort = candidate.get("config", {}).get("reasoning_effort")
                assert effort != "extra_high", (
                    f"{role_name}/{candidate['provider']}: "
                    f"found deprecated 'extra_high' reasoning_effort"
                )


# ===========================================================================
# GitHub Copilot model mirror
# ===========================================================================


class TestQualityGitHubCopilotModel:
    """GitHub Copilot candidates with GPT models should be updated too."""

    def test_security_audit_copilot_model(self) -> None:
        data = _load("quality.yaml")
        candidates = data["roles"]["security-audit"]["candidates"]
        copilot = _find_candidate(candidates, "github-copilot")
        assert copilot is not None
        assert copilot["model"] == "gpt-5.4", (
            f"security-audit/github-copilot: expected gpt-5.4, got '{copilot['model']}'"
        )


# ===========================================================================
# YAML validity
# ===========================================================================


class TestQualityYAMLValidity:
    def test_yaml_loads_without_error(self) -> None:
        data = _load("quality.yaml")
        assert data is not None
        assert "roles" in data
        assert "name" in data
