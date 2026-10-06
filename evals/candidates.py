"""Bounded catalog discovery and private, asserted reuse planning; no executor.

``family_masks`` names caller-declared family/tier/modality cells. Numeric ID
versions are compared only within the same nonnumeric ID shape and advertised
modality, never across tiers. "Latest" means within this bounded supplied catalog,
not globally newest, entitled, or quality-qualified. No trial model is preselected.

Assigned conditions have exactly sources/task/grader/runtime/root/tools/
native_settings/budgets/model_revisions/binding_ref. Task includes fixture identity;
root includes fixed controller/protocol identity. Sources and tools are complete
caller-declared name -> revision maps, not discovered installation/config hashes.
The comparison projection excludes treatment (model_revisions/binding_ref);
delivered revision and exact binding are checked separately for each receipt.
Unknown identities are null, not aliases disguised as verified revisions.

Receipts use anchors-reuse/v1 and are assertions, not authenticated evidence.
Outcome/score are retained but NEVER used to select reuse. Regrade is old output,
not fresh execution. Binding references, conditions and receipt lookup IDs remain
private: serialization is for caller-controlled storage, not publication.
"""

from __future__ import annotations

import asyncio
import copy
import fnmatch
import math
import re
from dataclasses import dataclass, field
from typing import Any

MAX_MASKS = 8
MAX_MODELS = 64
DISCOVERY_TIMEOUT_S = 30
SNAPSHOT_VERSION = "anchors-candidates/v1"
RECEIPT_VERSION = "anchors-reuse/v1"
PROVENANCES = frozenset({"live", "fallback", "manual", "failed"})
DISPOSITIONS = (
    "exact_comparable",
    "regrade",
    "accounting_only",
    "historical",
    "rerun",
)
PROJECTION_FIELDS = (
    "sources",
    "task",
    "grader",
    "runtime",
    "root",
    "tools",
    "native_settings",
    "budgets",
)
CONDITION_FIELDS = {*PROJECTION_FIELDS, "model_revisions", "binding_ref"}
RECEIPT_FIELDS = {
    "version",
    "receipt_id",
    "model_id",
    "model_revision",
    "binding_ref",
    "assigned_conditions",
    "identity_verified",
    "qualified",
    "measurement_valid",
    "artifacts_retained",
    "references_available",
    "accounting_complete",
    "outcome",
    "score",
}
MODALITIES = frozenset(
    {
        "vision",
        "image_generation",
        "image-gen",
        "image_input",
        "image_output",
        "audio",
        "audio_input",
        "audio_output",
    }
)
REASONS = frozenset(
    {
        "complete",
        "nonlive",
        "empty_catalog",
        "no_candidates",
        "binding_unknown",
        "catalog_failed",
        "catalog_limit",
        "invalid_catalog",
    }
)


def _fields(value: Any, fields: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("unexpected or missing fields")


def _text(value: Any, *, unknown: bool = False) -> None:
    if unknown and value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError("invalid identity")


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected string sequence")
    for item in value:
        _text(item)
    if len(set(value)) != len(value):
        raise ValueError("duplicate strings")
    return tuple(sorted(value))


def _masks(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or not 1 <= len(value) <= MAX_MASKS:
        raise ValueError("expected one to eight family masks")
    for family, mask in value.items():
        _text(family)
        _text(mask)
        if not re.search(r"[a-zA-Z]", mask):
            raise ValueError("unbounded family mask")
    return tuple(sorted(value.items()))


def _version(model_id: str) -> tuple[str, tuple[int, ...] | None, str]:
    """Separate dated revisions from generations; normalize version placement."""
    dated = re.search(r"[-@](20[0-9]{6}|20[0-9]{2}-[0-9]{2}-[0-9]{2})$", model_id)
    release = dated[1].replace("-", "") if dated else ""
    base = model_id[: dated.start()] if dated else model_id
    match = re.search(r"(?<![a-zA-Z0-9])([0-9]+(?:[.-][0-9]+)*)(?![a-zA-Z0-9])", base)
    if match is None:
        return base, None, release
    parts = tuple(int(part) for part in re.split(r"[.-]", match[1]))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    shape = base[: match.start()] + base[match.end() :]
    # Claude moved the version before/after the tier without changing the family.
    shape = re.sub(r"-+", "-", shape).strip("-").removesuffix("-preview")
    return shape, parts, release


@dataclass(frozen=True)
class Candidate:
    family: str
    id: str
    capabilities: tuple[str, ...]
    latest: bool | None

    def __post_init__(self) -> None:
        _text(self.family)
        _text(self.id)
        object.__setattr__(self, "capabilities", _strings(self.capabilities))
        if self.latest is not None and self.latest is not True:
            raise ValueError("latest must be true or unknown")
        if self.latest is True and _version(self.id)[1] is None:
            raise ValueError("unversioned identity cannot establish latest")


@dataclass(frozen=True)
class Snapshot:
    family_masks: tuple[tuple[str, str], ...]
    required_capabilities: tuple[str, ...]
    provenance: str
    freshness: str
    reason: str
    candidates: tuple[Candidate, ...]
    binding_ref: str | None = field(repr=False)
    version: str = SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        if self.version != SNAPSHOT_VERSION:
            raise ValueError("unsupported snapshot version")
        _text(self.binding_ref, unknown=True)
        for value in (self.provenance, self.reason, self.freshness):
            _text(value)
        if self.provenance not in PROVENANCES or self.reason not in REASONS:
            raise ValueError("invalid discovery provenance")
        masks = dict(self.family_masks)
        if len(masks) != len(self.family_masks):
            raise ValueError("duplicate family masks")
        object.__setattr__(self, "family_masks", _masks(masks))
        object.__setattr__(
            self, "required_capabilities", _strings(self.required_capabilities)
        )
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if self.freshness not in {"bounded_live", "unknown"}:
            raise ValueError("invalid freshness")
        if self.freshness == "bounded_live" and (
            self.provenance != "live"
            or self.reason != "complete"
            or self.binding_ref is None
            or not self.candidates
        ):
            raise ValueError("freshness needs live bound evidence")
        if self.reason == "complete" and self.freshness != "bounded_live":
            raise ValueError("inconsistent completeness")
        failure_reason = self.reason in {
            "catalog_failed",
            "catalog_limit",
            "invalid_catalog",
        }
        if failure_reason != (self.provenance == "failed"):
            raise ValueError("inconsistent failure provenance")
        if self.reason == "nonlive" and self.provenance not in {"manual", "fallback"}:
            raise ValueError("inconsistent nonlive provenance")
        if self.reason == "binding_unknown" and (
            self.provenance != "live" or self.binding_ref is not None
        ):
            raise ValueError("inconsistent binding evidence")
        if self.reason in {"empty_catalog", "no_candidates"} and self.candidates:
            raise ValueError("empty discovery cannot supply candidates")
        if self.provenance == "failed" and self.candidates:
            raise ValueError("failed discovery cannot supply candidates")
        if len(self.candidates) > MAX_MODELS:
            raise ValueError("candidate limit exceeded")
        seen = set()
        groups = set()
        for candidate in self.candidates:
            if not isinstance(candidate, Candidate):
                raise ValueError("invalid candidate")
            pair = (candidate.family, candidate.id)
            if pair in seen or candidate.family not in masks:
                raise ValueError("duplicate or undeclared candidate")
            seen.add(pair)
            if not fnmatch.fnmatchcase(candidate.id, masks[candidate.family]):
                raise ValueError("candidate outside family mask")
            if not set(self.required_capabilities) <= set(candidate.capabilities):
                raise ValueError("required capability not advertised")
            if self.freshness == "unknown" and candidate.latest is not None:
                raise ValueError("unknown discovery cannot establish latest")
            group = (
                candidate.family,
                _version(candidate.id)[0],
                tuple(cap for cap in candidate.capabilities if cap in MODALITIES),
            )
            if group in groups:
                raise ValueError("nonwinning historical candidate in snapshot")
            groups.add(group)

    def to_dict(self) -> dict:
        """PRIVATE persistence only; never print this envelope."""
        return {
            "version": self.version,
            "family_masks": dict(self.family_masks),
            "required_capabilities": list(self.required_capabilities),
            "provenance": self.provenance,
            "freshness": self.freshness,
            "reason": self.reason,
            "binding_ref": self.binding_ref,
            "candidates": [
                {
                    "family": candidate.family,
                    "id": candidate.id,
                    "capabilities": list(candidate.capabilities),
                    "latest": candidate.latest,
                }
                for candidate in self.candidates
            ],
        }

    @classmethod
    def from_dict(cls, value: dict) -> Snapshot:
        _fields(
            value,
            {
                "version",
                "family_masks",
                "required_capabilities",
                "provenance",
                "freshness",
                "reason",
                "binding_ref",
                "candidates",
            },
        )
        if not isinstance(value["candidates"], list):
            raise ValueError("invalid candidates")
        if len(value["candidates"]) > MAX_MODELS:
            raise ValueError("candidate limit exceeded")
        candidates = []
        for item in value["candidates"]:
            _fields(item, {"family", "id", "capabilities", "latest"})
            candidates.append(Candidate(**item))
        return cls(
            family_masks=_masks(value["family_masks"]),
            required_capabilities=_strings(value["required_capabilities"]),
            provenance=value["provenance"],
            freshness=value["freshness"],
            reason=value["reason"],
            candidates=tuple(candidates),
            binding_ref=value["binding_ref"],
            version=value["version"],
        )


async def discover(
    provider: Any,
    binding_ref: str | None,
    family_masks: dict[str, str],
    required_capabilities: tuple[str, ...],
    provenance: str,
) -> Snapshot:
    """Call ONLY the supplied object's list_models, once, with no client creation.

    The caller authorizes metadata access and attests live/fallback/manual
    provenance (including disabling Copilot/ChatGPT fallback for a live claim).
    This function cannot detect a provider lying about that provenance. Empty
    catalogs, including Azure/manual-deployment menus, always remain unknown.
    Oversized catalogs fail closed instead of truncating then claiming latest.
    """
    masks = _masks(family_masks)
    required = _strings(required_capabilities)
    _text(binding_ref, unknown=True)
    _text(provenance)
    if provenance not in PROVENANCES:
        raise ValueError("explicit discovery provenance required")

    def snapshot(reason, candidates=(), actual_provenance=provenance):
        fresh = "bounded_live" if reason == "complete" else "unknown"
        return Snapshot(
            masks, required, actual_provenance, fresh, reason, candidates, binding_ref
        )

    if provenance == "failed":
        return snapshot("catalog_failed")
    try:
        models = await asyncio.wait_for(
            provider.list_models(), timeout=DISCOVERY_TIMEOUT_S
        )
    except Exception:
        # Exception bodies and provider config may contain secrets/endpoint identity.
        return snapshot("catalog_failed", actual_provenance="failed")
    if not isinstance(models, (list, tuple)):
        return snapshot("invalid_catalog", actual_provenance="failed")
    if len(models) > MAX_MODELS:
        return snapshot("catalog_limit", actual_provenance="failed")
    if not models:
        return snapshot("empty_catalog")
    inventory = {}
    try:
        for model in models:
            # Core ModelInfo is pydantic, not a dict; never iterate/serialize config.
            model_id = model.get("id") if isinstance(model, dict) else model.id
            caps = (
                model.get("capabilities", [])
                if isinstance(model, dict)
                else getattr(model, "capabilities", [])
            )
            _text(model_id)
            caps = _strings(caps)
            if model_id in inventory and inventory[model_id] != caps:
                raise ValueError("conflicting duplicate model")
            inventory[model_id] = caps
    except Exception:
        return snapshot("invalid_catalog", actual_provenance="failed")
    winners = {}
    for family, mask in masks:
        for model_id, caps in inventory.items():
            if not fnmatch.fnmatchcase(model_id, mask) or not set(required) <= set(
                caps
            ):
                continue
            shape, version, release = _version(model_id)
            group = (family, shape, tuple(cap for cap in caps if cap in MODALITIES))
            # Equal-generation GA and preview are peers, with deterministic GA ties.
            preview = bool(re.search(r"-preview(?:[-@]20[0-9-]+)?$", model_id))
            rank = (version or (), not preview, release, model_id)
            if group not in winners or rank > winners[group][0]:
                winners[group] = (rank, model_id, caps)
    if len(winners) > MAX_MODELS:
        return snapshot("catalog_limit", actual_provenance="failed")
    if not winners:
        return snapshot("no_candidates")
    reason = (
        "nonlive"
        if provenance != "live"
        else "binding_unknown"
        if binding_ref is None
        else "complete"
    )
    candidates = tuple(
        Candidate(
            group[0],
            model_id,
            caps,
            True if reason == "complete" and rank[0] else None,
        )
        for group, (rank, model_id, caps) in sorted(winners.items())
    )
    return snapshot(reason, candidates)


def _json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("expected finite JSON data")


def _conditions(value: dict) -> dict:
    _fields(value, CONDITION_FIELDS)
    _json_value(value)
    for name in ("task", "grader", "runtime", "root", "binding_ref"):
        _text(value[name], unknown=True)
    for name in ("sources", "tools", "model_revisions"):
        mapping = value[name]
        if not isinstance(mapping, dict) or (name == "sources" and not mapping):
            raise ValueError("invalid revision map")
        for key, revision in mapping.items():
            _text(key)
            _text(revision, unknown=True)
    if not isinstance(value["native_settings"], dict):
        raise ValueError("invalid native settings")
    budgets = value["budgets"]
    if not isinstance(budgets, dict) or not budgets:
        raise ValueError("missing budget projection")
    for key, amount in budgets.items():
        _text(key)
        if amount is not None and (
            type(amount) not in (int, float)
            or (type(amount) is float and not math.isfinite(amount))
            or amount < 0
        ):
            raise ValueError("invalid assigned budget")
    return copy.deepcopy(value)


def assigned_projection(assigned_conditions: dict) -> dict:
    """Exact predeclared assignment, excluding treatment and all observations."""
    conditions = _conditions(assigned_conditions)
    return {key: conditions[key] for key in PROJECTION_FIELDS}


def validate_receipt(receipt: dict) -> dict:
    """Validate a private v1 assertion; retain losing outcomes and unknown scores."""
    _fields(receipt, RECEIPT_FIELDS)
    if receipt["version"] != RECEIPT_VERSION:
        raise ValueError("unsupported reuse receipt version")
    for key in ("receipt_id", "model_id"):
        _text(receipt[key])
    for key in ("model_revision", "binding_ref"):
        _text(receipt[key], unknown=True)
    _conditions(receipt["assigned_conditions"])
    for key in (
        "identity_verified",
        "qualified",
        "measurement_valid",
        "artifacts_retained",
        "references_available",
        "accounting_complete",
    ):
        if type(receipt[key]) is not bool:
            raise ValueError("expected explicit evidence status")
    _text(receipt["outcome"])
    if receipt["outcome"] not in {"success", "failure", "timeout", "unknown"}:
        raise ValueError("invalid outcome")
    score = receipt["score"]
    if score is not None and (
        type(score) not in (int, float)
        or (type(score) is float and not math.isfinite(score))
    ):
        raise ValueError("invalid score")
    return copy.deepcopy(receipt)


def _known_projection(conditions: dict) -> bool:
    return (
        all(
            conditions[key] is not None for key in ("task", "grader", "runtime", "root")
        )
        and all(value is not None for value in conditions["sources"].values())
        and all(value is not None for value in conditions["tools"].values())
        and all(value is not None for value in conditions["budgets"].values())
    )


def reuse_disposition(receipt: dict, assigned_conditions: dict) -> str:
    """Classify assignment/fidelity, never success, tool choices, latency or score."""
    old = validate_receipt(receipt)
    current = _conditions(assigned_conditions)
    prior = old["assigned_conditions"]
    model = old["model_id"]
    revision = old["model_revision"]
    binding = old["binding_ref"]
    if (
        not old["identity_verified"]
        or revision is None
        or revision != prior["model_revisions"].get(model)
        or revision != current["model_revisions"].get(model)
        or binding is None
        or binding != prior["binding_ref"]
        or binding != current["binding_ref"]
        or not _known_projection(prior)
        or not _known_projection(current)
    ):
        return "historical"
    changed = {key for key in PROJECTION_FIELDS if prior[key] != current[key]}
    if changed - {"grader"}:
        return "rerun"
    if not old["qualified"] or not old["measurement_valid"]:
        return "accounting_only" if old["accounting_complete"] else "rerun"
    if changed == {"grader"}:
        return (
            "regrade"
            if old["artifacts_retained"] and old["references_available"]
            else "rerun"
        )
    return "exact_comparable"


def plan_refresh(
    snapshot: Snapshot | dict,
    receipts: list[dict] | tuple[dict, ...],
    assigned_conditions: dict,
    incumbent_id: str,
) -> dict:
    """Private refresh plan; anchor ALWAYS fresh, unchanged eligible cells reused.

    All receipts remain in the disposition index. Multiple receipts for one model
    are all retained, never chosen by score. A grader-only change schedules regrade,
    not fresh candidate execution. Unknown catalog evidence downgrades receipts
    to historical. A fresh anchor is a required future diagnostic, NOT proof that
    reuse is currently stable or authority to execute/promote.
    """
    if isinstance(snapshot, dict):
        snapshot = Snapshot.from_dict(snapshot)
    if not isinstance(snapshot, Snapshot):
        raise ValueError("expected discovery snapshot")
    _text(incumbent_id)
    current = _conditions(assigned_conditions)
    if not isinstance(receipts, (list, tuple)):
        raise ValueError("expected receipt array")
    available = {candidate.id for candidate in snapshot.candidates}
    targets = available | {incumbent_id}
    classified = {}
    by_model = {model_id: [] for model_id in targets}
    for raw in receipts:
        receipt = validate_receipt(raw)
        receipt_id, model_id = receipt["receipt_id"], receipt["model_id"]
        if receipt_id in classified:
            raise ValueError("duplicate immutable receipt ID")
        disposition = reuse_disposition(receipt, current)
        if (
            model_id not in targets
            or snapshot.freshness != "bounded_live"
            or snapshot.binding_ref is None
            or snapshot.binding_ref != current["binding_ref"]
        ):
            disposition = "historical"
        classified[receipt_id] = disposition
        if model_id in by_model:
            by_model[model_id].append(disposition)
    fresh = {incumbent_id}
    for model_id in available - {incumbent_id}:
        dispositions = by_model[model_id]
        # Keep missing/invalid cells; a good attempt cannot erase a bad one.
        if not dispositions or any(
            value not in {"exact_comparable", "regrade"} for value in dispositions
        ):
            fresh.add(model_id)
    return {
        "version": RECEIPT_VERSION,
        "dispositions": dict(sorted(classified.items())),
        "reuse_ids": sorted(
            key for key, value in classified.items() if value == "exact_comparable"
        ),
        "regrade_ids": sorted(
            key for key, value in classified.items() if value == "regrade"
        ),
        "fresh_model_ids": [incumbent_id, *sorted(fresh - {incumbent_id})],
        "discovery_freshness": snapshot.freshness,
        "execution_supported": False,
    }
