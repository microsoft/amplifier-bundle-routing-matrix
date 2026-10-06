"""Synthetic wire controls. All sockets/files use pytest's worktree basetemp."""

import asyncio
import base64
import json
import secrets
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from anchors_bridge import (
    CampaignBounds,
    CellAdmission,
    Controller,
    Receiver,
    WIRE_VERSION,
    read_frame,
    selected_headers,
    socket_address,
    write_frame,
)
from anchors_transport import AnchorsLedger, Authority, Limits, Policy
from live_transport import SmokeBlocked, canonical, httpx

ENDPOINT = "https://gateway.example/v1"
ROOT = "synthetic-sol-6"
WORKER = "synthetic-luna-6"
TOOLS = canonical(
    [
        {
            "type": "function",
            "name": "synthetic_tool",
            "description": "Synthetic.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "strict": False,
        }
    ]
)


def admission(cell="A0"):
    return CellAdmission(cell, ROOT, WORKER, "high", "high", TOOLS, TOOLS)


def policy(cell="A0", phase="root"):
    return Policy(
        cell,
        "synthetic-" + cell + "-" + phase,
        None if phase == "root" else "synthetic-" + cell + "-root",
        "controller" if phase == "root" else "coding",
        phase,
        ROOT if phase == "root" else WORKER,
        "high",
        tuple(json.loads(TOOLS)),
    )


def body(assigned=None, text="synthetic", limits=Limits()):
    assigned = assigned or policy()
    return {
        "model": assigned.expected_model,
        "reasoning": {"effort": "high"},
        "tools": list(assigned.wire_tools),
        "input": [{"role": "user", "content": text}],
        "max_output_tokens": limits.output_max,
        "store": False,
        "stream": False,
        "service_tier": "default",
        "include": [],
    }


def payload(model, response_id=None):
    return {
        "id": response_id or secrets.token_hex(16),
        "model": model,
        "status": "completed",
        "service_tier": "default",
        "usage": {
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }


def frame(controller, assigned=None, text="synthetic"):
    assigned = assigned or policy()
    return {
        "version": WIRE_VERSION,
        "campaign_id": controller.campaign_id,
        "capability": controller.capability(assigned.cell_id),
        "request_id": secrets.token_hex(16),
        "context": {
            k: getattr(assigned, k)
            for k in ("cell_id", "session_id", "parent_id", "phase", "role_origin")
        },
        "method": "POST",
        "url": ENDPOINT + "/responses",
        "timeout": {k: 60 for k in ("connect", "read", "write", "pool")},
        "body": base64.b64encode(canonical(body(assigned, text))).decode(),
    }


def controller(tmp_path, *, bounds=CampaignBounds(), limits=Limits(), reply=None):
    ledger = AnchorsLedger(tmp_path / "ledger", "synthetic-campaign-lock", limits)
    seen = []

    async def upstream(request):
        assert len(ledger.unresolved(ledger.events())) == 1
        seen.append(request)
        if reply:
            return await reply(request)
        return httpx.Response(200, json=payload(json.loads(request.content)["model"]))

    value = Controller(
        "synthetic-campaign",
        Authority(ledger, None, ENDPOINT, True, True),
        (admission(), admission("B1")),
        selected_headers(
            "SYNTHETIC_CREDENTIAL", {"SYNTHETIC_CREDENTIAL": "fake-test-key"}
        ),
        bounds=bounds,
        upstream=httpx.MockTransport(upstream),
    )
    ledger.start_cell("A0")
    return value, ledger, seen


def test_actual_uds_httpx2_roundtrip_no_sdk_headers_or_key_echo(tmp_path):
    async def check():
        server, ledger, seen = controller(tmp_path)
        socket = tmp_path / "controller.sock"
        await server.start(socket)
        receiver = Receiver(
            socket, server.campaign_id, server.capability("A0"), policy()
        )
        try:
            request = httpx.Request(
                "POST",
                ENDPOINT + "/responses",
                content=canonical(body()),
                headers={"Authorization": "Bearer dummy-sdk", "X-Unknown": "not-sent"},
                extensions={
                    "timeout": {k: 60 for k in ("connect", "read", "write", "pool")}
                },
            )
            result = await receiver.handle_async_request(request)
            assert result.json()["model"] == ROOT
            assert "fake-test-key" not in result.text
            assert seen[0].headers["Authorization"] == "Bearer fake-test-key"
            assert "X-Unknown" not in seen[0].headers
            assert str(seen[0].url) == ENDPOINT + "/responses"
            assert ledger.accounting()["requests"] == 1
            assert ledger.accounting()["total_usd"] is None
            assert ledger.accounting()["unresolved_requests"] == 0
            assert "fake-test-key" not in ledger.path.read_text()
        finally:
            await receiver.aclose()
            await server.close()
        assert not socket.exists() and not server._tasks

    asyncio.run(check())


@pytest.mark.parametrize(
    "mutation",
    [
        "auth",
        "campaign",
        "cell",
        "phase",
        "role",
        "worker_parent",
        "model",
        "effort",
        "schema",
        "output",
        "body_limit",
        "count",
        "get",
        "url",
        "timeout",
        "fields",
        "duplicate_json",
    ],
)
def test_independent_controller_negative_admission(tmp_path, mutation):
    async def check():
        server, ledger, seen = controller(tmp_path)
        value = frame(server)
        b = body()
        if mutation == "auth":
            value["capability"] = "wrong"
        elif mutation == "campaign":
            value["campaign_id"] = "wrong"
        elif mutation == "cell":
            value["context"]["cell_id"] = "B1"
        elif mutation == "phase":
            value["context"]["phase"] = "auxiliary"
        elif mutation == "role":
            value["context"]["role_origin"] = "security-audit"
        elif mutation == "worker_parent":
            value = frame(server, policy(phase="worker"))
        elif mutation in {"model", "effort", "schema", "output"}:
            if mutation == "model":
                b["model"] = "synthetic-other"
            elif mutation == "effort":
                b["reasoning"]["effort"] = "low"
            elif mutation == "schema":
                b["tools"][0]["parameters"] = {}
            else:
                b["max_output_tokens"] = 4097
            value["body"] = base64.b64encode(canonical(b)).decode()
        elif mutation == "body_limit":
            value["body"] = base64.b64encode(b" " * 131073).decode()
        elif mutation == "count":
            value["url"] += "/input_tokens"
        elif mutation == "get":
            value["method"] = "GET"
        elif mutation == "url":
            value["url"] = "https://other.example/responses"
        elif mutation == "timeout":
            value["timeout"]["read"] = 61
        elif mutation == "fields":
            value["headers"] = {"Authorization": "solver-supplied"}
        else:
            value["body"] = base64.b64encode(b'{"model":"a","model":"b"}').decode()
        try:
            with pytest.raises(Exception):
                await server.dispatch(value)
            assert seen == []
            assert ledger.accounting()["requests"] == 0
        finally:
            await server.close()

    asyncio.run(check())


def test_bound_context_and_fresh_ids_cannot_rebind_or_replay(tmp_path):
    async def check():
        server, ledger, seen = controller(tmp_path)
        original = frame(server)
        try:
            await server.dispatch(original)
            with pytest.raises(SmokeBlocked, match="ipc_replay"):
                await server.dispatch(original)
            with pytest.raises(SmokeBlocked, match="logical_or_payload_replay"):
                await server.dispatch(frame(server))
            root = replace(policy(), session_id="another-root")
            with pytest.raises(SmokeBlocked, match="ipc_root_rebind"):
                await server.dispatch(frame(server, root, "other"))
            await server.dispatch(frame(server, policy(phase="worker"), "worker"))
            worker = replace(policy(phase="worker"), session_id="another-worker")
            with pytest.raises(SmokeBlocked, match="ipc_worker_lineage"):
                await server.dispatch(frame(server, worker, "other-worker"))
            assert len(seen) == ledger.accounting()["requests"] == 2
        finally:
            await server.close()

    asyncio.run(check())


@pytest.mark.parametrize("kind", ["requests", "tokens"])
def test_whole_campaign_bounds_do_not_reset_at_second_cell(tmp_path, kind):
    async def check():
        limits = Limits(native_context_max=100, output_max=4096)
        bounds = CampaignBounds(
            requests=2 if kind == "requests" else 48,
            reserved_tokens=8392 if kind == "tokens" else 50_596_608,
        )
        server, ledger, seen = controller(tmp_path, bounds=bounds, limits=limits)
        try:
            await server.dispatch(frame(server))
            ledger.finish_cell("A0", {"instrumentation": "valid"})
            ledger.start_cell("B1")
            await server.dispatch(frame(server, policy("B1"), "second"))
            with pytest.raises(SmokeBlocked, match="campaign_(request|token)_cap"):
                await server.dispatch(frame(server, policy("B1", "worker"), "third"))
            assert len(seen) == ledger.accounting()["requests"] == 2
        finally:
            await server.close()

    asyncio.run(check())


@pytest.mark.parametrize(
    "failure",
    [
        "missing_usage",
        "status",
        "credential_echo",
        "exception",
        "oversize",
        "repeated_id",
    ],
)
def test_failed_response_retains_custody_and_blocks_next_wire(tmp_path, failure):
    async def check():
        async def reply(request):
            p = payload(ROOT, "synthetic-fixed-response")
            if failure == "missing_usage":
                del p["usage"]
            elif failure == "status":
                p["status"] = "incomplete"
            elif failure == "credential_echo":
                p["output"] = "fake-test-key"
            elif failure == "exception":
                raise RuntimeError("fake-test-key must never be logged")
            elif failure == "oversize":
                return httpx.Response(200, content=b" " * 262145)
            return httpx.Response(200, json=p)

        server, ledger, seen = controller(tmp_path, reply=reply)
        try:
            if failure == "repeated_id":
                await server.dispatch(frame(server, text="first"))
            with pytest.raises(Exception):
                await server.dispatch(frame(server, text="second"))
            assert ledger.accounting()["unresolved_requests"] == 1
            with pytest.raises(SmokeBlocked, match="http_active_or_unresolved"):
                await server.dispatch(frame(server, text="third"))
            assert ledger.accounting()["total_usd"] is None
            assert "fake-test-key" not in ledger.path.read_text()
            assert len(seen) == (2 if failure == "repeated_id" else 1)
        finally:
            await server.close()

    asyncio.run(check())


def test_uds_bad_auth_redacted_and_cleanup(tmp_path):
    async def check():
        server, _, seen = controller(tmp_path)
        path = tmp_path / "socket"
        await server.start(path)
        try:
            with socket_address(path) as address:
                reader, writer = await asyncio.open_unix_connection(address)
            try:
                value = frame(server)
                value["capability"] = "fake-test-key"
                await write_frame(writer, value)
                reply = await read_frame(reader)
                assert reply == {"ok": False, "error": "controller_refused"}
                assert not seen
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.close()

    asyncio.run(check())


def test_optional_env_projection_never_reads_other_config():
    class Selected(dict):
        def get(self, name):
            assert name == "SYNTHETIC_CREDENTIAL"
            return "fake-test-key"

    assert selected_headers("SYNTHETIC_CREDENTIAL", Selected()) == {
        "Authorization": "Bearer fake-test-key"
    }
    with pytest.raises(SmokeBlocked):
        selected_headers("lowercase-reference", {})


def test_json_boolean_integer_schema_substitution_is_not_exact(tmp_path):
    async def check():
        server, ledger, seen = controller(tmp_path)
        value = frame(server)
        parsed = json.loads(base64.b64decode(value["body"]))
        parsed["tools"][0]["strict"] = 0  # Python equality is not JSON identity.
        value["body"] = base64.b64encode(canonical(parsed)).decode()
        try:
            with pytest.raises(SmokeBlocked, match="ipc_schema_exact"):
                await server.dispatch(value)
            assert seen == [] and ledger.accounting()["requests"] == 0
        finally:
            await server.close()

    asyncio.run(check())


def test_escaped_credential_echo_rejected_before_settlement(tmp_path):
    async def check():
        async def reply(request):
            data = canonical({**payload(ROOT), "debug": "fake-test-key"})
            data = data.replace(b"fake-test-key", b"\\u0066ake-test-key")
            return httpx.Response(200, content=data)

        server, ledger, _ = controller(tmp_path, reply=reply)
        try:
            with pytest.raises(SmokeBlocked, match="ipc_credential_echo"):
                await server.dispatch(frame(server))
            assert ledger.accounting()["unresolved_requests"] == 1
        finally:
            await server.close()

    asyncio.run(check())


@pytest.mark.parametrize("elapsed,admitted", [(3599.99, True), (3600, False)])
def test_whole_campaign_wall_boundary(tmp_path, elapsed, admitted):
    async def check():
        server, ledger, seen = controller(tmp_path)
        # Don't modify asyncio's own clock; only replace this controller's start.
        import time

        server._started = time.monotonic() - elapsed
        try:
            if admitted:
                await server.dispatch(frame(server))
                assert len(seen) == 1
            else:
                with pytest.raises(SmokeBlocked, match="campaign_deadline"):
                    await server.dispatch(frame(server))
                assert ledger.accounting()["requests"] == 0
        finally:
            await server.close()

    asyncio.run(check())
