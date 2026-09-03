# PREREGISTRATION — `model_performance-ytg` (W4-PR2: presets revision)

**Lane:** `ytg-presets-revision` · **Item:** `model_performance-ytg` · **Date:** 2026-09-02
**Cap:** $40 (owner-approved) · **Capture root:**
`/home/bkrabach/dev/openai-evals-team-ci/.amplifier/evaluation/treatment-validation/20260902-ytg-presets-revision/`

> **This file is written and committed BEFORE the runs it governs.** A gate rewritten
> after seeing its own result is a non-result and will be reported as one. Section 5
> records the commit that froze this file.

---

## 1. WHAT CHANGED SINCE 161 WROTE ITS GATES

161 adjudicated four presets against the **pre-#55** world: the shipped `openai` matrix
had no `preset:` block, and a terra-rooted session sent 9.1–31.0% of its tree requests to
`sol` at efforts the caller never named. **#55 (`320f24e`) landed knob-consistent
delegation as the DEFAULT for OpenAI roots.** Every gate 161 wrote that compares a preset
to "what ships today" is therefore comparing against a different artifact than the one on
disk now.

Before spending anything, this lane asked the resolver itself what each 161 preset would
route **today**, walking the real code path (`parse_preset` → `plan_candidates` →
`resolve_model_role`) against the fixed fake roster the repo's own golden-fixture test
uses. Tool: `tools/plan_equivalence.py`; full output: `plan-equivalence.json`. Cost: **$0**,
re-runnable by anyone:

```
PYTHONPATH=modules/hooks-routing python3 docs/lanes/ytg-presets-revision/tools/plan_equivalence.py \
  docs/lanes/ytg-presets-revision/tools/cand/cand-{cheap-fast,balanced,qsr}.yaml
```

**Result — per-role (model, effort) plan vs the shipped `openai` matrix, at the root each
preset would actually be run at (`gpt-5.6-terra@medium`):**

| 161 preset (as a shippable matrix) | differing roles vs shipped `openai` | distinct today? |
|---|---|---|
| `balanced` | **0 of 13** | **NO — it *is* the shipped default** |
| `quality-slow-reasonable` | **1 of 13** (`reasoning` → `gpt-5.6-sol@high`, capped) | yes, narrowly |
| `cheap-fast` | **12 of 13** (every role → `gpt-5.6-luna@medium`) | **yes** |

Two consequences that decide this lane's spend, both established at $0:

1. **`balanced` is not a candidate any more.** Its D2 is byte-for-byte what
   `routing/openai.yaml` already resolves to for a terra-rooted caller. 161's headline
   (`balanced` beats `ctl-legacy` by −38% cost / −44% wall) was a measurement of **#55's
   own mechanism**, and #55 shipped it. Shipping a `balanced` matrix would be a second
   name for the default.
2. **`cheap-fast` is the one preset that does something the default structurally cannot.**
   `inherit: strict` clamps a tree to *at most* the root's rung; it can never take a tree
   *below* it. A matrix that pins every role to the cheap rung is the only way to say
   "keep my root where it is, run the tree cheap".

---

## 2. THE PRESET SET, REVISED — AND WHAT IS DROPPED BEFORE SPENDING

| preset | disposition | reason (all measured; none is a preference) |
|---|---|---|
| **`openai-cheap-fast`** | **MEASURED HERE** (gates in §3) | The only 161 preset still distinct from the default at its own root. Was also the only 161 PASS, and the only arm with complete cost non-overlap. Its missing half (S1) is bought here. |
| `balanced` | **DROPPED** | §1: 0 of 13 roles differ from the shipped `openai` matrix at `terra@medium` ($0, reproducible). A rename, not a win. Its one residual delta is at *cold* resolution only — `general`/`coding`/`ui-coding` at `medium` instead of `openai.yaml`'s `high` — which contradicts that pin's own 2026-09-01 rebaseline evidence and is not this lane's to overturn. |
| `quality-slow-reasonable` | **DROPPED** | §1: its ONLY delta vs today's default is one capped escalation of `reasoning` to `sol@high`. 161 measured that delta **uncapped** (an upper bound on its cost) at **+24% cost ($1.2942 vs $1.0399) at the same median score (100)**. The only thing it bought was **3/3 vs 2/3** on the S3 pass rule — a difference the battery cannot resolve at n=3 (§10.6), let alone the n=2 this cap affords. Shipping it would sell a reliability win never measured at a cost that was. |
| `quality-fast-expensive` | **DROPPED** | 161 falsified its load-bearing clause by **2.5×**: `G-P2` asks for the lowest wall of the four; it posted the **highest** (584.8 s vs 235.6 s). The mechanism its wall claim depends on (`G-F1`, fan-out cap) **has never been run** and Phase 2b is unfunded. Re-validating it on S1 is also unaffordable here: **$15.96–$27.18/run** would consume 80–136% of this lane's entire cap for one arm. |

**Anthropic mapping: deliberately NOT shipped inside `openai-cheap-fast`.** 161's
`cheap-fast-anth` run 02 scored **28**, below all 10 baseline haiku runs (range 38–88);
quality non-inferiority on the Anthropic path is **not established**. A cheap-tree matrix
carrying haiku candidates would ship that unvalidated mapping silently. The shipped file
is OpenAI-only and says so in its header.

---

## 3. THE GATES — WRITTEN BEFORE THE RUNS THEY ADJUDICATE

### The arms

| arm | routing matrix | root (provider default_model @ effort) | scenarios |
|---|---|---|---|
| `cf` | `openai-cheap-fast.yaml` (this PR's new file, pushed into the container's routing dir) | `gpt-5.6-terra` @ `medium` | S3 n=2, S1 n=2 |
| `ctl` | `SHIPPED:openai` (with #55's `preset:` block — i.e. **what ships today**) | `gpt-5.6-terra` @ `medium` | S3 n=2, S1 n=2 |
| `guard` | `SHIPPED:anthropic` (untouched by this PR) | `claude-haiku-4-5` (no effort — the parameter is unsupported, PRESETS.md §0.3) | S3 n=2 |

`ctl` is the **in-window control and the clock cell**. Every gate below is decided
*within this lane's window only*: `00 §fact 3` (the provider tail moved 6.5× in two
calendar days) makes cross-day wall comparison invalid, so no gate here compares a wall
number to a 2026-09-01/02 baseline.

Same root on `cf` and `ctl` **on purpose**: the only variable between them is the routing
matrix, which is the only thing this PR ships.

### `G-CF1` — cost (PRIMARY; failing this drops the preset)

> At root `gpt-5.6-terra@medium`, S3 **median cost/run under `openai-cheap-fast` is lower
> than under the shipped `openai` matrix**, AND the two arms' min–max cost ranges **do not
> overlap** at n=2 per side.

**Why this threshold is achievable AND honest.** 161 measured a luna-pinned tree at
**$0.4183 (range $0.3236–$0.5274)** against a terra tree at **$1.0399 (range
$1.0342–$1.2638)** — complete non-overlap at n=3, the only clean separation in that wave.
Here the *root's own* calls stay terra in both arms, so the gap is expected to be
**smaller** than 161's 2.5×; the gate asks only for non-overlap, not for a magnitude.
**Stated weakness, attached to the verdict in advance:** at n=2 per side, complete
separation has probability **1/C(4,2) = 1/6 = 0.167** under exchangeability — far weaker
than the battery's n=5 (1/252) and weaker than 161's n=3 (1/20). A PASS here is a
*separated ranking at p=0.167*, and will be reported in exactly those words.

### `G-CF2` — wall (ranking, no separation required)

> S3 median wall under `openai-cheap-fast` **≤** S3 median wall under the shipped `openai`
> matrix.

**Why achievable and honest:** 161 measured the luna-pinned arm as the **fastest** of five
arms (235.6 s median) and the cheap arms' wall ranges did not overlap the expensive ones'.
No separation is demanded because wall variance is large (161: `ctl-legacy` 301.7–571.5 s)
and n=2 cannot separate it. A tie fails this gate; a ranking loss fails it.

### `G-CF3` — quality FLOOR (not non-inferiority)

> S3 **median total ≥ 75** (the scenario's own pass threshold) AND **no graded run below 70**.

**Why a floor and not non-inferiority.** The preset's own contract is *"gives up quality
headroom"* (PRESETS.md §1). A non-inferiority gate would be a claim the preset never made
and, at n=2 on a near-ceiling instrument, one this lane cannot establish either way.
**Why these numbers:** 161 measured this arm at **80 / 90 / 88** (median 88), and 70 is the
recorded `luna-medium` baseline median. The floor is a real constraint, not a formality —
it is exactly the shape that catches 161's `cheap-fast-anth` run 02 (score **28**). **If
either run lands below 70 the preset does not ship**, whatever `G-CF1` says.

### `G-CF4` — S1 (the half 161 could not buy)

> On S1 at the same root, **both runs reach the scenario's terminal marker**
> (`completion=complete`), AND median cost/run under `openai-cheap-fast` is **lower** than
> under the shipped `openai` matrix.

**Why this shape.** 161's `G-P1` says "on both S1 and S3" and 161 bought only the S3 half.
S1 is where luna's delegation blow-up was measured (**$3.96 median, up to $13.50**), so it
is the scenario most able to falsify a cheap-tree claim. **Quality is deliberately not a
clause here:** S1 quality is ⛔ vacuous as a win by the battery's own report card (100% for
10/16 cells). No separation is demanded (n=2, and S1 cost variance is the largest in the
corpus: $0.40–$27.18 across cells).

### `G-GUARD` — the Anthropic guardrail (three independent legs, ALL must hold)

> **(a) File identity.** `git diff --stat origin/main...HEAD` shows `routing/anthropic.yaml`
> **absent** from the diff. Recorded pre-change md5: `b2540bd65f1481a937eb3843c925d650`.
>
> **(b) Resolution identity ($0, deterministic).** The repo's own golden-fixture test
> (`tests/test_default_resolution_unchanged.py`) passes for `anthropic.yaml` and every
> other recorded matrix, with the fixture **not regenerated**. This is strictly stronger
> than any live n=2 run: it checks every role, exactly, against the pre-feature recording.
>
> **(c) Live mapping (the leg a file check cannot cover).** With this PR's routing
> directory present in the container, an `SHIPPED:anthropic` arm at root
> `claude-haiku-4-5`, n=2 on S3: both runs complete, **median score ≥ 70**, **no run below
> 38** (the recorded baseline minimum across 10 haiku runs), and median cost/run within the
> recorded `haiku-high` envelope (baseline median **$0.8649**), read as **≤ $1.30** (+50%
> headroom for a different window).

**Why (c) is phrased as regression-detection, not non-inferiority.** The recorded haiku
baseline itself spans **38–88** at n=10. A non-inferiority gate at n=2 against a median of
78 would fail or pass on noise. "No run below anything ever recorded" is what "a mapping
regression cannot hide behind an unchanged file" actually means at this n, and it is
stated as such.

---

## 4. WHAT WOULD MAKE A PASS HERE WRONG

| gate | the evidence that would overturn a PASS |
|---|---|
| `G-CF1` | An S3 window where the terra root's own calls dominate the tree (fewer delegations) — the cheap-tree saving is proportional to delegated work, and a low-delegation workload would show no gap. Tree size is recorded per run for exactly this reason. |
| `G-CF2` | A wall win driven by *fewer completed sub-tasks* rather than faster ones. Tree LLM-call count and the S3 pass count are recorded per run to expose that. |
| `G-CF3` | n=2 clearing a floor 161's own n=3 cleared, then a third run landing at 28 (as `cheap-fast-anth` did). The floor is a tripwire, never proof of quality parity. |
| `G-CF4` | An S1 run whose cost is low because it *stopped early*. This is why completion is a clause of the gate and not a footnote. |
| `G-GUARD` | Nothing in a routing-matrix PR can move the anthropic path except the loader itself; leg (b) is the real check and leg (c) is the end-to-end confirmation. A (c) failure with (a)+(b) passing would indicate a provider-side or window effect, not a mapping regression, and would be reported that way. |

---

## 5. FREEZE

This file is committed **before** the first API call of this lane. The commit that
introduces it is the freeze point; `DONE-NOTE.md` records that sha and any deviation from
what is written above, including any gate that could not be run.
