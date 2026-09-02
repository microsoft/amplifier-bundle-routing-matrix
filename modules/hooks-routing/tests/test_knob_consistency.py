"""Unit tests for knob-consistent routing (the pure layer).

Every test here runs with no provider, no network and no session -- which is
the point of keeping the clamp a pure function. The integration path (resolver,
resolver_class, mount) is covered in test_knob_consistent_routing.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from amplifier_module_hooks_routing.knob_consistency import (
    CANONICAL_EFFORT_KEY,
    CallerContext,
    ClampRecord,
    EscalationState,
    Preset,
    derive_caller_context,
    parse_preset,
    plan_candidates,
    rung_of,
    validate_preset,
)

OPENAI_LADDER = [
    ["gpt-?.?-luna*", "gpt-?.?-mini*"],
    ["gpt-?.?-terra*"],
    ["gpt-?.?-sol*", "gpt-[0-9].[0-9]"],
]

ANTHROPIC_LADDER = [
    ["claude-haiku-*"],
    ["claude-sonnet-*"],
    ["claude-opus-*"],
]


def _preset(**kwargs: Any) -> Preset:
    base: dict[str, Any] = {
        "inherit": "strict",
        "tier_ladder": {"openai": OPENAI_LADDER, "anthropic": ANTHROPIC_LADDER},
    }
    base.update(kwargs)
    return Preset(**base)


def _matrix(preset_block: Any, roles: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": "t",
        "preset": preset_block,
        "roles": roles
        if roles is not None
        else {
            "general": {
                "description": "d",
                "candidates": [{"provider": "openai", "model": "gpt-?.?-terra*"}],
            },
            "fast": {
                "description": "d",
                "candidates": [{"provider": "openai", "model": "gpt-?.?-luna*"}],
            },
        },
    }


# ---------------------------------------------------------------------------
# parse_preset -- the default-off contract
# ---------------------------------------------------------------------------


class TestParsePreset:
    def test_absent_preset_returns_none(self) -> None:
        """No `preset:` key means None, which is what every branch tests."""
        assert parse_preset({"name": "x", "roles": {}}) is None

    def test_non_dict_preset_returns_none(self) -> None:
        assert parse_preset({"preset": "yes"}) is None
        assert parse_preset({"preset": ["a"]}) is None

    def test_none_input_returns_none(self) -> None:
        assert parse_preset(None) is None

    def test_empty_preset_is_inactive(self) -> None:
        """A `preset: {}` block parses but does not change resolution."""
        preset = parse_preset({"preset": {}, "roles": {}})
        assert preset is not None
        assert preset.inherit == "none"
        assert preset.active is False

    def test_full_block_round_trips(self) -> None:
        preset = parse_preset(
            {
                "preset": {
                    "axis": ["quality", "cheap"],
                    "tier_ladder": {"openai": ["gpt-?.?-luna*", "gpt-?.?-sol*"]},
                    "session_scoped": {"openai": {"reasoning_effort": "medium"}},
                    "delegation": {
                        "inherit": "tier-and-effort",
                        "escalate": {
                            "allow_roles": ["reasoning"],
                            "max_uses": 3,
                            "on_exhausted": "error",
                        },
                        "fan_out_max": 3,
                        "delegate_timeout_s": 1550,
                        "on_timeout": "partial",
                        "report_unhonored": False,
                    },
                    "context": {"module": "context-simple"},
                },
                "roles": {},
            }
        )
        assert preset is not None
        assert preset.inherit == "tier-and-effort"
        assert preset.active is True
        assert preset.clamps_tier is True
        assert preset.escalate_allow_roles == ("reasoning",)
        assert preset.escalate_max_uses == 3
        assert preset.escalate_on_exhausted == "error"
        assert preset.report_unhonored is False
        assert preset.axis == ("quality", "cheap")
        assert preset.fan_out_max == 3
        assert preset.delegate_timeout_s == 1550
        assert preset.context == {"module": "context-simple"}
        assert preset.session_scoped == {"openai": {"reasoning_effort": "medium"}}

    def test_bare_string_rung_becomes_one_glob_rung(self) -> None:
        """The design source writes one glob per rung; a list is also allowed."""
        preset = parse_preset(
            {"preset": {"tier_ladder": {"openai": ["a*", ["b*", "c*"]]}}, "roles": {}}
        )
        assert preset is not None
        assert preset.tier_ladder["openai"] == [["a*"], ["b*", "c*"]]


# ---------------------------------------------------------------------------
# validate_preset -- ROUTING-PROPOSAL.md section 2.2
# ---------------------------------------------------------------------------


class TestValidatePreset:
    def test_no_preset_is_always_valid(self) -> None:
        """This function can never reject a matrix that predates the feature."""
        assert validate_preset({"name": "x", "roles": {"general": {}}}) == []

    def test_unknown_inherit_mode_rejected(self) -> None:
        errors = validate_preset(_matrix({"delegation": {"inherit": "maximal"}}))
        assert any("inherit='maximal'" in e for e in errors)

    def test_unknown_on_exhausted_rejected(self) -> None:
        errors = validate_preset(
            _matrix(
                {
                    "tier_ladder": {"openai": OPENAI_LADDER},
                    "delegation": {
                        "inherit": "strict",
                        "escalate": {"on_exhausted": "explode"},
                    },
                }
            )
        )
        assert any("on_exhausted" in e for e in errors)

    def test_ladder_required_for_clamping_modes(self) -> None:
        for mode in ("tier-and-effort", "strict"):
            errors = validate_preset(_matrix({"delegation": {"inherit": mode}}))
            assert any("tier_ladder is required" in e for e in errors), mode

    def test_ladder_not_required_for_effort_mode(self) -> None:
        """`effort` never clamps a tier, so it needs no order."""
        errors = validate_preset(_matrix({"delegation": {"inherit": "effort"}}))
        assert errors == []

    def test_candidate_off_ladder_is_rejected(self) -> None:
        """An unclampable candidate is the original defect in a new hat."""
        errors = validate_preset(
            _matrix(
                {
                    "tier_ladder": {"openai": OPENAI_LADDER},
                    "delegation": {"inherit": "strict"},
                },
                roles={
                    "general": {
                        "description": "d",
                        "candidates": [{"provider": "openai", "model": "o3-pro"}],
                    },
                    "fast": {
                        "description": "d",
                        "candidates": [
                            {"provider": "openai", "model": "gpt-?.?-luna*"}
                        ],
                    },
                },
            )
        )
        assert any("matches 0 rungs" in e for e in errors)

    def test_candidate_provider_without_ladder_is_rejected(self) -> None:
        errors = validate_preset(
            _matrix(
                {
                    "tier_ladder": {"openai": OPENAI_LADDER},
                    "delegation": {"inherit": "strict"},
                },
                roles={
                    "general": {
                        "description": "d",
                        "candidates": [
                            {"provider": "gemini", "model": "gemini-3-pro-preview"}
                        ],
                    },
                    "fast": {
                        "description": "d",
                        "candidates": [
                            {"provider": "openai", "model": "gpt-?.?-luna*"}
                        ],
                    },
                },
            )
        )
        assert any("has no preset.tier_ladder entry" in e for e in errors)

    def test_allow_roles_must_be_real_roles(self) -> None:
        errors = validate_preset(
            _matrix(
                {
                    "tier_ladder": {"openai": OPENAI_LADDER},
                    "delegation": {
                        "inherit": "tier-and-effort",
                        "escalate": {"allow_roles": ["resaoning"]},
                    },
                }
            )
        )
        assert any("'resaoning' is not a role" in e for e in errors)

    def test_fan_out_cap_without_timeout_rejected(self) -> None:
        """A cap without a timeout converts a straggler into a queue."""
        errors = validate_preset(
            _matrix({"delegation": {"inherit": "effort", "fan_out_max": 3}})
        )
        assert any("delegate_timeout_s must be set" in e for e in errors)

    def test_non_canonical_effort_key_rejected(self) -> None:
        """ROUTING-PROPOSAL.md's `effort:` for anthropic loses to this repo's
        canonical spelling, which its own hygiene test already enforces."""
        errors = validate_preset(
            _matrix(
                {
                    "effort_keys": {"anthropic": "effort"},
                    "delegation": {"inherit": "effort"},
                }
            )
        )
        assert any("canonical effort key" in e for e in errors)

    def test_effort_on_effortless_model_rejected(self) -> None:
        """Measured: claude-haiku-4-5 carries no effort field at all."""
        errors = validate_preset(
            _matrix(
                {"delegation": {"inherit": "effort"}},
                roles={
                    "general": {
                        "description": "d",
                        "candidates": [
                            {
                                "provider": "anthropic",
                                "model": "claude-haiku-*",
                                "config": {CANONICAL_EFFORT_KEY: "medium"},
                            }
                        ],
                    },
                    "fast": {"description": "d", "candidates": []},
                },
            )
        )
        assert any("accepts no effort parameter" in e for e in errors)

    def test_session_scoped_allow_list_enforced(self) -> None:
        errors = validate_preset(
            _matrix(
                {
                    "session_scoped": {"openai": {"temperature": 0.3}},
                    "delegation": {"inherit": "effort"},
                }
            )
        )
        assert any("not on the declared invalidator allow-list" in e for e in errors)

    def test_shipped_knob_consistent_matrix_validates(self) -> None:
        """The one matrix in this repo that carries a preset must pass."""
        import yaml
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[3]
            / "routing"
            / "openai-knob-consistent.yaml"
        )
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert validate_preset(data) == []


# ---------------------------------------------------------------------------
# rung_of
# ---------------------------------------------------------------------------


class TestRungOf:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("gpt-5.6-luna", 0),
            ("gpt-5.6-terra", 1),
            ("gpt-5.6-sol", 2),
            ("gpt-?.?-terra*", 1),  # a matrix glob, not a concrete id
            ("gpt-[0-9].[0-9]", 2),  # matches only by exact-string equality
            ("o3-pro", None),  # genuinely off-ladder
        ],
    )
    def test_rungs(self, model: str, expected: int | None) -> None:
        assert rung_of(model, OPENAI_LADDER) == expected

    def test_empty_ladder_is_none_not_zero(self) -> None:
        """Off-ladder must never be silently treated as the cheap rung."""
        assert rung_of("gpt-5.6-sol", None) is None
        assert rung_of("gpt-5.6-sol", []) is None

    def test_case_insensitive(self) -> None:
        assert rung_of("GPT-5.6-TERRA", OPENAI_LADDER) == 1


# ---------------------------------------------------------------------------
# plan_candidates -- the feature, mode by mode
# ---------------------------------------------------------------------------

TERRA_CALLER = CallerContext(
    family="openai", model="gpt-5.6-terra", effort="medium", provider_key="terra"
)
SOL_CALLER = CallerContext(
    family="openai", model="gpt-5.6-sol", effort="xhigh", provider_key="sol"
)
REASONING_CANDIDATES = [
    {
        "provider": "openai",
        "model": "gpt-?.?-sol*",
        "config": {CANONICAL_EFFORT_KEY: "xhigh"},
    },
    {
        "provider": "openai",
        "model": "gpt-[0-9].[0-9]",
        "config": {CANONICAL_EFFORT_KEY: "xhigh"},
    },
]


class TestPlanCandidatesDefaultOff:
    def test_no_preset_returns_input_identically(self) -> None:
        """Identity, not equality: the default path cannot even copy the list."""
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, TERRA_CALLER, None, None
        )
        assert planned is REASONING_CANDIDATES
        assert record is None

    def test_inherit_none_returns_input_identically(self) -> None:
        planned, record = plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            TERRA_CALLER,
            _preset(inherit="none"),
            None,
        )
        assert planned is REASONING_CANDIDATES
        assert record is None

    def test_unknown_caller_leaves_candidates_alone(self) -> None:
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, None, _preset(), EscalationState()
        )
        assert planned is REASONING_CANDIDATES
        assert record is not None
        assert record.honored is False
        assert "caller context unavailable" in record.reason

    def test_report_unhonored_false_suppresses_the_record(self) -> None:
        planned, record = plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            None,
            _preset(report_unhonored=False),
            None,
        )
        assert planned is REASONING_CANDIDATES
        assert record is None

    def test_caller_off_ladder_is_reported_not_guessed(self) -> None:
        off = CallerContext(family="openai", model="o3-pro", effort="high")
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, off, _preset(), EscalationState()
        )
        assert planned is REASONING_CANDIDATES
        assert record is not None
        assert record.honored is False
        assert "not on the" in record.reason


class TestPlanCandidatesEffortMode:
    def test_model_kept_effort_replaced(self) -> None:
        planned, record = plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            TERRA_CALLER,
            _preset(inherit="effort"),
            None,
        )
        assert [c["model"] for c in planned] == [
            "gpt-?.?-sol*",
            "gpt-[0-9].[0-9]",
        ]
        assert planned[0]["config"][CANONICAL_EFFORT_KEY] == "medium"
        assert record is not None and record.honored is True
        assert record.granted_effort == "medium"
        assert record.requested_effort == "xhigh"

    def test_inputs_are_not_mutated(self) -> None:
        before = [dict(c, config=dict(c["config"])) for c in REASONING_CANDIDATES]
        plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            TERRA_CALLER,
            _preset(inherit="effort"),
            None,
        )
        assert REASONING_CANDIDATES == before

    def test_effort_unsupported_target_drops_the_key_and_says_so(self) -> None:
        haiku = [{"provider": "anthropic", "model": "claude-haiku-*"}]
        caller = CallerContext(
            family="anthropic", model="claude-sonnet-5", effort="medium"
        )
        planned, record = plan_candidates(
            "fast", haiku, caller, _preset(inherit="effort"), None
        )
        assert CANONICAL_EFFORT_KEY not in (planned[0].get("config") or {})
        assert record is not None
        assert record.honored is False
        assert record.reason == "effort unsupported on target model"

    def test_caller_without_effort_leaves_candidate_effort_alone(self) -> None:
        caller = CallerContext(family="openai", model="gpt-5.6-terra", effort=None)
        planned, _ = plan_candidates(
            "reasoning", REASONING_CANDIDATES, caller, _preset(inherit="effort"), None
        )
        assert planned[0]["config"][CANONICAL_EFFORT_KEY] == "xhigh"


class TestPlanCandidatesStrict:
    def test_the_defect_fixed_sol_becomes_terra(self) -> None:
        """The measured case: reasoning -> sol@xhigh under a terra@medium root."""
        planned, record = plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            TERRA_CALLER,
            _preset(inherit="strict"),
            EscalationState(),
        )
        assert len(planned) == 1
        assert planned[0]["model"] == "gpt-?.?-terra*"
        assert planned[0]["config"][CANONICAL_EFFORT_KEY] == "medium"
        assert record is not None
        assert record.honored is True
        assert record.requested_model == "gpt-?.?-sol*"
        assert record.granted_model == "gpt-?.?-terra*"
        assert "substituted the ladder rung" in record.reason

    def test_candidate_already_below_ceiling_is_kept(self) -> None:
        fast = [
            {"provider": "openai", "model": "gpt-?.?-luna*"},
            {"provider": "openai", "model": "gpt-?.?-mini*"},
        ]
        planned, record = plan_candidates(
            "fast", fast, TERRA_CALLER, _preset(), EscalationState()
        )
        assert [c["model"] for c in planned] == ["gpt-?.?-luna*", "gpt-?.?-mini*"]
        assert planned[0]["config"][CANONICAL_EFFORT_KEY] == "medium"
        assert record is not None and record.honored is True

    def test_a_sol_caller_is_not_clamped_at_all(self) -> None:
        """Inheritance is a ceiling, not a demotion: a top-rung caller keeps
        the top-rung candidate."""
        planned, record = plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            SOL_CALLER,
            _preset(),
            EscalationState(),
        )
        assert planned[0]["model"] == "gpt-?.?-sol*"
        assert planned[0]["config"][CANONICAL_EFFORT_KEY] == "xhigh"
        assert record is not None and record.honored is True

    def test_mixed_ladder_keeps_matrix_order_among_survivors(self) -> None:
        candidates = [
            {"provider": "openai", "model": "gpt-?.?-sol*"},
            {"provider": "openai", "model": "gpt-?.?-terra*"},
            {"provider": "openai", "model": "gpt-?.?-luna*"},
        ]
        planned, _ = plan_candidates(
            "general", candidates, TERRA_CALLER, _preset(), EscalationState()
        )
        assert [c["model"] for c in planned] == ["gpt-?.?-terra*", "gpt-?.?-luna*"]

    def test_cross_family_clamp_uses_the_rung_ordinal(self) -> None:
        """A sonnet (rung 1) caller facing an openai candidate list gets the
        openai rung-1 model, not the openai flagship."""
        caller = CallerContext(
            family="anthropic", model="claude-sonnet-5", effort="medium"
        )
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, caller, _preset(), EscalationState()
        )
        assert planned[0]["model"] == "gpt-?.?-terra*"
        assert record is not None and record.honored is True

    def test_strict_denies_escalation_even_for_allowed_roles(self) -> None:
        preset = _preset(
            inherit="strict", escalate_allow_roles=("reasoning",), escalate_max_uses=3
        )
        state = EscalationState(max_uses=3)
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, TERRA_CALLER, preset, state
        )
        assert planned[0]["model"] == "gpt-?.?-terra*"
        assert state.used == 0
        assert record is not None and record.escalated is False

    def test_substitute_only_never_falls_open_to_the_original(self) -> None:
        """If the substitute glob does not resolve, the child must fall through
        to the session default (= the caller's own model), NOT back to sol."""
        planned, _ = plan_candidates(
            "reasoning",
            REASONING_CANDIDATES,
            TERRA_CALLER,
            _preset(),
            EscalationState(),
        )
        assert all("sol" not in c["model"] for c in planned)

    def test_no_ladder_for_candidate_family_is_reported_not_clamped(self) -> None:
        preset = _preset(tier_ladder={"anthropic": ANTHROPIC_LADDER})
        caller = CallerContext(
            family="anthropic", model="claude-sonnet-5", effort="medium"
        )
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, caller, preset, EscalationState()
        )
        assert planned is REASONING_CANDIDATES
        assert record is not None and record.honored is False
        assert "no 'openai' ladder to substitute from" in record.reason


class TestPlanCandidatesEscalation:
    def _preset_with_escalation(self, max_uses: int = 2) -> Preset:
        return _preset(
            inherit="tier-and-effort",
            escalate_allow_roles=("reasoning",),
            escalate_max_uses=max_uses,
        )

    def test_allowed_role_escalates_and_keeps_its_own_effort(self) -> None:
        preset = self._preset_with_escalation()
        state = EscalationState(max_uses=2)
        planned, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, TERRA_CALLER, preset, state
        )
        assert planned[0]["model"] == "gpt-?.?-sol*"
        # Escalation is the documented exception to "inherited effort wins".
        assert planned[0]["config"][CANONICAL_EFFORT_KEY] == "xhigh"
        assert state.used == 1
        assert record is not None
        assert record.escalated is True
        assert record.escalations_remaining == 1

    def test_budget_exhausts_then_clamps(self) -> None:
        preset = self._preset_with_escalation(max_uses=1)
        state = EscalationState(max_uses=1)
        first, _ = plan_candidates(
            "reasoning", REASONING_CANDIDATES, TERRA_CALLER, preset, state
        )
        second, record = plan_candidates(
            "reasoning", REASONING_CANDIDATES, TERRA_CALLER, preset, state
        )
        assert first[0]["model"] == "gpt-?.?-sol*"
        assert second[0]["model"] == "gpt-?.?-terra*"
        assert state.remaining == 0
        assert record is not None and record.escalated is False

    def test_role_not_on_allow_list_never_escalates(self) -> None:
        preset = self._preset_with_escalation()
        state = EscalationState(max_uses=2)
        planned, _ = plan_candidates(
            "creative",
            [{"provider": "openai", "model": "gpt-?.?-sol*"}],
            TERRA_CALLER,
            preset,
            state,
        )
        assert planned[0]["model"] == "gpt-?.?-terra*"
        assert state.used == 0

    def test_escalation_not_consumed_when_candidate_is_already_below(self) -> None:
        """A budget spent on a candidate that needed no escalation is a budget
        silently stolen from one that does."""
        preset = self._preset_with_escalation()
        state = EscalationState(max_uses=2)
        plan_candidates(
            "reasoning",
            [{"provider": "openai", "model": "gpt-?.?-luna*"}],
            TERRA_CALLER,
            preset,
            state,
        )
        assert state.used == 0

    def test_escalation_state_arithmetic(self) -> None:
        state = EscalationState(max_uses=2)
        assert state.remaining == 2
        state.consume()
        state.consume()
        state.consume()
        assert state.remaining == 0


# ---------------------------------------------------------------------------
# derive_caller_context -- the single-repo mechanism
# ---------------------------------------------------------------------------


def _coordinator_with(providers: Any) -> MagicMock:
    coordinator = MagicMock()
    coordinator.config = {"providers": providers}
    return coordinator


class TestDeriveCallerContext:
    def test_reads_the_active_provider_spec(self) -> None:
        coordinator = _coordinator_with(
            [
                {
                    "module": "provider-openai",
                    "id": "sol",
                    "config": {"priority": 10, "default_model": "gpt-5.6-sol"},
                },
                {
                    "module": "provider-openai",
                    "id": "terra",
                    "config": {
                        "priority": 0,
                        "default_model": "gpt-5.6-terra",
                        CANONICAL_EFFORT_KEY: "medium",
                    },
                },
            ]
        )
        caller = derive_caller_context(coordinator, _preset())
        assert caller is not None
        assert caller.family == "openai"
        assert caller.model == "gpt-5.6-terra"
        assert caller.effort == "medium"
        assert caller.provider_key == "terra"

    def test_missing_priority_does_not_win_over_an_explicit_zero(self) -> None:
        coordinator = _coordinator_with(
            [
                {
                    "module": "provider-anthropic",
                    "config": {"default_model": "claude-opus-5"},
                },
                {
                    "module": "provider-openai",
                    "config": {"priority": 0, "default_model": "gpt-5.6-terra"},
                },
            ]
        )
        caller = derive_caller_context(coordinator, _preset())
        assert caller is not None and caller.model == "gpt-5.6-terra"

    def test_no_default_model_returns_none(self) -> None:
        coordinator = _coordinator_with(
            [{"module": "provider-openai", "config": {"priority": 0}}]
        )
        assert derive_caller_context(coordinator, _preset()) is None

    @pytest.mark.parametrize(
        "config", [None, {}, {"providers": []}, {"providers": "nope"}]
    )
    def test_degrades_to_none_never_raises(self, config: Any) -> None:
        coordinator = MagicMock()
        coordinator.config = config
        assert derive_caller_context(coordinator, _preset()) is None

    def test_bare_object_without_config_returns_none(self) -> None:
        assert derive_caller_context(object(), _preset()) is None

    def test_effort_absent_is_none_not_empty_string(self) -> None:
        coordinator = _coordinator_with(
            [
                {
                    "module": "provider-openai",
                    "config": {"priority": 0, "default_model": "gpt-5.6-terra"},
                }
            ]
        )
        caller = derive_caller_context(coordinator, _preset())
        assert caller is not None and caller.effort is None


# ---------------------------------------------------------------------------
# ClampRecord shape -- this is a wire contract for the event log
# ---------------------------------------------------------------------------


class TestClampRecord:
    def test_to_dict_shape(self) -> None:
        record = ClampRecord(
            role="reasoning",
            mode="strict",
            honored=True,
            reason="because",
            caller={"family": "openai"},
            requested_model="gpt-?.?-sol*",
            requested_effort="xhigh",
            granted_model="gpt-?.?-terra*",
            granted_effort="medium",
            escalations_remaining=2,
        )
        payload = record.to_dict()
        assert payload["role"] == "reasoning"
        assert payload["requested"] == {"model": "gpt-?.?-sol*", "effort": "xhigh"}
        assert payload["granted"] == {"model": "gpt-?.?-terra*", "effort": "medium"}
        assert payload["escalations_remaining"] == 2
        assert payload["honored"] is True
