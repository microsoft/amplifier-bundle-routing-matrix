# Bounded role-resolution fan-out + `list_models()` de-duplication

## What was wrong

`on_session_start` resolved every agent's `model_role` in one unbounded
`asyncio.gather` (`hooks-routing/__init__.py`, the
`await asyncio.gather(*(_resolve_one(cfg) for cfg in agents.values()))` line),
and every glob candidate issued its own `list_models()` HTTPS request
(`resolver.py:_resolve_glob`).

On the measured 41-agent `-b recipes` bundle that is up to 41 simultaneous TLS
handshakes — and it runs on **every** session mount: the CLI's own and every
spawned agent's, so a recipe that spawns agents re-enters it once per step.

The `preresolved_models` cache that already existed cannot help here. It is
only consulted *after* a fetch has returned, and every member of a concurrent
burst reads it before any of them has. It de-duplicates sequential callers,
never simultaneous ones.

## Why it matters beyond traffic

That burst is the documented trigger for a native abort. `truststore` 0.10.4's
`wrap_bio` calls `_configure_context` **without** taking `self._ctx_lock` —
its own `wrap_socket` does take it (`_api.py:113-119`) — so 20–37 threads at a
time ran `ctx.set_default_verify_paths()` on one shared `ssl.SSLContext` and
glibc aborted the process: `double free or corruption`, exit 134 (sometimes
SIGSEGV, exit 139), with no Python traceback, no error result and no partial
output. Every captured abort had the same shape: **100% via `wrap_bio`, 0% via
`wrap_socket`.**

The missing lock is the *defect* and belongs upstream. The unbounded fan-out is
what converts a latent race into a routine crash, and it is fixable here,
independently of which `truststore` version is installed.

## The change

Two independent reductions of the same burst; they compose.

1. **`asyncio.Semaphore` around `_resolve_one`'s resolution call.** Default 4,
   overridable via this hook's own mount config
   (`max_concurrent_role_resolutions`), validated loudly at mount time like
   `placement` already is. Every agent is still resolved — only the arrival
   rate is capped.

2. **Single-flight `list_models()` per provider** (`resolver._fetch_model_names`).
   The first caller for a provider key records an `asyncio.Future`; callers
   arriving while it is in flight await that same future instead of opening
   their own connection. Failures are shared too (so a failing provider also
   costs one request per burst), but each caller still handles and logs its own
   failure, so warning output is unchanged. The slot is released once the fetch
   settles, so a later call may retry exactly as it could before.

Passing no `inflight_model_lists` (the default) restores the previous call
pattern byte for byte. Resolution results are unchanged in every case.

## Measured

Mount-time `list_models()` calls, 41 agents, all resolving globs against one
provider (`tests/test_bounded_fanout.py::TestMountTimeHttpCallCount`):

| | concurrent `list_models()` calls | peak in flight |
|---|---|---|
| before | 41 | 41 |
| semaphore only | 4 | 4 |
| semaphore + coalescing (shipped) | **1** | **1** |

Peak in-flight resolutions, 20 agents across 20 distinct providers (isolates
the semaphore — distinct providers cannot be coalesced):

| config | peak |
|---|---|
| before (unbounded) | 20 |
| default (`4`) | ≤ 4 |
| `max_concurrent_role_resolutions: 1` | 1 |
| `max_concurrent_role_resolutions: 8` | ≤ 8, > 4 |

## Evidence

- `evidence/fail-before.txt` — the new tests against stock `HEAD~1` code:
  13 failed, headline `41-agent mount issued 41 list_models() calls; expected 1`
  and `peak in-flight list_models() was 20, expected <= 4`.
- `evidence/suite-after.txt` — full suites after the change: 590 passed
  (module), 39 passed (repo root).

Each bounded assertion is paired with an anti-vacuity guard that raises the
ceiling and observes the concurrency the harness is actually capable of
producing (20-way), so a bound test cannot pass because the harness never
produced concurrency in the first place.

## Not addressed here

- The missing lock in `truststore.SSLContext.wrap_bio`. That is the defect;
  this is the trigger.
- Whether bounding the fan-out **alone** eliminates the abort in practice.
  Other concurrent HTTP in the process can still race an unlocked `wrap_bio`.
  This lane reduces the exposure at its largest single source; it does not
  claim to close the race.
