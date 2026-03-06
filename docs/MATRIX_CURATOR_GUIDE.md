# Matrix Curator Guide

How to update existing routing matrices or create new ones.

---

## YAML Schema

Every matrix file has three top-level fields and a `roles` map:

```yaml
name: my-matrix
description: "Short description of the matrix's philosophy."
updated: "2026-02-28"

roles:
  general:
    description: "Balanced catch-all for unspecialized tasks"
    candidates:
      - provider: anthropic
        model: claude-sonnet-4-6
      - provider: openai
        model: gpt-5.4

  fast:
    description: "Quick parsing, classification, utility work"
    candidates:
      - provider: anthropic
        model: claude-haiku-4-5
```

### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Matrix identifier (matches the filename without `.yaml`) |
| `description` | Yes | One-line description of this matrix's design philosophy |
| `updated` | Yes | Last update date in `YYYY-MM-DD` format |
| `roles` | Yes | Map of role names to role definitions |

### Role Definition

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | What this role is for — shown in `amplifier routing show` |
| `candidates` | Yes | Ordered list of provider/model candidates (tried top-to-bottom) |

### Candidate Fields

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | Yes | Module type name (e.g., `anthropic`, `openai`, `google`, `ollama`) |
| `model` | Yes | Exact model name or glob pattern |
| `config` | No | Optional map of parameters passed to the provider session config |

---

## Provider Names

The `provider` field uses the module **type name**, not the full module identifier:

| Write this | Not this |
|------------|----------|
| `anthropic` | `provider-anthropic` |
| `openai` | `provider-openai` |
| `google` | `provider-gemini` |
| `ollama` | `provider-ollama` |
| `github-copilot` | `provider-github-copilot` |

---

## Model Names: Exact vs Globs

**Exact names** pin a specific model version:

```yaml
- provider: anthropic
  model: claude-sonnet-4-6
```

Use exact names when you want precision — the matrix won't silently shift to a newer model.

**Glob patterns** match dynamically against available models:

```yaml
- provider: ollama
  model: "*"              # any model from this provider

- provider: anthropic
  model: claude-sonnet-*  # latest Sonnet variant
```

Use globs when you want the candidate to auto-match the latest available model. The `"*"` pattern is useful for providers like Ollama where the user chooses which models to install.

---

## Required Roles

Every matrix **must** define these two roles:

- **`general`** — the catch-all fallback for agents that don't specify a model role
- **`fast`** — used by utility agents and quick classification tasks

The remaining 11 roles are optional: `coding`, `ui-coding`, `security-audit`, `reasoning`, `critique`, `creative`, `writing`, `research`, `vision`, `image-gen`, and `critical-ops`. If an agent requests a role that isn't defined, it falls back through its `model_role` list until it finds a defined role.

---

## The `config` Key

The optional `config` map is passed directly to the provider's session configuration. Use it for model-specific parameters:

```yaml
- provider: anthropic
  model: claude-opus-4-6
  config:
    reasoning_effort: high

- provider: openai
  model: gpt-5.4
  config:
    reasoning_effort: high
```

Common values:

| Key | Values | Effect |
|-----|--------|--------|
| `reasoning_effort` | `none`, `low`, `medium`, `high`, `xhigh` | Controls extended thinking / chain-of-thought depth |

Only include `config` when a candidate genuinely needs different parameters from the provider default. Most candidates don't need it.

---

## Adding a New Role

1. Add the role definition under `roles` in each matrix file that should support it:

```yaml
roles:
  # ... existing roles ...

  my-new-role:
    description: "What this role is for"
    candidates:
      - provider: anthropic
        model: claude-sonnet-4-6
      - provider: openai
        model: gpt-5.4
```

2. Update the context file (`context/routing-instructions.md`) to mention the new role so agents know it exists.

3. New roles don't need to be added to every matrix — agents using fallback chains will gracefully skip missing roles.

---

## Adding a New Matrix File

1. Create a new YAML file in the `routing/` directory (e.g., `routing/local-only.yaml`).

2. Define at least `general` and `fast` roles.

3. Set `name` to match the filename (without `.yaml`).

4. The matrix becomes available immediately via `amplifier routing list` and `amplifier routing use <name>`.

---

## Testing Your Matrix

Use the CLI to verify your matrix resolves correctly against installed providers:

```bash
# Show resolved roles for the active matrix
amplifier routing show

# Show a specific matrix
amplifier routing show quality

# List all available matrices
amplifier routing list
```

`amplifier routing show` displays each role, its resolved provider/model (based on what you have installed), and whether any roles failed to resolve.

---

## The `base` Keyword (User Overrides)

Users can override specific roles in their `settings.yaml` without editing matrix files. This is for **user configuration**, not for matrix files themselves.

```yaml
# In ~/.amplifier/settings.yaml
routing:
  matrix: balanced
  overrides:
    coding:
      - provider: ollama
        model: codellama:70b
      - base  # append the matrix's original candidates after this
```

The `base` keyword tells the routing hook to insert the matrix's candidates for that role at that position. Without `base`, the override completely replaces the matrix's candidates.

**Do not use `base` in matrix files** — it only has meaning in user override configuration.

---

## Complete Role Taxonomy (13 Roles)

The routing system defines 13 roles organized into 5 categories. For full descriptions, fallback chain examples, and decision flowcharts, see `context/role-definitions.md`.

| # | Role | Category | Model Tier | Reasoning | Description |
|---|------|----------|------------|-----------|-------------|
| 1 | `general` | Foundation | Mid (Sonnet, gpt-5.4) | default | Versatile catch-all, no specialization needed |
| 2 | `fast` | Foundation | Cheap (Haiku, gpt-5-mini) | default | Quick utility tasks — parsing, classification, file ops |
| 3 | `coding` | Coding | Mid, code-specialized | default | Code generation, implementation, debugging |
| 4 | `ui-coding` | Coding | Mid, code-specialized | default | Frontend/UI code — components, layouts, styling |
| 5 | `security-audit` | Coding | Mid, code-specialized | high | Vulnerability assessment, attack surface analysis |
| 6 | `reasoning` | Cognitive | Heavy (Opus, gpt-5.4) | high | Deep architectural reasoning, system design |
| 7 | `critique` | Cognitive | Mid | extra-high | Analytical evaluation — finding flaws in existing work |
| 8 | `creative` | Cognitive | Heavy (Opus, gpt-5.4) | default | Design direction, aesthetic judgment |
| 9 | `writing` | Cognitive | Heavy (Opus, gpt-5.4) | default | Long-form content — docs, marketing, case studies |
| 10 | `research` | Cognitive | Heavy (Opus, gpt-5.4-pro) | high | Deep investigation, information synthesis |
| 11 | `vision` | Capability | Mid, multimodal | default | Understanding visual input — screenshots, diagrams |
| 12 | `image-gen` | Capability | Specialized | default | Image generation, visual mockup creation |
| 13 | `critical-ops` | Operational | Heavy (Opus, gpt-5.4) | default | High-reliability operational tasks — infrastructure, orchestration |

---

## Sourcing Methodology

Model selection is informed by three complementary data sources, combined with human curation.

### Artificial Analysis Benchmarks

[Artificial Analysis](https://artificialanalysis.ai/) provides standardized benchmarks across providers. Use their leaderboard to compare:

- **Quality scores** (MMLU, HumanEval, GPQA) for capability assessment
- **Speed** (tokens/second) for latency-sensitive roles like `fast`
- **Cost** (per million tokens) for budget-conscious matrix variants
- **Context window** sizes for roles like `research` that benefit from long context

### StrongDM Weather Report Alignment

The StrongDM Weather Report categorizes AI model capabilities into 14 areas. The following table maps those categories to our 13 roles:

| Weather Report Category | Our Role | Notes |
|------------------------|----------|-------|
| General Knowledge | `general` | Broad factual and reasoning tasks |
| Coding | `coding` | Code generation and debugging |
| Frontend Development | `ui-coding` | Components, layouts, CSS |
| Security Analysis | `security-audit` | Vulnerability scanning, code auditing |
| System Design | `reasoning` | Architecture, multi-step planning |
| Code Review | `critique` | Evaluating existing work for flaws |
| Creative Writing | `creative` | Aesthetic direction, brand voice |
| Technical Writing | `writing` | Documentation, long-form content |
| Research & Analysis | `research` | Investigation and synthesis |
| Image Understanding | `vision` | Screenshot and diagram analysis |
| Image Generation | `image-gen` | Visual content creation |
| DevOps & Infrastructure | `critical-ops` | Deployment, orchestration |
| Quick Tasks & Classification | `fast` | Parsing, triage, bulk processing |
| Mathematical Reasoning | `reasoning` | Maps to reasoning for deep analysis |

### Curated Selection

After reviewing benchmark data and weather report alignment, follow this 3-step process:

1. **Shortlist candidates** — For each role, identify the top 2-3 models per provider based on benchmark rankings for that role's task type.
2. **Hands-on evaluation** — Test shortlisted models against representative prompts from real agent workflows. Benchmarks measure general capability; curation tests task-specific fit.
3. **Rank and commit** — Order candidates by preference (best first) in the matrix YAML. The routing hook tries candidates top-to-bottom.

---

## Curation Principles

### Pin Model Names

Always use exact, versioned model names in matrix files. Globs are for user overrides and local providers only.

**Good** — pinned to a specific version:
```yaml
- provider: anthropic
  model: claude-sonnet-4-6
```

**Bad** — will silently shift when provider updates:
```yaml
- provider: anthropic
  model: claude-sonnet-*
```

The only exception is `model: "*"` for providers like Ollama where users choose their own models.

### Provider-Specific Naming

Different providers use different naming conventions for the **same underlying model**. Always use the provider's native format.

| Model | anthropic | openai | google | github-copilot |
|-------|-----------|--------|--------|----------------|
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | — | — | `claude-sonnet-4.6` |
| Claude Opus 4.6 | `claude-opus-4-6` | — | — | `claude-opus-4.6` |
| Claude Haiku 4.5 | `claude-haiku-4-5` | — | — | `claude-haiku-4.5` |
| GPT-5.2 | — | `gpt-5.2` | — | `gpt-5.2` |
| GPT-5.3 Codex | — | `gpt-5.3-codex` | — | `gpt-5.3-codex` |
| GPT-5.4 | — | `gpt-5.4` | — | `gpt-5.4` |
| GPT-5.4 Pro | — | `gpt-5.4-pro` | — | `gpt-5.4-pro` |

> **CRITICAL:** Anthropic uses **hyphens** (`claude-sonnet-4-6`) while GitHub Copilot uses **dots** (`claude-sonnet-4.6`). Mixing these up causes silent resolution failures — the candidate won't match any installed model.

### Model Blacklist

The following models must **never** appear in any matrix file:

| Model | Reason |
|-------|--------|
| `gpt-4.1` | Deprecated; replaced by gpt-5.x family |
| `claude-opus-4.6-fast` | Not a real model; confused with claude-opus-4-6 |
| `claude-opus-4-6-fast` | Not a real model; no "fast" variant of Opus exists |

If a blacklisted model appears in a PR, reject and request replacement with a valid alternative.

### Required Roles

Every matrix **must** define `general` and `fast`. All 13 roles should be present in multi-provider matrices (`balanced.yaml`, `quality.yaml`, `economy.yaml`). Single-provider matrices may omit roles that the provider cannot fill.

### balanced.yaml as Reference

The `balanced.yaml` matrix is the canonical reference for model selection. When creating or updating other matrices:

- Use `balanced.yaml` as the starting template
- Verify your matrix covers at least the same roles
- Deviate from `balanced.yaml` only where the matrix philosophy demands it (e.g., `economy.yaml` trades quality for cost)

---

## Deriving Per-Provider Matrices

Single-provider matrices (e.g., `anthropic.yaml`, `openai.yaml`) are derived from `balanced.yaml` using this 5-step process:

1. **Start from balanced.yaml** — Copy the full role structure as your starting point.
2. **Filter to one provider** — For each role, keep only candidates from the target provider. Remove all other provider entries.
3. **Fill gaps with provider equivalents** — If a role has no candidates after filtering, find the provider's closest equivalent model and add it.
4. **Add glob fallback** — For roles where the provider may introduce new models, consider adding a glob fallback as the last candidate (e.g., `claude-sonnet-*`).
5. **Validate with tests** — Run `python -m pytest tests/` to ensure the matrix passes all structural validation.

---

## When to Refresh

Matrix refreshes are triggered when any of the following occur:

- A major model release from any provider (e.g., new Claude or GPT version)
- A model deprecation or retirement announcement
- Significant benchmark score changes on Artificial Analysis
- A new Weather Report edition from StrongDM
- User-reported resolution failures or quality regressions
- Quarterly scheduled review (even if no triggers)

Follow this 6-step refresh process:

1. **Review triggers** — Identify what changed and which roles are affected.
2. **Benchmark check** — Compare the new model against current candidates on Artificial Analysis.
3. **Update balanced.yaml first** — Make changes in the canonical reference matrix.
4. **Propagate to derived matrices** — Update `quality.yaml`, `economy.yaml`, and single-provider matrices following their respective philosophies.
5. **Run the full test suite** — Execute `python -m pytest tests/` across all test files.
6. **Update the `updated` date** — Set the `updated` field in every modified matrix to today's date.

---

## Checklist for Matrix Updates

- [ ] `general` and `fast` roles are defined
- [ ] `updated` field reflects today's date
- [ ] `provider` uses module type names (not full module identifiers)
- [ ] Candidates are ordered by preference (best first)
- [ ] `config` is only present where needed
- [ ] No blacklisted models (`gpt-4.1`, `claude-opus-4.6-fast`, `claude-opus-4-6-fast`)
- [ ] No duplicate candidates within the same role
- [ ] Provider-specific naming correct (anthropic hyphens, copilot dots)
- [ ] Tests pass: `python -m pytest tests/`
- [ ] Verified with `amplifier routing show`