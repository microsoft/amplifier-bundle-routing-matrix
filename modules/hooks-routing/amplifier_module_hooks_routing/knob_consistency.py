"""Knob-consistent routing -- propagate the caller's tier/effort intent across
the delegation boundary.

**Default-off by construction.** Everything in this module is inert unless a
matrix file carries an optional top-level ``preset:`` block. A matrix with no
``preset:`` key resolves exactly as it did before this module existed, byte for
byte -- see :func:`parse_preset` returning ``None`` and
:func:`plan_candidates` never being called in that case.

Why this exists
---------------
A cell pins model/effort **for the root only**; sub-agents are routed by the
routing matrix, so the effort dial governs only the root's own work. Measured:
a terra S1 tree sent 85-96% of its LLM calls to sol; a haiku cell billed $2.225
with 26 of 49 calls on sol; luna costs $1.5 when it delegates to sol vs
$0.48-0.78 when it does not (``00-what-we-know.md`` section 2c). The matrix
answers "what does this role need?" and never asks "what did the caller ask
for?".

This module inserts that question as **level 3** of the resolution chain:

===  ======================================================  ================
 #   level                                                    where
===  ======================================================  ================
 1   explicit ``delegate(provider_preferences=[...])``        tool-delegate
 2   agent frontmatter ``provider_preferences`` (the pin)     tool-delegate
 3   **inherited caller intent, filtered by ``inherit``**     **this module**
 4   agent frontmatter ``model_role`` -> matrix candidate      resolver.py
 5   matrix ``general`` fallback                              matrix_loader.py
===  ======================================================  ================

Levels 1 and 2 stay strictly above level 3, so an author or caller who *wants*
a specialist model still gets one: inheritance is a default, never a ceiling on
explicit intent. Level 1 is enforced for free -- tool-delegate never calls the
resolver when ``provider_preferences`` is set. Level 2 is enforced in
``__init__.py``'s session-start path, which skips the clamp for any agent that
already carries an explicit pin.

What this module deliberately does NOT do
-----------------------------------------
The ``preset:`` block can also carry fan-out, timeout, partial-result,
``session_scoped`` and ``context`` knobs. Those are **parsed and validated here
but never applied**, because the design source is explicit that they are a
different treatment:

    "Bound the tree; do not vary effort inside it. **These must not ship as
    one treatment.**" -- ROUTING-PROPOSAL.md section 6.3

Applying them would also require changes outside this repository (the provider
and context mount configs are assembled by the app, not by a routing hook).
Parsing them keeps a preset file honest and single-sourced; refusing to act on
them keeps this treatment single-variable.

Cross-vendor safety
-------------------
Anthropic's ``G-EFFORT-CONSTANT`` requires exactly one distinct effort value
across every request of a session. This design clears it by construction: a
delegate **spawns a new session** with its own request prefix, so setting the
child's effort at creation is not a change to any existing session's effort.
Nothing here re-configures a running session, and escalation consumes a use
only when a *new* child is spawned at a higher rung.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# The four inheritance modes (ROUTING-PROPOSAL.md section 3.2).
#   none            -- ignore the caller; return today's candidate. The default.
#   effort          -- keep the candidate's model, carry the caller's effort.
#   tier-and-effort -- clamp the model to at most the caller's rung, carry the
#                      caller's effort, allow declared escalations.
#   strict          -- as above, and escalation is denied outright.
INHERIT_MODES = ("none", "effort", "tier-and-effort", "strict")

VALID_ON_EXHAUSTED = ("fall_back", "error")

# The canonical effort key for THIS repository, enforced across every shipped
# matrix by tests/test_matrix_config_validation.py. Note this deliberately
# diverges from ROUTING-PROPOSAL.md section 2.2, whose example writes
# ``effort:`` for anthropic candidates: providers accept ``effort`` only as a
# deprecated alias, and a matrix that used it would fail this repo's own
# hygiene test. One spelling, every family.
CANONICAL_EFFORT_KEY = "reasoning_effort"

# Models that accept no effort parameter at all. Measured on our own traffic:
# ``claude-haiku-4-5`` requests carry no effort field and a fixed
# ``thinking: {budget_tokens: 32000}`` (n=228 requests / 10 runs, PRESETS.md
# section 0.3). Inheriting an effort into one of these is a no-op, and the
# clamp record must say so rather than pretend intent was honoured.
DEFAULT_EFFORT_UNSUPPORTED: tuple[str, ...] = ("claude-haiku-*",)


@dataclass(frozen=True)
class CallerContext:
    """The caller session's own resolved routing triple.

    This is the "what did the caller ask for?" half of the problem. It is
    derived from the caller's own provider mount config (see
    :func:`derive_caller_context`), which is where the app records the answer
    after applying ``--model``/``--provider``, settings, or a parent's
    ``provider_preferences``.

    Attributes:
        family: Provider family name as it appears in a ladder key and in a
            matrix candidate's ``provider:`` field (``"openai"``,
            ``"anthropic"``).
        model: Concrete resolved model id (``"gpt-5.6-terra"``).
        effort: The caller's effort value, or ``None`` when the caller's
            provider config carries none.
        provider_key: The mounted provider key the caller is actually using.
            Diagnostic only; never used for matching.
    """

    family: str
    model: str
    effort: str | None = None
    provider_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "model": self.model,
            "effort": self.effort,
            "provider_key": self.provider_key,
        }


@dataclass(frozen=True)
class Preset:
    """A parsed, validated ``preset:`` block.

    Only :attr:`inherit`, :attr:`tier_ladder`, :attr:`escalate_*`,
    :attr:`effort_keys`, :attr:`effort_unsupported` and
    :attr:`report_unhonored` affect routing. The remaining fields are parsed
    and carried so a preset file can be single-sourced and validated, but are
    NOT acted on by this module -- see the module docstring.
    """

    inherit: str = "none"
    tier_ladder: dict[str, list[list[str]]] = field(default_factory=dict)
    escalate_allow_roles: tuple[str, ...] = ()
    escalate_max_uses: int = 0
    escalate_on_exhausted: str = "fall_back"
    report_unhonored: bool = True
    effort_keys: dict[str, str] = field(default_factory=dict)
    effort_unsupported: tuple[str, ...] = DEFAULT_EFFORT_UNSUPPORTED
    # Parsed, never applied here (separate treatment -- see module docstring).
    axis: tuple[str, ...] = ()
    session_scoped: dict[str, Any] = field(default_factory=dict)
    fan_out_max: int | None = None
    delegate_timeout_s: int | None = None
    on_timeout: str = "partial"
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        """True when this preset changes resolution at all."""
        return self.inherit != "none"

    @property
    def clamps_tier(self) -> bool:
        return self.inherit in ("tier-and-effort", "strict")

    def effort_key_for(self, family: str) -> str:
        return self.effort_keys.get(family, CANONICAL_EFFORT_KEY)

    def supports_effort(self, model: str) -> bool:
        """False when *model* accepts no effort parameter (e.g. haiku)."""
        lowered = model.lower()
        return not any(
            fnmatch.fnmatch(lowered, pat.lower()) for pat in self.effort_unsupported
        )


@dataclass
class EscalationState:
    """Per-session escalation budget.

    ``max_uses`` is per session, not per delegation tree: the counter lives on
    the resolver instance, which is constructed once per ``mount()`` and lives
    for the session.
    """

    max_uses: int = 0
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_uses - self.used)

    def consume(self) -> None:
        self.used += 1


@dataclass
class ClampRecord:
    """One structured account of what the caller asked for and what it got.

    Emitted as a ``routing:intent-clamped`` event and recorded on the resolver
    instance. **Emit, never inject** -- this record goes to the event log, not
    into the conversation (injected telemetry becomes prefix mutation at
    worst; ROUTING-PROPOSAL.md section 3.4 item 3).
    """

    role: str
    mode: str
    honored: bool
    reason: str
    caller: dict[str, Any] | None = None
    requested_model: str | None = None
    requested_effort: str | None = None
    granted_model: str | None = None
    granted_effort: str | None = None
    escalated: bool = False
    escalations_remaining: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "mode": self.mode,
            "honored": self.honored,
            "reason": self.reason,
            "caller": self.caller,
            "requested": {
                "model": self.requested_model,
                "effort": self.requested_effort,
            },
            "granted": {"model": self.granted_model, "effort": self.granted_effort},
            "escalated": self.escalated,
            "escalations_remaining": self.escalations_remaining,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _as_rungs(raw: Any) -> list[list[str]]:
    """Normalise one family's ladder to a list of rungs, each a list of globs.

    ROUTING-PROPOSAL.md section 2.2 writes one glob per rung. A real matrix
    needs more than one: ``openai.yaml``'s ``fast`` role lists both
    ``gpt-?.?-luna*`` and ``gpt-?.?-mini*``, and every flagship role carries
    the ``gpt-[0-9].[0-9]`` migration fallback. Both spellings are accepted --
    a bare string is a one-glob rung.
    """
    rungs: list[list[str]] = []
    for entry in raw or []:
        if isinstance(entry, str):
            rungs.append([entry])
        elif isinstance(entry, list):
            rungs.append([g for g in entry if isinstance(g, str)])
    return rungs


def parse_preset(matrix_file: dict[str, Any] | None) -> Preset | None:
    """Parse a loaded matrix file's optional ``preset:`` block.

    Args:
        matrix_file: The whole parsed matrix YAML (from ``load_matrix``), NOT
            the ``roles`` sub-dict.

    Returns:
        A :class:`Preset`, or ``None`` when the file carries no ``preset:``
        block. ``None`` is the default-off signal every caller checks.
    """
    if not isinstance(matrix_file, dict):
        return None
    raw = matrix_file.get("preset")
    if not isinstance(raw, dict):
        return None

    delegation = raw.get("delegation") or {}
    if not isinstance(delegation, dict):
        delegation = {}
    escalate = delegation.get("escalate") or {}
    if not isinstance(escalate, dict):
        escalate = {}

    ladder_raw = raw.get("tier_ladder") or {}
    tier_ladder: dict[str, list[list[str]]] = {}
    if isinstance(ladder_raw, dict):
        for family, rungs in ladder_raw.items():
            tier_ladder[str(family)] = _as_rungs(rungs)

    axis_raw = raw.get("axis") or ()
    axis = tuple(str(a) for a in axis_raw) if isinstance(axis_raw, list) else ()

    allow_roles_raw = escalate.get("allow_roles") or []
    allow_roles = (
        tuple(str(r) for r in allow_roles_raw)
        if isinstance(allow_roles_raw, list)
        else ()
    )

    effort_keys_raw = raw.get("effort_keys") or {}
    effort_keys = (
        {str(k): str(v) for k, v in effort_keys_raw.items()}
        if isinstance(effort_keys_raw, dict)
        else {}
    )

    unsupported_raw = raw.get("effort_unsupported")
    effort_unsupported = (
        tuple(str(p) for p in unsupported_raw)
        if isinstance(unsupported_raw, list)
        else DEFAULT_EFFORT_UNSUPPORTED
    )

    return Preset(
        inherit=str(delegation.get("inherit", "none")),
        tier_ladder=tier_ladder,
        escalate_allow_roles=allow_roles,
        escalate_max_uses=int(escalate.get("max_uses", 0) or 0),
        escalate_on_exhausted=str(escalate.get("on_exhausted", "fall_back")),
        report_unhonored=bool(delegation.get("report_unhonored", True)),
        effort_keys=effort_keys,
        effort_unsupported=effort_unsupported,
        axis=axis,
        session_scoped=raw.get("session_scoped") or {},
        fan_out_max=delegation.get("fan_out_max"),
        delegate_timeout_s=delegation.get("delegate_timeout_s"),
        on_timeout=str(delegation.get("on_timeout", "partial")),
        context=raw.get("context") or {},
    )


# ---------------------------------------------------------------------------
# Validation (ROUTING-PROPOSAL.md section 2.2)
# ---------------------------------------------------------------------------


def validate_preset(matrix_file: dict[str, Any]) -> list[str]:
    """Validate a matrix file's ``preset:`` block against the section 2.2 rules.

    A file with no ``preset:`` block is valid and returns ``[]`` -- this
    function can never reject a matrix that predates the feature.

    Returns:
        List of error strings. Empty means valid. The caller (``mount()``)
        raises on a non-empty list, because a preset is opt-in: failing loud
        cannot break anyone who has not asked for the feature, and a silently
        misapplied tier ceiling is exactly the class of defect this whole
        change exists to remove.
    """
    errors: list[str] = []
    raw = matrix_file.get("preset")
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        return [f"preset: must be a mapping, got {type(raw).__name__}."]

    preset = parse_preset(matrix_file)
    assert preset is not None  # narrowed: raw is a dict

    if preset.inherit not in INHERIT_MODES:
        errors.append(
            f"preset.delegation.inherit={preset.inherit!r} is not one of "
            f"{', '.join(INHERIT_MODES)}."
        )

    if preset.escalate_on_exhausted not in VALID_ON_EXHAUSTED:
        errors.append(
            f"preset.delegation.escalate.on_exhausted="
            f"{preset.escalate_on_exhausted!r} is not one of "
            f"{', '.join(VALID_ON_EXHAUSTED)}."
        )

    # Rule: a ladder is required whenever clamping is requested -- clamping
    # needs an order, and failing loud beats guessing one.
    if preset.clamps_tier and not preset.tier_ladder:
        errors.append(
            f"preset.tier_ladder is required when delegation.inherit="
            f"{preset.inherit!r} (clamping needs an explicit order)."
        )

    for family, rungs in preset.tier_ladder.items():
        if not rungs:
            errors.append(f"preset.tier_ladder.{family}: empty ladder.")
        for i, rung in enumerate(rungs):
            if not rung:
                errors.append(f"preset.tier_ladder.{family}: rung {i} is empty.")

    roles = matrix_file.get("roles") or {}

    # Rule: escalate.allow_roles must be a subset of the file's own role names
    # -- catches typos that would silently deny escalation.
    for role in preset.escalate_allow_roles:
        if role not in roles:
            errors.append(
                f"preset.delegation.escalate.allow_roles: {role!r} is not a "
                f"role in this matrix (have: {', '.join(sorted(roles))})."
            )

    # Rule: a cap without a timeout converts a straggler into a queue.
    if preset.fan_out_max is not None and preset.delegate_timeout_s is None:
        errors.append(
            "preset.delegation.delegate_timeout_s must be set whenever "
            "fan_out_max is set (a cap without a timeout converts a straggler "
            "into a queue)."
        )

    # Rule: every candidate model glob must match exactly one rung of its
    # provider's ladder -- otherwise a candidate is unclampable and silently
    # exempt, which is the defect in a different costume.
    if preset.clamps_tier:
        for role_name, role_data in roles.items():
            if not isinstance(role_data, dict):
                continue
            for i, cand in enumerate(role_data.get("candidates") or []):
                if not isinstance(cand, dict):
                    continue
                family = str(cand.get("provider", ""))
                model = str(cand.get("model", ""))
                ladder = preset.tier_ladder.get(family)
                if ladder is None:
                    errors.append(
                        f"Role {role_name!r} candidate {i} ({family}/{model}): "
                        f"provider {family!r} has no preset.tier_ladder entry, "
                        f"so this candidate is unclampable."
                    )
                    continue
                hits = [
                    r for r, rung in enumerate(ladder) if _glob_in_rung(model, rung)
                ]
                if len(hits) != 1:
                    errors.append(
                        f"Role {role_name!r} candidate {i} ({family}/{model}): "
                        f"model glob matches {len(hits)} rungs of the "
                        f"{family!r} ladder, expected exactly 1."
                    )

    # Rule: effort must be spelled canonically, and must not be declared on a
    # model that has no effort parameter (measured: haiku carries none).
    for family, key in preset.effort_keys.items():
        if key != CANONICAL_EFFORT_KEY:
            errors.append(
                f"preset.effort_keys.{family}={key!r}: this repository's "
                f"canonical effort key is {CANONICAL_EFFORT_KEY!r} (enforced "
                f"by tests/test_matrix_config_validation.py)."
            )

    for role_name, role_data in roles.items():
        if not isinstance(role_data, dict):
            continue
        for i, cand in enumerate(role_data.get("candidates") or []):
            if not isinstance(cand, dict):
                continue
            cfg = cand.get("config") or {}
            model = str(cand.get("model", ""))
            if CANONICAL_EFFORT_KEY in cfg and not preset.supports_effort(model):
                errors.append(
                    f"Role {role_name!r} candidate {i} ({model}): "
                    f"{CANONICAL_EFFORT_KEY} declared on a model that accepts "
                    f"no effort parameter (preset.effort_unsupported)."
                )

    # Rule: session_scoped keys must be drawn from a declared invalidator
    # allow-list. This module never APPLIES them (separate treatment), but a
    # preset that names a non-prefix knob here freezes it for no reason, and
    # one that omits a prefix knob leaks it per-turn -- both worth catching at
    # authoring time rather than on the wire.
    allowed_invalidators = {
        "reasoning_effort",
        "reasoning_summary",
        "text_verbosity",
        "thinking",
        "effort",
        "model",
        "parallel_tool_calls",
        "text_format",
        "context_management",
    }
    session_scoped = preset.session_scoped
    if isinstance(session_scoped, dict):
        for family, knobs in session_scoped.items():
            if not isinstance(knobs, dict):
                errors.append(
                    f"preset.session_scoped.{family}: expected a mapping, got "
                    f"{type(knobs).__name__}."
                )
                continue
            for key in knobs:
                if key not in allowed_invalidators:
                    errors.append(
                        f"preset.session_scoped.{family}.{key}: not on the "
                        f"declared invalidator allow-list "
                        f"({', '.join(sorted(allowed_invalidators))})."
                    )

    return errors


def _glob_in_rung(model: str, rung: list[str]) -> bool:
    """True when *model* (a concrete id OR a glob) belongs to *rung*.

    Two ways to belong, and both are needed:

    * **fnmatch** -- a concrete id against a rung glob (``gpt-5.6-terra`` vs
      ``gpt-?.?-terra*``), which is the runtime case.
    * **exact string equality** -- a matrix glob against an identical rung
      glob, which is the authoring case. Equality is not redundant: a
      character-class glob does not fnmatch itself (the ``[`` in the literal
      name ``gpt-[0-9].[0-9]`` is not a digit, so the class never matches it),
      and without this a curator's migration-fallback candidate would be
      declared unclampable and silently exempted from the ceiling -- the
      original defect, wearing a different hat.

    Comparison is case-insensitive in both directions, matching
    :func:`resolver._resolve_glob`'s own OS-independent semantics.
    """
    lowered = model.lower()
    return any(
        lowered == g.lower() or fnmatch.fnmatch(lowered, g.lower()) for g in rung
    )


def rung_of(model: str, ladder: list[list[str]] | None) -> int | None:
    """Index of the ladder rung *model* sits on, or ``None`` when off-ladder.

    Off-ladder is a real, reportable state -- never silently treated as rung 0
    (which would clamp everything to the cheap tier) or as the top rung (which
    would exempt it). The caller emits an un-honoured record instead.
    """
    if not ladder:
        return None
    for i, rung in enumerate(ladder):
        if _glob_in_rung(model, rung):
            return i
    return None


# ---------------------------------------------------------------------------
# Caller-context derivation
# ---------------------------------------------------------------------------


def derive_caller_context(
    coordinator: Any,
    preset: Preset | None = None,
) -> CallerContext | None:
    """Read the caller session's own resolved (family, model, effort).

    ROUTING-PROPOSAL.md sections 4.2-4.3 route this through a new
    ``caller_context`` argument threaded from tool-delegate, which would
    require a coordinated change in ``amplifier-foundation``. **This
    implementation does not need one**, and that is the single most useful
    deviation in this change:

    the resolver is mounted in the *caller's* session and holds the *caller's*
    coordinator. The caller's own resolved triple is already recorded there --
    ``amplifier_foundation.spawn_utils._apply_single_override`` writes
    ``config.priority = 0`` and ``config.default_model = <model>`` (plus any
    inherited effort) onto the chosen provider spec when a session is spawned,
    and the app writes the same shape for a root session from settings and
    ``--model``. So the answer to "what did the caller ask for?" is a read, not
    a plumbing change.

    This also makes inheritance transitive for free: a child session's own
    ``session:start`` sees its own (already clamped) provider config, so the
    ceiling propagates down the whole tree without any per-level bookkeeping.

    Returns:
        A :class:`CallerContext`, or ``None`` when the caller's model cannot be
        determined (no provider specs, or no ``default_model`` on the active
        one). ``None`` disables the feature for that resolution and is
        reported, never guessed around.
    """
    config = getattr(coordinator, "config", None)
    if not isinstance(config, dict):
        return None
    specs = config.get("providers")
    if not isinstance(specs, list) or not specs:
        return None

    best: dict[str, Any] | None = None
    best_priority: int | None = None
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        cfg = spec.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
        try:
            priority = int(cfg.get("priority", 100))
        except (TypeError, ValueError):
            priority = 100
        if best_priority is None or priority < best_priority:
            best, best_priority = spec, priority

    if best is None:
        return None

    cfg = best.get("config") or {}
    model = cfg.get("default_model")
    if not model or not isinstance(model, str):
        return None

    module = str(best.get("module") or "")
    family = module.replace("provider-", "") or str(best.get("id") or "")
    effort_key = (preset or Preset()).effort_key_for(family)
    effort = cfg.get(effort_key)
    return CallerContext(
        family=family,
        model=model,
        effort=str(effort) if effort is not None else None,
        provider_key=str(best.get("id") or module),
    )


# ---------------------------------------------------------------------------
# The clamp
# ---------------------------------------------------------------------------


def _with_effort(
    candidate: dict[str, Any],
    preset: Preset,
    effort: str | None,
) -> dict[str, Any]:
    """Return a copy of *candidate* carrying *effort*, honouring the target.

    Inherited effort wins over the candidate's own declared effort
    (ROUTING-PROPOSAL.md section 4.8's proposed precedence rule), except that
    a model with no effort parameter has the key removed entirely rather than
    silently accepting a value it will drop.
    """
    out = dict(candidate)
    cfg = dict(out.get("config") or {})
    family = str(out.get("provider", ""))
    key = preset.effort_key_for(family)
    model = str(out.get("model", ""))

    if not preset.supports_effort(model):
        cfg.pop(key, None)
    elif effort is not None:
        cfg[key] = effort

    if cfg:
        out["config"] = cfg
    else:
        out.pop("config", None)
    return out


def _effort_of(candidate: dict[str, Any], preset: Preset) -> str | None:
    cfg = candidate.get("config") or {}
    key = preset.effort_key_for(str(candidate.get("provider", "")))
    value = cfg.get(key)
    return str(value) if value is not None else None


def plan_candidates(
    role: str,
    candidates: list[Any],
    caller: CallerContext | None,
    preset: Preset | None,
    escalations: EscalationState | None = None,
) -> tuple[list[Any], ClampRecord | None]:
    """Rewrite a role's candidate list to honour the caller's intent.

    This is the whole feature, as a pure function. It returns a NEW ordered
    candidate list for the existing resolution loop to walk, plus an optional
    :class:`ClampRecord` describing what happened. It never resolves globs,
    never touches a provider, and never mutates its inputs -- which is what
    makes every mode fully unit-testable with no network and no session.

    Returns the input list unchanged, and ``None``, whenever the feature is
    off. That identity is what guarantees default behaviour is byte-identical.

    Args:
        role: The role name being resolved (used for escalation allow-lists
            and for the record).
        candidates: The role's ordered candidate list, straight from the
            matrix.
        caller: The caller's resolved triple, or ``None`` when unknown.
        preset: The active preset, or ``None`` when the matrix has none.
        escalations: Per-session escalation budget. ``None`` means no budget.

    Returns:
        ``(candidates, clamp_record_or_None)``.
    """
    if preset is None or not preset.active:
        return candidates, None

    mode = preset.inherit

    if caller is None:
        record = ClampRecord(
            role=role,
            mode=mode,
            honored=False,
            reason="caller context unavailable -- matrix candidate used as-is",
        )
        return candidates, record if preset.report_unhonored else None

    dict_candidates = [c for c in candidates if isinstance(c, dict)]
    if not dict_candidates:
        return candidates, None

    # ---- mode: effort -- keep the model, carry the depth --------------------
    if mode == "effort":
        planned = [_with_effort(c, preset, caller.effort) for c in dict_candidates]
        top = planned[0]
        honored = preset.supports_effort(str(top.get("model", "")))
        record = ClampRecord(
            role=role,
            mode=mode,
            honored=honored,
            reason=(
                "effort inherited" if honored else "effort unsupported on target model"
            ),
            caller=caller.to_dict(),
            requested_model=str(dict_candidates[0].get("model", "")),
            requested_effort=_effort_of(dict_candidates[0], preset),
            granted_model=str(top.get("model", "")),
            granted_effort=_effort_of(top, preset),
            escalations_remaining=escalations.remaining if escalations else 0,
        )
        return planned, record

    # ---- modes: tier-and-effort / strict ------------------------------------
    ladder = preset.tier_ladder.get(caller.family)
    caller_rung = rung_of(caller.model, ladder)
    if caller_rung is None:
        record = ClampRecord(
            role=role,
            mode=mode,
            honored=False,
            reason=(
                f"caller model {caller.model!r} is not on the "
                f"{caller.family!r} tier ladder -- no ceiling could be derived"
            ),
            caller=caller.to_dict(),
            requested_model=str(dict_candidates[0].get("model", "")),
            granted_model=str(dict_candidates[0].get("model", "")),
            escalations_remaining=escalations.remaining if escalations else 0,
        )
        return candidates, record if preset.report_unhonored else None

    original_top = dict_candidates[0]

    # Escalation is the controlled exception: a role on the allow-list may
    # exceed the caller's rung, at most max_uses times per session. `strict`
    # denies it outright, for any role.
    may_escalate = (
        mode != "strict"
        and role in preset.escalate_allow_roles
        and escalations is not None
        and escalations.remaining > 0
    )
    if may_escalate:
        top_rung = rung_of(
            str(original_top.get("model", "")),
            preset.tier_ladder.get(str(original_top.get("provider", ""))),
        )
        if top_rung is not None and top_rung > caller_rung:
            # Escalating candidate keeps its OWN declared effort -- the
            # candidate is an allowed escalation, so inherited effort does not
            # override it (ROUTING-PROPOSAL.md section 4.8).
            assert escalations is not None  # narrowed by may_escalate
            escalations.consume()
            record = ClampRecord(
                role=role,
                mode=mode,
                honored=True,
                reason=(
                    f"escalation granted for role {role!r} "
                    f"(rung {top_rung} > caller rung {caller_rung})"
                ),
                caller=caller.to_dict(),
                requested_model=str(original_top.get("model", "")),
                requested_effort=_effort_of(original_top, preset),
                granted_model=str(original_top.get("model", "")),
                granted_effort=_effort_of(original_top, preset),
                escalated=True,
                escalations_remaining=escalations.remaining,
            )
            return candidates, record

    # Filter: keep every candidate at or below the caller's rung, in matrix
    # order. Nothing is invented -- these are the curator's own choices.
    kept: list[dict[str, Any]] = []
    for cand in dict_candidates:
        cand_family = str(cand.get("provider", ""))
        cand_rung = rung_of(
            str(cand.get("model", "")), preset.tier_ladder.get(cand_family)
        )
        if cand_rung is not None and cand_rung <= caller_rung:
            kept.append(cand)

    if kept:
        planned = [_with_effort(c, preset, caller.effort) for c in kept]
        top = planned[0]
        clamped = str(top.get("model", "")) != str(original_top.get("model", ""))
        record = ClampRecord(
            role=role,
            mode=mode,
            honored=True,
            reason=(
                f"{mode}: clamped to caller rung {caller_rung}"
                if clamped
                else f"{mode}: candidate already at or below caller rung {caller_rung}"
            ),
            caller=caller.to_dict(),
            requested_model=str(original_top.get("model", "")),
            requested_effort=_effort_of(original_top, preset),
            granted_model=str(top.get("model", "")),
            granted_effort=_effort_of(top, preset),
            escalations_remaining=escalations.remaining if escalations else 0,
        )
        return planned, record

    # No curated candidate sits at or below the ceiling. Substitute the
    # ladder's own rung glob for the top candidate's family -- still not an
    # invention: the preset author declared those globs as the tier order.
    sub_family = str(original_top.get("provider", ""))
    sub_ladder = preset.tier_ladder.get(sub_family) or []
    if not sub_ladder:
        record = ClampRecord(
            role=role,
            mode=mode,
            honored=False,
            reason=(
                f"no candidate at or below caller rung {caller_rung} and no "
                f"{sub_family!r} ladder to substitute from"
            ),
            caller=caller.to_dict(),
            requested_model=str(original_top.get("model", "")),
            granted_model=str(original_top.get("model", "")),
            escalations_remaining=escalations.remaining if escalations else 0,
        )
        return candidates, record if preset.report_unhonored else None

    rung_index = min(caller_rung, len(sub_ladder) - 1)
    substitute = _with_effort(
        {
            "provider": sub_family,
            "model": sub_ladder[rung_index][0],
            "config": dict(original_top.get("config") or {}),
        },
        preset,
        caller.effort,
    )
    record = ClampRecord(
        role=role,
        mode=mode,
        honored=True,
        reason=(
            f"{mode}: no curated candidate at or below caller rung "
            f"{caller_rung}; substituted the ladder rung for {sub_family!r}"
        ),
        caller=caller.to_dict(),
        requested_model=str(original_top.get("model", "")),
        requested_effort=_effort_of(original_top, preset),
        granted_model=str(substitute.get("model", "")),
        granted_effort=_effort_of(substitute, preset),
        escalations_remaining=escalations.remaining if escalations else 0,
    )
    # Substitute ONLY. If its glob does not resolve against the installed
    # provider, resolution returns empty and the child falls through to the
    # session default -- which IS the caller's own model, i.e. exactly the
    # ceiling that was asked for. Appending the originals here would be a
    # fail-OPEN that let sol back through the door this change exists to shut.
    return [substitute], record
