# amplifier-actions-example

Reference configuration showing how to use
[`microsoft/amplifier-app-actions`](https://github.com/microsoft/amplifier-app-actions)
with [`kenotron-ms/amplifier-bundle-dev-support`](https://github.com/kenotron-ms/amplifier-bundle-dev-support)
for automated issue triage, deep investigation, and PR review on Amplifer ecosystem repos.

---

## What's here

Just four workflow files. No local context files. No recipes. All agent knowledge lives in the bundle.

```
.github/
  workflows/
    issue-triage.yml    ← fires on issues: opened
    investigate.yml     ← fires on /repro comment or needs-investigation label
    pr-review.yml       ← fires on pull_request: opened or /pr comment
    triage-continue.yml ← fires on any issue comment (continues/re-investigates)
```

---

## How it works

Each workflow sets `bundle:` to a file in `amplifier-bundle-dev-support`. The bundle is the
active bundle for the entire run — it carries all context (triage principles, verification
discipline, PR review framework, investigation methodology). The `prompt:` in the workflow
is just the event trigger.

```
workflow prompt: "Triage this issue: https://..."
  + bundle context: GUIDANCE + AGENTS principles + ISSUE_HANDLING workflow
  + tools: github_post_comment, github_add_label, github_checkout_repo
  = agent session
```

No local `AGENTS.md`, `GUIDANCE.md`, or recipe files needed. Any repo that copies these
workflows and adds the `ANTHROPIC_API_KEY` secret gets the same behavior.

---

## Prerequisites

One repository secret:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

---

## Customizing

To change agent behavior, update the context files in
[`amplifier-bundle-dev-support`](https://github.com/kenotron-ms/amplifier-bundle-dev-support) —
not this repo. Changes there propagate to all workflows that reference the bundle via `@main`.

To pin to a specific version, change `@main` to a tag or commit SHA:

```yaml
bundle: git+https://github.com/kenotron-ms/amplifier-bundle-dev-support@v1.0.0#subdirectory=bundles/issue-triage.bundle.md
```

---

## Security

These workflows use `issues` and `pull_request` triggers — not `pull_request_target`.
The agent can read files, post comments, and add labels. It cannot execute code,
make network requests outside the GitHub API, or modify repository content.

`investigate.yml` uses `enable_reproduction: true` which installs Incus and requires
a full VM runner (`ubuntu-latest`), not a container runner.
