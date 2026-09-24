"""Focused tests for the opt-in `routing/openai-gpt6-canary.yaml` matrix.

Companion to `microsoft-amplifier/amplifier-support#524`. This matrix is
intentionally NOT covered by `tests/test_default_resolution_unchanged.py`'s
golden-fixture byte-identity check (it is new; there is no pre-feature
recording for a file that did not exist yet -- see that test's
`EXCLUDED_FROM_RECORDING` comment). Everything that check would normally give
us for free is instead asserted here, directly, against this one file:

1. Structural shape: opt-in only, 4-rung strict ladder, exact GPT-6 ids.
2. Per-model `reasoning_effort` validation (astra vs. sol/luna allowed sets
   differ). The actual per-model rule DATA lives in the shared, repository-
   level `tests/matrix_validation_rules.yaml` (`reasoning_effort_values_by_model`)
   and is enforced for every shipped matrix by
   `tests/test_matrix_config_validation.py`; this file re-runs that same
   check scoped to just this one matrix, so a failure here points straight
   at the canary rather than at the parametrized sweep over every matrix.
3. No-catalog/no-capability-preflight behaviour for exact GPT-6 ids: they
   resolve the same way whether the provider's model catalog is missing,
   errors, or lists only near-miss strings that are NOT the clean id --
   because, per the matrix file's own "NO CATALOG/CAPABILITY PREFLIGHT"
   note, an exact (non-glob) candidate never calls `list_models()` at all.
   Near-miss strings in a catalog must never be selected in place of an
   exact id, and must never be picked up by this matrix's GLOB candidates
   either.
4. The delegation-preset cold-resolution invariant: with no caller context,
   resolution is identical whether or not the preset is attached (the same
   invariant `test_preset_bearing_matrix_is_stock_without_a_caller` checks
   for `openai.yaml`, reproduced here without touching the golden fixture).
5. The escalation-clamp behaviour the whole file exists to exercise: a
   `reasoning` sub-delegation from a caller below the `astra` rung is
   clamped down to the matrix's own second (`gpt-5.6-terra`) candidate; a
   caller already AT the `astra` rung is not. This clamp path is the ONLY
   way that second candidate is ever reached -- see the matrix file's "NO
   CATALOG/CAPABILITY PREFLIGHT" note: it is not a capability/outage
   fallback, and cold resolution (no caller context) never reaches it.
"""

from __future__ import annotations

import asyncio
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTING_DIR = REPO_ROOT / "routing"
MATRIX_PATH = ROUTING_DIR / "openai-gpt6-canary.yaml"
RULES_PATH = Path(__file__).parent / "matrix_validation_rules.yaml"

sys.path.insert(0, str(REPO_ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing.knob_consistency import (  # noqa: E402
    CANONICAL_EFFORT_KEY,
    CallerContext,
    EscalationState,
    parse_preset,
)
from amplifier_module_hooks_routing.resolver import (  # noqa: E402
    _is_glob,
    resolve_model_role,
)

# ---------------------------------------------------------------------------
# Per-model effort validation data -- READ from the repository-level rules
# file, not duplicated here. `reasoning_effort_values_by_model` in
# tests/matrix_validation_rules.yaml is the single source of truth (also
# enforced, for every shipped matrix, by
# tests/test_matrix_config_validation.py::test_reasoning_effort_values_valid_per_model).
# That file's own header documents the source (OpenAI's first-party model
# pages, per the amplifier-support#524 routing study, verified 2026-09-24).
# ---------------------------------------------------------------------------
_RULES = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
GPT_6_ALLOWED_EFFORTS: dict[str, frozenset[str]] = {
    model: frozenset(values)
    for model, values in _RULES["reasoning_effort_values_by_model"].items()
}


@lru_cache(maxsize=1)
def _load_matrix() -> dict[str, Any]:
    """The file is static for the whole test run -- read and parse it once.

    No test in this module mutates the returned dict, so callers safely
    share the cached object.
    """
    return yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))


def _roles() -> dict[str, Any]:
    return _load_matrix()["roles"]


def _gpt6_candidates() -> list[tuple[str, int, dict[str, Any]]]:
    """Every (role, index, candidate) whose model is an exact GPT-6 id."""
    out = []
    for role, role_def in _roles().items():
        for i, cand in enumerate(role_def["candidates"]):
            if cand.get("model") in GPT_6_ALLOWED_EFFORTS:
                out.append((role, i, cand))
    return out


def _providers(models: dict[str, list[str]]) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for name, model_list in models.items():
        provider = MagicMock()
        provider.list_models = AsyncMock(return_value=list(model_list))
        providers[name] = provider
    return providers


def _providers_with_erroring_catalog(names: list[str]) -> dict[str, Any]:
    """Providers whose `list_models()` raises. Used to prove exact-id
    candidates never call it (so it can never be the reason they fail)."""
    providers: dict[str, Any] = {}
    for name in names:
        provider = MagicMock()
        provider.list_models = AsyncMock(
            side_effect=RuntimeError(f"{name}: simulated catalog fetch failure")
        )
        providers[name] = provider
    return providers


# A roster that mounts every model this matrix can select, so a cold
# resolution always finds its top candidate rather than falling through.
FULL_OPENAI_ROSTER = [
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
]

# A catalog that lists near-miss strings for every GPT-6 id -- close enough
# to look like a stale/wrong entry -- but never the three clean ids
# themselves, and never any 5.6-family id either. Used to prove (a) exact
# GPT-6 candidates resolve to the clean id regardless (no catalog dependency
# at all) and (b) this matrix's glob candidates (`gpt-?.?-terra`,
# `gpt-?.?-luna`) never accidentally match a GPT-6-shaped near-miss.
NEAR_MISS_ONLY_ROSTER = [
    "gpt-6-astra-preview",
    "gpt-6-astra-fast",
    "gpt-60-astra",
    "gpt-6-sol-fast",
    "gpt-6-sol-mini",
    "gpt-6-luna-fast",
    "gpt-6-luna-mini",
]

# A roster that has NO models at all for the provider -- distinct from a
# catalog error: this is what an empty-but-successful list_models() call
# returns, per openai.yaml's own documented "if that call fails, the glob
# resolves to nothing" behaviour for GLOB candidates. Exact ids must not
# share that fate.
EMPTY_ROSTER: list[str] = []


# ---------------------------------------------------------------------------
# 1. Structural shape
# ---------------------------------------------------------------------------


def test_matrix_file_exists_and_parses() -> None:
    assert MATRIX_PATH.exists(), f"missing {MATRIX_PATH}"
    data = _load_matrix()
    assert data is not None
    assert "roles" in data


def test_is_not_the_default_matrix() -> None:
    """This canary must never become anyone's default silently."""
    behaviour = yaml.safe_load(
        (REPO_ROOT / "behaviors" / "routing.yaml").read_text(encoding="utf-8")
    )
    declared = [
        hook.get("config", {}).get("default_matrix")
        for hook in behaviour.get("hooks", [])
        if hook.get("module") == "hooks-routing"
    ]
    assert "openai-gpt6-canary" not in declared, (
        "openai-gpt6-canary must stay opt-in; behaviors/routing.yaml must "
        "not default to it"
    )


def test_ships_a_preset_with_strict_inherit_and_four_rungs() -> None:
    data = _load_matrix()
    assert "preset" in data, "openai-gpt6-canary.yaml must carry a preset: block"
    parsed = parse_preset(data)
    assert parsed is not None
    assert parsed.inherit == "strict"
    rungs = parsed.tier_ladder["openai"]
    assert len(rungs) == 4, f"expected a 4-rung ladder, got {len(rungs)}: {rungs}"
    # Astra sits ALONE on the top rung -- the deviation from the study's
    # guidance the matrix file documents under "WHY A FOURTH RUNG".
    assert rungs[-1] == ["gpt-6-astra"]
    assert "gpt-6-sol" in rungs[2]
    assert "gpt-6-luna" in rungs[0]


def test_gpt6_model_ids_are_exact_no_globs() -> None:
    """No GPT-6 candidate may use a glob -- see the file header: the family
    has no numeric sub-version and no dated snapshots to glob over."""
    for role, i, cand in [
        (role, i, cand)
        for role, role_def in _roles().items()
        for i, cand in enumerate(role_def["candidates"])
    ]:
        model = cand.get("model", "")
        if model.startswith("gpt-6"):
            assert model in GPT_6_ALLOWED_EFFORTS, (
                f"{role}[{i}]: {model!r} is a gpt-6* id but not one of the "
                f"three known exact ids {sorted(GPT_6_ALLOWED_EFFORTS)}"
            )
            assert not _is_glob(model), (
                f"{role}[{i}]: GPT-6 candidate {model!r} must be an exact id, "
                "not a glob"
            )


def test_canary_scope_is_exactly_fast_coding_reasoning() -> None:
    """Only these three roles may select a GPT-6 model; every other role
    stays on the pre-existing gpt-5.6-terra/-luna candidates."""
    roles = _roles()
    gpt6_roles = {
        role
        for role, role_def in roles.items()
        if any(c.get("model") in GPT_6_ALLOWED_EFFORTS for c in role_def["candidates"])
    }
    assert gpt6_roles == {"fast", "coding", "reasoning"}


def test_fast_and_coding_have_exactly_one_candidate_reasoning_has_two() -> None:
    """The documented asymmetry: `reasoning` keeps the pre-existing
    gpt-5.6-terra candidate as an explicit second candidate (reachable only
    via the strict clamp -- see module docstring point 5, and
    TestEscalationClamp below); `fast` and `coding` do not have a second
    candidate of any kind, because one would be equally unreachable by
    ordinary resolution and would misleadingly read as a fallback that does
    not exist -- see the matrix file's "NO CATALOG/CAPABILITY PREFLIGHT"
    note."""
    roles = _roles()
    assert len(roles["fast"]["candidates"]) == 1
    assert roles["fast"]["candidates"][0]["model"] == "gpt-6-luna"

    assert len(roles["coding"]["candidates"]) == 1
    assert roles["coding"]["candidates"][0]["model"] == "gpt-6-sol"

    reasoning_models = [c["model"] for c in roles["reasoning"]["candidates"]]
    assert reasoning_models[0] == "gpt-6-astra"
    assert "gpt-?.?-terra" in reasoning_models[1:]


# ---------------------------------------------------------------------------
# 2. Per-model effort validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,index,candidate",
    _gpt6_candidates(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_gpt6_candidates_use_a_model_valid_effort(
    role: str, index: int, candidate: dict[str, Any]
) -> None:
    model = candidate["model"]
    effort = (candidate.get("config") or {}).get(CANONICAL_EFFORT_KEY)
    allowed = GPT_6_ALLOWED_EFFORTS[model]
    assert effort is not None, f"{role}[{index}] ({model}): no {CANONICAL_EFFORT_KEY} set"
    assert effort in allowed, (
        f"{role}[{index}]: reasoning_effort={effort!r} is not valid for "
        f"{model!r} (allowed: {sorted(allowed)})"
    )


def test_astra_candidate_does_not_use_none() -> None:
    """Regression guard named directly: `none` is valid for sol/luna but NOT
    for astra -- a future edit that moves `reasoning` to `none` on astra must
    fail here, not go silently inert on the wire."""
    roles = _roles()
    astra_candidate = roles["reasoning"]["candidates"][0]
    assert astra_candidate["model"] == "gpt-6-astra"
    assert astra_candidate["config"][CANONICAL_EFFORT_KEY] != "none"


# ---------------------------------------------------------------------------
# 3. No catalog / no capability preflight -- missing, erroring, and
#    near-miss-only catalogs all resolve exact GPT-6 ids identically.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,expected_model",
    [("fast", "gpt-6-luna"), ("coding", "gpt-6-sol"), ("reasoning", "gpt-6-astra")],
)
def test_exact_gpt6_ids_resolve_with_an_empty_catalog(
    role: str, expected_model: str
) -> None:
    """`list_models()` returning an empty (but successful) list must not
    affect an exact-id candidate -- unlike a glob, which would resolve to
    nothing (see openai.yaml's own documented degrade path for globs)."""
    roles = _roles()
    providers = _providers({"openai": EMPTY_ROSTER})
    result = asyncio.run(resolve_model_role([role], roles, providers))
    assert result, f"role {role!r} resolved to nothing with an empty catalog"
    assert result[0]["model"] == expected_model


@pytest.mark.parametrize(
    "role,expected_model",
    [("fast", "gpt-6-luna"), ("coding", "gpt-6-sol"), ("reasoning", "gpt-6-astra")],
)
def test_exact_gpt6_ids_resolve_when_list_models_raises(
    role: str, expected_model: str
) -> None:
    """`list_models()` raising must not affect an exact-id candidate. This
    is the direct proof of the matrix file's central claim: `list_models()`
    is never even CALLED for a non-glob candidate, so its failure mode is
    structurally unreachable for `fast`/`coding`/`reasoning`'s top
    candidate. If this ever starts calling `list_models()` for an exact id,
    this test fails with the injected RuntimeError instead of silently
    passing."""
    roles = _roles()
    providers = _providers_with_erroring_catalog(["openai"])
    result = asyncio.run(resolve_model_role([role], roles, providers))
    assert result, f"role {role!r} resolved to nothing when list_models() raised"
    assert result[0]["model"] == expected_model
    providers["openai"].list_models.assert_not_called()


@pytest.mark.parametrize(
    "role,expected_model",
    [("fast", "gpt-6-luna"), ("coding", "gpt-6-sol"), ("reasoning", "gpt-6-astra")],
)
def test_exact_gpt6_ids_resolve_to_the_clean_id_with_a_near_miss_only_catalog(
    role: str, expected_model: str
) -> None:
    """A catalog full of near-miss strings for every GPT-6 id (`-preview`,
    `-fast`, `-mini`, a digit near-miss) but never the clean id itself must
    not change the result: the exact candidate resolves to the CLEAN id it
    names, never to a near-miss, because no matching against the catalog
    happens for it at all."""
    roles = _roles()
    providers = _providers({"openai": NEAR_MISS_ONLY_ROSTER})
    result = asyncio.run(resolve_model_role([role], roles, providers))
    assert result, f"role {role!r} resolved to nothing with a near-miss-only catalog"
    assert result[0]["model"] == expected_model
    assert result[0]["model"] not in NEAR_MISS_ONLY_ROSTER


def test_glob_candidates_never_match_a_gpt6_near_miss() -> None:
    """The OTHER half of the near-miss guarantee: this matrix's glob
    candidates (`gpt-?.?-terra`, `gpt-?.?-luna`, used by every non-canaried
    role) must not accidentally select a GPT-6-shaped near-miss string if
    one happens to be present in the catalog alongside legitimate 5.6-family
    ids. `gpt-?.?-terra`/`gpt-?.?-luna` require a literal '.' after a single
    version-digit character; none of the GPT-6 near-miss ids have that
    shape, so none should ever satisfy the glob."""
    roles = _roles()
    mixed_roster = NEAR_MISS_ONLY_ROSTER + ["gpt-5.6-terra", "gpt-5.6-luna"]
    providers = _providers({"openai": mixed_roster})

    async def _run() -> dict[str, Any]:
        return {
            role: await resolve_model_role([role], roles, providers)
            for role in ("general", "ui-coding", "critique")
        }

    resolved = asyncio.run(_run())
    for role, result in resolved.items():
        assert result, f"role {role!r} resolved to nothing"
        assert result[0]["model"] in ("gpt-5.6-terra", "gpt-5.6-luna"), (
            f"role {role!r} resolved to {result[0]['model']!r}, "
            "which looks like it matched a GPT-6 near-miss string"
        )
        assert result[0]["model"] not in NEAR_MISS_ONLY_ROSTER


def test_reasoning_candidates_never_call_list_models_cold() -> None:
    """Cold resolution (no caller context) of `reasoning` must not touch
    `list_models()` at all: BOTH its candidates -- `gpt-6-astra` (the one
    that always wins cold) and `gpt-5.6-terra` (never reached cold, see
    module docstring point 5) -- are either an exact id or never evaluated,
    so the erroring mock must never be invoked."""
    roles = _roles()
    providers = _providers_with_erroring_catalog(["openai"])
    result = asyncio.run(resolve_model_role(["reasoning"], roles, providers))
    assert result and result[0]["model"] == "gpt-6-astra"
    providers["openai"].list_models.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Cold-resolution / preset-is-opt-in-twice invariant
# ---------------------------------------------------------------------------


def test_cold_resolution_is_unchanged_by_the_preset() -> None:
    """No caller context: resolving with the parsed preset attached must
    equal resolving with no preset at all. Reproduces, for this one new
    matrix, the same invariant
    test_preset_bearing_matrix_is_stock_without_a_caller checks for
    openai.yaml -- without depending on that test's golden fixture, since
    this matrix was never in the pre-feature recording."""
    data = _load_matrix()
    roles = data["roles"]
    parsed = parse_preset(data)
    assert parsed is not None

    async def _resolve_all(preset: Any) -> dict[str, Any]:
        return {
            role: await resolve_model_role(
                [role],
                roles,
                _providers({"openai": FULL_OPENAI_ROSTER}),
                preset=preset,
                caller_context=None,
            )
            for role in roles
        }

    without = asyncio.run(_resolve_all(None))
    with_preset = asyncio.run(_resolve_all(parsed))
    assert with_preset == without


def test_every_non_exempt_role_resolves_with_the_full_roster() -> None:
    """Sanity: with every GPT-6/5.6 model mounted, no role silently yields
    nothing (mirrors tests/test_single_provider_coverage.py's intent for
    this one opt-in matrix, which that file does not cover since it is
    parametrized over the shipped matrix names, not a glob)."""
    roles = _roles()
    providers = _providers({"openai": FULL_OPENAI_ROSTER})

    async def _run() -> dict[str, Any]:
        return {
            role: await resolve_model_role([role], roles, providers) for role in roles
        }

    resolved = asyncio.run(_run())
    unresolved = {r for r, got in resolved.items() if not got}
    assert not unresolved, f"roles with no resolution: {sorted(unresolved)}"


# ---------------------------------------------------------------------------
# 5. Escalation clamp -- the point of the exercise
# ---------------------------------------------------------------------------

TERRA_CALLER = CallerContext(
    family="openai", model="gpt-5.6-terra", effort="medium", provider_key="terra"
)
SOL_CALLER = CallerContext(
    family="openai", model="gpt-5.6-sol", effort="high", provider_key="sol"
)
ASTRA_CALLER = CallerContext(
    family="openai", model="gpt-6-astra", effort="high", provider_key="astra"
)


def _resolve_reasoning(caller: CallerContext | None) -> list[dict[str, Any]]:
    data = _load_matrix()
    roles = data["roles"]
    preset = parse_preset(data)
    providers = _providers({"openai": FULL_OPENAI_ROSTER})
    return asyncio.run(
        resolve_model_role(
            ["reasoning"],
            roles,
            providers,
            caller_context=caller,
            preset=preset,
            escalations=EscalationState(),
        )
    )


def test_reasoning_clamps_to_terra_for_a_terra_tier_caller() -> None:
    """A caller resolved to gpt-5.6-terra (rung 2 of 4) must not be able to
    delegate a sub-agent onto gpt-6-astra (rung 4) -- strict inherit denies
    the escalation and the sub-agent lands on the matrix's own second
    (`gpt-5.6-terra`) candidate instead. This is the one and only path that
    reaches that second candidate at all -- see module docstring point 5."""
    result = _resolve_reasoning(TERRA_CALLER)
    assert result
    assert result[0]["model"] == "gpt-5.6-terra"


def test_reasoning_clamps_to_sol_rung_for_a_sol_tier_caller() -> None:
    """A caller at rung 3 (sol) is still below astra's rung 4 and must also
    be denied the escalation."""
    result = _resolve_reasoning(SOL_CALLER)
    assert result
    assert result[0]["model"] != "gpt-6-astra"


def test_reasoning_lands_on_astra_for_an_astra_tier_caller() -> None:
    """A caller already AT the top rung is not a clamp target: `reasoning`
    resolves to its own top candidate, gpt-6-astra, unchanged."""
    result = _resolve_reasoning(ASTRA_CALLER)
    assert result
    assert result[0]["model"] == "gpt-6-astra"
