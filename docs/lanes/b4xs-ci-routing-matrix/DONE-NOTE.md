# DONE-NOTE — `model_performance-b4xs`: CI for amplifier-bundle-routing-matrix

**Lane:** `b4xs-ci-routing-matrix` · **Branch:** `lane/b4xs-ci-routing-matrix`
**Outcome:** **A. RESOLVED** — every deliverable DONE. No cap-bound NOT-POSSIBLE.
**Spend:** **$0.00 of $0.00** authority. Zero API calls, zero DTU launches, zero
containers, zero infrastructure rows registered. GitHub Actions minutes only.
**Date:** 2026-09-06

---

## Result in one line

`microsoft/amplifier-bundle-routing-matrix` had **no `.github/workflows/` at all**; it now
has a four-job CI that was **observed red before it was observed green**, and the red run
proves `modules/hooks-routing`'s **590 tests actually execute** rather than merely that a
pytest step exists in the YAML.

---

## Deliverables

| # | Deliverable | State |
|---|---|---|
| 1 | `.github/workflows/ci.yml` on push+PR: ruff, per-`modules/*` tests, cheap bundle-structure parse | **DONE** |
| 2 | Evidence that `modules/hooks-routing`'s tests ran and passed in CI — job named, count named | **DONE** |
| 3 | RED run URL and GREEN run URL, both quoted in the real PR body | **DONE** |
| 4 | Workflow only (+ minimal fixes if genuinely required); STOP-and-report if clean main is red | **DONE** — 2 minimal fixes, both named below |
| 5 | No `validate-bundle-repo` in CI | **DONE** — not wired; reason recorded in the workflow comment |

**Publication:** draft PR **#65** → marked ready when green.
<https://github.com/microsoft/amplifier-bundle-routing-matrix/pull/65>

---

## The non-negotiable gate: proof the CI can go red

Method: the workflow was pushed on scratch branch `scratch/b4xs-ci-red-proof` carrying two
deliberately failing tests — one under `modules/hooks-routing/tests/`, one under `tests/` —
so a single run would prove **both** test jobs execute. Draft PR **#64** was opened, the run
observed, then the PR closed and the branch deleted from `origin`.

**RED run:** <https://github.com/microsoft/amplifier-bundle-routing-matrix/actions/runs/34062081727>
(`pull_request`, head `4f7e123b686eaec70ed8fcd6ed06dea995ac33ba`, conclusion `failure`)

| Job | Result | Log evidence |
|---|---|---|
| `Tests — modules/hooks-routing` | **FAILURE** | `1 failed, 590 passed in 3.30s` |
| `Tests — root (Python 3.11)` | **FAILURE** | `1 failed, 39 passed in 4.78s` |
| `Tests — root (Python 3.12)` | **FAILURE** | `1 failed, 39 passed in 2.19s` |
| `Tests — root (Python 3.13)` | **FAILURE** | `1 failed, 39 passed in 2.83s` |
| `Lint (ruff)` | SUCCESS | `All checks passed!` |
| `Bundle structure` | SUCCESS | `OK -- bundle structure checks passed` |

Two things make this a real proof rather than a ceremony:

1. `1 failed, **590 passed**` names the count. A workflow with a wrong test directory or a
   swallowed exit code would have reported `no tests ran` — or exit 0 — and looked identical
   on a green PR.
2. `Lint` and `Bundle structure` stayed **green in the same run**, so the red is attributable
   to the failing tests and not to the workflow falling over.

**GREEN run (workflow commit `bcbf0df`):**
<https://github.com/microsoft/amplifier-bundle-routing-matrix/actions/runs/34062187453>
— **6/6 jobs success**, module job `590 passed in 3.24s`, `runtime deps OK`.

The head-SHA green run (this commit, which adds the lane artifacts) is quoted in the PR body
alongside it.

Raw evidence: `evidence/red-run-34062081727.json`,
`evidence/red-run-job-modules-hooks-routing.log`, `evidence/green-run-34062187453.json`,
`evidence/green-run-job-modules-hooks-routing.log`, `evidence/local-clean-room.txt`.

---

## What the template dictated

Template: `microsoft/amplifier-bundle-context-intelligence/.github/workflows/ci.yml`.
It handles `modules/` subpackages by **per-module install + pytest** — each module owns its
own `uv.lock`, each gets its own matrix leg, `working-directory: modules/<name>`, `uv sync
--frozen` — with a **separate** root-suite job across Python 3.11/3.12/3.13, and a `lint` job.
**Not a workspace.** This PR follows that shape exactly.

The one structural difference: context-intelligence has a root `pyproject.toml` + `uv.lock`
(it ships an importable `context_intelligence` package). routing-matrix has neither — it is a
bundle, and only `modules/*` are installable. So the root job runs in an ephemeral uv
environment with its three real dependencies (`pytest`, `pytest-asyncio`, `pyyaml`), which is
sufficient: `tests/test_default_resolution_unchanged.py` reaches the module through a
`sys.path` insert of its own.

---

## Findings worth keeping

### 1. `uv run --with X pytest` silently runs WITHOUT X — use `python -m pytest`

Measured on this host at **uv 0.12.6**, same tree, same flags:

```
uv run --frozen --extra dev --with git+…/amplifier-foundation pytest   -> 574 passed, 14 failed, 2 skipped
uv run --frozen --extra dev --with git+…/amplifier-foundation python -m pytest -> 590 passed
```

The `pytest` **console script** does not see the `--with` overlay; `python -m pytest` does.
This repo's own committed lane evidence
(`docs/lanes/bounded-role-resolution-fanout/evidence/suite-after.txt`) records the console-script
form producing `590 passed`, so the behaviour changed under it at some uv version. Anyone
copying that documented command into a new context today gets 14 failures that have nothing to
do with their change.

### 2. "ruff's default rules" is a moving target — pin the version

Same tree, same `check --isolated .`:

| ruff | findings |
|---|---|
| `0.15.11` (what the sibling repo's lockfile resolves to) | **2** |
| `latest` | **28** |

An unpinned linter turns an unrelated upstream release into a red PR nobody caused. CI pins
`ruff@0.15.11`; a new root `ruff.toml` additionally stops ruff walking up the filesystem and
picking up an unrelated parent-directory config — the mechanism by which a local run and a CI
run come to disagree about which rules are even enabled.

### 3. Two tests would have SKIPPED silently on a botched dependency install

`modules/hooks-routing/tests/test_resume_lifecycle.py:271` and
`test_role_pin_fidelity.py:605` guard themselves with `pytest.importorskip`. Without
`amplifier-foundation` the suite reports `574 passed, 2 skipped` — green-looking, 16 tests
short. The workflow therefore carries an explicit
`import amplifier_foundation.spawn_utils, amplifier_core.session` step that converts that
silent skip into a red run. (foundation is a runtime dep resolved by amplifier's module
system, so it is absent from `uv.lock` on purpose.)

### 4. Clean `main` was NOT red in tests — it was red in lint, twice, and both were real

The goal said STOP-and-report if the suite is red on clean main in CI. The **test suites were
green** on clean main (590 + 39, verified locally before writing any YAML). `ruff check` was
red, with exactly two findings, and both are genuine defects rather than style noise:

- `matrix_loader.py:352` **F402** — the loop variable `field` shadowed the `field` imported
  from `dataclasses` at module scope. Renamed to `cfg_field`; no behaviour change, suite
  still 590 green.
- `test_matrix_loader.py:5` **F401** — unused `import textwrap`.

Nothing was silenced: no `continue-on-error`, no narrowed test selection, no `noqa`.

---

## Decisions taken without asking (per SCOPE-OUTS: choose, record, continue)

1. **`ruff format --check` is NOT wired.** This repo has never been ruff-formatted; at
   `0.15.11` defaults the formatter would rewrite **14 files / ~137 lines**. That is a pure
   whitespace normalisation — mechanical (`uvx ruff@0.15.11 format .`) but it does not belong
   in the PR that introduces CI, where it would collide with every in-flight branch. Recorded
   as a named omission in the workflow's own comment at the point of omission, and in the PR
   body, so the next contributor sees a decision rather than an oversight.
2. **`routing/*.yaml` is included in the structure check** (syntax parse only) beyond the
   `bundle.md` + `behaviors/*.yaml` the goal named. It costs nothing and the *semantics* are
   already covered by `tests/test_matrix_config_validation.py`, which is stricter.
3. **The structure check lives in a committed script**, `.github/scripts/check_bundle_structure.py`,
   rather than an inline `python -c`. Same cost, and a contributor can run the identical
   command locally — the goal's own warning about CI and local drifting apart.
4. **`amplifier-foundation` is installed from `git+…@main`, unpinned**, matching the command
   this repo's own lane evidence already documents for local runs. An upstream foundation
   change can therefore redden this repo's CI. Flagged to the maintainers in the PR body as a
   judgement call rather than decided here.
5. **Ubuntu only.** The goal warned about the cross-platform defect class (a backslash-`a`
   becoming BEL in interpolated source; `str(Path.relative_to(...))` emitting OS-native
   separators) and said to add macOS/Windows only if the sibling template does. It does not,
   so this does not. The structure script nonetheless avoids both traps by construction: it
   resolves paths relative to its own location rather than interpolating them into source, and
   reports with `.as_posix()`.
6. **The bundle-structure script treats an empty glob as a FAILURE.** A check reporting
   "0 problems in 0 files" with exit 0 is indistinguishable from a working one — the exact
   defect class this program has already been bitten by.

---

## Spend ledger

| Item | Authorised | Spent |
|---|---|---|
| API calls | $0.00 | **$0.00** — none made |
| DTU / containers | $0.00 | **$0.00** — none launched |
| Infrastructure rows registered | — | **none** |
| GitHub Actions minutes | unmetered by this goal | 3 runs: 1 red (6 jobs), 2 green (6 jobs each) |

Arithmetic check on the authority, as the goal requires: this deliverable buys **no runs**
(`0 runs x 0 arms x $0.00 / 1.00 = $0.00`), so the cap closes trivially and never binds. There
is no residue and no unspendable remainder to report.

---

## What remains open

1. **`ruff format` normalisation** — 14 files / ~137 lines, mechanical, its own PR.
2. **Pinning `amplifier-foundation`** in the module test job — maintainer judgement call.
3. **Three sibling repos still have no workflows.** The CI sweep that motivated this lane
   found 7 repos green on main HEAD and **4 with no workflow files at all**. This lane closes
   one quarter of that gap; the other three are unaddressed.
4. **Merging is the manager's stage**, not this lane's (Procedure 4 forbids the lane to
   merge). Acceptance requires a successful check-run on `main` HEAD after merge, which by
   construction cannot exist until the merge happens.
