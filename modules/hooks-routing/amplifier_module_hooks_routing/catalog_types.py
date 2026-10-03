"""Immutable, credential-free inputs for the bounded catalog API."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .knob_consistency import CallerContext
from .matrix_loader import validate_matrix_name

CATALOG_STATES = (
    "fresh_complete", "fresh_partial", "stale", "failed",
    "built_in_fallback", "manual", "unknown",
)


class UnsupportedVersionError(ValueError):
    """Unsupported API schema or semantic generation; no implicit migration."""


class UnsupportedPredictionError(ValueError):
    """No live-state snapshot protocol is implemented."""


def freeze(value: Any) -> Any:
    """Copy JSON-like policy data into recursively immutable containers."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Snapshot mapping keys must be strings")
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("Snapshots accept only finite JSON-like data, not live objects")


def thaw(value: Any) -> Any:
    """Detached JSON-compatible output; callers cannot mutate the snapshot."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def _text(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identity and revision fields must be nonempty strings")


def validate_module(module: str) -> None:
    if not isinstance(module, str) or not re.fullmatch(r"provider-[a-z][a-z0-9-]*", module):
        raise ValueError("Expected an exact full provider module ID")


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(s, str) or not s for s in value):
        raise ValueError("Expected a sequence of nonempty strings")
    if len(set(value)) != len(value):
        raise ValueError("Duplicate sequence entries")
    return tuple(value)


@dataclass(frozen=True)
class Selection:
    matrix_id: str
    semantic_generation: int = 1

    def __post_init__(self) -> None:
        validate_matrix_name(self.matrix_id)
        if type(self.semantic_generation) is not int or self.semantic_generation != 1:
            raise UnsupportedVersionError("Only semantic_generation=1 is supported")


@dataclass(frozen=True)
class ScopeBinding:
    module: str
    instance_id: str
    binding_id: str
    binding_revision: str

    def __post_init__(self) -> None:
        validate_module(self.module)
        for value in (self.instance_id, self.binding_id, self.binding_revision):
            _text(value)


def binding_key(value: Any) -> tuple[str, str, str, str]:
    return value.module, value.instance_id, value.binding_id, value.binding_revision


@dataclass(frozen=True)
class ApprovedScope:
    approval_revision: str
    allowed: tuple[ScopeBinding, ...] = ()

    def __post_init__(self) -> None:
        _text(self.approval_revision)
        allowed = tuple(self.allowed)
        if any(type(item) is not ScopeBinding for item in allowed):
            raise ValueError("Scope requires ScopeBinding entries")
        if len({item.instance_id for item in allowed}) != len(allowed):
            raise ValueError("Duplicate scope instance identities")
        object.__setattr__(self, "allowed", allowed)


@dataclass(frozen=True)
class ProviderSnapshot:
    module: str
    instance_id: str
    binding_id: str
    binding_revision: str
    priority: int = 0
    default_model: str = ""
    availability: str = "unknown"
    principal_assurance: str = "unknown"
    # Choice metadata only, never credentials, endpoints or mount options.
    config_choices: Mapping[str, tuple[str, ...]] | None = None
    native_capabilities: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        ScopeBinding(self.module, self.instance_id, self.binding_id, self.binding_revision)
        if type(self.priority) is not int or not isinstance(self.default_model, str):
            raise ValueError("Invalid provider priority/default_model")
        if self.availability not in ("available", "unavailable", "unknown"):
            raise ValueError("Invalid availability")
        if self.principal_assurance not in ("attested", "host_connection_bound", "unknown"):
            raise ValueError("Invalid principal assurance")
        if self.config_choices is not None:
            object.__setattr__(self, "config_choices", freeze({
                key: _strings(choices) for key, choices in self.config_choices.items()
            }))
        if self.native_capabilities is not None:
            object.__setattr__(self, "native_capabilities", _strings(self.native_capabilities))


@dataclass(frozen=True)
class CatalogSnapshot:
    module: str
    instance_id: str
    binding_id: str
    binding_revision: str
    revision: str
    state: str = "unknown"
    models: tuple[str, ...] = ()
    model_capabilities: Mapping[str, tuple[str, ...]] | None = None

    def __post_init__(self) -> None:
        ScopeBinding(self.module, self.instance_id, self.binding_id, self.binding_revision)
        _text(self.revision)
        if self.state not in CATALOG_STATES:
            raise ValueError("Invalid catalog evidence state")
        object.__setattr__(self, "models", _strings(self.models))
        if self.model_capabilities is not None:
            if set(self.model_capabilities) - set(self.models):
                raise ValueError("Capability evidence names a model outside its catalog")
            object.__setattr__(self, "model_capabilities", freeze({
                key: _strings(caps) for key, caps in self.model_capabilities.items()
            }))


@dataclass(frozen=True)
class AssessmentInputs:
    providers: tuple[ProviderSnapshot, ...]
    catalogs: tuple[CatalogSnapshot, ...]
    approved_scope: ApprovedScope
    topology_revision: str
    catalog_revision: str
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...] = ()
    caller_context: CallerContext | None = None
    # Not approximated in v1: supplying this field is explicitly rejected.
    explicit_preferences: Mapping[str, Any] | None = None
    role_capability_needs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, cls in (("providers", ProviderSnapshot), ("catalogs", CatalogSnapshot)):
            entries = tuple(getattr(self, name))
            if any(type(item) is not cls for item in entries):
                raise ValueError(f"{name} requires immutable snapshot entries, not providers")
            if len({item.instance_id for item in entries}) != len(entries):
                raise ValueError(f"Duplicate {name} instance identities")
            object.__setattr__(self, name, entries)
        if type(self.approved_scope) is not ApprovedScope:
            raise ValueError("approved_scope requires ApprovedScope")
        by_id = {provider.instance_id: provider for provider in self.providers}
        for catalog in self.catalogs:
            provider = by_id.get(catalog.instance_id)
            if provider is None or binding_key(provider) != binding_key(catalog):
                raise ValueError("Catalog/provider binding correspondence mismatch")
        for revision in (self.topology_revision, self.catalog_revision):
            _text(revision)
        for name in ("required_roles", "optional_roles"):
            object.__setattr__(self, name, _strings(getattr(self, name)))
        if not self.required_roles or set(self.required_roles) & set(self.optional_roles):
            raise ValueError("Required roles must be nonempty and disjoint from optional roles")
        if self.caller_context is not None and type(self.caller_context) is not CallerContext:
            raise ValueError("caller_context requires CallerContext")
        if self.caller_context is not None:
            _text(self.caller_context.family)
            _text(self.caller_context.model)
            if (
                not isinstance(self.caller_context.provider_key, str)
                or (self.caller_context.effort is not None and not isinstance(self.caller_context.effort, str))
            ):
                raise ValueError("CallerContext fields must be scalar strings")
        if self.explicit_preferences is not None:
            raise NotImplementedError("Explicit provider preferences are not assessed in catalog v1")
        if set(self.role_capability_needs) - set(self.required_roles + self.optional_roles):
            raise ValueError("Capability requirements must name assessed roles")
        object.__setattr__(self, "role_capability_needs", freeze({
            key: _strings(caps) for key, caps in self.role_capability_needs.items()
        }))