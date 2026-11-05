# Image-role policy direction (DRAFT 2026-10-13)

Companion to [IR](../contracts/image-routing.v1.md). These are proposed policy
changes, not deployed YAML, benchmark wins or evidence of account entitlement.
Existing [vision](VISION.md) and catalogue promises retain their meaning.

## Proposed first preferences

| Strategy | Agent-capable/controller model | Native image model |
| --- | --- | --- |
| balanced | `gpt-6.1-sol` | `gpt-image-2.5-flare` |
| quality | `gpt-6-astra` | `gpt-image-2.5-sunburst` |
| economy | `gpt-6-luna` | `gpt-image-2.5-flare` |
| openai / openai-api | initially Sol + Flare | preserve each profile's existing scope |
| gemini | strategy-selected tool-capable Gemini model | `gemini-nano-banana-2.1` |

Quality-focused Gemini policy can prefer `gemini-3-pro-image`; narrower speed
work can prefer `gemini-3.1-flash-lite-image` only when input/control limits fit.
Mixed strategies retain qualified native-image alternatives after OpenAI choices.
A Gemini operation uses only the native image model; the top-level model exists
for ordinary agent consumers, not an extra paid controller call.

The native image model lives under `config.image_generation.model`. Provider-
owned operation configuration selects the transport; the generic resolver does
not serialize vendor HTTP fields. A mainline controller and image model are
separate requirements when a provider uses a hosted image tool.

## Preservation rules

Do not rewrite provider-specific Anthropic, Copilot, Gemini or ChatGPT scope to
make a raster route appear available. Image-planning agents can still work where
native raster generation is unsupported; an image operation must refuse there.
Custom shadowing policy and explicit account/model choices remain authoritative.
Image-role changes must preserve the caller's ordinary agent resolution behavior,
including applicable effort handling, rather than treating image quality as effort.

The new optional path implements the [generic role-consumption convention](https://github.com/microsoft/amplifier-foundation/blob/main/contracts/model-role-consumption.v1.md).
That linked draft is part of the coordinated documentation packet, not an API
available in released Foundation. No provider or image-tool runtime import is added.

## Source observations

At `edf3603295c03fbe4cc06dc9d818fa84d9405d33`, shared strategies prefer a Gemini
image model and the resolver returns the first successful candidate. Its exact
model match is not an image-capability probe. The ordinary role path can promote
that model into an agent session, so model-role separation needs a regression.

Official documentation checked October 13, 2026:

- [OpenAI image tool](https://developers.openai.com/api/docs/guides/tools-image-generation.md)
  distinguishes the mainline model from the image-tool model.
- [Flare](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare.md) and
  [Sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst.md)
  provide the current image aliases and their intended uses.
- [Nano Banana 2.1](https://ai.google.dev/gemini-api/docs/models/gemini-nano-banana-2.1)
  supports image output but not function calling.

Before adoption, qualify actual provider/module/account combinations, the optional
compatibility extension, and negative cases in IR. Do not claim live availability
or relative quality from this documentation research. Existing runtime, catalogue
and evaluation checks remain required when code or model policy actually changes.
