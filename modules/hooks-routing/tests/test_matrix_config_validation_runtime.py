"""Runtime tests for validate_matrix_config().

Covers the "closed on values, open on keys" contract: a candidate's
``config:`` value is only ever flagged when the provider explicitly
declares that key as a ``choice`` field with a non-empty ``choices`` list.
Any key the provider doesn't declare (the common case -- providers consume
many more config keys than they declare as ConfigFields) must pass through
silently, no matter what value it carries.
"""

from __future__ import annotations

from typing import Any

from amplifier_module_hooks_routing.matrix_loader import validate_matrix_config

# ---------------------------------------------------------------------------
# Fakes -- mirror the shape of amplifier_core's ProviderInfo/ConfigField
# (attributes .id / .field_type / .choices) without importing amplifier_core.
# ---------------------------------------------------------------------------


class _FakeField:
    def __init__(
        self, id: str, field_type: str = "text", choices: list[str] | None = None
    ) -> None:
        self.id = id
        self.field_type = field_type
        self.choices = choices


class _FakeInfo:
    def __init__(self, config_fields: list[_FakeField]) -> None:
        self.config_fields = config_fields


class _FakeProvider:
    """Fake provider exposing get_info() like a real amplifier_core provider."""

    def __init__(
        self, config_fields: list[_FakeField], raise_on_get_info: bool = False
    ) -> None:
        self._config_fields = config_fields
        self._raise = raise_on_get_info

    def get_info(self) -> _FakeInfo:
        if self._raise:
            raise RuntimeError("boom")
        return _FakeInfo(self._config_fields)


# Mirrors provider-anthropic's declared reasoning_effort choice field, plus a
# second fake choice field ("output_mode") so mixed valid/invalid scenarios
# can be tested without conflating two errors on the same key.
ANTHROPIC_FIELDS = [
    _FakeField(
        "reasoning_effort",
        field_type="choice",
        choices=["low", "medium", "high", "xhigh", "max"],
    ),
    _FakeField("output_mode", field_type="choice", choices=["compact", "verbose"]),
    _FakeField("api_key", field_type="secret"),
]


def _matrix(config: dict[str, Any], provider: str = "anthropic") -> dict[str, Any]:
    """Build a minimal matrix dict with a single candidate carrying *config*."""
    return {
        "roles": {
            "general": {
                "description": "General purpose",
                "candidates": [
                    {
                        "provider": provider,
                        "model": "claude-sonnet-4",
                        "config": config,
                    },
                ],
            },
        },
    }


def test_invalid_reasoning_effort_value_reported() -> None:
    providers = {"anthropic": _FakeProvider(ANTHROPIC_FIELDS)}
    errors = validate_matrix_config(
        _matrix({"reasoning_effort": "extra_high"}), providers
    )
    assert len(errors) == 1
    assert "extra_high" in errors[0]
    assert "xhigh" in errors[0]


def test_valid_reasoning_effort_value_passes() -> None:
    providers = {"anthropic": _FakeProvider(ANTHROPIC_FIELDS)}
    errors = validate_matrix_config(_matrix({"reasoning_effort": "xhigh"}), providers)
    assert errors == []


def test_undeclared_keys_pass_through_silently() -> None:
    """OPEN-KEY RULE: undeclared provider knobs must never be flagged.

    These are real provider-consumed keys (thinking_budget_tokens,
    throttle_threshold, temperature) that provider-anthropic never declares
    as ConfigFields -- plus a hypothetical future knob. None may error.
    """
    providers = {"anthropic": _FakeProvider(ANTHROPIC_FIELDS)}
    config = {
        "thinking_budget_tokens": 32000,
        "throttle_threshold": 0.8,
        "temperature": 0.5,
        "some_future_knob": "anything",
    }
    errors = validate_matrix_config(_matrix(config), providers)
    assert errors == []


def test_mixed_valid_invalid_and_undeclared_keys() -> None:
    """One valid declared key + one invalid declared key + two undeclared keys."""
    providers = {"anthropic": _FakeProvider(ANTHROPIC_FIELDS)}
    config = {
        "reasoning_effort": "high",  # valid
        "output_mode": "bogus",  # invalid
        "temperature": 0.5,  # undeclared
        "some_future_knob": "anything",  # undeclared
    }
    errors = validate_matrix_config(_matrix(config), providers)
    assert len(errors) == 1
    assert "output_mode" in errors[0]


def test_providers_none_returns_no_errors() -> None:
    errors = validate_matrix_config(_matrix({"reasoning_effort": "extra_high"}), None)
    assert errors == []


def test_provider_not_found_returns_no_errors() -> None:
    """Provider not installed -- we cannot and must not judge it."""
    providers = {"openai": _FakeProvider(ANTHROPIC_FIELDS)}
    errors = validate_matrix_config(
        _matrix({"reasoning_effort": "extra_high"}, provider="anthropic"), providers
    )
    assert errors == []


def test_get_info_raising_returns_no_errors() -> None:
    """A provider whose get_info() raises must never break validation."""
    providers = {"anthropic": _FakeProvider(ANTHROPIC_FIELDS, raise_on_get_info=True)}
    errors = validate_matrix_config(
        _matrix({"reasoning_effort": "extra_high"}), providers
    )
    assert errors == []


def test_base_keyword_candidate_does_not_crash() -> None:
    """The literal 'base' string candidate (valid in overrides) is skipped."""
    providers = {"anthropic": _FakeProvider(ANTHROPIC_FIELDS)}
    matrix = {
        "roles": {
            "general": {
                "description": "General purpose",
                "candidates": ["base"],
            },
        },
    }
    errors = validate_matrix_config(matrix, providers)
    assert errors == []
