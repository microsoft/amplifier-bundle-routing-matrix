"""Final HTTP admission for the separate routing-live-smoke/v1 contract.

No environment, credentials, provider tables, or network are consulted on import.
Quotes are supplied by the controller. The append-only ledger is accounting
authority; an interrupted reservation is unresolved, never automatically refunded.
"""

from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

try:
    import httpx2 as httpx
except ImportError:  # Offline planning/tests do not require the optional SDK stack.
    try:
        import httpx
    except ImportError:
        httpx = None

VERSION = "routing-live-smoke/v1"
STANDARD_ENDPOINT = "https://api.openai.com/v1"
COUNT_PATH = "/v1/responses/input_tokens"
GENERATION_PATH = "/v1/responses"
COUNT_FIELDS = frozenset(
    {
        "input",
        "instructions",
        "model",
        "parallel_tool_calls",
        "reasoning",
        "text",
        "tool_choice",
        "tools",
        "truncation",
    }
)
GENERATION_FIELDS = COUNT_FIELDS | {
    "max_output_tokens",
    "store",
    "stream",
    "service_tier",
    "include",
}
ROOT_MODEL = "gpt-6.1-sol"
WORKER_MODELS = (ROOT_MODEL, "gpt-6-astra")
TOOL_NAME = "delegate_coding"
TOOL_DESCRIPTION = "Run the fixed interval-union task once through the coding resolver."
TOOL_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
WIRE_TOOL = {
    "type": "function",
    "name": TOOL_NAME,
    "description": TOOL_DESCRIPTION,
    "parameters": TOOL_SCHEMA,
    "strict": False,
}


class SmokeBlocked(RuntimeError):
    """Only a safe boundary code is exposed, never an upstream exception body."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise SmokeBlocked(code)


def integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def strict_json(raw: bytes, bound: int = 262144) -> Any:
    require(isinstance(raw, bytes) and len(raw) <= bound, "json_size")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "json_duplicate_key")
            result[key] = value
        return result

    def bad_constant(_):
        raise SmokeBlocked("json_nonfinite")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=bad_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise SmokeBlocked("json_invalid") from None


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def money(value: Any) -> Decimal:
    require(isinstance(value, (str, Decimal)), "decimal_required")
    try:
        parsed = Decimal(value)
    except Exception:
        raise SmokeBlocked("decimal_invalid") from None
    require(parsed.is_finite() and parsed >= 0, "decimal_invalid")
    return parsed


def ceil_usd(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class SmokeLimits:
    campaign_usd: Decimal = Decimal("100")
    cell_usd: Decimal = Decimal("40")
    whole_cell_s: int = 1200
    generation_max: int = 3
    count_max: int = 0
    body_bytes_max: int = 8192
    native_context_max: int = 1050000
    output_max: int = 4096
    reserved_tokens_max: int = 3162288

    def __post_init__(self):
        require(
            type(self.campaign_usd) is Decimal and type(self.cell_usd) is Decimal,
            "decimal_required",
        )
        require(
            all(
                type(getattr(self, k)) is int
                for k in (
                    "whole_cell_s",
                    "generation_max",
                    "count_max",
                    "body_bytes_max",
                    "native_context_max",
                    "output_max",
                    "reserved_tokens_max",
                )
            ),
            "integer_limit_required",
        )
        require(
            self.campaign_usd == Decimal("100")
            and self.cell_usd == Decimal("40")
            and self.whole_cell_s == 1200
            and self.generation_max == 3
            and self.count_max == 0
            and self.body_bytes_max == 8192
            and self.native_context_max == 1050000
            and self.output_max == 4096
            and self.reserved_tokens_max == 3162288,
            "unsupported_limits",
        )


@dataclass(frozen=True)
class ModelRate:
    fresh_input: Decimal
    cache_read: Decimal
    cache_write: Decimal
    output: Decimal
    request_usd: Decimal

    def __post_init__(self):
        for value in vars(self).values():
            require(type(value) is Decimal, "decimal_required")
            money(value)


@dataclass(frozen=True)
class PriceQuote:
    revision: str
    source: str
    verified_at: datetime
    effective_at: datetime
    expires_at: datetime
    binding_ref: str
    service_tier: str
    currency: str
    rates: dict[str, ModelRate]
    native_context_max: int
    window_source: str
    long_context_rates: dict[str, ModelRate]
    cache_semantics: str = "cached-subset-no-writes"

    def __post_init__(self):
        require(
            all(
                isinstance(x, str) and 0 < len(x) <= 256
                for x in (
                    self.revision,
                    self.source,
                    self.binding_ref,
                    self.service_tier,
                )
            ),
            "quote_provenance",
        )
        require(self.currency == "USD", "quote_currency")
        require(self.service_tier == "default", "quote_service_tier")
        require(self.cache_semantics == "cached-subset-no-writes", "quote_semantics")
        require(set(self.rates) == set(WORKER_MODELS), "quote_models")
        require(
            all(isinstance(x, ModelRate) for x in self.rates.values()), "quote_rates"
        )
        require(
            type(self.native_context_max) is int and self.native_context_max == 1050000,
            "quote_window",
        )
        require(
            isinstance(self.window_source, str) and bool(self.window_source),
            "quote_window_source",
        )
        require(set(self.long_context_rates) == set(WORKER_MODELS), "quote_long_rates")
        for model, expected in (
            (ROOT_MODEL, (Decimal("5"), Decimal("15"))),
            ("gpt-6-astra", (Decimal("25"), Decimal("75"))),
        ):
            rate = self.long_context_rates[model]
            require(
                isinstance(rate, ModelRate)
                and max(rate.fresh_input, rate.cache_read, rate.cache_write)
                == expected[0]
                and rate.output == expected[1]
                and rate.request_usd == Decimal(0),
                "quote_long_rate_bound",
            )
            require(self.rates[model].request_usd == Decimal(0), "quote_extra_charge")
            ordinary = self.rates[model]
            require(
                max(ordinary.fresh_input, ordinary.cache_read, ordinary.cache_write)
                <= max(rate.fresh_input, rate.cache_read, rate.cache_write)
                and ordinary.output <= rate.output,
                "quote_underreserved",
            )
        for stamp in (self.verified_at, self.effective_at, self.expires_at):
            require(stamp.tzinfo is not None, "quote_timezone")
        object.__setattr__(self, "rates", MappingProxyType(dict(self.rates)))
        object.__setattr__(
            self, "long_context_rates", MappingProxyType(dict(self.long_context_rates))
        )

    def validate(self, now: datetime) -> None:
        require(
            self.effective_at <= now and self.verified_at <= now < self.expires_at,
            "quote_expired_or_future",
        )

    @property
    def lock(self) -> str:
        return fingerprint(
            {
                "revision": self.revision,
                "source": self.source,
                "verified_at": self.verified_at.isoformat(),
                "effective_at": self.effective_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
                "binding_ref": self.binding_ref,
                "service_tier": self.service_tier,
                "currency": self.currency,
                "cache_semantics": self.cache_semantics,
                "native_context_max": self.native_context_max,
                "window_source": self.window_source,
                "long_context_rates": {
                    m: {k: str(v) for k, v in vars(r).items()}
                    for m, r in self.long_context_rates.items()
                },
                "rates": {
                    m: {k: str(v) for k, v in vars(r).items()}
                    for m, r in self.rates.items()
                },
            }
        )

    def reserve(self, model: str) -> Decimal:
        rate = self.long_context_rates[model]
        return (
            Decimal(self.native_context_max)
            * max(rate.fresh_input, rate.cache_read, rate.cache_write)
            / Decimal(1000000)
            + Decimal(4096) * rate.output / Decimal(1000000)
            + rate.request_usd
        ).quantize(Decimal("0.01"), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class SessionPolicy:
    cell_id: str
    session_id: str
    parent_id: str | None
    role_origin: str
    phase: str
    expected_model: str
    expected_effort: str = "high"

    def __post_init__(self):
        require(self.cell_id in {"A0", "A1", "B1"}, "cell_identity")
        require(self.phase in {"root", "worker"}, "phase")
        require(self.expected_effort == "high", "effort")
        require(self.expected_model in WORKER_MODELS, "model")
        if self.phase == "root":
            require(
                self.parent_id is None
                and self.role_origin == "controller"
                and self.expected_model == ROOT_MODEL,
                "root_policy",
            )
        else:
            require(
                bool(self.parent_id)
                and self.role_origin == "coding"
                and self.expected_model
                == ("gpt-6-astra" if self.cell_id == "B1" else ROOT_MODEL),
                "worker_policy",
            )


def validate_payload(body: dict, policy: SessionPolicy, kind: str) -> str:
    """Version-pinned subset of the real provider's finalized count projection."""
    require(isinstance(body, dict), "request_object")
    allowed = COUNT_FIELDS if kind == "count" else GENERATION_FIELDS
    require(not (set(body) - allowed), "request_unknown_field")
    require(body.get("include", []) == [], "encrypted_replay_disallowed")
    require(body.get("model") == policy.expected_model, "request_model")
    reasoning = body.get("reasoning")
    require(
        isinstance(reasoning, dict)
        and set(reasoning) <= {"effort", "summary"}
        and reasoning.get("effort") == "high"
        and reasoning.get("summary", "auto") in {"auto", "concise", "detailed"},
        "request_effort",
    )
    require("input" in body and isinstance(body["input"], list), "request_input")
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
    # No image/file/audio/hosted tools/remote context can enter either endpoint.
    for item in body["input"]:
        require(isinstance(item, dict), "input_item")
        kind_ = item.get("type", "message")
        if kind_ == "message":
            require(
                set(item) <= {"type", "role", "content"}
                and item.get("role") in {"user", "assistant", "system", "developer"},
                "input_message",
            )
            content = item.get("content")
            if isinstance(content, str):
                continue
            require(isinstance(content, list), "input_content")
            for part in content:
                require(
                    isinstance(part, dict)
                    and set(part) <= {"type", "text", "annotations"}
                    and part.get("type") in {"input_text", "output_text"}
                    and isinstance(part.get("text"), str)
                    and part.get("annotations", []) == [],
                    "input_text_only",
                )
        elif kind_ == "function_call":
            require(
                policy.phase == "root"
                and set(item) <= {"type", "call_id", "name", "arguments"}
                and item.get("name") == TOOL_NAME
                and item.get("arguments") == "{}",
                "input_function",
            )
        elif kind_ == "function_call_output":
            require(
                policy.phase == "root"
                and set(item) == {"type", "call_id", "output"}
                and isinstance(item["output"], str),
                "input_function_output",
            )
        else:
            raise SmokeBlocked("input_type")
    if policy.phase == "root":
        require(
            body.get("tools") == [WIRE_TOOL]
            and body.get("tool_choice") == "auto"
            and body.get("parallel_tool_calls") is True,
            "root_tools",
        )
    else:
        require(
            not ({"tools", "tool_choice", "parallel_tool_calls"} & set(body)),
            "worker_tools",
        )
    if kind == "generation":
        require(
            body.get("max_output_tokens") == 4096
            and body.get("store") is False
            and body.get("service_tier") == "default"
            and body.get("stream", False) is False,
            "generation_policy",
        )
    return fingerprint({key: body[key] for key in sorted(COUNT_FIELDS & set(body))})


class Ledger:
    """Single writer transaction lock plus fsync before every wire attempt.

    Reconstructs state from immutable events. New instances and processes cannot
    replay a cell/proof or turn a crashed request into refunded capacity.
    """

    version = VERSION

    def __init__(self, path: Path, campaign_lock: str, limits: SmokeLimits):
        self.path = Path(path)
        self.campaign_lock = campaign_lock
        self.limits = limits
        self._thread_lock = threading.RLock()
        require(self.path.parent.is_dir() and not self.path.is_symlink(), "ledger_path")
        with self.transaction() as events:
            if not events:
                self._append(
                    {
                        "event": "campaign",
                        "lock": campaign_lock,
                        "scheduled": ["A0", "A1", "B1"],
                    }
                )
            else:
                require(events[0].get("lock") == campaign_lock, "campaign_changed")

    @contextlib.contextmanager
    def transaction(self):
        with self._thread_lock:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "r+b") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                try:
                    raw = stream.read()
                    require(len(raw) <= 4 * 1024 * 1024, "ledger_size")
                    events = [strict_json(line) for line in raw.splitlines()]
                    require(
                        all(e.get("version") == self.version for e in events),
                        "ledger_version",
                    )
                    self._stream = stream
                    yield events
                finally:
                    self._stream = None
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def _append(self, record: dict) -> dict:
        record = copy.deepcopy(
            {"version": self.version, "id": uuid.uuid4().hex, **record}
        )
        require(self._stream is not None, "ledger_transaction")
        self._stream.seek(0, os.SEEK_END)
        self._stream.write(canonical(record) + b"\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        return record

    def events(self) -> list[dict]:
        with self.transaction() as events:
            return copy.deepcopy(events)

    @staticmethod
    def liability(events: list[dict], cell_id: str | None = None) -> Decimal:
        settlements = {e["wire_id"]: e for e in events if e["event"] == "settle"}
        observed = {
            e["wire_id"]: money(e["observed_priced_usd"])
            for e in events
            if e["event"] == "response" and e.get("observed_priced_usd") is not None
        }
        total = Decimal(0)
        for event in events:
            if event["event"] != "reserve":
                continue
            if cell_id is not None and event["cell_id"] != cell_id:
                continue
            settled = settlements.get(event["id"])
            total += (
                money(settled["usd"])
                if settled
                else max(
                    money(event["reserved_usd"]),
                    observed.get(event["id"], Decimal(0)),
                )
            )
        return total

    @staticmethod
    def unresolved(events: list[dict]) -> list[dict]:
        settled = {e["wire_id"] for e in events if e["event"] == "settle"}
        return [e for e in events if e["event"] == "reserve" and e["id"] not in settled]

    def start_cell(self, cell_id: str) -> dict:
        require(cell_id in {"A0", "A1", "B1"}, "cell_identity")
        with self.transaction() as events:
            started = [e for e in events if e["event"] == "cell_start"]
            ended = {e["cell_id"]: e for e in events if e["event"] == "cell_end"}
            require(not any(e["cell_id"] == cell_id for e in started), "cell_once_only")
            require(all(e["cell_id"] in ended for e in started), "cell_active")
            require(not self.unresolved(events), "liability_unresolved")
            require(
                all(e["receipt"]["instrumentation"] == "valid" for e in ended.values()),
                "prior_instrumentation",
            )
            require(cell_id == "A0" or "A0" in ended, "baseline_required")
            return self._append(
                {"event": "cell_start", "cell_id": cell_id, "started": time.time()}
            )

    def finish_cell(self, cell_id: str, receipt: dict) -> None:
        with self.transaction() as events:
            require(
                any(
                    e["event"] == "cell_start" and e["cell_id"] == cell_id
                    for e in events
                ),
                "cell_not_started",
            )
            require(
                not any(
                    e["event"] == "cell_end" and e["cell_id"] == cell_id for e in events
                ),
                "cell_already_ended",
            )
            self._append({"event": "cell_end", "cell_id": cell_id, "receipt": receipt})

    def abort_cell(self, cell_id: str, reason: str):
        with self.transaction():
            self._append(
                {
                    "event": "cell_abort",
                    "cell_id": cell_id,
                    "reason": reason if reason.isidentifier() else "protocol_failure",
                }
            )

    def reserve(
        self,
        policy: SessionPolicy,
        body: dict,
        kind: str,
        quote: PriceQuote,
        logical_id: str | None,
    ) -> dict:
        projection = validate_payload(body, policy, kind)
        quote.validate(datetime.now(timezone.utc))
        require(kind == "generation", "count_billing_unqualified")
        require(
            len(canonical(body)) <= self.limits.body_bytes_max, "request_body_bytes"
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
                    e["event"] == "cell_abort" and e["cell_id"] == policy.cell_id
                    for e in events
                ),
                "cell_aborted",
            )
            require(
                not any(
                    e["event"] == "cell_end" and e["cell_id"] == policy.cell_id
                    for e in events
                ),
                "cell_ended",
            )
            require(
                time.time() - starts[0]["started"] < self.limits.whole_cell_s,
                "cell_deadline",
            )
            require(not self.unresolved(events), "http_active_or_unresolved")
            reservations = [
                e
                for e in events
                if e["event"] == "reserve" and e["cell_id"] == policy.cell_id
            ]
            same_kind = [e for e in reservations if e["kind"] == kind]
            require(isinstance(logical_id, str) and bool(logical_id), "logical_id")
            require(len(same_kind) < self.limits.generation_max, "generation_cap")
            require(
                sum(e["phase"] == policy.phase for e in same_kind)
                < (2 if policy.phase == "root" else 1),
                "phase_cap",
            )
            require(
                not any(
                    e["logical_id"] == logical_id
                    or (
                        e["session_id"] == policy.session_id
                        and e["projection"] == projection
                    )
                    for e in same_kind
                ),
                "logical_or_payload_replay",
            )
            tokens = self.limits.native_context_max + self.limits.output_max
            require(
                sum(e["reserved_tokens"] for e in same_kind) + tokens
                <= self.limits.reserved_tokens_max,
                "reserved_token_cap",
            )
            charge = quote.reserve(policy.expected_model)
            require(
                self.liability(events) + charge <= self.limits.campaign_usd,
                "campaign_usd_cap",
            )
            require(
                self.liability(events, policy.cell_id) + charge <= self.limits.cell_usd,
                "cell_usd_cap",
            )
            return self._append(
                {
                    "event": "reserve",
                    **vars(policy),
                    "kind": kind,
                    "logical_id": logical_id if kind == "generation" else None,
                    "projection": projection,
                    "count_policy": "blocked_before_wire",
                    "native_input": None,
                    "input_bound_policy": "qualified_native_total_context_upper_bound",
                    "input_token_liability": self.limits.native_context_max,
                    "request_body_bytes": len(canonical(body)),
                    "reserved_tokens": tokens,
                    "quote_revision": quote.revision,
                    "quote_lock": quote.lock,
                    "reserved_usd": str(charge),
                    "wire_effort": body["reasoning"]["effort"],
                    "wire_output_cap": body.get("max_output_tokens"),
                    "started": time.time(),
                }
            )

    def response(
        self, reservation: dict, payload: dict, quote: PriceQuote, http_status: int
    ) -> None:
        with self.transaction() as events:
            persisted = next((e for e in events if e["id"] == reservation["id"]), None)
            require(persisted == reservation, "reservation_changed")
            require(quote.lock == reservation["quote_lock"], "quote_changed")
            require(
                reservation["id"] in {e["id"] for e in self.unresolved(events)},
                "wire_already_reconciled",
            )
            require(
                not any(
                    e.get("wire_id") == reservation["id"]
                    and e["event"] in {"response", "wire_fault"}
                    for e in events
                ),
                "response_replay",
            )
            require(isinstance(payload, dict), "response_object")
            usage = numeric_usage(payload.get("usage"))
            observed = {
                key: payload.get(key)
                if isinstance(payload.get(key), str) and 0 < len(payload[key]) <= 256
                else None
                for key in ("id", "model", "status", "service_tier")
            }
            settlement = settle_usage(usage, quote, reservation["expected_model"])
            priced_observation = (
                settlement
                if observed["model"] == reservation["expected_model"]
                and observed["service_tier"] == quote.service_tier
                else None
            )
            valid = (
                http_status == 200
                and observed["id"] is not None
                and observed["model"] == reservation["expected_model"]
                and observed["status"] == "completed"
                and observed["service_tier"] == quote.service_tier
                and settlement is not None
                and usage["input_tokens"] <= self.limits.native_context_max
                and usage["output_tokens"] <= self.limits.output_max
                and settlement <= money(reservation["reserved_usd"])
            )
            self._append(
                {
                    "event": "response",
                    "wire_id": reservation["id"],
                    "http_status": http_status,
                    **observed,
                    "usage": usage,
                    "valid": valid,
                    "observed_priced_usd": (
                        str(priced_observation)
                        if priced_observation is not None
                        else None
                    ),
                    "duration_s": max(0, time.time() - reservation["started"]),
                }
            )
            if valid:
                self._append(
                    {
                        "event": "settle",
                        "wire_id": reservation["id"],
                        "usd": str(settlement),
                    }
                )
            require(valid, "generation_measurement_invalid")

    def fault(self, reservation: dict) -> None:
        with self.transaction() as events:
            require(any(e == reservation for e in events), "reservation_changed")
            if not any(
                e.get("wire_id") == reservation["id"]
                and e["event"] in {"response", "wire_fault"}
                for e in events
            ):
                self._append(
                    {
                        "event": "wire_fault",
                        "wire_id": reservation["id"],
                        "accounting": "unknown",
                    }
                )

    def denied(self, policy: SessionPolicy, kind: str, code: str) -> None:
        with self.transaction() as events:
            require(sum(e["event"] == "denied" for e in events) < 64, "denial_log_cap")
            self._append(
                {
                    "event": "denied",
                    **vars(policy),
                    "kind": kind,
                    "disposition": "blocked_before_send",
                    "reason": code
                    if code.isidentifier() and code.islower()
                    else "admission_refused",
                }
            )


def numeric_usage(value: Any) -> dict | None:
    """Preserve all available numeric subdivisions, but never arbitrary strings."""
    if not isinstance(value, dict):
        return None
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 128:
            return None
        if integer(item):
            result[key] = item
        elif isinstance(item, dict):
            nested = numeric_usage(item)
            if nested is None:
                return None
            result[key] = nested
        else:
            return None
    return result


def settle_usage(usage: dict | None, quote: PriceQuote, model: str) -> Decimal | None:
    if usage is None or not all(
        integer(usage.get(k)) for k in ("input_tokens", "output_tokens", "total_tokens")
    ):
        return None
    inputs, outputs = usage["input_tokens"], usage["output_tokens"]
    if inputs + outputs != usage["total_tokens"]:
        return None
    details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    if not isinstance(details, dict) or not integer(details.get("cached_tokens")):
        return None
    if not isinstance(output_details, dict) or not integer(
        output_details.get("reasoning_tokens")
    ):
        return None
    # Other categories are retained, not silently treated as priced text.
    if set(usage) != {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "input_tokens_details",
        "output_tokens_details",
    }:
        return None
    if set(details) not in (
        {"cached_tokens"},
        {"cached_tokens", "cache_write_tokens"},
    ) or set(output_details) != {"reasoning_tokens"}:
        return None
    if "cache_write_tokens" in details and (
        not integer(details["cache_write_tokens"]) or details["cache_write_tokens"] != 0
    ):
        return None
    cached = details["cached_tokens"]
    if cached > inputs or output_details["reasoning_tokens"] > outputs:
        return None
    rate = (quote.long_context_rates if inputs > 272000 else quote.rates)[model]
    return ceil_usd(
        (
            Decimal(inputs - cached) * rate.fresh_input
            + Decimal(cached) * rate.cache_read
            + Decimal(outputs) * rate.output
        )
        / Decimal(1000000)
        + rate.request_usd
    )


@dataclass(frozen=True)
class AdmissionAuthority:
    ledger: Ledger
    quote: PriceQuote
    endpoint: str
    endpoint_qualified: bool
    binding_qualified: bool
    timeout_s: int = 60

    def __post_init__(self):
        require(
            type(self.endpoint_qualified) is bool
            and type(self.binding_qualified) is bool,
            "authority_qualification_type",
        )
        require(
            self.endpoint == STANDARD_ENDPOINT and self.endpoint_qualified,
            "endpoint_unqualified",
        )
        require(self.binding_qualified, "binding_unqualified")
        require(
            type(self.timeout_s) is int and 0 < self.timeout_s <= 60, "request_timeout"
        )


class AdmittedTransport(httpx.AsyncBaseTransport if httpx else object):
    count_path = COUNT_PATH

    def endpoint_matches(self, request):
        url = request.url
        return (
            request.method == "POST"
            and url.scheme == "https"
            and url.host == "api.openai.com"
            and url.port in {None, 443}
            and not url.query
            and not url.fragment
            and not url.userinfo
            and url.path == GENERATION_PATH
        )

    def __init__(
        self,
        authority: AdmissionAuthority,
        policy: SessionPolicy,
        verify_session: Callable[[], None],
        logical_id: Callable[[], str | None],
        receiver=None,
    ):
        self.authority = authority
        self.policy = policy
        self.verify_session = verify_session
        self.logical_id = logical_id
        if receiver is None:
            require(httpx is not None, "httpx_unavailable")
            receiver = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self.receiver = receiver
        self.closed = False

    async def handle_async_request(self, request):
        kind = "unknown"
        try:
            require(not self.closed, "transport_closed")
            url = request.url
            if request.method == "POST" and url.path == self.count_path:
                self.verify_session()
                self.authority.ledger.denied(
                    self.policy, "count", "count_billing_unqualified"
                )
                raise RuntimeError("smoke.count_billing_unqualified")
            require(
                self.endpoint_matches(request),
                "wire_endpoint",
            )
            timeout = request.extensions.get("timeout")
            require(
                isinstance(timeout, dict)
                and set(timeout) == {"connect", "read", "write", "pool"}
                and all(
                    isinstance(x, (int, float))
                    and not isinstance(x, bool)
                    and 0 < x <= self.authority.timeout_s
                    for x in timeout.values()
                ),
                "wire_timeout",
            )
            self.verify_session()
            body = strict_json(
                request.content, self.authority.ledger.limits.body_bytes_max
            )
            kind = "count" if url.path == self.count_path else "generation"
            reservation = self.authority.ledger.reserve(
                self.policy,
                body,
                kind,
                self.authority.quote,
                self.logical_id(),
            )
        except SmokeBlocked as exc:
            self.authority.ledger.denied(self.policy, kind, str(exc))
            raise
        response = None
        try:
            response = await self.receiver.handle_async_request(request)
            # Stream into a bounded buffer instead of first allocating an unbounded aread.
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                require(size <= 262144, "response_size")
                chunks.append(chunk)
            raw = b"".join(chunks)
            payload = strict_json(raw)
            self.authority.ledger.response(
                reservation,
                payload,
                self.authority.quote,
                response.status_code,
            )
            require(httpx is not None, "httpx_unavailable")
            return httpx.Response(
                response.status_code,
                content=raw,
                headers={"content-type": "application/json"},
            )
        except BaseException:
            self.authority.ledger.fault(reservation)
            raise SmokeBlocked("wire_or_measurement_failure") from None
        finally:
            if response is not None:
                await response.aclose()

    async def aclose(self):
        await self.receiver.aclose()
        self.closed = True
