# DONE-NOTE — `model_performance-cly` (LAYER B: agent-frontmatter `model_role`)

**Lane:** `cly-layerb-agent-model-role` · **Branch:** `lane/cly-layerb-agent-model-role`
**Repo:** `microsoft/amplifier-bundle-routing-matrix` · **Base:** `origin/main` = `7daf882`
**Outcome: branch A — RESOLVED.** Every deliverable is DONE. Nothing was recorded
NOT-POSSIBLE, and the cap never bound.

**Spend: $0.00 against a $0.00 authority. Residue: $0.00, unspent and not needed.**
No API call, no container, no DTU. The authority's arithmetic —
`0 runs × 0 arms × $0 / 1.00 = $0.00` — closed on first read: this was a source-read
question whose reproductions were already on disk, and it stayed one. The three
empirical checks that were run are local in-process kernel probes (see
`evidence/kernel-probes.md`), which cost nothing.

---

## Deliverables

| # | Deliverable | State |
|---|---|---|
| 1 | The mechanism named at file:line — does the hook fire for a spawned child, does it see the child's agent configs, where does it write? | **DONE** — all three answered from source, two confirmed against the real kernel. `FINDINGS.md` §1. |
| 2 | A plain verdict, unhedged, at the top of FINDINGS | **DONE** — `FINDINGS.md`, first section. |
| 3 | If NOT honored: blast radius + a fix with a fail-before test in a DRAFT PR | **DONE** — `FINDINGS.md` §3 (blast radius, incl. the explicit "is the default install affected?" answer), §5 (the fix). Fail-before 4F/3P → after 7P. |
| 4 | Full suite green, pasted in the PR body | **DONE** — 594 passed. |
| 5 | DRAFT PR on origin, branch `lane/cly-layerb-agent-model-role` | **DONE** — see `publication` in the lane marker. |
| 6 | This DONE-NOTE at `docs/lanes/cly-layerb-agent-model-role/DONE-NOTE.md` | **DONE** — never the repo root (item kez). |

Deliverable 4's alternate branch ("if honored, and `n_prefs: 0` had another cause") does
not apply: it is not honored. The characterization tests it would have asked for exist
anyway as the single-instance controls, which pin the path that *does* work.

---

## The answer, in one line

**Agent-frontmatter `model_role` is NOT honored on spawned children on any install whose
provider entries carry an explicit `id:`** — `hooks-routing`'s `session:start` handler
called `resolve_model_role()` without forwarding the `coordinator`, disabling the
multi-instance provider-lookup fallback, so every candidate was skipped and no
`provider_preferences` was ever written. Layer A always forwarded it
(`resolver_class.py:220`); that asymmetry is the whole defect, and the fix is one
argument.

---

## What was measured

Nothing new was run. What was *read*:

- **13 of 13** — the corrected count. The item said 11 of 13 agents had `n_prefs: 0`;
  re-reading `wire/agent-prefs-armA.json` against the resolver's output contract shows
  the two non-zero entries are hand-written frontmatter pins, not resolver output (one
  is a glob, which the resolver can never emit; the other has six preferences, and
  layer B writes at most one). **Zero agents in that container carried resolver output.**
- **2 real session captures** re-read off disk, parent and spawned child, from
  `treatment-validation/20260903-h7n-knobanth/runs/h7n-armA-s3-01/all-sessions/` — mount
  plans, hook lists, agent configs, lifecycle-event sequences, `provider:resolve` basis.
- **1 more capture** (`20260901-rebaseline/.../anchors-amp-dev-git-ops`) to check the
  resumed-delegate case before making a claim about resume behaviour.
- **3 in-process kernel probes**, reproducible, in `evidence/kernel-probes.md`.
- **7 new tests**, 4 of which fail on `origin/main` and pass after the fix.

Suite: **587 passed** at `7daf882` → **594 passed** after (+7). Ruff unchanged at the
two pre-existing findings (`F402 matrix_loader.py:346`, `F401 test_matrix_loader.py:5`),
which are not this lane's.

---

## Deviations and judgement calls, recorded

1. **The goal said "start in this repo; if the answer lives in `amplifier-app-cli`, say
   so and STOP."** The answer lives in **this** repo, so the lane continued and shipped a
   fix. `amplifier-app-cli` and `amplifier-foundation` were read and quoted (`session.py:151`,
   `_session_exec.py:61-70`, `session_spawner.py:568-575`, `runtime/config.py:479-515`,
   `_observability.py:27-30`) and **not modified**.

2. **A wrong hypothesis was carried for part of the lane and is recorded rather than
   hidden.** The absence of any `routing:matrix-loaded` event in the captures was briefly
   read as "the hook never ran". It is not evidence of that: no `routing:*` name is in
   the recorders' `additional_events` allow-list, so those events *cannot* appear in any
   capture. Written up as `FINDINGS.md` §6a because the next reader will hit the same
   trap — and because it means a probe reporting `n_clamp_events: 0` is reporting a blind
   spot, not a zero.

3. **A second, distinct defect was found and filed, not fixed.** On a resumed **root**
   session the handler never runs at all (`session.py:151` is either/or; this module
   registers only `session:start`). Measured: the arm-A parent emitted
   `session:start ×1, session:resume ×4`. It also contradicts this repo's own
   `role_pin.py:26-28`. Filed as **`model_performance-fde`**, linked discovered-from
   `cly`. Kept out of this PR deliberately — different trigger, different blast radius,
   and it changes *when* the handler runs rather than *what it resolves*. Bundling it
   would have made a one-argument parity fix unreviewable.

4. **No infrastructure was created**, so nothing was registered in the infra ledger and
   nothing needed tearing down. `sweep` was never run.

---

## What remains open

- `model_performance-fde` — the resumed-root gap, filed with mechanism, capture and a
  candidate fix. Unpriced; answerable at $0 from source and existing captures.
- Adding `routing:*` to `FOUNDATION_OBSERVABILITY_EVENTS` so routing decisions are
  visible in captures at all. That is an `amplifier-foundation` change and therefore
  **out of this lane's repo boundary** — named in `FINDINGS.md` §6a, not filed as an
  item, because this lane cannot judge foundation's allow-list policy.
- Whether the fix changes real routing on a live multi-instance host is **not** claimed
  here. It is proven at the unit level and against the captured mount plan; a wire-level
  confirmation would need a run, which this lane had no authority to buy and did not need.
