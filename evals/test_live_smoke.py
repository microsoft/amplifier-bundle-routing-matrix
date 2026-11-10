"""Controller logic only: artifacts are NEVER imported/executed on this host."""

import copy
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent))
from live_smoke import (
    ASSESSOR_DRIVER,
    SOURCE_LABELS,
    AssessmentSpec,
    CampaignSpec,
    CellSpec,
    DelegateCodingTool,
    GradeReceipt,
    Ledger,
    SourceLock,
    SmokeBlocked,
    SmokeLimits,
    arm_matrix,
    assessment_cases,
    assessor_create_args,
    baseline_matrix,
    compare_assessment,
    extract_module,
    grid_union,
    preflight,
    prepare_output,
    report,
    write_once,
    source_digest,
    TREE_LABELS,
    IMPLEMENTATION_BLOCKERS,
    grade_artifact,
)
import smoke_cli
from test_live_transport import quote


def campaign_json(spec):
    return {
        "version": spec.version,
        "campaign_id": spec.campaign_id,
        "sources": [
            {"label": s.label, "path": str(s.path), "sha256": s.sha256}
            for s in spec.sources
        ],
        "module_sources": {k: str(p) for k, p in spec.module_sources.items()},
        "quote": {
            **{
                k: v
                for k, v in vars(spec.quote).items()
                if k
                not in {
                    "rates",
                    "long_context_rates",
                    "verified_at",
                    "effective_at",
                    "expires_at",
                }
            },
            **{
                k: getattr(spec.quote, k).isoformat()
                for k in ("verified_at", "effective_at", "expires_at")
            },
            "rates": {
                k: {n: str(v) for n, v in vars(r).items()}
                for k, r in spec.quote.rates.items()
            },
            "long_context_rates": {
                k: {n: str(v) for n, v in vars(r).items()}
                for k, r in spec.quote.long_context_rates.items()
            },
        },
        "assessment": vars(spec.assessment),
        "private_output_root": str(spec.private_output_root),
        "endpoint_qualified": spec.endpoint_qualified,
        "binding_qualified": spec.binding_qualified,
        "full_stack_qualification": spec.full_stack_qualification,
        "assessor_qualification": spec.assessor_qualification,
        "pair_order": list(spec.pair_order),
    }


def campaign(tmp_path, qualified=False):
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    sources = []
    for label in sorted(SOURCE_LABELS):
        path = inventory / label
        if label in TREE_LABELS:
            path.mkdir()
            (path / "__init__.py").write_bytes(f"# synthetic {label}\n".encode())
        else:
            path.write_bytes(f"# synthetic {label}\n".encode())
        sources.append(SourceLock(label, path, source_digest(path)))
    modules = {}
    for label in ("shim", "loop", "context", "routing"):
        path = inventory / label
        (path / "pyproject.toml").write_text("[project]\nname='synthetic'\n")
        modules[label] = path
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    sources = [replace(s, sha256=source_digest(s.path)) for s in sources]
    return CampaignSpec(
        "synthetic-campaign",
        tuple(sources),
        modules,
        quote(),
        AssessmentSpec(
            "synthetic/python@sha256:" + "a" * 64,
            "synthetic-qualification",
            qualified,
            17,
        ),
        private,
        True,
        True,
        "synthetic-mock" if qualified else None,
        "synthetic-grader-controls" if qualified else None,
    )


def synthetic_records(cases):
    """Asserted control data, not a claim that an artifact ran."""
    return [
        {
            "id": c["id"],
            "status": "value_error" if c["invalid"] else "return",
            "shape": not c["invalid"],
            "answer": None if c["invalid"] else grid_union(c["input"]),
            "mutated": False,
        }
        for c in cases
    ]


def test_single_leaf_treatment():
    baseline = baseline_matrix()
    assert arm_matrix(CellSpec("A0", "gpt-6.1-sol")) == baseline
    assert arm_matrix(CellSpec("A1", "gpt-6.1-sol")) == baseline
    candidate = copy.deepcopy(baseline)
    candidate["roles"]["coding"]["candidates"][0]["model"] = "gpt-6-astra"
    assert arm_matrix(CellSpec("B1", "gpt-6-astra")) == candidate
    assert "preset" not in baseline


@pytest.mark.parametrize(
    "output",
    [
        '{"module":"def coalesce(ranges):\\n return []\\n"}',
        '{"module":"def coalesce(ranges):\\n raise ValueError()\\n"}',
    ],
)
def test_strict_extraction_syntax_only(output):
    assert extract_module(output).startswith(b"def coalesce")


@pytest.mark.parametrize(
    "output",
    [
        '```json\n{"module":"x"}\n```',
        '{"module":"x","extra":1}',
        '{"module":null}',
        '{"module":"pass"}',
        '{"module":"def coalesce(: pass"}',
        '{"module":"def coalesce(r): pass","module":"pass"}',
        '{"module":"' + "x" * 16384 + '"}',
    ],
)
def test_extraction_rejects_malformed_not_zero_grade(output):
    with pytest.raises(SmokeBlocked):
        extract_module(output)


def test_artifact_never_executed_in_controller(tmp_path):
    marker = tmp_path / "must-not-exist"
    text = f"open({str(marker)!r}, 'w').write('unsafe')\ndef coalesce(r): return []\n"
    assert extract_module(json.dumps({"module": text})) == text.encode()
    assert not marker.exists()


def test_grid_independent_expected_union():
    assert grid_union([[-3, 1], [1, 4], [-1, 2], [8, 9]]) == [[-3, 4], [8, 9]]


def test_complete_comparisons_without_running_artifact():
    cases = assessment_cases(17)
    grade = compare_assessment(
        json.dumps(synthetic_records(cases)).encode(), cases, True
    )
    assert grade.validity == "valid"
    assert dict(grade.awards) == {
        "union": 1,
        "touching_empty": 1,
        "invalid": 1,
        "immutability": 1,
    }
    assert len(grade.comparisons) == len(cases) > 40
    assert grade.critical == "pass"
    assert assessment_cases(17) == assessment_cases(17)
    assert assessment_cases(17) != assessment_cases(18)


@pytest.mark.parametrize("fault", ["constant", "nonmerge", "bool", "mutation"])
def test_comparison_discrimination_asserted_data_only(fault):
    cases = assessment_cases(17)
    records = synthetic_records(cases)
    if fault == "constant":
        for c, r in zip(cases, records):
            if not c["invalid"]:
                r["answer"] = []
    elif fault == "nonmerge":
        records[0]["answer"] = cases[0]["input"]
    elif fault == "bool":
        case = next(c for c in cases if c["input"] == [[True, 2]])
        records[int(case["id"])]["status"] = "return"
    else:
        records[0]["mutated"] = True
    grade = compare_assessment(json.dumps(records).encode(), cases, True)
    assert grade.validity == "valid"
    assert not all(value == 1 for _, value in grade.awards)
    if fault == "mutation":
        assert grade.critical == "fail"


@pytest.mark.parametrize("raw", [b"[]", b"{}", b"not-json", b"[true]", b"x" * 65537])
def test_invalid_grader_keeps_missing_awards(raw):
    grade = compare_assessment(raw, assessment_cases(17), True)
    assert grade.validity == "invalid"
    assert grade.awards == ()
    assert grade.critical == "unknown"


def test_empty_and_partial_case_set_cannot_pass():
    assert compare_assessment(b"[]", [], True).validity == "invalid"
    cases = assessment_cases(17)
    assert (
        compare_assessment(
            json.dumps(synthetic_records(cases)[:-1]).encode(),
            cases,
            True,
        ).validity
        == "invalid"
    )


def test_bool_forged_answer_cannot_exploit_integer_equality():
    cases = assessment_cases(17)
    records = synthetic_records(cases)
    records[1]["answer"][0][0] = True
    assert (
        dict(
            compare_assessment(
                json.dumps(records).encode(),
                cases,
                True,
            ).awards
        )["union"]
        == 0
    )


def test_assessor_launch_contract_no_credentials_or_network(tmp_path):
    from live_smoke import GRAMMAR_SHA256

    proof = tmp_path / "synthetic-proof.json"
    image = "synthetic/python@sha256:" + "a" * 64
    proof.write_text(
        json.dumps(
            {
                "actual_python_image": image,
                "isolated_controls_passed": True,
                "absence_verified": True,
                "execution_exit": 0,
                "runtime_checks": {
                    "uid": 65534,
                    "capabilities": "none",
                    "no_new_privileges": True,
                    "provider_credentials_present": False,
                    "docker_socket_present": False,
                    "personal_mount_present": False,
                    "root_fs_readonly": True,
                    "tmp_writable": True,
                    "external_network_denied": True,
                },
            }
        )
    )
    spec = AssessmentSpec(
        image,
        "synthetic-not-runtime-evidence",
        False,
        1,
        isolation_path=proof,
        isolation_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),
        validator_sha256=GRAMMAR_SHA256,
        driver_sha256=hashlib.sha256(ASSESSOR_DRIVER.encode()).hexdigest(),
    )
    args = assessor_create_args(
        "synthetic-assessor",
        Path("/synthetic/solution.py"),
        Path("/synthetic/driver.py"),
        spec,
    )
    assert "--network" in args and args[args.index("--network") + 1] == "none"
    assert "--read-only" in args and "--cap-drop" in args
    assert "--user" in args and args[args.index("--user") + 1] == "65534:65534"
    assert not any("docker.sock" in x or "HOME" in x or "API_KEY" in x for x in args)
    assert "--env" not in args
    assert "grid_union" not in ASSESSOR_DRIVER
    assert "expected" not in ASSESSOR_DRIVER
    with pytest.raises(SmokeBlocked, match="assessor_source_locks"):
        assessor_create_args(
            "synthetic", Path("/a"), Path("/b"), replace(spec, validator_sha256="bad")
        )


def test_preflight_honest_no_runtime_imports(tmp_path):
    spec = campaign(tmp_path)
    result = preflight(spec)
    assert not result["ready"]
    assert result["model_calls"] == 0
    assert result["blockers"] == [
        *IMPLEMENTATION_BLOCKERS,
        "assessor_source_image_qualification",
        "source_bound_execution_qualification",
        "assessment_resource_authority",
    ]
    (
        next(s.path for s in spec.sources if s.label == "routing") / "__init__.py"
    ).write_bytes(b"changed")
    assert "source_routing" in preflight(spec)["blockers"]


def test_private_output_and_immutable_files(tmp_path):
    spec = campaign(tmp_path)
    output = prepare_output(spec, spec.private_output_root / spec.campaign_id)
    write_once(output / "receipt.json", b"{}")
    with pytest.raises(FileExistsError):
        write_once(output / "receipt.json", b"changed")
    with pytest.raises(SmokeBlocked, match="private_output_path"):
        prepare_output(spec, tmp_path / "not-private")


def test_every_scheduled_cell_reported_with_interruption(tmp_path):
    value = Ledger(tmp_path / "campaign.jsonl", "synthetic", SmokeLimits())
    value.start_cell("A0")
    result = report(value)
    assert result["cells"]["A0"]["instrumentation"] == "interrupted"
    assert result["cells"]["A1"]["instrumentation"] == "not-run"
    assert result["cells"]["B1"]["instrumentation"] == "not-run"


def test_delegate_schema_and_no_model_override():
    assert DelegateCodingTool.input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert "model" not in DelegateCodingTool.input_schema["properties"]


def test_mock_cli_guarded_once_baseline_and_pair(tmp_path, monkeypatch):
    spec = campaign(tmp_path, qualified=True)
    monkeypatch.setattr(smoke_cli, "load_campaign", lambda _: spec)
    monkeypatch.setenv("SMOKE_OPENAI_CREDENTIAL", "synthetic-not-a-secret")
    # A fake orchestration test does not qualify or enable real runtime execution.
    monkeypatch.setattr(
        smoke_cli,
        "preflight",
        lambda _: {
            "ready": True,
            "synthetic": True,
            "model_calls": 0,
        },
    )
    calls = []

    async def fake_run(cell, authority, output, campaign_, credential):
        authority.ledger.start_cell(cell.cell_id)
        calls.append(cell.cell_id)
        result = {
            "instrumentation": "valid",
            "cleanup": "confirmed",
            "grade": GradeReceipt(
                "valid", (), (), "unknown", "confirmed", None
            ).as_dict(),
        }
        authority.ledger.finish_cell(cell.cell_id, result)

        class Receipt:
            instrumentation = "valid"

        return Receipt()

    monkeypatch.setattr(smoke_cli, "run_cell", fake_run)
    runner = CliRunner()
    args = [
        "--spec",
        "synthetic.json",
        "--output-dir",
        str(spec.private_output_root / spec.campaign_id),
    ]
    assert runner.invoke(smoke_cli.cli, ["run-baseline", *args]).exit_code == 1
    assert calls == []
    assert runner.invoke(smoke_cli.cli, ["preflight", *args]).exit_code == 0
    assert runner.invoke(smoke_cli.cli, ["run-pair", *args]).exit_code == 1
    assert calls == []
    assert runner.invoke(smoke_cli.cli, ["run-baseline", *args]).exit_code == 0
    assert runner.invoke(smoke_cli.cli, ["run-baseline", *args]).exit_code == 1
    assert runner.invoke(smoke_cli.cli, ["run-pair", *args]).exit_code == 0
    assert calls == ["A0", "A1", "B1"]
    assert runner.invoke(smoke_cli.cli, ["run-pair", *args]).exit_code == 1


def test_cli_bad_input_sanitized(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("PRIVATE PATH OR ERROR BODY")
    result = CliRunner().invoke(
        smoke_cli.cli,
        [
            "preflight",
            "--spec",
            str(bad),
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "PRIVATE" not in result.output and str(tmp_path) not in result.output


def test_campaign_cannot_reset_accounting_with_another_output_dir(tmp_path):
    spec = campaign(tmp_path)
    prepare_output(spec, spec.private_output_root / spec.campaign_id)
    with pytest.raises(SmokeBlocked, match="campaign_output_changed"):
        prepare_output(spec, spec.private_output_root / "another-run")


def test_no_image_boolean_can_enable_unqualified_observer(tmp_path):
    spec = campaign(tmp_path, qualified=True)
    artifact = tmp_path / "solution.py"
    artifact.write_text("raise RuntimeError('must not execute')\n")
    grade = grade_artifact(artifact, spec.assessment)
    assert grade.validity == "invalid" and grade.awards == ()
    assert grade.blocker == "artifact_restricted_grammar"
    artifact.write_text("def coalesce(ranges):\n    return []\n")
    with pytest.raises(SmokeBlocked, match="assessor_source_locks"):
        grade_artifact(artifact, spec.assessment)
    assert "assessor_source_image_qualification" in preflight(spec)["blockers"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("quote.rates", []),
        ("quote.rates", {"gpt-6.1-sol": []}),
        ("module_sources", []),
        ("assessment", []),
        ("sources", ["private-input"]),
        ("pair_order", 1),
        ("full_stack_qualification", {}),
        ("quote.long_context_rates", {"gpt-6.1-sol": []}),
        ("assessment_authority", []),
        ("qualification_path", []),
    ],
)
def test_nested_malformed_cli_input_has_no_traceback(tmp_path, field, value):
    spec = campaign(tmp_path)
    raw = campaign_json(spec)
    target = raw
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(raw))
    result = CliRunner().invoke(
        smoke_cli.cli,
        [
            "preflight",
            "--spec",
            str(path),
            "--output-dir",
            str(spec.private_output_root / spec.campaign_id),
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.output) == {"error": "invalid_smoke_input"}
    assert "Traceback" not in result.output and str(tmp_path) not in result.output


def test_actual_cli_input_preflight_and_offline_report(tmp_path):
    spec = campaign(tmp_path)
    raw = campaign_json(spec)
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(raw))
    args = [
        "--spec",
        str(path),
        "--output-dir",
        str(spec.private_output_root / spec.campaign_id),
    ]
    runner = CliRunner()
    blocked = runner.invoke(smoke_cli.cli, ["preflight", *args])
    assert blocked.exit_code == 1
    assert set(IMPLEMENTATION_BLOCKERS) <= set(json.loads(blocked.output)["blockers"])
    result = runner.invoke(smoke_cli.cli, ["report", *args])
    assert result.exit_code == 0
    assert set(json.loads(result.output)["cells"]) == {"A0", "A1", "B1"}


def test_repeated_cancellation_cannot_drop_assessor_custody():
    import asyncio
    from live_smoke import join_with_custody

    async def check():
        gate = asyncio.Event()

        async def worker():
            await gate.wait()
            return "cleanup-confirmed"

        job = asyncio.create_task(worker())
        join = asyncio.create_task(join_with_custody(job))
        await asyncio.sleep(0)
        join.cancel()
        await asyncio.sleep(0)
        join.cancel()
        await asyncio.sleep(0)
        assert not job.cancelled() and not job.done() and not join.done()
        gate.set()
        result, cancelled = await join
        assert result == "cleanup-confirmed" and cancelled
        assert job.done() and not job.cancelled()

    asyncio.run(check())


def test_asserted_qualification_binding_not_execution_authenticity(tmp_path):
    from live_smoke import GRAMMAR_SHA256, VERSION

    spec = campaign(tmp_path)
    # Deliberately asserted synthetic schema control, never a live qualification.
    receipt = {
        "version": VERSION,
        "campaign_lock": spec.lock,
        "full_stack": {
            "models": {
                "A0": ["gpt-6.1-sol"] * 3,
                "B1": ["gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-sol"],
            },
            "effort": "high",
            "service_tier": "default",
            "transmitted_counts": 0,
            "child_tools": 0,
            "cleanup": "confirmed",
            "factory_negative_cases": [
                "missing",
                "replaced",
                "copied",
                "send_replaced",
                "dormant_after_cleanup",
            ],
            "sdk_version": "3.24.0",
        },
        "assessor": {
            "image": spec.assessment.image,
            "grammar_sha256": GRAMMAR_SHA256,
            "driver_sha256": spec.assessment.driver_sha256,
            "case_count": len(assessment_cases(17)),
            "correct_awards": {
                "union": 1,
                "touching_empty": 1,
                "invalid": 1,
                "immutability": 1,
            },
            "bad_controls": ["nonmerge", "bool", "mutation", "constant"],
            "hang": "invalid",
            "spoof_controls": "rejected_before_execution",
            "cleanup": "confirmed",
        },
        "controller": {
            "output_root": str(spec.private_output_root),
            "isolated": True,
            "resource_cost_policy": "verified_no_charge",
            "once_only": True,
            "deadline_cleanup": "qualified",
        },
    }
    path = tmp_path / "asserted-proof.json"
    path.write_text(json.dumps(receipt))
    qualified = replace(
        spec,
        qualification_path=path,
        qualification_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert qualified.qualification()["version"] == VERSION
    # References alone still cannot enable execution; image/source authority absent.
    assert not preflight(qualified)["ready"]
    with pytest.raises(SmokeBlocked, match="qualification_binding"):
        replace(qualified, pair_order=("B1", "A1")).qualification()
    path.write_text("{}")
    with pytest.raises(SmokeBlocked, match="qualification_receipt_changed"):
        qualified.qualification()
