# DONE-NOTE — `model_performance-ytg` (W4-PR2: presets revision)

**Lane:** `ytg-presets-revision` · **Branch:** `lane/ytg-presets-revision` · **Date:** 2026-09-02
**Result:** **no preset ships.** One preset was designed, built, measured and **withdrawn**;
three were dropped at $0 before spending. This PR's net diff is documentation and tooling
only — **zero routing files, zero test files.**

---

## 1. DELIVERABLES

| deliverable | status |
|---|---|
| Each preset ends PASS or DROPPED-with-measured-reason | **DONE** — 0 PASS, 4 DROPPED. `FINDINGS.md` §1 (the three $0 drops) and §4 (the measured drop). |
| Gates re-registered BEFORE the runs that test them | **DONE** — `PREREGISTRATION.md` committed at `56e0ccc`, before the first API call; `PREREGISTRATION-ADDENDUM-1.md` at `1a4d04c`, mid-wave, written with a failing gate already on the table. No gate text was edited after a result was seen. |
| n=2 per preset on S1+S3, raw per-run numbers committed | **DONE with one shortfall** — 12 runs, every per-run number in `FINDINGS.md` §3 and `analysis.json`. Shortfall: 2 of 12 runs are ungraded (driver defect, §3 below), so `G-CF3` stands at **n=1 graded**, not the registered n=2. Recorded as under-powered, not as a pass. |
| Anthropic guardrail: `routing/anthropic.yaml` byte-identical, proven, **and** run | **DONE** — leg (a) `git diff --stat origin/main...HEAD` does not list the file (md5 unchanged `b2540bd65f1481a937eb3843c925d650`, verified *inside* each container too); leg (b) golden-fixture identity test passes unregenerated (11 passed); leg (c) live n=4 arm **FAILED** on quality — reported as a failure, with the pre-registered reading in `FINDINGS.md` §4. |
| DRAFT PR carrying only the presets that passed, tests green | **DONE** — none passed, so the PR carries **no matrix**. Full suite **570 passed** (the pre-existing baseline at `8f6dde4`), because the tree no longer differs from main outside `docs/`. |
| DONE-NOTE in the PR body | **DONE** — this file, at `docs/lanes/ytg-presets-revision/DONE-NOTE.md` (never the repo root). |

---

## 2. SPEND — **$45.11 MEASURED AGAINST A $40 CAP. THIS IS AN OVERRUN.**

| phase | runs | measured $ | running total |
|---|---|---|---|
| S3, `cf` + `ctl` + `guard` 01–02 | 6 | 6.1915 | 6.19 |
| `guard` 03–04 | 2 | 1.5237 | 7.72 |
| **S1, `cf` + `ctl`** | **4** | **37.3942** | **45.11** |
| unmeasured (3 container provisions + readiness warm-up probes; no session events) | — | ~0.30 est. | ~45.41 |

**Per-run S1 cost, the line that broke the cap:** `cf` **$7.1948** and **$17.7812**; `ctl`
**$3.1659** and **$9.2523**.

### What went wrong, precisely

The four S1 runs were launched as **one batch** (two driver invocations, `s1_n=2` each) when
measured spend stood at **$6.19**. They were sized on the corpus's *median* S1 cost
(~$4/run → ~$16 expected). The corpus's own recorded S1 range is **$0.40–$27.18/run**, and
this wave drew from the top of it. Because all four runs were committed at launch, there was
**no per-run stop between $27.33 and $45.11** — by the time the total was visible, the spend
had already happened.

**This is my error, and it is an arithmetic one:** 4 × median ≈ $16; 4 × recorded tail
≈ $109. A cap that a single run can consume 44% of must be spent one run at a time.

### What was done on discovery

- All spending stopped immediately; the three eval containers were destroyed and **verified
  gone** (`lane_teardown.sh … teardown --yes` → `verified-gone=3 rows-flipped=3 failed=0`),
  touching only this lane's own ledger rows.
- `ADDENDUM-1`'s two committed extra S3 runs (`cf-s3-03`, `ctl-s3-03`, ~$2.2) were **not
  executed**, and are reported as NOT-MEASURED rather than quietly dropped.

### What the remaining budget would have bought, had it not been spent

At the point of overrun, ~$12.7 of the cap had been consumed by the *second* S1 run alone.
Spent instead as the addendum planned, it would have bought roughly **10–12 further S3 runs**
— enough to take both OpenAI arms to **n=5** (the battery's own n, separation p = 1/252
instead of 1/6) and to resolve the single most consequential ambiguity in this lane: whether
`G-CF1`'s cost separation survives once every `cf` run actually delegates.

---

## 3. DEVIATIONS FROM THE PRE-REGISTRATION

| # | deviation | why, and how it is carried |
|---|---|---|
| 1 | **`G-CF3` measured at n=1, registered at n=2.** | My driver never pushed the S3 scenario dir into the container, so the in-container grader was absent and the first run of each OpenAI arm graded `?`. Deliverables are wiped by the next run's reset → unrecoverable. Fixed mid-wave (20:53) out of band; the driver now does it. The gate is reported as **PASS at n=1, under-powered**, never as a clean pass. |
| 2 | **`guard` run at n=4, registered at n=2.** | Two extra runs were bought (~$1.5) *before* the cap was in danger, to give the guardrail's median a meaningful basis. More data at unchanged thresholds. It did not help the gate: n=4 is what produced the 28. |
| 3 | **`ADDENDUM-1`'s extra S3 runs not executed.** | Cap already exceeded (§2). Reported as NOT-MEASURED; **no n=3 verdict is claimed in either direction**. |
| 4 | **Anthropic mapping of `cheap-fast` never built or run.** | Declared in `PREREGISTRATION.md` §2 before spending: 161's `cheap-fast-anth` run 02 scored 28, so quality non-inferiority on that path is not established and shipping haiku candidates would carry an unvalidated mapping silently. |

---

## 4. WHAT A READER SHOULD TAKE FROM THIS LANE

1. **#55 subsumed the routing half of the preset programme for OpenAI roots.** At
   `gpt-5.6-terra@medium`, `balanced` differs from the shipped matrix in **0 of 13 roles**.
   161's headline preset win was a measurement of the mechanism #55 then shipped.
2. **The one remaining distinct idea — a tree *below* the root's rung — is falsified on S1.**
   Cost tracks **call count**, and the cheap model needed 173 and 92 calls where the control's
   whole tree needed 70 and 28. Cheap per token, expensive per task.
3. **The Anthropic guardrail's live leg is mis-specified**, and this lane is the evidence:
   all four guardrail runs had `tree_sessions = 1`, so the leg never exercised a *mapping*;
   and its "no run below 38" floor is contradicted by two independent 28s.
4. **A $0 resolver-level equivalence check should precede any future preset spend.**
   It cost nothing, killed three of four candidates on measured grounds, and found a silent
   config footgun (`escalate.allow_roles`) on the way.

---

## 5. INFRASTRUCTURE

3 DTU containers (`val-ytg-a/b/c`, profile `eval-container` pinned identically to 161's
wave). All three registered in the infra ledger **at creation** and claimed by this lane
before any run; all three destroyed and verified absent at lane end. `sweep` was never run.

**Capture root:**
`/home/bkrabach/dev/openai-evals-team-ci/.amplifier/evaluation/treatment-validation/20260902-ytg-presets-revision/`
(12 run directories with per-run `arm_verify.txt`, `RUNLOG.jsonl`, session trees, wire
audits, scorecards; `measure/` carries the per-run `dw_measure.py` output.)

**Reproduce the $0 half of this lane with no spend at all:**

```
PYTHONPATH=modules/hooks-routing python3 docs/lanes/ytg-presets-revision/tools/plan_equivalence.py \
  docs/lanes/ytg-presets-revision/tools/cand/cand-{cheap-fast,balanced,qsr}.yaml
```
