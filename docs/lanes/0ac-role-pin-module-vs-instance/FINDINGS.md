# recipes-0ac — role_pin re-pinned by SPELLING, not by module

**Lane:** `fix/role-pin-module-vs-instance`
**File:** `modules/hooks-routing/amplifier_module_hooks_routing/role_pin.py`
**Measured:** 2026-09-02, 14-provider host
**Base:** `452560b`

## The defect

A session's `provider_preferences` names its provider by **module** —
`anthropic`, `openai`, `gemini` — because that is what the routing matrix
writes and the spawner copies verbatim. A host mounts **instances**, each keyed
by its own `id:`.

`_match_mounted` compared the preference string against mounted provider KEYS
by spelling (`_name_variants`: the id, the id minus `provider-`, the id plus
`provider-`). Nothing in that comparison knows what module an instance is. Two
failure modes fell out of it:

1. A module with several instances, none of them *named* after the module,
   matched no key at all — the preference was skipped and the walk moved on to
   the NEXT, worse preference. (Where two keys did answer to one spelling,
   `_match_mounted` returned the candidate list and the caller abandoned the
   whole pin as `pinned_provider_ambiguous`, on the grounds that upstream's own
   two helpers disagreed on which instance wins. That gap is now closed
   upstream — see the cross-reference below.)
2. An instance *named* like a module matched that module's preference by
   spelling alone, whatever module it actually was.

## Evidence

Child session `...a0a049acf77d43c7`
(`~/.amplifier/projects/-home-bkrabach-dev-recipe-bundles-team-ci/sessions/*a0a049acf77d43c7*/events.jsonl`),
a `reasoning`-role agent:

```
session:fork     opus   priority 0                    <- spawner promoted the right instance
session:config   gemini priority 0, opus demoted 1    <- this module overrode it
```

Session `provider_preferences`, in order:

```
[{anthropic, claude-opus-*}, {openai, ...}, {gemini, gemini-3-pro-*}]
```

Host mount plan (trimmed to the instances the chain can reach):

| key      | module                     | priority | default_model                    |
| -------- | -------------------------- | -------- | -------------------------------- |
| `opus`   | `provider-anthropic`       | 1        | `claude-opus-5`                  |
| `sonnet` | `provider-anthropic`       | 5        | `claude-sonnet-5`                |
| `fable`  | `provider-anthropic`       | 6        | `claude-sonnet-4-5`              |
| `gemini` | `provider-gemini`          | 7        | `gemini-3.1-flash-image-preview` |
| `sol`    | `provider-openai-*`        | 2        | `gpt-5.6-sol`                    |
| `terra`  | `provider-openai-*`        | 3        | `gpt-5.6-terra`                  |

* `anthropic` — three instances of that module mounted, none named it → no
  match → preference 1 skipped.
* `openai` — same shape → preference 2 skipped.
* `gemini` — matched a key literally, purely because one instance happened to
  be named after a module → **won**, on the third preference.
* its `model` (`gemini-3-pro-*`) was an unresolved glob, so the pin correctly
  refused to write a literal glob as a model name — leaving that instance's own
  `default_model`, `gemini-3.1-flash-image-preview`.

A reasoning agent was pinned to a 65K-token **image** model and returned 400s.

## The rule now

Resolution happens in three passes, and the ORDER is the fix:

1. **`wanted` names a MODULE** → every mounted instance of that module is a
   candidate; resolve to the one whose `default_model` matches the
   preference's `model` (fnmatch, case-insensitive, dated-snapshot tolerant),
   else the highest-priority instance (lowest priority number), ties broken on
   key name. Never skipped, never abandoned as ambiguous. Running this pass
   FIRST is what module-checks a literal key match: an instance merely *named*
   `gemini` cannot satisfy `provider: gemini` while a real `provider-gemini`
   instance is mounted.
2. **`wanted` is a key** → instance-id mode, unchanged. Pass 1 defers to this
   reading when `wanted` is both a module and a key of that same module and no
   instance serves the pinned model: an exact key beats a priority tie-break.
   Model intent outranks both.
3. **`wanted` is a spelling variant of one or more keys** → resolved by pass
   1's rule instead of refused.

Priority for the tie-break is read from the MOUNT PLAN
(`coordinator.config["providers"]`) before the live objects, because the live
priorities are precisely the drift this module exists to repair. `model` is now
threaded into the matcher — it is half the rule, and the matcher previously
never saw it.

The emitted `routing:role-pin-reasserted` record gained
`pinned_provider_declared`, `provider_resolution` and (when more than one
instance answered) `resolution_candidates`, so the choice is readable from the
event rather than inferred.

Unchanged: protected config keys, the `_apply_single_override` mirror
(promote to 0, demote ties to 1, restore `default_model` and non-protected
preference config), never fighting the orchestrator, and running on
`session:resume` as well as `session:start`. A coordinator that exposes no
mount plan degrades to exactly the pre-existing spelling behaviour.

### Residual, named rather than hidden

Pass 2 cannot verify a module claim for a name no mounted instance implements.
An instance keyed `gemini` whose module is `provider-anthropic`, on a host with
NO gemini module mounted, still matches `provider: gemini` — there is no
registry at this layer that could call `"gemini"` a module name in the
abstract, and refusing would break the ordinary instance-id pin. The measured
failure requires a real instance of the named module to exist; pass 1 owns that
case.

## Cross-reference

The same rule is now stated in three layers, deliberately identically:

* here (`role_pin._pick_instance`) — re-asserting a session's own pin;
* `resolver.find_provider_by_type` — the routing matrix's own bare-type
  fallback, landed in #60;
* `amplifier_foundation.spawn_utils._find_provider_instance` — the spawn layer
  (sibling PR). That is the fix that closes the "upstream helpers disagree"
  gap this module used to cite as its reason for refusing to resolve.

If the three ever disagree, a child is pinned at spawn to one instance and
re-pinned at `session:start` to another — which is the failure above.

## Tests

`modules/hooks-routing/tests/test_role_pin_module_vs_instance.py` (new, 11
tests) replays the measured host shape; `test_role_pin_fidelity.py`'s two
ambiguity tests are superseded in place (they asserted the refusal that is the
bug).

* `evidence/fail-before.txt` — 12 failed at `452560b` with the new tests
  applied, including the capture replayed verbatim (pre-fix record pins
  `gemini`, `model_not_reasserted_reason: model_is_unresolved_pattern`). The
  single passing GATE-adjacent case is the legitimate collision control
  (instance `gemini` really IS `provider-gemini`), which must not change.
* `evidence/suite-after.txt` — 574 passed (module suite), 39 passed
  (repo-root suite).
