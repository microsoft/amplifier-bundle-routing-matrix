"""Tests for the inert-config-key guard (model_performance-565).

WHAT THIS GUARDS

A matrix candidate can carry a `config:` block. That block is merged into the
child provider's MOUNT config. `validate_matrix_config` only judges VALUES of
keys the provider DECLARES; a key the provider does not declare takes the
explicit "undeclared key -- the open-key rule. Pass silently" branch
(matrix_loader.py:219-221).

`reasoning_effort` on a `gemini` candidate lands in exactly that branch.
provider-gemini consumes a closed set of 15 mount-config keys
(`_CONSUMED_CONFIG_KEYS`, provider-gemini __init__.py:551-566) and no effort
key is among them, so the setting is inert at EVERY value -- the read never
happens, which is why the value cannot matter.

These tests pin three properties:
  1. The guard NAMES the offending key, candidate and replacement.
  2. The guard REMOVES the key, so nothing downstream reports it as applied.
  3. The guard is SCOPED BY EVIDENCE -- it touches nothing else.

Plus a mechanised audit over every shipped matrix, so the day someone adds an
effort key to a gemini candidate the suite fails instead of the setting
sitting inert for a whole evaluation wave.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from amplifier_module_hooks_routing.matrix_loader import (
    EFFORT_KEYS,
    INERT_CONFIG_RULES,
    InertKeyRule,
    inert_config_rule,
    strip_inert_config,
    validate_matrix_inert_config,
)

# Walk up from tests/ -> hooks-routing/ -> modules/ -> bundle root
BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ROUTING_DIR = BUNDLE_ROOT / "routing"
SHIPPED_MATRICES = sorted(ROUTING_DIR.glob("*.yaml"))


def _matrix(*candidates: dict[str, Any]) -> dict[str, Any]:
    """Wrap candidates in the composed-matrix shape the guard consumes."""
    return {
        "roles": {
            "reasoning": {
                "description": "Deep reasoning",
                "candidates": list(candidates),
            }
        }
    }


# ---------------------------------------------------------------------------
# The rule table itself
# ---------------------------------------------------------------------------


class TestRuleTable:
    def test_effort_keys_cover_both_spellings(self) -> None:
        """A guard covering one spelling leaves the other silently dropping."""
        assert set(EFFORT_KEYS) == {"effort", "reasoning_effort"}

    def test_a_gemini_rule_is_enforced(self) -> None:
        assert any(r.provider == "gemini" for r in INERT_CONFIG_RULES)

    def test_gemini_rule_is_provider_keyed_not_model_keyed(self) -> None:
        """Gemini's defect is at the PROVIDER, so every model it serves is hit.

        Keying this on a model substring would need one row per model id and
        would silently miss the next id Google ships.
        """
        rule = next(r for r in INERT_CONFIG_RULES if r.provider == "gemini")
        assert rule.model_marker == ""

    def test_every_rule_carries_a_named_reason_and_remediation(self) -> None:
        """A rule with no evidence and no fix is not actionable."""
        for rule in INERT_CONFIG_RULES:
            assert isinstance(rule, InertKeyRule)
            assert len(rule.reason) > 80, rule
            assert rule.keys
            assert callable(rule.remediation)

    def test_rule_table_is_not_a_general_capability_model(self) -> None:
        """A provider absent from the table is not asserted to ignore anything."""
        assert inert_config_rule("openai", "gpt-5.2", "reasoning_effort") is None
        assert (
            inert_config_rule("anthropic", "claude-sonnet-4-5", "reasoning_effort")
            is None
        )
        assert inert_config_rule("ollama", "qwen3:32b", "reasoning_effort") is None


# ---------------------------------------------------------------------------
# inert_config_rule()
# ---------------------------------------------------------------------------


class TestInertConfigRule:
    @pytest.mark.parametrize(
        "model",
        [
            "gemini-*-pro-preview",
            "gemini-3.7-flash",
            "gemini-2.5-pro",
            "gemini-4-whatever-ships-next",
            "GEMINI-3.7-FLASH",
        ],
    )
    @pytest.mark.parametrize("key", ["reasoning_effort", "effort"])
    def test_matches_every_gemini_model_and_both_spellings(
        self, model: str, key: str
    ) -> None:
        assert inert_config_rule("gemini", model, key) is not None

    def test_does_not_match_a_key_outside_the_rule(self) -> None:
        """`temperature` IS consumed by gemini -- stripping it would be a bug."""
        assert inert_config_rule("gemini", "gemini-3.7-flash", "temperature") is None

    def test_does_not_match_another_provider(self) -> None:
        assert inert_config_rule("openai", "gpt-5.2", "reasoning_effort") is None

    def test_tolerates_non_string_input(self) -> None:
        assert inert_config_rule("gemini", None, "reasoning_effort") is not None  # type: ignore[arg-type]
        assert inert_config_rule(None, "gemini-3.7-flash", "reasoning_effort") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_matrix_inert_config()
# ---------------------------------------------------------------------------


class TestValidateMatrixInertConfig:
    def test_names_key_candidate_and_replacement(self) -> None:
        errors = validate_matrix_inert_config(
            _matrix(
                {
                    "provider": "gemini",
                    "model": "gemini-*-pro-preview",
                    "config": {"reasoning_effort": "high"},
                }
            )
        )
        assert len(errors) == 1
        err = errors[0]
        assert "reasoning_effort='high'" in err
        assert "gemini/gemini-*-pro-preview" in err
        assert "Role 'reasoning' candidate 0" in err
        assert "REJECTED" in err
        assert "extra_request_params" in err
        assert "thinking_level" in err

    @pytest.mark.parametrize(
        ("value", "expected_level"),
        [
            ("minimal", "minimal"),
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("xhigh", "high"),
            ("max", "high"),
        ],
    )
    def test_remediation_names_the_exact_thinking_level_per_value(
        self, value: str, expected_level: str
    ) -> None:
        """Naming the knob without its value is not actionable.

        Mirrors provider-gemini's own effort -> thinking_level ladder
        (_EFFORT_TO_LEVEL, provider-gemini __init__.py:348-355).
        """
        errors = validate_matrix_inert_config(
            _matrix(
                {
                    "provider": "gemini",
                    "model": "gemini-3.7-flash",
                    "config": {"reasoning_effort": value},
                }
            )
        )
        assert f"thinking_level: {expected_level}" in errors[0]

    def test_remediation_warns_about_the_2x_thinking_level_400(self) -> None:
        """Getting the generation split wrong turns an inert key into a 400."""
        errors = validate_matrix_inert_config(
            _matrix(
                {
                    "provider": "gemini",
                    "model": "gemini-*-pro-preview",
                    "config": {"reasoning_effort": "high"},
                }
            )
        )
        assert "thinking_budget" in errors[0]
        assert "gemini-2" in errors[0]

    def test_rejects_every_value_not_just_the_high_ones(self) -> None:
        """The read never happens, so no value is distinguishable."""
        for value in ("minimal", "low", "medium", "high", "xhigh", "max"):
            errors = validate_matrix_inert_config(
                _matrix(
                    {
                        "provider": "gemini",
                        "model": "gemini-3.7-flash",
                        "config": {"reasoning_effort": value},
                    }
                )
            )
            assert len(errors) == 1, f"{value} not rejected"

    def test_clean_matrix_produces_no_errors(self) -> None:
        assert (
            validate_matrix_inert_config(
                _matrix(
                    {"provider": "gemini", "model": "gemini-3.7-flash"},
                    {
                        "provider": "openai",
                        "model": "gpt-5.2",
                        "config": {"reasoning_effort": "high"},
                    },
                )
            )
            == []
        )

    def test_needs_no_provider_instances_or_coordinator(self) -> None:
        """Pure function of the matrix -- runs when providers are absent.

        validate_matrix_config returns [] early when no providers are
        installed; this check must still fire, because a curator editing a
        matrix rarely has every provider mounted.
        """
        errors = validate_matrix_inert_config(
            _matrix(
                {
                    "provider": "gemini",
                    "model": "gemini-3.7-flash",
                    "config": {"effort": "max"},
                }
            )
        )
        assert len(errors) == 1

    def test_tolerates_malformed_matrix_shapes(self) -> None:
        """A bad matrix must never crash the loader."""
        assert validate_matrix_inert_config({}) == []
        assert validate_matrix_inert_config({"roles": None}) == []
        assert validate_matrix_inert_config({"roles": {"r": "not-a-dict"}}) == []
        assert (
            validate_matrix_inert_config({"roles": {"r": {"candidates": ["base"]}}})
            == []
        )
        assert (
            validate_matrix_inert_config(
                {"roles": {"r": {"candidates": [{"provider": "gemini"}]}}}
            )
            == []
        )


# ---------------------------------------------------------------------------
# strip_inert_config()
# ---------------------------------------------------------------------------


class TestStripInertConfig:
    def test_removes_the_inert_key(self) -> None:
        cleaned, errors = strip_inert_config(
            _matrix(
                {
                    "provider": "gemini",
                    "model": "gemini-*-pro-preview",
                    "config": {"reasoning_effort": "xhigh"},
                }
            )
        )
        cfg = cleaned["roles"]["reasoning"]["candidates"][0]["config"]
        assert "reasoning_effort" not in cfg
        assert len(errors) == 1

    def test_preserves_live_sibling_keys(self) -> None:
        cleaned, _ = strip_inert_config(
            _matrix(
                {
                    "provider": "gemini",
                    "model": "gemini-3.7-flash",
                    "config": {"reasoning_effort": "high", "temperature": 0.2},
                }
            )
        )
        cfg = cleaned["roles"]["reasoning"]["candidates"][0]["config"]
        assert cfg == {"temperature": 0.2}

    def test_does_not_mutate_the_input(self) -> None:
        original = _matrix(
            {
                "provider": "gemini",
                "model": "gemini-3.7-flash",
                "config": {"reasoning_effort": "high"},
            }
        )
        strip_inert_config(original)
        assert (
            original["roles"]["reasoning"]["candidates"][0]["config"][
                "reasoning_effort"
            ]
            == "high"
        )

    def test_clean_matrix_is_returned_unchanged_without_a_copy(self) -> None:
        """A clean matrix costs no deepcopy."""
        clean = _matrix({"provider": "gemini", "model": "gemini-3.7-flash"})
        result, errors = strip_inert_config(clean)
        assert result is clean
        assert errors == []


# ---------------------------------------------------------------------------
# Mechanised audit of every shipped matrix
# ---------------------------------------------------------------------------


class TestShippedMatrices:
    def test_the_audit_actually_found_matrix_files(self) -> None:
        """Guard the guard: a glob that matches nothing proves nothing."""
        assert len(SHIPPED_MATRICES) >= 8, SHIPPED_MATRICES

    @pytest.mark.parametrize(
        "matrix_path", SHIPPED_MATRICES, ids=lambda p: p.name
    )
    def test_shipped_matrix_carries_no_inert_config_keys(
        self, matrix_path: Path
    ) -> None:
        """Every shipped matrix must load with nothing to strip.

        This is the mechanised form of the one-off audit. 14 candidates across
        balanced/economy/gemini/quality carried an inert `reasoning_effort` on
        a `gemini` candidate and were fixed in the same change that added this
        guard. This test fails the day one comes back.
        """
        data = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
        errors = validate_matrix_inert_config({"roles": data.get("roles") or {}})
        assert errors == [], (
            f"{matrix_path.name} carries config keys the target never reads:\n"
            + "\n".join(errors)
        )
