"""Parent-only two-cell orchestration and concrete bubblewrap execution.

No resource provisioner, scheduler, host eval fallback, credential-store discovery
or public export. Run inside the parent's existing private DTU. Acceptance objects
are issued by the parent's infrastructure owner, NEVER read from solver input.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import resource
import signal
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from anchors_adapter import RepositoryLock, Sources, require_distinct_arms
from anchors_bridge import (
    CampaignBounds,
    CellAdmission,
    Controller,
    identity,
    policy_lock,
)
from anchors_transport import AnchorsLedger, Authority, Limits
from candidates import Snapshot, discover, plan_refresh
from interval_repair import Artifact, source_binding
from source_locks import SourceLock
from live_transport import SmokeBlocked, canonical, fingerprint, require
from repair_assessor import (
    DRIVER_SOURCE,
    AssessmentRequest,
    grade_receipt,
    make_request,
    strict_json,
)

VERSION = "anchors-campaign/v1"
FAILURE_CODES = frozenset(
    {
        "journey_incomplete",
        "snapshot_paths",
        "snapshot_protected",
        "snapshot_unsafe",
        "solver_execution",
        "solver_result",
        "resolved_treatment",
        "wire_incomplete",
        "solver_cleanup",
        "assessment_invalid",
        "sandbox_output_limit",
        "timeout",
        "cancelled",
        "unclassified",
    }
)


def failure_code(error):
    """Closed diagnostics only; never serialize arbitrary exception text."""
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if type(error) is SmokeBlocked and str(error) in FAILURE_CODES:
        return str(error)
    if type(error) is ValueError:
        return {
            "missing or unknown task path": "snapshot_paths",
            "protected public file changed": "snapshot_protected",
            "unsafe or unreadable task tree": "snapshot_unsafe",
        }.get(str(error), "unclassified")
    return "unclassified"


def read_solver_failure(raw):
    """Accept bounded typed diagnostics, never arbitrary solver log content."""
    try:
        value = strict_json(raw, 8192)
        require(
            type(value) is dict
            and set(value) == {"version", "failure"}
            and value["version"] == VERSION,
            "solver_failure",
        )
        result = value["failure"]
        require(
            type(result) is dict
            and set(result) == {"code", "journey", "cleanup"}
            and result["code"] in FAILURE_CODES
            and type(result["cleanup"]) is bool,
            "solver_failure",
        )
        journey = result["journey"]
        require(
            type(journey) is dict
            and set(journey)
            == {"delegated", "completed", "two_sessions", "protocol_error"}
            and all(type(v) is bool for v in journey.values()),
            "solver_failure",
        )
        return result
    except Exception:
        return None


def load_sources(value):
    """Explicit private map of path+content locks; never discover ambient installs."""
    require(
        type(value) is dict and set(value) == {"repositories", "runtime"},
        "source_map",
    )
    output = []
    for group in ("repositories", "runtime"):
        require(type(value[group]) is dict, "source_map")
        locks = []
        for name, lock in sorted(value[group].items()):
            require(
                type(lock) is dict and set(lock) == {"label", "path", "sha256"},
                "source_lock",
            )
            cls = RepositoryLock if group == "repositories" else SourceLock
            locks.append((name, cls(lock["label"], Path(lock["path"]), lock["sha256"])))
        output.append(tuple(locks))
    return Sources(*output)


def sources_spec(sources):
    return {
        group: {
            name: {"label": lock.label, "path": str(lock.path), "sha256": lock.sha256}
            for name, lock in getattr(sources, group)
        }
        for group in ("repositories", "runtime")
    }


def projection_digest(path, deadline=None):
    """Full confidentiality inventory: no ignored caches/config/private subtrees."""
    path = Path(path)
    files, total = [], 0
    entries = [path] if path.is_file() else path.rglob("*")
    count = 0
    for entry in entries:
        count += 1
        require(deadline is None or time.monotonic() < deadline, "sandbox_deadline")
        require(count <= 65536, "projection_size")
        if entry.is_symlink():
            files.append((str(entry.relative_to(path)), "link", os.readlink(entry)))
        elif entry.is_file():
            total += entry.stat().st_size
            require(total <= 4_294_967_296, "projection_size")
            with entry.open("rb") as stream:
                hasher = hashlib.sha256()
                while chunk := stream.read(1_048_576):
                    require(
                        deadline is None or time.monotonic() < deadline,
                        "sandbox_deadline",
                    )
                    hasher.update(chunk)
                digest = hasher.hexdigest()
            files.append(
                (str(entry.relative_to(path)) if entry != path else ".", "file", digest)
            )
        else:
            require(entry.is_dir(), "projection_special_file")
    require(bool(files), "projection_empty")
    return fingerprint(sorted(files))


@dataclass(frozen=True)
class SandboxSpec:
    """Exact parent-audited RO runtime/source projection; no personal HOME mount.

    Paths retain their names so editable imports and SourceLocks remain valid.
    Parent must audit contents too; path checks cannot prove absence of secrets.
    """

    purpose: str
    python: str
    readonly: tuple[str, ...]
    projection_locks: tuple[tuple[str, str], ...]
    resource_envelope: str
    executable: str = "/usr/bin/bwrap"
    memory_bytes: int = 2_147_483_648
    process_count: int = 64
    log_bytes: int = 16_384
    tmpfs_bytes: int = 134_217_728
    system_aliases: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        require(self.purpose in {"solver", "assessor"}, "sandbox_purpose")
        require(
            type(self.readonly) is tuple and 0 < len(self.readonly) <= 64,
            "sandbox_mounts",
        )
        for path in (self.python, self.executable, *self.readonly):
            p = Path(path)
            require(
                p.is_absolute()
                and ".." not in p.parts
                and p.exists()
                and not p.is_symlink()
                and str(p.resolve()) == path,
                "sandbox_path",
            )
        for path in self.readonly:
            require(
                path
                not in {
                    "/",
                    "/home",
                    "/root",
                    "/tmp",
                    "/var",
                    "/run",
                    "/proc",
                    "/sys",
                    "/dev",
                    "/etc",
                }
                and path != str(Path.home()),
                "sandbox_broad_mount",
            )
        require(
            any(Path(self.python).is_relative_to(Path(p)) for p in self.readonly),
            "sandbox_python_mount",
        )
        require(
            type(self.projection_locks) is tuple
            and tuple(p for p, _ in self.projection_locks) == self.readonly
            and type(self.resource_envelope) is str
            and bool(self.resource_envelope),
            "sandbox_projection_locks",
        )
        for value, maximum in (
            (self.memory_bytes, 2_147_483_648),
            (self.process_count, 64),
            (self.log_bytes, 16_384),
            (self.tmpfs_bytes, 268_435_456),
        ):
            require(type(value) is int and 0 < value <= maximum, "sandbox_limits")
        allowed_aliases = {
            "/bin": "/usr/bin",
            "/sbin": "/usr/sbin",
            "/lib": "/usr/lib",
            "/lib64": "/usr/lib64",
        }
        require(type(self.system_aliases) is tuple, "sandbox_aliases")
        require(
            len(dict(self.system_aliases)) == len(self.system_aliases),
            "sandbox_aliases",
        )
        for alias, target in self.system_aliases:
            require(
                allowed_aliases.get(alias) == target
                and any(Path(target).is_relative_to(Path(p)) for p in self.readonly),
                "sandbox_alias_outside_projection",
            )

    @property
    def lock(self):
        return self.lock_at()

    def lock_at(self, deadline=None):
        self.validate_projection(deadline)
        return fingerprint(
            {
                "spec": asdict(self),
                "launcher": Path(__file__).read_bytes().hex(),
                "bwrap": fingerprint(Path(self.executable).read_bytes().hex()),
                "python": projection_digest(self.python, deadline),
            }
        )

    def validate_projection(self, deadline=None):
        for path, digest in self.projection_locks:
            require(
                projection_digest(path, deadline) == digest,
                "sandbox_projection_changed",
            )


@dataclass(frozen=True)
class IsolationAcceptance:
    """Trusted parent infrastructure result, not a solver qualification boolean.

    Receipt/canary evidence remains private. Issuing this object requires external
    observation of exactly this spec; this library cannot authenticate its issuer.
    A callable receiver or DTU allow_external is never this acceptance.
    """

    sandbox_lock: str
    receipt_ref: str = field(repr=False)
    checks: frozenset[str]

    def require_for(self, spec, deadline=None):
        expected = {
            "network_denied",
            "credentials_absent",
            "private_paths_absent",
            "descendants_reaped",
            "resource_bounds",
        }
        if spec.purpose == "solver":
            expected |= {"uds_only"}
        else:
            expected |= {"assessor_controls"}
        require(
            self.sandbox_lock == spec.lock_at(deadline)
            and bool(self.receipt_ref)
            and self.checks == frozenset(expected),
            "independent_isolation_acceptance_required",
        )


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    cleanup: bool


class BubblewrapSandbox:
    """Concrete networkless, private-root runner; no unrestricted-host fallback."""

    def __init__(self, spec, acceptance):
        require(type(spec) is SandboxSpec, "sandbox_spec")
        require(
            type(acceptance) is IsolationAcceptance,
            "independent_isolation_acceptance_required",
        )
        acceptance.require_for(spec)
        self.spec, self.acceptance = spec, acceptance
        self.active = None

    def command(self, argv, *, socket_path=None):
        spec = self.spec
        require(type(argv) in (tuple, list) and bool(argv), "sandbox_argv")
        args = [
            spec.executable,
            "--unshare-all",
            "--unshare-user",
            "--die-with-parent",
            "--new-session",
            "--disable-userns",
            "--assert-userns-disabled",
            "--uid",
            "65534",
            "--gid",
            "65534",
            "--cap-drop",
            "ALL",
            "--clearenv",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            str(spec.tmpfs_bytes),
            "--tmpfs",
            "/tmp",
            "--size",
            str(spec.tmpfs_bytes),
            "--tmpfs",
            "/work",
            "--dir",
            "/ipc",
        ]
        for path in spec.readonly:
            args.extend(["--ro-bind", path, path])
        for alias, target in spec.system_aliases:
            args.extend(["--symlink", target, alias])
        if socket_path is not None:
            require(spec.purpose == "solver", "assessor_no_ipc")
            args.extend(["--ro-bind", str(socket_path), "/ipc/controller.sock"])
        args.extend(
            [
                "--setenv",
                "PATH",
                f"{Path(spec.python).parent}:/usr/bin:/bin",
                "--setenv",
                "HOME",
                "/work",
                "--setenv",
                "TMPDIR",
                "/tmp",
                "--setenv",
                "PYTHONDONTWRITEBYTECODE",
                "1",
                "--setenv",
                "LC_ALL",
                "C.UTF-8",
                "--chdir",
                "/work",
                "--",
                *argv,
            ]
        )
        return args

    async def run(self, argv, input_bytes, *, wall_s, output_bytes, socket_path=None):
        deadline = time.monotonic() + wall_s
        await asyncio.wait_for(
            asyncio.to_thread(self.acceptance.require_for, self.spec, deadline),
            max(0, deadline - time.monotonic()),
        )
        require(self.active is None, "sandbox_busy")
        require(
            type(input_bytes) is bytes
            and len(input_bytes) <= 1_048_576
            and type(wall_s) in (int, float)
            and 0 < wall_s <= 1200
            and type(output_bytes) is int
            and 0 < output_bytes <= 400_000,
            "sandbox_bounds",
        )
        spec = self.spec

        def limits():
            os.umask(0o077)
            resource.setrlimit(
                resource.RLIMIT_AS, (spec.memory_bytes, spec.memory_bytes)
            )
            resource.setrlimit(
                resource.RLIMIT_NPROC, (spec.process_count, spec.process_count)
            )
            resource.setrlimit(resource.RLIMIT_FSIZE, (262144, 262144))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (int(wall_s) + 1, int(wall_s) + 1))

        require(time.monotonic() < deadline, "sandbox_deadline")
        creation = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *self.command(argv, socket_path=socket_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={},
                close_fds=True,
                start_new_session=True,
                preexec_fn=limits,
            )
        )
        interruption = None
        try:
            process = await asyncio.wait_for(
                asyncio.shield(creation), max(0, deadline - time.monotonic())
            )
        except BaseException as error:
            # A deadline ends execution, never custody of a fork in progress.
            interruption = error
            while not creation.done():
                try:
                    await asyncio.shield(creation)
                except asyncio.CancelledError:
                    continue
            process = creation.result()
        self.active = process

        async def read(stream, maximum):
            chunks, size = [], 0
            while chunk := await stream.read(4096):
                size += len(chunk)
                require(size <= maximum, "sandbox_output_limit")
                chunks.append(chunk)
            return b"".join(chunks)

        async def execute():
            process.stdin.write(input_bytes)
            await process.stdin.drain()
            process.stdin.close()
            stdout, _ = await asyncio.gather(
                read(process.stdout, output_bytes), read(process.stderr, spec.log_bytes)
            )
            await process.wait()
            return stdout

        task = asyncio.create_task(execute())
        try:
            if interruption is not None:
                raise interruption
            stdout = await asyncio.wait_for(task, max(0, deadline - time.monotonic()))
            returncode = process.returncode
        finally:
            # Namespace init exit kills namespace descendants. Also kill the owned
            # outer process group, even if the immediate process already exited.
            async def reap():
                task.cancel()
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.gather(task, return_exceptions=True)
                await process.wait()
                self.active = None

            cleanup = asyncio.create_task(reap())
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()
        return ProcessResult(returncode, stdout, process.returncode is not None)


# A supervisor INSIDE the sandbox captures only the standalone driver's result.
ASSESS_SUPERVISOR = r"""
import base64, json, os, subprocess, sys
from pathlib import Path
os.umask(0o077)
value = json.loads(sys.stdin.buffer.read(1048577))
Path('/work/driver.py').write_bytes(base64.b64decode(value['driver'], validate=True))
Path('/work/request.json').write_bytes(base64.b64decode(value['request'], validate=True))
child = subprocess.run([sys.executable, '-I', '-B', '/work/driver.py',
                       '/work/request.json', '/work/result.json'],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)
if child.returncode != 0:
    raise SystemExit(1)
path = Path('/work/result.json')
if not path.is_file() or path.stat().st_size > 16384:
    raise SystemExit(1)
sys.stdout.buffer.write(path.read_bytes())
"""


class IsolatedAssessor:
    """Async parent infrastructure API; request bytes/cases never reach solver."""

    def __init__(self, sandbox):
        require(
            type(sandbox) is BubblewrapSandbox and sandbox.spec.purpose == "assessor",
            "assessor_sandbox",
        )
        self.sandbox = sandbox

    async def run(self, request):
        require(
            type(request) is AssessmentRequest
            and request.driver_source == DRIVER_SOURCE,
            "assessor_driver",
        )
        result = await self.sandbox.run(
            [self.sandbox.spec.python, "-I", "-B", "-c", ASSESS_SUPERVISOR],
            canonical(
                {
                    "driver": base64.b64encode(request.driver_source).decode("ascii"),
                    "request": base64.b64encode(request.input_json).decode("ascii"),
                }
            ),
            wall_s=request.limits.wall_s,
            output_bytes=request.limits.output_bytes,
        )
        require(result.returncode == 0, "assessor_execution")
        receipt = strict_json(result.stdout, request.limits.output_bytes)
        raw = canonical({"execution": receipt, "cleanup": result.cleanup})
        require(len(raw) <= request.limits.output_bytes, "assessor_output")
        return raw

    def __call__(self, request):
        """Standalone repair_assessor.assess-compatible synchronous entry."""
        return asyncio.run(self.run(request))


async def select_pair(provider, binding_ref, family_masks, *, provenance):
    snapshot = await discover(
        provider, binding_ref, family_masks, ("tools",), provenance
    )
    require(snapshot.freshness == "bounded_live", "catalog_unqualified")
    require(set(family_masks) == {"sol", "luna"}, "pair_families")
    pair = []
    for family in ("sol", "luna"):
        choices = [c for c in snapshot.candidates if c.family == family]
        require(
            len(choices) == 1 and choices[0].latest is True, "catalog_pair_ambiguous"
        )
        pair.append(choices[0].id)
    require_distinct_arms(pair[0], pair[1])
    return snapshot, tuple(pair)


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    sources: Sources
    root_model: str
    workers: tuple[str, str]
    effort: str
    endpoint: str = field(repr=False)
    root_tools: bytes = field(repr=False)
    worker_tools: bytes = field(repr=False)
    catalog: Snapshot = field(repr=False)
    limits: Limits = Limits()
    bounds: CampaignBounds = CampaignBounds()

    def __post_init__(self):
        identity(self.campaign_id)
        require(type(self.workers) is tuple and len(self.workers) == 2, "two_workers")
        require_distinct_arms(self.workers[0], self.workers[1])
        require(self.root_model == self.workers[0], "fixed_incumbent_root")
        require(
            type(self.catalog) is Snapshot
            and self.catalog.freshness == "bounded_live"
            and set(dict(self.catalog.family_masks)) == {"sol", "luna"}
            and tuple(
                next((c.id for c in self.catalog.candidates if c.family == family), "")
                for family in ("sol", "luna")
            )
            == self.workers
            and len(self.catalog.candidates) == 2
            and all(c.latest is True for c in self.catalog.candidates),
            "campaign_catalog_pair",
        )
        require(self.effort in {"low", "medium", "high", "xhigh"}, "effort")
        require(self.limits.dollar_ceiling is None, "observe_only_campaign")

    def admissions(self):
        return tuple(
            CellAdmission(
                cell,
                self.root_model,
                worker,
                self.effort,
                self.effort,
                self.root_tools,
                self.worker_tools,
            )
            for cell, worker in zip(("A0", "B1"), self.workers)
        )

    @property
    def lock(self):
        return fingerprint(
            {
                "version": VERSION,
                "campaign_id": self.campaign_id,
                "sources": sources_spec(self.sources),
                "task": dict(source_binding()),
                "policy": policy_lock(self.admissions()),
                "catalog": self.catalog.to_dict(),
                "limits": asdict(self.limits),
                "bounds": asdict(self.bounds),
            }
        )


def solver_spec(campaign, cell, worker):
    return {
        "version": VERSION,
        "campaign_id": campaign.campaign_id,
        "cell_id": cell,
        "sources": sources_spec(campaign.sources),
        "root_model": campaign.root_model,
        "worker_model": worker,
        "root_effort": campaign.effort,
        "worker_effort": campaign.effort,
        "endpoint": campaign.endpoint,
        "limits": asdict(campaign.limits),
    }


def read_solver_result(raw):
    value = strict_json(raw, 400_000)
    require(
        type(value) is dict
        and set(value) == {"version", "artifact", "binding", "resolution", "cleanup"}
        and value["version"] == VERSION
        and type(value["cleanup"]) is bool,
        "solver_result",
    )
    require(type(value["artifact"]) is dict, "solver_artifact")
    files = tuple(
        (name, base64.b64decode(value["artifact"][name], validate=True))
        for name in sorted(value["artifact"])
    )
    artifact = Artifact(files, tuple(sorted(value["binding"].items())))
    require(artifact.binding == source_binding(), "solver_binding")
    return artifact, value


async def run_campaign(
    campaign,
    private_root,
    headers,
    solver_sandbox,
    assessor,
    private_cases,
    *,
    quote=None,
    upstream=None,
):
    """Serial A0 fresh incumbent, B1 changed worker. One controller, no retries.

    ``Campaign`` must use exact IDs returned by ``select_pair`` on the parent's
    selected configured provider. Public comparison/promotion is never emitted.
    """
    require(type(campaign) is Campaign, "campaign_spec")
    started = time.monotonic()
    require(
        type(solver_sandbox) is BubblewrapSandbox
        and type(assessor) is IsolatedAssessor,
        "concrete_sandbox_required",
    )
    require(solver_sandbox.spec.purpose == "solver", "solver_sandbox")
    deadline = started + campaign.bounds.wall_s
    await asyncio.wait_for(
        asyncio.to_thread(
            solver_sandbox.acceptance.require_for, solver_sandbox.spec, deadline
        ),
        max(0, deadline - time.monotonic()),
    )
    await asyncio.wait_for(
        asyncio.to_thread(
            assessor.sandbox.acceptance.require_for, assessor.sandbox.spec, deadline
        ),
        max(0, deadline - time.monotonic()),
    )
    await asyncio.wait_for(
        asyncio.to_thread(campaign.sources.validate),
        max(0, deadline - time.monotonic()),
    )
    root = Path(private_root)
    require(
        root.is_dir() and root.resolve() == root and root.stat().st_mode & 0o077 == 0,
        "private_output",
    )
    require(
        all(
            not root.is_relative_to(lock.path)
            for _, lock in campaign.sources.repositories
        ),
        "output_outside_sources",
    )
    require(
        all(
            not root.is_relative_to(Path(path)) and not Path(path).is_relative_to(root)
            for path in (*solver_sandbox.spec.readonly, *assessor.sandbox.spec.readonly)
        ),
        "output_outside_projection",
    )
    output = root / campaign.campaign_id
    output.mkdir(mode=0o700)  # single-use; no resetting a campaign on retry
    ledger = AnchorsLedger(output / "controller-ledger", campaign.lock, campaign.limits)
    authority = Authority(ledger, quote, campaign.endpoint, True, True)
    controller = Controller(
        campaign.campaign_id,
        authority,
        campaign.admissions(),
        headers,
        bounds=campaign.bounds,
        upstream=upstream,
    )
    reports = []
    controller._started = started
    # Short UDS path under explicit private scratch avoids sockaddr path truncation.
    with tempfile.TemporaryDirectory(prefix="ipc-", dir=root) as directory:
        socket_path = Path(directory) / "controller.sock"
        try:
            await controller.start(socket_path)
            for cell, worker in zip(("A0", "B1"), campaign.workers):
                row = {
                    "cell_id": cell,
                    "worker_model": worker,
                    "grade": None,
                    "completion": "unknown",
                    "cleanup": False,
                    "delivered_revision": None,
                }
                reports.append(row)
                stage = "solver_launch"
                try:
                    ledger.start_cell(cell)
                    result = await solver_sandbox.run(
                        [
                            solver_sandbox.spec.python,
                            "-B",
                            str(
                                campaign.sources.root("amplifier-bundle-routing-matrix")
                                / "evals/solver_entry.py"
                            ),
                        ],
                        canonical(
                            {
                                "spec": solver_spec(campaign, cell, worker),
                                "capability": controller.capability(cell),
                            }
                        ),
                        wall_s=min(
                            campaign.limits.whole_cell_s,
                            campaign.bounds.wall_s - (time.monotonic() - started),
                        ),
                        output_bytes=400_000,
                        socket_path=socket_path,
                    )
                    row["process_returncode"] = result.returncode
                    row["cleanup"] = result.cleanup
                    if result.returncode != 0:
                        row["solver_failure"] = read_solver_failure(result.stdout)
                    require(result.returncode == 0, "solver_execution")
                    stage = "solver_result"
                    artifact, returned = read_solver_result(result.stdout)
                    expected = [
                        {
                            "provider": "openai",
                            "model": worker,
                            "config": {"reasoning_effort": campaign.effort},
                        }
                    ]
                    require(returned["resolution"] == expected, "resolved_treatment")
                    row["cleanup"] = result.cleanup and returned["cleanup"]
                    # Private immutable snapshot is retained before assessment.
                    (output / (cell + "-artifact.json")).write_bytes(result.stdout)
                    stage = "assessment"
                    request = make_request(artifact, private_cases)
                    assessment = await asyncio.wait_for(
                        assessor.run(request),
                        min(35, campaign.bounds.wall_s - (time.monotonic() - started)),
                    )
                    row["grade"] = grade_receipt(request, assessment)
                    grade = row["grade"]
                    row["completion"] = (
                        "success"
                        if grade["success"] is True
                        else "failure"
                        if grade["success"] is False
                        else "unknown"
                    )
                    calls = [
                        e
                        for e in ledger.events()
                        if e["event"] == "reserve" and e["cell_id"] == cell
                    ]
                    require(
                        {e["phase"] for e in calls} == {"root", "worker"}
                        and not ledger.unresolved(ledger.events()),
                        "wire_incomplete",
                    )
                    require(row["cleanup"], "solver_cleanup")
                    require(
                        grade["operational_ready"] and grade["validity"] == "valid",
                        "assessment_invalid",
                    )
                    ledger.finish_cell(cell, {"instrumentation": "valid"})
                    row["instrumentation"] = "valid"
                except Exception as error:
                    ledger.abort_cell(cell, "campaign_cell_blocked")
                    row["instrumentation"] = "invalid"
                    row["reason"] = "campaign_cell_blocked"
                    row["failure_stage"] = stage
                    row["failure_code"] = failure_code(error)
                    break
                finally:
                    row["elapsed_s"] = time.monotonic() - started
        finally:
            cleanup = asyncio.create_task(controller.close())
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()
    for cell, worker in zip(("A0", "B1"), campaign.workers):
        if not any(r["cell_id"] == cell for r in reports):
            reports.append(
                {
                    "cell_id": cell,
                    "worker_model": worker,
                    "grade": None,
                    "completion": "not_run",
                    "cleanup": None,
                    "delivered_revision": None,
                }
            )
    report = {
        "version": VERSION,
        "sources": sources_spec(campaign.sources),
        "task": dict(source_binding()),
        "cells": reports,
        "calls": [
            {
                key: event[key]
                for key in (
                    "id",
                    "cell_id",
                    "session_id",
                    "parent_id",
                    "phase",
                    "role_origin",
                    "expected_model",
                    "wire_effort",
                    "reserved_tokens",
                )
            }
            for event in ledger.events()
            if event["event"] == "reserve"
        ],
        "cost": ledger.accounting(),
        "elapsed_s": time.monotonic() - started,
        "promotion_supported": False,
        "reuse_identity": "unknown",
    }
    (output / "report.json").write_bytes(canonical(report))
    return report


def refresh_report(snapshot, retained_receipts, conditions, incumbent_id):
    """Adjacent-cycle demonstration uses existing assignment-only reuse policy."""
    return plan_refresh(snapshot, retained_receipts, conditions, incumbent_id)
