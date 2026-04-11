---
name: role-definitions
description: 'Detailed model routing role definitions, decision flowchart, model tier grid, and fallback chain best practices. Load when authoring agents or debugging model routing.'
version: 1.0.0
---

# Model Routing Role Definitions

Reference for choosing the right `model_role` when writing agent frontmatter or delegating to sub-agents. There are 13 roles organized into 5 categories.

## Quick Decision Flowchart

```
What does your agent primarily DO?
│
├─ Writes code?
│   ├─ Frontend/UI code (components, layouts, CSS)? → ui-coding
│   ├─ Security vulnerability scanning? → security-audit
│   └─ General code (backend, IaC, tests, debugging)? → coding
│
├─ Thinks deeply / designs systems?
│   ├─ Designing architecture or solving complex problems? → reasoning
│   ├─ Reviewing/critiquing existing work for flaws? → critique
│   └─ Investigating and synthesizing from multiple sources? → research
│
├─ Creates content?
│   ├─ Aesthetic/design direction (visual, brand, style)? → creative
│   └─ Long-form writing (docs, marketing, case studies)? → writing
│
├─ Works with images?
│   ├─ Needs to understand/analyze images? → vision
│   └─ Needs to generate images? → image-gen
│
├─ Orchestrates high-stakes operations?
│   └─ Infrastructure, deployments, shadow environments? → critical-ops
│
├─ Quick utility task (parsing, classification, file ops)?
│   └─ → fast
│
└─ None of the above / genuinely varied work?
    └─ → general
```

## Role-by-Role Reference

### Foundation Roles

These two roles are required in every matrix and serve as universal fallbacks.

#### `general`
- **Description:** Versatile catch-all, no specialization needed
- **Model tier:** Mid (Sonnet, gpt-5.4, Gemini Pro)
- **When to use:** The agent's work is genuinely varied — knowledge experts, ecosystem consultants, integration specialists
- **When NOT to use:** If you can name what the agent primarily does (codes, designs, reviews), use that role instead
- **Example agents:** explorer, foundation-expert, amplifier-expert, core-expert
- **Example chains:** `general` (terminal — no fallback needed)

#### `fast`
- **Description:** Quick utility tasks — parsing, classification, file ops, bulk work
- **Model tier:** Cheap (Haiku, gpt-5-mini, Gemini Flash)
- **When to use:** Well-defined, low-ambiguity, high-volume, or latency-sensitive tasks — file operations, git commands, notification triage, data extraction
- **When NOT to use:** If the agent needs judgment calls, synthesis, or quality prose
- **Example agents:** file-ops, git-ops, shell-exec, health-checker, triage-manager
- **Example chains:** `fast` (terminal — fast agents rarely need fallback)

---

### Coding Domain Roles

For agents whose primary output is code.

#### `coding`
- **Description:** Code generation, implementation, debugging
- **Model tier:** Mid, code-specialized (Sonnet, gpt-5.4, Gemini Pro)
- **When to use:** The agent writes, modifies, or debugs code as its primary activity — bug fixing, feature implementation, test writing, infrastructure-as-code
- **When NOT to use:** If the agent primarily reviews code (use `critique`), designs UI layouts (use `ui-coding`), or audits for vulnerabilities (use `security-audit`)
- **Example agents:** bug-hunter, modular-builder, test-coverage, python-dev, rust-dev
- **Example chains:** `[coding, general]`

#### `ui-coding`
- **Description:** Frontend/UI code — components, layouts, styling, spatial reasoning
- **Model tier:** Mid, code-specialized (same as `coding` today — will diverge as visually-tuned models emerge)
- **When to use:** The agent builds user-facing interfaces — components, layouts, responsive design, CSS, accessibility
- **When NOT to use:** If the agent writes backend code that serves a frontend (use `coding`). If it evaluates design aesthetics without writing code (use `creative`)
- **Example agents:** component-designer, layout-architect, responsive-strategist
- **Example chains:** `[ui-coding, coding, general]`

#### `security-audit`
- **Description:** Vulnerability assessment, attack surface analysis, code auditing
- **Model tier:** Mid, code-specialized + high reasoning
- **When to use:** The agent examines code or systems for security vulnerabilities, reviews authentication flows, assesses attack surfaces
- **When NOT to use:** If the agent is doing general code review (use `critique`). If it's implementing security features (use `coding`)
- **Example agents:** security-guardian
- **Example chains:** `[security-audit, critique, general]`

---

### Cognitive Mode Roles

For agents whose primary value is in HOW they think.

#### `reasoning`
- **Description:** Deep architectural reasoning, system design, complex multi-step analysis
- **Model tier:** Heavy (Opus, gpt-5.4-pro, Gemini Pro) with high reasoning effort
- **When to use:** The agent designs systems, plans architectures, breaks complex problems into steps, or needs extended chain-of-thought
- **When NOT to use:** If the agent evaluates existing work (use `critique`), writes prose (use `writing`), or generates creative concepts (use `creative`)
- **Example agents:** zen-architect, brainstormer, plan-writer, recipe-author
- **Example chains:** `[reasoning, general]`

#### `critique`
- **Description:** Analytical evaluation — finding flaws in existing work, not generating solutions
- **Model tier:** Mid with extra-high reasoning effort
- **When to use:** The agent reviews, evaluates, or finds flaws in existing code, architecture, or plans
- **When NOT to use:** If the agent builds something new (use `reasoning` or `coding`). If it checks for security vulnerabilities specifically (use `security-audit`)
- **Example agents:** spec-reviewer, code-quality-reviewer, friction-detector
- **Example chains:** `[critique, reasoning, general]` or `[critique, general]`

#### `creative`
- **Description:** Design direction, aesthetic judgment, high-quality creative output
- **Model tier:** Heavy (Opus, gpt-5.4, Gemini Pro)
- **When to use:** The agent makes aesthetic judgments, establishes design direction, creates visual concepts
- **When NOT to use:** If the agent writes long-form content (use `writing`). If it writes UI code (use `ui-coding`)
- **Example agents:** art-director, style-curator, storyboard-writer, character-designer
- **Example chains:** `[creative, general]` or `[creative, writing, general]`

#### `writing`
- **Description:** Long-form content — documentation, marketing, case studies, storytelling
- **Model tier:** Heavy (Opus, gpt-5.4, Gemini Pro)
- **When to use:** The agent produces sustained written content — documentation, blog posts, case studies, release notes
- **When NOT to use:** If the output is code with comments (use `coding`). If the writing is short utility text (use `fast`)
- **Example agents:** technical-writer, marketing-writer, release-manager
- **Example chains:** `[writing, creative, general]` or `[writing, general]`

#### `research`
- **Description:** Deep investigation, information synthesis across multiple sources
- **Model tier:** Heavy (Opus, gpt-5.4-pro, Gemini Pro) with high reasoning effort
- **When to use:** The agent investigates and synthesizes from multiple sources. Extended context windows matter
- **When NOT to use:** If the agent designs based on what it already knows (use `reasoning`)
- **Example agents:** browser-researcher, story-researcher
- **Example chains:** `[research, general]`

---

### Capability Roles

For agents that need specific model capabilities beyond text.

#### `vision`
- **Description:** Understanding visual input — screenshots, diagrams, UI mockups
- **Model tier:** Mid, multimodal (Gemini Flash, Sonnet, gpt-5.4)
- **When to use:** The agent analyzes screenshots, reads diagrams, interprets UI mockups
- **When NOT to use:** If the agent generates images (use `image-gen`). If it writes UI code without seeing existing UI (use `ui-coding`)
- **Example agents:** browser-operator, visual-documenter
- **Example chains:** `[vision, general]`

#### `image-gen`
- **Description:** Image generation, visual mockup creation, visual ideation
- **Model tier:** Specialized (gemini-3-pro-image-preview) — sparse provider coverage
- **When to use:** The agent creates images — generating mockups, producing comic panels, visual prototypes
- **When NOT to use:** If the agent analyzes existing images (use `vision`)
- **IMPORTANT:** Always include a non-image-gen fallback. Google-only in most matrices today.
- **Example agents:** panel-artist, cover-artist
- **Example chains:** `[image-gen, creative, general]` (NEVER `image-gen` alone)

---

### Operational Role

#### `critical-ops`
- **Description:** High-reliability operational tasks — infrastructure, orchestration, coordination where mistakes are costly
- **Model tier:** Heavy (Opus, gpt-5.4-pro, Gemini Pro)
- **When to use:** The agent orchestrates infrastructure, manages deployments, verifies shadow environments, or performs operational tasks where failures cascade
- **When NOT to use:** If the agent writes IaC as its primary activity (use `coding`). If it does quick operational checks (use `fast`)
- **Example agents:** shadow-operator, shadow-smoke-test, container-operator
- **Example chains:** `[critical-ops, coding, general]`

---

## Model Tier Grid

Every role maps to a unique (model-tier x reasoning-config) cell:

```
                default reasoning        high reasoning         extra-high reasoning
             ┌──────────────────────┬──────────────────────┬──────────────────────┐
  Heavy      │  creative            │  reasoning           │                      │
  (Opus)     │  writing             │  research            │                      │
             │  critical-ops        │                      │                      │
             ├──────────────────────┼──────────────────────┼──────────────────────┤
  Mid        │  general   coding    │  security-audit      │  critique            │
  (Sonnet)   │  ui-coding           │                      │                      │
             ├──────────────────────┤                      │                      │
  Flash      │  fast     vision     │                      │                      │
  (Haiku)    │                      │                      │                      │
             ├──────────────────────┤                      │                      │
  Specialized│  image-gen           │                      │                      │
             └──────────────────────┴──────────────────────┴──────────────────────┘
```

## Fallback Chain Best Practices

1. **Every chain should end with `general`** (or `fast` for utility agents)
2. **Go specific → general:** `[ui-coding, coding, general]` not `[general, ui-coding]`
3. **Sparse roles need fallbacks:** `[image-gen, creative, general]` — image-gen has limited provider coverage
4. **Don't over-chain:** 2-3 roles is typical. More than 4 suggests confusion about the agent's purpose
5. **Single role is fine** when the agent's need is unambiguous: `fast`, `general`, `coding`
