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

import yaml
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ROUTING_DIR = REPO_ROOT / "routing"
RULES_PATH = Path(__file__).parent / "matrix_validation_rules.yaml"

RULES = yaml.safe_load(RULES_PATH.read_text())
CANONICAL_EFFORT_KEY = RULES["canonical_effort_key"]
ALLOWED_CONFIG_KEYS = set(RULES["allowed_config_keys"])
EFFORT_VALUES_BY_PROVIDER = RULES["reasoning_effort_values"]

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

    def test_config_keys_in_allowlist(self, matrix_path):
        """(c) Every candidate config key is a known key.

        Catches typos and unsupported knobs -- providers pass unknown config
        through or ignore it, so a misspelled key fails silently at runtime.
        New legitimate keys go in tests/matrix_validation_rules.yaml.
        """
        violations = []
        for role, i, cand in iter_candidates(matrix_path):
            for key in cand.get("config") or {}:
                if key not in ALLOWED_CONFIG_KEYS:
                    violations.append(
                        f"{role}[{i}] ({cand.get('provider')}/{cand.get('model')}): "
                        f"unknown config key {key!r} (allowed: {sorted(ALLOWED_CONFIG_KEYS)})"
                    )
        assert not violations, (
            f"{matrix_path.name}: unknown config keys found:\n  "
            + "\n  ".join(violations)
        )
