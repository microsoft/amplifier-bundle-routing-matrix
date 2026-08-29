# Model Routing

This session uses the routing matrix system for model selection.

## Available Roles

The live role list for the active matrix is injected into your context every turn
(`Active routing matrix: … / Available model roles: …`). Use those role names — they are
authoritative. Role sets and descriptions differ per matrix; do not rely on any list
written down here.

## For Agent Authors

Use `model_role` in agent frontmatter to declare what kind of model your agent needs:

```yaml
model_role: coding                           # single role
model_role: [ui-coding, coding, general]     # fallback chain (specific → general)
model_role: fast                             # utility agent
```

Fallback chains are tried left-to-right. Always end with `general` or `fast`.

## For Delegating Agents

When delegating to sub-agents, you can override the model role:

```json
{
  "agent": "foundation:explorer",
  "instruction": "Analyze these UI screenshots...",
  "model_role": "vision"
}
```

For detailed role definitions, decision flowchart, model tier grid, and fallback chain guidance, use `load_skill(skill_name='role-definitions')`.
