"""Opt-in source-qualified real Anchors with intercepted HTTP, never live calls."""

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

__test__ = "amplifier_core" in sys.modules and "amplifier_foundation" in sys.modules
sys.path.insert(0, str(Path(__file__).parents[1]))


def sources():
    from anchors_adapter import RepositoryLock, Sources, repository_digest

    roots = json.loads(os.environ["ANCHORS_SOURCE_ROOTS"])
    from live_smoke import SourceLock, source_digest

    modules = {
        "core": "amplifier_core",
        "foundation": "amplifier_foundation",
        "provider": "amplifier_module_provider_openai",
        "sdk": "openai",
        "httpx": "httpx2",
        "loop": "amplifier_module_loop_streaming",
        "context": "amplifier_module_context_simple",
        "delegate": "amplifier_module_tool_delegate",
        "filesystem": "amplifier_module_tool_filesystem",
        "search": "amplifier_module_tool_search",
        "bash": "amplifier_module_tool_bash",
        "routing": "amplifier_module_hooks_routing",
        "shim": "amplifier_module_eval_openai",
        "core_native": "amplifier_core._engine",
    }
    runtime = []
    for name, module in modules.items():
        path = Path(importlib.import_module(module).__file__).resolve()
        if name != "core_native":
            path = path.parent
        runtime.append(
            (
                name,
                SourceLock(
                    "core_native" if name == "core_native" else "foundation",
                    path,
                    source_digest(path),
                ),
            )
        )
    return Sources(
        tuple(
            (
                name,
                RepositoryLock(
                    "foundation",
                    Path(path).resolve(),
                    repository_digest(Path(path).resolve()),
                ),
            )
            for name, path in sorted(roots.items())
        ),
        tuple(runtime),
    )


def output_text(text):
    return [
        {
            "type": "message",
            "id": "synthetic-message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]


def function(name, arguments):
    return [
        {
            "type": "function_call",
            "id": "synthetic-function",
            "call_id": "synthetic-" + name,
            "name": name,
            "arguments": json.dumps(arguments),
            "status": "completed",
        }
    ]


def response(model, output):
    return {
        "id": "synthetic-response",
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": "completed",
        "service_tier": "default",
        "error": None,
        "incomplete_details": None,
        "output": output,
        "parallel_tool_calls": True,
        "tools": [],
        "tool_choice": "auto",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 40,
            "total_tokens": 140,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 30},
        },
    }


@pytest.mark.parametrize("worker", ["gpt-6.1-sol", "gpt-6-luna"])
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing_factory",
        "wrong_model",
        "changed_instruction",
        "inherited_context",
        "repeat_delegate",
    ],
)
def test_stock_anchors_builder_repairs_real_repo(tmp_path, worker, fault):
    from anchors_adapter import AnchorsRun, DELEGATE_ARGUMENTS
    from anchors_transport import AnchorsLedger, Authority, Limits
    from test_interval_repair import GOOD_SOURCE, REGRESSION_SOURCE
    import httpx2 as httpx

    locked = sources()
    matrix = tmp_path / "matrix"
    matrix.mkdir()
    ledger = AnchorsLedger(
        tmp_path / "ledger",
        "synthetic-anchors",
        Limits(output_max=2048) if worker == "gpt-6-luna" else Limits(),
    )
    ledger.start_cell("A0")
    seen, root_calls, child_calls = [], [], []

    def receiver(policy):
        async def receive(request):
            body = json.loads(request.content)
            seen.append((policy.phase, body, str(request.url)))
            if policy.phase == "root":
                root_calls.append(body)
                arguments = dict(DELEGATE_ARGUMENTS)
                if fault == "changed_instruction":
                    arguments["instruction"] = "Return a root-authored solution."
                if fault == "inherited_context":
                    arguments["context_depth"] = "all"
                output = (
                    function("delegate", arguments)
                    if len(root_calls) == 1
                    else output_text("Done.")
                )
                if fault == "repeat_delegate" and len(root_calls) == 1:
                    repeated = function("delegate", arguments)
                    repeated[0]["call_id"] = "synthetic-repeat"
                    output += repeated
            else:
                child_calls.append(body)
                n = len(child_calls)
                output = (
                    function("read_file", {"file_path": "instructions.txt"})
                    if n == 1
                    else function(
                        "write_file",
                        {"file_path": "intervals.py", "content": GOOD_SOURCE.decode()},
                    )
                    if n == 2
                    else function(
                        "write_file",
                        {
                            "file_path": "test_regression.py",
                            "content": REGRESSION_SOURCE.decode(),
                        },
                    )
                    if n == 3
                    else output_text(
                        "Repaired; regression retained. NOT RUN: assessor-owned."
                    )
                )
            return httpx.Response(
                200,
                json=response(
                    "wrong-synthetic-model"
                    if fault == "wrong_model"
                    else body["model"],
                    output,
                ),
            )

        return httpx.MockTransport(receive)

    class Run(AnchorsRun):
        async def before_initialize(self, session):
            await super().before_initialize(session)
            if fault == "missing_factory":
                session.coordinator.register_capability(
                    "anchors.provider_factory", None
                )

    run = Run(
        locked,
        Authority(
            ledger,
            None,
            "https://gateway.example/v1",
            True,
            True,
            timeout_s=30 if worker == "gpt-6-luna" else 60,
        ),
        tmp_path / "repo",
        matrix,
        "A0",
        "gpt-6.1-sol",
        worker,
        "high",
        "high",
        receiver,
    )

    async def check():
        try:
            if fault:
                with pytest.raises(Exception):
                    await run.run()
                if fault == "repeat_delegate":
                    assert len(child_calls) == 4
                    assert len(run.sessions) == 2
                else:
                    assert not child_calls
                return
            artifact = await run.run()
            assert dict(artifact.files)["intervals.py"] == GOOD_SOURCE
            assert dict(artifact.files)["test_regression.py"] == REGRESSION_SOURCE
            assert len(run.sessions) == 2
            child = run.sessions[1]
            assert child.parent_id == run.sessions[0].session_id
            assert "delegate" not in child.coordinator.get("tools")
            assert child.coordinator.get_capability("session.spawn") is None
        finally:
            assert await run.close()

    asyncio.run(check())
    if fault:
        return
    assert [phase for phase, _, _ in seen] == [
        "root",
        "worker",
        "worker",
        "worker",
        "worker",
        "root",
    ]
    assert all(b["reasoning"]["effort"] == "high" for _, b, _ in seen)
    assert all(url == "https://gateway.example/v1/responses" for _, _, url in seen)
    assert [b["model"] for p, b, _ in seen if p == "worker"] == [worker] * 4
    assert ledger.accounting()["missing_cost_requests"] == 6
    assert ledger.accounting()["total_usd"] is None


def test_missing_transitive_source_refuses_without_network(tmp_path):
    from anchors_adapter import Sources, load_anchors
    from live_transport import SmokeBlocked

    with pytest.raises(SmokeBlocked, match="source_missing"):
        asyncio.run(load_anchors(Sources(()), tmp_path))
