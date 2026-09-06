"""SCRATCH — deliberately failing test. Do not merge.

Exists only to prove that the modules/hooks-routing suite is genuinely
EXECUTED by the `Tests — modules/hooks-routing` CI job, rather than that a
pytest step merely exists in the workflow. Deleted with its branch.
"""


def test_ci_red_proof_module_suite_runs():
    assert False, "deliberate failure: proving Tests — modules/hooks-routing runs"
