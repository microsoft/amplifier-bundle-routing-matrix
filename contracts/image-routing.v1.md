# Image-role routing policy — v1 (DRAFT 2026-10-13)

What this strategy implementation owes consumers of image-operation routes.

## Who builds against this

Role consumers, policy curators and provider-operation adapters. The existing
[catalog contract](routing-catalog.v1.md) owns identity, scope and enforcement
claims. [Policy notes](../docs/IMAGE-ROUTING.md) own proposed model rankings.

## What it is

An image role retains an agent-capable conversational model and a separately
selected image model. The provider decides whether execution uses one or both.

```yaml
# Illustrative route, not a deployed policy update.
provider: openai
model: gpt-6.1-sol
config:
  image_generation:
    model: gpt-image-2.5-flare
    transport: responses
```

## The promises

1. **IR1 — Keep policy here.** Candidate ordering, strategy identity and source
   precedence remain strategy-owned. Broken: a consumer copies these rankings
   or reads a different matrix than the resolver actually loaded.
2. **IR2 — Qualify before selection.** An optional operation-aware route checks
   exact-instance image execution, controls and model compatibility before it
   commits a winner. Broken: vision input or a bare model name qualifies output.
3. **IR3 — Preserve agent compatibility.** Ordinary role resolution retains an
   agent-capable top-level model; image-only selection is separate configuration.
   Broken: an existing delegate or recipe gets a non-tool-capable image model.
4. **IR4 — Keep scope intact.** Apply catalogue RC3/RC7 to the complete route;
   API, subscription and deployment identities do not collapse into vendor names.
   Broken: OpenAI preference borrows API billing from a restricted subscription route.
5. **IR5 — Keep preferences explicit.** OpenAI-first shared image policy does
   not rewrite provider-specific strategies, custom files or explicit pins.
   Broken: selecting a Gemini-only strategy transmits to a different vendor.
6. **IR6 — Stop at execution.** Candidate selection may advance before dispatch
   only within allowed order. A failed or uncertain effect is not re-routed.
   Broken: an image timeout causes another account or image model to run.
7. **IR7 — Report actual evidence.** Preserve selected source and model-pair
   provenance; capability, catalogue visibility, entitlement and measured quality
   are distinct. Broken: a policy refresh is reported as a quality or live-access win.

## Not in v1

- Universal dispatch/account enforcement; RC6 owns its prerequisite and current
  limitation. This hook cannot qualify execution paths it does not control.
- More provider adapters; promote each with a concrete image-output API and
  exact endpoint/account qualification, never from brand or vision support.
- Automatic paid benchmarking or model-price ranking; promote with a separate
  evaluation design and approved spend envelope.

## How the kit checks it

Proposed checks; neither this file nor the policy note changes shipped matrices.

| Promise | Good observation | Falsifier |
| --- | --- | --- |
| IR1 | Custom shadowing file remains the actual winner | Consumer uses bundled ranking instead |
| IR2 | Incompatible first route is filtered before commitment | Unsupported controls sent or ignored |
| IR3 | Same row serves agent resolution and image preparation | Native image model becomes agent default |
| IR4 | Exact API/subscription/deployment scopes stay separate | Family alias expands account access |
| IR5 | Provider-specific strategies and explicit pins unchanged | Shared default overwrites custom intent |
| IR6 | Unknown effect records zero selection retries | Another image is requested |
| IR7 | New candidates labelled policy, not quality evidence | Catalogue success becomes entitlement |

## Open questions

The generic optional resolver extension requires interoperable signature/version
qualification; this contract does not prescribe a private consumer dependency.
Locking requires a good/bad kit, passing resolver and real consumer integration,
an end-to-end example and the steward's decision. Those gates are not complete.

## Changelog

| Date | Change | Evidence |
| --- | --- | --- |
| 2026-10-13 | Initial IR1–IR7. | Existing image role and single-winner resolution lack operation-aware compatibility; native image models are not necessarily agent-capable. |
