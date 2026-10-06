"""Synthetic offline contracts; no credentials, live catalogs, inference or DTU.

The attribute-object case exercises Core's pydantic ModelInfo access contract
without requiring Core in ordinary offline CI. Pre-import amplifier_core.models
in the root-owned pytest process to additionally select the actual ModelInfo case.
"""

import asyncio
import copy
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent))
import candidates
import candidates_cli

MASKS = {
    "openai/sol/text": "gpt-*-sol",
    "openai/luna/text": "gpt-*-luna",
    "gemini/flash/text": "gemini-*-flash",
    "claude/haiku/text": "claude-haiku-*",
}
INCUMBENT = "gpt-6.1-sol"
LOSER = "gpt-6.2-luna"
OLD = "gemini-2.5-flash"
NEW = "gemini-3.5-flash"
ADDED = "claude-haiku-5.5"


class Catalog:
    def __init__(self, models):
        self.models = models
        self.calls = 0

    @property
    def config(self):
        raise AssertionError("discovery must not inspect configuration")

    async def list_models(self):
        self.calls += 1
        if isinstance(self.models, Exception):
            raise self.models
        return self.models


class AttributeModel:
    """Non-dictionary Core ModelInfo-shaped object; iteration is not supported."""

    def __init__(self, model_id, capabilities):
        self.id = model_id
        self.capabilities = capabilities

    def __iter__(self):
        raise AssertionError("ModelInfo must be read via attributes")


def discover(models, masks=None, required=("tools",), provenance="live", binding="b1"):
    return asyncio.run(
        candidates.discover(
            Catalog(models),
            binding,
            masks if masks is not None else MASKS,
            required,
            provenance,
        )
    )


def menu(*ids):
    return [{"id": model_id, "capabilities": ["tools"]} for model_id in ids]


def conditions(*ids):
    """Completely fabricated pinned identities, not real evidence/configuration."""
    return {
        "sources": {
            name: f"synthetic-{name}-revision-1"
            for name in (
                "cli",
                "core",
                "foundation",
                "routing",
                "provider",
                "evaluation",
            )
        },
        "task": "synthetic-task-and-fixtures-1",
        "grader": "synthetic-grader-1",
        "runtime": "synthetic-runtime-1",
        "root": "synthetic-fixed-root-controller-protocol-1",
        "tools": {"terminal": "synthetic-tool-1"},
        "native_settings": {"reasoning_effort": "high", "context_limit": 8192},
        "budgets": {"calls": 3, "seconds": 300, "tokens": 1024},
        "model_revisions": {
            model_id: f"synthetic-delivered-{model_id}-1" for model_id in ids
        },
        "binding_ref": "b1",
    }


def receipt(model_id, assigned, receipt_id=None, *, outcome="failure", score=0):
    return {
        "version": "anchors-reuse/v1",
        "receipt_id": receipt_id or f"synthetic-receipt-{model_id}",
        "model_id": model_id,
        "model_revision": assigned["model_revisions"].get(model_id),
        "binding_ref": assigned["binding_ref"],
        "assigned_conditions": copy.deepcopy(assigned),
        "identity_verified": True,
        "qualified": True,
        "measurement_valid": True,
        "artifacts_retained": True,
        "references_available": True,
        "accounting_complete": True,
        "outcome": outcome,
        "score": score,
    }


def test_adjacent_two_cycle_refresh_retains_loser_and_only_changes_subset():
    first = discover(menu(INCUMBENT, LOSER, OLD))
    assigned1 = conditions(INCUMBENT, LOSER, OLD)
    first_plan = candidates.plan_refresh(first, [], assigned1, INCUMBENT)
    assert first_plan["fresh_model_ids"] == [INCUMBENT, OLD, LOSER]
    receipts = [
        receipt(INCUMBENT, assigned1, "cycle1-incumbent", outcome="success", score=1),
        receipt(LOSER, assigned1, "cycle1-loser", outcome="failure", score=0),
        receipt(OLD, assigned1, "cycle1-old", outcome="timeout", score=None),
    ]
    saved = copy.deepcopy(receipts)
    second = discover(menu(INCUMBENT, LOSER, OLD, NEW, ADDED))
    assigned2 = conditions(INCUMBENT, LOSER, NEW, ADDED)
    report = candidates.plan_refresh(second, receipts, assigned2, INCUMBENT)
    assert {model.id for model in second.candidates} == {INCUMBENT, LOSER, NEW, ADDED}
    assert report["reuse_ids"] == ["cycle1-incumbent", "cycle1-loser"]
    assert report["fresh_model_ids"] == [INCUMBENT, ADDED, NEW]
    assert report["dispositions"]["cycle1-old"] == "historical"
    assert report["execution_supported"] is False
    assert receipts == saved  # No relabeling old outcomes/grades/conditions as fresh.

    # Same IDs but changed delivered generation are NOT unchanged treatment.
    revised = copy.deepcopy(assigned2)
    revised["model_revisions"][LOSER] = "synthetic-delivered-luna-generation-2"
    changed = candidates.plan_refresh(second, receipts, revised, INCUMBENT)
    assert changed["dispositions"]["cycle1-loser"] == "historical"
    assert LOSER in changed["fresh_model_ids"]

    # A source change forces current cells fresh while retired IDs stay historical.
    revised = copy.deepcopy(assigned2)
    revised["sources"]["routing"] = "synthetic-routing-revision-2"
    changed = candidates.plan_refresh(second, receipts, revised, INCUMBENT)
    assert changed["reuse_ids"] == []
    assert changed["dispositions"] == {
        "cycle1-incumbent": "rerun",
        "cycle1-loser": "rerun",
        "cycle1-old": "historical",
    }
    assert set(changed["fresh_model_ids"]) == {INCUMBENT, LOSER, NEW, ADDED}


def test_changed_grader_regrades_all_current_arms_not_candidate_execution():
    snapshot = discover(menu(INCUMBENT, LOSER))
    before = conditions(INCUMBENT, LOSER)
    receipts = [receipt(model_id, before) for model_id in (INCUMBENT, LOSER)]
    after = copy.deepcopy(before)
    after["grader"] = "synthetic-grader-2"
    report = candidates.plan_refresh(snapshot, receipts, after, INCUMBENT)
    assert report["reuse_ids"] == []
    assert set(report["regrade_ids"]) == {item["receipt_id"] for item in receipts}
    assert report["fresh_model_ids"] == [INCUMBENT]  # Mandatory contemporaneous anchor.
    assert all(value == "regrade" for value in report["dispositions"].values())
    assert all(
        item["assigned_conditions"]["grader"] == before["grader"] for item in receipts
    )
    receipts[1]["artifacts_retained"] = False
    report = candidates.plan_refresh(snapshot, receipts, after, INCUMBENT)
    assert report["dispositions"][receipts[1]["receipt_id"]] == "rerun"
    assert report["fresh_model_ids"] == [INCUMBENT, LOSER]


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout", "unknown"])
@pytest.mark.parametrize("score", [None, 0, -1, 1])
def test_scores_and_outcomes_never_filter_reuse(outcome, score):
    assigned = conditions(LOSER)
    item = receipt(LOSER, assigned, outcome=outcome, score=score)
    assert candidates.reuse_disposition(item, assigned) == "exact_comparable"
    assert candidates.validate_receipt(item)["score"] == score


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("task", "synthetic-task-and-fixtures-2"),
        ("runtime", "synthetic-runtime-2"),
        ("root", "synthetic-root-2"),
        ("tools", {"terminal": "synthetic-tool-2"}),
        ("native_settings", {"reasoning_effort": "low"}),
        ("budgets", {"calls": 2, "seconds": 300, "tokens": 1024}),
    ],
)
def test_each_changed_assignment_requires_rerun(field, replacement):
    before = conditions(LOSER)
    after = copy.deepcopy(before)
    after[field] = replacement
    assert candidates.reuse_disposition(receipt(LOSER, before), after) == "rerun"


@pytest.mark.parametrize("field", ["model_revision", "binding_ref"])
def test_missing_or_changed_delivered_identity_fails_reuse(field):
    assigned = conditions(LOSER)
    item = receipt(LOSER, assigned)
    item[field] = None
    assert candidates.reuse_disposition(item, assigned) == "historical"
    item[field] = "synthetic-wrong-identity"
    assert candidates.reuse_disposition(item, assigned) == "historical"


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(binding_ref=None),
        lambda value: value.update(binding_ref="synthetic-rebound-binding"),
        lambda value: value["model_revisions"].clear(),
        lambda value: value["model_revisions"].update({LOSER: None}),
        lambda value: value.update(root=None),
        lambda value: value["sources"].update(core=None),
        lambda value: value["tools"].update(terminal=None),
        lambda value: value["budgets"].update(tokens=None),
    ],
)
def test_unknown_assignment_identity_is_not_exact_comparable(change):
    assigned = conditions(LOSER)
    item = receipt(LOSER, assigned)
    change(assigned)
    assert candidates.reuse_disposition(item, assigned) == "historical"


def test_all_five_dispositions_and_no_best_attempt_selection():
    assigned = conditions(LOSER, INCUMBENT)
    item = receipt(LOSER, assigned)
    item["measurement_valid"] = False
    assert candidates.reuse_disposition(item, assigned) == "accounting_only"
    item["accounting_complete"] = False
    assert candidates.reuse_disposition(item, assigned) == "rerun"
    good = receipt(LOSER, assigned, "good-assertion")
    report = candidates.plan_refresh(
        discover(menu(LOSER, INCUMBENT)), [item, good], assigned, INCUMBENT
    )
    assert report["reuse_ids"] == ["good-assertion"]
    assert report["dispositions"][item["receipt_id"]] == "rerun"
    assert report["fresh_model_ids"] == [INCUMBENT, LOSER]
    with pytest.raises(ValueError, match="duplicate"):
        candidates.plan_refresh(
            discover(menu(LOSER)), [good, good], assigned, INCUMBENT
        )


def test_projection_excludes_treatment_not_fixed_native_budget_or_grader():
    assigned = conditions(LOSER)
    projected = candidates.assigned_projection(assigned)
    assert set(projected) == set(candidates.PROJECTION_FIELDS)
    assert "model_revisions" not in projected and "binding_ref" not in projected
    projected["native_settings"]["reasoning_effort"] = "low"
    assert assigned["native_settings"]["reasoning_effort"] == "high"


def test_numeric_versions_deterministic_tiers_modalities_and_exact_ids():
    models = [
        AttributeModel("gpt-6.9-sol", ["tools"]),
        AttributeModel("gpt-6.10-sol", ["tools"]),
        AttributeModel("gpt-10-sol", ["tools"]),
        AttributeModel("gpt-6.10-sol-fast", ["tools"]),
        AttributeModel("gpt-6.9-sol", ["tools"]),  # Identical duplicate is harmless.
        AttributeModel("gpt-6.8-sol", ["vision", "tools"]),
        AttributeModel("gpt-6.9-sol", ["tools"]),
        AttributeModel("gpt-20-astra", ["tools"]),
        AttributeModel("gpt-6-luna", ["tools"]),
        AttributeModel("claude-sonnet-5-9", ["tools"]),
        AttributeModel("claude-sonnet-5-10", ["tools"]),
        AttributeModel("claude-3-7-sonnet-20250219", ["tools"]),
    ]
    masks = {"openai": "gpt-*", "sonnet": "claude-*sonnet*"}
    first = discover(models, masks)
    second = discover(list(reversed(models)), masks)
    assert first == second
    assert {candidate.id for candidate in first.candidates} == {
        "gpt-10-sol",
        "gpt-6.10-sol-fast",
        "gpt-6.8-sol",  # Actual vision modality is not erased by a newer text menu.
        "gpt-6-luna",
        "gpt-20-astra",
        "claude-sonnet-5-10",
    }
    assert all(candidate.latest is True for candidate in first.candidates)
    assert first.freshness == "bounded_live"
    assert first.binding_ref == "b1"
    with pytest.raises(FrozenInstanceError):
        first.binding_ref = "other"
    with pytest.raises(FrozenInstanceError):
        first.candidates[0].id = "other"
    assert "b1" not in repr(first)
    assert candidates.Snapshot.from_dict(first.to_dict()) == first


def test_preview_ga_peers_do_not_keep_nonwinning_history():
    models = menu(
        "gemini-2.5-pro-preview",
        "gemini-3-pro-preview",
        "gemini-3-pro-preview-20261001",
        "gemini-3-pro",
    )
    result = discover(models, {"gemini/pro/text": "gemini-*-pro*"})
    assert [model.id for model in result.candidates] == ["gemini-3-pro"]
    models.extend(menu("gemini-3.1-pro-preview"))
    result = discover(models, {"gemini/pro/text": "gemini-*-pro*"})
    assert [model.id for model in result.candidates] == ["gemini-3.1-pro-preview"]


def test_date_suffix_does_not_outrank_new_generation_and_alias_is_unknown():
    result = discover(
        menu("gpt-6.1-sol-20261001", "gpt-6.2-sol", "gpt-latest-sol"),
        {"sol": "gpt-*-sol*"},
    )
    assert {candidate.id for candidate in result.candidates} == {
        "gpt-6.2-sol",
        "gpt-latest-sol",
    }
    assert (
        next(
            candidate.latest
            for candidate in result.candidates
            if candidate.id == "gpt-latest-sol"
        )
        is None
    )


def test_required_capabilities_are_actual_not_name_inference():
    result = discover(
        [
            {"id": "gemini-9-pro-image", "capabilities": ["tools"]},
            {"id": "gemini-2.5-pro-image", "capabilities": ["vision", "tools"]},
            {"id": "gemini-3-pro-image"},
        ],
        {"gemini/pro/vision": "gemini-*-pro-image"},
        required=("vision", "tools"),
    )
    assert [candidate.id for candidate in result.candidates] == ["gemini-2.5-pro-image"]
    result = discover(
        menu("gemini-9-pro-image"), {"image": "gemini-*"}, ("image_generation",)
    )
    assert result.candidates == ()
    assert result.freshness == "unknown"


@pytest.mark.parametrize("provenance", ["fallback", "manual", "failed"])
def test_nonlive_including_copilot_chatgpt_fallback_never_claims_latest(provenance):
    provider = Catalog(menu(INCUMBENT, LOSER))
    result = asyncio.run(
        candidates.discover(provider, "b1", MASKS, ("tools",), provenance)
    )
    assert result.provenance == provenance
    assert result.freshness == "unknown"
    assert all(candidate.latest is None for candidate in result.candidates)
    assert provider.calls == (0 if provenance == "failed" else 1)
    report = candidates.plan_refresh(
        result, [receipt(LOSER, conditions(LOSER))], conditions(LOSER), INCUMBENT
    )
    assert report["reuse_ids"] == []
    assert set(report["dispositions"].values()) == {"historical"}


def test_empty_azure_discovery_and_missing_binding_remain_unknown():
    result = discover([], {"azure/deployment/text": "deployment-*"})
    assert result.reason == "empty_catalog"
    assert result.freshness == "unknown"
    result = discover(menu(INCUMBENT), binding=None)
    assert result.reason == "binding_unknown"
    assert result.candidates[0].latest is None


def test_selected_object_only_once_exception_redaction_and_cancellation():
    provider = Catalog(menu(INCUMBENT))
    result = asyncio.run(candidates.discover(provider, "b1", MASKS, ("tools",), "live"))
    assert provider.calls == 1
    assert result.binding_ref == "b1"
    failed = discover(RuntimeError("fabricated-private-provider-config"))
    assert failed.provenance == "failed"
    assert failed.reason == "catalog_failed"
    assert "fabricated-private" not in json.dumps(failed.to_dict())

    class Cancelled:
        async def list_models(self):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(candidates.discover(Cancelled(), "b1", MASKS, (), "live"))


def test_bounds_fail_closed_not_truncate_then_claim_latest():
    sixty_four = menu(*(f"fixture-{number}-model" for number in range(64)))
    result = discover(sixty_four, {"fixture": "fixture-*"})
    assert result.freshness == "bounded_live"
    assert [model.id for model in result.candidates] == ["fixture-63-model"]
    result = discover(sixty_four + menu("fixture-64-model"), {"fixture": "fixture-*"})
    assert result.freshness == "unknown"
    assert result.provenance == "failed"
    assert result.reason == "catalog_limit"
    assert result.candidates == ()
    provider = Catalog([])
    with pytest.raises(ValueError):
        asyncio.run(
            candidates.discover(
                provider, "b1", {str(n): "fixture-*" for n in range(9)}, (), "live"
            )
        )
    assert provider.calls == 0
    # Overlapping masks also cannot inflate the returned snapshot beyond 64.
    distinct = menu(*(f"fixture-{n}-tier-{n}" for n in range(33)))
    result = discover(distinct, {"one": "fixture-*", "two": "fixture-*"})
    assert result.reason == "catalog_limit"


@pytest.mark.parametrize(
    "models",
    [
        "not-a-model-list",
        [SimpleNamespace(name="no-id")],
        [{"id": INCUMBENT, "capabilities": "vision"}],
        [{"id": "", "capabilities": []}],
        [
            {"id": INCUMBENT, "capabilities": ["tools"]},
            {"id": INCUMBENT, "capabilities": ["vision"]},
        ],
    ],
)
def test_malformed_catalog_has_no_freshness_claim(models):
    result = discover(models)
    assert result.provenance == "failed"
    assert result.freshness == "unknown"
    assert result.candidates == ()


@pytest.mark.parametrize("provenance", ["unknown", "fresh", "", None])
def test_explicit_closed_provenance_required_before_provider_access(provenance):
    provider = Catalog([])
    with pytest.raises(ValueError):
        asyncio.run(candidates.discover(provider, "b1", MASKS, (), provenance))
    assert provider.calls == 0


@pytest.mark.parametrize(
    "change", ["unknown", "missing", "version", "bool", "nonfinite"]
)
def test_receipt_schema_is_strict(change):
    assigned = conditions(LOSER)
    item = receipt(LOSER, assigned)
    if change == "unknown":
        item["observed_call_tree"] = []
    elif change == "missing":
        del item["binding_ref"]
    elif change == "version":
        item["version"] = "unversioned"
    elif change == "bool":
        item["qualified"] = "true"
    else:
        item["score"] = float("nan")
    with pytest.raises(ValueError):
        candidates.validate_receipt(item)


def test_snapshot_input_cannot_upgrade_fallback_or_add_config_fields():
    value = discover(menu(INCUMBENT), provenance="fallback").to_dict()
    value["candidates"][0]["latest"] = True
    with pytest.raises(ValueError):
        candidates.Snapshot.from_dict(value)
    value = discover(menu(INCUMBENT)).to_dict()
    value["endpoint"] = "synthetic-private-endpoint"
    with pytest.raises(ValueError):
        candidates.Snapshot.from_dict(value)
    assigned = conditions(LOSER)
    assigned["observed_score"] = 0
    with pytest.raises(ValueError):
        candidates.assigned_projection(assigned)


def test_saved_snapshot_rejects_historic_nonwinning_models_and_excess_entries():
    value = discover(menu(INCUMBENT)).to_dict()
    older = {**value["candidates"][0], "id": "gpt-5.6-sol"}
    value["candidates"].append(older)
    with pytest.raises(ValueError, match="nonwinning"):
        candidates.Snapshot.from_dict(value)
    value["candidates"] = [older] * 65
    with pytest.raises(ValueError, match="limit"):
        candidates.Snapshot.from_dict(value)


def test_catalog_binding_change_cannot_reuse_matching_receipt_conditions():
    assigned = conditions(LOSER)
    result = candidates.plan_refresh(
        discover(menu(LOSER), binding="synthetic-other-binding"),
        [receipt(LOSER, assigned)],
        assigned,
        INCUMBENT,
    )
    assert result["reuse_ids"] == []
    assert set(result["dispositions"].values()) == {"historical"}
    assert result["fresh_model_ids"] == [INCUMBENT, LOSER]


@pytest.mark.parametrize("masks", [{}, {"any": "*"}, {"any": ""}, {"any": None}])
def test_invalid_or_unbounded_masks_refused_before_catalog_access(masks):
    provider = Catalog([])
    with pytest.raises(ValueError):
        asyncio.run(candidates.discover(provider, "b1", masks, (), "live"))
    assert provider.calls == 0


def test_eight_masks_allowed_and_snapshot_is_independent_of_input_mutation():
    masks = {f"cell-{index}": "gpt-*-sol" for index in range(8)}
    models = menu(INCUMBENT)
    result = discover(models, masks)
    assert len(result.candidates) == 8
    models[0]["capabilities"].append("fabricated-capability")
    masks.clear()
    assert len(result.family_masks) == 8
    assert all(model.capabilities == ("tools",) for model in result.candidates)


def cli_inputs(tmp_path):
    assigned = conditions(INCUMBENT, LOSER)
    assigned["binding_ref"] = "fabricated-private-binding"
    assigned["root"] = "fabricated-private-controller"
    snapshot = discover(menu(INCUMBENT, LOSER), binding=assigned["binding_ref"])
    prior = [receipt(LOSER, assigned, "fabricated-private-lookup")]
    values = {"snapshot": snapshot.to_dict(), "receipts": prior, "conditions": assigned}
    args = ["subset"]
    for name, value in values.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        args.extend([f"--{name}", str(path)])
    args.extend(["--incumbent", INCUMBENT])
    return args


def test_cli_saved_subset_only_allowlists_output(tmp_path):
    result = CliRunner().invoke(candidates_cli.main, cli_inputs(tmp_path))
    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["fresh_model_ids"] == [INCUMBENT]
    assert output["reuse_count"] == 1
    assert output["execution_supported"] is False
    assert "fabricated-private" not in result.output
    assert "binding_ref" not in result.output
    assert "native_settings" not in result.output
    assert set(candidates_cli.main.commands) == {"subset"}


def test_cli_from_unrelated_cwd_and_errors_do_not_echo_private_inputs(tmp_path):
    args = cli_inputs(tmp_path)
    other = tmp_path / "unrelated"
    other.mkdir()
    result = subprocess.run(
        [sys.executable, str(Path(candidates_cli.__file__).resolve()), *args],
        cwd=other,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["fresh_model_ids"] == [INCUMBENT]
    (tmp_path / "snapshot.json").write_text(
        '{"private-path": "fabricated-private-value"', encoding="utf-8"
    )
    failed = CliRunner().invoke(candidates_cli.main, args)
    assert failed.exit_code == 2
    assert json.loads(failed.output) == {"error": "malformed_or_unreadable_inputs"}
    assert str(tmp_path) not in failed.output
    assert "fabricated-private" not in failed.output


if "amplifier_core.models" in sys.modules:

    def test_actual_core_pydantic_modelinfo_when_root_preimports_core():
        model = sys.modules["amplifier_core.models"].ModelInfo(
            id=INCUMBENT,
            display_name="Synthetic Sol",
            context_window=8192,
            max_output_tokens=1024,
            capabilities=["tools", "vision"],
        )
        result = discover([model], required=("vision", "tools"))
        assert result.candidates[0].id == INCUMBENT
        assert result.candidates[0].capabilities == ("tools", "vision")
