"""Bounded, non-promotional routing calibration, separate from offline v1.

Generated modules are parsed here, NEVER executed here. Actual execution is
available only through the qualified, credential-free assessment container.
Optional Core/Foundation/provider imports happen only on the real-stack path.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import os
import random
import re
import selectors
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
import threading
from restricted_interval import (
    ASSESSOR_DRIVER as RESTRICTED_DRIVER,
    GRAMMAR_SHA256,
    GRAMMAR_VERSION,
    ArtifactUngradable,
    validate_interval_module,
)

from live_transport import (
    VERSION,
    ROOT_MODEL,
    TOOL_NAME,
    TOOL_DESCRIPTION,
    TOOL_SCHEMA,
    AdmissionAuthority,
    AdmittedTransport,
    Ledger,
    ModelRate,
    PriceQuote,
    SessionPolicy,
    SmokeBlocked,
    SmokeLimits,
    canonical,
    fingerprint,
    money,
    require,
    strict_json,
    httpx,
)

ROOT_PROMPT = (
    "Call delegate_coding exactly once with {}. This runs a fixed coding task. "
    "After its receipt, acknowledge it briefly. Do not write, revise or supply code."
)
TASK_FILE = Path(__file__).parent / "tasks" / "interval-union-v1" / "task.json"
SOURCE_LABELS = frozenset(
    {
        "core_native",
        "core_python",
        "foundation",
        "loop",
        "context",
        "provider",
        "shim",
        "routing",
        "sdk",
        "httpx",
        "task",
        "protocol",
        "assessor",
    }
)
TREE_LABELS = SOURCE_LABELS - {"core_native", "task"}
IMPLEMENTATION_BLOCKERS = ()
MODULE_IDS = {
    "loop": "loop-streaming",
    "context": "context-simple",
    "shim": "provider-openai",
    "routing": "hooks-routing",
}


@dataclass(frozen=True)
class SourceLock:
    label: str
    path: Path
    sha256: str

    def validate(self):
        require(re.fullmatch(r"[0-9a-f]{64}", self.sha256) is not None, "source_digest")
        require(
            self.path.is_dir() if self.label in TREE_LABELS else self.path.is_file(),
            "source_inventory_shape",
        )
        require(source_digest(self.path) == self.sha256, "source_changed")


def source_digest(path: Path) -> str:
    """Bounded explicit executable inventory; never an ambient repository census."""
    require(path.resolve() == path and not path.is_symlink(), "source_symlink")
    if path.is_file():
        require(path.stat().st_size <= 1024 * 1024 * 1024, "source_inventory_size")
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    require(path.is_dir(), "source_directory")
    ignored = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".cache"}
    inventory = []
    total = 0
    for file in sorted(path.rglob("*")):
        rel = file.relative_to(path)
        if any(part in ignored for part in rel.parts):
            continue
        require(not file.is_symlink(), "source_symlink")
        if not file.is_file() or file.suffix in {".pyc", ".pyo"}:
            continue
        total += file.stat().st_size
        require(
            total <= 1024 * 1024 * 1024 and len(inventory) < 8192,
            "source_inventory_size",
        )
        with file.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory.append(
            {
                "path": rel.as_posix(),
                "sha256": digest,
            }
        )
    require(bool(inventory), "source_empty_inventory")
    return fingerprint(inventory)


@dataclass(frozen=True)
class AssessmentSpec:
    image: str
    qualification_ref: str
    image_qualified: bool
    seed: int
    timeout_s: int = 15
    output_max: int = 65536
    isolation_path: Path | None = None
    isolation_sha256: str | None = None
    validator_sha256: str | None = None
    driver_sha256: str | None = None
    grammar_version: str = GRAMMAR_VERSION

    def __post_init__(self):
        require(
            re.fullmatch(r"[a-z0-9./:_-]+@sha256:[0-9a-f]{64}", self.image) is not None,
            "assessor_image_digest",
        )
        require(type(self.seed) is int, "assessor_seed")
        require(type(self.image_qualified) is bool, "assessor_qualification_type")
        require(
            type(self.timeout_s) is int
            and type(self.output_max) is int
            and self.timeout_s == 15
            and self.output_max == 65536,
            "assessor_limits",
        )

    def validate_locks(self):
        require(
            self.grammar_version == GRAMMAR_VERSION
            and self.validator_sha256 == GRAMMAR_SHA256
            and self.driver_sha256
            == hashlib.sha256(RESTRICTED_DRIVER.encode()).hexdigest(),
            "assessor_source_locks",
        )
        require(
            self.isolation_path is not None and self.isolation_sha256 is not None,
            "assessor_isolation_receipt",
        )
        raw = self.isolation_path.read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == self.isolation_sha256,
            "assessor_isolation_changed",
        )
        proof = strict_json(raw, 16384)
        require(
            proof.get("actual_python_image") == self.image
            and proof.get("isolated_controls_passed") is True
            and proof.get("absence_verified") is True
            and proof.get("execution_exit") == 0,
            "assessor_isolation_unqualified",
        )
        require(
            proof.get("runtime_checks")
            == {
                "uid": 65534,
                "capabilities": "none",
                "no_new_privileges": True,
                "provider_credentials_present": False,
                "docker_socket_present": False,
                "personal_mount_present": False,
                "root_fs_readonly": True,
                "tmp_writable": True,
                "external_network_denied": True,
            },
            "assessor_isolation_controls",
        )


@dataclass(frozen=True)
class CellSpec:
    cell_id: str
    worker_model: str

    def __post_init__(self):
        require(self.cell_id in {"A0", "A1", "B1"}, "cell_identity")
        require(
            self.worker_model
            == ("gpt-6-astra" if self.cell_id == "B1" else ROOT_MODEL),
            "cell_assignment",
        )


@dataclass(frozen=True)
class AssessmentAuthority:
    staging_root: Path
    registrar_script: Path
    registrar_sha256: str
    claim_script: Path
    claim_sha256: str
    batch_dir: Path
    owner: str

    def validate(self):
        require(
            self.staging_root.is_dir()
            and self.staging_root.resolve() == self.staging_root
            and self.staging_root.stat().st_mode & 0o077 == 0,
            "assessment_staging",
        )
        for path, digest in (
            (self.registrar_script, self.registrar_sha256),
            (self.claim_script, self.claim_sha256),
        ):
            require(
                path.is_file()
                and path.resolve() == path
                and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                "assessment_registrar_source",
            )
        require(self.batch_dir.is_dir(), "assessment_batch")
        require(
            isinstance(self.owner, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", self.owner) is not None,
            "assessment_owner",
        )

    def register(self, name):
        self.validate()
        require(
            re.fullmatch(r"routing-assessor-[a-f0-9]{32}", name) is not None,
            "assessment_resource_name",
        )
        rc, _ = bounded_process(
            [
                str(self.registrar_script),
                str(self.batch_dir),
                "add",
                "docker",
                name,
                "docker",
                "rm",
                "--force",
                name,
            ],
            b"",
            10,
            4096,
        )
        require(rc == 0, "assessment_registrar_refused")
        rc, _ = bounded_process(
            [
                str(self.claim_script),
                str(self.batch_dir),
                self.owner,
                "claim",
                name,
            ],
            b"",
            10,
            4096,
        )
        require(rc == 0, "assessment_claim_refused")


@dataclass(frozen=True)
class CampaignSpec:
    campaign_id: str
    sources: tuple[SourceLock, ...]
    module_sources: dict[str, Path]
    quote: PriceQuote
    assessment: AssessmentSpec
    private_output_root: Path
    endpoint_qualified: bool
    binding_qualified: bool
    full_stack_qualification: str | None = None
    assessor_qualification: str | None = None
    pair_order: tuple[str, str] = ("A1", "B1")
    limits: SmokeLimits = SmokeLimits()
    version: str = VERSION
    qualification_path: Path | None = None
    qualification_sha256: str | None = None
    assessment_authority: AssessmentAuthority | None = None

    def __post_init__(self):
        require(self.version == VERSION, "contract_version")
        require(
            type(self.endpoint_qualified) is bool
            and type(self.binding_qualified) is bool,
            "authority_qualification_type",
        )
        require(
            isinstance(self.campaign_id, str)
            and re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", self.campaign_id) is not None,
            "campaign_identity",
        )
        require(
            len(self.sources) == len(SOURCE_LABELS)
            and {s.label for s in self.sources} == SOURCE_LABELS,
            "source_inventory",
        )
        require(set(self.module_sources) == set(MODULE_IDS), "module_inventory")
        require(self.pair_order in {("A1", "B1"), ("B1", "A1")}, "pair_order")
        object.__setattr__(
            self, "module_sources", MappingProxyType(dict(self.module_sources))
        )

    @property
    def lock(self):
        return fingerprint(
            {
                "version": self.version,
                "campaign_id": self.campaign_id,
                "sources": {s.label: s.sha256 for s in self.sources},
                "quote_lock": self.quote.lock,
                "assessment_image": self.assessment.image,
                "grammar_version": GRAMMAR_VERSION,
                "grammar_sha256": GRAMMAR_SHA256,
                "driver_sha256": hashlib.sha256(ASSESSOR_DRIVER.encode()).hexdigest(),
                "seed": self.assessment.seed,
                "pair_order": self.pair_order,
                "full_stack_qualification": self.full_stack_qualification,
                "assessor_qualification": self.assessor_qualification,
                "limits": {k: str(v) for k, v in vars(self.limits).items()},
                "count_policy": "blocked_before_wire",
                "input_bound_policy": "qualified_native_total_context_upper_bound",
                "private_output_root": str(self.private_output_root),
                "assessment_authority": {
                    k: str(v) for k, v in vars(self.assessment_authority).items()
                }
                if self.assessment_authority
                else None,
            }
        )

    def qualification(self):
        require(
            self.qualification_path is not None
            and self.qualification_sha256 is not None,
            "qualification_receipt_missing",
        )
        raw = self.qualification_path.read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == self.qualification_sha256,
            "qualification_receipt_changed",
        )
        proof = strict_json(raw, 65536)
        require(
            isinstance(proof, dict)
            and set(proof)
            == {
                "version",
                "campaign_lock",
                "full_stack",
                "assessor",
                "controller",
            }
            and proof["version"] == VERSION
            and proof["campaign_lock"] == self.lock,
            "qualification_binding",
        )
        stack = proof["full_stack"]
        require(
            isinstance(stack, dict)
            and stack.get("models")
            == {
                "A0": [ROOT_MODEL, ROOT_MODEL, ROOT_MODEL],
                "B1": [ROOT_MODEL, "gpt-6-astra", ROOT_MODEL],
            }
            and stack.get("effort") == "high"
            and stack.get("service_tier") == "default"
            and stack.get("transmitted_counts") == 0
            and type(stack.get("transmitted_counts")) is int
            and stack.get("child_tools") == 0
            and type(stack.get("child_tools")) is int
            and stack.get("cleanup") == "confirmed"
            and stack.get("factory_negative_cases")
            == [
                "missing",
                "replaced",
                "copied",
                "send_replaced",
                "dormant_after_cleanup",
            ]
            and stack.get("sdk_version") == "3.24.0",
            "full_stack_qualification_invalid",
        )
        assess = proof["assessor"]
        require(
            isinstance(assess, dict)
            and assess.get("image") == self.assessment.image
            and assess.get("grammar_sha256") == GRAMMAR_SHA256
            and assess.get("driver_sha256") == self.assessment.driver_sha256
            and assess.get("case_count") == len(assessment_cases(self.assessment.seed))
            and assess.get("correct_awards")
            == {"union": 1, "touching_empty": 1, "invalid": 1, "immutability": 1}
            and assess.get("bad_controls")
            == ["nonmerge", "bool", "mutation", "constant"]
            and assess.get("hang") == "invalid"
            and assess.get("spoof_controls") == "rejected_before_execution"
            and assess.get("cleanup") == "confirmed",
            "assessor_qualification_invalid",
        )
        controller = proof["controller"]
        require(
            isinstance(controller, dict)
            and controller.get("output_root") == str(self.private_output_root)
            and controller.get("isolated") is True
            and controller.get("resource_cost_policy") == "verified_no_charge"
            and controller.get("once_only") is True
            and controller.get("deadline_cleanup") == "qualified",
            "controller_qualification_invalid",
        )
        return proof


def baseline_matrix() -> dict:
    return {
        "name": "interval-smoke",
        "description": "Controlled coding smoke only.",
        "updated": "2026-10-03",
        "roles": {
            role: {
                "description": f"Controlled {role} role.",
                "candidates": [
                    {
                        "provider": "openai",
                        "model": ROOT_MODEL,
                        "config": {"reasoning_effort": "high"},
                    }
                ],
            }
            for role in ("general", "fast", "coding")
        },
    }


def arm_matrix(cell: CellSpec) -> dict:
    matrix = copy.deepcopy(baseline_matrix())
    matrix["roles"]["coding"]["candidates"][0]["model"] = cell.worker_model
    return matrix


def extract_module(output: str) -> bytes:
    require(isinstance(output, str), "artifact_text")
    try:
        raw = output.encode("utf-8")
    except UnicodeError:
        raise SmokeBlocked("artifact_encoding") from None
    parsed = strict_json(raw, 16384)
    require(
        isinstance(parsed, dict)
        and set(parsed) == {"module"}
        and isinstance(parsed["module"], str),
        "artifact_schema",
    )
    module = parsed["module"]
    try:
        tree = ast.parse(module)
    except (SyntaxError, ValueError, RecursionError):
        raise SmokeBlocked("artifact_syntax") from None
    require(
        any(isinstance(n, ast.FunctionDef) and n.name == "coalesce" for n in tree.body),
        "artifact_function",
    )
    return module.encode("utf-8")


def write_once(path: Path, raw: bytes) -> None:
    require(not path.is_symlink(), "immutable_path")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_output(spec: CampaignSpec, output_dir: Path) -> Path:
    root = spec.private_output_root
    require(
        root.is_absolute() and root.is_dir() and root.resolve() == root,
        "private_output_root",
    )
    require(root.stat().st_mode & 0o077 == 0, "private_output_permissions")
    output_dir = Path(output_dir)
    require(
        output_dir.is_absolute()
        and output_dir.resolve() == output_dir
        and output_dir.is_relative_to(root),
        "private_output_path",
    )
    require(output_dir == root / spec.campaign_id, "campaign_output_changed")
    source_repo = Path(__file__).resolve().parents[1]
    require(not output_dir.is_relative_to(source_repo), "output_inside_source")
    require(
        all(not root.is_relative_to(path) for path in spec.module_sources.values()),
        "output_inside_module_source",
    )
    require(
        all(
            not root.is_relative_to(s.path if s.path.is_dir() else s.path.parent)
            for s in spec.sources
        ),
        "output_inside_locked_source",
    )
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(output_dir.stat().st_mode & 0o077 == 0, "private_output_permissions")
    return output_dir


def preflight(spec: CampaignSpec) -> dict:
    """Inert checks: no provider, SDK, credential, subprocess or network calls."""
    blockers = list(IMPLEMENTATION_BLOCKERS)
    for source in spec.sources:
        try:
            source.validate()
        except (SmokeBlocked, OSError):
            blockers.append(f"source_{source.label}")
    try:
        spec.quote.validate(datetime.now(timezone.utc))
    except SmokeBlocked:
        blockers.append("price_quote")
    if not spec.endpoint_qualified:
        blockers.append("endpoint_qualification")
    if not spec.binding_qualified:
        blockers.append("binding_qualification")
    try:
        spec.assessment.validate_locks()
    except (SmokeBlocked, OSError, ValueError, TypeError, AttributeError):
        blockers.append("assessor_source_image_qualification")
    try:
        spec.qualification()
    except (SmokeBlocked, OSError, ValueError, TypeError, AttributeError):
        blockers.append("source_bound_execution_qualification")
    try:
        require(spec.assessment_authority is not None, "assessment_authority")
        spec.assessment_authority.validate()
    except (SmokeBlocked, OSError, ValueError, TypeError, AttributeError):
        blockers.append("assessment_resource_authority")
    for label, path in spec.module_sources.items():
        if not path.is_absolute() or not (path / "pyproject.toml").is_file():
            blockers.append(f"module_{label}")
    return {
        "version": VERSION,
        "campaign_lock": spec.lock,
        "ready": not blockers,
        "blockers": blockers,
        "scheduled": ["A0", *spec.pair_order],
        "model_calls": 0,
        "scope": "descriptive-smoke-not-ranking-or-promotion",
    }


def task_prompt() -> str:
    task = strict_json(TASK_FILE.read_bytes(), 16384)
    require(task["version"] == "interval-union-v1", "task_version")
    return task["instructions"]


def assessment_cases(seed: int) -> list[dict]:
    """Frozen independent controller-side cases; no expected keys reach the driver."""
    rng = random.Random(seed)
    cases = []
    groups = {
        "union": [
            [[-5, 2], [-3, 0], [7, 9]],
            [[1, 4], [1, 4], [2, 3]],
            [[-8, -6], [-7, 3], [8, 10]],
        ],
        "touching_empty": [[], [[-2, 1], [1, 5]], [[8, 9], [3, 8]]],
        "immutability": [[[3, 8], [-2, 5]], [[7, 9], [1, 3], [2, 6]]],
    }
    for _ in range(24):
        ranges = []
        for _ in range(rng.randint(0, 8)):
            a = rng.randint(-12, 10)
            ranges.append([a, rng.randint(a + 1, 13)])
        groups["union"].append(ranges)
    for group, inputs in groups.items():
        for value in inputs:
            cases.append(
                {
                    "id": str(len(cases)),
                    "group": group,
                    "input": value,
                    "invalid": False,
                }
            )
    invalid = [
        None,
        {},
        3,
        "ranges",
        [1],
        [[1]],
        [[1, 2, 3]],
        [[True, 2]],
        [[0, False]],
        [[1.0, 2]],
        [["1", 2]],
        [[2, 2]],
        [[4, -2]],
        [[0, 2], [4, 3]],
    ]
    for value in invalid:
        cases.append(
            {"id": str(len(cases)), "group": "invalid", "input": value, "invalid": True}
        )
    # Include tuple pairs as a distinct driver conversion, outer tuple is invalid.
    cases.append(
        {
            "id": str(len(cases)),
            "group": "union",
            "input": [[-3, 2], [2, 4]],
            "invalid": False,
            "pairs_tuple": True,
        }
    )
    cases.append(
        {
            "id": str(len(cases)),
            "group": "invalid",
            "input": [[1, 2]],
            "invalid": True,
            "outer_tuple": True,
        }
    )
    return cases


def grid_union(ranges: list) -> list[list[int]]:
    # Integer occupancy, independent of the usual sorting/merging implementation.
    occupied = {x for a, b in ranges for x in range(a, b)}
    result = []
    for x in sorted(occupied):
        if result and result[-1][1] == x:
            result[-1][1] = x + 1
        else:
            result.append([x, x + 1])
    return result


# This driver is trusted source, mounted read-only. Expected values are computed
# above in the controller and are deliberately absent from the container input.
ASSESSOR_DRIVER = RESTRICTED_DRIVER


@dataclass(frozen=True)
class GradeReceipt:
    validity: str
    awards: tuple[tuple[str, int], ...]
    comparisons: tuple[dict, ...]
    critical: str
    cleanup: str
    blocker: str | None

    def as_dict(self):
        return {
            "validity": self.validity,
            "awards": dict(self.awards),
            "comparisons": list(self.comparisons),
            "critical": self.critical,
            "cleanup": self.cleanup,
            "blocker": self.blocker,
        }


def compare_assessment(raw: bytes, cases: list[dict], cleanup: bool) -> GradeReceipt:
    try:
        records = strict_json(raw, 65536)
        require(
            bool(cases) and isinstance(records, list) and len(records) == len(cases),
            "assessor_incomplete",
        )
        require(
            [r["id"] for r in records] == [c["id"] for c in cases], "assessor_case_ids"
        )
        awards = {
            key: 1 for key in ("union", "touching_empty", "invalid", "immutability")
        }
        comparisons = []
        mutation = False
        for case, record in zip(cases, records, strict=True):
            require(
                isinstance(record, dict)
                and set(record) == {"id", "status", "shape", "answer", "mutated"}
                and record["status"] in {"return", "value_error", "exception"}
                and type(record["shape"]) is bool
                and type(record["mutated"]) is bool,
                "assessor_record",
            )
            mutation |= record["mutated"]
            if case["invalid"]:
                correct = record["status"] == "value_error"
            else:
                answer = record["answer"]
                # bool == 1 must not forge independently checked endpoint equality.
                exact_shape = isinstance(answer, list) and all(
                    isinstance(p, list)
                    and len(p) == 2
                    and all(type(x) is int for x in p)
                    for p in answer
                )
                correct = (
                    record["status"] == "return"
                    and record["shape"]
                    and exact_shape
                    and answer == grid_union(case["input"])
                )
            awards[case["group"]] &= int(correct)
            awards["immutability"] &= int(not record["mutated"])
            comparisons.append(
                {
                    "case_id": case["id"],
                    "group": case["group"],
                    "correct": bool(correct),
                    "mutated": record["mutated"],
                }
            )
        require({c["group"] for c in cases} == set(awards), "assessor_empty_group")
        return GradeReceipt(
            "valid",
            tuple(awards.items()),
            tuple(comparisons),
            "fail" if mutation else "pass",
            "confirmed" if cleanup else "unconfirmed",
            None,
        )
    except (SmokeBlocked, KeyError, TypeError, ValueError):
        return GradeReceipt(
            "invalid",
            (),
            (),
            "unknown",
            "confirmed" if cleanup else "unconfirmed",
            "assessor_protocol",
        )


def bounded_process(
    argv: list[str],
    input_: bytes,
    timeout_s: int,
    output_max: int,
    stderr_sink: list[bytes] | None = None,
) -> tuple[int, bytes]:
    """No shell; bound combined stdout/stderr and elapsed, including malicious output."""
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.defpath},
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    output, size = [], 0
    deadline = time.monotonic() + timeout_s
    try:
        process.stdin.write(input_)
        process.stdin.close()
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            require(time.monotonic() < deadline, "assessor_timeout")
            for key, _ in selector.select(
                min(0.1, max(0, deadline - time.monotonic()))
            ):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    size += len(chunk)
                    require(size <= output_max, "assessor_output_bound")
                    if key.fileobj is process.stdout:
                        output.append(chunk)
                    elif stderr_sink is not None:
                        stderr_sink.append(chunk)
        return process.wait(timeout=max(0.1, deadline - time.monotonic())), b"".join(
            output
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def assessor_create_args(
    name: str,
    artifact: Path,
    driver: Path,
    spec: AssessmentSpec,
    admission=None,
) -> list[str]:
    spec.validate_locks()
    return [
        "docker",
        "create",
        "--name",
        name,
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "32",
        "--memory",
        "128m",
        "--cpus",
        "1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=8m",
        "--interactive",
        "--mount",
        f"type=bind,src={artifact},dst=/input/solution.py,readonly",
        "--mount",
        f"type=bind,src={driver},dst=/input/driver.py,readonly",
        "--mount",
        f"type=bind,src={driver.parent / 'restricted_interval.py'},dst=/input/restricted_interval.py,readonly",
        spec.image,
        "python",
        "-I",
        "-B",
        "/input/driver.py",
        *(
            [admission.source_sha256, admission.normalized_sha256, GRAMMAR_SHA256]
            if admission
            else []
        ),
    ]


_ASSESSOR_LOCK = threading.Lock()


def grade_artifact(
    artifact: Path,
    spec: AssessmentSpec,
    *,
    staging_root: Path | None = None,
    registrar=None,
) -> GradeReceipt:
    """Restricted artifacts execute ONLY in a separately qualified Docker sandbox."""
    require(artifact.is_file() and artifact.resolve() == artifact, "assessor_artifact")
    require(artifact.stat().st_size <= 16384, "assessor_artifact_bound")
    raw = artifact.read_bytes()
    try:
        _, admission = validate_interval_module(raw.decode("utf-8"))
    except (ArtifactUngradable, UnicodeError):
        return GradeReceipt(
            "invalid", (), (), "unknown", "confirmed", "artifact_restricted_grammar"
        )
    spec.validate_locks()
    require(
        staging_root is not None
        and staging_root.is_dir()
        and staging_root.resolve() == staging_root
        and callable(registrar),
        "assessor_resource_authority",
    )
    require(_ASSESSOR_LOCK.acquire(blocking=False), "assessor_concurrency")
    name = "routing-assessor-" + uuid.uuid4().hex
    staging = staging_root / name
    journal = staging / "resources.jsonl"

    def event(disposition, **fields):
        fd = os.open(
            journal, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "ab") as stream:
            stream.write(
                canonical({"name": name, "event": disposition, **fields}) + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    cleanup, created, blocker, output = False, False, None, None
    cases = assessment_cases(spec.seed)
    try:
        staging.mkdir(mode=0o700)
        solution = staging / "solution.py"
        driver = staging / "driver.py"
        validator = staging / "restricted_interval.py"
        write_once(solution, raw)
        write_once(driver, ASSESSOR_DRIVER.encode())
        write_once(
            validator, (Path(__file__).parent / "restricted_interval.py").read_bytes()
        )
        for path in (solution, driver, validator):
            path.chmod(0o444)
        event(
            "creation_intent",
            source_sha256=admission.source_sha256,
            normalized_sha256=admission.normalized_sha256,
            validator_sha256=GRAMMAR_SHA256,
            driver_sha256=spec.driver_sha256,
            image=spec.image,
            case_count=len(cases),
        )
        registrar(name)
        event("registered")
        created = True  # unknown create outcomes still require cleanup by exact name
        rc, container_id = bounded_process(
            assessor_create_args(name, solution, driver, spec, admission),
            b"",
            10,
            4096,
        )
        event(
            "create_return",
            rc=rc,
            container_id=container_id.decode("ascii", errors="replace").strip()[:128],
        )
        require(rc == 0, "assessor_create")
        stderr_chunks = []
        rc, output = bounded_process(
            ["docker", "start", "--attach", "--interactive", name],
            canonical(cases),
            spec.timeout_s,
            spec.output_max,
            stderr_sink=stderr_chunks,
        )
        stderr_code = b"".join(stderr_chunks).decode("ascii", errors="replace").strip()
        event(
            "execute_return",
            rc=rc,
            diagnostic=stderr_code
            if re.fullmatch(r"assessor_invalid_[a-zA-Z_]+", stderr_code)
            else "none_or_unrecognized",
        )
        require(rc == 0, "assessor_execution")
    except (SmokeBlocked, OSError, subprocess.SubprocessError) as exc:
        blocker = str(exc) if isinstance(exc, SmokeBlocked) else "assessor_process"
        if staging.is_dir():
            event("execution_fault", reason=blocker)
    finally:
        try:
            if created:
                try:
                    rc, _ = bounded_process(
                        ["docker", "rm", "--force", name], b"", 10, 4096
                    )
                    probe_rc, names = bounded_process(
                        [
                            "docker",
                            "ps",
                            "--all",
                            "--quiet",
                            "--filter",
                            f"name=^/{name}$",
                        ],
                        b"",
                        10,
                        4096,
                    )
                    cleanup = rc == 0 and probe_rc == 0 and not names.strip()
                except (SmokeBlocked, OSError, subprocess.SubprocessError):
                    cleanup = False
                event("cleanup", confirmed=cleanup)
            else:
                cleanup = True
        finally:
            _ASSESSOR_LOCK.release()
    if blocker:
        grade = GradeReceipt(
            "invalid",
            (),
            (),
            "unknown",
            "confirmed" if cleanup else "unconfirmed",
            blocker,
        )
    else:
        grade = compare_assessment(output, cases, cleanup)
    if staging.is_dir():
        write_once(
            staging / "grade.json",
            canonical(
                {
                    **grade.as_dict(),
                    "source_sha256": admission.source_sha256,
                    "grammar_version": GRAMMAR_VERSION,
                    "validator_sha256": GRAMMAR_SHA256,
                    "driver_sha256": spec.driver_sha256,
                    "image": spec.image,
                    "case_count": len(cases),
                    "resource_name": name,
                }
            ),
        )
    return grade


def minimal_bundle(spec: CampaignSpec, arm_dir: Path, worker: bool):
    from amplifier_foundation import Bundle

    config = {
        "reasoning_effort": "high",
        "max_output_tokens": 4096,
        "max_retries": 0,
        "auto_continue": False,
        "use_streaming": False,
        "timeout": 60,
        "close_timeout": 10,
        "reasoning_replay_scope": "none",
    }
    if not worker:
        config["default_model"] = ROOT_MODEL
    config["extra_request_params"] = {"service_tier": "default", "include": []}
    return Bundle(
        name="interval-smoke-worker" if worker else "interval-smoke-root",
        session={
            "orchestrator": {
                "module": "loop-streaming",
                "source": str(spec.module_sources["loop"]),
                "config": {"max_iterations": 2},
            },
            "context": {
                "module": "context-simple",
                "source": str(spec.module_sources["context"]),
            },
        },
        providers=[
            {
                "module": "provider-openai",
                "source": str(spec.module_sources["shim"]),
                "config": config,
            }
        ],
        hooks=[
            {
                "module": "hooks-routing",
                "source": str(spec.module_sources["routing"]),
                "config": {
                    "default_matrix": "interval-smoke",
                    "custom_routing_dirs": [str(arm_dir)],
                },
            }
        ],
        tools=[],
        agents={},
        spawn={},
        base_path=arm_dir,
    )


class DelegateCodingTool:
    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    input_schema = TOOL_SCHEMA

    def __init__(
        self,
        root,
        prepared,
        child_bundle,
        before_initialize,
        spec: CellSpec,
        output_dir: Path,
        verify_root,
    ):
        self.root = root
        self.prepared = prepared
        self.child_bundle = child_bundle
        self.before_initialize = before_initialize
        self.spec = spec
        self.output_dir = output_dir
        self.verify_root = verify_root
        self.called = False
        self.completed = False
        self.resolution = None

    async def execute(self, input: dict):
        from amplifier_core.models import ToolResult

        require(type(input) is dict and input == {}, "delegate_arguments")
        require(not self.called, "delegate_once_only")
        self.called = True
        self.verify_root()
        resolver = self.root.coordinator.get_capability("model_role_resolver")
        resolved = await resolver.resolve("coding")
        require(
            len(resolved) == 1
            and resolved[0].provider == "openai"
            and resolved[0].model == self.spec.worker_model
            and resolved[0].config == {"reasoning_effort": "high"},
            "resolver_arm",
        )
        self.resolution = {
            "provider": resolved[0].provider,
            "model": resolved[0].model,
            "config": dict(resolved[0].config),
            "role_origin": "coding",
        }
        write_once(self.output_dir / "resolution.json", canonical(self.resolution))
        result = await self.prepared.spawn(
            self.child_bundle,
            task_prompt(),
            compose=False,
            parent_session=self.root,
            session_id=uuid.uuid4().hex,
            provider_preferences=resolved,
            session_cwd=self.output_dir,
            before_initialize=self.before_initialize,
        )
        output = result.get("output")
        require(isinstance(output, str), "spawn_output")
        require(len(output.encode("utf-8")) <= 16384, "artifact_size")
        write_once(self.output_dir / "worker-output.json", output.encode("utf-8"))
        write_once(self.output_dir / "solution.py", extract_module(output))
        self.completed = True
        return ToolResult(
            success=True,
            output={"receipt_id": uuid.uuid4().hex, "status": "artifact-retained"},
        )


class RealStack:
    """Own injected clients even when Foundation initialization fails."""

    def __init__(
        self,
        campaign: CampaignSpec,
        cell: CellSpec,
        authority: AdmissionAuthority,
        arm_dir: Path,
        credential_value: str,
        receiver_factory=None,
    ):
        self.campaign, self.cell, self.authority = campaign, cell, authority
        self.arm_dir = arm_dir
        self.credential_value = credential_value
        self.receiver_factory = receiver_factory
        self.clients, self.sessions, self.logical = [], [], {}
        self.providers = {}
        self.factories = {}
        self.closed = False

    def verify_session(self, session):
        for source in self.campaign.sources:
            source.validate()
        coordinator = session.coordinator
        require(
            self.factories.get(session.session_id) is not None
            and coordinator.get_capability("smoke.provider_factory")
            is self.factories[session.session_id],
            "factory_authority_changed",
        )
        provider = self.providers.get(session.session_id)
        require(
            provider is not None
            and coordinator.get("providers") == {"openai": provider},
            "provider_registry",
        )
        resolver = coordinator.get_capability("model_role_resolver")
        require(
            resolver is not None
            and resolver.name == "interval-smoke"
            and resolver.matrix_source == "user"
            and resolver.matrix_path == str(self.arm_dir / "interval-smoke.yaml")
            and not resolver.shadowed_paths,
            "routing_provenance",
        )
        import yaml

        parsed = yaml.safe_load((self.arm_dir / "interval-smoke.yaml").read_text())
        require(
            parsed == arm_matrix(self.cell) and "preset" not in parsed, "matrix_changed"
        )
        tools = coordinator.get("tools")
        if session.parent_id is None:
            require(set(tools) == {TOOL_NAME}, "root_tool_registry")
        else:
            require(
                tools == {} and session.parent_id == self.sessions[0].session_id,
                "child_tool_lineage",
            )
        require(
            coordinator.get_capability("session.spawn") is None,
            "ambient_spawn_capability",
        )

    async def before_initialize(self, session):
        from amplifier_core.models import HookResult
        from amplifier_module_provider_openai import OpenAIProvider
        from openai import AsyncOpenAI

        self.sessions.append(session)
        policy = SessionPolicy(
            self.cell.cell_id,
            session.session_id,
            session.parent_id,
            "coding" if session.parent_id else "controller",
            "worker" if session.parent_id else "root",
            self.cell.worker_model if session.parent_id else ROOT_MODEL,
        )

        async def fatal(coordinator, config, error):
            self.authority.ledger.abort_cell(self.cell.cell_id, "provider_mount_failed")
            raise SmokeBlocked("provider_mount_failed") from None

        async def before_load(coordinator, config):
            require(
                coordinator is session.coordinator
                and coordinator.get_capability("smoke.provider_factory")
                is self.factories.get(session.session_id)
                and self.factories.get(session.session_id) is not None,
                "factory_authority_missing",
            )

        async def request_id(event, data):
            require(isinstance(data.get("request_id"), str), "core_request_id_missing")
            self.logical[session.session_id] = data["request_id"]
            return HookResult()

        session.coordinator.register_capability("provider.load_failure", fatal)
        session.coordinator.register_capability("provider.before_load", before_load)
        session.coordinator.hooks.register(
            "llm:request", request_id, name="smoke-logical-id", priority=100
        )

        def factory(coordinator, config):
            require(coordinator is session.coordinator, "factory_coordinator")
            require(config["default_model"] == policy.expected_model, "factory_model")
            transport = AdmittedTransport(
                self.authority,
                policy,
                lambda: self.verify_session(session),
                lambda: self.logical.get(session.session_id),
                receiver=(
                    self.receiver_factory(policy) if self.receiver_factory else None
                ),
            )
            http = httpx.AsyncClient(
                transport=transport,
                follow_redirects=False,
                trust_env=False,
                timeout=60,
            )
            sdk = AsyncOpenAI(
                api_key=self.credential_value,
                base_url=self.authority.endpoint,
                max_retries=0,
                http_client=http,
                timeout=60,
            )
            self.clients.append((sdk, http, transport))
            provider = OpenAIProvider(
                self.credential_value,
                config=config,
                coordinator=coordinator,
                client=sdk,
            )
            self.providers[session.session_id] = provider
            return provider

        self.factories[session.session_id] = factory
        session.coordinator.register_capability("smoke.provider_factory", factory)

    async def run(self, output_dir: Path):
        import amplifier_module_eval_openai
        import amplifier_module_provider_openai

        # Assert distinct source-selected shim and the actual underlying implementation.
        for label, module in (
            ("shim", amplifier_module_eval_openai),
            ("provider", amplifier_module_provider_openai),
        ):
            locked = next(s for s in self.campaign.sources if s.label == label)
            require(
                Path(module.__file__).resolve().is_relative_to(locked.path),
                f"mounted_{label}_source",
            )
        bundle = minimal_bundle(self.campaign, self.arm_dir, worker=False)
        prepared = await bundle.prepare(
            install_deps=False,
            strict=True,
            cache_dir=output_dir / "cache",
        )
        root = await prepared.create_session(
            session_id=uuid.uuid4().hex,
            session_cwd=output_dir,
            before_initialize=self.before_initialize,
        )
        tool = DelegateCodingTool(
            root,
            prepared,
            minimal_bundle(self.campaign, self.arm_dir, worker=True),
            self.before_initialize,
            self.cell,
            output_dir,
            lambda: self.verify_session(root),
        )
        await root.coordinator.mount("tools", tool, name=TOOL_NAME)
        self.verify_session(root)
        await root.execute(ROOT_PROMPT)
        require(
            tool.called and tool.completed and len(self.sessions) == 2,
            "delegation_protocol",
        )
        return tool.resolution

    async def close(self, deadline=None):
        okay = True

        def budget(maximum):
            if deadline is None:
                return maximum
            require(time.monotonic() < deadline, "cleanup_deadline")
            return min(maximum, deadline - time.monotonic())

        for session in reversed(self.sessions):
            try:
                await asyncio.wait_for(session.cleanup(), budget(15))
            except BaseException:
                okay = False
        for sdk, http, transport in self.clients:
            try:
                await asyncio.wait_for(sdk.close(), budget(10))
                await asyncio.wait_for(http.aclose(), budget(10))
                if not transport.closed:
                    await asyncio.wait_for(transport.aclose(), budget(10))
                okay &= sdk.is_closed() and http.is_closed and transport.closed
            except BaseException:
                okay = False
        self.credential_value = None
        self.closed = bool(okay)
        return self.closed


@dataclass(frozen=True)
class SmokeReceipt:
    cell_id: str
    instrumentation: str
    setup: str
    protocol: str
    treatment: str
    subject_result: str
    grade: GradeReceipt | None
    subject_usd: str | None
    liability_usd: str
    elapsed_s: float
    cleanup: str
    blocker: str | None

    def as_dict(self):
        result = dict(vars(self))
        result["grade"] = self.grade.as_dict() if self.grade else None
        result["evaluation_model_usd"] = "0"
        result["application_model_usd"] = "0"
        result["resource_usd"] = None
        return result


def reconcile_cell(ledger: Ledger, cell: CellSpec) -> dict:
    events = ledger.events()
    reservations = [
        e for e in events if e["event"] == "reserve" and e["cell_id"] == cell.cell_id
    ]
    generations = [e for e in reservations if e["kind"] == "generation"]
    responses = {e["wire_id"]: e for e in events if e["event"] == "response"}
    settlements = {e["wire_id"]: e for e in events if e["event"] == "settle"}
    roots = [e for e in generations if e["phase"] == "root"]
    children = [e for e in generations if e["phase"] == "worker"]
    valid = len(roots) == 2 and len(children) == 1 and bool(reservations)
    root_id = roots[0]["session_id"] if roots else None
    for generation in generations:
        response = responses.get(generation["id"])
        valid &= bool(
            response
            and response["valid"]
            and generation["id"] in settlements
            and generation["count_policy"] == "blocked_before_wire"
            and generation["native_input"] is None
        )
    valid &= all(
        e["expected_model"] == ROOT_MODEL and e["parent_id"] is None for e in roots
    )
    valid &= all(
        e["expected_model"] == cell.worker_model
        and e["parent_id"] == root_id
        and e["role_origin"] == "coding"
        for e in children
    )
    unresolved = [e for e in ledger.unresolved(events) if e["cell_id"] == cell.cell_id]
    total = ledger.liability(events, cell.cell_id)
    return {
        "valid": bool(valid and not unresolved),
        "subject_usd": str(total) if not unresolved else None,
        "liability_usd": str(total),
        "transmissions": len(reservations),
        "generation_ids": [e["id"] for e in generations],
        "logical_ids": [e["logical_id"] for e in generations],
    }


async def join_with_custody(job):
    """Cancellation never cancels the worker's resource custody, even twice."""
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(job)
            return result, cancelled
        except asyncio.CancelledError:
            cancelled = True
            if job.done():
                return job.result(), cancelled


async def run_cell(
    spec: CellSpec,
    authority: AdmissionAuthority,
    output_dir: Path,
    campaign: CampaignSpec,
    credential_value: str,
    receiver_factory=None,
    assessor=grade_artifact,
    assessment_staging: Path | None = None,
    resource_registrar=None,
) -> SmokeReceipt:
    started = time.monotonic()
    deadline = started + campaign.limits.whole_cell_s
    ready = preflight(campaign)
    require(ready["ready"], "preflight_blocked")
    if campaign.assessment_authority is not None:
        campaign.assessment_authority.validate()
        assessment_staging = campaign.assessment_authority.staging_root
        resource_registrar = campaign.assessment_authority.register
    require(
        assessment_staging is not None
        and assessment_staging.is_dir()
        and callable(resource_registrar),
        "assessor_resource_authority",
    )
    output_dir = prepare_output(campaign, output_dir)
    require(
        authority.ledger.path == output_dir / "campaign.jsonl",
        "campaign_ledger_changed",
    )
    require(authority.quote.lock == campaign.quote.lock, "campaign_quote_changed")
    require(time.monotonic() < deadline - 300, "cell_setup_deadline")
    authority.ledger.start_cell(spec.cell_id)
    cell_dir = output_dir / spec.cell_id
    cell_dir.mkdir(mode=0o700)
    # JSON is a YAML subset and retains the exact parsed arm fingerprint.
    write_once(cell_dir / "interval-smoke.yaml", canonical(arm_matrix(spec)))
    stack = RealStack(
        campaign, spec, authority, cell_dir, credential_value, receiver_factory
    )
    grade, blocker = None, None
    setup, protocol = "unknown", "unknown"
    try:
        await asyncio.wait_for(
            stack.run(cell_dir), max(0.001, deadline - time.monotonic() - 300)
        )
        setup, protocol = "valid", "valid"
        # No untrusted code executes before this separate controller call.
        # The bounded subprocess assessor owns timeout+cleanup. Await its worker
        # to completion; timing out a to_thread await would orphan its custody.
        assessment_job = asyncio.create_task(
            asyncio.to_thread(
                assessor,
                cell_dir / "solution.py",
                campaign.assessment,
                staging_root=assessment_staging,
                registrar=resource_registrar,
            )
        )
        grade, cancelled = await join_with_custody(assessment_job)
        if cancelled:
            raise asyncio.CancelledError()
        require(grade.validity == "valid", "grade_invalid")
        require(grade.cleanup == "confirmed", "assessor_cleanup")
    except BaseException as exc:
        blocker = str(exc) if isinstance(exc, SmokeBlocked) else "cell_execution"
    finally:
        cleanup = await stack.close(deadline=deadline)
    accounting = reconcile_cell(authority.ledger, spec)
    instrumentation = (
        "valid"
        if not blocker
        and cleanup
        and accounting["valid"]
        and time.monotonic() - started <= campaign.limits.whole_cell_s
        else "blocked"
    )
    subject_result = "unknown"
    if grade and grade.validity == "valid":
        subject_result = (
            "success" if all(v == 1 for _, v in grade.awards) else "failure"
        )
    receipt = SmokeReceipt(
        spec.cell_id,
        instrumentation,
        setup,
        protocol,
        "valid" if accounting["valid"] else "unknown",
        subject_result,
        grade,
        accounting["subject_usd"],
        accounting["liability_usd"],
        time.monotonic() - started,
        "confirmed"
        if cleanup and grade and grade.cleanup == "confirmed"
        else "unconfirmed",
        blocker or (None if instrumentation == "valid" else "accounting_or_cleanup"),
    )
    authority.ledger.finish_cell(spec.cell_id, receipt.as_dict())
    return receipt


def report(ledger: Ledger) -> dict:
    events = ledger.events()
    ended = {e["cell_id"]: e["receipt"] for e in events if e["event"] == "cell_end"}
    started = {e["cell_id"] for e in events if e["event"] == "cell_start"}
    return {
        "version": VERSION,
        "scope": "descriptive-smoke-not-ranking-or-promotion",
        "cells": {
            cell: ended.get(
                cell,
                {"instrumentation": "interrupted" if cell in started else "not-run"},
            )
            for cell in ("A0", "A1", "B1")
        },
        "liability_usd": str(ledger.liability(events)),
        "unresolved_wire_ids": [e["id"] for e in ledger.unresolved(events)],
        "all_events_retained": len(events),
    }


def load_campaign(path: Path) -> CampaignSpec:
    """Private runtime input. Reject unknown fields and never echo parsing errors."""
    from datetime import datetime

    raw = strict_json(Path(path).read_bytes(), 131072)
    require(isinstance(raw, dict), "campaign_object")
    require(
        {
            "version",
            "campaign_id",
            "sources",
            "module_sources",
            "quote",
            "assessment",
            "private_output_root",
            "endpoint_qualified",
            "binding_qualified",
            "full_stack_qualification",
            "assessor_qualification",
            "pair_order",
        }
        <= set(raw)
        <= {
            "version",
            "campaign_id",
            "sources",
            "module_sources",
            "quote",
            "assessment",
            "private_output_root",
            "endpoint_qualified",
            "binding_qualified",
            "full_stack_qualification",
            "assessor_qualification",
            "pair_order",
            "qualification_path",
            "qualification_sha256",
            "assessment_authority",
        },
        "campaign_schema",
    )
    quote = raw["quote"]
    require(isinstance(quote, dict), "quote_object")
    require(
        set(quote)
        == {
            "revision",
            "source",
            "verified_at",
            "effective_at",
            "expires_at",
            "binding_ref",
            "service_tier",
            "currency",
            "rates",
            "native_context_max",
            "window_source",
            "long_context_rates",
            "cache_semantics",
        },
        "quote_schema",
    )
    require(
        isinstance(quote["rates"], dict)
        and isinstance(quote["long_context_rates"], dict),
        "quote_rates_object",
    )
    require(
        all(
            isinstance(r, dict)
            for r in [*quote["rates"].values(), *quote["long_context_rates"].values()]
        ),
        "model_rate_object",
    )
    require(isinstance(raw["module_sources"], dict), "module_sources_object")
    require(
        isinstance(raw["sources"], list)
        and all(
            isinstance(s, dict) and set(s) == {"label", "path", "sha256"}
            for s in raw["sources"]
        ),
        "sources_array",
    )
    require(isinstance(raw["assessment"], dict), "assessment_object")
    require(
        raw.get("assessment_authority") is None
        or isinstance(raw["assessment_authority"], dict),
        "assessment_authority_object",
    )
    require(
        raw.get("qualification_path") is None
        or isinstance(raw["qualification_path"], str),
        "qualification_path",
    )
    require(
        raw.get("qualification_sha256") is None
        or isinstance(raw["qualification_sha256"], str),
        "qualification_sha256",
    )
    require(
        isinstance(raw["pair_order"], list)
        and all(isinstance(c, str) for c in raw["pair_order"]),
        "pair_order_array",
    )
    require(
        all(
            raw[k] is None or isinstance(raw[k], str)
            for k in ("full_stack_qualification", "assessor_qualification")
        ),
        "qualification_reference",
    )
    quote = PriceQuote(
        **{
            k: v
            for k, v in quote.items()
            if k
            not in {
                "rates",
                "long_context_rates",
                "verified_at",
                "effective_at",
                "expires_at",
            }
        },
        rates={
            k: ModelRate(**{n: money(v) for n, v in r.items()})
            for k, r in quote["rates"].items()
        },
        long_context_rates={
            k: ModelRate(**{n: money(v) for n, v in r.items()})
            for k, r in quote["long_context_rates"].items()
        },
        **{
            k: datetime.fromisoformat(quote[k])
            for k in ("verified_at", "effective_at", "expires_at")
        },
    )
    return CampaignSpec(
        **{
            k: v
            for k, v in raw.items()
            if k
            not in {
                "sources",
                "module_sources",
                "quote",
                "assessment",
                "private_output_root",
                "pair_order",
                "qualification_path",
                "assessment_authority",
            }
        },
        sources=tuple(
            SourceLock(s["label"], Path(s["path"]), s["sha256"]) for s in raw["sources"]
        ),
        module_sources={k: Path(v) for k, v in raw["module_sources"].items()},
        quote=quote,
        assessment=AssessmentSpec(
            **{
                k: Path(v) if k == "isolation_path" and v is not None else v
                for k, v in raw["assessment"].items()
            }
        ),
        private_output_root=Path(raw["private_output_root"]),
        pair_order=tuple(raw["pair_order"]),
        qualification_path=Path(raw["qualification_path"])
        if raw.get("qualification_path")
        else None,
        assessment_authority=AssessmentAuthority(
            **{
                k: Path(v)
                if k.endswith("_root") or k.endswith("_script") or k == "batch_dir"
                else v
                for k, v in raw["assessment_authority"].items()
            }
        )
        if isinstance(raw.get("assessment_authority"), dict)
        else None,
    )
