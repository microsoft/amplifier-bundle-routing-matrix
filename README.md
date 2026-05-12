# amplifier-actions-example

Reference configuration showing a repository set up with
[amplifier-app-actions](https://github.com/kenotron-ms/amplifier-app-actions)
for automated issue triage and PR review.

## Design principle

Comments are the premium interface. When a new issue is opened, the agent posts
a structured triage comment. When a new PR is opened, the agent posts a structured
review comment. The comment is the product — it is how analysis reaches the user.

Prompts are not the configuration surface. Recipes are. Each recipe encodes a
structured investigation process: what to check, in what order, how to report
findings. Swapping the recipe changes the behavior; swapping the workflow file
does not.

## What's configured

| File | Purpose |
|------|---------|
| `.github/workflows/issue-triage.yml` | Triggers on `issues: opened`, runs the triage recipe |
| `.github/workflows/pr-review.yml` | Triggers on `pull_request: opened`, runs the review recipe |
| `.github/amplifier/triage-recipe.yaml` | Structured triage: classify → label → comment |
| `.github/amplifier/pr-review-recipe.yaml` | Structured review: read files → five checks → comment |

## Prerequisites

One repository secret:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

## Customizing the recipes

Edit the `.github/amplifier/*.yaml` recipe files. The recipe encodes the
investigation logic: which steps to run, what to check, how to format the
output comment. The workflow files do not need to change when you change
what the agent investigates.

Recipes support multiple steps with explicit ordering, bash steps for
deterministic data gathering, and agent steps for LLM analysis. See the
[amplifier-app-actions docs](https://github.com/kenotron-ms/amplifier-app-actions)
for the full recipe schema.

## Security

These workflows use `issues` and `pull_request` triggers — not `pull_request_target`.
The agent can read files, post comments, and add labels. It cannot execute code,
make network requests outside the GitHub API, or modify repository content.
