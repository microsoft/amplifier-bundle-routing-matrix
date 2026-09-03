# PREREGISTRATION ADDENDUM 1 — committed BEFORE the runs it governs

**Written:** 2026-09-02 ~21:20 PT, mid-wave, with the results below already visible.
**Governs:** two additional S3 runs (`cf-s3-03`, `ctl-s3-03`).
**Changes no threshold.** Every gate text in `PREREGISTRATION.md` §3 stands exactly as written.

---

## Why this addendum exists

Adding runs after seeing results is how a wave gets p-hacked. The protection is to
commit — in writing, before the runs — to *what will be run* and *that the result will be
reported whichever way it falls*. That is what this file is.

## What is already known at the time of writing (nothing here is hidden)

S3, n=2 per arm, all in one window:

| arm | run 01 | run 02 |
|---|---|---|
| `cf` | $1.0670 / 486.3 s / score **ungraded** / 2 sessions / luna×21 + terra×22 | $0.7774 / 209.4 s / score 88 / **1 session** / terra×27 |
| `ctl` | $1.3813 / 391.7 s / score **ungraded** / 3 sessions / terra×40 | $1.1427 / 270.1 s / score 100 / 2 sessions / terra×29 |

S1, n=1–2:

| arm | run 01 | run 02 |
|---|---|---|
| `cf` | $7.1948 / 880.0 s / 5 sessions / luna×80 + terra×12 | *(in flight)* |
| `ctl` | $3.1659 / 383.8 s / 3 sessions / luna×7 + terra×21 | $9.2523 / 577.5 s / 5 sessions / luna×23 + terra×47 |

Guardrail, n=4 (complete): scores 78 / 58 / 28 / 78; costs $1.0078 / $0.8153 / $0.8389 / $0.6848.

**So at the moment of writing, on the data in hand: `G-CF1` computes PASS, `G-CF2` computes
FAIL, `G-CF3` has only n=1 graded, and `G-GUARD` leg (c) computes FAIL.** This addendum is
written with a failing gate on the table, not to rescue one.

## The two defects this addendum responds to

1. **A driver defect cost the pre-registered n on quality.** `ytg_driver.sh` never pushed
   the S3 scenario directory into the container, so `/root/s3/grader.py` was absent and the
   first run of each OpenAI arm graded as `?`. The deliverables are wiped by the next run's
   reset, so those two scores are unrecoverable. `G-CF3` was pre-registered at n=2 and has
   n=1. Fixed at 20:53 by pushing the scenario dir out of band (all later runs graded); the
   driver now pushes it itself.
2. **A confounder the pre-registration named in advance, now observed.** §4 of
   `PREREGISTRATION.md` listed as a falsifier: *"An S3 window where the terra root's own
   calls dominate the tree (fewer delegations) — the cheap-tree saving is proportional to
   delegated work."* `cf-s3-02` ran with **tree_sessions = 1**: no delegation, so no matrix
   decision was exercised at all, so that run cannot distinguish the arms even in principle.

## What is committed to, here, before running it

1. Run **exactly one** additional S3 run per OpenAI arm — `cf-s3-03` and `ctl-s3-03` —
   under identical conditions, budget permitting (est. ~$2.2 total).
2. **Report every gate at BOTH n**: the n=2 verdict (the pre-registered n) and the n=3
   verdict, side by side, whichever way each falls. The n=2 verdict is never dropped
   because the n=3 verdict is nicer.
3. **No threshold moves.** `G-CF1` still needs median-lower AND complete non-overlap;
   `G-CF2` still needs median wall ≤ control; `G-CF3` still needs median ≥ 75 and no run
   below 70.
4. **Stop after these two runs.** No further runs will be bought for the OpenAI arms in
   this lane, whatever they show. If the extra run flips a gate, that is reported as a
   flip at n=3, not as "the gate passed".
5. The separation probability attached to any `G-CF1` PASS is restated for the n actually
   used: **1/6 at n=2, 1/20 at n=3** under exchangeability.

## What is NOT bought, and why

- **More guardrail runs.** The failing clause is quality, on an instrument whose own
  recorded baseline spans 38–88 at n=10. More n would sharpen an estimate of *haiku's
  variance*, which is not what the guardrail is for, and would not change legs (a)/(b) —
  the legs that can actually detect a mapping regression. `PREREGISTRATION.md` §4 already
  states how a (c)-only failure is to be read.
- **A `quality-slow-reasonable` arm.** Dropped in §2 before spending; nothing measured
  since bears on that decision.
