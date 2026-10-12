"""No default client or credential fallback is permitted in this mount."""

__amplifier_module_type__ = "provider"

SAFE_CONFIG = {
    "default_model",
    "reasoning_effort",
    "max_output_tokens",
    "max_retries",
    "auto_continue",
    "use_streaming",
    "timeout",
    "close_timeout",
    "priority",
    "reasoning_replay_scope",
    "extra_request_params",
}


class UnavailableProvider:
    """Permanently dormant public Provider state; never holds dispatch authority."""

    name = "openai"

    def get_info(self):
        from amplifier_core.models import ProviderInfo

        return ProviderInfo(
            id="openai",
            display_name="Unavailable evaluation provider",
            capabilities=[],
            defaults={},
        )

    async def list_models(self):
        raise RuntimeError("smoke_factory_missing")

    async def complete(self, request, **kwargs):
        raise RuntimeError("smoke_factory_missing")

    def parse_tool_calls(self, response):
        raise RuntimeError("smoke_factory_missing")


async def mount(coordinator, config=None):
    config = dict(config or {})
    if (
        set(config) - SAFE_CONFIG
        or config.get("default_model") not in {"gpt-6.1-sol", "gpt-6-astra"}
        or config.get("reasoning_effort") != "high"
        or type(config.get("max_output_tokens")) is not int
        or config.get("max_output_tokens") != 4096
        or type(config.get("max_retries")) is not int
        or config.get("max_retries") != 0
        or config.get("auto_continue") is not False
        or config.get("use_streaming") is not False
        or config.get("reasoning_replay_scope") != "none"
        or config.get("extra_request_params")
        != {"service_tier": "default", "include": []}
        or not 0 < config.get("timeout", 0) <= 60
        or not 0 < config.get("close_timeout", 0) <= 10
    ):
        raise RuntimeError("smoke_provider_config")
    factory = coordinator.get_capability("smoke.provider_factory")
    if factory is None:
        provider = UnavailableProvider()
        await coordinator.mount("providers", provider, name="openai")

        async def dormant_cleanup():
            pass

        return dormant_cleanup
    if not callable(factory):
        raise RuntimeError("smoke_factory_invalid")
    # Import only inside the explicitly installed isolated real stack.
    from amplifier_module_provider_openai import OpenAIProvider

    provider = factory(coordinator, config)
    if type(provider) is not OpenAIProvider:
        raise RuntimeError("smoke_provider_identity")
    await coordinator.mount("providers", provider, name="openai")

    async def cleanup():
        await provider.close()

    return cleanup
