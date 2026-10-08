"""Bounded Haiku config compatibility, not model ranking or protocol discovery.

Only exact native Anthropic 5.5 and released 4.5 IDs are qualified here.
Unresolved policy patterns defer to the concrete runtime/catalog selection.
No defaults are inserted: the provider owns adaptive thinking and medium effort.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

EFFORT_KEYS = ("effort", "reasoning_effort")
HAIKU_55 = "claude-haiku-5-5"
HAIKU_45 = ("claude-haiku-4-5", "claude-haiku-4-5-20251001")
HAIKU_55_EFFORTS = ("low", "medium", "high", "xhigh", "max")
COMPATIBILITY_CONFIG_KEYS = (
    *EFFORT_KEYS,
    "thinking_budget_tokens",
    "thinking_budget",
    "budget_tokens",
    "thinking",
    "thinking_mode",
    "thinking_type",
    "between_tools",
    "extended_thinking",
    "extra_request_params",
)


class HaikuCompatibilityError(ValueError):
    """Selected config cannot be honored; never permits candidate fallback."""

    def __init__(self, code: str, model: str, key: str, remediation: str):
        self.code, self.model, self.key = code, model, key
        super().__init__(f"{code}: {model} / {key} REJECTED — {remediation}")


def is_haiku(model: Any) -> bool:
    return isinstance(model, str) and "haiku" in model.lower()


def may_select_haiku(model: Any) -> bool:
    """Keep effort on class/generic globs that may select a concrete Haiku."""
    if is_haiku(model):
        return True
    if not isinstance(model, str):
        return False
    wildcard_positions = [model.index(c) for c in "*?[" if c in model]
    if not wildcard_positions:
        return False
    literal_prefix = model[: min(wildcard_positions)].lower()
    return "claude-haiku-".startswith(literal_prefix)


def haiku_effort_support(model: str, backend: str | None) -> bool | None:
    """None means unqualified, not supported. Backend is a module type, not an ID."""
    if not is_haiku(model):
        return None
    if model in HAIKU_45 or model == "claude-haiku-4.5":
        return False
    if backend == "anthropic" and model == HAIKU_55:
        return True
    return None


def effective_haiku_effort(config: Mapping[str, Any]) -> Any:
    """Expert output_config replaces computed output_config, including clears."""
    extra = config.get("extra_request_params")
    if isinstance(extra, Mapping) and "output_config" in extra:
        output = extra["output_config"]
        return output.get("effort") if isinstance(output, Mapping) else None
    return config.get("reasoning_effort") if config.get("reasoning_effort") is not None else config.get("effort")


def haiku_config_errors(
    backend: str | None,
    model: Any,
    config: Mapping[str, Any],
    *,
    policy: bool = False,
) -> list[HaikuCompatibilityError]:
    """Pure shared validation; policy defers globs and arbitrary instance IDs.

    Runtime must supply the *mounted module* and concrete model, after scope
    filtering. Anthropic model facts do not qualify Copilot's native protocol.
    """
    if not is_haiku(model):
        return []
    if policy and (
        any(c in model for c in "*?[")
        or backend not in ("anthropic", "github-copilot", "gemini", "openai")
    ):
        return []
    if policy:
        # Policy handles (even "gemini") can name any mounted module. Check
        # only the bounded native model rules here, not backend qualification.
        # Actual selection must still qualify the exact mount independently.
        backend = "anthropic"

    efforts = {key: config[key] for key in EFFORT_KEYS if config.get(key) is not None}
    extra = config.get("extra_request_params")
    extra = extra if isinstance(extra, Mapping) else {}
    output = extra.get("output_config")
    if isinstance(output, Mapping) and output.get("effort") is not None:
        efforts["extra_request_params.output_config.effort"] = output["effort"]
    manual = [
        key
        for key in ("thinking_budget_tokens", "thinking_budget", "budget_tokens")
        if config.get(key) is not None
    ]
    for key, thinking in (("thinking", config.get("thinking")),
                          ("extra_request_params.thinking", extra.get("thinking"))):
        if isinstance(thinking, Mapping):
            if (thinking.get("budget_tokens") is not None
                    or thinking.get("type") in ("enabled", "between_tools")
                    or thinking.get("mode") == "between_tools"):
                manual.append(key)
        elif thinking in ("enabled", "between_tools"):
            manual.append(key)
    manual.extend(
        key
        for key in ("thinking_mode", "thinking_type", "between_tools")
        if config.get(key) in ("enabled", "between_tools")
        or (key == "between_tools" and config.get(key) is not None)
    )
    if not efforts and not manual:
        return []

    support = haiku_effort_support(model, backend)
    errors = []
    for key, effort in efforts.items():
        if support is False:
            budget = 4096 if effort == "low" else 32000
            advice = (
                f"Haiku 4.5 has no native effort. Use thinking_budget_tokens: {budget} "
                "only on qualified native Anthropic 4.5, or explicitly select native 5.5."
            )
            errors.append(HaikuCompatibilityError("haiku_effort_unsupported", model, key, advice))
        elif support is None:
            errors.append(
                HaikuCompatibilityError(
                    "haiku_compatibility_unknown",
                    model,
                    key,
                    "Pin a qualified exact model/backend; no future ID or alias support is inferred.",
                )
            )
        elif effort not in HAIKU_55_EFFORTS:
            errors.append(
                HaikuCompatibilityError(
                    "haiku_effort_invalid",
                    model,
                    key,
                    "Native 5.5 accepts only low, medium, high, xhigh, max.",
                )
            )
    for key in manual:
        if backend == "anthropic" and model in HAIKU_45:
            continue
        code = (
            "haiku_manual_thinking_forbidden" if support is True else "haiku_compatibility_unknown"
        )
        errors.append(
            HaikuCompatibilityError(
                code,
                model,
                key,
                "Remove the manual budget/between_tools setting explicitly. Native 5.5 uses "
                "adaptive thinking; manual budgets are qualified only for native Anthropic 4.5.",
            )
        )
    # The transport escape hatch wins over computed thinking/output_config.
    thinking = extra.get("thinking", config.get("thinking"))
    disabled = (
        thinking == "disabled"
        or isinstance(thinking, Mapping) and thinking.get("type") == "disabled"
        or config.get("thinking_type") == "disabled"
        or config.get("thinking_mode") == "disabled"
        or config.get("extended_thinking") is False
    )
    effective_effort = effective_haiku_effort(config)
    if support is True and disabled and effective_effort in ("xhigh", "max"):
        errors.append(HaikuCompatibilityError(
            "haiku_disabled_thinking_effort", model, "thinking",
            "Remove explicit thinking disable or use low, medium, high; "
            "xhigh/max require adaptive thinking on native 5.5.",
        ))
    return errors


def require_haiku_config(
    backend: str | None,
    model: Any,
    config: Mapping[str, Any],
    *,
    policy: bool = False,
) -> None:
    errors = haiku_config_errors(backend, model, config, policy=policy)
    if errors:
        raise errors[0]
