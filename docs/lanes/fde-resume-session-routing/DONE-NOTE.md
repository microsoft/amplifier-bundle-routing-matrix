# DONE-NOTE — lane `fde-resume-session-routing` (`model_performance-fde`)

**Outcome: branch A — RESOLVED.** Every deliverable is DONE. The cap did not
bind: the authority was `0 runs x 0 arms x $0 / 1.00 = $0.00` and the item is a
source-read plus existing captures, so nothing needed buying and nothing was
bought. The cap's arithmetic closes trivially at a validity rate of 1.00 because
no run was priced into it.

Parent commit `d8c6a32` (cly PR #60). Branch `lane/fde-resume-session-routing`.

---

## Deliverables

| # | Deliverable | State |
|---|---|---|
| 1 | Resume-only lifecycle resolves agent `model_role` and reasserts the role pin, with a fail-before test | **DONE** |
| 2 | `session:start` lifecycle byte-identical; mutual exclusivity **proven** by test, not asserted | **DONE** |
| 3 | Adjudicate the 74w role-pin claim | **DONE** |
| 4 | State whether any published measurement moves | **DONE** |
| 5 | Full suite green with before/after counts | **DONE** — 594 → 602 |
| 6 | Fail-before evidence committed and pasted in the PR body | **DONE** |
| 7 | Draft PR on origin | **DONE** — see `publication` in `DONE.json` |
| 8 | This note at the lane artifact root | **DONE** |

Nothing was dropped, deferred, or recorded NOT-POSSIBLE.

## What was measured

All figures from committed captures under
`.amplifier/evaluation/treatment-validation` (1462 `events.jsonl`, `$0`).
Reproducer committed at `evidence/lifecycle_census.py`.

- **1026 of 1238** root-resume lifecycle legs (82.9%), across **212** resumed
  root sessions, ran with hooks-routing's handler never invoked.
- **212 of 212** of those sessions had agents declaring `model_role`
  (2774 agent definitions) — layer B was load-bearing on all of them.
- **43** of those roots spawned **82** delegates on a skipped leg. That is the
  population handed to `model_performance-34l`
  (`evidence/affected-spawns-for-34l.txt`).
- **0 of 212** declared a session-level `provider_preferences` — so the 74w
  role-pin reassert, though genuinely never invoked on those legs, would have
  been a no-op on every one of them.
- `turn_count` separates the two `session:resume` emitters **102/102 vs
  1029/1029**, n=1131.

## Deviations from the goal, and why

1. **The goal's likely fix was insufficient, and this is the lane's main
   technical finding.** The goal proposed registering the handler for
   `session:resume` "…mutually exclusive per process, so no double-run — verify
   that rather than trusting it." Verified: **false in production.** A resumed
   delegate child receives both events on one bus ~5 ms apart, because
   `session_spawner.py:1763-1774` emits its own observability `session:resume`
   and the reconstructed child then emits the kernel `session:start`. The naive
   fix would have double-resolved and duplicated `routing:matrix-loaded` on
   every delegate resume leg — breaking deliverable 2 while satisfying
   deliverable 1. Shipped instead: a once-per-mount latch **plus** a
   `turn_count` discriminator, so the delegate leg still runs at
   `session:start`, same event and same ordering as before.

2. **The 74w finding is reported smaller than the goal expected.** The goal
   anticipated "74w's merged fix has been inert for root resumes since it
   landed… a bigger finding than this fix." Mechanically true. Measurably nil:
   no resumed root session in the corpus carries a role pin, so the silenced
   reassert had nothing to reassert. Reported that way round deliberately — an
   overstated finding misleads the next reader as much as a buried one. The
   material half of this item is layer B.

3. **`custom_routing_dirs`, not `routing_dirs`.** The pre-existing
   `test_role_pin_survives_resume.py` passes `routing_dirs`, which `mount()`
   never reads (`__init__.py:94`), so it silently falls back to the repo's real
   shipped matrix. Harmless for that file (role_pin does not consult the
   matrix), fatal for a layer-B test. The new tests use the key `mount()`
   actually reads. Not fixed in the old file — out of this lane's scope, and it
   changes no behaviour there.

4. **Two existing assertions changed.** `test_init.py` hard-coded
   `register.call_count == 2` in two places; now `== 3`, with an explicit
   `"session:resume" in events_registered` assertion so the count is not the
   only thing pinning the registration.

## Choices made without waiting for a human

- Fixed the misleading `role_pin.py` docstring and added a scope note to
  `test_role_pin_survives_resume.py`, rather than leaving the corrected claim
  only in this lane's findings where the next reader of that file would not see
  it.
- Did **not** touch `amplifier-core` or `amplifier-app-cli`. The two-emitter
  situation and the `is_resumed=False`-on-a-resumed-child reconstruction are
  upstream design facts; this module now tolerates them. Named in FINDINGS §7,
  not fixed here (explicit scope-out).

## Spend

| item | amount |
|---|---|
| API / model spend | **$0.00** |
| DTU / container / infrastructure | **$0.00** — none created; nothing to register or tear down |
| **Total** | **$0.00** against a $0.00 authority |

No infrastructure was created, so no `infra_ledger.sh` row exists and no
`lane_teardown.sh` claim or teardown was needed. No container, DTU or eval was
run (explicit scope-out). Residue: $0.00 of a $0.00 authority — the cap was
correctly sized for a source-read item and never came close to binding.

## Verification

```
PYTHONPATH=modules/hooks-routing python3 -m pytest tests modules/hooks-routing/tests -q
```

- at `d8c6a32` (parent, lane files stashed): **594 passed**
- at lane HEAD: **602 passed** (+8, the new file)
- fail-before at `d8c6a32` with only the source change reverted:
  **6 failed, 2 passed** (`evidence/fail-before.txt`)
- ruff: 2 pre-existing findings only (`F402 matrix_loader.py:346`,
  `F401 test_matrix_loader.py:5`) — not this lane's, not introduced by it

## Artifacts

```
docs/lanes/fde-resume-session-routing/
├── DONE-NOTE.md                        (this file)
├── FINDINGS.md                         (full write-up + 74w adjudication)
└── evidence/
    ├── lifecycle_census.py             (reproducer, $0)
    ├── lifecycle-census.txt            (its output)
    ├── delegate-resume-order.txt       (verbatim root + delegate orderings)
    ├── affected-spawns-for-34l.txt     (82 spawns / 43 roots, for 34l)
    ├── fail-before.txt                 (6 failed / 2 passed at d8c6a32)
    └── suite-after.txt                 (602 passed)
```
