"""Explicit real-stack qualification, not part of dependency-light offline CI.

Invoke by pre-importing real Core/Foundation in the SAME pytest process. No
importorskip/xfail/stubs: every selected test requires installed native modules.
All model HTTP is intercepted; no credential or real endpoint is consulted.
"""

import asyncio
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# Ordinary offline CI has only pytest/Click/PyYAML. Explicit full-stack invocation
# must pre-import the real runtime; its imports fail before pytest if unavailable.
__test__ = "amplifier_core" in sys.modules and "amplifier_foundation" in sys.modules
sys.path.insert(0, str(Path(__file__).parents[1]))
from live_smoke import (
    ASSESSOR_DRIVER,
    SOURCE_LABELS,
    TASK_FILE,
    AssessmentSpec,
    CampaignSpec,
    CellSpec,
    Ledger,
    RealStack,
    SmokeLimits,
    SourceLock,
    arm_matrix,
    canonical,
    reconcile_cell,
    write_once,
    source_digest,
)
from live_transport import (
    ROOT_MODEL,
    WIRE_TOOL,
    AdmissionAuthority,
    AdmittedTransport,
    ModelRate,
    PriceQuote,
    SessionPolicy,
)


def make_campaign(tmp_path):
    modules = {
        "loop": Path(
            importlib.import_module("amplifier_module_loop_streaming").__file__
        ),
        "context": Path(
            importlib.import_module("amplifier_module_context_simple").__file__
        ),
        "shim": Path(importlib.import_module("amplifier_module_eval_openai").__file__),
        "routing": Path(
            importlib.import_module("amplifier_module_hooks_routing").__file__
        ),
    }
    paths = {
        "core_native": Path(importlib.import_module("amplifier_core._engine").__file__),
        "core_python": Path(importlib.import_module("amplifier_core").__file__).parent,
        "foundation": Path(
            importlib.import_module("amplifier_foundation").__file__
        ).parent,
        "provider": Path(
            importlib.import_module("amplifier_module_provider_openai").__file__
        ).parent,
        "sdk": Path(importlib.import_module("openai").__file__).parent,
        "httpx": Path(importlib.import_module("httpx2").__file__).parent,
        "task": TASK_FILE,
        "protocol": Path(sys.modules["live_smoke"].__file__).parent,
        "assessor": Path(sys.modules["live_smoke"].__file__).parent,
        **{k: v.parent for k, v in modules.items()},
    }
    assert set(paths) == SOURCE_LABELS
    now = datetime.now(timezone.utc)
    quote = PriceQuote(
        "synthetic-full-stack-quote",
        "synthetic-test-not-live-pricing",
        now - timedelta(seconds=1),
        now - timedelta(days=1),
        now + timedelta(days=1),
        "synthetic-binding",
        "default",
        "USD",
        {
            model: ModelRate(
                Decimal("2"), Decimal("1"), Decimal("2"), Decimal("4"), Decimal("0")
            )
            for model in (ROOT_MODEL, "gpt-6-astra")
        },
        1050000,
        "synthetic-qualified-total-window",
        {
            model: ModelRate(Decimal(i), Decimal(i), Decimal(i), Decimal(o), Decimal(0))
            for model, i, o in ((ROOT_MODEL, "5", "15"), ("gpt-6-astra", "25", "75"))
        },
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    return CampaignSpec(
        "synthetic-real-stack",
        tuple(
            SourceLock(label, path, source_digest(path))
            for label, path in paths.items()
        ),
        {label: path.parents[1] for label, path in modules.items()},
        quote,
        AssessmentSpec(
            "synthetic/python@sha256:" + "a" * 64,
            "not-qualified-for-execution",
            False,
            17,
        ),
        private,
        True,
        True,
    )


def payload(model, output):
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


def text_output(text):
    return [
        {
            "type": "message",
            "id": "synthetic-message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]


class RecordingReceiver:
    def __init__(self):
        self.requests = []
        self.root_calls = 0

    def factory(self, policy):
        import httpx2 as httpx

        async def receive(request):
            body = json.loads(request.content)
            self.requests.append(
                {"policy": dict(vars(policy)), "path": request.url.path, "body": body}
            )
            if request.url.path.endswith("input_tokens"):
                raise AssertionError("count must never reach receiver")
            if policy.phase == "worker":
                module = "def coalesce(ranges):\n    return []\n"
                output = text_output(json.dumps({"module": module}))
            elif self.root_calls == 0:
                self.root_calls += 1
                output = [
                    {
                        "type": "function_call",
                        "id": "synthetic-function",
                        "call_id": "synthetic-call",
                        "name": "delegate_coding",
                        "arguments": "{}",
                        "status": "completed",
                    }
                ]
            else:
                self.root_calls += 1
                output = text_output("Receipt acknowledged.")
            return httpx.Response(200, json=payload(body["model"], output))

        return httpx.MockTransport(receive)


@pytest.mark.parametrize("cell_id", ["A0", "B1"])
def test_real_native_root_and_routing_resolved_child(tmp_path, cell_id):
    # B1's isolated ledger needs accepted A0 only as scheduling setup. It is not
    # asserted as an observed model result, and does not enter comparison evidence.
    campaign = make_campaign(tmp_path)
    ledger = Ledger(tmp_path / "ledger.jsonl", campaign.lock, SmokeLimits())
    ledger.start_cell("A0")
    if cell_id == "B1":
        ledger.finish_cell(
            "A0", {"instrumentation": "valid", "synthetic_schedule_only": True}
        )
        ledger.start_cell(cell_id)
    cell = CellSpec(cell_id, "gpt-6-astra" if cell_id == "B1" else ROOT_MODEL)
    arm_dir = campaign.private_output_root / cell_id
    arm_dir.mkdir(mode=0o700)
    write_once(arm_dir / "interval-smoke.yaml", canonical(arm_matrix(cell)))
    recorder = RecordingReceiver()
    authority = AdmissionAuthority(
        ledger, campaign.quote, "https://api.openai.com/v1", True, True
    )
    stack = RealStack(
        campaign,
        cell,
        authority,
        arm_dir,
        "synthetic-not-a-credential",
        recorder.factory,
    )

    async def check():
        try:
            resolution = await stack.run(arm_dir)
            assert resolution["model"] == cell.worker_model
            assert len(stack.sessions) == 2
            assert stack.sessions[1].coordinator.get("tools") == {}
            assert stack.sessions[1].parent_id == stack.sessions[0].session_id
        finally:
            assert await stack.close(), "explicit SDK/HTTP/transport closure required"

    asyncio.run(check())
    calls = [r for r in recorder.requests if r["path"] == "/v1/responses"]
    assert [r["body"]["model"] for r in calls] == [
        ROOT_MODEL,
        cell.worker_model,
        ROOT_MODEL,
    ]
    assert all(r["body"]["reasoning"]["effort"] == "high" for r in calls)
    assert all(r["body"]["max_output_tokens"] == 4096 for r in calls)
    assert all(r["body"]["service_tier"] == "default" for r in calls)
    assert len(recorder.requests) == 3
    assert (
        sum(e["event"] == "denied" and e["kind"] == "count" for e in ledger.events())
        > 0
    )
    assert reconcile_cell(ledger, cell)["valid"]
    assert (arm_dir / "solution.py").read_bytes().startswith(b"def coalesce")
    # Artifact is retained only, never executed in this controller/subject DTU.


def test_real_sdk_http_count_generation_and_duplicate_guard(tmp_path):
    import httpx2 as httpx
    from openai import AsyncOpenAI

    campaign = make_campaign(tmp_path)
    ledger = Ledger(tmp_path / "sdk.jsonl", campaign.lock, SmokeLimits())
    ledger.start_cell("A0")
    policy = SessionPolicy(
        "A0", "synthetic-root", None, "controller", "root", ROOT_MODEL
    )
    seen = []

    async def receive(request):
        seen.append(json.loads(request.content))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        return httpx.Response(200, json=payload(ROOT_MODEL, text_output("synthetic")))

    transport = AdmittedTransport(
        AdmissionAuthority(
            ledger, campaign.quote, "https://api.openai.com/v1", True, True
        ),
        policy,
        lambda: None,
        lambda: "synthetic-logical",
        httpx.MockTransport(receive),
    )

    async def check():
        http = httpx.AsyncClient(transport=transport, trust_env=False, timeout=60)
        sdk = AsyncOpenAI(
            api_key="synthetic",
            base_url="https://api.openai.com/v1",
            max_retries=0,
            http_client=http,
        )
        count_body = {
            "model": ROOT_MODEL,
            "input": [{"role": "user", "content": "synthetic"}],
            "reasoning": {"effort": "high"},
            "tools": [WIRE_TOOL],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        try:
            with pytest.raises(Exception):
                await sdk.responses.input_tokens.count(**count_body)
            await sdk.responses.create(
                **count_body,
                max_output_tokens=4096,
                store=False,
                service_tier="default",
            )
            with pytest.raises(Exception):
                await sdk.responses.create(
                    **count_body,
                    max_output_tokens=4096,
                    store=False,
                    service_tier="default",
                )
            assert len(seen) == 1
        finally:
            await sdk.close()
            assert sdk.is_closed() and http.is_closed and transport.closed

    asyncio.run(check())
    events = ledger.events()
    assert not ledger.unresolved(events)
    assert [e["event"] for e in events].count("reserve") == 1
    assert ledger.liability(events) == Decimal("0.000340")


def test_real_shim_missing_factory_and_unsafe_config():
    shim = importlib.import_module("amplifier_module_eval_openai")
    from amplifier_core import AmplifierSession

    session = AmplifierSession(
        {
            "session": {
                "orchestrator": {"module": "loop-streaming"},
                "context": {"module": "context-simple"},
            },
            "providers": [],
            "tools": [],
            "hooks": [],
        }
    )
    config = {
        "default_model": ROOT_MODEL,
        "reasoning_effort": "high",
        "max_output_tokens": 4096,
        "max_retries": 0,
        "auto_continue": False,
        "use_streaming": False,
        "reasoning_replay_scope": "none",
        "timeout": 60,
        "close_timeout": 10,
        "extra_request_params": {"service_tier": "default", "include": []},
    }

    async def dormant_check():
        cleanup = await shim.mount(session.coordinator, config)
        provider = session.coordinator.get("providers", "openai")
        assert type(provider) is shim.UnavailableProvider
        assert provider.get_info().capabilities == []
        for closed in (False, True):
            if closed:
                await cleanup()
            with pytest.raises(RuntimeError, match="smoke_factory_missing"):
                await provider.complete(None)
            with pytest.raises(RuntimeError, match="smoke_factory_missing"):
                await provider.list_models()
            with pytest.raises(RuntimeError, match="smoke_factory_missing"):
                provider.parse_tool_calls(None)

    asyncio.run(dormant_check())
    with pytest.raises(RuntimeError, match="smoke_provider_config"):
        asyncio.run(shim.mount(session.coordinator, {**config, "api_key": "synthetic"}))
    assert (
        type(session.coordinator.get("providers", "openai")) is shim.UnavailableProvider
    )


def test_receiver_no_request_for_bad_effort_native_sdk(tmp_path):
    import httpx2 as httpx
    from openai import AsyncOpenAI

    campaign = make_campaign(tmp_path)
    ledger = Ledger(tmp_path / "guard.jsonl", campaign.lock, SmokeLimits())
    ledger.start_cell("A0")
    seen = []

    async def receive(request):
        seen.append(request)
        return httpx.Response(500, json={})

    transport = AdmittedTransport(
        AdmissionAuthority(
            ledger, campaign.quote, "https://api.openai.com/v1", True, True
        ),
        SessionPolicy("A0", "synthetic-root", None, "controller", "root", ROOT_MODEL),
        lambda: None,
        lambda: "id",
        httpx.MockTransport(receive),
    )

    async def check():
        http = httpx.AsyncClient(transport=transport, trust_env=False, timeout=60)
        sdk = AsyncOpenAI(
            api_key="synthetic",
            base_url="https://api.openai.com/v1",
            max_retries=3,
            http_client=http,
        )
        try:
            with pytest.raises(Exception):
                await sdk.responses.create(
                    model=ROOT_MODEL,
                    input=[],
                    reasoning={"effort": "low"},
                    max_output_tokens=4096,
                    store=False,
                    tools=[WIRE_TOOL],
                    tool_choice="auto",
                    parallel_tool_calls=True,
                )
            assert seen == []
            assert ledger.unresolved(ledger.events()) == []
        finally:
            await sdk.close()

    asyncio.run(check())


@pytest.mark.parametrize("fault", ["timeout", "partial", "wrong_model", "oversize"])
def test_actual_http_fault_retains_unknown_liability(tmp_path, fault):
    import httpx2 as httpx
    from openai import AsyncOpenAI

    campaign = make_campaign(tmp_path)
    ledger = Ledger(tmp_path / "fault.jsonl", campaign.lock, SmokeLimits())
    ledger.start_cell("A0")
    policy = SessionPolicy(
        "A0", "synthetic-root", None, "controller", "root", ROOT_MODEL
    )
    seen = []

    async def receive(request):
        seen.append(request.url.path)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        if fault == "timeout":
            raise httpx.ReadTimeout("synthetic")
        result = payload(ROOT_MODEL, text_output("synthetic"))
        if fault == "partial":
            result["usage"] = {"input_tokens": 100}
        elif fault == "wrong_model":
            result["model"] = "gpt-6-astra"
        else:
            return httpx.Response(200, content=b"x" * 262145)
        return httpx.Response(200, json=result)

    transport = AdmittedTransport(
        AdmissionAuthority(
            ledger, campaign.quote, "https://api.openai.com/v1", True, True
        ),
        policy,
        lambda: None,
        lambda: "synthetic-logical",
        httpx.MockTransport(receive),
    )

    async def check():
        http = httpx.AsyncClient(transport=transport, trust_env=False, timeout=60)
        sdk = AsyncOpenAI(
            api_key="synthetic",
            base_url="https://api.openai.com/v1",
            max_retries=2,
            http_client=http,
        )
        params = {
            "model": ROOT_MODEL,
            "input": [{"role": "user", "content": "synthetic"}],
            "reasoning": {"effort": "high"},
            "tools": [WIRE_TOOL],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        try:
            with pytest.raises(Exception):
                await sdk.responses.input_tokens.count(**params)
            with pytest.raises(Exception):
                await sdk.responses.create(
                    **params,
                    max_output_tokens=4096,
                    store=False,
                    service_tier="default",
                )
            assert seen == ["/v1/responses"]
            unresolved = ledger.unresolved(ledger.events())
            assert len(unresolved) == 1
            assert ledger.liability(ledger.events()) == Decimal(
                unresolved[0]["reserved_usd"]
            )
        finally:
            await sdk.close()
            assert sdk.is_closed() and http.is_closed and transport.closed

    asyncio.run(check())


def test_real_modules_and_assessor_are_distinct():
    import amplifier_core
    from amplifier_module_provider_openai import OpenAIProvider
    from amplifier_module_eval_openai import mount

    assert Path(amplifier_core._engine.__file__).suffix == ".so"
    assert "amplifier_module_provider_openai" in OpenAIProvider.__module__
    assert "amplifier_module_eval_openai" in mount.__module__
    assert "expected" not in ASSESSOR_DRIVER
    assert not os.environ.get("SMOKE_OPENAI_CREDENTIAL")


@pytest.mark.parametrize("phase", ["root", "worker"])
@pytest.mark.parametrize("tamper", ["missing", "replaced", "copied"])
def test_actual_session_factory_authority_negative(tmp_path, phase, tamper):
    campaign = make_campaign(tmp_path)
    value = Ledger(tmp_path / "negative.jsonl", campaign.lock, SmokeLimits())
    value.start_cell("A0")
    cell = CellSpec("A0", ROOT_MODEL)
    arm_dir = campaign.private_output_root / "negative"
    arm_dir.mkdir(mode=0o700)
    write_once(arm_dir / "interval-smoke.yaml", canonical(arm_matrix(cell)))
    recorder = RecordingReceiver()

    class TamperedStack(RealStack):
        async def before_initialize(self, session):
            await super().before_initialize(session)
            selected = "worker" if session.parent_id else "root"
            if selected == phase:
                original = self.factories[session.session_id]
                replacement = (
                    None
                    if tamper == "missing"
                    else (lambda coordinator, config: original(coordinator, config))
                    if tamper == "copied"
                    else (lambda coordinator, config: None)
                )
                session.coordinator.register_capability(
                    "smoke.provider_factory", replacement
                )

    stack = TamperedStack(
        campaign,
        cell,
        AdmissionAuthority(
            value,
            campaign.quote,
            "https://api.openai.com/v1",
            True,
            True,
        ),
        arm_dir,
        "synthetic",
        recorder.factory,
    )

    async def check():
        try:
            with pytest.raises(Exception):
                await stack.run(arm_dir)
            # Child refusal permits the one initiating root generation, but no
            # child or acknowledgement transport; root refusal permits none.
            assert len(recorder.requests) == (0 if phase == "root" else 1)
            assert all(r["policy"]["phase"] == "root" for r in recorder.requests)
        finally:
            assert await stack.close()

    asyncio.run(check())


def test_factory_replaced_after_mount_refuses_at_send(tmp_path):
    campaign = make_campaign(tmp_path)
    value = Ledger(tmp_path / "send.jsonl", campaign.lock, SmokeLimits())
    value.start_cell("A0")
    cell = CellSpec("A0", ROOT_MODEL)
    arm_dir = campaign.private_output_root / "send"
    arm_dir.mkdir(mode=0o700)
    write_once(arm_dir / "interval-smoke.yaml", canonical(arm_matrix(cell)))
    recorder = RecordingReceiver()

    class SendTamperedStack(RealStack):
        checks = 0

        def verify_session(self, session):
            self.checks += 1
            if self.checks > 1:
                session.coordinator.register_capability(
                    "smoke.provider_factory",
                    lambda coordinator, config: None,
                )
            return super().verify_session(session)

    stack = SendTamperedStack(
        campaign,
        cell,
        AdmissionAuthority(
            value,
            campaign.quote,
            "https://api.openai.com/v1",
            True,
            True,
        ),
        arm_dir,
        "synthetic",
        recorder.factory,
    )

    async def check():
        try:
            with pytest.raises(Exception):
                await stack.run(arm_dir)
            assert recorder.requests == []
        finally:
            assert await stack.close()

    asyncio.run(check())
