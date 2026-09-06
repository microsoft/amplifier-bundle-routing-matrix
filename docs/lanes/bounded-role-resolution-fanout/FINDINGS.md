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

## Verified in product (A-B-A′, one disposable container)

The report's own probe (`probe-min.yaml`, one agent step, one token, run
through `amplifier tool invoke recipes ... -b recipes` with
`PYTHONFAULTHANDLER=1`), aborts counted by exit code 134/139. Only the three
`hooks-routing` module files changed between arms; **`truststore` 0.10.4 was
stock and untouched throughout** (its `_api.py` still carries exactly one
`with self._ctx_lock`, the one in `wrap_socket`).

| arm | hooks-routing | attempts | aborts |
|---|---|---|---|
| A | stock (`main`) | 10 concurrent + 6 sequential = 16 | **4** |
| B | this branch | 20 concurrent + 6 sequential = 26 | **0** |
| A′ | reverted to stock | 10 concurrent + 6 sequential = 16 | **7** |

Stock combined: **11 aborts in 32**. Patched: **0 in 26**. The failure returns
immediately on revert.

Every stock abort carried the documented signature: 21–36 threads inside
`truststore/_openssl.py:38 _configure_context`, **100% via `wrap_bio`, 0% via
`wrap_socket`**; 65 threads alive at the abort in the captured dump. Both
outcomes appeared (`double free or corruption (fasttop)` → exit 134, and
`Segmentation fault` → exit 139), confirming they are the same bug.

Environment: Ubuntu 24.04.4 aarch64, kernel 6.17.0-1029-nvidia, Python 3.12,
**OpenSSL 3.0.13**, `truststore` 0.10.4, amplifier CLI 2026.09.06-9fd6ad5
(core 1.6.1) — i.e. the report's environment.

That the patched code is what actually ran (rather than merely what sat on
disk) is pinned by bytecode: `__pycache__` was removed before arm B and
regenerated during it, and the resulting `.pyc` files contain the new
`max_concurrent_role_resolutions` and `inflight_model_lists` symbols.

## Evidence

- `evidence/probe-abort-aba.txt` — the full A-B-A′ probe output, environment
  banner, per-run exit codes and faulthandler signatures.
- `evidence/profile.yaml`, `evidence/run-probe.sh`, `evidence/summarize.sh`,
  `evidence/probe-min.yaml` — the probe harness, so the run is repeatable.
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
- Closing the race. 0 aborts in 26 is the measured result at this sample size
  on this host, not a proof of impossibility: other concurrent HTTP in the
  process can still reach an unlocked `wrap_bio`. What is established is that
  removing this fan-out removes the observed failure, and that restoring the
  fan-out brings it straight back.
