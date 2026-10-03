"""Bounded offline experiment contracts. No evaluation/runtime imports or execution.

Hashes authenticate consistency, not the truth of an adapter's assertions.
All public reports are JSON-compatible; only plan() reads benchmark files.
"""

# Schema violations intentionally share ValueError at this library boundary.
# ruff: noqa: TRY004

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import random
import re
import statistics
from pathlib import Path, PurePosixPath

import yaml


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate or non-string mapping key")
        result[key] = value
    return result


def _yaml_mapping(loader, node):
    return _unique_pairs(
        (loader.construct_object(k), loader.construct_object(v)) for k, v in node.value
    )


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping
)


def _reject_constant(_):
    raise ValueError("nonfinite JSON number")


def read_json(path):
    """Strict normalized JSON only (not JSONL, raw events, or provider logs)."""
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_reject_constant,
    )


def fingerprint(value):
    """SHA256 of sorted, compact UTF-8 JSON; arrays preserve order."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _object(value, required, optional=()):
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError("expected mapping")
    if set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("unknown or missing fields")
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected nonempty string")
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise ValueError("invalid identifier")
    return value


def _number(value, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError("expected finite number in bounds")
    return value


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("expected integer in bounds")
    return value


def _enum(value, choices):
    if not isinstance(value, str) or value not in choices:
        raise ValueError("unsupported enum value")


def _hash(value, length=64):
    if not isinstance(value, str) or not re.fullmatch(f"[0-9a-f]{{{length}}}", value):
        raise ValueError("invalid SHA lock")


def _safe(value):
    """Reject non-JSON values, nonfinite numbers and recognizable secret values.

    Strict field schemas below disallow credential values/URLs/host overrides.
    This shape check is defense in depth, not a general-purpose secret scanner.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            _text(key)
            _safe(item)
    elif isinstance(value, list):
        for item in value:
            _safe(item)
    elif isinstance(value, str):
        if re.search(
            r"sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]+|"
            r"-----BEGIN .*PRIVATE KEY|/home/|/Users/|"
            r"(?i:api[_-]?key|password|secret)\s*=",
            value,
        ):
            raise ValueError("secret/private-path-shaped value not accepted")
    elif value is None or type(value) in (int, float, bool):
        if type(value) in (int, float) and not math.isfinite(value):
            raise ValueError("nonfinite value")
    else:
        raise ValueError("expected JSON-compatible value")


def _native(config):
    _object(
        config,
        (),
        ("reasoning_effort", "thinking_budget_tokens", "extra_request_params"),
    )
    if "reasoning_effort" in config:
        _enum(
            config["reasoning_effort"],
            ("none", "minimal", "low", "medium", "high", "xhigh", "max"),
        )
    if "thinking_budget_tokens" in config:
        _integer(config["thinking_budget_tokens"], 1)
    if "extra_request_params" in config:
        extra = _object(config["extra_request_params"], ("thinking_config",))
        thinking = _object(extra["thinking_config"], ("thinking_level",))
        _enum(thinking["thinking_level"], ("low", "medium", "high"))


def _identity(value):
    _object(value, ("backend", "model", "native_config"))
    _id(value["backend"])
    _id(value["model"])
    _native(value["native_config"])


def _preset_gate(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if "preset" in key.lower():
                raise ValueError("inheritance_observability: presets unsupported")
            _preset_gate(item)
    elif isinstance(value, list):
        for item in value:
            _preset_gate(item)


def _matrix(matrix):
    _preset_gate(matrix)
    _object(matrix, ("name", "description", "updated", "roles"))
    for key in ("name", "description", "updated"):
        _text(matrix[key])
    roles = matrix["roles"]
    if not isinstance(roles, dict) or not {"general", "fast"} <= set(roles):
        raise ValueError("matrix must include general and fast")
    for role, value in roles.items():
        _id(role)
        _object(value, ("description", "candidates"))
        _text(value["description"])
        candidates = value["candidates"]
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("expected nonempty candidates")
        for candidate in candidates:
            _object(candidate, ("provider", "model"), ("config",))
            _id(candidate["provider"])
            _text(candidate["model"])
            _native(candidate.get("config", {}))


def _treatment(manifest):
    arms = manifest["arms"]
    if not isinstance(arms, list) or len(arms) != 2:
        raise ValueError("exactly two ordered arms required")
    if [arm.get("id") if isinstance(arm, dict) else None for arm in arms] != [
        "baseline",
        "candidate",
    ]:
        raise ValueError("arms must be baseline, candidate in that order")
    matrices = []
    for arm in arms:
        _object(arm, ("id", "matrix", "matrix_sha256"))
        _matrix(arm["matrix"])
        _hash(arm["matrix_sha256"])
        if fingerprint(arm["matrix"]) != arm["matrix_sha256"]:
            raise ValueError("matrix_sha256 mismatch")
        matrices.append(arm["matrix"])
    role = manifest["target_role"]
    _id(role)
    if any(role not in matrix["roles"] for matrix in matrices):
        raise ValueError("target role absent")
    originals = [matrix["roles"][role]["candidates"][0] for matrix in matrices]
    for candidate in originals:
        if candidate["provider"] != "openai":
            raise ValueError("only primary exact OpenAI candidate supported")
        if re.search(r"[*?\[\]]", candidate["model"]):
            raise ValueError("changed-candidate globs unsupported")
        if set(candidate.get("config", {})) != {"reasoning_effort"}:
            raise ValueError("explicit native effort required; no inherited knobs")
    left, right = copy.deepcopy(matrices)
    a = left["roles"][role]["candidates"][0]
    b = right["roles"][role]["candidates"][0]
    if manifest["estimand"] == "model":
        if a["model"] == b["model"]:
            raise ValueError("model treatment must change a leaf")
        b["model"] = a["model"]
    else:
        if a["config"]["reasoning_effort"] == b["config"]["reasoning_effort"]:
            raise ValueError("effort treatment must change a leaf")
        b["config"]["reasoning_effort"] = a["config"]["reasoning_effort"]
    if left != right:
        raise ValueError("only one primary model OR effort leaf may differ")
    return {
        arm["id"]: {
            "backend": "openai",
            "model": candidate["model"],
            "native_config": copy.deepcopy(candidate["config"]),
        }
        for arm, candidate in zip(arms, originals)
    }


CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".cache"}


def _no_symlinks(path):
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlinks unsupported")


def task_tree_hash(task_dir):
    """Hash every relative file path + file SHA256, except generated caches.

    Binary fixtures are hashed as bytes, never parsed. Symlinks are rejected,
    including links hidden in excluded caches. Empty directories do not count.
    """
    root = Path(task_dir).absolute()
    _no_symlinks(root)
    if not root.is_dir():
        raise ValueError("task directory missing")
    entries = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            if (Path(directory) / name).is_symlink():
                raise ValueError("symlinks unsupported")
        # Visit caches too, to check links; exclude their files from the digest.
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root)
            if CACHE_DIRS.intersection(relative.parts) or path.suffix in (
                ".pyc",
                ".pyo",
            ):
                continue
            if not path.is_file():
                raise ValueError("nonregular task file")
            entries.append(
                {
                    "path": relative.as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return fingerprint(sorted(entries, key=lambda item: item["path"]))


def _yaml(path):
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(value, dict):
        raise ValueError("benchmark YAML must be a mapping")
    return value


def _load_task(root, task):
    """Pure loader matching load_task's metadata ID and instructions contract.

    Deliberately does not import amplifier_evaluation. The independent integration
    check can compare these fields with harness.loaders.load_task at its pin.
    """
    path = task["path"]
    if not isinstance(path, str):
        raise ValueError("task path must be relative")
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in path or path == ".":
        raise ValueError("task path must be portable and confined")
    directory = Path(root).absolute() / relative
    _no_symlinks(directory)
    for name in ("meta.yaml", "task.yaml", "profile.yaml", "grader.yaml"):
        if not (directory / name).is_file():
            raise ValueError("required task file missing")
    if task_tree_hash(directory) != task["sha256"]:
        raise ValueError("task sha256 mismatch")
    meta = _yaml(directory / "meta.yaml")
    task_data = _yaml(directory / "task.yaml")
    _yaml(directory / "profile.yaml")
    _text(task_data.get("instructions"))
    actual_id = str(meta.get("name", directory.name))
    if actual_id != task["id"]:
        raise ValueError("task metadata ID mismatch")
    timeout = _integer(meta.get("timeout", 3600), 1)
    grader_bytes = (directory / "grader.yaml").read_bytes()
    rubric_hash = hashlib.sha256(grader_bytes).hexdigest()
    if rubric_hash != task["rubric_sha256"]:
        raise ValueError("rubric_sha256 mismatch")
    grader = _yaml(directory / "grader.yaml")
    _object(grader, ("evaluations",))
    evaluations = grader["evaluations"]
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("grader evaluations missing")
    criteria, groups, seen = [], [], set()
    for evaluation in evaluations:
        _object(evaluation, ("name", "weight", "steps", "rubric"), ("mounts",))
        name = _id(evaluation["name"])
        if name in seen:
            raise ValueError("duplicate evaluation name")
        seen.add(name)
        weight = _number(evaluation["weight"])
        _text(evaluation["steps"])
        rubric = evaluation["rubric"]
        if not isinstance(rubric, dict) or not rubric:
            raise ValueError("empty rubric")
        group = []
        for key, criterion in rubric.items():
            _id(key)
            _object(criterion, ("points", "description"))
            maximum = _number(criterion["points"])
            if maximum == 0:
                raise ValueError("zero-point criterion unsupported")
            _text(criterion["description"])
            identity = name + "." + key
            criteria.append({"id": identity, "min": 0, "max": maximum})
            group.append(identity)
        groups.append({"weight": weight, "criteria": group})
    if len({item["id"] for item in criteria}) != len(criteria):
        raise ValueError("duplicate criterion identity")
    if sum(group["weight"] for group in groups) <= 0:
        raise ValueError("grader weights must have positive total")
    # Bounds are locked from the existing rubric, not supplied arbitrary scores.
    if task["required_criteria"] != criteria:
        raise ValueError("complete grader criterion identities/bounds must match")
    text = grader_bytes.decode("utf-8")
    flags = []
    for code, pattern in (
        ("unresolved_rubric_reference", r"\{\{.*?\}\}"),
        ("time_sensitive_year", r"\b20\d\d\b"),
        ("recency", r"(?i)recent|up.to.date"),
        ("live_url", r"(?i)https?://|HTTP requests|URLs.*accessible"),
        ("model_choice", r"(?i)uses_recent_model|model identifier|recent model"),
    ):
        if re.search(pattern, text, re.DOTALL):
            flags.append(code)
    if re.search(r"(?i)recall|discrepanc|false.positive", text) and not task.get(
        "false_positive_policy"
    ):
        raise ValueError("explicit false_positive_policy required")
    return {
        "id": actual_id,
        "timeout_s": timeout,
        "criteria": criteria,
        "groups": groups,
        "rubric_sha256": rubric_hash,
        "audit_flags": flags,
    }


def _rules(task):
    criteria = task["required_criteria"]
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("required criteria missing")
    bounds = {}
    for item in criteria:
        _object(item, ("id", "min", "max"))
        identity = _id(item["id"])
        low, high = _number(item["min"]), _number(item["max"])
        if high <= low or identity in bounds:
            raise ValueError("bad criterion bounds/duplicate identity")
        bounds[identity] = (low, high)
    for key in ("success_rule", "critical_rule"):
        rule = _object(task[key], ("minimum_awards",))
        thresholds = rule["minimum_awards"]
        if not isinstance(thresholds, dict) or set(thresholds) - set(bounds):
            raise ValueError("rule references unknown criterion")
        if key == "success_rule" and set(thresholds) != set(bounds):
            raise ValueError("success rule must cover all target criteria")
        for identity, threshold in thresholds.items():
            if not bounds[identity][0] <= _number(threshold) <= bounds[identity][1]:
                raise ValueError("rule threshold out of bounds")


def plan(manifest, benchmark_root) -> dict:
    """Validate locks and build a seeded, balanced, paired exploratory schedule."""
    _safe(manifest)
    _object(
        manifest,
        (
            "version",
            "synthetic",
            "stage",
            "hypothesis",
            "estimand",
            "target_role",
            "sources",
            "root",
            "backend_topology",
            "credential_env_names",
            "evaluator",
            "seed",
            "repetitions",
            "budgets",
            "tasks",
            "arms",
        ),
    )
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("manifest version must be 1")
    if type(manifest["synthetic"]) is not bool:
        raise ValueError("synthetic must be explicit boolean")
    _enum(manifest["stage"], ("exploratory",))
    _text(manifest["hypothesis"])
    _enum(manifest["estimand"], ("model", "effort"))
    _integer(manifest["seed"])
    repetitions = _integer(manifest["repetitions"], 1)
    _identity(manifest["root"])
    topology = manifest["backend_topology"]
    if not isinstance(topology, list) or not topology:
        raise ValueError("shared topology required")
    mounts, backends = set(), set()
    for item in topology:
        _object(item, ("mount", "backend"))
        mount, backend = _id(item["mount"]), _id(item["backend"])
        if mount in mounts or backend in backends or mount != backend:
            raise ValueError("only unique exact backend mounts supported")
        mounts.add(mount)
        backends.add(backend)
    if "openai" not in backends or manifest["root"]["backend"] not in backends:
        raise ValueError("root/target backend missing")
    sources = manifest["sources"]
    _object(
        sources,
        (
            "cli",
            "core",
            "foundation",
            "routing",
            "evaluation",
            *("provider-" + backend for backend in sorted(backends)),
        ),
    )
    for sha in sources.values():
        _hash(sha, 40)
    credentials = manifest["credential_env_names"]
    if not isinstance(credentials, list):
        raise ValueError("credential_env_names must be names only")
    for name in credentials:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError("credential variable name required, never its value")
    if len(set(credentials)) != len(credentials):
        raise ValueError("credential_env_names must be unique")
    _object(manifest["evaluator"], ("driver", "extractor", "judge"))
    for evaluator in manifest["evaluator"].values():
        _object(
            evaluator,
            (
                "backend",
                "model",
                "native_config",
                "source",
                "protocol_sha256",
                "config_sha256",
            ),
        )
        _identity(
            {key: evaluator[key] for key in ("backend", "model", "native_config")}
        )
        if evaluator["source"] != "evaluation" or evaluator["backend"] not in backends:
            raise ValueError("evaluator must use pinned evaluation source/backend")
        for key in ("protocol_sha256", "config_sha256"):
            _hash(evaluator[key])
        if evaluator["config_sha256"] != fingerprint(
            {key: value for key, value in evaluator.items() if key != "config_sha256"}
        ):
            raise ValueError("evaluator config_sha256 mismatch")
    budgets = _object(
        manifest["budgets"],
        (
            "subject_tokens",
            "time_s",
            "subject_usd",
            "evaluation_usd",
            "application_usd",
        ),
    )
    for value in budgets.values():
        if value is not None:
            _number(value)
    expected = _treatment(manifest)
    for arm in manifest["arms"]:
        for role in arm["matrix"]["roles"].values():
            for candidate in role["candidates"]:
                if candidate["provider"] not in mounts:
                    raise ValueError("matrix provider absent from shared topology")
    tasks = manifest["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("nonempty task portfolio required")
    resolved, task_ids, task_paths = [], set(), set()
    warnings, blockers = [], []
    for task in tasks:
        _object(
            task,
            (
                "id",
                "path",
                "split",
                "sha256",
                "rubric_sha256",
                "required_criteria",
                "success_rule",
                "critical_rule",
            ),
            ("false_positive_policy",),
        )
        _id(task["id"])
        _text(task["path"])
        _enum(task["split"], ("development", "heldout"))
        if task["id"] in task_ids or task["path"] in task_paths:
            raise ValueError("duplicate task ID/path")
        task_ids.add(task["id"])
        task_paths.add(task["path"])
        for key in ("sha256", "rubric_sha256"):
            _hash(task[key])
        if "false_positive_policy" in task:
            _text(task["false_positive_policy"])
        _rules(task)
        loaded = _load_task(benchmark_root, task)
        resolved.append(loaded)
        for flag in loaded["audit_flags"]:
            warning = {"task_id": task["id"], "code": flag, "requires_followup": True}
            warnings.append(warning)
            if flag == "unresolved_rubric_reference":
                blockers.append(warning)
    frozen = copy.deepcopy(manifest)
    manifest_hash = fingerprint(frozen)
    blocks = [
        (task, repeat) for task in resolved for repeat in range(1, repetitions + 1)
    ]
    firsts = [i % 2 for i in range(len(blocks))]
    random.Random(manifest["seed"]).shuffle(firsts)
    schedule = []
    for (task, repeat), first in zip(blocks, firsts):
        pair_id = fingerprint(
            {"manifest_sha256": manifest_hash, "task_id": task["id"], "repeat": repeat}
        )
        for order, arm_id in enumerate(
            ("baseline", "candidate") if first == 0 else ("candidate", "baseline"), 1
        ):
            arm = manifest["arms"][0 if arm_id == "baseline" else 1]
            locked_task = next(item for item in tasks if item["id"] == task["id"])
            schedule.append(
                {
                    "cell_id": fingerprint({"pair_id": pair_id, "arm_id": arm_id}),
                    "pair_id": pair_id,
                    "arm_id": arm_id,
                    "task_id": task["id"],
                    "repeat": repeat,
                    "arm_order": order,
                    "matrix_sha256": arm["matrix_sha256"],
                    "task_sha256": locked_task["sha256"],
                    "rubric_sha256": task["rubric_sha256"],
                    "sources_sha256": fingerprint(manifest["sources"]),
                    "agent_timeout_s": task["timeout_s"],
                }
            )
    result = {
        "version": 1,
        "manifest": frozen,
        "manifest_sha256": manifest_hash,
        "expected_target_calls": expected,
        "tasks": resolved,
        "schedule": schedule,
        "trial_count": len(schedule),
        "warnings": warnings,
        "rubric_blockers": blockers,
        "budgets_enforced": False,
        "agent_stage_ceiling_s": sum(cell["agent_timeout_s"] for cell in schedule),
        "agent_stage_ceiling_hours": sum(cell["agent_timeout_s"] for cell in schedule)
        / 3600,
        "limits": [
            "Exploratory, unqualified task rubrics; no model ranking or promotion.",
            "Agent-stage ceiling excludes setup, controller, grading and cleanup.",
            "Source/evaluator locks are declared identities, not verified installations.",
            "Only primary preset-free OpenAI model/effort leaves are supported.",
            "No explicit slice pins, inherited knobs, fallback changes or live execution.",
        ],
    }
    result["plan_sha256"] = fingerprint(result)
    return result


def _check_plan(value):
    if not isinstance(value, dict) or "plan_sha256" not in value:
        raise ValueError("expected a plan")
    if (
        fingerprint({k: v for k, v in value.items() if k != "plan_sha256"})
        != value["plan_sha256"]
    ):
        raise ValueError("plan_sha256 mismatch")


def readiness(run_plan) -> dict:
    """Plan validity is distinct from execution support (always unsupported)."""
    _check_plan(run_plan)
    return {
        "plan_valid": True,
        "plan_sha256": run_plan["plan_sha256"],
        "execution_supported": False,
        "ready": False,
        "blockers": [
            "execution_unsupported",
            "pricing_and_whole_lifecycle_budget_enforcement_pending",
            "instrumentation_and_adapter_calibration_pending",
            "graded_rubric_qualification_and_blinding_pending",
        ]
        + run_plan["rubric_blockers"],
        "warnings": run_plan["warnings"],
        "credential_values_checked": False,
    }


def _record(record, run_plan, cell, task, attempts_seen, calls_seen):
    _safe(record)
    _object(
        record,
        (
            "synthetic",
            "plan_sha256",
            "cell_id",
            "attempt_id",
            "matrix_sha256",
            "task_sha256",
            "rubric_sha256",
            "sources_sha256",
            "setup",
            "outcome",
            "outcome_evidence_ids",
            "treatment",
            "actual_target_calls",
            "grade",
            "elapsed_s",
            "cost",
            "cleanup",
        ),
    )
    if (
        type(record["synthetic"]) is not bool
        or record["synthetic"] != run_plan["manifest"]["synthetic"]
    ):
        raise ValueError("synthetic provenance mismatch")
    if record["plan_sha256"] != run_plan["plan_sha256"]:
        raise ValueError("cross-plan evidence")
    for key in ("matrix_sha256", "task_sha256", "rubric_sha256", "sources_sha256"):
        if record[key] != cell[key]:
            raise ValueError("evidence lock mismatch")
    attempt_id = _id(record["attempt_id"])
    if attempt_id in attempts_seen:
        raise ValueError("duplicate attempt_id")
    attempts_seen.add(attempt_id)
    for key in ("setup", "treatment"):
        _enum(record[key], ("valid", "invalid", "unknown"))
    _enum(record["outcome"], ("success", "failure", "timeout", "unknown"))
    _enum(record["cleanup"], ("confirmed", "unconfirmed"))
    _number(record["elapsed_s"])
    receipts = record["outcome_evidence_ids"]
    if not isinstance(receipts, list):
        raise ValueError("outcome_evidence_ids must be an array")
    for receipt in receipts:
        _id(receipt)
    if len(set(receipts)) != len(receipts):
        raise ValueError("duplicate outcome evidence ID")
    calls = record["actual_target_calls"]
    if not isinstance(calls, list):
        raise ValueError("actual_target_calls must be an array")
    expected = run_plan["expected_target_calls"][cell["arm_id"]]
    for call in calls:
        _object(call, ("id", "actual_role", "backend", "model", "native_config"))
        call_id = _id(call["id"])
        if call_id in calls_seen:
            raise ValueError("duplicate call ID")
        calls_seen.add(call_id)
        _id(call["actual_role"])
        _identity({k: call[k] for k in ("backend", "model", "native_config")})
    if record["treatment"] == "valid" and (
        not calls
        or any(
            call["actual_role"] != run_plan["manifest"]["target_role"]
            or any(call[key] != expected[key] for key in expected)
            for call in calls
        )
    ):
        raise ValueError("valid treatment requires exact actual target-role exposure")
    grade = _object(
        record["grade"], ("validity", "rubric_sha256", "criteria", "critical")
    )
    _enum(grade["validity"], ("valid", "invalid", "missing"))
    _enum(grade["critical"], ("pass", "fail", "unknown"))
    if grade["rubric_sha256"] != cell["rubric_sha256"]:
        raise ValueError("grade rubric_sha256 mismatch")
    awards = grade["criteria"]
    if not isinstance(awards, dict):
        raise ValueError("criteria awards must be a mapping")
    bounds = {item["id"]: item for item in task["required_criteria"]}
    if set(awards) - set(bounds):
        raise ValueError("unknown criterion identity")
    for identity, award in awards.items():
        if not bounds[identity]["min"] <= _number(award) <= bounds[identity]["max"]:
            raise ValueError("criterion award out of bounds")
    if grade["validity"] == "valid" and set(awards) != set(bounds):
        raise ValueError("valid grade must contain every exact criterion")
    if grade["validity"] == "missing" and (awards or grade["critical"] != "unknown"):
        raise ValueError("missing grade cannot assert awards or critical pass/fail")
    if grade["validity"] == "invalid" and grade["critical"] != "unknown":
        raise ValueError("invalid grade cannot establish critical pass/fail")
    if grade["validity"] == "valid" and grade["critical"] != "unknown":
        passes = all(
            awards[key] >= minimum
            for key, minimum in task["critical_rule"]["minimum_awards"].items()
        )
        if (grade["critical"] == "pass") != passes:
            raise ValueError("critical receipt conflicts with declared rule")
    cost = _object(
        record["cost"], ("coverage", "subject_usd", "evaluation_usd", "application_usd")
    )
    _enum(cost["coverage"], ("measured", "unknown"))
    for key in ("subject_usd", "evaluation_usd", "application_usd"):
        if cost[key] is not None:
            _number(cost[key])
    if cost["coverage"] == "measured" and any(
        cost[key] is None
        for key in ("subject_usd", "evaluation_usd", "application_usd")
    ):
        raise ValueError("measured cost requires all three components")


def _costs(attempts, scheduled_count, missing_cells):
    components = ("subject_usd", "evaluation_usd", "application_usd")
    complete = bool(attempts) and all(
        attempt["cost"]["coverage"] == "measured" for attempt in attempts
    )
    report = {
        "attempt_count": len(attempts),
        "fully_measured_attempts": sum(
            attempt["cost"]["coverage"] == "measured" for attempt in attempts
        ),
        "scheduled_cells": scheduled_count,
        "components": {},
    }
    for key in components:
        known = [a["cost"][key] for a in attempts if a["cost"][key] is not None]
        report["components"][key] = {
            "known_attempts": len(known),
            "unknown_attempts": len(attempts) - len(known),
            "measured_total_usd": sum(known) if known else None,
            "lower_bound": not complete or bool(missing_cells),
        }
    report["all_attempt_components_covered"] = complete
    report["total_usd"] = (
        sum(sum(a["cost"][key] for key in components) for a in attempts)
        if complete
        else None
    )
    return report


def analyze(run_plan, records) -> dict:
    """Reconcile every scheduled cell; never choose a best attempt or fill zeros."""
    _check_plan(run_plan)
    if not isinstance(records, list):
        raise ValueError("normalized evidence must be a JSON array of attempts")
    cells = {cell["cell_id"]: cell for cell in run_plan["schedule"]}
    tasks = {task["id"]: task for task in run_plan["manifest"]["tasks"]}
    resolved = {task["id"]: task for task in run_plan["tasks"]}
    grouped = {identity: [] for identity in cells}
    attempts_seen, calls_seen = set(), set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("cell_id"), str):
            raise ValueError("record cell_id required")
        if record["cell_id"] not in cells:
            raise ValueError("unscheduled cell_id")
        cell = cells[record["cell_id"]]
        _record(
            record, run_plan, cell, tasks[cell["task_id"]], attempts_seen, calls_seen
        )
        grouped[record["cell_id"]].append(copy.deepcopy(record))
    rows = []
    for cell in run_plan["schedule"]:
        attempts = grouped[cell["cell_id"]]
        row = {
            **cell,
            "attempts": attempts,
            "attempt_count": len(attempts),
            "cell_status": "missing"
            if not attempts
            else ("multiple_attempts_blocked" if len(attempts) != 1 else "observed"),
            "completion": "unknown",
            "quality_eligible": False,
            "attribution_eligible": False,
            "upstream_score": None,
            "critical_failures": sum(
                a["grade"]["critical"] == "fail" for a in attempts
            ),
            "cleanup_unconfirmed_attempts": sum(
                a["cleanup"] == "unconfirmed" for a in attempts
            ),
        }
        if len(attempts) == 1:
            attempt = attempts[0]
            task = tasks[cell["task_id"]]
            grade = attempt["grade"]
            outcome_verified = attempt["setup"] == "valid" and bool(
                attempt["outcome_evidence_ids"]
            )
            row["quality_eligible"] = (
                attempt["setup"] == "valid" and grade["validity"] == "valid"
            )
            row["attribution_eligible"] = attempt["treatment"] == "valid"
            if outcome_verified and attempt["outcome"] in ("failure", "timeout"):
                row["completion"] = "failure"
            elif (
                outcome_verified
                and attempt["outcome"] == "success"
                and grade["validity"] == "valid"
            ):
                success_thresholds_met = all(
                    grade["criteria"][key] >= minimum
                    for key, minimum in task["success_rule"]["minimum_awards"].items()
                )
                if grade["critical"] == "fail" or not success_thresholds_met:
                    row["completion"] = "failure"
                elif grade["critical"] == "pass":
                    row["completion"] = "success"
            if row["quality_eligible"]:
                bounds = {c["id"]: c["max"] for c in task["required_criteria"]}
                groups = resolved[cell["task_id"]]["groups"]
                row["upstream_score"] = (
                    100
                    * sum(
                        group["weight"]
                        * sum(grade["criteria"][key] for key in group["criteria"])
                        / sum(bounds[key] for key in group["criteria"])
                        for group in groups
                    )
                    / sum(group["weight"] for group in groups)
                )
        rows.append(row)
    arms = {}
    for arm_id in ("baseline", "candidate"):
        arm_rows = [row for row in rows if row["arm_id"] == arm_id]
        attempts = [a for row in arm_rows for a in row["attempts"]]
        counts = {
            status: sum(row["completion"] == status for row in arm_rows)
            for status in ("success", "failure", "unknown")
        }
        durations = [a["elapsed_s"] for a in attempts]
        denominator = len(arm_rows)
        arms[arm_id] = {
            "scheduled_cells": denominator,
            "completion": counts,
            "completion_rate_bounds": [
                counts["success"] / denominator,
                (counts["success"] + counts["unknown"]) / denominator,
            ],
            "missing_cells": sum(row["cell_status"] == "missing" for row in arm_rows),
            "multiple_attempt_cells": sum(
                row["cell_status"] == "multiple_attempts_blocked" for row in arm_rows
            ),
            "quality_eligible_cells": sum(row["quality_eligible"] for row in arm_rows),
            "missing_treatment_cells": sum(
                not row["attribution_eligible"] for row in arm_rows
            ),
            "critical_failures": sum(row["critical_failures"] for row in arm_rows),
            "cleanup_unconfirmed_attempts": sum(
                row["cleanup_unconfirmed_attempts"] for row in arm_rows
            ),
            "observed_attempt_duration_s": {
                "count": len(durations),
                "median": statistics.median(durations) if durations else None,
                "max": max(durations) if durations else None,
            },
            "cost": _costs(
                attempts,
                denominator,
                sum(row["cell_status"] == "missing" for row in arm_rows),
            ),
        }
    paired = []
    for task_id, task in tasks.items():
        differences = []
        for repeat in range(1, run_plan["manifest"]["repetitions"] + 1):
            pair = [
                row
                for row in rows
                if row["task_id"] == task_id and row["repeat"] == repeat
            ]
            if all(
                row["quality_eligible"] and row["attribution_eligible"] for row in pair
            ):
                baseline = next(row for row in pair if row["arm_id"] == "baseline")
                candidate = next(row for row in pair if row["arm_id"] == "candidate")
                differences.append(
                    {
                        "repeat": repeat,
                        "pair_id": baseline["pair_id"],
                        "candidate_minus_baseline_upstream_score": candidate[
                            "upstream_score"
                        ]
                        - baseline["upstream_score"],
                        "criterion_differences": {
                            c["id"]: candidate["attempts"][0]["grade"]["criteria"][
                                c["id"]
                            ]
                            - baseline["attempts"][0]["grade"]["criteria"][c["id"]]
                            for c in task["required_criteria"]
                        },
                    }
                )
        denominator = run_plan["manifest"]["repetitions"]
        paired.append(
            {
                "task_id": task_id,
                "scheduled_pairs": denominator,
                "complete_pairs": len(differences),
                "missing_or_ineligible_pairs": denominator - len(differences),
                "differences": differences,
            }
        )
    usd_comparable = all(
        arms[arm]["cost"]["all_attempt_components_covered"]
        and not arms[arm]["missing_cells"]
        and not arms[arm]["multiple_attempt_cells"]
        for arm in arms
    )
    return {
        "plan_sha256": run_plan["plan_sha256"],
        "synthetic": run_plan["manifest"]["synthetic"],
        "promotional": False,
        "cells": rows,
        "arms": arms,
        "paired_tasks": paired,
        "usd_comparison_eligible": usd_comparable,
        "cleanup_ready": bool(records)
        and all(a["cleanup"] == "confirmed" for a in records)
        and all(row["cell_status"] != "missing" for row in rows),
        "unsupported_limits": [
            "No execution or authenticated call receipts; adapter assertions only.",
            "No retry policy: all multi-attempt cells are blocked, all costs retained.",
            "No rankings, winner, promotion, confidence intervals or noninferiority.",
            "No population inference, p95, live price lookup or budget enforcement.",
            "Upstream weighted scores are descriptive, not qualified decision rubrics.",
            "Missing treatment blocks attribution, not arm-specific outcome reporting.",
            "Missing cost is unknown, never zero; partial totals are lower bounds.",
        ],
    }
