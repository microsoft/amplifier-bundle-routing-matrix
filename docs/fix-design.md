# Fix Design: Routing Matrix Provider Override

**Issue:** [kenotron-ms/amplifier-actions-example#89](https://github.com/kenotron-ms/amplifier-actions-example/issues/89)

## Root Cause

Two confirmed root causes:

1. **Silent Priority Override**: The `routing: matrix: copilot` setting in `~/.amplifier/settings.yaml` takes unconditional precedence over per-provider `priority:` fields. The routing matrix resolves the provider for sub-agents before the priority system is consulted, so user-configured priorities (e.g., `priority: 1` for Anthropic) are silently ignored.

2. **Futile Retry Logic**: The retry loop in the AI model request path does not classify errors before retrying. A `400 prompt is too long` (payload-too-large) error is structurally non-transient and will never succeed on retry, yet the code retries it 5 times anyway, wasting ~6 seconds.

## Files to Change

| Repository | Component | Reason |
|-----------|-----------|---------|
| `amplifier-bundle-routing-matrix` | Matrix provider selection logic | Emit warning when matrix overrides priority-1 provider; optionally fall back to priority-ranked provider |
| `amplifier-core` | Retry loop in AI model request path | Add error classifier to skip retries for HTTP 400 "prompt is too long" errors |

## Suggested Fix

### 1. amplifier-bundle-routing-matrix

**What**: Add conflict detection between matrix setting and provider priorities.

**How**:
- When matrix is configured (e.g., `matrix: copilot`), check if any provider has `priority: 1` set
- If conflict detected:
  - Emit a warning to the user explaining the matrix is overriding their priority config
  - Optionally: fall back to the priority-ranked provider when matrix provider is unavailable or fails
  - Document the precedence relationship between matrix and priority settings

**Example warning**:
```
⚠️  Routing matrix 'copilot' is overriding your priority-1 provider 'anthropic'.
    To use priority-based routing, remove 'routing: matrix:' from settings.yaml
    or set 'matrix: balanced' to honor provider priorities.
```

### 2. amplifier-core

**What**: Add error classification to skip retries on non-transient errors.

**How**:
- Before retry loop, classify the error type
- For HTTP 400 errors where response body matches `prompt is too long` or payload-size patterns:
  - Short-circuit the retry loop immediately
  - Surface the error with context about context size limits
- Keep retries for genuinely transient errors (network timeouts, 5xx errors, etc.)

**Benefits**:
- Saves ~6 seconds of futile retry waiting
- Provides clearer error messaging about context size issues
- Applies to all providers using the shared retry logic (Anthropic, OpenAI, Gemini, Azure OpenAI, Copilot)

## Expected Outcome

1. Users will be informed when their routing matrix conflicts with provider priorities
2. No more silent overrides of user intent
3. Faster failures on non-transient errors
4. Clearer precedence relationship between routing matrix and provider priorities
