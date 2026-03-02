# Routing Matrix Bundle

Curated model routing matrices for Amplifier. Maps semantic roles (like `coding`, `reasoning`, `fast`) to ranked lists of provider/model candidates, so agents request *what kind* of model they need rather than hardcoding a specific one.

The routing hook tries candidates top-to-bottom and uses the first that matches an installed provider.

## Matrices

Seven curated matrices ship with this bundle:

| Matrix | When to use |
|--------|-------------|
| **balanced** (default) | Mixed workloads. Good quality/cost tradeoff for everyday development. |
| **quality** | Maximum capability. Uses the strongest models for every role, regardless of cost. |
| **economy** | Cost-optimized. Prefers free tiers, smaller models, and local providers like Ollama. |
| **anthropic** | Anthropic Claude models exclusively. |
| **openai** | OpenAI models exclusively. |
| **gemini** | Google Gemini models exclusively. |
| **copilot** | GitHub Copilot-optimized. Balances multiplier costs, avoids the 30x fast-variant trap. |

Browse the matrix files directly in the [`routing/`](routing/) directory.

## Including the Bundle

**Foundation already includes this bundle** — no extra configuration needed if you use Foundation.

To include it in a custom bundle:

```yaml
includes:
  - routing-matrix:behaviors/routing.yaml
```

## How Agents Use `model_role`

Agents declare what kind of model they need via the `model_role` frontmatter field. The routing hook resolves this to a concrete provider/model at session start.

**String shorthand** — request a single role:

```yaml
meta:
  name: my-agent
  description: "..."
  model_role: coding
```

**List form with fallbacks** — try roles in order:

```yaml
meta:
  name: my-agent
  description: "..."
  model_role: [vision, coding, general]
```

The system tries `vision` first. If no installed provider matches any candidate for that role, it falls back to `coding`, then `general`.

### Available Roles

| Role | Description |
|------|-------------|
| `general` | Versatile catch-all, no specialization needed |
| `fast` | Quick parsing, classification, file ops, bulk work |
| `coding` | Code generation, implementation, debugging |
| `ui-coding` | Frontend/UI code — components, layouts, styling, spatial reasoning |
| `security-audit` | Vulnerability assessment, attack surface analysis, code auditing |
| `reasoning` | Deep architectural reasoning, system design, complex multi-step analysis |
| `critique` | Analytical evaluation — finding flaws in existing work |
| `creative` | Design direction, aesthetic judgment, high-quality creative output |
| `writing` | Long-form content — documentation, marketing, case studies, storytelling |
| `research` | Deep investigation, information synthesis across multiple sources |
| `vision` | Understanding visual input — screenshots, diagrams, UI mockups |
| `image-gen` | Image generation, visual mockup creation, visual ideation |
| `critical-ops` | High-reliability operational tasks — infrastructure, orchestration |

Every matrix must define at least `general` and `fast`. All other roles are optional — agents fall back through their `model_role` list if a role isn't defined.

## Selecting a Matrix

**Via CLI command:**

```bash
amplifier routing use balanced   # or: quality, economy
amplifier routing list           # show available matrices
amplifier routing show           # show resolved roles for current matrix
```

**Via settings.yaml:**

```yaml
# ~/.amplifier/settings.yaml (global) or .amplifier/settings.yaml (project)
routing:
  matrix: quality
```

## Overriding Specific Roles

Users can override individual role assignments without replacing the entire matrix. Use the `base` keyword in `settings.yaml` to reference the active matrix and selectively replace roles:

```yaml
# ~/.amplifier/settings.yaml
routing:
  matrix: balanced
  overrides:
    coding:
      - provider: ollama
        model: codellama:70b
    fast:
      - provider: ollama
        model: llama3:8b
      - base  # fall back to the matrix's "fast" candidates after Ollama
```

With `base` in the list, the matrix's original candidates for that role are appended after your overrides. Without `base`, your override completely replaces the matrix's candidates.

## Creating a Custom Matrix

Create a YAML file following this schema:

```yaml
name: my-matrix
description: "Short description of this matrix's philosophy."
updated: "2026-02-28"

roles:
  general:                          # REQUIRED
    description: "Balanced catch-all"
    candidates:
      - provider: anthropic         # Module type name (not "provider-anthropic")
        model: claude-sonnet-4-6    # Exact model name
      - provider: ollama
        model: "*"                  # Glob: any model from this provider

  fast:                             # REQUIRED
    description: "Quick utility work"
    candidates:
      - provider: openai
        model: gpt-5-mini

  coding:                           # Optional
    description: "Code generation"
    candidates:
      - provider: anthropic
        model: claude-sonnet-4-6
        config:                     # Optional: passed to provider session config
          reasoning_effort: high
```

### Schema Reference

**Top-level fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Matrix identifier |
| `description` | Yes | Human-readable description |
| `updated` | Yes | Last update date (YYYY-MM-DD) |
| `roles` | Yes | Map of role name to role definition |

**Role definition:**

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | What this role is for |
| `candidates` | Yes | Ordered list of provider/model candidates |

**Candidate fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | Yes | Module type name (e.g., `anthropic`, `openai`, `ollama`) |
| `model` | Yes | Exact model name or glob pattern (e.g., `claude-sonnet-*`, `*`) |
| `config` | No | Model parameters passed to provider (e.g., `reasoning_effort: high`) |

Place custom matrix files in `routing/` within this bundle, or reference them from your own bundle.

See [docs/MATRIX_CURATOR_GUIDE.md](docs/MATRIX_CURATOR_GUIDE.md) for detailed authoring guidance.