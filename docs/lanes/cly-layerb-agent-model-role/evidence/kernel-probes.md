# Kernel probes — reproducible, $0, no network

Two claims in `FINDINGS.md` are about the **real Rust kernel**, not about this
module, and both were checked rather than assumed. Neither probe makes a network
call, spawns a container, or touches a provider.

Run with the interpreter of an installed amplifier (the probes need
`amplifier_core._engine`, `context-simple` and `loop-streaming`):

```
$(dirname $(command -v amplifier))/python probe_config_identity.py
$(dirname $(command -v amplifier))/python probe_event_order.py
```

---

## Probe 1 — `coordinator.config` is the LIVE dict, not a per-call copy

Claim under test: `__init__.py:477`'s in-place `agent_cfg["provider_preferences"] = prefs`
actually persists into the session config that `session_spawner.py:575` later reads. If
`coordinator.config` returned a fresh dict converted from Rust on every access, layer B
would write into a throwaway and be inert *even with the fix*.

```python
# probe_config_identity.py
from amplifier_core._engine import RustSession

cfg = {
    "session": {"orchestrator": "loop-streaming", "context": "context-simple"},
    "agents": {"architect": {"model_role": ["reasoning", "general"]}},
}
s = RustSession(config=cfg)
co = s.coordinator

print("coordinator.config is cfg?     ", co.config is cfg)
print("agents dict identity vs cfg:   ", co.config.get("agents") is cfg["agents"])

co.config["agents"]["architect"]["provider_preferences"] = [
    {"provider": "anthropic", "model": "claude-x"}
]
print("re-read via coordinator.config:", co.config["agents"]["architect"])
print("original caller-owned dict:    ", cfg["agents"]["architect"])
print("session.config:               ", s.config["agents"]["architect"])
```

Observed (amplifier_core 1.6.1):

```
coordinator.config is cfg?      True
agents dict identity vs cfg:    True
re-read via coordinator.config: {'model_role': ['reasoning', 'general'], 'provider_preferences': [{'provider': 'anthropic', 'model': 'claude-x'}]}
original caller-owned dict:     {'model_role': ['reasoning', 'general'], 'provider_preferences': [{'provider': 'anthropic', 'model': 'claude-x'}]}
session.config:                 {'model_role': ['reasoning', 'general'], 'provider_preferences': [{'provider': 'anthropic', 'model': 'claude-x'}]}
```

**Result: the write target is correct.** Ruled out as a cause.

---

## Probe 2 — `session:start` fires BEFORE `session:config`, and mutations carry

Claim under test: the h7n capture reads `session:config`, so `n_prefs: 0` there is only
meaningful if `session:start` has already run by then. `_session_exec.py:61-70` asserts
this ordering in prose ("the base session event ... which the Rust kernel already
emitted synchronously before calling this helper"); this executes it.

```python
# probe_event_order.py  (abridged — full flow: initialize, register, execute)
cfg = {
    "session": {"orchestrator": "loop-streaming", "context": "context-simple", "raw": True},
    "agents": {"architect": {"model_role": ["reasoning", "general"]}},
}
s = RustSession(config=cfg); await s.initialize(); co = s.coordinator

async def on_start(event, data):          # stands in for hooks-routing's handler
    for cfg_ in co.config.get("agents", {}).values():
        cfg_["provider_preferences"] = [{"provider": "anthropic", "model": "claude-x"}]
    order.append(("session:start", counts_from(co.config["agents"])))

async def on_cfg(event, data):            # what agent_prefs.py reads
    agents = ((data or {}).get("raw") or {}).get("agents") or {}
    order.append(("session:config", counts_from(agents)))

co.hooks.register("session:start",  on_start, priority=5, name="probe-start")
co.hooks.register("session:config", on_cfg,   priority=5, name="probe-config")
await s.execute("hi")                     # provider error after emission is fine
```

Observed:

```json
[["session:start",  {"architect": 1}],
 ["session:config", {"architect": 1}]]
```

**Result: `session:start` runs first, and its in-place write is visible in the
`session:config` raw payload.** So the probe's `n_prefs: 0` is a real zero — the
handler ran and resolved nothing — not a snapshot taken too early. Ruled out as a cause.

---

## Probe 3 — `coordinator.get("hooks")` really is the emit bus

Minor, but it was a live hypothesis for why no `routing:matrix-loaded` event appears in
any capture (`__init__.py:357-363` resolves the bus this way and silently skips if it
is absent).

```
mount_points keys:                ['context', 'hooks', 'module-source-resolver', 'orchestrator', 'providers', 'tools']
co.get("hooks") is co.hooks:      True (same RustHookRegistry object)
has emit?                         True
```

**Result: the emit path is fine.** The events are missing from captures for a different
reason — the recorders' `additional_events` allow-list does not contain any `routing:*`
name (see `FINDINGS.md` §6a).
