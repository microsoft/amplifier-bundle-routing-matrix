"""Validation for candidate `config:` maps in every shipped routing matrix.

Prevents recurrence of two silent-failure bug classes:

1. Non-canonical effort keys (`effort`, `thinking_effort`, ...) that some
   providers read and others silently ignore. The single canonical spelling
   is `reasoning_effort`.
2. Invalid values (e.g. the historical `reasoning_effort: extra_high`) that
   providers warn about and ignore, leaving the candidate's setting inert.

Allowed keys and per-provider value sets are DATA in
tests/matrix_validation_rules.yaml -- extend them there, not here.
"""

import sys
import yaml
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ROUTING_DIR = REPO_ROOT / "routing"
RULES_PATH = Path(__file__).parent / "matrix_validation_rules.yaml"

sys.path.insert(0, str(REPO_ROOT / "modules" / "hooks-routing"))
from amplifier_module_hooks_routing.resolver import _is_glob  # noqa: E402

RULES = yaml.safe_load(RULES_PATH.read_text())
CANONICAL_EFFORT_KEY = RULES["canonical_effort_key"]
EFFORT_VALUES_BY_PROVIDER = RULES["reasoning_effort_values"]
EFFORT_VALUES_BY_MODEL = RULES.get("reasoning_effort_values_by_model", {})

MATRIX_FILES = sorted(ROUTING_DIR.glob("*.yaml"))


def iter_candidates(matrix_path):
    """Yield (role, index, candidate) for every candidate in a matrix file."""
    data = yaml.safe_load(matrix_path.read_text())
    for role, role_def in (data.get("roles") or {}).items():
        for i, candidate in enumerate(role_def.get("candidates") or []):
            yield role, i, candidate


def test_matrices_exist():
    """Sanity: the glob found the shipped matrices (guards against dir moves)."""
    assert MATRIX_FILES, f"No matrix files found in {ROUTING_DIR}"


@pytest.mark.parametrize("matrix_path", MATRIX_FILES, ids=lambda p: p.name)
class TestMatrixConfigValidation:
    """Every shipped matrix passes all three config-hygiene checks."""

    def test_effort_keys_are_canonical(self, matrix_path):
        """(a) Any effort-family key must be spelled exactly `reasoning_effort`.

        Catches legacy/mixed spellings (`effort`, `thinking_effort`,
        `reasoning-effort`, ...) that are inert on some providers.
        """
        violations = []
        for role, i, cand in iter_candidates(matrix_path):
            for key in cand.get("config") or {}:
                if "effort" in key.lower() and key != CANONICAL_EFFORT_KEY:
                    violations.append(
                        f"{role}[{i}] ({cand.get('provider')}/{cand.get('model')}): "
                        f"key {key!r} must be {CANONICAL_EFFORT_KEY!r}"
                    )
        assert not violations, (
            f"{matrix_path.name}: non-canonical effort keys found:\n  "
            + "\n  ".join(violations)
        )

    def test_reasoning_effort_values_valid_per_provider(self, matrix_path):
        """(b) `reasoning_effort` values come from the provider's allowed set.

        Providers silently warn+ignore unknown values, so an invalid value
        (like the historical `extra_high`) makes the setting inert. Unknown
        providers fail loudly: add their documented set to
        tests/matrix_validation_rules.yaml.
        """
        violations = []
        for role, i, cand in iter_candidates(matrix_path):
            value = (cand.get("config") or {}).get(CANONICAL_EFFORT_KEY)
            if value is None:
                continue
            provider = cand.get("provider")
            allowed = EFFORT_VALUES_BY_PROVIDER.get(provider)
            if allowed is None:
                violations.append(
                    f"{role}[{i}]: provider {provider!r} has no entry in "
                    f"reasoning_effort_values -- add its documented set to "
                    f"{RULES_PATH.name}"
                )
            elif value not in allowed:
                violations.append(
                    f"{role}[{i}] ({provider}/{cand.get('model')}): "
                    f"reasoning_effort={value!r} not in allowed set {allowed} "
                    f"for provider {provider!r}"
                )
        assert not violations, (
            f"{matrix_path.name}: invalid reasoning_effort values:\n  "
            + "\n  ".join(violations)
        )

    def test_reasoning_effort_values_valid_per_model(self, matrix_path):
        """(c) A narrower, per-MODEL allowed set overrides the provider-wide
        superset for any EXACT (non-glob) model id listed in
        tests/matrix_validation_rules.yaml's `reasoning_effort_values_by_model`.

        The provider-wide check above cannot catch this class: e.g.
        `gpt-6-astra` and `gpt-6-sol` are both `provider: openai` and both
        pass the provider-wide superset for `none`, but `gpt-6-astra`
        rejects `none` at the provider while `gpt-6-sol` accepts it. Only a
        model-keyed table can tell them apart. Glob candidates are
        deliberately excluded -- a glob can resolve to more than one
        concrete model, so only an exact id is checked here.
        """
        violations = []
        for role, i, cand in iter_candidates(matrix_path):
            model = cand.get("model")
            if not isinstance(model, str) or _is_glob(model):
                continue  # glob candidate -- not checked per-model
            allowed = EFFORT_VALUES_BY_MODEL.get(model)
            if allowed is None:
                continue  # no per-model rule for this id -- provider-wide check covers it
            value = (cand.get("config") or {}).get(CANONICAL_EFFORT_KEY)
            if value is not None and value not in allowed:
                violations.append(
                    f"{role}[{i}] ({cand.get('provider')}/{model}): "
                    f"reasoning_effort={value!r} not in the model-specific "
                    f"allowed set {allowed} for {model!r} "
                    f"(reasoning_effort_values_by_model in {RULES_PATH.name})"
                )
        assert not violations, (
            f"{matrix_path.name}: invalid per-model reasoning_effort values:\n  "
            + "\n  ".join(violations)
        )
