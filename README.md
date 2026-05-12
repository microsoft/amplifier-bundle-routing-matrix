# amplifier-actions-example

Reference configuration showing a repository set up with [amplifier-app-actions](https://github.com/kenotron-ms/amplifier-app-actions) for automated issue triage and PR review.

## What's configured

- `.github/workflows/issue-triage.yml` — triages new issues: classifies type, adds label, posts acknowledgment comment
- `.github/workflows/pr-review.yml` — reviews new PRs: summarizes changes, flags concerns, posts findings

## Prerequisites

One repository secret:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

## Customizing the prompts

Edit the `prompt:` block in either workflow file. The prompt tells the agent what to do with the issue or PR. See the [amplifier-app-actions docs](https://github.com/kenotron-ms/amplifier-app-actions) for all configuration options including alternative providers, recipe mode, and model selection.

## Security

These workflows use `issues` and `pull_request` triggers — not `pull_request_target`. The agent can read files, post comments, and add labels. It cannot execute code, make network requests, or modify repository content.
