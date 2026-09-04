# FINDINGS — LAYER B: is agent-frontmatter `model_role` honored on spawned children?

**Item:** `model_performance-cly` · **Lane:** `cly-layerb-agent-model-role`
**Branch:** `lane/cly-layerb-agent-model-role` · **Base:** `origin/main` = `7daf882`
**Spend: $0.00 against a $0.00 authority.** No container, no DTU, no API call. Every
number below is a deterministic read of shipped source or of a capture that already
existed on disk.

---

## VERDICT

# NO — on any install whose provider entries carry an explicit `id:`, an agent's own frontmatter `model_role` is silently ignored, and every such agent is spawned on the session's default provider ordering instead.

On a stock install where each provider mounts under its bare type name
(`anthropic`, `openai`), it IS honored. The defect is not "layer B is dead"; it is
"layer B dies exactly where the routing matrix's own recommended multi-instance
setup is used" — which is the eval harness, and the shipped
`docs/MATRIX_CURATOR_GUIDE.md:148` example, and this program's own dev host.

---

## 1. The mechanism, named at file:line

Three questions were asked. All three are answered from source, and two of the three
answers are **yes** — the failure is in the fourth step nobody had named yet.

### 1a. Does hooks-routing's `session:start` hook FIRE for a spawned child? — **YES**

`amplifier_core/session.py:151` picks the lifecycle event mutually exclusively:

```python
event_base = SESSION_RESUME if self._is_resumed else SESSION_START
```

A spawned child is a freshly-constructed session object (`is_resumed=False`), so it
emits `session:start`. Confirmed in a real capture — the delegate child
`0000000000000000-c6df738e3a54433d_anchors-amp-dev-explorer` in
`treatment-validation/20260903-h7n-knobanth/runs/h7n-armA-s3-01/all-sessions/` has the
lifecycle sequence `session:fork → session:start → session:config → session:end`.

`hooks-routing` is in that child's mount plan: its `session:config` raw payload lists
`hooks-routing` as the 13th hook module. So the handler is registered and the event
fires.

### 1b. Does it SEE the child's agent configs? — **YES**

`__init__.py:385-389` reads them from `coordinator.config`:

```python
agents = coordinator.config.get("agents", {}) if hasattr(coordinator, "config") else {}
```

The same capture's child shows **13 agents in `config["agents"]`, all 13 carrying a
declared `model_role`**. The parent shows the identical 13. So the handler is looking
at a populated dict, not an empty one.

### 1c. WHERE does it write the resolved `provider_preferences`? — in-place, into the LIVE session config

`__init__.py:477`:

```python
agent_cfg["provider_preferences"] = prefs
```

`agent_cfg` is a value of `coordinator.config["agents"]`. **`coordinator.config` is the
live dict, not a per-call copy** — verified against the real Rust kernel, not inferred:

```
coordinator.config is cfg?            True
agents dict identity vs cfg:          True
after in-place mutate, session.config: {'model_role': [...], 'provider_preferences': [...]}
```

And the write is visible downstream: `session:start` is emitted **before**
`session:config`, so a mutation made in the handler appears in the `session:config`
raw payload. Also verified against the real kernel (`_session_exec.py:61-70` documents
the ordering; the probe proves it):

```
[["session:start",  {"architect": 1}],
 ["session:config", {"architect": 1}]]
```

Both probes are reproduced in `evidence/kernel-probes.md`.

**Consequence for the h7n capture: it is a VALID readout of layer B.** `n_prefs: 0`
there is not a timing artifact. The handler ran, saw the agents, and wrote nothing.

### 1d. Why it wrote nothing — `resolver.py:192-208` reached with `coordinator=None`

`resolve_model_role` asks `find_provider_by_type` whether a matrix candidate's bare
`provider:` type is installed. That function has two strategies
(`resolver.py:184-208`):

1. **Direct key match** against the mounted `providers` dict — `anthropic`,
   `provider-anthropic`, the prefix-stripped form.
2. **Coordinator-backed fallback** — used when every instance of a module is mounted
   under its own explicit `id:` and none is keyed by the bare type. It reads
   `coordinator.config["providers"]` (`_get_provider_specs`, `resolver.py:56-71`) to map
   instance ids back to module types.

Strategy 2 is gated on the `coordinator` argument:

```python
provider_specs = _get_provider_specs(coordinator)
if not provider_specs:
    return None
```

**Layer A passes it. Layer B did not.**

| layer | call site | `coordinator=` |
|---|---|---|
| A — caller-supplied `model_role` via the `model_role_resolver` capability | `resolver_class.py:220` | **passed** |
| B — agent's own frontmatter `model_role` at `session:start` | `__init__.py:450-459` (pre-fix) | **omitted** |

With `coordinator=None`, strategy 2 is disabled, every candidate is skipped,
`resolve_model_role` returns `[]` (`resolver.py:406`), the `if resolved:` guard at
`__init__.py:460` is false, and **no key is written at all**. That is `n_prefs: 0`.

---

## 2. The capture says 11 of 13. The correct number is **13 of 13.**

The item reports "11 of 13 agents had `n_prefs: 0`". Re-reading
`wire/agent-prefs-armA.json` against the resolver's own output contract, the two
non-zero entries are **not** resolver output either:

| agent | `n_prefs` | top model | why this is NOT layer B output |
|---|---|---|---|
| `digital-twin-universe:dtu-profile-builder` | 1 | `claude-opus-*` | **A glob.** `_resolve_glob` (`resolver.py:409-466`) resolves a glob to a concrete name off `list_models()`; the resolver can never emit `*`. |
| `foundation:session-analyst` | 6 | `claude-haiku-*` | **Six preferences, and a glob.** `resolve_model_role` returns on its first match — a single-element list (`resolver.py:395-404`). Layer B writes exactly one preference or none. |

Both are hand-written frontmatter `provider_preferences:` pins — SPAWN_PRECEDENCE.md's
rank 2(a), which flows through unchanged whether or not a routing bundle is installed.

**So zero of the thirteen agents in that container carried resolver output.** Layer B
produced nothing for anyone.

This closes cleanly against the matrix that was loaded. Arm A ran
`default_matrix: anthropic`, and every one of `routing/anthropic.yaml`'s 13 candidates
is `provider: anthropic`. The container mounted ten provider instances and **every one
had an explicit `id:`** — `opus`, `sonnet`, `haiku`, and others — so `providers` had no
`anthropic` key at all. 13 roles × 0 reachable candidates = 0 resolutions. Observed: 0.

---

## 3. Blast radius

**The trigger is not "multi-instance". It is "the mount key is not the bare type
name".** `amplifier_app_cli/runtime/config.py:479-515` maps a settings entry's `id:` to
the mount plan's `instance_id`, unconditionally and with no count guard; the kernel
(`amplifier_core/_session_init.py`) then remaps that instance's mount name to the id.
One provider entry with `id: opus` is enough.

| install shape | layer B before this fix |
|---|---|
| Stock: no `id:` on any provider entry | **works** — provider mounts as `anthropic`, strategy 1 matches |
| Any entry whose `id:` equals its default mount name (e.g. `id: gemini`) | **works** — strategy 1 still matches |
| Any entry whose `id:` differs (`opus`, `sonnet`, `haiku`, `openai-internal`) | **broken for every candidate naming that bare type** |

**Which spawns:** all of them. Layer B is a parent-side mechanism — the parent resolves
its agents' declared roles at its own `session:start` and the resolved value is read at
spawn time by `session_spawner.py:575` and by tool-delegate's agent-level fallback
(`:1822`, per 67u). Nothing about the child's own mount plan is involved, so no spawn
path escapes it. Layer A (a caller passing `model_role` on the delegate call) is
untouched — it never used the broken path.

**What the failure looks like:** nothing. The child mounts the session's
priority-1 provider and reports a perfectly plausible model name. In the arm-A capture
the spawned `anchors-amp-dev:explorer` — frontmatter `model_role: ["general","fast"]` —
resolved to `{"basis": "priority", "provider": "opus", "model": "claude-opus-5"}`. A
`general`/`fast` agent ran on the top-tier reasoning model, and the only trace is the
word `priority` in a `provider:resolve` event.

**Is the DEFAULT single-instance install affected? No.** Stated plainly because the
item asked: a user who never named a provider instance was always fine. The people hit
are the ones who followed `docs/MATRIX_CURATOR_GUIDE.md:133-149` — the guide that
exists *because* the routing matrix wants per-tier instances.

---

## 4. Why it was never caught

Every pre-existing `session:start` test mounts providers keyed by the **bare type
name** — `_providers()` in `test_knob_consistent_routing.py:91-92` returns
`{"openai": ...}`. That is strategy 1, the branch that needs no coordinator. The
coordinator fallback added for #57 was tested at the `find_provider_by_type` /
resolver-capability level (layer A) and never through the `session:start` handler.
The two layers were never asserted to agree.

`tests/test_session_start_multi_instance.py::TestLayerParity` now asserts exactly that.

---

## 5. The fix

One argument, `__init__.py`, in `_resolve_one`:

```python
 resolved = await resolve_model_role(
     model_role,
     effective_matrix,
     providers,
     preresolved_models=preresolved_models,
+    coordinator=coordinator,
     caller_context=agent_caller_context,
     ...
 )
```

`resolve_model_role` already accepts `coordinator` and already documents it as the
multi-instance fallback source (`resolver.py:294-299`). Nothing else changes: on a
stock install `find_provider_by_type` returns at strategy 1 before the coordinator is
ever consulted, so the default path is byte-identical.

**Fail-before / pass-after**, `modules/hooks-routing/tests/test_session_start_multi_instance.py`:

```
before:  4 failed, 3 passed
after:   7 passed
```

The 3 that passed before are the single-instance controls — they are there to prove the
fix does not move the default install.

Full suite: **594 passed** (587 at `7daf882`, +7 new). Ruff unchanged at the two
pre-existing findings (`F402 matrix_loader.py:346`, `F401 test_matrix_loader.py:5`).

---

## 6. Two things found on the way, filed rather than fixed

### 6a. `routing:*` telemetry is unrecordable by default — filed as part of this note only

`hooks-routing` emits `routing:matrix-loaded`, `routing:intent-clamped` and
`routing:role-pin-reasserted`. None is in the Rust kernel's `ALL_EVENTS`, and the
recorders' `additional_events` — read verbatim out of the arm-A capture's
`session:config` — do not include any `routing:*` name:

```
hook-context-intelligence -> ["delegate:agent_spawned", ..., "session:config", "mentions:resolved"]
```

`amplifier_foundation/bundle/_observability.py:27-30` is where that allow-list is
seeded. **Consequence for anyone reading a capture: the absence of a `routing:*` event
proves nothing.** In particular a probe reporting `n_clamp_events: 0` is measuring a
blind spot, not a zero. This cost this lane a wrong hypothesis before the allow-list was
read; it will cost the next reader the same unless the events are added to
`FOUNDATION_OBSERVABILITY_EVENTS` (a foundation change — **not this repo**, so not
attempted here).

### 6b. On a resumed ROOT session the handler never runs at all — filed as `model_performance-fde`

`session.py:151` is an either/or. `hooks-routing` registers only `session:start`
(`__init__.py:695-700`). The arm-A **parent**, driven as five separate resuming
processes, emitted `session:start ×1, session:resume ×4` — so four of five turns ran
with no layer B resolution, no role-pin reassert, and no matrix telemetry, *even on a
stock install where this lane's fix would otherwise make layer B work*.

This also contradicts a load-bearing comment in this repo: `role_pin.py:26-28` says the
reassert "Runs on every `session:start` -- including the one a RESUME fires". For a
**delegate child** that is true (the `git-ops` capture in `20260901-rebaseline` shows
`fork → resume → start`). For a **root** resume it is not.

Filed as `model_performance-fde` with the mechanism, the capture, and a candidate fix.
Deliberately **not** bundled into this PR: it is a different trigger with a different
blast radius, and it changes *when* the handler runs rather than *what it resolves*.

---

## 7. Scope kept

- Did **not** re-open the organic delegation path (h7n verified it healthy).
- Did **not** re-derive 67u's three ruled-out explanations.
- Did **not** modify `amplifier-app-cli` or `amplifier-foundation` — both were read and
  quoted only. The answer turned out to live in **this** repo, which is why a fix ships
  here.
- Did **not** run a container or a DTU. The $0 authority was sufficient and is unspent.
