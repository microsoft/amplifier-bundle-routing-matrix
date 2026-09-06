"""Contract tests for the built-in openai-chatgpt routing matrix."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
MATRIX_PATH = REPO_ROOT / "routing" / "openai-chatgpt.yaml"
OPENAI_MATRIX_PATH = REPO_ROOT / "routing" / "openai.yaml"

BASE_PATTERN = "gpt-[0-9].[0-9]"
HIGH_EFFORT_ROLES = {
    "general",
    "coding",
    "ui-coding",
    "security-audit",
    "reasoning",
    "critique",
    "research",
    "critical-ops",
}
EXPECTED_CANDIDATES = {
    "general": ["gpt-?.?-terra*", BASE_PATTERN],
    "fast": ["gpt-?.?-luna*", "gpt-?.?-mini*"],
    "coding": ["gpt-?.?-terra*", BASE_PATTERN],
    "ui-coding": ["gpt-?.?-terra*", BASE_PATTERN],
    "security-audit": ["gpt-?.?-terra*", BASE_PATTERN],
    "reasoning": ["gpt-?.?-sol*", BASE_PATTERN],
    "critique": ["gpt-?.?-terra*", BASE_PATTERN],
    "creative": ["gpt-?.?-sol*", BASE_PATTERN],
    "writing": ["gpt-?.?-sol*", BASE_PATTERN],
    "research": ["gpt-?.?-sol*", BASE_PATTERN],
    "vision": ["gpt-?.?-terra*", BASE_PATTERN],
    "image-gen": ["gpt-?.?-sol*", BASE_PATTERN],
    "critical-ops": ["gpt-?.?-sol*", BASE_PATTERN],
}


def load_yaml(path: Path) -> dict:
    """Load one routing matrix."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_openai_chatgpt_matrix_contract():
    """The ChatGPT matrix has complete, provider-compatible role routing."""
    assert MATRIX_PATH.exists(), f"Missing built-in matrix: {MATRIX_PATH}"

    matrix = load_yaml(MATRIX_PATH)
    openai_matrix = load_yaml(OPENAI_MATRIX_PATH)

    assert matrix["name"] == "openai-chatgpt"
    assert matrix["updated"] == "2026-09-01"
    assert set(matrix["roles"]) == set(EXPECTED_CANDIDATES)
    assert len(matrix["roles"]) == 13

    for role, expected_models in EXPECTED_CANDIDATES.items():
        candidates = matrix["roles"][role]["candidates"]
        assert [candidate["provider"] for candidate in candidates] == [
            "openai-chatgpt"
        ] * len(expected_models)
        assert [candidate["model"] for candidate in candidates] == expected_models

        efforts = [
            candidate.get("config", {}).get("reasoning_effort")
            for candidate in candidates
        ]
        expected_efforts = (
            ["high", "high"]
            if role in HIGH_EFFORT_ROLES
            else [None] * len(expected_models)
        )
        assert efforts == expected_efforts
        assert "xhigh" not in efforts

    for role, role_def in matrix["roles"].items():
        if role == "image-gen":
            assert (
                "no native image generation through openai-chatgpt"
                in role_def["description"].lower()
            )
        else:
            assert (
                role_def["description"] == openai_matrix["roles"][role]["description"]
            )
