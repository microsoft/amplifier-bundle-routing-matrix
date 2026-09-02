"""Regression lock on the `reasoning` role's OpenAI reasoning-effort pin.

`model_role=reasoning` routes to the OpenAI flagship (`sol`) tier at
`reasoning_effort: xhigh`. That value is now a MEASURED default, not an
inherited one, and these tests stop it drifting to `max` unnoticed.

Evidence (LEAD-6, item `model_performance-bm1`, spend $0.25, 2026-09-02):
`xhigh` and `max` were compared head-to-head on gpt-5.6-sol, n=5/arm, 10
interleaved requests, all raw wire fields. They are NOT SEPARABLE:

    reasoning_tokens  max:xhigh = 1.091   (mean 806.4 vs 739.0)
    wall clock        max:xhigh = 1.068   (mean 14.36s vs 13.44s)
    cost/request      max:xhigh = 1.084

All three land near 1.0, far under the pre-registered 1.5x gate -- and
within-arm spread EXCEEDS the between-arm difference (xhigh 565-980 = 1.73x,
max 463-1110 = 2.40x, ranges fully overlapping). Both the cheapest and the
most expensive request in the whole probe were `max` requests.
`response.reasoning.effort` echoed the requested value 10/10, so `max` is
genuinely accepted by the deployment rather than silently coerced -- the null
is real, not an artefact of a rejected parameter.

What this does NOT assert: that `xhigh` is BETTER than `max`. No quality claim
is made or implied (quality remains blocked on cb2), and the probe covers one
short single-turn shape at n=5. The pin is de-risking -- `max` is an
unbounded-latency default that buys nothing measurable on the shape we could
measure. Re-raising this role to `max` needs NEW evidence, not a preference.

Source: `probes/lead6-xhigh-vs-max/FINDINGS.md` (evals repo); raw captures
under `.amplifier/evaluation/treatment-validation/20260902-bm1/`.

Scope note: both checks are deliberately scoped to OpenAI candidates, because
the measurement above is an OpenAI-only measurement. Anthropic, Gemini and
Copilot candidates of the same role are out of this evidence's reach and are
not constrained here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
ROUTING_DIR = REPO_ROOT / "routing"

# Use the bundle's own loader rather than a bare yaml.safe_load, so this test
# exercises the same parse path the runtime resolver uses. The module is not
# pip-installed in the repo-level test env; add its source dir explicitly so
# this file also passes when run on its own.
sys.path.insert(0, str(REPO_ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing.matrix_loader import load_matrix  # noqa: E402

MATRIX_FILES = sorted(ROUTING_DIR.glob("*.yaml"))

# The effort the measurement licenses, and the one it rules out as unjustified.
EXPECTED_EFFORT = "xhigh"
REJECTED_EFFORT = "max"

# Flagship OpenAI tier the reasoning role targets. Matched as a substring so
# the tier-suffix globs (`gpt-?.?-sol*`) and any exact pin both count.
FLAGSHIP_MARKER = "sol"


def reasoning_openai_candidates(matrix_path: Path):
    """Yield (index, candidate) for each OpenAI candidate of the reasoning role."""
    matrix = load_matrix(matrix_path)
    role = (matrix.get("roles") or {}).get("reasoning")
    if not role:
        return
    for i, candidate in enumerate(role.get("candidates") or []):
        if candidate.get("provider") == "openai":
            yield i, candidate


def test_matrices_exist():
    """Sanity: the glob found the shipped matrices (guards against dir moves)."""
    assert MATRIX_FILES, f"No matrix files found in {ROUTING_DIR}"


def test_at_least_one_matrix_routes_reasoning_to_openai_flagship():
    """Guard the guard: the checks below must not pass vacuously.

    If every OpenAI flagship candidate were deleted from the reasoning role,
    `test_reasoning_flagship_pins_xhigh` would pass while asserting nothing.
    """
    covered = [
        p.name
        for p in MATRIX_FILES
        if any(
            FLAGSHIP_MARKER in str(c.get("model", ""))
            for _, c in reasoning_openai_candidates(p)
        )
    ]
    assert covered, (
        "No shipped matrix routes model_role=reasoning to an OpenAI flagship "
        "(sol) candidate -- the xhigh pin below is asserting nothing. If the "
        "flagship tier was intentionally renamed, update FLAGSHIP_MARKER."
    )


@pytest.mark.parametrize("matrix_path", MATRIX_FILES, ids=lambda p: p.name)
def test_reasoning_role_never_pins_max_on_openai(matrix_path):
    """No OpenAI candidate of `reasoning` may pin `reasoning_effort: max`.

    `max` was measured against `xhigh` and found not separable on cost,
    latency or reasoning-token spend, while carrying an unbounded-latency
    reputation. It is not banned as a value (the validation rules still allow
    it for candidates whose own evidence supports it) -- it is banned for
    THIS role, on THIS provider, because the measurement says it buys nothing.
    """
    violations = [
        f"reasoning[{i}] ({cand.get('provider')}/{cand.get('model')}): "
        f"reasoning_effort={REJECTED_EFFORT!r}"
        for i, cand in reasoning_openai_candidates(matrix_path)
        if (cand.get("config") or {}).get("reasoning_effort") == REJECTED_EFFORT
    ]
    assert not violations, (
        f"{matrix_path.name}: model_role=reasoning pins the unjustified "
        f"{REJECTED_EFFORT!r} effort on an OpenAI candidate:\n  "
        + "\n  ".join(violations)
        + f"\n\nMeasured not separable from {EXPECTED_EFFORT!r} "
        "(LEAD-6/model_performance-bm1, n=5/arm: reasoning_tokens 1.091x, "
        "wall 1.068x, cost 1.084x, all under the 1.5x gate). Raising this "
        "role back to 'max' requires new evidence -- see this file's docstring."
    )


@pytest.mark.parametrize("matrix_path", MATRIX_FILES, ids=lambda p: p.name)
def test_reasoning_flagship_pins_xhigh(matrix_path):
    """Every OpenAI flagship (`sol`) candidate of `reasoning` pins `xhigh`.

    Absent is a failure too: with no `reasoning_effort` the request inherits
    whatever the resolved provider INSTANCE defaults to, which is exactly how
    a `sol` candidate ends up running at `max` without any matrix saying so.
    """
    violations = []
    for i, cand in reasoning_openai_candidates(matrix_path):
        if FLAGSHIP_MARKER not in str(cand.get("model", "")):
            continue
        effort = (cand.get("config") or {}).get("reasoning_effort")
        if effort != EXPECTED_EFFORT:
            violations.append(
                f"reasoning[{i}] (openai/{cand.get('model')}): "
                f"reasoning_effort={effort!r}, expected {EXPECTED_EFFORT!r}"
            )
    assert not violations, (
        f"{matrix_path.name}: OpenAI flagship candidate(s) of "
        f"model_role=reasoning do not pin {EXPECTED_EFFORT!r}:\n  "
        + "\n  ".join(violations)
        + "\n\nAn unpinned candidate silently inherits the provider "
        "instance's own default effort. See this file's docstring for the "
        "measurement that fixed this value."
    )
