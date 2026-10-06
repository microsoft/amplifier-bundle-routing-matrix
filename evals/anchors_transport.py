"""Tool-enabled Anchors profile. Reuses PR82's fsynced ledger and HTTP custody.

Price is optional ONLY under observe-only cost policy. Missing price is never
zero; complete usage can settle request custody without settling dollars.
Native count traffic is still refused, not fabricated or sent unmetered.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from urllib.parse import urlsplit

from live_transport import (
    AdmissionAuthority,
    AdmittedTransport,
    GENERATION_FIELDS,
    Ledger,
    ModelRate,
    PriceQuote,
    SessionPolicy,
    canonical,
    fingerprint,
    integer,
    money,
    numeric_usage,
    require,
    settle_usage,
)

VERSION = "routing-anchors-repair/v1"


@dataclass(frozen=True)
class Limits:
    whole_cell_s: int = 1200
    generation_max: int = 24
    body_bytes_max: int = 131072
    native_context_max: int = 1050000
    output_max: int = 4096
    reserved_tokens_max: int = 25298304
    dollar_ceiling: Decimal | None = None

    def __post_init__(self):
        for name, maximum in (
            ("whole_cell_s", 1200),
            ("generation_max", 24),
            ("body_bytes_max", 131072),
            ("native_context_max", 1050000),
            ("output_max", 4096),
            ("reserved_tokens_max", 25298304),
        ):
            require(
                type(getattr(self, name)) is int and 0 < getattr(self, name) <= maximum,
                "anchors_limit",
            )
        if self.dollar_ceiling is not None:
            require(type(self.dollar_ceiling) is Decimal, "decimal_required")
            money(self.dollar_ceiling)


@dataclass(frozen=True)
class Quote(PriceQuote):
    """Same USD/cache usage semantics, with controller-supplied exact models/rates."""

    def __post_init__(self):
        require(
            self.currency == "USD" and self.service_tier == "default", "quote_semantics"
        )
        require(self.cache_semantics == "cached-subset-no-writes", "quote_semantics")
        require(0 < self.native_context_max <= 1050000, "quote_window")
        require(
            bool(self.revision)
            and bool(self.source)
            and bool(self.binding_ref)
            and bool(self.window_source),
            "quote_provenance",
        )
        require(
            self.rates and set(self.rates) == set(self.long_context_rates),
            "quote_models",
        )
        for model, ordinary in self.rates.items():
            require(isinstance(model, str) and bool(model), "quote_models")
            upper = self.long_context_rates[model]
            require(
                type(ordinary) is ModelRate and type(upper) is ModelRate, "quote_rates"
            )
            require(
                max(ordinary.fresh_input, ordinary.cache_read, ordinary.cache_write)
                <= max(upper.fresh_input, upper.cache_read, upper.cache_write)
                and ordinary.output <= upper.output
                and ordinary.request_usd <= upper.request_usd,
                "quote_underreserved",
            )
        require(
            all(
                t.tzinfo is not None
                for t in (self.verified_at, self.effective_at, self.expires_at)
            ),
            "quote_timezone",
        )
        object.__setattr__(self, "rates", MappingProxyType(dict(self.rates)))
        object.__setattr__(
            self, "long_context_rates", MappingProxyType(dict(self.long_context_rates))
        )


@dataclass(frozen=True)
class Policy(SessionPolicy):
    wire_tools: tuple = ()

    def __post_init__(self):
        require(self.cell_id in {"A0", "A1", "B1"}, "cell_identity")
        require(self.phase in {"root", "worker"}, "phase")
        require(
            isinstance(self.expected_model, str)
            and 0 < len(self.expected_model) <= 128
            and not any(c in self.expected_model for c in "*?[]"),
            "model",
        )
        require(self.expected_effort in {"low", "medium", "high", "xhigh"}, "effort")
        require(
            (
                self.phase == "root"
                and self.parent_id is None
                and self.role_origin == "controller"
            )
            or (
                self.phase == "worker"
                and bool(self.parent_id)
                and self.role_origin == "coding"
            ),
            "policy_lineage",
        )


def validate(body, policy, limits):
    require(
        isinstance(body, dict) and not (set(body) - GENERATION_FIELDS), "request_fields"
    )
    require(body.get("model") == policy.expected_model, "request_model")
    require(
        body.get("reasoning", {}).get("effort") == policy.expected_effort,
        "request_effort",
    )
    require(
        set(body.get("reasoning", {})) <= {"effort", "summary"}, "request_reasoning"
    )
    require(
        body.get("reasoning", {}).get("summary", "auto")
        in {"auto", "concise", "detailed"},
        "request_reasoning",
    )
    require(
        "instructions" not in body or isinstance(body["instructions"], str),
        "request_instructions",
    )
    require(
        "text" not in body or body["text"] == {"format": {"type": "text"}},
        "request_text",
    )
    require(
        "truncation" not in body or body["truncation"] == "disabled",
        "request_truncation",
    )
    require(
        body.get("max_output_tokens") == limits.output_max
        and body.get("store") is False
        and body.get("stream", False) is False
        and body.get("service_tier") == "default"
        and body.get("include", []) == [],
        "generation_policy",
    )
    require(
        body.get("tools", []) == list(policy.wire_tools)
        and body.get("tool_choice", "auto") == "auto"
        and body.get("parallel_tool_calls", True) is True,
        "wire_tools",
    )
    names = {t["name"] for t in policy.wire_tools}
    require(type(body.get("input")) is list, "request_input")
    for item in body["input"]:
        require(type(item) is dict, "input_item")
        kind = item.get("type", "message")
        if kind == "message":
            require(
                set(item) <= {"type", "role", "content"}
                and item.get("role") in {"user", "assistant", "system", "developer"},
                "input_message",
            )
            content = item.get("content")
            require(isinstance(content, (str, list)), "input_content")
            if isinstance(content, list):
                for part in content:
                    require(
                        type(part) is dict
                        and set(part) <= {"type", "text", "annotations"}
                        and part.get("type") in {"input_text", "output_text"}
                        and isinstance(part.get("text"), str)
                        and part.get("annotations", []) == [],
                        "text_only",
                    )
        elif kind == "function_call":
            require(
                set(item) <= {"type", "call_id", "name", "arguments"}
                and item.get("name") in names
                and isinstance(item.get("arguments"), str),
                "input_function",
            )
        elif kind == "function_call_output":
            require(
                set(item) == {"type", "call_id", "output"}
                and isinstance(item["output"], str),
                "input_function_output",
            )
        else:
            require(False, "input_type")
    require(len(canonical(body)) <= limits.body_bytes_max, "request_body_bytes")
    return fingerprint(body)


class AnchorsLedger(Ledger):
    version = VERSION

    @staticmethod
    def liability(events, cell_id=None):
        """Known priced lower bound only. Missing dollars are reported separately."""
        return sum(
            (
                money(e["usd"])
                for e in events
                if e["event"] == "settle"
                and e.get("usd") is not None
                and (cell_id is None or e["cell_id"] == cell_id)
            ),
            Decimal(0),
        )

    def reserve(self, policy, body, kind, quote, logical_id):
        require(kind == "generation", "count_billing_unqualified")
        projection = validate(body, policy, self.limits)
        require(isinstance(logical_id, str) and bool(logical_id), "logical_id")
        if quote is not None:
            quote.validate(datetime.now(timezone.utc))
            require(
                policy.expected_model in quote.rates
                and quote.native_context_max == self.limits.native_context_max,
                "quote_model_window",
            )
        require(
            self.limits.dollar_ceiling is None or quote is not None,
            "ceiling_requires_quote",
        )
        with self.transaction() as events:
            starts = [
                e
                for e in events
                if e["event"] == "cell_start" and e["cell_id"] == policy.cell_id
            ]
            require(len(starts) == 1, "cell_not_started")
            require(
                not any(
                    e["event"] in {"cell_abort", "cell_end"}
                    and e["cell_id"] == policy.cell_id
                    for e in events
                ),
                "cell_inactive",
            )
            require(
                time.time() - starts[0]["started"] < self.limits.whole_cell_s,
                "cell_deadline",
            )
            require(not self.unresolved(events), "http_active_or_unresolved")
            calls = [
                e
                for e in events
                if e["event"] == "reserve" and e["cell_id"] == policy.cell_id
            ]
            require(len(calls) < self.limits.generation_max, "generation_cap")
            require(
                sum(e["phase"] == "root" for e in calls) < 2
                if policy.phase == "root"
                else True,
                "phase_cap",
            )
            require(
                not any(
                    e["logical_id"] == logical_id
                    or (
                        e["session_id"] == policy.session_id
                        and e["projection"] == projection
                    )
                    for e in calls
                ),
                "logical_or_payload_replay",
            )
            tokens = self.limits.native_context_max + self.limits.output_max
            require(
                sum(e["reserved_tokens"] for e in calls) + tokens
                <= self.limits.reserved_tokens_max,
                "reserved_token_cap",
            )
            charge = quote.reserve(policy.expected_model) if quote else None
            require(
                self.limits.dollar_ceiling is None
                or self.liability(events) + charge <= self.limits.dollar_ceiling,
                "dollar_ceiling",
            )
            return self._append(
                {
                    "event": "reserve",
                    **{k: v for k, v in vars(policy).items() if k != "wire_tools"},
                    "kind": kind,
                    "logical_id": logical_id,
                    "projection": projection,
                    "reserved_tokens": tokens,
                    "reserved_usd": str(charge) if charge else None,
                    "quote_lock": quote.lock if quote else None,
                    "wire_effort": policy.expected_effort,
                    "request_body_bytes": len(canonical(body)),
                    "started": time.time(),
                }
            )

    def response(self, reservation, payload, quote, http_status):
        usage = numeric_usage(payload.get("usage")) if type(payload) is dict else None
        valid = (
            http_status == 200
            and type(payload) is dict
            and isinstance(payload.get("id"), str)
            and bool(payload["id"])
            and payload.get("model") == reservation["expected_model"]
            and payload.get("status") == "completed"
            and payload.get("service_tier") == "default"
            and usage is not None
            and set(usage)
            == {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "input_tokens_details",
                "output_tokens_details",
            }
            and all(
                integer(usage.get(k))
                for k in ("input_tokens", "output_tokens", "total_tokens")
            )
            and usage["input_tokens"] + usage["output_tokens"] == usage["total_tokens"]
            and usage["input_tokens"] <= self.limits.native_context_max
            and usage["output_tokens"] <= self.limits.output_max
            and type(usage["input_tokens_details"]) is dict
            and type(usage["output_tokens_details"]) is dict
            and set(usage["input_tokens_details"])
            <= {"cached_tokens", "cache_write_tokens"}
            and integer(usage["input_tokens_details"].get("cached_tokens"))
            and usage["input_tokens_details"]["cached_tokens"] <= usage["input_tokens"]
            and usage["input_tokens_details"].get("cache_write_tokens", 0) == 0
            and set(usage["output_tokens_details"]) == {"reasoning_tokens"}
            and integer(usage["output_tokens_details"].get("reasoning_tokens"))
            and usage["output_tokens_details"]["reasoning_tokens"]
            <= usage["output_tokens"]
        )
        usd = (
            settle_usage(usage, quote, reservation["expected_model"])
            if quote and valid
            else None
        )
        with self.transaction() as events:
            require(any(e == reservation for e in events), "reservation_changed")
            require(
                reservation["quote_lock"] == (quote.lock if quote else None),
                "quote_changed",
            )
            require(
                not any(
                    e.get("wire_id") == reservation["id"]
                    and e["event"] in {"response", "wire_fault", "settle"}
                    for e in events
                ),
                "response_replay",
            )
            self._append(
                {
                    "event": "response",
                    "wire_id": reservation["id"],
                    "usage": usage,
                    "valid": bool(valid),
                    "priced_usd": str(usd) if usd is not None else None,
                }
            )
            if valid:
                self._append(
                    {
                        "event": "settle",
                        "wire_id": reservation["id"],
                        "cell_id": reservation["cell_id"],
                        "usd": str(usd) if usd is not None else None,
                    }
                )
        require(valid, "generation_measurement_invalid")

    def accounting(self):
        events = self.events()
        calls = [e for e in events if e["event"] == "reserve"]
        settlements = [e for e in events if e["event"] == "settle"]
        return {
            "requests": len(calls),
            "missing_cost_requests": len(calls)
            - sum(e["usd"] is not None for e in settlements),
            "known_usd_lower_bound": str(self.liability(events)),
            "total_usd": str(self.liability(events))
            if len(calls) == len(settlements)
            and all(e["usd"] is not None for e in settlements)
            else None,
            "unresolved_requests": len(self.unresolved(events)),
        }


@dataclass(frozen=True)
class Authority(AdmissionAuthority):
    def __post_init__(self):
        url = urlsplit(self.endpoint)
        require(
            url.scheme == "https"
            and bool(url.hostname)
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
            and not self.endpoint.endswith("/"),
            "endpoint",
        )
        require(
            self.endpoint_qualified is True and self.binding_qualified is True,
            "authority_unqualified",
        )
        require(
            type(self.timeout_s) is int and 0 < self.timeout_s <= 60, "request_timeout"
        )


class Transport(AdmittedTransport):
    def __init__(self, authority, policy, verify_session, logical_id, receiver=None):
        require(
            receiver is not None
            and callable(getattr(receiver, "handle_async_request", None))
            and callable(getattr(receiver, "aclose", None)),
            "external_receiver_required",
        )
        super().__init__(authority, policy, verify_session, logical_id, receiver)

    @property
    def count_path(self):
        return urlsplit(self.authority.endpoint).path + "/responses/input_tokens"

    def endpoint_matches(self, request):
        return (
            request.method == "POST"
            and str(request.url) == self.authority.endpoint + "/responses"
        )
