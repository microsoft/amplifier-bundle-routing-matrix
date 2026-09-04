# model_performance-fde — hooks-routing never ran on a resumed ROOT session

Lane `fde-resume-session-routing`. Parent commit `d8c6a32` (cly's PR #60).
Spend: **$0.00** — source read plus committed captures. Nothing was run, bought,
or provisioned.

---

## 1. The defect, confirmed at source

`amplifier_core/session.py:145-151` emits exactly one lifecycle event per
session object, choosing it **mutually exclusively**:

```python
if not self._lifecycle_event_emitted:
    self._lifecycle_event_emitted = True
    from .events import SESSION_RESUME, SESSION_START
    event_base = SESSION_RESUME if self._is_resumed else SESSION_START
```

`hooks-routing` registered only for `"session:start"`
(`__init__.py:715` at `d8c6a32`). So on a resumed ROOT session — every
interactive `amplifier` resume and every multi-turn eval driver —
`on_session_start` never ran, taking with it:

- layer-B resolution of every agent's declared `model_role`,
- the 74w role-pin reassert (`role_pin.reassert_own_role_pin`),
- the `routing:matrix-loaded` source telemetry.

## 2. Measured, from committed captures ($0)

`evidence/lifecycle_census.py` over
`.amplifier/evaluation/treatment-validation` — 1462 `events.jsonl` files
(`context-intelligence/` mirrors excluded to avoid double-counting):

| | |
|---|---|
| root sessions | 633 |
| … that resumed at least once | **212** |
| lifecycle legs across those | 1238 |
| legs that fired `session:start` | 212 |
| **legs with the handler NOT invoked** | **1026 (82.9%)** |

The cited capture, verbatim (`evidence/delegate-resume-order.txt`) — a root
session driven over 5 executions as separate resuming processes:

```
session:start   x1
session:resume  x4
session:config  x5
session:end     x5
```

Only the first process fired `session:start`.

## 3. The trap the goal flagged — and it was real

The goal's likely fix was "register the same handler for `session:resume`
alongside `session:start`; the two events are mutually exclusive per process, so
no double-run." **The mutual-exclusivity premise is true of the kernel and false
of production**, so the naive fix would have regressed the very deliverable that
demanded no double resolution.

A resumed **delegate child** receives BOTH events, on the same bus, ~5 ms apart:

```
fork, start,  config, end,
fork, resume, START,  config, end,     <- resumed leg
fork, resume, START,  config, end
```

`amplifier_app_cli/session_spawner.py:1763-1774` emits its own observability
`session:resume` on the **child coordinator's own hooks bus** ("Emit
session:resume event for observability"), and the reconstructed child session
(`is_resumed=False`) then emits the kernel `session:start`. Registering the same
handler on both events without a guard would have double-resolved every agent
and emitted `routing:matrix-loaded` twice on every delegate resume leg.

**Discriminator, measured corpus-wide:**

| session:resume payload | carries `turn_count` | n |
|---|---|---|
| delegate child (spawner observability emit) | yes | 102 |
| root (kernel lifecycle emit) | no | 1029 |

100% separation, n=1131.

**What shipped** (`modules/hooks-routing/amplifier_module_hooks_routing/__init__.py`):

1. a hard **once-per-mount latch**, so "runs exactly once" is a property of this
   module rather than a bet on another package's emit count — it holds against
   an emitter nobody has written yet;
2. the **`turn_count` discriminator**, so a delegate leg still runs at
   `session:start` exactly where it ran before. Not merely "once" — *same event,
   same ordering*, i.e. byte-identical rather than coincidentally equivalent.

## 4. Adjudication: the 74w role-pin claim

**The claim.** `role_pin.py` (module docstring) said "`session:start` fires on
the resumed leg *before* the first `provider:resolve`", and `__init__.py`'s
inline comment said the handler "Runs on every session:start — including the one
a RESUME fires."

**Verdict: true for the population 74w measured, false as a general statement.**

- 74w's capture is a **delegate child**
  (`0000000000000000-25443a97b60d4965_anchors-amp-dev-git-ops`). A resumed
  delegate child is reconstructed with `is_resumed=False` and therefore really
  does emit `session:start` on its resumed leg — confirmed in the corpus, 68
  delegate children resumed and every resumed leg shows `fork → resume → START`.
  **74w's fix is live there.**
- A resumed **root** session emits `session:resume` instead. **74w's reassert
  never ran on any root resume between 74w landing and this change.**

**Why the 74w test could not have caught it.**
`test_role_pin_survives_resume.py::_fire_session_start` simulates a resume by
*firing `session:start`*. It pins what the handler does once invoked and never
asks which event a resume actually emits. Both the file and the source docstring
are corrected in this PR rather than left to mislead the next reader.

**Blast radius of the 74w gap: nil — and this matters.** The goal anticipated
this would be "a bigger finding than this fix". Measured, it is not:

> **0 of 212** resumed root sessions in the committed corpus declared a
> session-level `provider_preferences`.

Root sessions do not carry role pins; delegates do, and delegates fire
`session:start`. So on every one of those 1026 skipped legs the reassert would
have found no pin and returned `None`. The gap was real and the reassert it
silenced was a no-op every time. **The materially affected half of fde is layer
B, not the role pin** — reported this way round rather than inflated, because an
overstated finding costs the next reader exactly as much as a buried one.

## 5. Does any published measurement move?

**Yes, potentially — for layer B, and the affected population is named.**

| | |
|---|---|
| resumed root sessions whose agents declared `model_role` | **212 of 212** |
| agent definitions carrying `model_role` across them | 2774 |
| legs where that resolution was skipped | 1026 |
| resumed roots that **spawned a delegate on a skipped leg** | **43** |
| delegate spawns on a skipped leg | **82** (74 root/delegate pairs) |

Layer B writes `provider_preferences` into `coordinator.config["agents"][name]`,
which `session_spawner.py:568-575` reads *at spawn time*. So the defect only
changes an outcome where a delegate was actually spawned during a skipped leg.
That population is enumerated in `evidence/affected-spawns-for-34l.txt` and is
handed to **`model_performance-34l`** as its exact re-read set.

**Two honesty constraints on that number, both load-bearing:**

1. **This does not overlap cly's defect the way one might assume.** cly's defect
   (missing `coordinator=`) disabled layer B only for matrix candidates whose
   bare provider type is not itself a mounted key. In 209 of 212 of these
   captures a bare-type key *was* present (`openai`), so layer B was partly live
   on `session:start` legs and resolving `openai`-typed candidates. It resolved
   **nothing** on resume legs. The two defects are additive here, not redundant
   — fde cannot be waved off as "cly already zeroed it".
2. **Absence of `routing:*` events proves nothing.** Per cly's FINDINGS §6a they
   are in no recorder's allow-list. This lane therefore reports *which spawns
   occurred on an unresolved leg*, and does **not** claim which model each one
   landed on. Establishing that requires comparing each delegate's actual
   requests against what its declared `model_role` would have resolved to —
   that is 34l's work, not a claim made here.

## 6. What shipped

| file | change |
|---|---|
| `modules/hooks-routing/amplifier_module_hooks_routing/__init__.py` | register `session:resume`; once-per-mount latch; spawner-emit discriminator; corrected comments |
| `modules/hooks-routing/amplifier_module_hooks_routing/role_pin.py` | corrected the "fires on the resumed leg" claim, with the measured scope |
| `modules/hooks-routing/tests/test_resume_lifecycle.py` | **new**, 8 tests |
| `modules/hooks-routing/tests/test_init.py` | two `register.call_count == 2` → `== 3`, plus an explicit `session:resume` assertion |
| `modules/hooks-routing/tests/test_role_pin_survives_resume.py` | docstring: names its own scope honestly |

**Fail-before**, at parent `d8c6a32` (`evidence/fail-before.txt`): **6 failed, 2
passed** of the 8 new tests. The 2 that pass before the change do so *by design*:

- `test_kernel_emits_exactly_one_lifecycle_event_per_process` executes the
  kernel's either/or against the **shipped** `amplifier_core.session` over three
  `execute()` calls per direction — the deliverable said prove it, not assert
  it, so it is exercised rather than mocked;
- `test_session_start_leg_is_unchanged` is the byte-identity control and must
  pass on both sides of the diff.

**Suite: 594 → 602, green** (`PYTHONPATH=modules/hooks-routing python3 -m pytest
tests modules/hooks-routing/tests -q`). Ruff: the same 2 pre-existing findings
(`F402 matrix_loader.py:346`, `F401 test_matrix_loader.py:5`), none introduced.

## 7. Left open

- **`model_performance-34l`** — the 82 spawns above are its re-read set.
- **Upstream, not touched here (scope-out):** two independent emitters put
  `session:resume` on one bus with different payload shapes, and a "resumed"
  delegate child reports `is_resumed=False`. Both are app-cli/kernel concerns.
  This module now tolerates them; it cannot fix them, and did not try.
