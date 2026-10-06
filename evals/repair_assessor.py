"""Receipt grading with an injected, parent-qualified isolated runner only.

Runner contract: callable(AssessmentRequest) -> bounded JSON bytes. It must run
request.driver_source as a standalone script INSIDE its qualified sandbox, with
argv [request_json_path, driver_result_path], and wrap that result as
{"execution": <driver result>, "cleanup": <independently confirmed runtime bool>}.
No local execution fallback exists. The parent owns hard wall/memory/process/
output bounds, network-none, no credentials/mounts, cancellation and teardown.
The emitted supervisor uses separate child processes, not an AST restriction.
These integrity hashes bind inputs; they do not authenticate runner assertions
or provide a tamper-proof grader against actively malicious arbitrary Python.

Private case JSON: {"categories": {category: [case, ...], ...}} with exactly
overlap/touch/order/invalid/immutability, all nonempty. A case has "ranges" and
either "expected" (JSON list of integer pairs) or "raises": "ValueError".
Optional "container" and "pair_container" are "list" or "tuple". Cases are
supplied by the assessor owner; no hidden answers are shipped or staged.
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from typing import Callable

try:
    from .interval_repair import (
        BUGGY_SOURCE,
        Artifact,
        canonical_json,
        sha256,
        source_binding,
    )
except ImportError:
    from interval_repair import (
        BUGGY_SOURCE,
        Artifact,
        canonical_json,
        sha256,
        source_binding,
    )

CATEGORIES = ("overlap", "touch", "order", "invalid", "immutability")
RECEIPT_VERSION = "interval-repair-receipt/v1"
REQUEST_VERSION = "interval-repair-request/v1"


@dataclass(frozen=True)
class Limits:
    wall_s: int = 30
    phase_s: int = 4
    cpu_s: int = 3
    memory_bytes: int = 268_435_456
    process_count: int = 16
    input_bytes: int = 262_144
    output_bytes: int = 16_384
    case_bytes: int = 65_536
    case_count: int = 128

    def __post_init__(self):
        ceilings = (30, 4, 3, 268_435_456, 16, 262_144, 16_384, 65_536, 128)
        for value, maximum in zip(asdict(self).values(), ceilings):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("limits must be positive integers within ceilings")
        if self.wall_s < 4 * self.phase_s + 2:
            raise ValueError("wall bound must reserve time for all phases and cleanup")


@dataclass(frozen=True)
class AssessmentRequest:
    input_json: bytes
    driver_source: bytes
    limits: Limits

    def __post_init__(self):
        if (
            type(self.input_json) is not bytes
            or type(self.driver_source) is not bytes
            or type(self.limits) is not Limits
        ):
            raise ValueError("assessment requests require immutable bytes and limits")

    @property
    def sha256(self):
        return strict_json(self.input_json, self.limits.input_bytes)["request_sha256"]


class IsolationRequired(ValueError):
    pass


def strict_json(raw: bytes, maximum: int):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ValueError("JSON bytes missing or outside bounds")

    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate JSON key")
            result[name] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite JSON number")

    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, RecursionError, ValueError):
        raise ValueError("invalid bounded JSON") from None


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("incomplete or unknown receipt fields")


def _count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError("invalid selected/result count")
    return value


def _private_cases(raw: bytes, limits: Limits):
    cases = strict_json(raw, limits.case_bytes)
    _keys(cases, ("categories",))
    _keys(cases["categories"], CATEGORIES)
    total = 0
    for category, values in cases["categories"].items():
        if type(values) is not list or not values:
            raise ValueError("every objective category requires cases")
        total += len(values)
        for case in values:
            if type(case) is not dict:
                raise ValueError("case must be an object")
            optional = {"container", "pair_container"} & set(case)
            expected = {"ranges", "raises" if "raises" in case else "expected"}
            _keys(case, expected | optional)
            for field in optional:
                if case[field] not in ("list", "tuple"):
                    raise ValueError("invalid container selector")
            if "raises" in case:
                if case["raises"] != "ValueError":
                    raise ValueError("only ValueError is an expected fault")
            else:
                output = case["expected"]
                if type(output) is not list or any(
                    type(pair) is not list
                    or len(pair) != 2
                    or any(type(n) is not int for n in pair)
                    or pair[0] > pair[1]
                    for pair in output
                ):
                    raise ValueError("expected result must be integer pairs")
            if category == "invalid" and "raises" not in case:
                raise ValueError("invalid cases must expect ValueError")
            if category != "invalid" and category != "immutability":
                if "expected" not in case:
                    raise ValueError("functional cases must expect a result")
    if total > limits.case_count:
        raise ValueError("too many private cases")
    return cases


# Executable bytes are sent to the isolated runner, NEVER evaluated here.
DRIVER_SOURCE = r'''"""Standalone supervisor: run only in the parent-qualified sandbox."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CATEGORIES = ("overlap", "touch", "order", "invalid", "immutability")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CountingResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.assertion_failures = 0

    def addFailure(self, test, error):
        if issubclass(error[0], AssertionError):
            self.assertion_failures += 1
        super().addFailure(test, error)

    def addSubTest(self, test, subtest, error):
        if error is not None and issubclass(error[0], AssertionError):
            self.assertion_failures += 1
        super().addSubTest(test, subtest, error)


def ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from ids(test)
        else:
            yield test.id()


def run_tests(root, filename):
    source_hash = digest((root / "intervals.py").read_bytes())
    test_hash = digest((root / filename).read_bytes())
    load_module(root / "intervals.py", "intervals")
    module = load_module(root / filename, Path(filename).stem)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    selected_ids = list(ids(suite))
    result = CountingResult()
    suite.run(result)
    return {
        "selected": len(selected_ids), "run": result.testsRun,
        "failures": len(result.failures),
        "assertion_failures": result.assertion_failures,
        "errors": len(result.errors), "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "selection_sha256": digest(encode(selected_ids)),
        "source_sha256": source_hash, "test_sha256": test_hash,
    }


def objective(root, cases):
    function = load_module(root / "intervals.py", "intervals").coalesce
    results = {
        c: {"selected": 0, "passed": 0, "failed": 0, "errors": 0}
        for c in CATEGORIES
    }
    for category, values in cases["categories"].items():
        for case in values:
            value = copy.deepcopy(case["ranges"])
            if isinstance(value, list):
                if case.get("pair_container") == "tuple":
                    value = [tuple(p) if isinstance(p, list) else p for p in value]
                if case.get("container") == "tuple":
                    value = tuple(value)
            before = copy.deepcopy(value)
            error = False
            correct = False
            try:
                answer = function(value)
                if "expected" in case:
                    expected = [tuple(p) for p in case["expected"]]
                    correct = (
                        type(answer) is list and answer == expected
                        and all(type(p) is tuple and len(p) == 2
                                and all(type(n) is int for n in p) for p in answer)
                        and answer is not value
                    )
            except ValueError:
                correct = case.get("raises") == "ValueError"
            except Exception:
                correct = False
            except BaseException:
                error = True
            unchanged = type(value) is type(before) and value == before
            # JSON inputs have no cycles or custom equality. repr detects bool/int
            # substitution and inner list/tuple mutation that equality can miss.
            unchanged = unchanged and repr(value) == repr(before)
            if category != "immutability":
                result = results[category]
                result["selected"] += 1
                result["errors" if error else "passed" if correct else "failed"] += 1
            result = results["immutability"]
            result["selected"] += 1
            passed = unchanged and (correct if category == "immutability" else True)
            result["errors" if error else "passed" if passed else "failed"] += 1
    return results


def worker(mode, root, case_path, receipt_path, limits_path):
    limits = json.loads(Path(limits_path).read_bytes())
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_s"], limits["cpu_s"]))
    resource.setrlimit(resource.RLIMIT_AS,
                       (limits["memory_bytes"], limits["memory_bytes"]))
    resource.setrlimit(resource.RLIMIT_NPROC,
                       (limits["process_count"], limits["process_count"]))
    resource.setrlimit(resource.RLIMIT_FSIZE,
                       (limits["output_bytes"], limits["output_bytes"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(root)
    os.chdir(root)
    sys.dont_write_bytecode = True
    try:
        if mode == "objective":
            result = objective(root, json.loads(Path(case_path).read_bytes()))
        else:
            filename = "test_public.py" if mode == "public" else "test_regression.py"
            result = run_tests(root, filename)
        output = {"status": "completed", "result": result}
    except BaseException:
        output = {"status": "fault"}
    Path(receipt_path).write_bytes(encode(output))


def supervise(request_path):
    input_path = Path(request_path)
    if input_path.stat().st_size > 262144:
        raise ValueError("request exceeds ceiling")
    request = json.loads(input_path.read_bytes())
    request_hash = request.pop("request_sha256")
    if digest(encode(request)) != request_hash:
        raise ValueError("request binding mismatch")
    if request["driver_sha256"] != digest(Path(__file__).read_bytes()):
        raise ValueError("driver source mismatch")
    result = {
        "schema": "interval-repair-receipt/v1",
        "request_sha256": request_hash, "binding": request["binding"],
        "status": "fault", "cleanup": False,
    }
    limits = request["limits"]
    if request["schema"] != "interval-repair-request/v1":
        return result
    if len(encode(request)) > limits["input_bytes"]:
        return result
    files = {n: base64.b64decode(v, validate=True)
             for n, v in request["files"].items()}
    if set(files) != {"intervals.py", "test_public.py", "test_regression.py"}:
        return result
    for name, content in files.items():
        maximum = 16384 if name == "test_public.py" else 65536
        if not 0 < len(content) <= maximum:
            return result
    hashes = {n: digest(v) for n, v in files.items()}
    if hashes != request["file_sha256"]:
        return result
    if digest(encode(hashes)) != request["artifact_sha256"]:
        return result
    buggy = base64.b64decode(request["buggy_source"], validate=True)
    if digest(buggy) != request["buggy_sha256"]:
        return result
    work = Path(tempfile.mkdtemp(prefix="interval-assess-"))
    try:
        case_path = work / "private-cases.json"
        case_path.write_bytes(encode(request["cases"]))
        limits_path = work / "limits.json"
        limits_path.write_bytes(encode(limits))
        receipts = {}
        for mode in ("objective", "public", "regression_green", "regression_buggy"):
            root = work / mode
            root.mkdir()
            for name, content in files.items():
                (root / name).write_bytes(
                    buggy if mode == "regression_buggy" and name == "intervals.py"
                    else content
                )
                (root / name).chmod(0o444)
            root.chmod(0o555)
            receipt = work / (mode + ".json")
            log = work / (mode + ".log")
            with log.open("wb") as stream:
                try:
                    child = subprocess.run(
                        [sys.executable, "-I", "-B", str(Path(__file__).absolute()),
                         "--worker", mode, str(root), str(case_path),
                         str(receipt), str(limits_path)],
                        stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                        env={"PATH": "/usr/bin:/bin", "HOME": str(work),
                             "PYTHONDONTWRITEBYTECODE": "1"},
                        cwd=work, timeout=limits["phase_s"], check=False,
                    )
                except subprocess.TimeoutExpired:
                    result["status"] = "timeout"
                    return result
            if child.returncode != 0 or not receipt.is_file():
                return result
            if receipt.stat().st_size > limits["output_bytes"]:
                return result
            observed = json.loads(receipt.read_bytes())
            if observed.get("status") != "completed":
                return result
            receipts[mode] = observed["result"]
        result.update(receipts)
        result["status"] = "completed"
    except BaseException:
        result["status"] = "fault"
    finally:
        try:
            for mode in ("objective", "public", "regression_green", "regression_buggy"):
                root = work / mode
                if root.is_dir() and not root.is_symlink():
                    root.chmod(0o700)
            shutil.rmtree(work)
            result["cleanup"] = not work.exists()
        except BaseException:
            result["cleanup"] = False
    return result


if __name__ == "__main__":
    if len(sys.argv) == 7 and sys.argv[1] == "--worker":
        worker(*sys.argv[2:])
    elif len(sys.argv) == 3:
        output = supervise(sys.argv[1])
        payload = encode(output)
        if len(payload) > 16384:
            raise ValueError("driver receipt exceeds ceiling")
        Path(sys.argv[2]).write_bytes(payload)
    else:
        raise SystemExit("isolated driver requires request and result paths")
'''.encode("utf-8")


def make_request(
    artifact: Artifact, private_cases_json: bytes, *, limits: Limits = Limits()
) -> AssessmentRequest:
    """Construct immutable input; never import, compile or execute the artifact."""
    if type(artifact) is not Artifact or type(limits) is not Limits:
        raise ValueError("expected immutable artifact and limits")
    if artifact.binding != source_binding():
        raise ValueError("artifact task/grader binding is stale")
    # Directly constructed Artifacts must not bypass protected-public integrity.
    try:
        from .interval_repair import SOLVER_FILES, TASK_DIRECTORY, _read_tree
    except ImportError:
        from interval_repair import SOLVER_FILES, TASK_DIRECTORY, _read_tree
    if (
        dict(artifact.files)["test_public.py"]
        != dict(_read_tree(TASK_DIRECTORY, SOLVER_FILES))["test_public.py"]
    ):
        raise ValueError("protected public tests changed")
    cases = _private_cases(private_cases_json, limits)
    envelope = {
        "schema": REQUEST_VERSION,
        "binding": dict(artifact.binding),
        "driver_sha256": sha256(DRIVER_SOURCE),
        "artifact_sha256": artifact.sha256,
        "files": {
            name: base64.b64encode(data).decode("ascii")
            for name, data in artifact.files
        },
        "file_sha256": {name: sha256(data) for name, data in artifact.files},
        "buggy_source": base64.b64encode(BUGGY_SOURCE).decode("ascii"),
        "buggy_sha256": sha256(BUGGY_SOURCE),
        "cases": cases,
        "limits": asdict(limits),
    }
    envelope["request_sha256"] = sha256(canonical_json(envelope))
    payload = canonical_json(envelope)
    if len(payload) > limits.input_bytes:
        raise ValueError("encoded request exceeds input ceiling")
    return AssessmentRequest(payload, DRIVER_SOURCE, limits)


def _test_receipt(value, source_hash, test_hash):
    counts = (
        "selected",
        "run",
        "failures",
        "assertion_failures",
        "errors",
        "skipped",
        "expected_failures",
        "unexpected_successes",
    )
    _keys(value, (*counts, "selection_sha256", "source_sha256", "test_sha256"))
    for field in counts:
        _count(value[field])
    selection = value["selection_sha256"]
    if (
        type(selection) is not str
        or len(selection) != 64
        or any(c not in "0123456789abcdef" for c in selection)
    ):
        raise ValueError("invalid test-selection hash")
    if value["source_sha256"] != source_hash or value["test_sha256"] != test_hash:
        raise ValueError("test execution source mismatch")
    if value["run"] != value["selected"]:
        raise ValueError("selected tests were not all executed")
    if value["assertion_failures"] > value["failures"]:
        raise ValueError("assertion count exceeds failures")
    # Failed subtests may outnumber test methods; those are genuine assertions.
    if (
        sum(value[n] for n in ("skipped", "expected_failures", "unexpected_successes"))
        > value["run"]
    ):
        raise ValueError("inconsistent test result counts")


def _green(value):
    return value["selected"] > 0 and all(
        value[n] == 0
        for n in (
            "failures",
            "errors",
            "skipped",
            "expected_failures",
            "unexpected_successes",
        )
    )


def grade_receipt(request: AssessmentRequest, raw: bytes) -> dict:
    """Strict complete criteria; faults/missingness award nothing, not zero."""
    cleanup = None
    driver_cleanup = None

    def invalid(reason):
        return {
            "validity": "invalid",
            "reason": reason,
            "criteria": {},
            "success": None,
            "critical": "unknown",
            "cleanup": cleanup,
            "driver_cleanup": driver_cleanup,
            "operational_ready": False,
        }

    try:
        outer = strict_json(raw, request.limits.output_bytes)
        _keys(outer, ("execution", "cleanup"))
        if type(outer["cleanup"]) is not bool:
            raise ValueError("runtime cleanup must be explicit")
        cleanup = outer["cleanup"]
        receipt = outer["execution"]
        envelope = strict_json(request.input_json, request.limits.input_bytes)
        expected_hash = envelope["request_sha256"]
        unsigned = dict(envelope)
        del unsigned["request_sha256"]
        if (
            sha256(canonical_json(unsigned)) != expected_hash
            or envelope["schema"] != REQUEST_VERSION
            or envelope["driver_sha256"] != sha256(request.driver_source)
            or request.driver_source != DRIVER_SOURCE
            or envelope["limits"] != asdict(request.limits)
            or envelope["binding"] != dict(source_binding())
        ):
            raise ValueError("request source or version binding mismatch")
        base = {"schema", "request_sha256", "binding", "status", "cleanup"}
        if type(receipt) is not dict:
            raise ValueError("missing driver receipt")
        status = receipt.get("status")
        fields = base | (
            {"objective", "public", "regression_green", "regression_buggy"}
            if status == "completed"
            else set()
        )
        _keys(receipt, fields)
        if (
            receipt["schema"] != RECEIPT_VERSION
            or receipt["request_sha256"] != envelope["request_sha256"]
            or receipt["binding"] != envelope["binding"]
            or type(receipt["cleanup"]) is not bool
        ):
            raise ValueError("receipt binding or cleanup mismatch")
        driver_cleanup = receipt["cleanup"]
        if status in ("timeout", "fault"):
            return invalid("isolated_" + status)
        if status != "completed":
            raise ValueError("unknown execution status")
        _keys(receipt["objective"], CATEGORIES)
        criteria = {}
        case_categories = envelope["cases"]["categories"]
        for category in CATEGORIES:
            value = receipt["objective"][category]
            _keys(value, ("selected", "passed", "failed", "errors"))
            for count in value.values():
                _count(count)
            expected = (
                sum(len(values) for values in case_categories.values())
                if category == "immutability"
                else len(case_categories[category])
            )
            if (
                value["selected"] != expected
                or sum(value[n] for n in ("passed", "failed", "errors")) != expected
            ):
                raise ValueError("incomplete objective execution")
            if value["errors"]:
                return invalid("objective_execution_fault")
            criteria[category] = value["passed"] == expected
        hashes = envelope["file_sha256"]
        for name in ("public", "regression_green", "regression_buggy"):
            _test_receipt(
                receipt[name],
                envelope["buggy_sha256"]
                if name == "regression_buggy"
                else hashes["intervals.py"],
                hashes["test_public.py"]
                if name == "public"
                else hashes["test_regression.py"],
            )
            if receipt[name]["errors"]:
                return invalid("test_execution_fault")
        good, bad = receipt["regression_green"], receipt["regression_buggy"]
        if (
            good["selected"] != bad["selected"]
            or good["selection_sha256"] != bad["selection_sha256"]
        ):
            raise ValueError("regression selection changed during restoration")
        criteria["public"] = _green(receipt["public"])
        criteria["regression_green"] = _green(good)
        criteria["regression_red"] = (
            bad["selected"] > 0
            and bad["assertion_failures"] > 0
            and bad["assertion_failures"] == bad["failures"]
            and all(
                bad[n] == 0
                for n in ("skipped", "expected_failures", "unexpected_successes")
            )
        )
        return {
            "validity": "valid",
            "reason": None,
            "criteria": criteria,
            "success": all(criteria.values()),
            "critical": "pass" if criteria["immutability"] else "fail",
            "cleanup": cleanup,
            "driver_cleanup": driver_cleanup,
            "operational_ready": cleanup and driver_cleanup,
        }
    except (ValueError, TypeError, KeyError, RecursionError):
        return invalid("malformed_or_incomplete_receipt")


def assess(
    artifact: Artifact,
    private_cases_json: bytes,
    *,
    isolated_runner: Callable[[AssessmentRequest], bytes] | None = None,
    limits: Limits = Limits(),
) -> dict:
    if isolated_runner is None or not callable(isolated_runner):
        raise IsolationRequired("a parent-qualified isolated runner is required")
    request = make_request(artifact, private_cases_json, limits=limits)
    try:
        raw = isolated_runner(request)
    except TimeoutError:
        # No confirmed cleanup exists when the runner does not return its receipt.
        result = grade_receipt(request, b"")
        result["reason"] = "isolated_runner_timeout"
        return result
    except Exception:
        result = grade_receipt(request, b"")
        result["reason"] = "isolated_runner_fault"
        return result
    return grade_receipt(request, raw)
