# W4-PR2 — PRESETS REVISION: redesign the failing presets against measured data, re-validate

**Item:** `model_performance-ytg` · **Lane:** `ytg-presets-revision` · **Date:** 2026-09-02
**Spend:** **$45.11 measured against a $40 cap — an OVERRUN.** Cause, timeline and
remediation in `DONE-NOTE.md` §2. Nothing here is presented as if the cap held.
**Capture root:** `.amplifier/evaluation/treatment-validation/20260902-ytg-presets-revision/`
**Pre-registration:** `PREREGISTRATION.md` (frozen at `56e0ccc`, **before** the first API
call) and `PREREGISTRATION-ADDENDUM-1.md` (`1a4d04c`, mid-wave, with a failing gate already
on the table). No gate text in either file was edited after a result was seen.

---

## THE HEADLINE, IN FIVE LINES

1. **Nothing ships.** The one preset that survived design review failed **2 of its 4**
   pre-registered gates. `routing/openai-cheap-fast.yaml` was built, measured, and
   **withdrawn** (`9df09f7`); this PR's net diff touches no matrix and no test.
2. **Three of the four 161 presets were dropped at $0, before spending** — because #55
   changed what "the shipped matrix" means. Asking the resolver directly: at
   `gpt-5.6-terra@medium`, **`balanced` differs from today's shipped `openai` matrix in 0
   of 13 roles.** It *is* the default. 161's headline win was a measurement of #55's own
   mechanism, and #55 shipped it.
3. **The cheap-tree thesis is falsified on S1, in the opposite direction to its claim.**
   Pinning every role to luna made S1 **~2× MORE expensive** — median **$12.4880** vs the
   control's **$6.2091** — because the cheap model needed **161 and 80** calls where the
   control's whole tree needed **70 and 28**. Cheap per token is not cheap per task.
4. **The S3 cost win is real but hollow at this n.** `G-CF1` passes with non-overlapping
   ranges — and one of the two `cf` runs never delegated at all (`tree_sessions = 1`), so
   the matrix made **no routing decision** on it. The pre-registration named this
   confounder in advance as a falsifier; it then occurred.
5. **The Anthropic guardrail's two decisive legs PASS; its live leg fails on haiku's own
   variance.** `anthropic.yaml` is absent from the diff and byte-identical
   (`b2540bd65f1481a937eb3843c925d650`, verified *inside* every eval container), and the
   golden-fixture identity test passes unregenerated. The live n=4 arm scored **78/58/28/78**
   — median 68 against a ≥70 clause, and a 28 against a "no run below 38" clause set from a
   10-run baseline whose tail did not go that low.

---

## 1. WHAT #55 DID TO 161's GATES, AND WHY THREE PRESETS DIED FOR $0

161 adjudicated four presets against the **pre-#55** `openai` matrix — the one that sent
9.1–31.0% of a terra-rooted tree's requests to `sol` at efforts nobody named. **#55
(`320f24e`) made knob-consistent delegation the default for OpenAI roots.** Every 161 gate
phrased against "what ships today" now points at a different artifact.

Before spending anything, this lane asked the resolver itself, walking the real code path
(`parse_preset` → `plan_candidates` → `resolve_model_role`) against the fixed fake roster
the repo's own golden-fixture test uses. Tool: `tools/plan_equivalence.py`. Output:
`plan-equivalence.json`, `plan-equivalence-qsr.json`. **Cost $0; re-runnable by anyone.**

**Per-role (model, effort) plan vs the shipped `openai` matrix, by caller root:**

| candidate | @`luna@medium` | @`terra@medium` | @`terra@high` | @`sol@high` |
|---|---|---|---|---|
| `balanced` | 12 roles differ | **0 differ** | 13 differ | 13 differ |
| `quality-slow-reasonable` | 1 differs | **1 differs** (`reasoning`→`sol@high`) | 1 differs | 5 differ |
| `cheap-fast` | **0 differ** | **12 differ** (all → `luna@medium`) | 13 differ | 13 differ |

*(knob: routing matrix · family: gpt-5.6 sol/terra/luna · **measured**, deterministic, $0 ·
`plan-equivalence.json`)*

Read the diagonal. **Each preset is a no-op at exactly the root it was designed for** —
except `cheap-fast`, which is a no-op at *its* root (luna) and meaningful anywhere above it.
That is #55's `inherit: strict` doing its job: it is a **ceiling at the caller's rung**, so
a preset that pins the tree *to* the root's rung is now redundant by construction, and only
a preset that moves the tree *off* that rung is still distinct.

### The three drops, each with its measured reason

| preset | disposition | reason |
|---|---|---|
| `balanced` | **DROPPED** | 0 of 13 roles differ from the shipped `openai` matrix at `terra@medium`. A rename, not a win. Its only residual delta is at *cold* resolution (`general`/`coding`/`ui-coding` at `medium` vs `openai.yaml`'s `high`), which contradicts that pin's own 2026-09-01 rebaseline and is not this lane's evidence to overturn. |
| `quality-slow-reasonable` | **DROPPED** | Its ONLY delta vs today's default is one capped escalation of `reasoning` → `sol@high`. 161 measured that delta **uncapped** (an upper bound) at **+24% cost ($1.2942 vs $1.0399) at the same median score (100)**. All it bought was **3/3 vs 2/3** on the S3 pass rule — a difference the battery cannot resolve at n=3 (§10.6), let alone at the n this cap affords. |
| `quality-fast-expensive` | **DROPPED** | 161 falsified its load-bearing clause by **2.5×** (`G-P2` wants the lowest wall; it posted the highest, 584.8 s vs 235.6 s). Its mechanism (`G-F1` fan-out cap) has never been run and Phase 2b is unfunded. S1 re-validation alone would have cost **$15.96–$27.18/run** — 40–68% of the whole cap for one arm. |

**A defect found along the way, at $0.** The escalation allow-list key is
`preset.delegation.escalate.allow_roles`. A natural reading of `ROUTING-PROPOSAL.md` writes
`roles:`, which `parse_preset` silently ignores — the preset then parses, validates, and
**escalates nothing**, with no error. This lane hit it and caught it only because the
plan-equivalence output showed `quality-slow-reasonable` as *identical* to the default when
it should have differed in one role. A preset file with that typo is inert and says so
nowhere. *(knob: routing · **measured**, code-level · `knob_consistency.py:283-300`)*

---

## 2. THE ARMS, AND THE ONE THING THAT VARIED

| arm | matrix | root | n |
|---|---|---|---|
| `cf` | `openai-cheap-fast.yaml` (this lane's candidate, pushed into the container) | `gpt-5.6-terra@medium` | S3 2, S1 2 |
| `ctl` | **`SHIPPED:openai`** — with #55's `preset:` block, i.e. what ships today | `gpt-5.6-terra@medium` | S3 2, S1 2 |
| `guard` | **`SHIPPED:anthropic`** — untouched by this PR | `claude-haiku-4-5-20251001` (no effort) | S3 4 |

`cf` and `ctl` share a root **on purpose**: the only variable between them is the routing
matrix, which is the only thing a PR in this repo can ship.

**Verified, not assumed, before every single run** (`arm_verify.txt` per run; V2):
`ARM_OK matrix=… primary=terra model=gpt-5.6-terra effort=medium n_priority0=1`. And inside
every container, the files actually under test:

```
48f5fb2bea1dbd3b487caaa0f7a6752a  routing/openai.yaml        (== this tree; grep '^preset:' = 1)
b2540bd65f1481a937eb3843c925d650  routing/anthropic.yaml     (== this tree, byte-identical)
dfdf566bdd446001877fe7f5458d0e0e  routing/openai-cheap-fast.yaml  (== the candidate)
```

All twelve runs are in ONE window (2026-09-02 20:40–21:33 PT), same host, same pinned
container image. **No claim here compares a wall number across days** (`00 §fact 3`: the
provider tail moved 6.5× in two calendar days).

---

## 3. THE MEASUREMENTS

### S3 (5-turn multi-turn build)

| arm | run | cost $ | wall s | score | LLM calls | tree sessions | cache-read % | models on the wire |
|---|---|---|---|---|---|---|---|---|
| `cf` | 01 | 1.0670 | 486.3 | *ungraded* | 44 | 2 | 92.2 | luna×21, terra×22, gpt-5.6×1 |
| `cf` | 02 | 0.7774 | 209.4 | **88** | 28 | **1** | 92.7 | terra×27, gpt-5.6×1 |
| `ctl` | 01 | 1.3813 | 391.7 | *ungraded* | 41 | 3 | 86.5 | terra×40, gpt-5.6×1 |
| `ctl` | 02 | 1.1427 | 270.1 | **100** | 30 | 2 | 86.6 | terra×29, gpt-5.6×1 |

### S1 (single-shot diagnostic)

| arm | run | cost $ | wall s | anchors | LLM calls | tree sessions | cache-read % | models on the wire |
|---|---|---|---|---|---|---|---|---|
| `cf` | 01 | **7.1948** | 880.0 | 3/3 pass | 92 | 5 | 33.4 | **luna×80**, terra×12 |
| `cf` | 02 | **17.7812** | 1039.2 | 3/3 pass | **173** | 5 | 25.3 | **luna×161**, terra×12 |
| `ctl` | 01 | 3.1659 | 383.8 | 3/3 pass | 28 | 3 | 47.5 | luna×7, terra×21 |
| `ctl` | 02 | 9.2523 | 577.5 | 3/3 pass | 70 | 5 | 38.4 | luna×23, terra×47 |

### Anthropic guardrail (shipped `anthropic` matrix, haiku root)

| run | cost $ | wall s | score | LLM calls | tree sessions | cache-read % |
|---|---|---|---|---|---|---|
| 01 | 1.0078 | 500.5 | 78 | 43 | 1 | 90.5 |
| 02 | 0.8153 | 371.5 | 58 | 35 | 1 | 91.9 |
| 03 | 0.8389 | 317.0 | **28** | 40 | 1 | 93.1 |
| 04 | 0.6848 | 285.9 | 78 | 28 | 1 | 89.7 |

*(All runs `completion=complete`. Recorded baselines these are read against, DIFFERENT
WINDOW, context only: `haiku-high` n=5 median $0.8649 / 362.2 s / score 78, with the
10-run haiku score range 38–88.)*

---

## 4. THE VERDICTS

### `openai-cheap-fast` — **DROPPED** (2 of 4 gates failed)

| gate | threshold (pre-registered) | measured | verdict |
|---|---|---|---|
| `G-CF1` S3 cost | median lower **and** ranges non-overlapping | cf **$0.9222** (0.7774–1.0670) vs ctl **$1.2620** (1.1427–1.3813); max cf < min ctl | ✅ **PASS** (n=2/side, p=1/6) |
| `G-CF2` S3 wall | cf median **≤** ctl median | cf **347.9 s** vs ctl **330.9 s** | ❌ **FAIL** |
| `G-CF3` S3 quality floor | median ≥ 75 **and** no run < 70 | 88 — but **n=1 graded**, not the registered n=2 | ⚠️ **PASS at n=1** (under-powered by my own defect) |
| `G-CF4` S1 | both complete **and** cf median cost < ctl | both complete ✅; cf **$12.4880** vs ctl **$6.2091** — **2.01× the control** | ❌ **FAIL** |

**The S1 failure is the substantive one, and it inverts the preset's thesis.**
`PRESETS.md` §1 argued *"the model is already cheap; the routing is what costs"*, anchored
on luna's measured **$0.48–0.78 when it does not delegate to sol vs ~$1.50 when it does**.
This lane pinned the entire tree to luna and got the opposite: **cost tracks call count,
and the cheap model needs more calls.** `cf` ran **92 and 173** LLM calls against the
control's **28 and 70**, and its cache-read share collapsed to **33.4% / 25.3%** against the
control's **47.5% / 38.4%** — more sub-sessions each paying a cold head, and more turns
inside each. *(knob: routing matrix · family: gpt-5.6 luna/terra · **measured**, n=2/arm,
one window · `analysis.json`)*

This is the same shape 161 found on the Anthropic side running the other way
(*"knob-consistency makes an expensive root more expensive"*), and it generalises to:
**clamping a tree away from the root's own rung changes how much work gets done, not just
what it costs per unit** — in either direction.

**Why `G-CF1`'s PASS does not rescue it.** `cf-s3-02` ran with **`tree_sessions = 1`**: no
delegation, therefore no matrix decision, therefore that run cannot distinguish the arms
even in principle — it is two samples of "terra@medium doing its own work" and it landed
$0.37 apart from the control's nearest run. The pre-registration listed exactly this as the
falsifier for `G-CF1` (*"the cheap-tree saving is proportional to delegated work"*) and
recorded tree size per run so it could be seen. Of the four OpenAI S3 runs, **one of two
`cf` runs exercised the treatment at all.** A separated cost ranking at n=2, p=1/6, with
half the treatment arm inert, is not a shippable claim.

**What would have changed this verdict:** `ADDENDUM-1` committed, in writing and before
running them, to two more S3 runs (`cf-s3-03`, `ctl-s3-03`) and to reporting both the n=2
and n=3 verdicts whichever way they fell. **Those runs were never executed** — the S1 batch
had already consumed the cap. That is a NOT-MEASURED, not a quiet omission.

### The Anthropic guardrail — legs (a) and (b) **PASS**, leg (c) **FAILS**

| leg | what it proves | result |
|---|---|---|
| **(a)** file identity | `git diff --stat origin/main...HEAD` — `routing/anthropic.yaml` **absent** from the diff; md5 still `b2540bd65f1481a937eb3843c925d650` | ✅ **PASS** |
| **(b)** resolution identity | `tests/test_default_resolution_unchanged.py` — every role of every recorded matrix, exact, fixture **not** regenerated: 11 passed | ✅ **PASS** |
| **(c)** live mapping, n=4 | both clauses on quality miss: median **68** vs ≥70, and run 03 scored **28** vs a "no run below 38" floor. Cost clause holds: median **$0.8271** ≤ $1.30, *below* the $0.8649 baseline median | ❌ **FAIL** |

**How to read a (c)-only failure — as pre-registered in `PREREGISTRATION.md` §4, before the
result:** *"Nothing in a routing-matrix PR can move the anthropic path except the loader
itself; leg (b) is the real check and leg (c) is the end-to-end confirmation. A (c) failure
with (a)+(b) passing would indicate a provider-side or window effect, not a mapping
regression, and would be reported that way."* That is the situation. **The conjunction
`G-GUARD` nonetheless FAILS as written, and is reported as failed** — the interpretation
does not convert it into a pass.

Two things make the failure informative rather than alarming:

- **The threshold was wrong, and this is how we found out.** The 38 floor came from a
  10-run baseline (range 38–88). 161 independently recorded a haiku S3 run at **28**. This
  lane drew a 28 in 4 runs. **Haiku's S3 quality tail goes below anything the baseline
  recorded**, so a "no run below the recorded minimum" clause fails on ordinary sampling.
- **All four guardrail runs had `tree_sessions = 1`.** The haiku arm never delegated, so
  the live leg was measuring haiku's own single-session variance, not a *mapping* at all.
  A guardrail whose live leg cannot exercise the mapping it guards is mis-specified.

**Recommendation (not applied — this lane ships no code):** re-specify the guardrail's live
leg as (i) cost/wall non-inferiority plus (ii) a *tolerance interval* on quality from the
pooled baseline rather than its observed minimum, and (iii) require the arm to reach
`tree_sessions ≥ 2` or be reported as not-exercised.

---

## 5. VALIDITY, DISCARDS, AND WHAT WENT WRONG

Per battery §9 rule 1 — *a DISCARD is published, never dropped*.

| # | event | disposition |
|---|---|---|
| **1** | **My driver never pushed the S3 scenario directory into the container**, so the in-container grader `/root/s3/grader.py` was absent and `cf-s3-01` / `ctl-s3-01` graded as `?`. Deliverables are wiped by the next run's reset, so both scores are **unrecoverable**. | Fixed at 20:53 by pushing the scenario dir out of band (every later run graded); the driver now pushes it itself. Consequence carried into the verdict: **`G-CF3` stands at n=1, not the registered n=2**, and is labelled under-powered rather than quietly reported as a pass. Cost/wall for those runs are unaffected and are used. |
| **2** | **BUDGET OVERRUN: $45.11 measured against a $40 cap (+12.8%).** | Full accounting in `DONE-NOTE.md` §2. Cause: the S1 batch (4 runs) was sized on the corpus *median* S1 cost, not on its own recorded range of **$0.40–$27.18/run**; `cf-s1-02` alone cost **$17.78**. All four S1 runs were committed in a single driver invocation, so no per-run stop existed between $27.33 and $45.11. Containers destroyed immediately on discovery (verified gone ×3). |
| **3** | `ADDENDUM-1`'s two committed extra S3 runs were **not executed**. | Reported as **NOT-MEASURED** with its reason, in the addendum's own terms. The n=2 verdicts stand as the only verdicts; no n=3 verdict is claimed in either direction. |
| **4** | Every OpenAI run shows exactly **one** `gpt-5.6` call — a model no arm's matrix names. | Present in **both** arms equally, 1 call/run, so it does not affect any comparison. Recorded, not chased: it is an off-matrix call (most likely a session-utility call resolved against the provider roster rather than the matrix) and it deserves its own probe. |

**Validity conditions met:** V2 (arm re-asserted and re-verified before every run, 12/12),
V5 (`completion=complete` on 12/12 reported runs), V6 (all arms in one 53-minute window;
`ctl` is the in-window clock cell), V7 (single formula version — `dw_measure.py`, unchanged
from the three-knob wave and from 161), V8 (pinned container image, same profile as 161).

**V3 (knob-consistency) — measured, and it is what falsified the preset.** `cf`'s realised
routing was **100% on-knob when it delegated** (luna×21 of the delegated portion on S3;
luna×80 and ×161 on S1). The preset did exactly what it declared. It is the *consequence*
of doing so that failed.

**Not measured, therefore not claimed:** S7 retention, S6 held-out (single-use; spending it
on a spec that just failed would destroy the instrument), `G-P6` preset-switch prefix
isolation, per-boundary Anthropic re-warm distance, any n=3 S3 verdict.

---

## 6. WHAT WOULD CHANGE OUR MIND

| finding | the evidence that would overturn it |
|---|---|
| `cheap-fast` is more expensive on S1 | An S1 arm where the luna tree's call count is comparable to the control's. The cost delta here is call-count-driven (173/92 vs 70/28); a workload where the cheap model converges in the same number of turns would show the opposite. |
| `balanced` is the shipped default | A caller root other than `terra@medium`, or a cold (no-caller) resolution — where the plans differ in 12–13 roles. The equivalence is exact **at that root only**, and is stated that way. |
| The S3 cost win is hollow | An S3 window where every `cf` run delegates. One of two did; at n≥5 with all runs delegating, `G-CF1` would mean what it appears to mean. |
| The guardrail's 38 floor is wrong | A larger haiku baseline whose lower tail stops at 38. Two independent 28s (161's run 02, this lane's run 03) say it does not. |
| `quality-slow-reasonable` is absorbed | A discriminating quality instrument (S7/S6) where its 3/3-vs-2/3 reliability edge reproduces at n≥5. Never measured, here or in 161. |

---

## 7. WHAT THIS LANE RECOMMENDS

1. **Do not ship a `cheap-fast` matrix.** Its S3 cost win is confounded and its S1 cost
   claim is falsified by 2×. The measured lesson is worth more than the preset: *a routing
   matrix that lowers per-token price can raise per-task price by raising call count.*
2. **Retire `balanced` and `quality-slow-reasonable` from the preset programme.** #55
   already ships one; the other is one capped escalation whose only benefit is unmeasurable
   at any n this programme can afford.
3. **Fix the escalate key footgun** (`allow_roles` silently required) — either accept
   `roles:` as an alias or make `validate_preset` reject an `escalate` block with no
   `allow_roles`. Today a typo yields a preset that parses and escalates nothing.
4. **Re-specify the Anthropic guardrail's live leg** (§4): tolerance interval, not observed
   minimum; and require the arm to actually delegate or report itself not-exercised.
5. **Price S1 arms off the recorded tail, never the median.** This lane's overrun is one
   arithmetic error: 4 × median ≈ $16 vs 4 × tail ≈ $109. A cap that can be blown by one
   run needs a per-run stop between runs, not a batch.
