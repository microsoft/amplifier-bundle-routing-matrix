"""Synthetic controller controls only; artifacts and driver NEVER execute here.

Parent-owned isolated qualification can reuse GOOD_SOURCE, BAD_SOURCE,
MALFORMED_SOURCE, HANG_SOURCE, REGRESSION_SOURCE and DEVELOPMENT_CASES.
These are newly authored PUBLIC development controls, not private holdouts.
The mocked receipts below test validation, not actual execution or isolation.
"""

from __future__ import annotations

import ast
import base64
import copy
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from evals.interval_repair import (
    ARTIFACT_FILES,
    BUGGY_SOURCE,
    FILE_LIMITS,
    SOLVER_FILES,
    Artifact,
    canonical_json,
    sha256,
    snapshot_artifact,
    source_binding,
    stage_task,
)
from evals.repair_assessor import (
    CATEGORIES,
    DRIVER_SOURCE,
    RECEIPT_VERSION,
    IsolationRequired,
    Limits,
    assess,
    grade_receipt,
    make_request,
    strict_json,
)

GOOD_SOURCE = BUGGY_SOURCE.replace(
    b"    return sorted(copied)",
    b"""    merged = []
    for start, end in sorted(copied):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
""",
)
BAD_SOURCE = BUGGY_SOURCE
MALFORMED_SOURCE = b"def coalesce(:\n"
HANG_SOURCE = b"def coalesce(ranges):\n    while True:\n        pass\n"
REGRESSION_SOURCE = b"""import unittest
from intervals import coalesce


class Regression(unittest.TestCase):
    def test_merge(self):
        with self.subTest(kind="overlap"):
            self.assertEqual(coalesce([(3, 8), (5, 10)]), [(3, 10)])
        with self.subTest(kind="touch"):
            self.assertEqual(coalesce([(12, 15), (15, 18)]), [(12, 18)])
"""

DEVELOPMENT_CASES = {
    "categories": {
        "overlap": [
            {"ranges": [[3, 8], [5, 10]], "expected": [[3, 10]]},
            {"ranges": [[-5, 7], [-2, 1], [0, 4]], "expected": [[-5, 7]]},
        ],
        "touch": [
            {"ranges": [[12, 15], [15, 18]], "expected": [[12, 18]]},
            {"ranges": [[9, 9], [9, 9]], "expected": [[9, 9]]},
        ],
        "order": [
            {"ranges": [[21, 23], [-3, -1]], "expected": [[-3, -1], [21, 23]]},
            {"ranges": [], "expected": [], "container": "tuple"},
            {
                "ranges": [[0, 2], [3, 4]],
                "expected": [[0, 2], [3, 4]],
                "container": "tuple",
                "pair_container": "tuple",
            },
        ],
        "invalid": [
            {"ranges": value, "raises": "ValueError"}
            for value in (
                None,
                2,
                "not ranges",
                {"a": 2},
                [3],
                [[1]],
                [[1, 2, 3]],
                [[5, 2]],
                [[False, 2]],
                [[2, True]],
                [[1.0, 2]],
                [["1", 2]],
                [[None, 2]],
                [[1, 2], [9, 4]],
            )
        ],
        "immutability": [
            {"ranges": [[10, 14], [1, 3]], "expected": [[1, 3], [10, 14]]},
            {"ranges": [[1, 3], [False, 5]], "raises": "ValueError"},
        ],
    }
}


def synthetic_receipt(request):
    """Fabricated complete success receipt, not an execution attestation."""
    envelope = strict_json(request.input_json, request.limits.input_bytes)
    categories = envelope["cases"]["categories"]
    objective = {}
    for category in CATEGORIES:
        selected = (
            sum(len(values) for values in categories.values())
            if category == "immutability"
            else len(categories[category])
        )
        objective[category] = {
            "selected": selected,
            "passed": selected,
            "failed": 0,
            "errors": 0,
        }

    def test_receipt(test_file, buggy=False):
        return {
            "selected": 1,
            "run": 1,
            "failures": 2 if buggy else 0,
            "assertion_failures": 2 if buggy else 0,
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
            "selection_sha256": sha256(b"synthetic selected method"),
            "source_sha256": envelope["buggy_sha256"]
            if buggy
            else envelope["file_sha256"]["intervals.py"],
            "test_sha256": envelope["file_sha256"][test_file],
        }

    return {
        "execution": {
            "schema": RECEIPT_VERSION,
            "request_sha256": envelope["request_sha256"],
            "binding": envelope["binding"],
            "status": "completed",
            "cleanup": True,
            "objective": objective,
            "public": test_receipt("test_public.py"),
            "regression_green": test_receipt("test_regression.py"),
            "regression_buggy": test_receipt("test_regression.py", True),
        },
        "cleanup": True,
    }


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.task = self.root / "task"
        self.binding = stage_task(self.task)

    def retain_regression(self):
        (self.task / "test_regression.py").write_bytes(REGRESSION_SOURCE)

    def test_stage_only_three_solver_files(self):
        self.assertEqual(set(os.listdir(self.task)), set(SOLVER_FILES))
        self.assertEqual((self.task / "intervals.py").read_bytes(), BUGGY_SOURCE)
        self.assertEqual(self.binding, source_binding())
        with self.assertRaises(ValueError):
            stage_task(self.task)

    def test_snapshot_immutable_and_not_live(self):
        self.retain_regression()
        artifact = snapshot_artifact(self.task, expected_binding=self.binding)
        original_hash = artifact.sha256
        (self.task / "intervals.py").write_bytes(HANG_SOURCE)
        (self.task / "test_regression.py").write_bytes(b"raise RuntimeError\n")
        self.assertEqual(dict(artifact.files)["intervals.py"], BUGGY_SOURCE)
        self.assertEqual(dict(artifact.files)["test_regression.py"], REGRESSION_SOURCE)
        self.assertEqual(artifact.sha256, original_hash)
        with self.assertRaises(FrozenInstanceError):
            artifact.files = ()

    def test_unknown_file_and_directory_rejected(self):
        self.retain_regression()
        for directory in (False, True):
            with self.subTest(directory=directory):
                path = self.task / "unknown"
                path.mkdir() if directory else path.write_bytes(b"x")
                with self.assertRaises(ValueError):
                    snapshot_artifact(self.task)
                path.rmdir() if directory else path.unlink()

    def test_missing_regression_rejected(self):
        with self.assertRaises(ValueError):
            snapshot_artifact(self.task)

    def test_public_file_edits_rejected(self):
        self.retain_regression()
        for name in ("test_public.py", "instructions.txt"):
            with self.subTest(name=name):
                path = self.task / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.assertRaises(ValueError):
                    snapshot_artifact(self.task)
                path.write_bytes(original)

    def test_links_rejected(self):
        self.retain_regression()
        path = self.task / "intervals.py"
        path.unlink()
        path.symlink_to(self.root / "absent.py")
        with self.assertRaises(ValueError):
            snapshot_artifact(self.task)
        path.unlink()
        path.write_bytes(BUGGY_SOURCE)
        linked = self.root / "linked-task"
        linked.symlink_to(self.task, target_is_directory=True)
        with self.assertRaises(ValueError):
            snapshot_artifact(linked)
        with self.assertRaises(ValueError):
            stage_task(linked / "new")
        os.link(path, self.root / "hardlink.py")
        with self.assertRaises(ValueError):
            snapshot_artifact(self.task)

    def test_size_and_nonregular_rejected(self):
        self.retain_regression()
        path = self.task / "intervals.py"
        for content in (b"", b"x" * (FILE_LIMITS["intervals.py"] + 1)):
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                snapshot_artifact(self.task)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            snapshot_artifact(self.task)

    def test_binding_and_mutable_input_rejected(self):
        self.retain_regression()
        with self.assertRaises(ValueError):
            snapshot_artifact(self.task, expected_binding=())
        artifact = snapshot_artifact(self.task)
        with self.assertRaises(ValueError):
            Artifact(list(artifact.files), artifact.binding)
        files = tuple(
            (name, bytearray(data) if name == "intervals.py" else data)
            for name, data in artifact.files
        )
        with self.assertRaises(ValueError):
            Artifact(files, artifact.binding)
        with self.assertRaises(ValueError):
            Artifact((*artifact.files, ("extra.py", b"x")), artifact.binding)

    def test_import_time_sources_cannot_claim_newer_disk_bytes(self):
        self.retain_regression()
        with patch("evals.interval_repair._GRADER_SOURCE", ()):
            with self.assertRaises(ValueError):
                snapshot_artifact(self.task)

    def test_parent_traversal_rejected_without_following_links(self):
        linked = self.root / "linked"
        linked.symlink_to(self.task, target_is_directory=True)
        with self.assertRaises(ValueError):
            stage_task(linked / ".." / "new")


class AssessorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        task = Path(self.temporary.name) / "task"
        stage_task(task)
        (task / "intervals.py").write_bytes(GOOD_SOURCE)
        (task / "test_regression.py").write_bytes(REGRESSION_SOURCE)
        self.artifact = snapshot_artifact(task)
        self.cases = canonical_json(DEVELOPMENT_CASES)
        self.request = make_request(self.artifact, self.cases)
        self.receipt = synthetic_receipt(self.request)

    def grade(self, receipt=None):
        return grade_receipt(
            self.request, canonical_json(self.receipt if receipt is None else receipt)
        )

    def test_synthetic_good(self):
        result = self.grade()
        self.assertEqual(result["validity"], "valid")
        self.assertTrue(result["success"])
        self.assertEqual(
            set(result["criteria"]),
            {*CATEGORIES, "public", "regression_green", "regression_red"},
        )

    def test_no_runner_no_local_execution(self):
        with self.assertRaises(IsolationRequired):
            assess(self.artifact, self.cases)
        for source in (BAD_SOURCE, MALFORMED_SOURCE, HANG_SOURCE):
            artifact = replace(
                self.artifact,
                files=tuple(
                    (name, source if name == "intervals.py" else data)
                    for name, data in self.artifact.files
                ),
            )
            seen = []

            def runner(request):
                seen.append(request)
                return canonical_json(synthetic_receipt(request))

            # Even malformed/hanging source is passed as bytes, not imported here.
            result = assess(artifact, self.cases, isolated_runner=runner)
            self.assertTrue(result["success"])
            self.assertEqual(len(seen), 1)
            envelope = strict_json(seen[0].input_json, Limits().input_bytes)
            self.assertEqual(
                base64.b64decode(envelope["files"]["intervals.py"]), source
            )

    def test_bad_objective_is_valid_failure(self):
        for category in CATEGORIES:
            receipt = copy.deepcopy(self.receipt)
            value = receipt["execution"]["objective"][category]
            value["passed"] -= 1
            value["failed"] += 1
            result = self.grade(receipt)
            self.assertEqual(result["validity"], "valid")
            self.assertFalse(result["success"])
            self.assertFalse(result["criteria"][category])
            self.assertEqual(
                result["critical"], "fail" if category == "immutability" else "pass"
            )

    def test_malformed_no_awards(self):
        for raw in (
            b"",
            b"not JSON",
            b'{"cleanup":true,"cleanup":true}',
            b'{"cleanup":NaN}',
            b"x" * (Limits().output_bytes + 1),
            b"[]",
        ):
            result = grade_receipt(self.request, raw)
            self.assertEqual(result["validity"], "invalid")
            self.assertEqual(result["criteria"], {})
            self.assertIsNone(result["success"])
            self.assertEqual(result["critical"], "unknown")

    def test_hang_receipt_and_runner_exception(self):
        receipt = copy.deepcopy(self.receipt)
        execution = receipt["execution"]
        for field in ("objective", "public", "regression_green", "regression_buggy"):
            del execution[field]
        execution["status"] = "timeout"
        result = self.grade(receipt)
        self.assertEqual(result["reason"], "isolated_timeout")
        self.assertEqual(result["criteria"], {})
        self.assertTrue(result["cleanup"])

        def hang(_):
            raise TimeoutError("synthetic timeout, no actual hang")

        result = assess(self.artifact, self.cases, isolated_runner=hang)
        self.assertEqual(result["validity"], "invalid")
        self.assertEqual(result["reason"], "isolated_runner_timeout")
        self.assertIsNone(result["cleanup"])

    def test_cleanup_independent_of_quality(self):
        for location in ("runtime", "driver"):
            receipt = copy.deepcopy(self.receipt)
            if location == "runtime":
                receipt["cleanup"] = False
            else:
                receipt["execution"]["cleanup"] = False
            result = self.grade(receipt)
            self.assertTrue(result["success"])
            self.assertFalse(result["operational_ready"])
        del self.receipt["cleanup"]
        self.assertEqual(self.grade()["validity"], "invalid")

    def test_missing_extra_counts_binding_and_errors_invalid(self):
        mutations = (
            lambda r: r["execution"]["objective"].pop("overlap"),
            lambda r: r["execution"]["objective"].update(extra={}),
            lambda r: r["execution"].update(request_sha256="0" * 64),
            lambda r: r["execution"]["binding"].update(task_version="changed"),
            lambda r: r["execution"]["objective"]["touch"].update(selected=0),
            lambda r: r["execution"]["objective"]["order"].update(passed=True),
            lambda r: r["execution"]["regression_green"].update(source_sha256="0" * 64),
            lambda r: r["execution"]["regression_buggy"].update(run=0),
            lambda r: r["execution"]["regression_buggy"].update(errors=1),
            lambda r: r["execution"]["regression_buggy"].update(
                selection_sha256="0" * 64
            ),
        )
        for mutate in mutations:
            receipt = copy.deepcopy(self.receipt)
            mutate(receipt)
            result = self.grade(receipt)
            self.assertEqual(result["validity"], "invalid")
            self.assertEqual(result["criteria"], {})

    def test_vacuous_red_wrong_reason_and_skips_fail(self):
        for field, value in (
            ("assertion_failures", 0),
            ("skipped", 1),
            ("expected_failures", 1),
            ("unexpected_successes", 1),
        ):
            receipt = copy.deepcopy(self.receipt)
            receipt["execution"]["regression_buggy"][field] = value
            result = self.grade(receipt)
            self.assertEqual(result["validity"], "valid")
            self.assertFalse(result["criteria"]["regression_red"])
        for phase in ("regression_green", "regression_buggy"):
            value = self.receipt["execution"][phase]
            for name in (
                "selected",
                "run",
                "failures",
                "assertion_failures",
            ):
                value[name] = 0
        result = self.grade()
        self.assertEqual(result["validity"], "valid")
        self.assertFalse(result["success"])

    def test_source_and_private_cases_validation(self):
        with self.assertRaises(ValueError):
            make_request(replace(self.artifact, binding=()), self.cases)
        files = tuple(
            (name, b"x" if name == "test_public.py" else data)
            for name, data in self.artifact.files
        )
        with self.assertRaises(ValueError):
            make_request(replace(self.artifact, files=files), self.cases)
        for category in CATEGORIES:
            cases = copy.deepcopy(DEVELOPMENT_CASES)
            cases["categories"][category] = []
            with self.assertRaises(ValueError):
                make_request(self.artifact, canonical_json(cases))
        with self.assertRaises(ValueError):
            make_request(self.artifact, self.cases, limits=Limits(case_count=1))
        with self.assertRaises(ValueError):
            Limits(output_bytes=16_385)

    def test_hashes_driver_and_controls_parse_only(self):
        envelope = strict_json(self.request.input_json, Limits().input_bytes)
        request_hash = envelope.pop("request_sha256")
        self.assertEqual(request_hash, sha256(canonical_json(envelope)))
        self.assertEqual(envelope["driver_sha256"], sha256(DRIVER_SOURCE))
        self.assertEqual(tuple(sorted(envelope["files"])), ARTIFACT_FILES)
        self.assertEqual(envelope["buggy_sha256"], sha256(BUGGY_SOURCE))
        for source in (DRIVER_SOURCE, GOOD_SOURCE, BAD_SOURCE, HANG_SOURCE):
            ast.parse(source)  # parsing only, never compile/exec/import
        with self.assertRaises(SyntaxError):
            ast.parse(MALFORMED_SOURCE)
        self.assertNotEqual(GOOD_SOURCE, BAD_SOURCE)


if __name__ == "__main__":
    unittest.main()
