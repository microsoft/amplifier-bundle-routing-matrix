"""Offline contract tests. Every generated receipt and benchmark is SYNTHETIC.

No amplifier_evaluation, DTU, model or provider imports. Temporary synthetic
fixtures are removed after each test; only two tests read the pinned public tasks.
"""

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

HERE = Path(__file__).resolve().parent
# Keep direct library imports working under pytest --import-mode=importlib too.
sys.path.insert(0, str(HERE))
import cli  # noqa: E402
import evidence  # noqa: E402


def sample():
    return evidence.read_json(HERE / "sample_manifest.json")


def configured_benchmark_root():
    root = os.environ.get("ROUTING_EVAL_BENCHMARK_ROOT")
    if not root:
        pytest.fail(
            "Set ROUTING_EVAL_BENCHMARK_ROOT to the local amplifier-benchmark/tasks "
            "directory from evaluation revision 7c3646796eea2b042bbe6ffb2de3906d31daa381; "
            "see evals/README.md. No tasks are auto-discovered or downloaded."
        )
    path = Path(root)
    if not path.is_dir():
        pytest.fail(
            "ROUTING_EVAL_BENCHMARK_ROOT must name an existing benchmark tasks directory; "
            "see evals/README.md."
        )
    return path


@pytest.fixture(scope="module")
def benchmark_root():
    return configured_benchmark_root()


@pytest.fixture(scope="module")
def pinned_benchmark(benchmark_root):
    # Validate actual task trees, rubric bytes and criterion locks, not checkout HEAD.
    return evidence.plan(sample(), benchmark_root)


def rehash_arms(manifest):
    for arm in manifest["arms"]:
        arm["matrix_sha256"] = evidence.fingerprint(arm["matrix"])


@pytest.fixture
def experiment():
    with tempfile.TemporaryDirectory(prefix=".synthetic-test-", dir=HERE) as temp:
        root = Path(temp)
        task_dir = root / "different-directory-name"
        task_dir.mkdir()
        data = {
            "meta.yaml": {"name": "synthetic-task", "timeout": 1800},
            "task.yaml": {"instructions": "SYNTHETIC: produce a test artifact."},
            "profile.yaml": {"name": "synthetic-profile"},
            "grader.yaml": {
                "evaluations": [
                    {
                        "name": "bench",
                        "weight": 1,
                        "steps": "SYNTHETIC offline checks.",
                        "rubric": {
                            "functional": {
                                "points": 10,
                                "description": "Test function.",
                            },
                            "correctness": {
                                "points": 20,
                                "description": "Test result.",
                            },
                        },
                    }
                ]
            },
        }
        for name, value in data.items():
            (task_dir / name).write_text(yaml.safe_dump(value, sort_keys=False))
        (task_dir / "workspace").mkdir()
        (task_dir / "workspace/fixture.txt").write_text("SYNTHETIC fixture only.")
        manifest = sample()
        manifest["tasks"] = [
            {
                "id": "synthetic-task",
                "path": task_dir.name,
                "split": "development",
                "sha256": evidence.task_tree_hash(task_dir),
                "rubric_sha256": hashlib.sha256(
                    (task_dir / "grader.yaml").read_bytes()
                ).hexdigest(),
                "required_criteria": [
                    {"id": "bench.functional", "min": 0, "max": 10},
                    {"id": "bench.correctness", "min": 0, "max": 20},
                ],
                "success_rule": {
                    "minimum_awards": {
                        "bench.functional": 10,
                        "bench.correctness": 20,
                    }
                },
                "critical_rule": {"minimum_awards": {"bench.functional": 10}},
            }
        ]
        yield manifest, root, task_dir


def make_plan(experiment):
    manifest, root, _ = experiment
    return evidence.plan(manifest, root)


def synthetic_record(run_plan, cell, suffix="one"):
    """Full valid normalized synthetic receipt, never actual call evidence."""
    task = next(t for t in run_plan["manifest"]["tasks"] if t["id"] == cell["task_id"])
    expected = run_plan["expected_target_calls"][cell["arm_id"]]
    return {
        "synthetic": True,
        "plan_sha256": run_plan["plan_sha256"],
        "cell_id": cell["cell_id"],
        "attempt_id": "synthetic-" + cell["cell_id"] + suffix,
        **{
            k: cell[k]
            for k in ("matrix_sha256", "task_sha256", "rubric_sha256", "sources_sha256")
        },
        "setup": "valid",
        "outcome": "success",
        "outcome_evidence_ids": ["synthetic-receipt-" + cell["cell_id"]],
        "treatment": "valid",
        "actual_target_calls": [
            {
                "id": "synthetic-call-" + cell["cell_id"] + suffix,
                "actual_role": run_plan["manifest"]["target_role"],
                **copy.deepcopy(expected),
            }
        ],
        "grade": {
            "validity": "valid",
            "rubric_sha256": cell["rubric_sha256"],
            "criteria": {c["id"]: c["max"] for c in task["required_criteria"]},
            "critical": "pass",
        },
        "elapsed_s": 12,
        "cost": {
            "coverage": "measured",
            "subject_usd": 1.0,
            "evaluation_usd": 0.2,
            "application_usd": 0.3,
        },
        "cleanup": "confirmed",
    }


def records(run_plan):
    return [synthetic_record(run_plan, c) for c in run_plan["schedule"]]


def missing_grade(record):
    record["grade"].update(validity="missing", criteria={}, critical="unknown")


def row_for(report, record):
    return next(row for row in report["cells"] if row["cell_id"] == record["cell_id"])


def test_sample_locks_schedule_and_ceiling(benchmark_root, pinned_benchmark):
    manifest = sample()
    before = copy.deepcopy(manifest)
    result = evidence.plan(manifest, benchmark_root)
    assert manifest == before
    assert result == pinned_benchmark
    assert result["trial_count"] == 30
    assert result["agent_stage_ceiling_s"] == 102600
    assert result["agent_stage_ceiling_hours"] == 28.5
    assert {c["agent_timeout_s"] for c in result["schedule"]} == {1800, 4500}
    assert len({c["cell_id"] for c in result["schedule"]}) == 30
    assert len({c["pair_id"] for c in result["schedule"]}) == 15
    firsts = [c["arm_id"] for c in result["schedule"] if c["arm_order"] == 1]
    assert sorted([firsts.count("baseline"), firsts.count("candidate")]) == [7, 8]
    assert result["expected_target_calls"]["candidate"]["model"] == "gpt-6-astra"
    assert len(manifest["arms"][0]["matrix"]["roles"]) == 13
    planned = CliRunner().invoke(
        cli.main,
        [
            "plan",
            str(HERE / "sample_manifest.json"),
            "--benchmark-root",
            str(benchmark_root),
        ],
    )
    assert planned.exit_code == 0, planned.output
    assert json.loads(planned.output) == result


def test_seed_changes_order_not_balance(experiment):
    manifest, root, _ = experiment
    a = evidence.plan(manifest, root)
    manifest["seed"] = 8
    b = evidence.plan(manifest, root)
    assert [c["arm_id"] for c in a["schedule"]] != [c["arm_id"] for c in b["schedule"]]
    assert a["plan_sha256"] != b["plan_sha256"]
    assert a["trial_count"] == b["trial_count"]


def test_effort_leaf_supported(experiment):
    manifest, root, _ = experiment
    manifest["estimand"] = "effort"
    candidate = manifest["arms"][1]["matrix"]["roles"]["coding"]["candidates"][0]
    candidate["model"] = "gpt-6.1-sol"
    candidate["config"]["reasoning_effort"] = "medium"
    rehash_arms(manifest)
    assert evidence.plan(manifest, root)["expected_target_calls"]["candidate"][
        "native_config"
    ] == {"reasoning_effort": "medium"}


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m.update(version=True),
        lambda m: m.update(synthetic="true"),
        lambda m: m.update(secret="not-accepted"),
        lambda m: m.update(explicit_pin={"model": "gpt-6-astra"}),
        lambda m: m.update(estimand="backend_config"),
        lambda m: m.update(estimand="whole_policy"),
        lambda m: m.update(repetitions=0),
        lambda m: m.update(seed=float("nan")),
        lambda m: m["sources"].update(core="@main"),
        lambda m: m["sources"].update(core="abc"),
        lambda m: m["sources"].pop("foundation"),
        lambda m: m.update(credential_env_names=["key=value"]),
        lambda m: m.update(credential_env_names=[{}]),
        lambda m: m["root"].update(api_key="value"),
        lambda m: m["root"].update(overrides={"reasoning_effort": "low"}),
        lambda m: m["budgets"].update(subject_usd=float("inf")),
        lambda m: m["tasks"].append(copy.deepcopy(m["tasks"][0])),
        lambda m: m["tasks"][0].update(sha256="bad"),
        lambda m: m["tasks"][0].update(path="../escape"),
        lambda m: m["tasks"][0].update(path=[]),
        lambda m: m["arms"].reverse(),
        lambda m: m["arms"][1].update(matrix_sha256="0" * 64),
        lambda m: m["evaluator"]["judge"].update(model="another-model"),
        lambda m: m["arms"][1].update(evaluator={}),
    ],
)
def test_malformed_manifest_rejected(experiment, change):
    manifest, root, _ = experiment
    change(manifest)
    with pytest.raises(ValueError):
        evidence.plan(manifest, root)


@pytest.mark.parametrize(
    "kind",
    [
        "second_dimension",
        "other_role",
        "fallback",
        "backend",
        "glob",
        "extra_knob",
        "no_effort",
        "whole_matrix_description",
    ],
)
def test_non_leaf_treatments_rejected(experiment, kind):
    manifest, root, _ = experiment
    matrix = manifest["arms"][1]["matrix"]
    candidate = matrix["roles"]["coding"]["candidates"][0]
    if kind == "second_dimension":
        candidate["config"]["reasoning_effort"] = "medium"
    elif kind == "other_role":
        matrix["roles"]["general"]["candidates"][0]["model"] = "gpt-6-astra"
    elif kind == "fallback":
        matrix["roles"]["coding"]["candidates"][4]["model"] = "gpt-6-astra"
    elif kind == "backend":
        candidate["provider"] = "anthropic"
    elif kind == "glob":
        candidate["model"] = "gpt-6-*"
    elif kind == "extra_knob":
        candidate["config"]["temperature"] = 0
    elif kind == "no_effort":
        del candidate["config"]
    else:
        matrix["description"] += "changed"
    rehash_arms(manifest)
    with pytest.raises(ValueError):
        evidence.plan(manifest, root)


@pytest.mark.parametrize("arm_index", [0, 1])
@pytest.mark.parametrize("estimand", ["model", "effort"])
def test_any_preset_rejects_inheritance_effort_and_model_rung(
    experiment, arm_index, estimand
):
    manifest, root, _ = experiment
    manifest["estimand"] = estimand
    if estimand == "effort":
        primary = manifest["arms"][1]["matrix"]["roles"]["coding"]["candidates"][0]
        primary["model"] = "gpt-6.1-sol"
        primary["config"]["reasoning_effort"] = "low"
    manifest["arms"][arm_index]["matrix"]["preset"] = {
        "strict": True,
        "inherit_effort": True,
        "tier_ladder": ["gpt-6-luna", "gpt-6-astra", "gpt-6.1-sol"],
    }
    rehash_arms(manifest)
    with pytest.raises(ValueError, match="inheritance_observability"):
        evidence.plan(manifest, root)


@pytest.mark.parametrize(
    "name",
    ["profile.yaml", "task.yaml", "grader.yaml", "workspace/fixture.txt", "meta.yaml"],
)
def test_every_task_component_mutation_rejected(experiment, name):
    manifest, root, directory = experiment
    with (directory / name).open("a") as file:
        file.write("\n# changed fixture bytes\n")
    with pytest.raises(ValueError, match="task sha256"):
        evidence.plan(manifest, root)


def test_cache_excluded_but_symlinks_rejected(experiment):
    manifest, root, directory = experiment
    cache = directory / "__pycache__"
    cache.mkdir()
    (cache / "generated.pyc").write_bytes(b"generated-cache")
    assert evidence.plan(manifest, root)["trial_count"] == 6
    (cache / "link").symlink_to(directory / "meta.yaml")
    with pytest.raises(ValueError, match="symlinks"):
        evidence.plan(manifest, root)


def test_metadata_id_not_directory_name(experiment):
    result = make_plan(experiment)
    assert result["tasks"][0]["id"] == "synthetic-task"
    assert result["manifest"]["tasks"][0]["path"] != "synthetic-task"


def test_placeholder_and_audit_flags_block_readiness(pinned_benchmark):
    result = pinned_benchmark
    readiness = evidence.readiness(result)
    assert readiness["plan_valid"] and not readiness["execution_supported"]
    assert not readiness["ready"]
    assert result["rubric_blockers"] == [
        {
            "task_id": "code-discrepancy-docs-knack",
            "code": "unresolved_rubric_reference",
            "requires_followup": True,
        }
    ]
    flags = {w["code"] for w in result["warnings"]}
    assert {"time_sensitive_year", "recency", "live_url", "model_choice"} <= flags


def test_even_clean_rubric_execution_unsupported(experiment):
    result = make_plan(experiment)
    assert not result["rubric_blockers"]
    assert not evidence.readiness(result)["ready"]


def test_complete_synthetic_paired_scores_no_winner(experiment):
    result = make_plan(experiment)
    attempts = records(result)
    for attempt in attempts:
        cell = next(c for c in result["schedule"] if c["cell_id"] == attempt["cell_id"])
        if cell["arm_id"] == "baseline":
            attempt["grade"]["criteria"]["bench.correctness"] = 14
    report = evidence.analyze(result, attempts)
    pairs = report["paired_tasks"][0]
    assert pairs["complete_pairs"] == 3 and pairs["missing_or_ineligible_pairs"] == 0
    assert all(
        d["candidate_minus_baseline_upstream_score"] == pytest.approx(20)
        for d in pairs["differences"]
    )
    assert report["synthetic"] and not report["promotional"]
    assert "winner" not in report
    assert report["usd_comparison_eligible"]
    assert report["arms"]["baseline"]["completion"]["failure"] == 3
    assert report["arms"]["candidate"]["completion"]["success"] == 3


def test_missing_grade_neither_success_failure_nor_zero(experiment):
    result = make_plan(experiment)
    attempt = records(result)[0]
    missing_grade(attempt)
    report = evidence.analyze(result, [attempt])
    row = row_for(report, attempt)
    assert row["completion"] == "unknown"
    assert row["upstream_score"] is None and not row["quality_eligible"]
    assert report["paired_tasks"][0]["complete_pairs"] == 0


@pytest.mark.parametrize("outcome", ["failure", "timeout"])
def test_verified_failure_timeout_denominator_without_quality_zero(experiment, outcome):
    result = make_plan(experiment)
    attempt = records(result)[0]
    missing_grade(attempt)
    attempt["outcome"] = outcome
    report = evidence.analyze(result, [attempt])
    row = row_for(report, attempt)
    assert row["completion"] == "failure"
    assert row["upstream_score"] is None
    arm = report["arms"][row["arm_id"]]
    assert arm["scheduled_cells"] == 3
    assert arm["completion"] == {"success": 0, "failure": 1, "unknown": 2}
    assert arm["completion_rate_bounds"] == [0, 2 / 3]


@pytest.mark.parametrize(
    "field,value", [("setup", "unknown"), ("outcome_evidence_ids", [])]
)
def test_unverified_outcomes_unknown(experiment, field, value):
    result = make_plan(experiment)
    attempt = records(result)[0]
    attempt[field] = value
    assert (
        row_for(evidence.analyze(result, [attempt]), attempt)["completion"] == "unknown"
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(actual_target_calls=[]),
        lambda r: r["actual_target_calls"][0].update(actual_role="general"),
        lambda r: r["actual_target_calls"][0].update(backend="openai-chatgpt"),
        lambda r: r["actual_target_calls"][0].update(model="spoofed-model"),
        lambda r: r["actual_target_calls"][0]["native_config"].update(
            reasoning_effort="low"
        ),
    ],
)
def test_valid_treatment_requires_exposure_role_backend_and_effort(experiment, change):
    result = make_plan(experiment)
    attempt = records(result)[0]
    change(attempt)
    with pytest.raises(ValueError, match="actual target-role exposure"):
        evidence.analyze(result, [attempt])


def test_missing_treatment_blocks_attribution_not_arm_outcome(experiment):
    result = make_plan(experiment)
    attempts = records(result)
    attempts[0].update(treatment="unknown", actual_target_calls=[])
    report = evidence.analyze(result, attempts)
    row = row_for(report, attempts[0])
    assert row["completion"] == "success" and row["quality_eligible"]
    assert not row["attribution_eligible"]
    assert report["paired_tasks"][0]["complete_pairs"] == 2
    assert report["paired_tasks"][0]["missing_or_ineligible_pairs"] == 1


def test_multiple_attempts_blocked_retaining_all_scores_and_costs(experiment):
    result = make_plan(experiment)
    attempts = records(result)
    extra = synthetic_record(result, result["schedule"][0], "two")
    attempts[0]["grade"]["criteria"]["bench.correctness"] = 1
    attempts.append(extra)
    report = evidence.analyze(result, attempts)
    row = row_for(report, extra)
    assert row["cell_status"] == "multiple_attempts_blocked"
    assert len(row["attempts"]) == 2
    assert row["upstream_score"] is None and row["completion"] == "unknown"
    assert report["paired_tasks"][0]["complete_pairs"] == 2
    assert report["arms"][row["arm_id"]]["cost"]["attempt_count"] == 4
    assert report["arms"][row["arm_id"]]["cost"]["total_usd"] == 6
    assert not report["usd_comparison_eligible"]


def test_partial_cost_not_zero_cleanup_does_not_erase_outcome(experiment):
    result = make_plan(experiment)
    attempts = records(result)
    attempt = attempts[0]
    attempt["cost"].update(
        coverage="unknown", evaluation_usd=None, application_usd=None
    )
    attempt["cleanup"] = "unconfirmed"
    report = evidence.analyze(result, attempts)
    row = row_for(report, attempt)
    assert row["completion"] == "success" and row["quality_eligible"]
    cost = report["arms"][row["arm_id"]]["cost"]
    assert cost["total_usd"] is None
    assert cost["components"]["evaluation_usd"]["unknown_attempts"] == 1
    assert cost["components"]["evaluation_usd"]["measured_total_usd"] == pytest.approx(
        0.4
    )
    assert cost["components"]["evaluation_usd"]["lower_bound"]
    assert not report["usd_comparison_eligible"] and not report["cleanup_ready"]
    assert report["paired_tasks"][0]["complete_pairs"] == 3


def test_all_unknown_cost_components_stay_none(experiment):
    result = make_plan(experiment)
    attempt = records(result)[0]
    attempt["cost"] = {
        "coverage": "unknown",
        "subject_usd": None,
        "evaluation_usd": None,
        "application_usd": None,
    }
    report = evidence.analyze(result, [attempt])
    cost = report["arms"][row_for(report, attempt)["arm_id"]]["cost"]
    assert cost["components"]["subject_usd"]["measured_total_usd"] is None
    assert cost["total_usd"] is None


def test_missing_cells_and_pair_denominators_retained(experiment):
    result = make_plan(experiment)
    attempts = records(result)[:1]
    report = evidence.analyze(result, attempts)
    assert len(report["cells"]) == 6
    assert sum(row["cell_status"] == "missing" for row in report["cells"]) == 5
    assert report["paired_tasks"][0]["scheduled_pairs"] == 3
    assert report["paired_tasks"][0]["missing_or_ineligible_pairs"] == 3
    assert not report["usd_comparison_eligible"]
    assert report["arms"][row_for(report, attempts[0])["arm_id"]]["cost"]["components"][
        "subject_usd"
    ]["lower_bound"]


def test_critical_failure_keeps_numeric_grade_but_prevents_success(experiment):
    result = make_plan(experiment)
    attempts = records(result)
    attempts[0]["grade"]["criteria"]["bench.functional"] = 0
    attempts[0]["grade"]["critical"] = "fail"
    report = evidence.analyze(result, attempts)
    row = row_for(report, attempts[0])
    assert row["upstream_score"] == pytest.approx(200 / 3)
    assert row["completion"] == "failure" and row["critical_failures"] == 1
    assert report["paired_tasks"][0]["complete_pairs"] == 3


@pytest.mark.parametrize("critical", ["pass", "fail"])
def test_invalid_grade_cannot_establish_critical_status(experiment, critical):
    result = make_plan(experiment)
    attempt = records(result)[0]
    attempt["grade"].update(validity="invalid", critical=critical)
    with pytest.raises(ValueError, match="invalid grade"):
        evidence.analyze(result, [attempt])


def test_failed_success_threshold_remains_failure_with_unknown_critical(experiment):
    result = make_plan(experiment)
    attempt = records(result)[0]
    attempt["grade"]["criteria"]["bench.correctness"] = 0
    attempt["grade"]["critical"] = "unknown"
    report = evidence.analyze(result, [attempt])
    row = row_for(report, attempt)
    arm = report["arms"][row["arm_id"]]
    assert row["completion"] == "failure"
    assert row["critical_failures"] == 0
    assert arm["completion"] == {"success": 0, "failure": 1, "unknown": 2}
    assert arm["completion_rate_bounds"] == [0, pytest.approx(2 / 3)]


def test_satisfied_thresholds_with_unknown_critical_remain_unknown(experiment):
    result = make_plan(experiment)
    attempt = records(result)[0]
    attempt["grade"]["critical"] = "unknown"
    row = row_for(evidence.analyze(result, [attempt]), attempt)
    assert row["completion"] == "unknown"
    assert row["quality_eligible"]
    assert row["critical_failures"] == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(plan_sha256="0" * 64),
        lambda r: r.update(matrix_sha256="0" * 64),
        lambda r: r.update(task_sha256="0" * 64),
        lambda r: r.update(rubric_sha256="0" * 64),
        lambda r: r.update(sources_sha256="0" * 64),
        lambda r: r["grade"].update(rubric_sha256="0" * 64),
        lambda r: r.update(cell_id="unscheduled"),
        lambda r: r.update(synthetic=False),
        lambda r: r.update(elapsed_s=float("nan")),
        lambda r: r.update(elapsed_s=-1),
        lambda r: r["cost"].update(subject_usd=float("inf")),
        lambda r: r["cost"].update(subject_usd=None),
        lambda r: r["grade"]["criteria"].update({"arbitrary.score": 20}),
        lambda r: r["grade"]["criteria"].update({"bench.correctness": 21}),
        lambda r: r["grade"]["criteria"].pop("bench.correctness"),
        lambda r: r["grade"].update(critical="fail"),
        lambda r: r.update(secrets={}),
        lambda r: r.pop("cleanup"),
    ],
)
def test_malformed_or_spoofed_evidence_rejected(experiment, change):
    result = make_plan(experiment)
    attempt = records(result)[0]
    change(attempt)
    with pytest.raises(ValueError):
        evidence.analyze(result, [attempt])


@pytest.mark.parametrize("duplicate", ["attempt", "call"])
def test_duplicate_immutable_ids_rejected(experiment, duplicate):
    result = make_plan(experiment)
    attempts = records(result)[:2]
    if duplicate == "attempt":
        attempts[1]["attempt_id"] = attempts[0]["attempt_id"]
    else:
        attempts[1]["actual_target_calls"][0]["id"] = attempts[0][
            "actual_target_calls"
        ][0]["id"]
    with pytest.raises(ValueError, match="duplicate"):
        evidence.analyze(result, attempts)


def test_cross_seed_plan_and_mutated_schedule_rejected(experiment):
    manifest, root, _ = experiment
    original = evidence.plan(manifest, root)
    manifest["seed"] += 1
    with pytest.raises(ValueError):
        evidence.analyze(evidence.plan(manifest, root), records(original))
    original["schedule"][0]["agent_timeout_s"] += 1
    with pytest.raises(ValueError, match="plan_sha256"):
        evidence.readiness(original)


def test_strict_json_duplicates_nonfinite_and_raw_jsonl(experiment):
    _, root, _ = experiment
    path = root / "synthetic.json"
    for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', "{}\n{}"):
        path.write_text(text)
        with pytest.raises(ValueError):
            evidence.read_json(path)


def test_cli_offline_json_and_status_contract(experiment):
    manifest, root, _ = experiment
    manifest_path = root / "synthetic-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    runner = CliRunner()
    args = [str(manifest_path), "--benchmark-root", str(root)]
    planned = runner.invoke(cli.main, ["plan", *args])
    assert planned.exit_code == 0, planned.output
    run_plan = json.loads(planned.output)
    ready = runner.invoke(cli.main, ["readiness", *args])
    assert ready.exit_code == 1 and not json.loads(ready.output)["execution_supported"]
    evidence_path = root / "synthetic-evidence.json"
    evidence_path.write_text(json.dumps(records(run_plan)))
    analyzed = runner.invoke(
        cli.main,
        [
            "analyze",
            str(manifest_path),
            str(evidence_path),
            "--benchmark-root",
            str(root),
        ],
    )
    assert analyzed.exit_code == 0, analyzed.output
    assert not json.loads(analyzed.output)["promotional"]
    evidence_path.write_text("[]\n[]")
    malformed = runner.invoke(
        cli.main,
        [
            "analyze",
            str(manifest_path),
            str(evidence_path),
            "--benchmark-root",
            str(root),
        ],
    )
    assert malformed.exit_code == 2
    manifest_path.write_text("{}")
    assert runner.invoke(cli.main, ["plan", *args]).exit_code == 2
    assert runner.invoke(cli.main, ["run"]).exit_code != 0


@pytest.mark.parametrize("command", ["plan", "readiness", "analyze"])
def test_cli_requires_explicit_root_before_input_io(monkeypatch, command):
    def forbidden_read(*args, **kwargs):
        pytest.fail("CLI read input before requiring --benchmark-root")

    monkeypatch.setattr(evidence, "read_json", forbidden_read)
    args = [command, "synthetic-manifest.json"]
    if command == "analyze":
        args.append("synthetic-evidence.json")
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 2
    assert "Missing option '--benchmark-root'" in result.output


@pytest.mark.parametrize("command", ["plan", "readiness", "analyze"])
def test_cli_unreadable_explicit_inputs_are_redacted(tmp_path, command):
    private_marker = "synthetic-private-path"
    args = [command, str(tmp_path / private_marker / "manifest.json")]
    if command == "analyze":
        args.append(str(tmp_path / private_marker / "evidence.json"))
    args.extend(["--benchmark-root", str(tmp_path / private_marker / "tasks")])
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 2
    assert json.loads(result.output) == {
        "error": "malformed_or_unreadable_inputs",
        "error_type": "FileNotFoundError",
    }
    assert private_marker not in result.output
    assert str(tmp_path) not in result.output


@pytest.mark.parametrize("value", [None, ""])
def test_missing_benchmark_configuration_fails_actionably(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ROUTING_EVAL_BENCHMARK_ROOT", raising=False)
    else:
        monkeypatch.setenv("ROUTING_EVAL_BENCHMARK_ROOT", value)
    with pytest.raises(pytest.fail.Exception, match="Set ROUTING_EVAL_BENCHMARK_ROOT"):
        configured_benchmark_root()


def test_nonexistent_benchmark_configuration_fails_actionably(monkeypatch, tmp_path):
    monkeypatch.setenv("ROUTING_EVAL_BENCHMARK_ROOT", str(tmp_path / "missing"))
    with pytest.raises(
        pytest.fail.Exception, match="existing benchmark tasks directory"
    ):
        configured_benchmark_root()


def test_relocation_keeps_historical_sample_bytes_and_source_pin():
    assert hashlib.sha256((HERE / "sample_manifest.json").read_bytes()).hexdigest() == (
        "7a4c7e484c0c6f788789686d8f52ac64d106a479bd34dac48051dc3c678e4064"
    )
    assert (
        sample()["sources"]["evaluation"] == "7c3646796eea2b042bbe6ffb2de3906d31daa381"
    )
    assert sample()["sources"]["routing"] == "183b453c5674fa9c4d51c24cd68e79bce34b28ea"


def test_direct_cli_from_unrelated_cwd(experiment, tmp_path):
    manifest, root, _ = experiment
    manifest_path = root / "synthetic-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    run_plan = evidence.plan(manifest, root)
    evidence_path = root / "synthetic-evidence.json"
    evidence_path.write_text(json.dumps(records(run_plan)))
    for command, expected_status in [("plan", 0), ("readiness", 1), ("analyze", 0)]:
        args = [sys.executable, str(HERE / "cli.py"), command, str(manifest_path)]
        if command == "analyze":
            args.append(str(evidence_path))
        args.extend(["--benchmark-root", str(root)])
        result = subprocess.run(
            args, cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False
        )
        assert result.returncode == expected_status, result.stderr
        report = json.loads(result.stdout)
        assert report["plan_sha256"] == run_plan["plan_sha256"]


def test_import_boundary_is_small_and_offline():
    assert Path(cli.__file__).resolve() == HERE / "cli.py"
    assert Path(evidence.__file__).resolve() == HERE / "evidence.py"
    assert cli.evidence is evidence
    forbidden = (
        "amplifier",
        "http",
        "requests",
        "subprocess",
        "socket",
        "openai",
        "anthropic",
        "google",
        "dtu",
    )
    for name in ("evidence.py", "cli.py"):
        tree = ast.parse((HERE / name).read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(module.startswith(forbidden) for module in imports)
