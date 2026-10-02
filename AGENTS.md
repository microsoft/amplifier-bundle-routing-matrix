# Routing bundle: agent handoff

## Read before work

Read `README.md`, `docs/HANDOFF.md`, `docs/VISION.md`, and the documents relevant to your change:
- Catalog, identity, scope or host integration: `contracts/routing-catalog.v1.md`, `docs/CATALOG-SPEC.md`, `docs/PROVIDER_AVAILABILITY.md`.
- Model preferences, evaluation or evidence: `docs/EVALUATION-PROGRAM.md`, `docs/MATRIX_CURATOR_GUIDE.md`.
- Tests and release gates: `.github/workflows/ci.yml`, `ruff.toml`, module `pyproject.toml` and module tests.

The new vision/catalog contract are **DRAFT**. They describe proposed direction, not delivered behavior, frozen promises or permission to implement. Handoff distinguishes current source facts, proposed changes and decisions still needed. Re-read local conventions at design/code/verification/publication transitions.

## Ownership and invariants

This bundle owns matrix identities, aliases, role definitions, preference policy and resolver semantics. Consumers own presentation, configuration persistence and credential authority. Do not import a consumer application or evaluation runner into the runtime hook. Portable dispatch enforcement is a separately qualified integration dependency, not a capability this routing hook already supplies.

Preserve custom-file precedence, explicit intent, caller inheritance, exact mounted-instance provenance and failure behavior. The current `openai` matrix is API-first across API and ChatGPT; it is **not API-only**. Do not silently change saved IDs, widen account scope, invent fallback IDs, or label wildcard/template discovery verified. Catalog membership and entitlement are different evidence.

The bounded catalog library is documented in `docs/catalog-api.md`. It reuses effective resolver semantics with snapshots and independent initial state; never pass live escalation state, reporting sinks or mutable caches to assessment. Catalog calls must not reach runtime logger handlers: preserve runtime diagnostics by explicit reporting injection, not global logger disabling. Explicit-preference assessment and next-dispatch prediction remain unsupported; broader specification examples are not executable interfaces.

## Verification

The root and routing-module suites both matter. Use the commands and supported Python matrix from `.github/workflows/ci.yml`; run `python -m pytest`, not an accidentally isolated `pytest` entry point. Module checks must actually import Foundation/Core where required; a dependency-induced skip is not a pass. CI pins Ruff at `0.15.11`; do not add unrelated whole-repo formatting. Run `.github/scripts/check_bundle_structure.py` for YAML/frontmatter changes.

Runtime/provider/spawn changes also need an isolated full-stack smoke with real installed dependencies. Record environment readiness before the check, exact revisions, selected test counts, actual results and skips. Unit or catalog checks do not establish live model quality, account containment or deployed adoption. Keep regressions present when reverting production to prove a real red/green pair.

Root CI now needs actual Core/Foundation because catalog tests exercise lifecycle and capability paths. Pre-import them in the **same pytest process** before module fixtures can install a stub; a separate import command is insufficient. Canonical/alias collapse also needs the entire winning-source group to match: a custom canonical profile must not suppress a still-valid bundled alias strategy.

No inference or recurring paid benchmarks in ordinary offline CI. Live runs need an approved token/time/spend envelope, private ignored output storage, lifecycle accounting and safe credentials; parsed-but-inert preset knobs are not budget controls.

## Publication and privacy

Commit only newly authored synthetic fixtures, approved public-source metadata and schema-allowlisted summaries. Never commit raw captures, secret/config-derived hashes, personal identities/paths/endpoints, account bindings, private session maps, holdout answers or private project links. Being visible in a local session is not publication permission. Public attribution must cite an already-public source and disclose no associated private identity.

New content classes require a fresh-context stranger/leak review before push; scan staged content and any uploaded artifacts. Do not copy a private governance document into this public bundle. Keep raw acquisition, subject execution and grading isolated from personal home/browser/credential stores. Do not delete source records merely to produce sanitized artifacts.

## Changes to direction

Drafts may be revised as drafts. A steward-locked document changes through an evidence-backed candidate proposal, never silent edits. Do not mark a document frozen or create a passing ledger from prose. The lock bar needs a discriminating good/bad kit, a passing real implementation, an end-to-end example and the steward's decision. Review approval is not ratification.
