"""Private bounded UDS authority. No SDK headers cross the solver boundary.

Session names are capability-bound claims, not independent Foundation provenance.
Only the parent installs model/schema policy, starts/finishes cells and owns keys.
The solver's existing adapter ledger remains a nonauthoritative shadow ledger.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import math
import os
import re
import secrets
import stat
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

from anchors_transport import Policy, validate
from live_transport import canonical, fingerprint, httpx, require
from repair_assessor import strict_json

WIRE_VERSION = "anchors-ipc/v1"
FRAME_MAX = 400_000
RESPONSE_MAX = 262_144
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def identity(value):
    require(type(value) is str and IDENTIFIER.fullmatch(value), "ipc_identity")
    return value


@contextlib.contextmanager
def socket_address(path):
    """Linux dirfd address avoids sockaddr_un length limits without changing cwd."""
    path = Path(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield f"/proc/self/fd/{fd}/{path.name}"
    finally:
        os.close(fd)


async def read_frame(reader):
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    require(0 < size <= FRAME_MAX, "ipc_frame_size")
    return strict_json(await reader.readexactly(size), FRAME_MAX)


async def write_frame(writer, value):
    raw = canonical(value)
    require(0 < len(raw) <= FRAME_MAX, "ipc_frame_size")
    writer.write(struct.pack("!I", len(raw)) + raw)
    await writer.drain()


@dataclass(frozen=True)
class CellAdmission:
    cell_id: str
    root_model: str
    worker_model: str
    root_effort: str
    worker_effort: str
    # Store canonical bytes so caller mutation cannot widen a running controller.
    root_tools: bytes = field(repr=False)
    worker_tools: bytes = field(repr=False)

    def policy(self, context):
        require(
            type(context) is dict
            and set(context)
            == {"cell_id", "session_id", "parent_id", "phase", "role_origin"},
            "ipc_context",
        )
        require(context["cell_id"] == self.cell_id, "ipc_cell")
        identity(context["session_id"])
        if context["parent_id"] is not None:
            identity(context["parent_id"])
        root = context["phase"] == "root"
        return Policy(
            **context,
            expected_model=self.root_model if root else self.worker_model,
            expected_effort=self.root_effort if root else self.worker_effort,
            wire_tools=tuple(
                strict_json(self.root_tools if root else self.worker_tools, 65536)
            ),
        )


@dataclass(frozen=True)
class CampaignBounds:
    wall_s: int = 3600
    requests: int = 48
    reserved_tokens: int = 50_596_608

    def __post_init__(self):
        for value, ceiling in zip(vars(self).values(), (3600, 48, 50_596_608)):
            require(type(value) is int and 0 < value <= ceiling, "campaign_bound")


class Controller:
    """One parent-owned, single-use campaign; durable accounting before upstream.

    ``headers`` is a selected mount/env projection, never the whole provider config.
    The upstream transport must be controller-owned, with no ambient proxy/redirect.
    Reopening is deliberately refused: recovery requires reconciling the old ledger.
    """

    def __init__(
        self,
        campaign_id,
        authority,
        admissions,
        headers,
        *,
        bounds=CampaignBounds(),
        upstream=None,
    ):
        identity(campaign_id)
        require(httpx is not None, "httpx_unavailable")
        require(
            type(headers) is dict
            and set(headers) == {"Authorization"}
            and type(headers["Authorization"]) is str
            and headers["Authorization"].startswith("Bearer ")
            and len(headers["Authorization"]) > 7
            and "\r" not in headers["Authorization"]
            and "\n" not in headers["Authorization"],
            "credential_projection",
        )
        require(
            tuple(a.cell_id for a in admissions) == ("A0", "B1"),
            "two_cell_schedule",
        )
        require(not authority.ledger.events()[1:], "campaign_already_used")
        self.campaign_id, self.authority, self.bounds = campaign_id, authority, bounds
        self.admissions = {a.cell_id: a for a in admissions}
        self._headers = dict(headers)
        self._capabilities = {
            cell: secrets.token_urlsafe(32) for cell in self.admissions
        }
        self._sessions, self._ids, self._responses = {}, set(), set()
        self._lock = asyncio.Lock()
        self._started = time.monotonic()
        self._upstream = upstream or httpx.AsyncHTTPTransport(
            retries=0, trust_env=False
        )
        self._server, self._path, self._tasks = None, None, set()
        self._connections = 0
        self.closed = False

    def capability(self, cell_id):
        return self._capabilities[cell_id]

    async def start(self, path):
        path = Path(path)
        require(self._server is None and not self.closed, "ipc_server_once")
        require(
            path.parent.is_dir()
            and not path.parent.is_symlink()
            and path.parent.resolve() == path.parent
            and path.parent.stat().st_mode & 0o077 == 0
            and not path.exists(),
            "ipc_private_directory",
        )
        with socket_address(path) as address:
            self._server = await asyncio.start_unix_server(
                self._connection, path=address
            )
        self._path = path
        self._inode = path.stat().st_ino
        path.chmod(0o600)
        return self

    async def _connection(self, reader, writer):
        task = asyncio.current_task()
        self._tasks.add(task)
        self._connections += 1
        try:
            require(self._connections <= 8, "ipc_connections")
            timeout = min(65, self.authority.timeout_s + 5)
            try:
                result = await asyncio.wait_for(self._exchange(reader), timeout=timeout)
            except Exception:
                # Never echo a provider exception, endpoint, header or input.
                result = {"ok": False, "error": "controller_refused"}
            await asyncio.wait_for(write_frame(writer, result), timeout=5)
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except Exception:
                writer.transport.abort()
            self._connections -= 1
            self._tasks.discard(task)

    async def _exchange(self, reader):
        return await self.dispatch(await read_frame(reader))

    async def dispatch(self, frame):
        require(
            type(frame) is dict
            and set(frame)
            == {
                "version",
                "campaign_id",
                "capability",
                "request_id",
                "context",
                "method",
                "url",
                "timeout",
                "body",
            },
            "ipc_fields",
        )
        require(
            frame["version"] == WIRE_VERSION
            and frame["campaign_id"] == self.campaign_id,
            "ipc_campaign",
        )
        context = frame["context"]
        require(type(context) is dict, "ipc_context")
        cell = context.get("cell_id")
        require(type(cell) is str and cell in self.admissions, "ipc_cell")
        capability = frame["capability"]
        require(
            type(capability) is str
            and len(capability) <= 128
            and hmac.compare_digest(capability, self._capabilities[cell]),
            "ipc_auth",
        )
        request_id = identity(frame["request_id"])
        require(
            frame["method"] == "POST"
            and frame["url"] == self.authority.endpoint + "/responses",
            "ipc_route",
        )
        timeout = frame["timeout"]
        require(
            type(timeout) is dict
            and set(timeout) == {"connect", "read", "write", "pool"}
            and all(
                type(x) in (int, float)
                and math.isfinite(x)
                and 0 < x <= self.authority.timeout_s
                for x in timeout.values()
            ),
            "ipc_timeout",
        )
        require(type(frame["body"]) is str, "ipc_body")
        raw = base64.b64decode(frame["body"], validate=True)
        body = strict_json(raw, self.authority.ledger.limits.body_bytes_max)
        policy = self.admissions[cell].policy(context)
        validate(body, policy, self.authority.ledger.limits)
        require(
            canonical(body.get("tools", [])) == canonical(list(policy.wire_tools)),
            "ipc_schema_exact",
        )
        async with self._lock:
            require(not self.closed, "ipc_closed")
            require(
                time.monotonic() - self._started < self.bounds.wall_s,
                "campaign_deadline",
            )
            require(request_id not in self._ids, "ipc_replay")
            sessions = self._sessions.setdefault(cell, {})
            if policy.phase == "root":
                require(
                    sessions.get("root", policy.session_id) == policy.session_id,
                    "ipc_root_rebind",
                )
            else:
                require(
                    sessions.get("root") == policy.parent_id
                    and policy.session_id != policy.parent_id
                    and sessions.get("worker", policy.session_id) == policy.session_id,
                    "ipc_worker_lineage",
                )
            events = self.authority.ledger.events()
            calls = [e for e in events if e["event"] == "reserve"]
            require(len(calls) < self.bounds.requests, "campaign_request_cap")
            require(not any(e["logical_id"] == request_id for e in calls), "ipc_replay")
            tokens = (
                self.authority.ledger.limits.native_context_max
                + self.authority.ledger.limits.output_max
            )
            require(
                sum(e["reserved_tokens"] for e in calls) + tokens
                <= self.bounds.reserved_tokens,
                "campaign_token_cap",
            )
            reservation = self.authority.ledger.reserve(
                policy, body, "generation", self.authority.quote, request_id
            )
            self._ids.add(request_id)
            sessions[policy.phase] = policy.session_id
            response = None
            try:
                # No solver-controlled headers, proxies, target or auth survive.
                request = httpx.Request(
                    "POST",
                    self.authority.endpoint + "/responses",
                    content=raw,
                    headers={**self._headers, "content-type": "application/json"},
                    extensions={"timeout": timeout},
                )
                remaining = self.bounds.wall_s - (time.monotonic() - self._started)

                async def send():
                    nonlocal response
                    response = await self._upstream.handle_async_request(request)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        require(size <= RESPONSE_MAX, "ipc_response_size")
                        chunks.append(chunk)
                    return b"".join(chunks)

                data = await asyncio.wait_for(
                    send(), min(self.authority.timeout_s, remaining)
                )
                # Defend against a misconfigured gateway echoing controller auth.
                require(
                    self._headers["Authorization"][7:].encode() not in data,
                    "ipc_credential_echo",
                )
                payload = strict_json(data, RESPONSE_MAX)
                credential = self._headers["Authorization"][7:]

                def no_credential(value):
                    if isinstance(value, str):
                        require(credential not in value, "ipc_credential_echo")
                    elif isinstance(value, dict):
                        for key, item in value.items():
                            no_credential(key)
                            no_credential(item)
                    elif isinstance(value, list):
                        for item in value:
                            no_credential(item)

                no_credential(payload)
                response_id = identity(payload.get("id"))
                require(response_id not in self._responses, "ipc_response_replay")
                self.authority.ledger.response(
                    reservation, payload, self.authority.quote, response.status_code
                )
                self._responses.add(response_id)
                return {
                    "ok": True,
                    "request_id": request_id,
                    "status": response.status_code,
                    "body": base64.b64encode(data).decode("ascii"),
                }
            except BaseException:
                self.authority.ledger.fault(reservation)
                raise
            finally:
                if response is not None:
                    await asyncio.wait_for(response.aclose(), 5)

    async def close(self):
        self.closed = True
        try:
            if self._server is not None:
                self._server.close()
                await asyncio.wait_for(self._server.wait_closed(), 2)
            tasks = tuple(self._tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 5
                )
            await asyncio.wait_for(self._upstream.aclose(), 5)
        finally:
            self._headers.clear()
            self._capabilities.clear()
            if self._path and self._path.exists():
                require(
                    stat.S_ISSOCK(self._path.stat().st_mode)
                    and self._path.stat().st_ino == self._inode,
                    "ipc_socket_replaced",
                )
                self._path.unlink()


class Receiver:
    """HTTPX2-compatible receiver, carrying ONLY an opaque per-cell capability."""

    def __init__(self, path, campaign_id, capability, policy, timeout_s=60):
        self.path, self.campaign_id = str(path), campaign_id
        self._capability, self.policy = capability, policy
        self.timeout_s, self.closed = timeout_s, False

    async def handle_async_request(self, request):
        require(not self.closed, "ipc_receiver_closed")
        request_id = secrets.token_hex(16)
        context = {
            key: getattr(self.policy, key)
            for key in ("cell_id", "session_id", "parent_id", "phase", "role_origin")
        }
        frame = {
            "version": WIRE_VERSION,
            "campaign_id": self.campaign_id,
            "capability": self._capability,
            "request_id": request_id,
            "context": context,
            "method": request.method,
            "url": str(request.url),
            "timeout": request.extensions.get("timeout"),
            "body": base64.b64encode(request.content).decode("ascii"),
        }

        async def exchange():
            with socket_address(self.path) as address:
                reader, writer = await asyncio.open_unix_connection(address)
            try:
                await write_frame(writer, frame)
                result = await read_frame(reader)
                require(
                    type(result) is dict
                    and set(result) == {"ok", "request_id", "status", "body"}
                    and result["ok"] is True
                    and result["request_id"] == request_id
                    and result["status"] == 200,
                    "ipc_controller_refused",
                )
                data = base64.b64decode(result["body"], validate=True)
                require(len(data) <= RESPONSE_MAX, "ipc_response_size")
                return httpx.Response(
                    200, content=data, headers={"content-type": "application/json"}
                )
            finally:
                writer.close()
                await writer.wait_closed()

        return await asyncio.wait_for(exchange(), self.timeout_s + 5)

    async def aclose(self):
        self.closed = True
        self._capability = ""


def receiver_factory(path, campaign_id, capability, timeout_s=60):
    return lambda policy: Receiver(path, campaign_id, capability, policy, timeout_s)


def selected_headers(credential_env, environ=None):
    """Tester-style exact env reference; controller ONLY, no store discovery."""
    require(
        type(credential_env) is str
        and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", credential_env),
        "credential_reference",
    )
    value = (os.environ if environ is None else environ).get(credential_env)
    require(type(value) is str and bool(value), "credential_missing")
    return {"Authorization": "Bearer " + value}


def policy_lock(admissions):
    return fingerprint(
        [
            {
                **vars(a),
                "root_tools": strict_json(a.root_tools, 65536),
                "worker_tools": strict_json(a.worker_tools, 65536),
            }
            for a in admissions
        ]
    )
