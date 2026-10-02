# Routing Matrix — Vision (DRAFT 2026-10-02)

This page describes the proposed destination, not shipped capabilities or current work. It is not ratified or frozen. Implementation status, review gaps and sequencing belong in [HANDOFF](HANDOFF.md). The proposed external seam is [routing-catalog.v1](../contracts/routing-catalog.v1.md); its concrete shapes belong in [CATALOG-SPEC](CATALOG-SPEC.md).

## What this bundle is

A portable, evidence-informed owner of model-routing strategies. Agents ask for capabilities; hosts present understandable choices; the same routing policy determines assessed and executed choices. Strategies evolve from measured outcomes without rewriting user intent, silently changing saved selection meaning, or expanding approved provider/account scope.

## Principles

### 1. Policy has one owner

Role definitions, model preferences, strategy identity, descriptions and recommended ordering live here. A consumer renders the catalog and preserves its actual IDs instead of inventing aliases or copying model-ranking rules. Runtime adapters supply capabilities; they do not redefine strategy meaning.

### 2. Evidence precedes preference

Catalog freshness establishes possible availability, not task quality. Recommendations cite comparable task evidence, actual role exposure, failure/missingness, critical outcomes and resource costs. Unknown prices, model revisions or grading remain unknown. Synthetic smoke checks are not benchmark wins.

### 3. Intent and scope survive

Explicit caller choices remain respected within the approved execution scope. Exact provider modules and account connections do not collapse into billing-family names. Additional accounts, aliases, overrides and fallback paths cannot silently enlarge consent. A scoped execution claim is unavailable until actual dispatch containment is qualified.

### 4. Assessment is honest and inert

Assessment uses the effective policy and immutable catalog/caller/scope inputs. It performs no inference or configuration mutation. Missing required roles, unknown catalogs, stale snapshots and unsupported enforcement have separate explanations. A preview does not spend live escalation state or claim model entitlement from string resolution.

### 5. Evidence improves through reuse

A qualified frozen regression core supports targeted new-model screening; fresh heldout families prevent repeated tuning from becoming the result. Changed bundles, providers, tools, graders or environments trigger explicit comparability review and affected-role recalibration. Regrading retained output is distinguished from fresh execution and repricing from measured spend.

### 6. Privacy is a boundary

Source contains public specifications, newly authored synthetic fixtures, pinned-source metadata and approved summary schemas. Private records are inspiration for mechanisms, not fixtures to publish after token substitution. Raw work, identities, account bindings and protected answers stay in isolated, private evidence storage. Public export is fail-closed and reviewed as a separate product boundary.

## What this deliberately resists

- Newest-model or leaderboard-only ranking presented as measured fit.
- One aggregate score standing for all roles, backends, modalities and budgets.
- Host-specific policy, hidden model calls in preview, or consumer runtime dependencies.
- Silent reinterpretation of legacy IDs or aliases used to disguise a fallback matrix.
- Availability or planner filtering presented as universally enforced account containment.
- Private transcripts, secret-derived fingerprints or automatic public trajectory uploads.
- Tiny repeated pilots presented as independent population evidence or automatic promotion.
- Governance machinery, contracts for internals, or frozen stamps without discriminating checks.

## Observable destination

A maintainer can trace each changed role preference to a reviewed evidence packet and its limits. A host can render the strategy without copying model rules. A caller can distinguish configured, assessed, executed and unknown outcomes. A scoped run either remains within its exact approved bindings or refuses an unsupported path. A new evaluator can reproduce a comparison without this conversation or private accounts.

## Changelog

| Date | Change | Basis |
| --- | --- | --- |
| 2026-10-02 | Initial draft direction; no accepted amendments or lock. | Request for reusable evidence-based strategies, consumer catalog ownership and safe future-agent handoff. |
