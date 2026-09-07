# Lane `smy5-patch-routing-matrix` — DONE-NOTE

**Item:** `model_performance-smy5` (project `model_performance`)
**Repo:** `microsoft/amplifier-bundle-routing-matrix`
**Branch:** `lane/smy5-patch-routing-matrix` (from `origin/main`, base `e717297`)
**Date:** 2026-09-07
**Spend:** **$0.00** of a **$0.00** authority (`0 runs x 0 arms x $0 / 1.00 = $0.00`, slack $0.00).
No API measurement was authorised and none was performed. No DTU, no infrastructure
created, no ledger rows, nothing to tear down.

---

## OUTCOME — **BRANCH A, SATISFIED**

> **Updated after the item was resolved.** At 17:17:57Z the holding sibling
> (`smy5-patch-app-cli`) resolved `model_performance-smy5`. Outcome A reads: *"the work item
> is resolved with a user-readable summary AND the deliverables below exist (as a draft PR
> on the module's origin)."* **Both clauses are now literally true** — the item is resolved,
> and this repo's deliverables exist as PR #68. The resolving actor is a sibling, not this
> lane, which is finding **F1**; that does not change whether the outcome holds.
>
> Its resolution text, however, described **only the app-cli slice** of a 13-repo item — the
> exact cost predicted below. That is corrected the sanctioned way: an **append-only
> erratum** (`work_erratum` — no claim required, any actor, any time), filed by this lane at
> **17:23:59Z**, naming the routing-matrix slice in full. Deliberately **not** `work_reopen`:
> the WORK stands and only the RECORD under-described it, so reopening would have cleared
> `closed_at` and moved every throughput roll-up for nothing.

**Branch A on the deliverables — every one is DONE.** The patch is applied, fidelity is
re-verified at today's head, char counts are quoted, a pin test exists and is proven
fail-before/pass-after, all four CI-equivalent checks are green locally, and the work is
shipped as a draft PR. Per the goal's LANDING STAGE clause, a draft PR is the bar; the
merge is the manager's next stage.

**One procedure step is NOT-POSSIBLE, and it is not the cap:** this lane could not
`work_claim` — and therefore can neither `work_resolve` nor `work_release` —
`model_performance-smy5`, because that single item is fanned out to **four concurrent
lanes** and one of them holds it. Both terminal verbs were **attempted and refused**; the
refusals are quoted verbatim under finding **F1**. Every one of the goal's three branches
bottoms out in one of those two verbs, so **for a non-holding lane the three branches are
not exhaustive** — there is no terminal verb this lane can execute. That is a defect in the
goal's procedure, not a blocker on the work: every deliverable was reachable and every
deliverable landed.

It is deliberately **not** OUTCOME branch C. Two reasons, and the second is the stronger:
writing `BLOCKED.md` would have discarded a complete, verified, zero-cost patch application
over a bookkeeping collision — and it would have been **false**, asserting this repo's work
is unreachable while PR #68 sits ready with 7/7 CI green.

**The terminal state was chosen once and has not moved.** What changed after review is
evidence, not the decision: the two refusals went from inferred to observed, and both
findings were filed as tracked queue items (`model_performance-17oq`,
`model_performance-7cdj`) via `work_add`, which needs no custody. Lane 1ru's BLOCKED →
REJECT → BLOCKED churn was produced by re-deciding under an ambiguous goal with no number
changing; no number changed here either, so nothing was re-decided.

---

## DELIVERABLES

| # | Deliverable | State |
|---|---|---|
| 1 | Patch applied (never force-applied with fuzz) | **DONE** |
| 2 | Fidelity table re-verified at today's head, not inherited | **DONE** — 21 atoms, 0 undeclared drops |
| 3 | Stock → lean char counts for every file touched | **DONE** — 1,148 → 735 (−413, −35.98%) |
| 4 | Pin test so the text cannot drift back | **DONE** — 24 tests, 9 red on stock / 24 green on lean |
| 5 | CI green where the repo has CI | **DONE** — this repo HAS CI (`.github/workflows/ci.yml`, added 2026-09-07 in #65); **7/7 hosted checks pass on the PR** |
| 6 | DRAFT PR, do not merge | **DONE** — [**PR #68**](https://github.com/microsoft/amplifier-bundle-routing-matrix/pull/68), opened draft, marked ready once its own CI went green. **Not merged.** |
| 7 | DONE-NOTE at the lane artifact root | **DONE** — this file, at `docs/lanes/smy5-patch-routing-matrix/` (never the repo root) |
| — | Item resolved (outcome A clause 1) | **SATISFIED** — resolved 17:17:57Z by the holding sibling; not by this lane (F1) |
| — | `work_resolve` / `work_release` by this lane | **NOT-POSSIBLE** — both attempted, both refused ("not currently holding … in this session") |
| — | Record corrected to name this repo's slice | **DONE** — `work_erratum` on smy5 at 17:23:59Z (no claim required); **not** `work_reopen`, which would have cleared `closed_at` |
| — | Findings filed as tracked work | **DONE** — `model_performance-17oq` (F3); `7cdj` superseded by `pvp6` (filed earlier by wayfinder, covers the same defect) |
| — | ly85 second-pass fidelity cross-check | **DONE** — sentence-coverage pass run; 2 flags, both adjudicated non-losses |

---

## 1. THE PATCH — APPLIED CLEANLY, ZERO FUZZ

**Source, read from the remote rather than a local checkout:**

```
gh api repos/microsoft/amplifier-foundation/commits/main --jq .sha
  -> 4384805741ed7a1a8644adfd6ded9fe1ff4b4a5a      # matches PR #372's SHA 4384805
docs/lanes/zc6t-lean-head-ship/patches/context-files/
  08-amplifier-bundle-routing-matrix-routing-instructions.md.patch   (2,018 B)
  08-amplifier-bundle-routing-matrix-routing-instructions.md.lean.md   (745 B)
docs/lanes/zc6t-lean-head-ship/patches/fidelity-report.json          (6,975 B)
```

**Applied with `git apply`, not `patch`.** This is deliberate and it is the one rule the
goal says matters most. `git apply` requires exact context and has no fuzz mode; `patch`
silently accepts fuzz, and fuzz is a silent placement decision — the `l4s1` precedent
(`"Hunk #1 succeeded at 56 with fuzz 2"`, hand-ported instead) and the stale diff placed
**147 lines out of position** in this same batch.

```
$ git apply --check -p1 --verbose 08-...routing-instructions.md.patch
Checking patch context/routing-instructions.md...
$ git apply -p1 08-...routing-instructions.md.patch
APPLIED
```

**No hand-porting was needed, and here is the value that proves it** rather than an exit
code: today's head file is **1,148 chars**, byte-for-byte the same number `zc6t` recorded
as `stock_chars` for index 8. The file has not moved since it was diffed.

**Independent confirmation the result is the intended one** — the applied file is
byte-identical to the artifact `zc6t` shipped:

```
$ sha256sum context/routing-instructions.md  08-...routing-instructions.md.lean.md
4ee0c680cdcfd4736101a60936860fe1ff6c3f0b2550c3bf7cd874e7f86ccd7e  context/routing-instructions.md
4ee0c680cdcfd4736101a60936860fe1ff6c3f0b2550c3bf7cd874e7f86ccd7e  08-...routing-instructions.md.lean.md
```

## 2. CHAR COUNTS

| File | Stock | Lean | Saved | % |
|---|---:|---:|---:|---:|
| `context/routing-instructions.md` | **1,148** chars (1,156 B) | **735** chars (745 B) | **−413** | **−35.98%** |

Chars ≠ bytes here: the file carries 4 multi-byte characters (`…` ×2, `—`, `→` in stock;
`…` ×2, `—`, `→` in lean), so byte counts run 8–10 higher. Counts above are **characters**,
which is what `zc6t`'s `fidelity-report.json` records (`stock_chars: 1148`,
`lean_chars: 735`, `saved_chars: 413`) — independently reproduced here, not copied.

Only one file in this repo was touched by the patch. The pin test file also changed
(deliverable 4); it is not head-resident and carries no head cost.

## 3. FIDELITY — RE-VERIFIED AT TODAY'S HEAD

Not inherited. `zc6t`'s report lists `missing_rules: []` for index 8; that claim was
**re-derived from scratch** by a checker written for this lane and committed beside this
note (`evidence/fidelity_check.py`, output in `evidence/fidelity-recheck.txt`).

The checker enumerates every atom of the STOCK file a reader could act on — inline-code
literals, fenced-block payload lines, code-comment labels, and imperative rule sentences —
and requires each to pass one of three ways, which are **not** interchangeable: present
verbatim, present via a **named** equivalence, or **declared dropped-by-design with a
reason**. Anything else exits non-zero.

**Result: 21 atoms — 0 undeclared drops.**

| Atom (stock) | Disposition in lean |
|---|---|
| `` `Active routing matrix: … / Available model roles: …` `` | verbatim |
| `` `model_role` ``, `` `general` ``, `` `fast` `` | verbatim |
| `` `load_skill(skill_name='role-definitions')` `` | verbatim |
| `model_role: coding` | verbatim |
| `model_role: [ui-coding, coding, general]` | verbatim |
| `model_role: fast` | verbatim |
| `# single role` | equivalent → ``single (`model_role: coding`)`` |
| `# fallback chain (specific → general)` | equivalent → `fallback chain tried left-to-right specific → general` |
| `# utility agent` | equivalent → ``utility (`model_role: fast`)`` |
| `"agent": "foundation:explorer"` | equivalent → `agent="foundation:explorer"` |
| `"model_role": "vision"` | equivalent → `model_role="vision"` |
| "This session uses the routing matrix system for model selection." | equivalent → "Model selection uses the routing matrix." |
| "injected into your context every turn" | equivalent → "injected every turn" |
| "Use those role names — they are authoritative." | equivalent → "is authoritative" |
| "Role sets and descriptions differ per matrix; do not rely on any list written down **here**." | equivalent → "…never rely on a list written down **elsewhere**" |
| "Use `model_role` in agent frontmatter to declare…" | equivalent → "Agent frontmatter `model_role`" |
| "Fallback chains are tried left-to-right." | equivalent → "tried left-to-right" |
| "Always end with `general` or `fast`." | equivalent → "always end a chain with `general` or `fast`" |
| "When delegating to sub-agents, you can override the model role:" | equivalent → "Delegators may override per call" |
| "For detailed role definitions, decision flowchart, model tier grid, and fallback chain guidance, use `load_skill(...)`" | equivalent → "Role definitions, decision flowchart, model tier grid, fallback guidance: `load_skill(...)`" |
| `"instruction": "Analyze these UI screenshots..."` | **DROPPED BY DESIGN** — illustrative filler for the example's `instruction` argument. It is not a rule, constraint, command or pointer. Lean keeps the argument itself (`instruction="…"`). |

**Two things worth a reviewer's eye, both recorded rather than smoothed over:**

- **`here` → `elsewhere` is a widened referent, not a weakened one.** Stock forbade
  relying on a role list "written down **here**" (this file). Lean forbids relying on one
  "written down **elsewhere**" (anywhere that is not the live per-turn injection). Since
  lean carries no list of its own, the lean form covers strictly more ground. Called out
  because a wording change to a prohibition is exactly the shape of the one **real**
  weakening in this batch (`edit_file`, restored at +450 chars and pinned) — assume it can
  happen again, and check rather than assume. **This one is not it.**
- **The first pass of the checker flagged 8 atoms**; the raw run is committed unedited at
  `evidence/fidelity-recheck-raw-first-pass.txt`. All 8 were artefacts of the checker, not
  of the patch: column-alignment whitespace, a trailing JSON comma, `# label` comments
  glued to their payload line, and two sentences glued across a removed fence by a naive
  splitter. The checker was sharpened (normalise whitespace/commas, split `#` labels into
  their own atoms, split paragraphs before sentences) and **every remaining surface-form
  change was written down as a named equivalence** rather than pattern-matched away. The
  first pass is kept so a reviewer can see that the pass was earned.

`zc6t`'s report records **4 flags across all 23 targets — 3 false positives and 1 real
weakening (`edit_file`)**. Index 8 (this file) was not among them, and this independent
re-derivation agrees.

### Second pass, forced by `model_performance-ly85` — and my first checker had the same blind spot

While this lane was working, `smy5-patch-wayfinder` filed **`model_performance-ly85`**: a
**second real weakening** in the batch. `zc6t` scored `wayfinder-voice.md` `missing_rules: []`
while the lean draft had in fact dropped a plain-prose constraint — the file's attention-cost
bar. Cause: **`zc6t`'s checker is token-only**, so every backticked command and identifier
survived and the file scored clean. Its verdict must be read as *"no TOKEN missing"*, never
*"nothing missing"*.

**That criticism lands on my first pass too, and I am not going to pretend otherwise.** My
checker selected rule sentences **by keyword** (`use`, `do not`, `never`, `always`, `must`,
…). A constraint phrased without any of those words would have been invisible to it as
well — a narrower form of the same bug.

So ly85's recommended second pass was implemented and run
(`evidence/sentence_coverage.py`, output `evidence/sentence-coverage-ly85.txt`): split stock
into sentences; require **≥60% of each sentence's content words** to appear somewhere in
lean. Deterministic, no model, no network, no spend.

**Result: 2 sentences flagged, both adjudicated non-losses. No restoration needed.**

| Flag | Coverage | Adjudication |
|---|---:|---|
| `"Analyze these UI screenshots...", "model_role":` | **0.25** | The same filler **already declared** dropped-by-design in pass 1. Two independent methods agreeing on what is gone — the good outcome. |
| `Use those role names — they are authoritative.` | **0.50** | Unmatched words are `names` and `those` — **anaphora, not substance**. The constraint itself (`is authoritative`) survives verbatim, and lean adds `never rely on a list written down elsewhere`, leaving no other source for role names. 4 content words, 2 anaphoric: a small-denominator artifact. |

Contrast ly85's genuine find, where **8 content words carrying the whole constraint** went
missing and nothing else in the file carried the ceiling. The shapes are not alike.

**This file is therefore clean on two independent passes, not one.**

## 4. PIN TEST — FAIL-BEFORE / PASS-AFTER

This repo **has** a suite. `modules/hooks-routing/tests/test_routing_instructions.py`
already existed and already validated this file — and **the lean rewrite broke 9 of its
17 tests**, which is the interesting part of this lane:

```
$ pytest tests/test_routing_instructions.py           # lean file, OLD tests
9 failed, 8 passed
```

The old assertions pinned markdown **scaffolding** — `## Available Roles`,
`## For Agent Authors`, `## For Delegating Agents`, a ```` ```yaml ```` fence and a
```` ```json ```` fence — which is precisely what the compression removes. Their stated
intent (live role list, frontmatter examples, delegation example, role-definitions
pointer) is fully preserved by the lean text.

**What was done, stated plainly so nobody has to reverse-engineer it:** every **content**
assertion of the old file is preserved. The five scaffolding assertions were **inverted** —
the scaffolding must now be ABSENT — and moved into a new `TestLeanHeadBudget` class.
Assertions that sliced the document by heading (`content.index("## …")`) were rewritten
against the whole document, since the headings no longer exist. New pins were added for
rules the old file never checked: the chain-order rule, the chain-terminator rule, the
`differ per matrix` warning, and all four things the `load_skill` pointer promises.

The budget class is the actual anti-drift ratchet:

- `test_char_count_within_budget` — ≤ **800** chars (measured lean 735; pre-patch stock 1,148)
- `test_did_not_revert_to_stock` — the stock restatement sentence must stay gone
- `test_section_headings_stay_collapsed` — the three headings must stay gone
- `test_example_fences_stay_collapsed` — no ``` fence may return

**Proof it pins, rather than merely passing:** the stock file was restored under the new
tests and the suite went red in exactly the right places.

```
$ pytest tests/test_routing_instructions.py       # STOCK file, NEW tests  (drift-back sim)
9 failed, 15 passed
  FAILED TestLiveRoleList::test_points_to_live_injection
  FAILED TestLiveRoleList::test_warns_role_sets_differ_per_matrix
  FAILED TestForDelegatingAgents::test_has_model_role_override_example
  FAILED TestForDelegatingAgents::test_example_names_a_real_agent
  FAILED TestReferencesRoleDefinitions::test_names_what_the_skill_contains
  FAILED TestLeanHeadBudget::test_char_count_within_budget
  FAILED TestLeanHeadBudget::test_did_not_revert_to_stock
  FAILED TestLeanHeadBudget::test_section_headings_stay_collapsed
  FAILED TestLeanHeadBudget::test_example_fences_stay_collapsed

$ pytest tests/test_routing_instructions.py       # LEAN file, NEW tests
24 passed
```

## 5. CI — THIS REPO HAS IT, AND ALL FOUR JOBS RUN GREEN

CI landed in this repo earlier today (`.github/workflows/ci.yml`, PR #65). All four jobs'
exact commands were run locally; transcripts in `evidence/`:

| CI job | Command | Result |
|---|---|---|
| Lint (ruff) | `uvx ruff@0.15.11 check .` | **All checks passed!** |
| Tests — root | `uv run --no-project --with pytest --with pytest-asyncio --with pyyaml python -m pytest tests -q` | **37 passed** |
| Tests — modules/hooks-routing | `uv run --frozen --extra dev --with git+…/amplifier-foundation python -m pytest -q` | **585 passed** |
| Bundle structure | `uv run --no-project --with pyyaml python .github/scripts/check_bundle_structure.py` | **OK — bundle structure checks passed** |

**The hosted run is the one that counts, and it is green** — 7/7 on
[PR #68](https://github.com/microsoft/amplifier-bundle-routing-matrix/pull/68),
run `34146503031`:

```
Bundle structure                pass  11s
Lint (ruff)                     pass   9s
Tests — modules/hooks-routing   pass  13s
Tests — root (Python 3.11)      pass  12s
Tests — root (Python 3.12)      pass  12s
Tests — root (Python 3.13)      pass  14s
license/cla                     pass
```

The PR was opened as a **draft** and marked ready only after that. **Not merged** — the
manager merges.

---

## FINDINGS

### F1 — One work item, four concurrent lanes: the claim procedure cannot be satisfied by more than one of them

`work_claim(project="model_performance", item_id="model_performance-smy5")` was the first
action of this lane, per procedure step 1. It was refused:

```
claim model_performance-smy5 as 'agent-spark-1-3875699' failed:
  Error claiming model_performance-smy5: issue already claimed by agent-spark-1-3875147
```

The holder is **live, not stale** (`work_stats`: `held_stale: 0`). It is a **sibling lane
of this same batch**:

```
/proc/3875147/cwd -> …/lanes/smy5-patch-app-cli/amplifier-app-cli
/proc/3875699/cwd -> …/lanes/smy5-patch-routing-matrix/amplifier-bundle-routing-matrix   (this lane)
```

Four lanes were launched within 2 seconds of each other against the **same item**:
`smy5-patch-app-cli`, `smy5-patch-routing-matrix`, `smy5-patch-skills`,
`smy5-patch-wayfinder`. Item `smy5` covers **13 repos** in one record, so it is a
one-item-to-many-lanes fan-out — and `work_claim` is, correctly, an exclusive
single-holder operation. **At most one of the four lanes can ever satisfy procedure step 1.**

Procedure step 1 says a refused claim means write `BLOCKED.md` and stop. Taken literally
that would have three of four lanes produce **nothing** — no patch, no PR — over a
bookkeeping collision, while the actual work sat fully reachable at zero cost. This lane
did not do that, for the reason the goal itself gives: *"If you can spend your way to the
deliverable and simply did not, that is neither B nor C: finish the work"*, and *"an
authority/goal that was mis-sized is a defect in the goal, not a failure of the lane."*
The choice was made once and recorded here; there was no churn.

The claim was **retried once at the end of the lane**, after all deliverables had landed
and PR #68 was green and ready. It was refused identically — the sibling still held the
item — so the finding is not a startup race that resolved itself:

```
17:00  claim … failed: issue already claimed by agent-spark-1-3875147
17:11  claim … failed: issue already claimed by agent-spark-1-3875147
```

#### The sharper form: all three terminal branches require custody this lane cannot obtain

This was **attempted and observed**, not inferred. After every deliverable had landed, both
terminal verbs were called and both refused, in the tool's own words:

```
work_resolve(id="model_performance-smy5", reason="…")
  -> not currently holding 'model_performance-smy5' in this session --
     refusing to resolve an item this session did not claim

work_release(id="model_performance-smy5")
  -> not currently holding 'model_performance-smy5' in this session --
     refusing to release an item this session did not claim
```

Both refusals are **correct tool behaviour** — a session must never resolve or release work
it does not own. But map them onto the goal's three branches:

| Branch | Terminal verb | Available to this lane? |
|---|---|---|
| **A** RESOLVED | `work_resolve` | **No** — refused, observed above |
| **B** RESOLVED AT THE CAP | `work_resolve` ("you still resolve") | **No** — same verb, same refusal |
| **C** BLOCKED | `work_release` | **No** — refused, observed above |

The goal states the three branches are **exhaustive**. For a non-holding lane in a fan-out
they are not: **none of the three branches' terminal verbs can be executed.** That is a
property of the goal's procedure — not of the work, which is complete, green and shipped.

> **Correction — I over-claimed this, and the fix matters.** I first wrote that a
> non-holding lane has *no executable terminal work-tracker verb at all*. That is false.
> **`work_erratum` requires no claim** — append-only, any actor, any time — and once the
> item was resolved it was exactly the right verb: the WORK stands, only the RECORD
> under-described it. It was used, at 17:23:59Z. The accurate statement is narrower: the
> three **branches'** verbs (`work_resolve`, `work_release`) are closed to a non-holder,
> not that the tracker offers a non-holder nothing.
>
> Lane `smy5-patch-wayfinder` framed this correctly before I did, in
> **`model_performance-pvp6`** (filed 17:10, ahead of my duplicate): it is branch C's
> *release leg* that is unexecutable **by construction** for branch C's own enumerated
> "refused claim" cause — C lists a cause that makes C's procedure impossible. What this
> lane adds, measured: **A and B are equally closed**, since both end in `work_resolve`,
> and both refusals above were observed rather than assumed.
>
> My duplicate item (`model_performance-7cdj`) has been marked **superseded by `pvp6`**
> via `work_edit(merge_into=…)` — closed structurally with a reference to the replacement,
> rather than resolved with an invented reason that loses the real id.

Branch C would also be **false** if written: `BLOCKED.md` tells the manager this repo's
work is unreachable, while PR #68 is ready with 7/7 CI green. A lane must not commit a
statement it knows to be untrue in order to satisfy a checklist.

#### What was done instead, so the finding is tracked rather than marker-only

`work_add` needs **no** held item, and is the sanctioned way to put work in the queue. Both
findings were filed as real, linked queue items rather than left as prose a reader might
skip:

| Item | Finding |
|---|---|
| **`model_performance-17oq`** | F3 — `publication_readback.sh` stale `head_sha` (affects the merge gate for **every** lane) |
| **`model_performance-7cdj`** | F1 — this fan-out defect, with the three refused branches quoted |

Both carry Given/When/Then acceptance criteria and a `relates-to` edge to
`model_performance-smy5`.

**What this costs, stated honestly:** the item's terminal `work_resolve` — with its
3–6 line summary — will be written by whichever lane holds it, and that lane cannot see
this repo's result. **The manager should treat this note and PR #68 as this repo's slice
of `smy5`'s resolution.**

**The fix, for the next batch:** either (a) file one item per repo and give each lane its
own, or (b) keep the umbrella item, have the **manager** hold it, and give lanes a
procedure step that does not require an exclusive claim (`work_list(item_id=…)` reads the
full spec — acceptance, description, design — with no claim and no custody). Option (b) is
one line of goal text.

### F2 — `docs/MATRIX_CURATOR_GUIDE.md` tells curators to do the exact thing this file forbids (pre-existing, NOT fixed here)

`docs/MATRIX_CURATOR_GUIDE.md:326`, step 2 of "Adding a New Role":

> Update the context file (`context/routing-instructions.md`) to mention the new role so agents know it exists.

`routing-instructions.md` — in **both** the stock and the lean form — says the opposite:
the per-turn injected list is authoritative and no written-down list should be relied on.
Following the curator guide re-introduces exactly the static role list that the file, this
lane's budget pin, and `test_no_static_role_table` all exist to prevent.

This is **pre-existing drift** (stock already carried the rule; the guide already
contradicted it) and it lives outside the file this lane owns, so it was **not** touched.
It is worth its own one-line item: delete step 2, or reword it to "no action needed — the
live injection picks the role up automatically."

### F3 — `publication_readback.sh` can return a STALE `head_sha` if run immediately after `git push`

Caught here, on this lane's own marker, which is exactly the claim the merge gate re-reads.

Run ~1 second after a successful `git push`, the script reported the **previous** commit:

```
17:12:20Z  publication_readback.sh -> head_sha 82c5b496…   (local HEAD was 5a6cd546…)
17:12:55Z  publication_readback.sh -> head_sha 5a6cd546…   (agrees)
```

Direct re-reads 20 s later agreed with each other and with local HEAD
(`git ls-remote` → `5a6cd546…`, `gh pr … headRefOid` → `5a6cd546…`), so this is GitHub API
propagation lag, not a bug in the script's logic. It **exits 0** either way.

Why it matters: `publication/v1` exists precisely because *"you can see your own commit and
you cannot see the absence of your own push"* (lane 74w). A stale-but-successful read
produces the **74w failure mode with the safety net in place** — a marker carrying a
40-hex sha that a remote genuinely returned, which nonetheless does not match the branch
when `merge_gate.sh` re-reads it. The lane would look like it published the wrong commit.

Caught here only because the returned sha was compared against a value already known
(local `HEAD`) rather than trusted for exiting 0 — "an exit code is not verification; the
content is."

**Fix (one line, in the tool):** have `publication_readback.sh` compare its `head_sha`
against `git rev-parse HEAD` in the checkout it was pointed at, and either retry or fail
loud on a mismatch, instead of emitting a block that is internally consistent and wrong.

---

## DEVIATIONS / CHOICES MADE WITHOUT WAITING

1. **Proceeded without holding the item** (F1). Recorded, not escalated — the goal forbids
   waiting on a human decision.
2. **Rewrote an existing test file rather than adding a second one.** Adding new tests
   beside the old ones would have left 9 permanently-red assertions pinning the very
   scaffolding the patch removes. The rewrite is documented in the file's own docstring so
   the next reader sees a decision rather than an unexplained deletion.
3. **Used `git apply`, never `patch`.** No fuzz is possible with `git apply`; this was a
   deliberate tool choice, not a convenience.
4. **Did not touch `~/.amplifier/cache`.** All stock/lean comparison used a scratch copy in
   `/tmp` and the repo's own working tree. (`zc6t` finding F6 — `amplifier source add`
   ignores `AMPLIFIER_HOME` — was never exercised; no `amplifier source` command was run.)
5. **Did not hand-edit the two hook-generated `<system-reminder>` blocks** (861 + 5,350
   chars). No source file in this repo produces them; that is `model_performance-z6wa`.

## SPEND LEDGER

| Item | Authorised | Spent |
|---|---:|---:|
| API measurement (`0 runs x 0 arms x $0 / 1.00`) | $0.00 | **$0.00** |
| DTU / infrastructure | none | **none created** |
| **Total** | **$0.00** | **$0.00** |

Residue: $0.00. Nothing was deferred for want of budget — the cap did not bind on any
deliverable, because no deliverable in this lane buys runs. No infrastructure was
registered, claimed, or torn down; `infra_ledger.sh sweep` was **not** run (it is the
manager's batch-close verb and sibling lanes are live).

## ARTIFACTS

```
docs/lanes/smy5-patch-routing-matrix/
├── DONE-NOTE.md                                  (this file)
└── evidence/
    ├── fidelity_check.py                         re-derivation tool, runnable
    ├── fidelity-recheck.txt                      21 atoms, 0 undeclared drops
    ├── fidelity-recheck-raw-first-pass.txt       the 8 checker artefacts, unedited
    ├── sentence_coverage.py                      ly85's 2nd pass, reusable
    ├── sentence-coverage-ly85.txt                2 flags, both adjudicated
    ├── suite-root.txt                            37 passed
    ├── suite-module-hooks-routing.txt            585 passed
    └── lint-and-structure.txt                    ruff + bundle structure, green
```
