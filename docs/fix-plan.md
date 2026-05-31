# Fix Implementation Plan

**Issue:** [kenotron-ms/amplifier-actions-example#89](https://github.com/kenotron-ms/amplifier-actions-example/issues/89)

## FILES TO CHANGE

### 1. amplifier-bundle-routing-matrix

**Target File:** Provider selection logic (likely `modules/*/routing_matrix.py` or `src/routing_matrix.py`)

**Changes:**
- Locate the function that resolves provider from matrix setting (searches for `config.get('default_matrix', 'balanced')`)
- Before returning matrix-selected provider:
  - Check all configured providers for `priority: 1`
  - If found and differs from matrix provider:
    - Emit warning via logging or stderr: `⚠️  Routing matrix '{matrix}' is overriding your priority-1 provider '{priority_provider}'.`
    - Suggest: `To use priority-based routing, remove 'routing: matrix:' from settings.yaml or set 'matrix: balanced'.`
- Add docstring clarifying matrix precedence over priorities

**Line-level approach:**
```python
# In provider resolution function
matrix_provider = config.get('default_matrix', 'balanced')

# ADD: Conflict detection
priority_one_provider = _find_priority_one_provider(config)
if priority_one_provider and priority_one_provider != matrix_provider:
    logger.warning(
        f"⚠️  Routing matrix '{matrix_provider}' is overriding "
        f"your priority-1 provider '{priority_one_provider}'.\n"
        f"    To use priority-based routing, remove 'routing: matrix:' "
        f"from settings.yaml or set 'matrix: balanced'."
    )

return matrix_provider
```

### 2. amplifier-core

**Target File:** Retry loop for AI model requests (likely `amplifier_core/session.py` or `amplifier_core/provider.py`)

**Changes:**
- Locate retry loop (searches for `retry` or `Failed to get response from the AI model; retried`)
- Add error classifier function before retry loop:
  ```python
  def _is_non_transient_error(error):
      """Check if error should skip retries."""
      if hasattr(error, 'status_code') and error.status_code == 400:
          error_msg = str(error).lower()
          if 'prompt is too long' in error_msg or 'tokens >' in error_msg:
              return True
      return False
  ```
- In retry loop, check before retry:
  ```python
  except Exception as e:
      if _is_non_transient_error(e):
          logger.error(f"Non-transient error (won't retry): {e}")
          raise  # Skip retry loop
      # existing retry logic
  ```

**Line-level approach:**
- Find: `for attempt in range(max_retries):`
- Add: Error classification check after exception catch
- Short-circuit: `raise` immediately for non-transient errors

---

## TESTS

### amplifier-bundle-routing-matrix

**New test:** `test_matrix_priority_conflict_warning`
- Setup: Mock config with `matrix: copilot` and Anthropic `priority: 1`
- Execute: Call provider resolution function
- Assert: Warning logged containing "overriding your priority-1 provider"

**New test:** `test_no_warning_when_matrix_matches_priority`
- Setup: Mock config with `matrix: anthropic` and Anthropic `priority: 1`
- Execute: Call provider resolution function
- Assert: No warning logged

### amplifier-core

**New test:** `test_no_retry_on_prompt_too_long`
- Setup: Mock provider that raises 400 "prompt is too long: 214679 tokens > 200000 maximum"
- Execute: Call AI model request function
- Assert: Function fails immediately without retries (0 retry attempts)

**New test:** `test_retry_on_transient_errors`
- Setup: Mock provider that raises 503 (service unavailable)
- Execute: Call AI model request function
- Assert: Retries occur as expected (5 attempts)

**Modified test:** Update existing retry tests to include non-transient error paths

---

## VERIFICATION

### Manual verification steps:

1. **Priority override warning:**
   ```bash
   # Set up ~/.amplifier/settings.yaml with:
   # routing:
   #   matrix: copilot
   # providers:
   #   anthropic:
   #     priority: 1
   
   amplifier run "test task"
   # Expected: Warning printed at startup about matrix override
   ```

2. **No retry on payload-too-large:**
   ```bash
   # Trigger a long session that exceeds Copilot's 200k limit
   # (or mock the error in tests)
   
   # Expected: 
   # - Immediate failure (no 6-second retry wait)
   # - Error message: "Non-transient error (won't retry): prompt is too long"
   ```

3. **Retries still work for transient errors:**
   ```bash
   # Simulate network timeout or 5xx error
   # Expected: Normal retry behavior (5 attempts with backoff)
   ```

### Automated verification:

```bash
# Run new tests
pytest tests/test_routing_matrix.py::test_matrix_priority_conflict_warning -v
pytest tests/test_routing_matrix.py::test_no_warning_when_matrix_matches_priority -v
pytest tests/test_core_retry.py::test_no_retry_on_prompt_too_long -v
pytest tests/test_core_retry.py::test_retry_on_transient_errors -v

# Run full test suite to ensure no regressions
pytest tests/ -v
```

### Success criteria:

- ✅ Warning emitted when matrix conflicts with priority-1 provider
- ✅ No warning when matrix matches priority provider
- ✅ Prompt-too-long errors fail immediately (0 retries)
- ✅ Transient errors still retry as before
- ✅ All existing tests pass
