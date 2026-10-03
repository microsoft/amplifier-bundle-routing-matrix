"""Bounded v1 catalog: explicit preparation, detached descriptions, pure planning.

No provider objects enter the public API. The only list_models implementation
used here returns copied snapshot data; the production resolution loop is reused.
This library does not attest principals, refresh catalogs or enforce dispatch.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .catalog_types import (
    AssessmentInputs, Selection, UnsupportedPredictionError, UnsupportedVersionError,
    binding_key, freeze, thaw, validate_module,
)
from .knob_consistency import EscalationState, parse_preset
from .matrix_loader import (
    BUNDLE_SOURCE, SOURCE_ALIASES, compose_effective_matrix, load_matrix,
    provider_module_allowlist, resolve_matrix_source, validate_matrix, validate_matrix_name,
)
from .resolver import NoScopedRouteError, PROVIDER_FAMILY_ALIASES, resolve_model_role

_KNOWN_TYPES = {"openai", "openai-chatgpt", "anthropic", "gemini", "github-copilot", "ollama"}
_UNSUPPORTED_PATHS = (
    "root_dispatch", "direct_provider_calls", "auxiliary_calls", "foreign_runtime",
    "external_model_tools", "provider_internal_fallback", "admission_revision_fencing",
)


@dataclass(frozen=True)
class PreparedCatalogSources:
    entries: Mapping[str, Any]
    source_revision: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source_revision, str) or not self.source_revision:
            raise ValueError("source_revision must be a nonempty opaque revision")
        object.__setattr__(self, "entries", freeze(self.entries))
        object.__setattr__(self, "warnings", tuple(self.warnings))


def _metadata(path: Path) -> tuple[list[dict], dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise UnsupportedVersionError("Only catalog metadata schema_version=1 is supported")
    rows = data.get("strategies")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Catalog metadata requires strategies")
    identities: dict[str, dict] = {}
    canonical = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid strategy metadata")
        selection = Selection(row["matrix_id"], row["semantic_generation"])
        validate_matrix_name(row["source_stem"])
        if not isinstance(row.get("label"), str) or not row["label"]:
            raise ValueError("Missing catalog label")
        if type(row.get("display_order")) is not int:
            raise ValueError("Invalid display_order")
        aliases = row.get("aliases")
        if not isinstance(aliases, list):
            raise ValueError("Invalid alias metadata")
        for name in (selection.matrix_id, *aliases):
            validate_matrix_name(name)
            if name in identities:
                raise ValueError("Duplicate/ambiguous/cyclic catalog identity")
            identities[name] = row
        canonical.add(selection.matrix_id)
        if row["source_stem"] != selection.matrix_id:
            if SOURCE_ALIASES.get(selection.matrix_id) != row["source_stem"]:
                raise ValueError("Unsupported executable source alias")
    if any(alias in canonical for row in rows for alias in row["aliases"]):
        raise ValueError("Alias cannot also be a canonical identity")
    return rows, identities


def _policy_domains(matrix: dict) -> tuple[list[str], bool]:
    domains = set()
    unknown = False
    for definition in matrix["roles"].values():
        for candidate in definition["candidates"]:
            provider = candidate["provider"].removeprefix("provider-")
            if provider not in _KNOWN_TYPES:
                unknown = True
                continue
            domains.update(f"provider-{name}" for name in (
                provider, *PROVIDER_FAMILY_ALIASES.get(provider, ())
            ))
    allowlist = provider_module_allowlist(matrix)
    if allowlist is not None:
        domains.intersection_update(allowlist)
    return sorted(domains), unknown


def _validate_policy(matrix: dict) -> None:
    validate_matrix_name(matrix.get("name"))
    if not isinstance(matrix.get("description"), str):
        raise ValueError("Missing matrix description")
    if not isinstance(matrix.get("roles"), dict):
        raise ValueError("Matrix roles must be a mapping")
    errors = validate_matrix(matrix)
    if errors:
        raise ValueError("Invalid matrix: " + "; ".join(errors))
    for definition in matrix["roles"].values():
        if not isinstance(definition["candidates"], list):
            raise ValueError("Candidates must be a list")
        for candidate in definition["candidates"]:
            if not isinstance(candidate, dict) or any(
                not isinstance(candidate.get(key), str) or not candidate[key]
                for key in ("provider", "model")
            ):
                raise ValueError("Malformed matrix candidate")
            if "config" in candidate and not isinstance(candidate["config"], dict):
                raise ValueError("Candidate config must be a mapping")


def prepare_catalog_sources(
    bundle_routing_dir: Path | str,
    custom_routing_dirs: Sequence[Path | str] = (),
    *,
    config_overrides: dict | None = None,
    capability_overrides: dict | None = None,
    disable_delegation_preset: bool = False,
    source_revision: str = "unknown",
    custom_revisions: Mapping[str, str] | None = None,
    config_override_revision: str = "unknown",
    capability_override_revision: str = "unknown",
) -> PreparedCatalogSources:
    """Read only explicit dirs, then freeze. No ambient HOME or implicit refresh.

    bundle_routing_dir designates public bundle policy: only its winning files
    are hashed. Custom/override revisions are opaque caller tokens or unknown.
    """
    bundle = Path(bundle_routing_dir)
    custom = tuple(Path(directory) for directory in custom_routing_dirs)
    rows, metadata = _metadata(bundle / "catalog.v1.json")
    requested = set(metadata)
    for directory in custom:
        requested.update(path.stem for path in directory.glob("*.yaml"))
    origins = {}
    for name in sorted(requested):
        validate_matrix_name(name)
        origins[name] = resolve_matrix_source(name, custom, bundle)
    entries, warnings = {}, []
    for row in rows:
        if set(row) - {"matrix_id", "semantic_generation", "source_stem", "aliases",
                       "label", "display_order", "strategy_note"}:
            warnings.append(f"{row['matrix_id']}: unsupported public catalog metadata fields")
    for name, origin in origins.items():
        if origin.path is None:
            raise FileNotFoundError(f"No source for catalog identity {name}")
        base = load_matrix(origin.path)
        _validate_policy(base)
        effective, _, inert_errors = compose_effective_matrix(
            base, config_overrides, capability_overrides, disable_delegation_preset
        )
        _validate_policy(effective)
        row = metadata.get(name)
        public = origin.source == BUNDLE_SOURCE and row is not None
        # An alias group collapses only when EVERY requested winner is the same
        # public policy. A custom canonical filename can split a bundled alias
        # too; checking only this entry would hide one of the winning sources.
        equivalent = (
            public and origin.path.stem == row["source_stem"]
            and all(
                origins[peer].source == BUNDLE_SOURCE
                and origins[peer].path is not None
                and origins[peer].path.resolve() == origin.path.resolve()
                for peer in (row["matrix_id"], *row["aliases"])
            )
        )
        canonical = row["matrix_id"] if row else name
        matrix_id = canonical if equivalent else name
        modules, unknown = _policy_domains(effective)
        template = bool(effective["roles"]) and all(
            candidate["model"] == "*"
            for definition in effective["roles"].values()
            for candidate in definition["candidates"]
        )
        kind = "template" if template else (
            "unknown" if unknown else "provider-specific" if len(modules) == 1 else "shared"
        )
        custom_meta = base.get("catalog", {}) if not public else {}
        if not isinstance(custom_meta, dict):
            custom_meta = {}
            warnings.append(f"{name}: unsupported custom catalog metadata")
        if not public:
            warnings.append(f"{name}: source-qualified custom policy; alias equivalence unverified")
            if set(custom_meta) - {"label", "strategy_note"}:
                warnings.append(f"{name}: unsupported custom metadata fields")
            for key in ("label", "strategy_note"):
                if key in custom_meta and not isinstance(custom_meta[key], str):
                    warnings.append(f"{name}: unsupported custom {key} metadata")
                    custom_meta.pop(key)
        policy_revision = (
            "sha256:" + hashlib.sha256(origin.path.read_bytes()).hexdigest()
            if public else (custom_revisions or {}).get(name, "unknown")
        )
        descriptor = {
            "schema_version": 1, "matrix_id": matrix_id, "semantic_generation": 1,
            "requested_id": name, "canonical_id": canonical, "declared_name": base["name"],
            "aliases": list(row["aliases"]) if equivalent else [],
            "alias_equivalence": "bundle_owned" if equivalent else "unverified",
            "source_disposition": "bundle_policy" if public else "source_qualified_custom",
            "label": row["label"] if public else custom_meta.get("label", base["name"]),
            "description": base["description"],
            "strategy_note": row.get("strategy_note") if public else custom_meta.get("strategy_note"),
            "display_order": row["display_order"] if public else 1000,
            "kind": kind, "possible_provider_modules": modules,
            "provider_domain_complete": not unknown,
            "provider_module_allowlist": list(provider_module_allowlist(base) or ()),
            "policy_revision": policy_revision,
            "identity_invariants": {
                "provider_domain": modules, "required_policy_roles": ["general", "fast"],
                "scope_semantics": "exact_module_constraint_not_account_consent",
            },
        }
        entries[name] = {
            "descriptor": descriptor, "matrix": effective,
            "disable_delegation_preset": disable_delegation_preset,
            "source": {
                **origin.to_dict(), "source_stem": origin.path.stem,
                "source_revision": source_revision, "local_only": True,
                "override_chain": [
                    {"kind": "config", "revision": config_override_revision},
                    {"kind": "capability", "revision": capability_override_revision},
                ],
                "inert_keys_removed": bool(inert_errors),
            },
        }
    return PreparedCatalogSources(entries, source_revision, tuple(warnings))


class _SnapshotUnavailable(ValueError):
    pass


class _SnapshotProvider:
    def __init__(self, provider: Any, catalog: Any) -> None:
        self.snapshot = provider
        self.catalog = catalog

    async def list_models(self) -> list[str]:
        return list(self.catalog.models) if self.catalog is not None else []


class _SnapshotCoordinator:
    def __init__(self, providers: dict[str, _SnapshotProvider]) -> None:
        self.providers = providers
        self.config = {"providers": [
            {"module": p.snapshot.module, "instance_id": key,
             "config": {"priority": p.snapshot.priority, "default_model": p.snapshot.default_model}}
            for key, p in providers.items()
        ]}

    def get_capability(self, name: str) -> Any:
        return self.check_available if name == "provider.check_available" else None

    def check_available(self, instance_id: str) -> None:
        if self.providers[instance_id].snapshot.availability == "unavailable":
            raise _SnapshotUnavailable("Snapshot marks provider unavailable")


class RoutingCatalogV1:
    """No I/O after construction; use a new prepared snapshot for explicit refresh."""

    def __init__(self, prepared: PreparedCatalogSources, api_version: int = 1) -> None:
        if type(api_version) is not int or api_version != 1:
            raise UnsupportedVersionError("Only API version 1 is supported")
        if type(prepared) is not PreparedCatalogSources:
            raise TypeError("prepare_catalog_sources must be called explicitly")
        self.prepared = prepared

    def list(self) -> dict:
        unique = {}
        for entry in self.prepared.entries.values():
            descriptor = entry["descriptor"]
            # Custom alias variants do not silently collapse into a public ID.
            if descriptor["matrix_id"] not in unique or descriptor["requested_id"] == descriptor["matrix_id"]:
                unique[descriptor["matrix_id"]] = descriptor
        return {
            "schema_version": 1, "source_revision": self.prepared.source_revision,
            "strategies": [thaw(d) for d in sorted(
                unique.values(), key=lambda d: (d["display_order"], d["matrix_id"])
            )],
            "warnings": list(self.prepared.warnings),
            "supported_prediction_modes": ["new_run"],
            "enforcement": {"status": "not_enforced"}, "execution_ready": False,
        }

    def describe(self, selection: Selection) -> dict:
        if type(selection) is not Selection:
            raise TypeError("selection requires Selection")
        entry = self.prepared.entries.get(selection.matrix_id)
        if entry is None:
            raise KeyError(f"Unknown catalog identity {selection.matrix_id}")
        return {
            **thaw(entry["descriptor"]), "effective_policy": thaw(entry["matrix"]),
            "delegation_preset_disabled": entry["disable_delegation_preset"],
            "source": thaw(entry["source"]),
            "enforcement": {"status": "not_enforced"}, "execution_ready": False,
        }

    async def assess(
        self, selection: Selection, inputs: AssessmentInputs, prediction_mode: str = "new_run",
    ) -> dict:
        if prediction_mode != "new_run":
            raise UnsupportedPredictionError("Only independent new_run resolution is supported")
        if type(inputs) is not AssessmentInputs:
            raise TypeError("inputs requires AssessmentInputs")
        description = self.describe(selection)
        matrix = description["effective_policy"]
        preset = None if self.prepared.entries[selection.matrix_id]["disable_delegation_preset"] else parse_preset(matrix)
        approved = {binding_key(binding) for binding in inputs.approved_scope.allowed}
        topology = {binding_key(provider) for provider in inputs.providers}
        scope_invalid = bool(approved - topology)
        catalogs = {catalog.instance_id: catalog for catalog in inputs.catalogs}
        providers = {
            p.instance_id: _SnapshotProvider(p, catalogs.get(p.instance_id))
            for p in inputs.providers if binding_key(p) in approved
        }
        coordinator = _SnapshotCoordinator(providers)
        constraint = provider_module_allowlist(matrix)
        # Scope has already filtered exact bindings. This extra constraint makes
        # missing/unknown routes explicit and guards every final module selection.
        constraint = constraint if constraint is not None else tuple(sorted({p.snapshot.module for p in providers.values()}))
        roles = []
        for role in inputs.required_roles + inputs.optional_roles:
            report = {"role": role, "required": role in inputs.required_roles,
                      "status": "blocked", "selection": None, "compatibility": "incompatible",
                      "native_config_evidence": "unknown", "reasons": []}
            if scope_invalid or not providers:
                report["reasons"] = ["scope_binding_changed_or_missing" if scope_invalid else "no_approved_bindings"]
            elif role not in matrix["roles"]:
                report.update(status="missing", reasons=["role_not_defined"])
            else:
                observed = []
                try:
                    resolved = await resolve_model_role(
                        [role], matrix["roles"], providers, coordinator=coordinator,
                        caller_context=inputs.caller_context, preset=preset,
                        escalations=EscalationState(max_uses=preset.escalate_max_uses if preset else 0),
                        provider_module_allowlist=constraint, observations=observed.append,
                        report_logs=False,
                    )
                except (NoScopedRouteError, _SnapshotUnavailable):
                    resolved = []
                uncertain_catalog = any(
                    event["status"] == "glob_no_match" and (
                        catalogs.get(event["provider"]) is None or
                        catalogs[event["provider"]].state != "fresh_complete" or
                        providers[event["provider"]].snapshot.availability == "unknown"
                    ) for event in observed
                )
                unavailable = any(event["status"] == "unavailable" for event in observed)
                uncertain_predecessor = unavailable or uncertain_catalog
                if not resolved:
                    report["reasons"] = [
                        "catalog_or_availability_uncertain" if uncertain_catalog
                        else "provider_unavailable" if unavailable else "no_scoped_role_match"
                    ]
                    if uncertain_catalog:
                        report.update(status="unknown", compatibility="unknown")
                else:
                    selected = resolved[0]
                    provider = providers[selected["provider"]].snapshot
                    catalog = catalogs.get(provider.instance_id)
                    # Final exact binding validation, after inherited intent.
                    if binding_key(provider) not in approved:
                        raise NoScopedRouteError("Final target outside approved binding scope")
                    report.update(status="selected", selection={
                        **selected, "module": provider.module,
                        "instance_id": provider.instance_id, "binding_id": provider.binding_id,
                        "binding_revision": provider.binding_revision, "local_only": True,
                        "principal_assurance": provider.principal_assurance,
                    })
                    reasons = report["reasons"]
                    complete = catalog is not None and catalog.state == "fresh_complete"
                    compatible = "verified" if complete and provider.availability == "available" else "unknown"
                    if not complete:
                        reasons.append("catalog_not_fresh_complete")
                    if provider.availability != "available":
                        reasons.append("availability_unknown")
                    if complete and selected["model"] not in catalog.models:
                        compatible = "incompatible"
                        reasons.append("exact_pin_absent_from_authoritative_catalog")
                    if uncertain_predecessor:
                        if compatible != "incompatible":
                            compatible = "unknown"
                        reasons.append("preferred_candidate_uncertain")
                    config = selected["config"]
                    choices = provider.config_choices
                    config_known = all(choices is not None and key in choices and choices[key] for key in config)
                    invalid_config = any(
                        choices is not None and key in choices and choices[key]
                        and str(value) not in choices[key] for key, value in config.items()
                    )
                    report["native_config_evidence"] = "incompatible" if invalid_config else "verified" if config_known else "unknown"
                    if invalid_config:
                        compatible = "incompatible"
                        reasons.append("invalid_native_config_choice")
                    elif config and not config_known:
                        if compatible != "incompatible":
                            compatible = "unknown"
                        reasons.append("native_config_schema_unknown")
                    needs = set(inputs.role_capability_needs.get(role, ()))
                    # A text-model role label never establishes native image generation.
                    if role == "image-gen":
                        needs.add("image-generation")
                    if role == "vision":
                        needs.add("vision")
                    if needs:
                        caps = None if catalog is None or catalog.model_capabilities is None else catalog.model_capabilities.get(selected["model"])
                        native = provider.native_capabilities
                        native_unsupported = native is not None and not needs.issubset(native)
                        model_unsupported = caps is not None and not needs.issubset(caps)
                        if native_unsupported or (complete and model_unsupported):
                            compatible = "incompatible"
                            reasons.append("required_native_capability_unsupported")
                        elif model_unsupported and compatible != "incompatible":
                            compatible = "unknown"
                            reasons.append("capability_evidence_not_authoritative")
                        elif caps is None or native is None or not complete:
                            if compatible != "incompatible":
                                compatible = "unknown"
                            reasons.append("required_native_capability_unknown")
                    report["compatibility"] = compatible
                    report["catalog_state"] = catalog.state if catalog else "unknown"
                    report["catalog_snapshot_revision"] = catalog.revision if catalog else "unknown"
            roles.append(report)
        required = [role for role in roles if role["required"]]
        compatibility = (
            "incompatible" if any(role["compatibility"] == "incompatible" for role in required)
            else "unknown" if any(role["compatibility"] == "unknown" for role in required)
            else "verified"
        )
        coverage = (
            "incomplete" if any(role["status"] in ("missing", "blocked") for role in required)
            else "unknown" if compatibility == "unknown" else "complete"
        )
        return {
            "schema_version": 1, "matrix_id": description["matrix_id"],
            "requested_id": selection.matrix_id, "semantic_generation": 1,
            "source_revision": self.prepared.source_revision,
            "topology_revision": inputs.topology_revision, "catalog_revision": inputs.catalog_revision,
            "approval_revision": inputs.approved_scope.approval_revision,
            "prediction_subject": "model_role_resolution",
            "prediction_mode": "new_run", "planning_state_mode": "independent_initial_resolution",
            "roles": roles, "compatibility": compatibility, "required_role_coverage": coverage,
            "scope_planning": "blocked" if scope_invalid or coverage == "incomplete" else "unknown" if any(r["status"] == "unknown" for r in required) else "contained",
            "enforcement": {"status": "not_enforced", "unsupported_paths": list(_UNSUPPORTED_PATHS)},
            "execution_ready": False, "local_binding_handles": True,
            "billing_assurance": "Host-supplied principal evidence; not attested by this library.",
        }

    async def discover_provider_only(self, provider_module: str, inputs: AssessmentInputs) -> dict:
        validate_module(provider_module)
        if type(inputs) is not AssessmentInputs:
            raise TypeError("inputs requires AssessmentInputs")
        # Intersection only: discovery cannot approve a new module/account.
        scope = replace(inputs.approved_scope, allowed=tuple(
            binding for binding in inputs.approved_scope.allowed if binding.module == provider_module
        ))
        restricted = replace(inputs, approved_scope=scope)
        candidates = []
        for descriptor in self.list()["strategies"]:
            selection = Selection(descriptor["requested_id"])
            description = self.describe(selection)
            assessment = await self.assess(selection, restricted)
            domains = description["possible_provider_modules"]
            known = description["provider_domain_complete"]
            dedicated = description["provider_module_allowlist"] == [provider_module]
            inherited = parse_preset(description["effective_policy"])
            inheritance_safe = (
                dedicated or inherited is None or not inherited.active
                or self.prepared.entries[selection.matrix_id]["disable_delegation_preset"]
            )
            kind = (
                "dedicated_profile" if dedicated and assessment["compatibility"] == "verified"
                else "natural_provider_only" if known and inheritance_safe and domains == [provider_module]
                else "requires_provider_restriction"
            )
            candidates.append({"matrix_id": description["matrix_id"], "discovery_kind": kind,
                               "descriptor": description, "assessment": assessment,
                               "reasons": ["exact_dedicated_verified"] if kind == "dedicated_profile" else [
                                   "policy_domain_single_module" if kind == "natural_provider_only" else "scope_filter_required_or_domain_unknown"
                               ]})
        candidates.sort(key=lambda item: (
            {"verified": 0, "unknown": 1, "incompatible": 2}[item["assessment"]["compatibility"]],
            0 if item["discovery_kind"] == "dedicated_profile" else 1 if item["discovery_kind"] == "natural_provider_only" else 2,
            item["descriptor"]["display_order"], item["matrix_id"],
        ))
        return {"schema_version": 1, "provider_module": provider_module, "candidates": candidates,
                "enforcement": {"status": "not_enforced"}, "execution_ready": False}