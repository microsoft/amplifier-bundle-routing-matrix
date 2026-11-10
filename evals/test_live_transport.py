"""Count-free amendment controls; all quoted test evidence is synthetic."""

import asyncio
import copy
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from live_transport import (
    ROOT_MODEL,
    WIRE_TOOL,
    AdmissionAuthority,
    AdmittedTransport,
    Ledger,
    ModelRate,
    PriceQuote,
    SessionPolicy,
    SmokeBlocked,
    SmokeLimits,
    canonical,
    numeric_usage,
    settle_usage,
    strict_json,
    validate_payload,
)


def quote():
    now = datetime.now(timezone.utc)
    return PriceQuote(
        "synthetic-quote",
        "synthetic-test-not-a-live-rate",
        now - timedelta(seconds=1),
        now - timedelta(days=1),
        now + timedelta(days=1),
        "synthetic-binding",
        "default",
        "USD",
        {
            model: ModelRate(
                Decimal("2"), Decimal("1"), Decimal("2"), Decimal("4"), Decimal(0)
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


def policy(phase="root", cell="A0"):
    return SessionPolicy(
        cell,
        f"synthetic-{phase}-{cell}",
        None if phase == "root" else f"synthetic-root-{cell}",
        "controller" if phase == "root" else "coding",
        phase,
        "gpt-6-astra" if phase == "worker" and cell == "B1" else ROOT_MODEL,
    )


def body(phase="root", cell="A0"):
    value = {
        "model": policy(phase, cell).expected_model,
        "input": [{"role": "user", "content": "synthetic input"}],
        "reasoning": {"effort": "high", "summary": "auto"},
        "max_output_tokens": 4096,
        "store": False,
        "service_tier": "default",
    }
    if phase == "root":
        value.update(
            tools=[copy.deepcopy(WIRE_TOOL)],
            tool_choice="auto",
            parallel_tool_calls=True,
        )
    return value


def ledger(tmp_path):
    value = Ledger(tmp_path / "ledger.jsonl", "synthetic-lock", SmokeLimits())
    value.start_cell("A0")
    return value


def response(model=ROOT_MODEL, inputs=100):
    return {
        "id": "synthetic-response",
        "model": model,
        "status": "completed",
        "service_tier": "default",
        "usage": {
            "input_tokens": inputs,
            "output_tokens": 40,
            "total_tokens": inputs + 40,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 30},
        },
    }


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"x":NaN}',
        b"\xff",
        b"{",
        b'"' + b"x" * 262145 + b'"',
    ],
)
def test_strict_json_failures(raw):
    with pytest.raises(SmokeBlocked):
        strict_json(raw)


@pytest.mark.parametrize(
    "key,value",
    [
        ("model", "unapproved"),
        ("reasoning", {"effort": "low"}),
        ("store", True),
        ("stream", True),
        ("max_output_tokens", 2048),
        ("previous_response_id", "synthetic-old"),
        ("background", True),
        ("metadata", {"x": "y"}),
        ("service_tier", "flex"),
        ("service_tier", "auto"),
        ("service_tier", None),
        ("include", ["reasoning.encrypted_content"]),
        ("tools", [{"type": "web_search"}]),
        (
            "input",
            [{"role": "user", "content": [{"type": "input_file", "file_id": "fake"}]}],
        ),
    ],
)
def test_policy_mutations_refuse_before_reservation(tmp_path, key, value):
    value_ = ledger(tmp_path)
    request = body()
    request[key] = value
    before = value_.events()
    with pytest.raises(SmokeBlocked):
        value_.reserve(policy(), request, "generation", quote(), "logical")
    assert value_.events() == before


def test_real_byte_bound_not_token_estimate(tmp_path):
    value = ledger(tmp_path)
    request = body()
    request["input"][0]["content"] = "é" * 4096
    assert len(canonical(request)) > 8192
    with pytest.raises(SmokeBlocked, match="request_body_bytes"):
        value.reserve(policy(), request, "generation", quote(), "logical")


def test_worst_native_context_reservations_and_phase_caps(tmp_path):
    q = quote()
    assert q.reserve(ROOT_MODEL) == Decimal("5.32")
    assert q.reserve("gpt-6-astra") == Decimal("26.56")
    value = ledger(tmp_path)
    for i in range(2):
        request = body()
        request["input"][0]["content"] += str(i)
        reservation = value.reserve(policy(), request, "generation", q, f"logical{i}")
        assert reservation["native_input"] is None
        assert reservation["reserved_tokens"] == 1050000 + 4096
        assert reservation["reserved_usd"] == "5.32"
        value.response(reservation, response(), q, 200)
    with pytest.raises(SmokeBlocked, match="phase_cap"):
        value.reserve(policy(), body(), "generation", q, "third")


def test_unknown_liability_and_once_only_survive_reopening(tmp_path):
    value = ledger(tmp_path)
    q = quote()
    reservation = value.reserve(policy(), body(), "generation", q, "logical")
    reopened = Ledger(value.path, "synthetic-lock", SmokeLimits())
    assert reopened.events()[-1] == reservation
    assert reopened.liability(reopened.events()) == Decimal("5.32")
    with pytest.raises(SmokeBlocked, match="http_active_or_unresolved"):
        reopened.reserve(policy(), body(), "generation", q, "retry")
    value.fault(reservation)
    value.finish_cell("A0", {"instrumentation": "blocked"})
    with pytest.raises(SmokeBlocked, match="liability_unresolved"):
        reopened.start_cell("A1")
    with pytest.raises(SmokeBlocked, match="cell_once_only"):
        reopened.start_cell("A0")


@pytest.mark.parametrize(
    "change",
    [
        {"model": "aliased-model"},
        {"status": "incomplete"},
        {"service_tier": "flex"},
        {"usage": None},
        {"usage": {"input_tokens": 100, "output_tokens": 1}},
    ],
)
def test_partial_response_keeps_full_liability(tmp_path, change):
    value = ledger(tmp_path)
    q = quote()
    reservation = value.reserve(policy(), body(), "generation", q, "logical")
    payload = response()
    payload.update(change)
    with pytest.raises(SmokeBlocked, match="generation_measurement_invalid"):
        value.response(reservation, payload, q, 200)
    assert value.liability(value.events()) == Decimal("5.32")
    assert len(value.unresolved(value.events())) == 1


def test_completed_response_releases_excess_but_denies_replay(tmp_path):
    value = ledger(tmp_path)
    q = quote()
    reservation = value.reserve(policy(), body(), "generation", q, "logical")
    value.response(reservation, response(), q, 200)
    assert value.liability(value.events()) == Decimal("0.000340")
    assert not value.unresolved(value.events())
    with pytest.raises(SmokeBlocked, match="logical_or_payload_replay"):
        value.reserve(policy(), body(), "generation", q, "new-id")
    with pytest.raises(SmokeBlocked, match="logical_or_payload_replay"):
        other = body()
        other["input"][0]["content"] = "changed"
        value.reserve(policy(), other, "generation", q, "logical")


def test_quote_underpricing_and_window_denied():
    q = quote()
    with pytest.raises(SmokeBlocked, match="quote_window"):
        replace(q, native_context_max=8192)
    with pytest.raises(SmokeBlocked, match="quote_service_tier"):
        replace(q, service_tier="flex")
    with pytest.raises(SmokeBlocked, match="quote_underreserved"):
        replace(
            q,
            rates={
                ROOT_MODEL: ModelRate(
                    Decimal("1000000"), Decimal(0), Decimal(0), Decimal("4"), Decimal(0)
                ),
                "gpt-6-astra": q.rates["gpt-6-astra"],
            },
        )
    with pytest.raises(SmokeBlocked, match="quote_long_rate_bound"):
        replace(
            q,
            long_context_rates={
                ROOT_MODEL: ModelRate(
                    Decimal("2"), Decimal("1"), Decimal("2"), Decimal("4"), Decimal(0)
                ),
                "gpt-6-astra": q.long_context_rates["gpt-6-astra"],
            },
        )
    with pytest.raises(SmokeBlocked, match="quote_expired"):
        replace(q, expires_at=q.effective_at).validate(datetime.now(timezone.utc))


def test_changed_reservation_quote_and_source_privacy(tmp_path):
    value = ledger(tmp_path)
    q = quote()
    reservation = value.reserve(policy(), body(), "generation", q, "logical")
    with pytest.raises(SmokeBlocked, match="reservation_changed"):
        value.response({**reservation, "reserved_usd": "0"}, response(), q, 200)
    with pytest.raises(SmokeBlocked, match="quote_changed"):
        value.response(reservation, response(), replace(q, revision="different"), 200)
    assert "synthetic input" not in value.path.read_text()
    assert "authorization" not in value.path.read_text()


def test_complete_cache_reasoning_no_double_billing():
    assert settle_usage(response()["usage"], quote(), ROOT_MODEL) == Decimal("0.000340")
    payload = response(inputs=500000)
    assert settle_usage(payload["usage"], quote(), ROOT_MODEL) == Decimal("2.500600")
    payload["usage"]["input_tokens_details"]["cache_write_tokens"] = 3
    assert settle_usage(payload["usage"], quote(), ROOT_MODEL) is None
    assert (
        numeric_usage(payload["usage"])["input_tokens_details"]["cache_write_tokens"]
        == 3
    )


def test_zero_cache_write_matches_absent_with_synthetic_825_token_usage():
    # Published USD/million: https://developers.openai.com/api/docs/pricing.md
    # Standard Sol 6.1 values; quote and usage remain wholly synthetic.
    q = quote()
    rate = ModelRate(*(Decimal(v) for v in ("2", "0.10", "2.50", "10", "0")))
    q = replace(q, rates={**q.rates, ROOT_MODEL: rate})
    usage = response(inputs=785)["usage"]  # 785 gross input + 40 gross output.
    expected = Decimal("0.001932")  # (765 * 2 + 20 * 0.10 + 40 * 10) / 1e6.
    assert settle_usage(usage, q, ROOT_MODEL) == expected
    assert "cache_write_tokens" not in usage["input_tokens_details"]
    usage["input_tokens_details"]["cache_write_tokens"] = 0
    assert settle_usage(usage, q, ROOT_MODEL) == expected
    assert numeric_usage(usage) == usage


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("input_tokens_details", "cache_write_tokens", v)
        for v in (1, -1, False, True, "0", 0.0, None)
    ]
    + [
        ("input_tokens_details", "unknown_category", 0),
        ("input_tokens_details", "cached_tokens", 786),
        ("output_tokens_details", "reasoning_tokens", 41),
        (None, "total_tokens", 826),
    ],
)
def test_zero_cache_write_does_not_relax_usage_validation(section, key, value):
    usage = response(inputs=785)["usage"]
    usage["input_tokens_details"]["cache_write_tokens"] = 0
    (usage if section is None else usage[section])[key] = value
    assert settle_usage(usage, quote(), ROOT_MODEL) is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api.openai.com/v1",
        "https://api.openai.com/v1?x=1",
        "https://other.invalid/v1",
        "https://user@api.openai.com/v1",
    ],
)
def test_endpoint_authority_fail_closed(tmp_path, endpoint):
    with pytest.raises(SmokeBlocked, match="endpoint_unqualified"):
        AdmissionAuthority(ledger(tmp_path), quote(), endpoint, True, True)


def test_zero_counts_before_underlying_transport(tmp_path):
    class URL:
        path = "/v1/responses/input_tokens"

    class Request:
        method = "POST"
        url = URL()

    class Receiver:
        sent = False

        async def handle_async_request(self, request):
            self.sent = True

    value = ledger(tmp_path)
    receiver = Receiver()
    transport = AdmittedTransport(
        AdmissionAuthority(value, quote(), "https://api.openai.com/v1", True, True),
        policy(),
        lambda: None,
        lambda: "logical",
        receiver,
    )
    with pytest.raises(RuntimeError, match="count_billing_unqualified"):
        asyncio.run(transport.handle_async_request(Request()))
    assert not receiver.sent
    assert value.events()[-1]["disposition"] == "blocked_before_send"
    assert value.events()[-1]["kind"] == "count"
    assert value.liability(value.events()) == 0
    assert not any(e["event"] == "count_ok" for e in value.events())


def test_worker_has_no_tools():
    request = body("worker")
    request["tools"] = [WIRE_TOOL]
    with pytest.raises(SmokeBlocked, match="worker_tools"):
        validate_payload(request, policy("worker"), "generation")
