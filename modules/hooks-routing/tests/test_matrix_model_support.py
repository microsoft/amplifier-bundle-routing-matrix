"""Tests for the model-aware effort guard.

THE DEFECT
----------
``validate_matrix_config`` is **closed on values and OPEN on keys**
(matrix_loader.py:146-154, :219-221): it only ever flags a value when the
provider declares that key as a ``choice`` field and the value is not among
the declared choices. That is exactly the wrong shape for this defect.

``reasoning_effort: high`` on a ``claude-haiku-*`` candidate is a DECLARED key
(provider-anthropic declares it, ``__init__.py:1017``) carrying a LEGAL value
on an INSTALLED provider -- so it sails through validation. It is then
collapsed to nothing when the request is built, because Haiku has
``supports_output_config=False`` and ``supports_adaptive_thinking=False``, so
every effort level above ``low`` resolves to the same
``default_thinking_budget=32000`` (provider-anthropic ``__init__.py:1541-1550``
capability table, ``__init__.py:3024-3046`` effort ladder). The operator is
never told. The cell measures nothing.

MEASURED EVIDENCE FOR THE RULE
------------------------------
20260901-threeknob capture root, effort attributed PER REQUEST by joining to
that request's own ``model`` field:

    claude-haiku-4-5            effort ABSENT, thinking.budget_tokens=32000, n=1438
    claude-haiku-4-5-20251001   effort ABSENT, thinking.budget_tokens=32000, n=6
    anth-haiku-high   n=702 requests -> exactly one distinct reasoning config
    anth-haiku-medium n=736 requests -> the SAME one

Two of sixteen cells in that wave were byte-identical configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from amplifier_module_hooks_routing.matrix_loader import (
    EFFORT_KEYS,
    effort_remediation,
    model_ignores_effort,
    strip_unsupported_effort,
    validate_matrix_model_support,
)

# Walk up from tests/ -> hooks-routing/ -> modules/ -> bundle root -> routing/
BUNDLE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ROUTING_DIR = BUNDLE_ROOT / "routing"


def _matrix(
    model: str, config: dict[str, Any] | None, role: str = "fast"
) -> dict[str, Any]:
    candidate: dict[str, Any] = {"provider": "anthropic", "model": model}
    if config is not None:
        candidate["config"] = config
    return {"roles": {role: {"description": "d", "candidates": [candidate]}}}


# ---------------------------------------------------------------------------
# The defect itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["effort", "reasoning_effort"])
@pytest.mark.parametrize(
    "model",
    [
        "claude-haiku-*",
        "claude-haiku-4.5",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
        "anthropic/claude-haiku-4.5",
        "CLAUDE-HAIKU-4.5",
    ],
)
def test_effort_on_any_haiku_spelling_is_rejected(model: str, key: str) -> None:
    errors = validate_matrix_model_support(_matrix(model, {key: "high"}))
    assert len(errors) == 1, errors
    # The error must NAME the role, the candidate, the model, the key and the
    # value. An unnamed "invalid config" is the failure mode being fixed.
    assert "fast" in errors[0]
    assert "candidate 0" in errors[0]
    assert model in errors[0]
    assert key in errors[0]
    assert "high" in errors[0]
    assert "REJECTED" in errors[0]
    # ...and it must say what to use instead.
    assert "thinking_budget_tokens" in errors[0]


def test_both_effort_spellings_on_one_candidate_are_each_named() -> None:
    errors = validate_matrix_model_support(
        _matrix("claude-haiku-*", {"effort": "high", "reasoning_effort": "medium"})
    )
    assert len(errors) == 2, errors
    assert any("effort='high'" in e for e in errors)
    assert any("reasoning_effort='medium'" in e for e in errors)


def test_rejection_is_structural_not_advisory() -> None:
    """The key must not survive into the effective matrix."""
    matrix = _matrix("claude-haiku-*", {"reasoning_effort": "high", "temperature": 1.0})
    cleaned, errors = strip_unsupported_effort(matrix)
    assert errors
    cfg = cleaned["roles"]["fast"]["candidates"][0]["config"]
    assert "reasoning_effort" not in cfg
    # Unrelated knobs are untouched -- a targeted rejection, not a purge.
    assert cfg["temperature"] == 1.0
    # ...and the input is not mutated.
    assert (
        matrix["roles"]["fast"]["candidates"][0]["config"]["reasoning_effort"] == "high"
    )


def test_every_haiku_role_and_candidate_index_is_named_separately() -> None:
    matrix = {
        "roles": {
            "fast": {
                "description": "d",
                "candidates": [
                    {"provider": "anthropic", "model": "claude-sonnet-5"},
                    {
                        "provider": "anthropic",
                        "model": "claude-haiku-4.5",
                        "config": {"reasoning_effort": "high"},
                    },
                ],
            },
            "general": {
                "description": "d",
                "candidates": [
                    {
                        "provider": "anthropic",
                        "model": "claude-haiku-*",
                        "config": {"effort": "low"},
                    },
                ],
            },
        }
    }
    errors = validate_matrix_model_support(matrix)
    assert len(errors) == 2, errors
    assert any("'fast' candidate 1" in e for e in errors)
    assert any("'general' candidate 0" in e for e in errors)


# ---------------------------------------------------------------------------
# The remediation must be EXACT, not generic advice
# ---------------------------------------------------------------------------


def test_remediation_is_value_specific() -> None:
    """`low` and the collapsed tiers have DIFFERENT exact replacements.

    On Haiku the effort ladder resolves ``low`` to budget 4096 and every tier
    above it to the model default 32000 (provider-anthropic
    ``__init__.py:3026-3046``). Telling an operator to "use
    thinking_budget_tokens" without the number is not actionable; telling them
    the wrong number silently changes behaviour.
    """
    assert "4096" in effort_remediation("claude-haiku-4.5", "low")
    for value in ("medium", "high", "xhigh", "max"):
        assert "32000" in effort_remediation("claude-haiku-4.5", value)


def test_remediation_appears_in_the_error() -> None:
    low = validate_matrix_model_support(
        _matrix("claude-haiku-*", {"reasoning_effort": "low"})
    )
    high = validate_matrix_model_support(
        _matrix("claude-haiku-*", {"reasoning_effort": "high"})
    )
    assert "4096" in low[0]
    assert "32000" in high[0]


def test_remediation_is_none_for_models_that_honour_effort() -> None:
    assert effort_remediation("claude-sonnet-5", "xhigh") is None


# ---------------------------------------------------------------------------
# Everything that must still pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-5",
        "claude-sonnet-*",
        "claude-opus-5",
        "claude-opus-4-8",
        "gpt-?.?-sol*",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gemini-*-pro-preview",
    ],
)
def test_effort_on_effort_honouring_models_is_untouched(model: str) -> None:
    matrix = _matrix(model, {"reasoning_effort": "xhigh"})
    assert validate_matrix_model_support(matrix) == []
    cleaned, errors = strip_unsupported_effort(matrix)
    assert errors == []
    assert cleaned is matrix  # no copy taken when there is nothing to strip


def test_haiku_without_any_effort_key_is_fine() -> None:
    assert validate_matrix_model_support(_matrix("claude-haiku-*", None)) == []
    assert validate_matrix_model_support(_matrix("claude-haiku-*", {})) == []


def test_haiku_with_a_non_effort_knob_is_fine() -> None:
    """Haiku's real reasoning dial IS thinking_budget_tokens -- do not block it."""
    matrix = _matrix("claude-haiku-*", {"thinking_budget_tokens": 32000})
    assert validate_matrix_model_support(matrix) == []
    cleaned, errors = strip_unsupported_effort(matrix)
    assert errors == []
    assert cleaned is matrix


def test_effort_keys_are_exactly_the_two_spellings() -> None:
    """Both spellings the anthropic provider consumes, and no others.

    provider-anthropic reads the canonical ``reasoning_effort`` and the legacy
    ``effort`` alias (``__init__.py:641-654``, :2926-2936). A guard that covers
    only one spelling leaves the other silently dropping.
    """
    assert set(EFFORT_KEYS) == {"effort", "reasoning_effort"}


# ---------------------------------------------------------------------------
# Shapes that must not crash the loader
# ---------------------------------------------------------------------------


def test_base_keyword_and_malformed_shapes_do_not_crash() -> None:
    matrix = {
        "roles": {
            "fast": {"candidates": ["base", None, 7, {"model": "claude-haiku-*"}]},
            "broken": ["not", "a", "mapping"],
            "no_candidates": {"description": "d"},
            "null_candidates": {"description": "d", "candidates": None},
        }
    }
    assert validate_matrix_model_support(matrix) == []
    cleaned, errors = strip_unsupported_effort(matrix)
    assert errors == []
    assert cleaned is matrix


def test_malformed_shapes_survive_the_strip_path_too() -> None:
    """One real offender alongside junk: strip must clean it without crashing."""
    matrix = {
        "roles": {
            "fast": {
                "candidates": [
                    "base",
                    None,
                    {"provider": "anthropic", "model": "claude-haiku-*", "config": None},
                    {
                        "provider": "anthropic",
                        "model": "claude-haiku-*",
                        "config": {"effort": "high"},
                    },
                ]
            },
            "broken": ["not", "a", "mapping"],
        }
    }
    cleaned, errors = strip_unsupported_effort(matrix)
    assert len(errors) == 1, errors
    assert "effort" not in cleaned["roles"]["fast"]["candidates"][3]["config"]


def test_empty_and_missing_matrix_are_fine() -> None:
    assert validate_matrix_model_support({}) == []
    assert validate_matrix_model_support({"roles": {}}) == []
    assert validate_matrix_model_support({"roles": None}) == []


def test_non_string_model_is_not_matched() -> None:
    assert model_ignores_effort(None) is None  # type: ignore[arg-type]
    assert model_ignores_effort(42) is None  # type: ignore[arg-type]
    assert model_ignores_effort("") is None


def test_candidate_with_no_model_key_does_not_crash() -> None:
    matrix = {
        "roles": {
            "fast": {
                "description": "d",
                "candidates": [{"provider": "anthropic", "config": {"effort": "high"}}],
            }
        }
    }
    assert validate_matrix_model_support(matrix) == []


# ---------------------------------------------------------------------------
# The reason must carry its evidence, not a vibe
# ---------------------------------------------------------------------------


def test_reason_cites_measured_evidence() -> None:
    reason = model_ignores_effort("claude-haiku-4.5")
    assert reason is not None
    assert "1,438" in reason  # the measured n, not an assertion of belief
    assert "32000" in reason
    assert "20260901-threeknob" in reason


# ---------------------------------------------------------------------------
# Regression guard over the SHIPPED matrices
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "matrix_path",
    sorted(ROUTING_DIR.glob("*.yaml")),
    ids=lambda p: p.name,
)
def test_shipped_matrix_has_no_rejected_effort_keys(matrix_path: Path) -> None:
    """No matrix this bundle ships may carry an inert effort knob.

    This is the mechanised form of the audit: it fails the day someone adds
    ``reasoning_effort`` to a Haiku candidate, instead of the setting sitting
    inert for a wave.
    """
    data = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    errors = validate_matrix_model_support(data)
    assert errors == [], f"{matrix_path.name}: " + "; ".join(errors)
