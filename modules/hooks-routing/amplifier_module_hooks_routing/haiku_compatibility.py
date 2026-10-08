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
COMPATIBILITY_SCALAR_TYPES = {
    "effort": (str,),
    "reasoning_effort": (str,),
    "thinking_mode": (str,),
    "thinking_type": (str,),
    "thinking_budget_tokens": (int,),
    "thinking_budget": (int,),
    "budget_tokens": (int,),
    "extended_thinking": (bool,),
    "between_tools": (bool, str),
}


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


def _haiku_thinking_disabled(config: Mapping[str, Any]) -> bool:
    """Qualified expert thinking wins; present-null mount thinking disables."""
    extra = config.get("extra_request_params")
    extra = extra if isinstance(extra, Mapping) else {}
    thinking = extra.get("thinking", config.get("thinking"))
    if ("thinking" in extra and isinstance(thinking, Mapping)
            and thinking.get("type") in ("adaptive", "disabled")):
        return thinking["type"] == "disabled"
    return (
        thinking == "disabled"
        or isinstance(thinking, Mapping) and thinking.get("type") == "disabled"
        or config.get("thinking_type") == "disabled"
        or config.get("thinking_mode") == "disabled"
        or "extended_thinking" in config and (
            config["extended_thinking"] is None or config["extended_thinking"] is False
        )
    )


def is_compatibility_leaf(value: Any, types: tuple[type, ...]) -> bool:
    """Closed scalar shapes shared by snapshots and merged runtime config."""
    return value is None or type(value) in types


def _unqualified_thinking_paths(config: Mapping[str, Any]) -> list[str]:
    """Recognized syntax only, not provider-wire qualification from metadata.

    Nested mode is not a synonym for the wire's type discriminator. Keep None
    clears, but refuse non-None mode even when it agrees with type.
    """
    modes = ("enabled", "between_tools", "adaptive", "disabled")
    paths = []
    extra = config.get("extra_request_params")
    if extra is not None and not isinstance(extra, Mapping):
        paths.append("extra_request_params")
    extra = extra if isinstance(extra, Mapping) else {}
    output = extra.get("output_config")
    if output is not None and not isinstance(output, Mapping):
        paths.append("extra_request_params.output_config")
    elif isinstance(output, Mapping) and not is_compatibility_leaf(output.get("effort"), (str,)):
        paths.append("extra_request_params.output_config.effort")
    for key, types in COMPATIBILITY_SCALAR_TYPES.items():
        if not is_compatibility_leaf(config.get(key), types):
            paths.append(key)
    for key, thinking in (("thinking", config.get("thinking")),
                          ("extra_request_params.thinking", extra.get("thinking"))):
        if isinstance(thinking, Mapping):
            if (set(thinking) - {"type", "mode", "budget_tokens"}
                    or any(not is_compatibility_leaf(value, (int,) if key == "budget_tokens" else (str,))
                           for key, value in thinking.items())
                    or thinking.get("mode") is not None
                    or thinking.get("type") is None and any(v is not None for v in thinking.values())
                    or thinking.get("type") is not None and thinking.get("type") not in modes):
                paths.append(key)
        elif thinking is not None and (
            key.startswith("extra_request_params")
            or not isinstance(thinking, str) or thinking not in modes
        ):
            paths.append(key)
    for key in ("thinking_type", "thinking_mode"):
        value = config.get(key)
        if value is not None and (not isinstance(value, str) or value not in modes):
            paths.append(key)
    scalar_modes = [config[key] for key in ("thinking_type", "thinking_mode")
                    if config.get(key) is not None]
    thinking = config.get("thinking")
    if isinstance(thinking, str):
        scalar_modes.append(thinking)
    elif isinstance(thinking, Mapping) and thinking.get("type") is not None:
        scalar_modes.append(thinking["type"])
    if scalar_modes and any(value != scalar_modes[0] for value in scalar_modes[1:]):
        paths.append("thinking")
    return paths


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
    unqualified = _unqualified_thinking_paths(config)
    if unqualified:
        return [HaikuCompatibilityError(
            "haiku_thinking_representation_unknown", model, key,
            "Use an unambiguous supported thinking representation; nested mode, "
            "unknown discriminators and non-scalar leaves are not qualified.",
        ) for key in unqualified]
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
    effective_effort = effective_haiku_effort(config)
    if support is True and _haiku_thinking_disabled(config) and effective_effort in ("xhigh", "max"):
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
