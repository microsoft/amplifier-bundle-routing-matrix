"""Opt-in actual Docker controls. Never execute fixture source on the host.

Run ONLY with the parent-qualified isolation proof and explicit registrar paths.
Ordinary offline CI does not select these cases. One control container at a time.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from live_smoke import (
    ASSESSOR_DRIVER,
    AssessmentSpec,
    GRAMMAR_SHA256,
    grade_artifact,
    bounded_process,
    require,
    strict_json,
)

__test__ = os.environ.get("ROUTING_ASSESSOR_CONTROLS") == "1"

VALIDATION = """\
    if type(ranges) is not list:
        raise ValueError()
    for pair in ranges:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            raise ValueError()
        if type(pair[0]) is not int or type(pair[1]) is not int or pair[0] >= pair[1]:
            raise ValueError()
"""
MERGING = """\
    result = []
    for start, end in sorted(tuple(pair) for pair in ranges):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result
"""
CORRECT = "def coalesce(ranges):\n" + VALIDATION + MERGING
CONTROLS = {
    "correct": CORRECT,
    "nonmerge": "def coalesce(ranges):\n"
    + VALIDATION
    + "    return sorted(tuple(pair) for pair in ranges)\n",
    "bool": CORRECT.replace(
        "type(pair[0]) is not int", "not isinstance(pair[0], int)"
    ).replace("type(pair[1]) is not int", "not isinstance(pair[1], int)"),
    "mutation": "def coalesce(ranges):\n"
    + VALIDATION
    + "    ranges.sort()\n"
    + MERGING,
    "constant": "def coalesce(ranges):\n" + VALIDATION + "    return []\n",
    "hang": "def coalesce(ranges):\n    while True:\n        pass\n",
    "spoof_globals": "def coalesce(ranges):\n    g = coalesce.__globals__\n    return []\n",
    "spoof_print": "def coalesce(ranges):\n    print('[]')\n    return []\n",
    "malformed": "def coalesce(:\n",
}


def test_real_assessor_controls():
    proof_path = Path(os.environ["ROUTING_ASSESSOR_ISOLATION_PROOF"]).resolve()
    proof_raw = proof_path.read_bytes()
    proof = strict_json(proof_raw, 16384)
    spec = AssessmentSpec(
        proof["actual_python_image"],
        "private-isolation-proof",
        True,
        17,
        isolation_path=proof_path,
        isolation_sha256=hashlib.sha256(proof_raw).hexdigest(),
        validator_sha256=GRAMMAR_SHA256,
        driver_sha256=hashlib.sha256(ASSESSOR_DRIVER.encode()).hexdigest(),
    )
    root = Path(os.environ["ROUTING_ASSESSOR_CONTROL_ROOT"]).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    registrar_script = Path(os.environ["ROUTING_ASSESSOR_REGISTRAR"])
    claim_script = registrar_script.parent / "lane_teardown.sh"
    batch = Path(os.environ["ROUTING_ASSESSOR_BATCH"])
    owner = os.environ["ROUTING_ASSESSOR_OWNER"]
    names = []

    def register(name):
        rc, _ = bounded_process(
            [
                str(registrar_script),
                str(batch),
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
        require(rc == 0, "assessor_registrar_refused")
        rc, _ = bounded_process(
            [str(claim_script), str(batch), owner, "claim", name],
            b"",
            10,
            4096,
        )
        require(rc == 0, "assessor_claim_refused")
        names.append(name)

    results = {}
    for label, source in CONTROLS.items():
        artifact = root / f"{label}.py"
        artifact.write_text(source)
        grade = grade_artifact(artifact, spec, staging_root=root, registrar=register)
        results[label] = grade.as_dict()
        assert grade.cleanup == "confirmed", label
        if label == "correct":
            assert grade.validity == "valid"
            assert len(grade.comparisons) == 48
            assert all(value == 1 for _, value in grade.awards)
            assert grade.critical == "pass"
        elif label in {"nonmerge", "bool", "mutation", "constant"}:
            assert grade.validity == "valid", (label, grade.blocker)
            assert any(value == 0 for _, value in grade.awards), label
            if label == "mutation":
                assert grade.critical == "fail"
        else:
            assert grade.validity == "invalid" and grade.awards == ()
            assert grade.critical == "unknown"
            assert grade.blocker == (
                "assessor_timeout" if label == "hang" else "artifact_restricted_grammar"
            )
    (root / "controls.json").write_text(
        json.dumps(
            {
                "results": results,
                "validator_sha256": GRAMMAR_SHA256,
                "driver_sha256": spec.driver_sha256,
                "image": spec.image,
                "case_count": 48,
                "owned_resource_names": names,
                "all_cleanup_confirmed": True,
            },
            sort_keys=True,
        )
    )
    assert len(names) == 6  # static refusals launch no resource
