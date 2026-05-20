# Investigation Principles for Issue Triage

This file is loaded by the `investigate` node at the start of every triage run.
Follow these principles — the `quality_eval` gate checks all of them.

---

## The 6 Quality Criteria quality_eval Will Check You On

Your output MUST demonstrate all six or you will be retried:

1. **PROXY CHECK** — Did you verify the code independently, or just restate the issue reporter's description?
   The reporter can be wrong. Verify every claim against actual source code before repeating it.

2. **SPECIFICITY** — Is your root cause a specific `file:line`?
   "Probably in this function" is not a root cause. Read the file and give the exact line.

3. **LAYER CHECK** — Is your fix at the correct ecosystem layer?
   Hierarchy (innermost → outermost): `amplifier-core` → `amplifier-module-*` → `amplifier-foundation` → `amplifier-bundle-*` → `amplifier-app-cli`
   If the same bug exists in 4 providers, fixing one provider is the wrong layer.
   Ask: **who does this fix NOT protect?**

4. **DIMENSIONALITY** — Did you check sibling modules?
   If the issue is in `provider-anthropic`, check `provider-openai`, `provider-gemini`, `provider-azure-openai`, `provider-vllm`, `provider-ollama`, `provider-github-copilot`.
   Use `github_checkout_repo` with `owner='microsoft'` for each.

5. **RECOMMENDATION** — One concrete recommendation, not a menu of options.
   "The team should consider X or Y" is not a recommendation.

6. **STRUCTURE** — Lead with the 2–3 sentence conclusion. Evidence comes after.
   Write your conclusion FIRST, then support it. Never end mid-sentence.

---

## How to Investigate (ISSUE_HANDLING.md Principles)

### Step 1: Reconnaissance — understand what's ACTUALLY broken

**Never assume the reporter's description is accurate.**

Common failure mode: reporter says "exception is unhandled" → you check the exception class →
you never look at the CALLER to see if the caller already has a try/except.

Always verify: does the calling code already handle the exception?
In `resolver.py` / routing hooks: check every `try/except` block around the relevant call.

### Step 2: Root Cause — exact file:line, not "probably in this area"

Trace the actual call chain:
- What calls what?
- Where does the exception originate?
- Does it propagate, or is it caught somewhere in the chain?

### Step 3: Sibling check — who ELSE has this gap?

Use `MODULES.md` to identify all sibling modules of the same type.
For provider issues: check ALL providers in `amplifier-module-provider-*`.
Find which ones have the same gap. Find which ones don't — understand why.

### Step 4: Layer decision — where should the fix live?

Brian's principle: **right repo, right layer**.
- Bug in one provider AND all others → fix in `amplifier-core` (or the resolver) — single fix, all protected
- Bug in one provider only → fix in that provider
- Policy decision → bundle level, not core

---

## Common Investigation Pitfalls

### Pitfall 1: Reporting exceptions as "unhandled" without checking the call chain

Before writing "the exception propagates uncaught", trace upward:
1. Does the immediate caller have a try/except?
2. Does the resolver/router have a try/except?
3. Is there a test that explicitly verifies graceful fallback?

In the Amplifier routing matrix: `_resolve_glob()` in `resolver.py` typically wraps
`provider.list_models()` in a broad `except Exception` block. If you find this,
the real question becomes: **is the catch-all sufficient, or does retry logic belong inside the provider?**

### Pitfall 2: Running out of time before writing conclusions

**Write your conclusion FIRST** using the required template below.
Do your investigation, then immediately write the conclusion before going into evidence detail.
If you run out of time, quality_eval sees a complete report, not a truncated one.

---

## Required Output Structure

Start your response with this block filled in (BEFORE any analysis detail):

```
## Summary

**Root cause:** [file:line — one sentence, specific, no hedging]
**Ecosystem layer affected:** [which repo/module — e.g. amplifier-module-provider-anthropic]
**Sibling modules with same issue:** [list each, or "None found"]
**Recommended fix:** [one concrete recommendation]
**Fix layer:** [where the fix should live — e.g. amplifier-module-provider-anthropic, or amplifier-core]
```

Then provide supporting evidence (code excerpts, file:line references, test names).

---

## Ecosystem Layer Reference

```
amplifier-core (kernel — mechanism only)
  └─ amplifier-module-provider-* (anthropic, openai, gemini, azure-openai, vllm, ollama, github-copilot)
  └─ amplifier-module-tool-* (filesystem, bash, web, search...)
  └─ amplifier-module-hooks-* (routing, logging, streaming-ui...)
  └─ amplifier-module-context-* (simple, persistent...)
  └─ amplifier-module-orchestrator-* (loop-basic, loop-streaming...)
  └─ amplifier-foundation (library — bundles, shared utilities)
      └─ amplifier-bundle-* (routing-matrix, attractor, recipes...)
          └─ amplifier-app-cli (application)
```
