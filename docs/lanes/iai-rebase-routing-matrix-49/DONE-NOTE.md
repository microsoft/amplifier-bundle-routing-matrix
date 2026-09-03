# DONE-NOTE — model_performance-iai (rebase routing-matrix #49 past #48)

**Spend: $0.00.** No API calls, no DTU, no infrastructure created — nothing
registered in the infra ledger, nothing to tear down. Pure code lane, within
the $0 authority.

## Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | #49 rebased with its own documented recipe, mergeable, BOTH inert-effort rejections retained | **DONE** — PR #49 head is now `7c8b0ea`, `mergeable: MERGEABLE` |
| 2 | Passing fail-before tests for BOTH rejections (each fails on the pre-fix parent, passes after) | **DONE** — three separate experiments, below |
| 3 | Full suite green on current main (≥499 tests), pasted in the PR body | **DONE** — 570 passed (baseline on `origin/main` d1d7128: 516) |
| 4 | PR marked ready with a comment naming what was reconciled — never merged | **DONE, then reverted to DRAFT at owner direction** — see "PR review state" below; comment posted; never merged |
| 5 | DONE-NOTE.md in the PR body | **DONE** (this file) |

## Which publication path was taken

**Pushed to PR #49's own head branch** (`lane/565-gemini-silent-drop`), the
primary path the item asked for — not the fallback superseding-PR path. This
required a force-push, because the rebased commit sits on `origin/main`
d1d7128 while the branch tip sat on 99d9b08.

Force-push was done with `--force-with-lease` pinned to the exact expected old
sha, and **the pre-rebase commit was pushed to `archive/pr49-pre-rebase-87c7e04`
first**, so lane 565's original work is still reachable by name on the remote
and nothing was destroyed to make this land.

`lane/iai-rebase-routing-matrix-49` was also pushed, carrying the identical
commit, so this lane's own branch exists on origin as git ground truth. It has
no PR of its own by design — a second PR for the same commit would be noise.
The publication claim in `DONE.json` names the branch that carries PR #49.

## PR review state — ready, then returned to DRAFT at owner direction

**Final state: `draft=true`, `state=open`, `merged=false`.** Recorded on the PR
timeline, both transitions, with actor and timestamp:

```
event=ready_for_review   actor=bkrabach  at=2026-09-03T02:25:42Z
event=convert_to_draft   actor=bkrabach  at=2026-09-03T02:31:50Z
```

This lane first marked the PR **ready**, reading the item's literal text: *"mark
the PR ready with a comment naming exactly what was reconciled"* (line 9), and
*"PR marked ready … (**or** a DRAFT superseding PR naming #49 **if the head
branch is unreachable**)"* (line 15) — where DRAFT appears only in a fallback
conditioned on the head branch being unreachable, which it was not.

The owner subsequently directed that the PR be returned to draft pending their
review. That was done (`gh pr ready --undo 49`).

**Recorded honestly, because the two are different things:** the revert is an
**owner decision**, not a correction of a misread requirement. The item text
says "marked ready"; this note does not retroactively claim otherwise. A future
reader comparing the item text to the PR's final state would otherwise find an
unexplained mismatch and have no way to tell which of the two was wrong.

Practical note for whoever merges: a draft PR is unmergeable by anyone, so #49
must be taken out of draft again before it can land. Nothing else about it
changed — same head commit, same tests, still never merged.

## The conflict, and how it was resolved

#48 and #49 both add a third validation check ahead of `validate_matrix_config`,
asking "will the target act on this key at all?" — a question the existing
validation structurally cannot ask, being closed on VALUES and open on KEYS.
They conflict textually in the same two files, and **semantically in how they
key**:

| finding | keys on | why |
|---|---|---|
| haiku (#48) | **MODEL** | provider-anthropic *does* read the key; one *model* collapses every level above `low` into an identical request |
| gemini (#49) | **PROVIDER** | provider-gemini never reads the key; **every** model it serves is affected |

Applied #49's own documented merge recipe (from its PR body), step for step:

1. Kept #49's generic `InertKeyRule` / `INERT_CONFIG_RULES` /
   `inert_config_rule` / `validate_matrix_inert_config` / `strip_inert_config`.
2. Deleted #48's `EFFORT_UNSUPPORTED_MODELS`, `model_ignores_effort`,
   `validate_matrix_model_support`, `strip_unsupported_effort` — subsumed.
3. Kept `_HAIKU_REASON` verbatim and `effort_remediation` renamed to
   `_haiku_remediation`; its `(model, value) -> str` signature already matched
   the table's `remediation` field, so it dropped in unchanged.
4. `mount()` keeps ONE guard block, not two.
5. #48's tests carried over with import names remapped.

## Deviations from the recipe, and why

**1. The haiku row uses `provider="*"`, not `provider="anthropic"`.**
The recipe specified `"anthropic"`. #48's guard as shipped on main matched the
model substring under **any** provider name (`model_ignores_effort` took only a
model). Narrowing the merged row to `"anthropic"` would silently stop rejecting
an inert effort key on a haiku model served under some other provider id — a
behaviour regression the rebase must not introduce, and exactly the class of
silent drop this guard exists to prevent. `provider="*"` is the wildcard the
table already defines for this. Pinned by
`test_haiku_row_matches_under_any_provider_name`. Row order is now load-bearing
(first match wins, narrow rows before the wildcard) and is itself pinned by
`test_a_narrow_row_is_matched_before_the_wildcard_row`.

**2. Ported #48's test module rather than rewriting its assertions.**
`test_matrix_model_support.py` keeps every assertion #48 made. Two of its entry
points (`model_ignores_effort`, `effort_remediation`) gained a provider
argument in the merged API, so two thin local helpers preserve the old
single-argument semantics instead of rewriting the assertions — the tests still
assert what the measurement earned, not what the new API makes convenient.

**3. Regenerated one golden-fixture entry, surgically.**
`tests/fixtures/resolution_golden_pre_knob_consistency.json` is a byte-identity
recording of cold resolution. #49 deletes 4 inert `reasoning_effort` keys from
`gemini.yaml`, which are the first candidate of those roles, so the recording
changed. That file's own docstring says such a change "must be named in a PR
body and the fixture regenerated on purpose, never silently" — so it is named
here and in the PR body. **No wire behaviour changes**: gemini never read the
key.

Patched `gemini.yaml`'s entry only, rather than running the documented
`--regenerate` path — **because `--regenerate` drops every `PRESET_BEARING`
matrix from the recording**, and `openai.yaml` became preset-bearing on
2026-09-02 while still being in the pre-feature recording. Running it would
have silently deleted `openai.yaml`'s 124 recorded lines and quietly exempted
it from the identity check. Filed as a separate item (see below).

**4. Extended `docs/MATRIX_CURATOR_GUIDE.md` to name BOTH enforced rules.**
#49's guide text named only the gemini rule. After the merge the table enforces
two, and a curator guide that lists one of them is worse than useless.

## Fail-before / pass-after — three experiments, all measured

Captures: `/home/bkrabach/dev/openai-evals-team-ci/.amplifier/evaluation/treatment-validation/20260902-model_performance-iai/`

**(1) At `99d9b08` — before #48 AND before #49 — merged mount-level tests present.**
The strong form: it asserts the *defect*, not a missing import.

```
FAILED test_init.py::TestUnsupportedEffortRejection::test_mount_strips_inert_effort_from_the_effective_matrix
FAILED test_init.py::TestUnsupportedEffortRejection::test_mount_logs_a_named_actionable_error
FAILED test_init.py::TestInertConfigRejection::test_mount_strips_inert_effort_from_the_effective_matrix
FAILED test_init.py::TestInertConfigRejection::test_mount_preserves_sibling_keys_on_a_stripped_candidate
FAILED test_init.py::TestInertConfigRejection::test_mount_logs_a_named_actionable_error
5 failed, 3 passed, 16 deselected in 0.10s

>       assert "reasoning_effort" in blob
E       AssertionError: assert 'reasoning_effort' in ''
```

The empty string IS the bug, for both rejections: the loader had nothing at all
to say about a key it was dropping.

**(2) At `origin/main` d1d7128 — #48 present, #49 absent.**
The discriminating one: it shows #48 does **not** already cover gemini.

```
FAILED test_init.py::TestInertConfigRejection::test_mount_strips_inert_effort_from_the_effective_matrix
FAILED test_init.py::TestInertConfigRejection::test_mount_preserves_sibling_keys_on_a_stripped_candidate
FAILED test_init.py::TestInertConfigRejection::test_mount_logs_a_named_actionable_error
3 failed, 5 passed, 16 deselected in 0.10s
```

Haiku passes, gemini fails. Exactly the gap #49 closes.

**(3) Row ablation on the merged tree** — each row deleted in turn, everything
else intact. This is what proves the merge kept BOTH behaviours rather than one
row quietly covering for the other:

| tree | result |
|---|---|
| gemini row removed | **28 failed** (all gemini tests), 537 passed |
| haiku row removed | **21 failed** (all haiku tests), 544 passed |
| both rows present | **570 passed** |

Each row is load-bearing, and neither substitutes for the other.

**Pass-after, full suite:**

```
$ PYTHONPATH=modules/hooks-routing python3 -m pytest tests modules/hooks-routing/tests -q
570 passed in 2.02s
```

Baseline on `origin/main` @ d1d7128, measured in a clean worktree: **516 passed**.
**+54, 0 regressions.** Requirement was ≥499.

`ruff check modules/hooks-routing/ tests/` reports exactly the two errors that
are already on `origin/main` (`F402 matrix_loader.py:346`,
`F401 test_matrix_loader.py:5`) — both untouched by this change, verified by
running ruff against `origin/main`'s own files.

## Filed while working here

`model_performance-d98` — `tests/test_default_resolution_unchanged.py
--regenerate` silently drops `PRESET_BEARING` matrices from the golden
recording. `openai.yaml` is both preset-bearing and in the pre-feature
recording, so the documented regeneration path would delete it from the file
and exempt it from the identity check with no warning. Not fixed here: the
correct fix is a change to the regeneration entry point, which is #50's file
and outside this rebase.

## Open / not done

- **No wire capture.** The lane cap is $0. Both rejections still rest on the
  evidence their originating lanes produced — a wire measurement for haiku
  (20260901-threeknob, n=1438), a provider code read for gemini. This lane
  added no new evidence about either defect, only the reconciliation.
- **Not merged**, per the wins-only policy. The manager merges.
- **provider-gemini is still not fixed** (a different repo). If it ever grows a
  config → request effort bridge, the gemini row must be deleted in the same
  change, or a working key starts being stripped. Unchanged from #49.
