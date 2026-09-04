# DONE-NOTE — model_performance-d98 (golden `--regenerate` silently drops PRESET_BEARING matrices)

**Spend: $0.00.** No API calls, no DTU, no containers, no infrastructure
created — nothing registered in the infra ledger, nothing to tear down. Pure
code lane, within the $0 authority. Every number below came from running
`python3` and `pytest` locally.

Branch `lane/d98-golden-regenerate`, one commit, one file changed:
`tests/test_default_resolution_unchanged.py`. No matrix YAML in the diff. The
golden fixture is **not** in the diff (`git status` clean on it — item
scope-out: "do NOT regenerate the golden fixture as part of this change").

## Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | The documented path stops destroying the recording | **DONE** — `--regenerate` now keeps `openai.yaml`; and refuses (exit 2, naming files) in the one case where a drop is genuine |
| 2 | A test that fails when a previously-recorded matrix disappears | **DONE** — two, neither with the subtraction blind spot |
| 3 | Fail-before evidence (new test fails at parent; before/after of `--regenerate` at parent) | **DONE** — both captured, raw output committed |
| 4 | The one set doing two jobs resolved explicitly | **DONE** — split into `PRESET_BEARING` + `EXCLUDED_FROM_RECORDING` |
| 5 | Full suite green | **DONE** — 584 passed |
| 6 | Draft PR on origin | **DONE** — see `DONE.json` `publication` block |
| 7 | DONE-NOTE in the PR body | **DONE** (this file) |

## What was actually wrong

`PRESET_BEARING = {"openai-knob-consistent.yaml", "openai.yaml"}` was **one set
answering two different questions**:

- *Does this matrix ship a `preset:` block?* — a property of the **matrix**.
  True for both names.
- *Is this matrix deliberately absent from the pre-feature recording?* — a
  property of the **recording**. True only for `openai-knob-consistent.yaml`.

`openai.yaml` was recorded at `99d9b08`, before it gained a preset on
2026-09-02, and is deliberately *still* covered by the byte-identity check —
the module comment says so, because `_snapshot()` never passes
`preset:`/`caller_context`, so a preset block is structurally inert for a cold
recording. Both use sites filtered on the single conflated set, so:

- `--regenerate` deleted `openai.yaml`'s entry, and
- `test_golden_covers_every_pre_existing_matrix` subtracted the same set
  before looking for unaccounted matrices, so nothing failed.

**Measured, at parent `0188a12`** (`evidence/parent-before.txt`,
`evidence/parent-regenerate-fixture.diff`):

```
matrices recorded BEFORE: [... 'ollama.yaml', 'openai.yaml', 'quality.yaml']
regenerated .../resolution_golden_pre_knob_consistency.json (7 matrices)
matrices recorded AFTER:  [... 'ollama.yaml', 'quality.yaml']
 .../resolution_golden_pre_knob_consistency.json | 118 ---------------------
 1 file changed, 118 deletions(-)
```

**118 deleted lines, not 124** — the item says 124; that is the diff *hunk*
span (`@@ -552,124 +552,6 @@`), which includes 6 lines of context. The entry
itself is 118 lines. Correcting the number, not disputing the bug.

And the silence is the real finding (`evidence/parent-silence.txt`) — with
`openai.yaml` freshly deleted from the fixture, at the parent commit:

```
tests/test_default_resolution_unchanged.py .......... 10 passed
full suite ......................................... 579 passed
```

A maintainer running the documented command sees a green suite and a
124-line-shorter fixture, and has no signal that a matrix just left the
identity check.

## The fix

1. **The set is split, each use site pointed at the one it means.**
   `PRESET_BEARING` (ships a preset) is now documentation only;
   `EXCLUDED_FROM_RECORDING = {"openai-knob-consistent.yaml"}` is what
   regeneration and the coverage tripwire filter on.
2. **`_regeneration_payload()`** — extracted from the previously untestable
   `__main__` one-liner. Two rules: an exemption never *evicts* an existing
   recording (an exemption declared today must not retroactively delete a
   recording made before it), and if regeneration would still lose a recorded
   matrix it raises `GoldenWouldLoseAMatrix` naming the files. `--regenerate`
   prints `REFUSED: …` and exits **2**. `--allow-drop` is the deliberate,
   reviewable yes.
3. Module docstring updated — a maintainer reading the regeneration
   instructions now reads the refusal and the escape hatch too.

Both halves of the deliverable, in a throwaway copy (`evidence/after-fixed.txt`):

```
regenerated ... (8 matrices)   exit=0     AFTER: [... 'openai.yaml', ...]
IDENTICAL (regeneration is now a no-op on an unchanged tree)

# economy.yaml removed from routing/:
REFUSED: ... this would DELETE these already-recorded matrices ...: ['economy.yaml'] ...
exit=2 ; fixture unchanged
# with --allow-drop:
WARNING: dropped on purpose (--allow-drop): ['economy.yaml']   exit=0
```

The regenerated output being **byte-identical to the committed fixture** is
worth its own line: it is independent evidence that this change moves nothing
about routing — only about what regeneration is willing to throw away.

## The tests, and which one is the fail-before

Five new tests. They are not interchangeable:

- **`test_regenerate_entry_point_preserves_every_recorded_matrix`** — *the
  fail-before test.* Copies `routing/ modules/ tests/` to a tmpdir and runs
  **the documented command as a subprocess**, then asserts nothing that was
  recorded is gone. The bug lived in `__main__`, which no test had ever
  executed; this executes it. Running against a throwaway copy is what lets a
  green suite exercise regeneration without rewriting the real fixture.
- **`test_every_recorded_matrix_is_still_in_the_fixture`** — the tripwire that
  outlives the fix. Compares the fixture against a frozen
  `RECORDED_MATRICES` manifest. It **subtracts nothing** — that subtraction is
  precisely the blind spot in `test_golden_covers_every_pre_existing_matrix` —
  and it does not derive its expectation from its own subject, because a check
  that reads the fixture to decide what the fixture should contain cannot
  notice the fixture shrinking.
- `test_regeneration_refuses_to_drop_a_recorded_matrix`,
  `test_regeneration_keeps_an_excluded_matrix_that_was_already_recorded` —
  unit coverage of the refusal and the no-evict rule.

**Honest limitation, stated rather than papered over:** only the *first* of
these fails at the parent commit. The manifest tripwire passes there, and must
— at parent the fixture is intact; it only becomes wrong *after* someone runs
`--regenerate`. Claiming both as fail-before evidence would be false.

**How the fail-before was run** (`evidence/fail-before.txt`): a detached
worktree at `0188a12`, carrying the **new test file with only the fix stashed**
— the `__main__` branch reverted to the parent's
`{k: v for k, v in snapshot.items() if k not in PRESET_BEARING}` one-liner,
everything else identical. Reverting only the fix is what makes this a test of
the fix rather than a test of the file:

```
E  AssertionError: `--regenerate` silently deleted already-recorded matrices
E  from the golden fixture: ['openai.yaml']
E    stdout: regenerated .../resolution_golden_pre_knob_consistency.json (7 matrices)
FAILED ...::test_regenerate_entry_point_preserves_every_recorded_matrix
1 failed, 3 passed
```

## Suite

```
PYTHONPATH=modules/hooks-routing python3 -m pytest tests modules/hooks-routing/tests -q
584 passed in 2.55s
```

Parent `0188a12` is **579**, not the 570 the item quotes for `8f6dde4` (#57
landed in between). 579 + 5 new = 584; no test was removed or skipped. `ruff
check .` reports the same **2 pre-existing** findings and no new ones —
`matrix_loader.py:352` (F402, the item says 346; the file shifted) and
`test_matrix_loader.py:5` (F401). Left untouched, as instructed.

## Deviations / choices made without asking

- **`--allow-drop` was added**, which the item did not ask for. Without it the
  refusal is a wall: a legitimately-deleted matrix could never be regenerated
  out of the fixture. The escape hatch is what makes the refusal safe to make
  strict.
- **`RECORDED_MATRICES` is a hand-maintained literal.** It has to be
  maintained by hand — deriving it from the fixture would reintroduce exactly
  the self-referential blind spot this item exists to close. Adding a matrix
  does not require touching it (the check is a subset test, not equality);
  only a deliberate removal does, and that is the reviewable act.
- **Kept `PRESET_BEARING` as a live name** rather than deleting it. It is now
  referenced only by documentation and one test, but it records a true fact
  about the matrices and is the natural home for the next preset-bearing file.
  A future reader who greps it will find the comment explaining that it is
  *not* the exclusion set.

## Open / not done

- Nothing blocked. No follow-up filed.
- `openai-knob-consistent.yaml` is still unrecorded and still exempt — correct
  and unchanged by this lane. If it ever *should* be recorded, that is a
  routing decision with its own review, not a regeneration detail.
