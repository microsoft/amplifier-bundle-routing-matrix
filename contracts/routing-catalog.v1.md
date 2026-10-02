# Routing catalog contract — v1 (DRAFT 2026-10-02)

Proposed seam between this bundle's strategy policy and consuming hosts. **Partially implemented; not ratified or frozen.** The bounded library subset is documented in [catalog-api](../docs/catalog-api.md); broader dispatch/adoption promises remain unqualified. [Specification and cases](../docs/CATALOG-SPEC.md) provide concrete examples; [handoff](../docs/HANDOFF.md) records evidence, gaps and ownership.

## Core — proposed promises

1. **RC1 — Identity outlives preference.** Strategy IDs and declared aliases belong to the bundle. Descriptors distinguish canonical/requested identity, semantic generation, provider-specific/shared/template classification, display label, sentence, optional note and presentation order. A fallback retains its actual strategy ID. Preference updates do not silently change identity invariants or legacy selections.

2. **RC2 — One effective planner.** Versioned list/describe/assess use supported descriptors and the same effective composition/resolution semantics as execution. Equal immutable inputs, including applicable planning state, produce equal plans. Assessment identifies a new-run baseline or revision-bound next-dispatch prediction; a fresh baseline is not a next-call guarantee. No inference, writes, hidden preparation/refresh or live-state mutation. Changed inputs invalidate prior assessment.

3. **RC3 — Exact scope in selection.** Approved exact provider modules and connection bindings are separate from the strategy ID. Filtering precedes alias/instance selection; final plans validate overrides, caller intent and fallback. Scope exhaustion is explicit. Explicit model preferences do not authorize additional accounts. OpenAI API and ChatGPT remain distinct modules.

4. **RC4 — Discovery tells the truth.** Provider-only discovery assesses the exact dedicated profile first, then other profiles/general strategies against the same roles and snapshots. Results distinguish dedicated, naturally provider-only, and restriction-required routes. Ranking is policy-owned; labels never rename the chosen general matrix or conceal required restrictions.

5. **RC5 — Compatibility has evidence.** Required-role coverage, optional gaps, catalog completeness/freshness, provider availability, scope planning and dispatch-enforcement readiness are separate fields. Exact string resolution, wildcard/template or empty non-authoritative discovery is not verified compatibility. Dynamic providers need actual instance-bound catalog/deployment evidence.

6. **RC6 — Enforcement is a prerequisite.** Scope-aware selection is not enforcement. Strict scoped execution requires accepted runtime/credential ownership and qualified admission preventing unauthorized requests across root, child, resume, auxiliary, direct and fallback paths. Post-call detection is not containment. Unsupported paths fail closed or are unavailable; the routing hook alone supplies no universal guarantee. Hosts disclose `not_enforced` where applicable.

7. **RC7 — Approval does not expand.** Persist identity/semantic generation plus approved scope separately, with effective source/revision and ordered override provenance. Runs pin their prepared inputs. New accounts, rebound IDs, semantic-breaking updates or changed custom policy require reassessment; no implicit scope expansion or mid-call replacement. Compatible preference changes remain inside identity and consent invariants.

8. **RC8 — Consumers share a seam.** UI and agent callers receive equivalent catalog/assessment meaning. The bundle owns strategy policy; hosts own presentation, local persistence and binding authority; portable runtime/credential owners implement dispatch admission. Private paths/bindings never become public evidence identifiers. Qualifying a planner does not qualify a different runtime or deployed consumer.

### Feature boundary grid

`REQUIRED` means needed to qualify this proposed seam; it does not assert present code. `IDIOM` permits local presentation without stronger claims; `EXCLUDED` means not owned or permitted there.

| Feature | Bundle catalog/planner | Host integration | Dispatch/credential boundary |
| --- | --- | --- | --- |
| IDs, aliases, display metadata, policy semantics | REQUIRED | IDIOM rendering | EXCLUDED policy ownership |
| Immutable assessed plan / snapshot provenance | REQUIRED | REQUIRED supplying inputs | REQUIRED verify adopted plan |
| Exact scope planning / no widened fallback | REQUIRED | REQUIRED binding/propagation | REQUIRED final target validation |
| Universal admission by routing hook alone | EXCLUDED | EXCLUDED unsupported claims | REQUIRED for strict execution |
| Presentation / saved selection+scope | EXCLUDED UI | REQUIRED | REQUIRED respect scope |
| Provider-account/principal attestation | EXCLUDED credential discovery | REQUIRED evidence/unknown reporting | REQUIRED binding validation |
| Inference or settings changes in preview | EXCLUDED | EXCLUDED hidden effects | EXCLUDED preview dispatch |

## Backlogged — named promotion triggers

- Distinct-ID Option A was accepted for the first slice: preserve legacy `openai` and add `openai-api` plus `openai-chatgpt`. Reinterpreting `openai` as API-only remains excluded without an explicitly approved migration and mixed-version qualification.
- Portable strict enforcement implementation: dispatch owners accept a mechanism and every supported path passes discriminating containment tests. Until then RC6 prohibits ready claims.
- Azure/dynamic backend adapters: an actual provider owner supplies versioned, instance-bound discovery/deployment evidence and fixtures.
- Automatic recommendation application or background paid recalibration: excluded from v1; a separately approved policy/budget seam is required before considering it.

## Conformance — required before locking

The bounded slice has descriptor, immutable snapshot, source/alias, required-role, catalog-evidence, module-selection, binding-planning and initial-resolution parity checks. These do **not** constitute a kit for the complete contract. Still required: explicit-preference assessment, exhausted versus fresh live state and admission revalidation; mandatory exact-account exclusions through every dispatch/fallback path with negative transport evidence; real consumer adoption and privacy-safe export checks. [The case table](../docs/CATALOG-SPEC.md#acceptance-cases) names observations and [handoff](../docs/HANDOFF.md) distinguishes completed verification from remaining gates.

No ledger or pass claim is derived from this draft. Locking needs a written spec, discriminating machine checks, at least one passing real implementation, an end-to-end example and the steward's decision.

## Reserved

`list`, `describe`, `assess` and `discover_provider_only` exist in the bounded library subset; [catalog-api](../docs/catalog-api.md) owns its exact current shapes and unsupported inputs. Broader illustrative schema fields and next-dispatch prediction remain proposed, not additional exports. Distinct provider IDs preserve legacy meaning; no consumer-generated aliases, ambient-account wildcard approval or secret-derived public account fingerprint is permitted by this draft.

## Changelog

| Date | Change | Evidence |
| --- | --- | --- |
| 2026-10-02 | Initial draft RC1–RC8; unresolved migration/enforcement explicit. | Source-inspected identity, discovery, preview-state and provider-admission gaps; read-only design feedback. No ratification or implementation conformance. |
| 2026-10-02 | Accepted distinct-ID first slice; qualify bounded planning subset separately from the full contract. | Additive profiles and shared snapshot resolver checks; universal dispatch admission and consumer adoption remain unimplemented. This is not a lock or blanket ratification. |
