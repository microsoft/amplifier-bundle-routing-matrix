"""Observe-only controls with fabricated tooling, usage and quotes; no live prices.

Pure ledger/authority controls always collect. Only TestHTTPXTransport is gated
by the transport's optional HTTPX dependency, not by Core, Foundation or an SDK.
The root session owns execution, selected-count verification and any fixes.
"""

import asyncio
import copy
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import anchors_transport
import live_transport
from anchors_transport import AnchorsLedger, Authority, Limits, Policy, Quote, Transport
from live_transport import ModelRate, SmokeBlocked, canonical, fingerprint, strict_json

GATEWAY = "https://gateway.example/v1"
MODELS = {"root": "synthetic-controller-model", "worker": "synthetic-builder-model"}
TOOL_NAMES = {
    "root": ("delegate",),
    "worker": ("read_file", "write_file", "edit_file", "grep", "glob", "bash"),
}


def policy(phase="worker", effort="high"):
    tools = tuple(
        {
            "type": "function",
            "name": name,
            "description": "Synthetic tooling schema, not a mounted tool.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            "strict": False,
        }
        for name in TOOL_NAMES[phase]
    )
    return Policy(
        "A0",
        f"synthetic-{phase}",
        None if phase == "root" else "synthetic-root",
        "controller" if phase == "root" else "coding",
        phase,
        MODELS[phase],
        effort,
        tools,
    )


def body(assigned=None, limits=None, text="synthetic input"):
    assigned = assigned or policy()
    limits = limits or Limits()
    return {
        "model": assigned.expected_model,
        "reasoning": {"effort": assigned.expected_effort, "summary": "auto"},
        "max_output_tokens": limits.output_max,
        "store": False,
        "stream": False,
        "service_tier": "default",
        "include": [],
        "tools": copy.deepcopy(list(assigned.wire_tools)),
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
            {
                "type": "function_call",
                "call_id": "synthetic-call",
                "name": assigned.wire_tools[0]["name"],
                "arguments": '{"text":"synthetic argument"}',
            },
            {
                "type": "function_call_output",
                "call_id": "synthetic-call",
                "output": "synthetic tool output",
            },
        ],
    }


def response(model=MODELS["worker"]):
    return {
        "id": "synthetic-response",
        "model": model,
        "status": "completed",
        "service_tier": "default",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 40,
            "total_tokens": 140,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 30},
        },
    }


def ledger(tmp_path, limits=None):
    value = AnchorsLedger(
        tmp_path / "ledger.jsonl", "synthetic-lock", limits or Limits()
    )
    value.start_cell("A0")
    return value


def quote(limits=None):
    """Arbitrary synthetic USD/million-token rates, never live pricing evidence."""
    limits = limits or Limits()
    now = datetime.now(timezone.utc)
    ordinary = ModelRate(*(Decimal(v) for v in ("2", "1", "2", "4", "0")))
    upper = ModelRate(*(Decimal(v) for v in ("3", "1", "3", "6", "0")))
    return Quote(
        revision="synthetic-quote",
        source="synthetic-test-not-live-pricing",
        verified_at=now - timedelta(seconds=1),
        effective_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
        binding_ref="synthetic-binding",
        service_tier="default",
        currency="USD",
        rates={model: ordinary for model in MODELS.values()},
        native_context_max=limits.native_context_max,
        window_source="synthetic-native-window",
        long_context_rates={model: upper for model in MODELS.values()},
    )


@pytest.mark.parametrize("phase", ["root", "worker"])
@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh"])
def test_tooling_profiles_reserve_exact_model_effort_and_schemas(
    tmp_path, phase, effort
):
    assigned = policy(phase, effort)
    value = ledger(tmp_path)
    request = body(assigned)
    reservation = value.reserve(
        assigned, request, "generation", None, "synthetic-logical"
    )
    assert reservation["expected_model"] == MODELS[phase]
    assert reservation["wire_effort"] == effort
    assert reservation["projection"] == fingerprint(request)
    assert reservation["request_body_bytes"] == len(canonical(request))
    assert reservation["reserved_tokens"] == 1050000 + 4096
    assert reservation["reserved_usd"] is None
    assert reservation["quote_lock"] is None
    assert "synthetic input" not in value.path.read_text()
    assert "synthetic tool output" not in value.path.read_text()


def test_complete_unpriced_usage_settles_custody_not_dollars_and_survives_reopen(
    tmp_path,
):
    value = ledger(tmp_path)
    for index in range(2):
        reservation = value.reserve(
            policy(),
            body(text=f"synthetic input {index}"),
            "generation",
            None,
            str(index),
        )
        value.response(reservation, response(), None, 200)
    observed = [e for e in value.events() if e["event"] == "response"]
    settled = [e for e in value.events() if e["event"] == "settle"]
    assert all(e["valid"] and e["priced_usd"] is None for e in observed)
    assert all(e["usd"] is None for e in settled)
    assert observed[0]["usage"] == response()["usage"]
    expected = {
        "requests": 2,
        "missing_cost_requests": 2,
        "known_usd_lower_bound": "0",
        "total_usd": None,
        "unresolved_requests": 0,
    }
    assert value.accounting() == expected
    reopened = AnchorsLedger(value.path, "synthetic-lock", value.limits)
    assert reopened.accounting() == expected


@pytest.mark.parametrize("fault", [False, True])
def test_unfinished_attempt_remains_unresolved_across_reopen(tmp_path, fault):
    value = ledger(tmp_path)
    reservation = value.reserve(
        policy(), body(), "generation", None, "synthetic-logical"
    )
    if fault:
        value.fault(reservation)
    reopened = AnchorsLedger(value.path, "synthetic-lock", value.limits)
    assert reopened.unresolved(reopened.events()) == [reservation]
    assert reopened.accounting()["missing_cost_requests"] == 1
    assert reopened.accounting()["total_usd"] is None
    before = reopened.events()
    with pytest.raises(SmokeBlocked, match="^http_active_or_unresolved$"):
        reopened.reserve(
            policy(), body(text="changed"), "generation", None, "new-logical"
        )
    assert reopened.events() == before


def test_synthetic_quote_settles_cache_and_reasoning_without_double_billing(tmp_path):
    value = ledger(tmp_path)
    quoted = quote()
    reservation = value.reserve(
        policy(), body(), "generation", quoted, "synthetic-logical"
    )
    assert quoted.reserve(MODELS["worker"]) == Decimal("3.18")
    assert reservation["reserved_usd"] == "3.18"
    assert reservation["quote_lock"] == quoted.lock
    value.response(reservation, response(), quoted, 200)
    assert value.accounting() == {
        "requests": 1,
        "missing_cost_requests": 0,
        "known_usd_lower_bound": "0.000340",
        "total_usd": "0.000340",
        "unresolved_requests": 0,
    }


def test_optional_dollar_ceiling_requires_quote_before_reservation(tmp_path):
    value = ledger(tmp_path, Limits(dollar_ceiling=Decimal("3.18")))
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^ceiling_requires_quote$"):
        value.reserve(policy(), body(), "generation", None, "synthetic-logical")
    assert value.events() == before


def test_synthetic_quoted_ceiling_accepts_equality_then_includes_settled_cost(tmp_path):
    value = ledger(tmp_path, Limits(dollar_ceiling=Decimal("3.18")))
    quoted = quote(value.limits)
    reservation = value.reserve(policy(), body(), "generation", quoted, "first")
    value.response(reservation, response(), quoted, 200)
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^dollar_ceiling$"):
        value.reserve(policy(), body(text="changed"), "generation", quoted, "second")
    assert value.events() == before
    assert value.accounting()["requests"] == 1
    assert value.accounting()["total_usd"] == "0.000340"


def test_synthetic_quoted_ceiling_below_reservation_refuses(tmp_path):
    value = ledger(tmp_path, Limits(dollar_ceiling=Decimal("3.179999")))
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^dollar_ceiling$"):
        value.reserve(policy(), body(), "generation", quote(), "synthetic-logical")
    assert value.events() == before


@pytest.mark.parametrize(
    "section,key,replacement",
    [
        (None, "input_tokens", True),
        (None, "output_tokens", -1),
        (None, "total_tokens", 141),
        (None, "total_tokens", "140"),
        (None, "unknown_tokens", 0),
        ("input_tokens_details", "cached_tokens", 101),
        ("input_tokens_details", "cache_write_tokens", 1),
        ("input_tokens_details", "unknown_tokens", 0),
        ("output_tokens_details", "reasoning_tokens", 41),
        ("output_tokens_details", "unknown_tokens", 0),
    ],
)
def test_malformed_usage_never_settles_or_becomes_zero(
    tmp_path, section, key, replacement
):
    value = ledger(tmp_path)
    reservation = value.reserve(
        policy(), body(), "generation", None, "synthetic-logical"
    )
    payload = response()
    target = payload["usage"] if section is None else payload["usage"][section]
    target[key] = replacement
    with pytest.raises(SmokeBlocked, match="^generation_measurement_invalid$"):
        value.response(reservation, payload, None, 200)
    assert value.unresolved(value.events()) == [reservation]
    assert not any(e["event"] == "settle" for e in value.events())
    assert value.accounting()["missing_cost_requests"] == 1
    assert value.accounting()["total_usd"] is None


@pytest.mark.parametrize(
    "change,status",
    [
        ({"usage": None}, 200),
        ({"usage": {"input_tokens": 100, "output_tokens": 40}}, 200),
        ({"status": "incomplete"}, 200),
        ({"status": "cancelled"}, 200),
        ({"model": "synthetic-wrong-model"}, 200),
        ({"service_tier": "flex"}, 200),
        ({}, 500),
    ],
)
def test_partial_or_invalid_response_retains_unresolved_request(
    tmp_path, change, status
):
    value = ledger(tmp_path)
    reservation = value.reserve(
        policy(), body(), "generation", None, "synthetic-logical"
    )
    payload = response()
    payload.update(change)
    with pytest.raises(SmokeBlocked, match="^generation_measurement_invalid$"):
        value.response(reservation, payload, None, status)
    assert value.events()[-1]["event"] == "response"
    assert value.events()[-1]["valid"] is False
    assert value.unresolved(value.events()) == [reservation]
    assert value.accounting()["total_usd"] is None


@pytest.mark.parametrize("valid", [False, True])
def test_duplicate_usage_response_is_refused_without_second_accounting(tmp_path, valid):
    value = ledger(tmp_path)
    quoted = quote()
    reservation = value.reserve(
        policy(), body(), "generation", quoted, "synthetic-logical"
    )
    payload = response()
    if valid:
        value.response(reservation, payload, quoted, 200)
    else:
        payload["status"] = "incomplete"
        with pytest.raises(SmokeBlocked, match="^generation_measurement_invalid$"):
            value.response(reservation, payload, quoted, 200)
    before = value.events()
    accounting = value.accounting()
    with pytest.raises(SmokeBlocked, match="^response_replay$"):
        value.response(reservation, response(), quoted, 200)
    assert value.events() == before
    assert value.accounting() == accounting


@pytest.mark.parametrize("generation_max", [1, 24])
def test_request_exhaustion_includes_every_settled_worker_attempt(
    tmp_path, generation_max
):
    value = ledger(tmp_path, Limits(generation_max=generation_max))
    for index in range(generation_max):
        reservation = value.reserve(
            policy(), body(text=str(index)), "generation", None, f"logical-{index}"
        )
        value.response(reservation, response(), None, 200)
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^generation_cap$"):
        value.reserve(policy(), body(text="exhausted"), "generation", None, "exhausted")
    assert value.events() == before
    assert value.accounting()["requests"] == generation_max
    assert value.accounting()["missing_cost_requests"] == generation_max
    assert value.accounting()["unresolved_requests"] == 0


def test_root_phase_cap_remains_two_with_larger_worker_budget(tmp_path):
    value = ledger(tmp_path)
    assigned = policy("root")
    for index in range(2):
        reservation = value.reserve(
            assigned, body(assigned, text=str(index)), "generation", None, str(index)
        )
        value.response(reservation, response(assigned.expected_model), None, 200)
    with pytest.raises(SmokeBlocked, match="^phase_cap$"):
        value.reserve(
            assigned, body(assigned, text="third"), "generation", None, "third"
        )
    assert value.accounting()["requests"] == 2


def test_token_budget_reserves_native_window_not_estimated_input_and_never_refunds(
    tmp_path,
):
    limits = Limits(native_context_max=100, output_max=40, reserved_tokens_max=140)
    value = ledger(tmp_path, limits)
    reservation = value.reserve(
        policy(), body(limits=limits), "generation", None, "synthetic-logical"
    )
    assert reservation["reserved_tokens"] == 140
    value.response(reservation, response(), None, 200)
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^reserved_token_cap$"):
        value.reserve(
            policy(), body(limits=limits, text="next"), "generation", None, "next"
        )
    assert value.events() == before


@pytest.mark.parametrize("elapsed,accepted", [(29.999, True), (30, False)])
def test_whole_cell_deadline_has_exact_boundary(
    tmp_path, monkeypatch, elapsed, accepted
):
    value = ledger(tmp_path, Limits(whole_cell_s=30))
    started = value.events()[-1]["started"]
    monkeypatch.setattr(anchors_transport.time, "time", lambda: started + elapsed)
    before = value.events()
    if accepted:
        value.reserve(policy(), body(), "generation", None, "synthetic-logical")
        assert value.accounting()["requests"] == 1
    else:
        with pytest.raises(SmokeBlocked, match="^cell_deadline$"):
            value.reserve(policy(), body(), "generation", None, "synthetic-logical")
        assert value.events() == before


@pytest.mark.parametrize("overflow", [0, 1])
def test_utf8_body_bound_accepts_exact_bytes_not_character_count(tmp_path, overflow):
    request = body(text="é" * 100)
    raw = canonical(request)
    assert len(raw) > len(raw.decode("utf-8"))
    value = ledger(tmp_path, Limits(body_bytes_max=len(raw) - overflow))
    before = value.events()
    if overflow:
        with pytest.raises(SmokeBlocked, match="^request_body_bytes$"):
            value.reserve(policy(), request, "generation", None, "synthetic-logical")
        assert value.events() == before
    else:
        reservation = value.reserve(
            policy(), request, "generation", None, "synthetic-logical"
        )
        assert reservation["request_body_bytes"] == len(raw)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://gateway.example/v1",
        GATEWAY + "/",
        GATEWAY + "?synthetic=1",
        GATEWAY + "#synthetic",
        "https://synthetic-user@gateway.example/v1",
        "https://synthetic-user:synthetic-password@gateway.example/v1",
    ],
)
def test_authority_rejects_unsafe_endpoint_forms(tmp_path, endpoint):
    with pytest.raises(SmokeBlocked, match="^endpoint$"):
        Authority(ledger(tmp_path), None, endpoint, True, True)


@pytest.mark.parametrize("endpoint_ok,binding_ok", [(False, True), (True, False)])
def test_authority_requires_both_qualifications(tmp_path, endpoint_ok, binding_ok):
    with pytest.raises(SmokeBlocked, match="^authority_unqualified$"):
        Authority(ledger(tmp_path), None, GATEWAY, endpoint_ok, binding_ok)


@pytest.mark.parametrize("timeout", [0, 61, True, 30.0])
def test_authority_requires_bounded_integer_timeout(tmp_path, timeout):
    with pytest.raises(SmokeBlocked, match="^request_timeout$"):
        Authority(ledger(tmp_path), None, GATEWAY, True, True, timeout)


@pytest.mark.parametrize(
    "receiver",
    [
        None,
        object(),
        SimpleNamespace(handle_async_request=lambda request: None),
        SimpleNamespace(aclose=lambda: None),
    ],
)
def test_missing_or_incomplete_receiver_never_builds_async_http_transport(
    tmp_path, monkeypatch, receiver
):
    built = []

    def forbidden_transport(*args, **kwargs):
        built.append((args, kwargs))
        raise AssertionError("default network transport must never be constructed")

    monkeypatch.setattr(
        live_transport,
        "httpx",
        SimpleNamespace(AsyncHTTPTransport=forbidden_transport),
    )
    value = ledger(tmp_path)
    authority = Authority(value, None, GATEWAY, True, True)
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^external_receiver_required$"):
        Transport(authority, policy(), lambda: None, lambda: "logical", receiver)
    assert built == []
    assert value.events() == before


def test_native_count_refused_before_receiver_or_body_access_without_httpx(tmp_path):
    value = ledger(tmp_path)
    receiver = SimpleNamespace(
        handle_async_request=lambda request: pytest.fail("count reached receiver"),
        aclose=lambda: None,
    )
    verified = []
    transport = Transport(
        Authority(value, None, GATEWAY, True, True),
        policy(),
        lambda: verified.append(True),
        lambda: pytest.fail("count requested a generation logical ID"),
        receiver,
    )
    request = SimpleNamespace(
        method="POST", url=SimpleNamespace(path="/v1/responses/input_tokens")
    )
    with pytest.raises(RuntimeError, match="^smoke.count_billing_unqualified$"):
        asyncio.run(transport.handle_async_request(request))
    assert verified == [True]
    assert value.events()[-1]["kind"] == "count"
    assert value.events()[-1]["disposition"] == "blocked_before_send"
    assert value.accounting()["requests"] == 0
    before = value.events()
    with pytest.raises(SmokeBlocked, match="^count_billing_unqualified$"):
        value.reserve(policy(), {}, "count", None, "synthetic-logical")
    assert value.events() == before


@pytest.mark.parametrize("change", ["equal", "model", "effort"])
def test_distinct_arms_helper_compares_resolved_assignments(change):
    from anchors_adapter import require_distinct_arms

    first = [
        {
            "provider": "openai",
            "model": MODELS["worker"],
            "config": {"reasoning_effort": "high"},
        }
    ]
    second = copy.deepcopy(first)
    if change == "model":
        second[0]["model"] = "synthetic-alternative-model"
    elif change == "effort":
        second[0]["config"]["reasoning_effort"] = "low"
    else:
        second[0] = dict(reversed(list(second[0].items())))
    if change == "equal":
        with pytest.raises(SmokeBlocked, match="^inheritance_erased_arms$"):
            require_distinct_arms(first, second)
    else:
        require_distinct_arms(first, second)


class Receiver:
    """Only an in-process response source; never constructs a network transport."""

    def __init__(self, value, reply=None):
        self.ledger = value
        self.reply = reply
        self.requests = []
        self.responses = []
        self.closed = False

    async def handle_async_request(self, request):
        self.requests.append(request)
        # The receiver must see durable custody before it can return any bytes.
        assert len(self.ledger.unresolved(self.ledger.events())) == 1
        assert self.ledger.events()[-1]["event"] == "reserve"
        if self.reply:
            result = self.reply(request)
        else:
            model = strict_json(request.content)["model"]
            result = live_transport.httpx.Response(200, json=response(model))
        self.responses.append(result)
        return result

    async def aclose(self):
        self.closed = True


def wire_request(authority, request_body, *, method="POST", url=None, raw=None):
    return live_transport.httpx.Request(
        method,
        url or authority.endpoint + "/responses",
        content=canonical(request_body) if raw is None else raw,
        extensions={
            "timeout": {
                part: authority.timeout_s
                for part in ("connect", "read", "write", "pool")
            }
        },
    )


def exchange(transport, request):
    async def run():
        try:
            result = await transport.handle_async_request(request)
            await result.aclose()
            return result
        finally:
            await transport.aclose()

    return asyncio.run(run())


class TestHTTPXTransport:
    # No skip/SDK gate: pure controls above still collect when HTTPX is absent.
    __test__ = live_transport.httpx is not None

    @pytest.mark.parametrize("phase", ["root", "worker"])
    @pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh"])
    def test_exact_gateway_tooling_and_lower_output_timeout_profile(
        self, tmp_path, phase, effort
    ):
        from anchors_adapter import model_config

        assigned = policy(phase, effort)
        limits = Limits(output_max=2048)
        value = ledger(tmp_path, limits)
        authority = Authority(value, None, GATEWAY, True, True, timeout_s=30)
        config = model_config(assigned.expected_model, effort, limits.output_max, 30)
        assert config["max_output_tokens"] == 2048
        assert config["timeout"] == 30
        receiver = Receiver(value)
        verified = []
        transport = Transport(
            authority,
            assigned,
            lambda: verified.append(True),
            lambda: "logical",
            receiver,
        )
        result = exchange(transport, wire_request(authority, body(assigned, limits)))
        assert result.status_code == 200
        assert result.json()["usage"] == response()["usage"]
        assert verified == [True]
        assert len(receiver.requests) == 1
        sent = receiver.requests[0]
        assert sent.method == "POST"
        assert str(sent.url) == GATEWAY + "/responses"
        assert strict_json(sent.content) == body(assigned, limits)
        assert all(t == 30 for t in sent.extensions["timeout"].values())
        assert receiver.closed and transport.closed
        assert receiver.responses[0].is_closed
        assert value.accounting()["requests"] == 1
        assert value.accounting()["missing_cost_requests"] == 1
        assert value.accounting()["total_usd"] is None
        assert value.accounting()["unresolved_requests"] == 0

    @pytest.mark.parametrize(
        "mutation,code",
        [
            ("model", "request_model"),
            ("effort", "request_effort"),
            ("schema", "wire_tools"),
            ("unknown_field", "request_fields"),
            ("output", "generation_policy"),
            ("store", "generation_policy"),
            ("stream", "generation_policy"),
            ("unknown_function", "input_function"),
        ],
    )
    def test_request_mutations_refuse_before_receiver(self, tmp_path, mutation, code):
        value = ledger(tmp_path)
        authority = Authority(value, None, GATEWAY, True, True)
        request_body = body()
        if mutation == "model":
            request_body["model"] = "synthetic-other-model"
        elif mutation == "effort":
            request_body["reasoning"]["effort"] = "low"
        elif mutation == "schema":
            request_body["tools"][0]["parameters"]["additionalProperties"] = True
        elif mutation == "unknown_field":
            request_body["previous_response_id"] = "synthetic-old-response"
        elif mutation == "output":
            request_body["max_output_tokens"] = 2048
        elif mutation in {"store", "stream"}:
            request_body[mutation] = True
        else:
            request_body["input"][1]["name"] = "synthetic-unknown-tool"
        receiver = Receiver(value)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "logical", receiver
        )
        with pytest.raises(SmokeBlocked, match=f"^{code}$"):
            exchange(transport, wire_request(authority, request_body))
        assert receiver.requests == []
        assert value.accounting()["requests"] == 0
        assert value.events()[-1]["reason"] == code
        assert value.events()[-1]["disposition"] == "blocked_before_send"

    @pytest.mark.parametrize(
        "method,url",
        [
            ("GET", GATEWAY + "/responses"),
            ("PUT", GATEWAY + "/responses"),
            ("POST", "https://other.example/v1/responses"),
            ("POST", "http://gateway.example/v1/responses"),
            ("POST", "https://gateway.example:8443/v1/responses"),
            ("POST", GATEWAY + "/responses/"),
            ("POST", GATEWAY + "/responses?synthetic=1"),
            ("POST", GATEWAY + "/responses#synthetic"),
            ("POST", "https://gateway.example/v2/responses"),
        ],
    )
    def test_endpoint_and_method_must_match_exactly(self, tmp_path, method, url):
        value = ledger(tmp_path)
        authority = Authority(value, None, GATEWAY, True, True)
        receiver = Receiver(value)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "logical", receiver
        )
        with pytest.raises(SmokeBlocked, match="^wire_endpoint$"):
            exchange(transport, wire_request(authority, body(), method=method, url=url))
        assert receiver.requests == []
        assert value.accounting()["requests"] == 0
        assert value.events()[-1]["reason"] == "wire_endpoint"

    @pytest.mark.parametrize("timeout", [None, {}, 0, 31, True, float("inf")])
    def test_wire_timeout_cannot_exceed_lower_authority(self, tmp_path, timeout):
        value = ledger(tmp_path, Limits(output_max=2048))
        authority = Authority(value, None, GATEWAY, True, True, timeout_s=30)
        receiver = Receiver(value)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "logical", receiver
        )
        request = wire_request(authority, body(limits=value.limits))
        request.extensions["timeout"] = (
            timeout
            if timeout is None or isinstance(timeout, dict)
            else {part: timeout for part in ("connect", "read", "write", "pool")}
        )
        with pytest.raises(SmokeBlocked, match="^wire_timeout$"):
            exchange(transport, request)
        assert receiver.requests == []
        assert value.accounting()["requests"] == 0

    @pytest.mark.parametrize(
        "bound,code",
        [
            ("requests", "generation_cap"),
            ("tokens", "reserved_token_cap"),
            ("deadline", "cell_deadline"),
            ("body", "json_size"),
        ],
    )
    def test_budget_bounds_deny_before_receiver(
        self, tmp_path, monkeypatch, bound, code
    ):
        request_body = body(text="next")
        limits = Limits(
            generation_max=1 if bound == "requests" else 24,
            reserved_tokens_max=1 if bound == "tokens" else 25298304,
            body_bytes_max=len(canonical(request_body)) - 1
            if bound == "body"
            else 131072,
        )
        value = ledger(tmp_path, limits)
        initial_requests = 0
        if bound == "requests":
            reservation = value.reserve(
                policy(), body(text="first"), "generation", None, "first"
            )
            value.response(reservation, response(), None, 200)
            initial_requests = 1
        if bound == "deadline":
            started = value.events()[-1]["started"]
            monkeypatch.setattr(
                anchors_transport.time, "time", lambda: started + limits.whole_cell_s
            )
        authority = Authority(value, None, GATEWAY, True, True)
        receiver = Receiver(value)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "next", receiver
        )
        with pytest.raises(SmokeBlocked, match=f"^{code}$"):
            exchange(transport, wire_request(authority, request_body))
        assert receiver.requests == []
        assert value.accounting()["requests"] == initial_requests
        assert value.events()[-1]["reason"] == code

    def test_raw_body_bytes_include_whitespace_not_only_canonical_projection(
        self, tmp_path
    ):
        request_body = body()
        raw = canonical(request_body)
        value = ledger(tmp_path, Limits(body_bytes_max=len(raw)))
        authority = Authority(value, None, GATEWAY, True, True)
        receiver = Receiver(value)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "logical", receiver
        )
        with pytest.raises(SmokeBlocked, match="^json_size$"):
            exchange(transport, wire_request(authority, request_body, raw=raw + b" "))
        assert receiver.requests == []
        assert value.accounting()["requests"] == 0

    def test_count_endpoint_refused_without_timeout_body_or_generation_id(
        self, tmp_path
    ):
        value = ledger(tmp_path)
        authority = Authority(value, None, GATEWAY, True, True)
        receiver = Receiver(value)
        transport = Transport(
            authority,
            policy(),
            lambda: None,
            lambda: pytest.fail("count requested generation ID"),
            receiver,
        )
        request = wire_request(
            authority, {}, url=GATEWAY + "/responses/input_tokens", raw=b"{"
        )
        request.extensions.clear()
        with pytest.raises(RuntimeError, match="^smoke.count_billing_unqualified$"):
            exchange(transport, request)
        assert receiver.requests == []
        assert value.accounting()["requests"] == 0
        assert value.events()[-1]["kind"] == "count"
        assert value.events()[-1]["reason"] == "count_billing_unqualified"

    @pytest.mark.parametrize(
        "failure",
        [
            "malformed_json",
            "duplicate_usage",
            "missing_usage",
            "scalar_usage_details",
            "partial_response",
            "cancelled_receiver",
            "partial_stream",
            "response_size",
        ],
    )
    def test_wire_failure_partial_or_cancel_retains_unresolved(self, tmp_path, failure):
        httpx = live_transport.httpx
        value = ledger(tmp_path)
        authority = Authority(value, None, GATEWAY, True, True)

        class BrokenStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                if failure == "response_size":
                    yield b" " * 262144
                    yield b" "
                else:
                    yield b'{"usage":'
                    raise RuntimeError("synthetic truncated stream")

        def reply(request):
            payload = response()
            if failure == "cancelled_receiver":
                raise asyncio.CancelledError
            if failure in {"partial_stream", "response_size"}:
                return httpx.Response(200, stream=BrokenStream())
            if failure == "malformed_json":
                return httpx.Response(200, content=b'{"usage":')
            if failure == "duplicate_usage":
                raw = canonical(payload).replace(
                    b'"input_tokens":100',
                    b'"input_tokens":100,"input_tokens":100',
                )
                return httpx.Response(200, content=raw)
            if failure == "missing_usage":
                del payload["usage"]
            elif failure == "scalar_usage_details":
                payload["usage"]["input_tokens_details"] = 0
            elif failure == "partial_response":
                payload["status"] = "incomplete"
            return httpx.Response(200, json=payload)

        receiver = Receiver(value, reply)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "logical", receiver
        )
        with pytest.raises(SmokeBlocked, match="^wire_or_measurement_failure$"):
            exchange(transport, wire_request(authority, body()))
        assert len(receiver.requests) == 1
        assert receiver.closed and transport.closed
        assert all(result.is_closed for result in receiver.responses)
        assert value.accounting()["requests"] == 1
        assert value.accounting()["unresolved_requests"] == 1
        assert value.accounting()["missing_cost_requests"] == 1
        assert value.accounting()["total_usd"] is None
        assert not any(e["event"] == "settle" for e in value.events())
        reservation = value.unresolved(value.events())[0]
        reopened = AnchorsLedger(value.path, "synthetic-lock", value.limits)
        assert reopened.unresolved(reopened.events()) == [reservation]
        before = reopened.events()
        with pytest.raises(SmokeBlocked, match="^http_active_or_unresolved$"):
            reopened.reserve(policy(), body(text="retry"), "generation", None, "retry")
        assert reopened.events() == before

    def test_quoted_dollar_ceiling_refused_before_receiver(self, tmp_path):
        value = ledger(tmp_path, Limits(dollar_ceiling=Decimal("3.179999")))
        authority = Authority(value, quote(), GATEWAY, True, True)
        receiver = Receiver(value)
        transport = Transport(
            authority, policy(), lambda: None, lambda: "logical", receiver
        )
        with pytest.raises(SmokeBlocked, match="^dollar_ceiling$"):
            exchange(transport, wire_request(authority, body()))
        assert receiver.requests == []
        assert value.accounting()["requests"] == 0
        assert value.events()[-1]["reason"] == "dollar_ceiling"
