"""Parent workflow controls; never execute repair bytes outside an OS sandbox."""

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent))
from anchors_campaign import (
    VERSION,
    BubblewrapSandbox,
    Campaign,
    IsolationAcceptance,
    IsolatedAssessor,
    ProcessResult,
    SandboxSpec,
    load_sources,
    read_solver_result,
    refresh_report,
    run_campaign,
    select_pair,
    solver_spec,
    projection_digest,
)
from anchors_adapter import Sources, RepositoryLock, repository_digest
from anchors_bridge import receiver_factory
from candidates import Snapshot
from interval_repair import Artifact, TASK_DIRECTORY, source_binding
from live_transport import SmokeBlocked, canonical, httpx
from repair_assessor import grade_receipt, make_request
from test_anchors_bridge import (
    ENDPOINT,
    ROOT,
    TOOLS,
    WORKER,
    body,
    payload,
    policy,
)
from test_interval_repair import GOOD_SOURCE, REGRESSION_SOURCE, DEVELOPMENT_CASES


def private_cases():
    return canonical(DEVELOPMENT_CASES)


def catalog():
    return Snapshot.from_dict(
        {
            "version": "anchors-candidates/v1",
            "family_masks": {"sol": "synthetic-sol-*", "luna": "synthetic-luna-*"},
            "required_capabilities": ["tools"],
            "provenance": "live",
            "freshness": "bounded_live",
            "reason": "complete",
            "binding_ref": "synthetic-binding",
            "candidates": [
                {
                    "family": "sol",
                    "id": ROOT,
                    "capabilities": ["tools"],
                    "latest": True,
                },
                {
                    "family": "luna",
                    "id": WORKER,
                    "capabilities": ["tools"],
                    "latest": True,
                },
            ],
        }
    )


def sandbox_spec(purpose):
    python = str(Path(sys.executable).resolve())
    readonly = (python,)
    return SandboxSpec(
        purpose,
        python,
        readonly,
        tuple((p, projection_digest(p)) for p in readonly),
        "synthetic-parent-resource-envelope",
        executable="/usr/bin/bwrap" if Path("/usr/bin/bwrap").exists() else python,
    )


def sandbox(purpose):
    spec = sandbox_spec(purpose)
    checks = {
        "network_denied",
        "credentials_absent",
        "private_paths_absent",
        "descendants_reaped",
        "resource_bounds",
        "uds_only" if purpose == "solver" else "assessor_controls",
    }
    return BubblewrapSandbox(
        spec,
        IsolationAcceptance(
            spec.lock, "synthetic-acceptance-NOT-OS-proof", frozenset(checks)
        ),
    )


def artifact():
    return Artifact(
        (
            ("intervals.py", GOOD_SOURCE),
            ("test_public.py", (TASK_DIRECTORY / "test_public.py").read_bytes()),
            ("test_regression.py", REGRESSION_SOURCE),
        ),
        source_binding(),
    )


def solver_output(worker=ROOT, cleanup=True):
    value = artifact()
    return canonical(
        {
            "version": VERSION,
            "artifact": {
                name: base64.b64encode(data).decode() for name, data in value.files
            },
            "binding": dict(value.binding),
            "resolution": [
                {
                    "provider": "openai",
                    "model": worker,
                    "config": {"reasoning_effort": "high"},
                }
            ],
            "cleanup": cleanup,
        }
    )


def synthetic_grade(request):
    """Asserted receipt, not execution. Existing driver controls are parent-only."""
    envelope = json.loads(request.input_json)
    binding = envelope["binding"]
    execution = {
        "schema": "interval-repair-receipt/v1",
        "request_sha256": request.sha256,
        "binding": binding,
        "status": "completed",
        "cleanup": True,
        "objective": {
            category: {
                "selected": sum(map(len, envelope["cases"]["categories"].values()))
                if category == "immutability"
                else len(values),
                "passed": sum(map(len, envelope["cases"]["categories"].values()))
                if category == "immutability"
                else len(values),
                "failed": 0,
                "errors": 0,
            }
            for category, values in envelope["cases"]["categories"].items()
        },
    }
    for phase in ("public", "regression_green", "regression_buggy"):
        execution[phase] = {
            "selected": 1,
            "run": 1,
            "failures": int(phase == "regression_buggy"),
            "assertion_failures": int(phase == "regression_buggy"),
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
            "selection_sha256": "a" * 64,
            "source_sha256": envelope["buggy_sha256"]
            if phase == "regression_buggy"
            else envelope["file_sha256"]["intervals.py"],
            "test_sha256": envelope["file_sha256"]["test_public.py"]
            if phase == "public"
            else envelope["file_sha256"]["test_regression.py"],
        }
    return canonical({"execution": execution, "cleanup": True})


def test_private_source_map_exact_fields_not_ambient_defaults():
    value = {"repositories": {}, "runtime": {}}
    assert load_sources(value) == Sources(())
    with pytest.raises(SmokeBlocked, match="source_map"):
        load_sources({})
    with pytest.raises(SmokeBlocked, match="source_lock"):
        load_sources({"repositories": {"synthetic": {"path": "/tmp"}}, "runtime": {}})


def test_pair_discovery_freezes_exact_latest_selected_catalog():
    async def check():
        calls = []

        async def models():
            calls.append(True)
            return [
                {"id": "synthetic-sol-5", "capabilities": ["tools"]},
                {"id": ROOT, "capabilities": ["tools"]},
                {"id": WORKER, "capabilities": ["tools"]},
            ]

        selected = SimpleNamespace(list_models=models)
        snapshot, pair = await select_pair(
            selected,
            "synthetic-binding",
            {"sol": "synthetic-sol-*", "luna": "synthetic-luna-*"},
            provenance="live",
        )
        assert pair == (ROOT, WORKER) and calls == [True]
        assert snapshot.provenance == "live"
        with pytest.raises(SmokeBlocked, match="catalog_unqualified"):
            await select_pair(
                selected,
                "synthetic-binding",
                {"sol": "synthetic-sol-*", "luna": "synthetic-luna-*"},
                provenance="fallback",
            )

    asyncio.run(check())


def test_sandbox_refuses_missing_or_wrong_independent_acceptance():
    # Read-only executable paths for command construction, never launch bwrap.
    spec = sandbox_spec("solver")
    python = spec.python
    with pytest.raises(SmokeBlocked, match="independent_isolation"):
        BubblewrapSandbox(spec, None)
    bad = IsolationAcceptance(spec.lock, "synthetic-receipt", frozenset())
    with pytest.raises(SmokeBlocked, match="independent_isolation"):
        BubblewrapSandbox(spec, bad)
    checks = frozenset(
        {
            "network_denied",
            "credentials_absent",
            "private_paths_absent",
            "descendants_reaped",
            "resource_bounds",
            "uds_only",
        }
    )
    # Synthetic acceptance tests policy wiring only; never invokes this sandbox.
    accepted = BubblewrapSandbox(
        spec, IsolationAcceptance(spec.lock, "synthetic", checks)
    )
    args = accepted.command(
        [python, "-B", "solver.py"], socket_path="/synthetic/socket"
    )
    assert "--unshare-all" in args and "--disable-userns" in args
    assert args[args.index("--uid") + 1] == "65534"
    assert "--cap-drop" in args and "--clearenv" in args
    assert "--share-net" not in args
    assert "/ipc/controller.sock" in args
    assert not any(name in args for name in ("OPENAI_API_KEY", str(Path.home())))
    changed = IsolationAcceptance("b" * 64, "synthetic", checks)
    with pytest.raises(SmokeBlocked, match="independent_isolation"):
        BubblewrapSandbox(spec, changed)


@pytest.mark.parametrize("mount", ["/", "/home", "/etc", "/proc", "/tmp"])
def test_personal_or_broad_store_mounts_refused(mount):
    with pytest.raises(SmokeBlocked, match="sandbox_broad_mount"):
        SandboxSpec(
            "solver",
            str(Path(sys.executable).resolve()),
            (mount,),
            ((mount, "synthetic"),),
            "synthetic-envelope",
        )


def test_assessor_concrete_runner_wraps_driver_and_cleanup(monkeypatch):
    request = make_request(artifact(), private_cases())
    observed = []
    isolated = sandbox("assessor")

    async def run(argv, stdin, **bounds):
        observed.append((argv, json.loads(stdin), bounds))
        receipt = json.loads(synthetic_grade(request))["execution"]
        return ProcessResult(0, canonical(receipt), True)

    monkeypatch.setattr(isolated, "run", run)

    async def check():
        assessor = IsolatedAssessor(isolated)
        raw = await assessor.run(request)
        grade = grade_receipt(request, raw)
        assert grade["success"] is True
        assert grade["criteria"]["regression_green"]
        assert grade["criteria"]["regression_red"]
        assert grade["cleanup"]
        assert base64.b64decode(observed[0][1]["request"]) == request.input_json
        assert observed[0][2]["wall_s"] == request.limits.wall_s
        assert "socket_path" not in observed[0][2]

    asyncio.run(check())


@pytest.mark.parametrize("fault", ["malformed", "hang", "output_limit", "cleanup"])
def test_assessor_failure_never_awards_fake_zero(fault, monkeypatch):
    request = make_request(artifact(), private_cases())
    isolated = sandbox("assessor")

    async def run(*args, **kwargs):
        if fault == "hang":
            raise TimeoutError
        if fault == "output_limit":
            raise SmokeBlocked("sandbox_output_limit")
        if fault == "malformed":
            return ProcessResult(0, b"{", True)
        receipt = json.loads(synthetic_grade(request))["execution"]
        return ProcessResult(0, canonical(receipt), False)

    monkeypatch.setattr(isolated, "run", run)

    async def check():
        runner = IsolatedAssessor(isolated)
        if fault == "cleanup":
            grade = grade_receipt(request, await runner.run(request))
            assert grade["success"] is True
            assert not grade["operational_ready"]
        else:
            with pytest.raises(Exception):
                await runner.run(request)

    asyncio.run(check())


def test_solver_result_allowlist_and_public_binding():
    value, result = read_solver_result(solver_output())
    assert dict(value.files)["intervals.py"] == GOOD_SOURCE
    assert result["resolution"][0]["model"] == ROOT
    corrupted = json.loads(solver_output())
    corrupted["root_response"] = "not allowed"
    with pytest.raises(SmokeBlocked, match="solver_result"):
        read_solver_result(canonical(corrupted))
    corrupted.pop("root_response")
    corrupted["artifact"]["../private"] = "YQ=="
    with pytest.raises(ValueError):
        read_solver_result(canonical(corrupted))


def test_two_arm_campaign_intercepted_wire_grade_and_report(tmp_path, monkeypatch):
    async def check():
        # Test source mapper exposes no runtime packages; this is orchestration,
        # not actual Anchors qualification. Real-stack command is documented.
        source = tmp_path / "source"
        source.mkdir()
        (source / "synthetic.txt").write_bytes(b"synthetic test source only")
        locked = Sources(
            (
                (
                    "amplifier-bundle-routing-matrix",
                    RepositoryLock(
                        "foundation",
                        source.resolve(),
                        repository_digest(source.resolve()),
                    ),
                ),
            )
        )
        output = tmp_path / "private"
        output.mkdir(mode=0o700)
        campaign = Campaign(
            "synthetic-pair",
            locked,
            ROOT,
            (ROOT, WORKER),
            "high",
            ENDPOINT,
            TOOLS,
            TOOLS,
            catalog(),
        )
        counts = []

        async def upstream(request):
            b = json.loads(request.content)
            counts.append(b["model"])
            return httpx.Response(200, json=payload(b["model"]))

        solver = sandbox("solver")

        async def solver_run(argv, stdin, **kwargs):
            envelope = json.loads(stdin)
            spec = envelope["spec"]
            assert "cases" not in spec
            factory = receiver_factory(
                kwargs["socket_path"], campaign.campaign_id, envelope["capability"]
            )
            for phase in ("root", "worker"):
                assigned = policy(spec["cell_id"], phase)
                # Root unchanged; A0 worker incumbent, B1 worker changed.
                if phase == "worker" and spec["cell_id"] == "A0":
                    from dataclasses import replace

                    assigned = replace(assigned, expected_model=ROOT)
                receiver = factory(assigned)
                try:
                    request = httpx.Request(
                        "POST",
                        ENDPOINT + "/responses",
                        content=canonical(body(assigned, phase)),
                        extensions={
                            "timeout": {
                                k: 60 for k in ("connect", "read", "write", "pool")
                            }
                        },
                    )
                    await receiver.handle_async_request(request)
                finally:
                    await receiver.aclose()
            return ProcessResult(0, solver_output(spec["worker_model"]), True)

        assessor = IsolatedAssessor(sandbox("assessor"))

        async def assessor_run(request):
            return synthetic_grade(request)

        monkeypatch.setattr(solver, "run", solver_run)
        monkeypatch.setattr(assessor, "run", assessor_run)

        report = await run_campaign(
            campaign,
            output,
            {"Authorization": "Bearer fake-test-key"},
            solver,
            assessor,
            private_cases(),
            upstream=httpx.MockTransport(upstream),
        )
        assert counts == [ROOT, ROOT, ROOT, WORKER]
        assert [c["completion"] for c in report["cells"]] == ["success", "success"]
        assert all(c["instrumentation"] == "valid" for c in report["cells"])
        assert all(c["delivered_revision"] is None for c in report["cells"])
        assert report["cost"]["requests"] == 4
        assert report["cost"]["total_usd"] is None
        assert report["promotion_supported"] is False
        assert report["reuse_identity"] == "unknown"
        saved = (output / campaign.campaign_id / "report.json").read_bytes()
        assert b"fake-test-key" not in saved and b"capability" not in saved
        assert not list(output.glob("ipc-*"))
        with pytest.raises(FileExistsError):
            await run_campaign(campaign, output, {}, solver, assessor, private_cases())

    asyncio.run(check())


def test_solver_spec_no_hidden_cases_or_credentials():
    campaign = Campaign(
        "synthetic",
        Sources(()),
        ROOT,
        (ROOT, WORKER),
        "high",
        ENDPOINT,
        TOOLS,
        TOOLS,
        catalog(),
    )
    spec = solver_spec(campaign, "B1", WORKER)
    assert "credential" not in canonical(spec).decode()
    assert "cases" not in spec
    assert spec["limits"]["dollar_ceiling"] is None
    assert spec["limits"]["whole_cell_s"] == 1200
    assert spec["limits"]["generation_max"] == 24
    assert spec["limits"]["output_max"] == 4096
    assert campaign.bounds.wall_s == 3600


def test_adjacent_reuse_cycle_changed_subset_plus_fresh_incumbent():
    from test_candidates import conditions, receipt

    conditions1 = conditions(ROOT, WORKER)
    old = receipt(ROOT, conditions1)
    old["model_revision"] = None
    old["identity_verified"] = False
    snap = Snapshot.from_dict(
        {
            "version": "anchors-candidates/v1",
            "family_masks": {"sol": "synthetic-sol-*", "luna": "synthetic-luna-*"},
            "required_capabilities": ["tools"],
            "provenance": "live",
            "freshness": "bounded_live",
            "reason": "complete",
            "binding_ref": conditions1["binding_ref"],
            "candidates": [
                {
                    "family": "sol",
                    "id": ROOT,
                    "capabilities": ["tools"],
                    "latest": True,
                },
                {
                    "family": "luna",
                    "id": WORKER,
                    "capabilities": ["tools"],
                    "latest": True,
                },
            ],
        }
    )
    first = refresh_report(snap, [], conditions1, ROOT)
    assert first["fresh_model_ids"] == [ROOT, WORKER]
    second = refresh_report(snap, [old], conditions1, ROOT)
    assert second["dispositions"][old["receipt_id"]] == "historical"
    assert second["fresh_model_ids"][0] == ROOT
    assert not second["reuse_ids"]
    assert old["model_revision"] is None


def test_cli_exception_is_redacted(tmp_path):
    from anchors_campaign_cli import main

    config = tmp_path / "config"
    config.write_bytes(b"{}")
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--private-config",
            str(config),
            "--parent-factory",
            "nonexistent_private_parent:run",
        ],
    )
    assert result.exit_code == 1
    assert result.output == '{"error":"campaign_refused"}\n'


def test_repeated_cancellation_keeps_custody_until_owned_process_reaped(monkeypatch):
    async def check():
        isolated = sandbox("assessor")
        killed = asyncio.Event()

        class Stream:
            def write(self, value):
                pass

            async def drain(self):
                pass

            def close(self):
                pass

            async def read(self, count):
                await asyncio.Event().wait()

        class Process:
            pid = 123456789  # Never signalled: killpg is intercepted below.
            returncode = None
            stdin, stdout, stderr = Stream(), Stream(), Stream()

            async def wait(self):
                await killed.wait()
                await asyncio.sleep(0.02)
                self.returncode = -9
                return -9

        process = Process()

        async def create(*args, **kwargs):
            assert kwargs["env"] == {} and kwargs["close_fds"] is True
            return process

        def kill(pid, sig):
            assert pid == process.pid
            killed.set()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
        monkeypatch.setattr(os, "killpg", kill)
        task = asyncio.create_task(
            isolated.run(["synthetic-python"], b"{}", wall_s=10, output_bytes=100)
        )

        async def active():
            while isolated.active is None:
                await asyncio.sleep(0)

        await asyncio.wait_for(active(), 2)
        task.cancel()
        await asyncio.wait_for(killed.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert isolated.active is None and process.returncode == -9

    asyncio.run(check())


def test_projection_content_change_invalidates_acceptance(tmp_path):
    python = str(Path(sys.executable).resolve())
    source = tmp_path / "projection"
    source.mkdir()
    (source / "module.py").write_bytes(b"synthetic")
    readonly = (python, str(source))
    spec = SandboxSpec(
        "solver",
        python,
        readonly,
        tuple((p, projection_digest(p)) for p in readonly),
        "synthetic-resource-envelope",
        executable="/usr/bin/bwrap" if Path("/usr/bin/bwrap").exists() else python,
    )
    before = spec.lock
    (source / "unexpected-config").write_bytes(b"synthetic-canary")
    with pytest.raises(SmokeBlocked, match="sandbox_projection_changed"):
        spec.lock
    assert before
