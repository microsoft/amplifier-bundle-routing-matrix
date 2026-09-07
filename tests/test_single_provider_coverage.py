"""Every supported provider must route on its own, from the default matrix.

WHY THIS EXISTS

`balanced` is the out-of-the-box matrix: `behaviors/routing.yaml` sets
`default_matrix: balanced`, and `hooks-routing`'s own code default is the same
string, so a consumer that configures nothing still lands here. A user who has
exactly ONE provider configured is therefore routed by `balanced` alone.

Nothing checked that `balanced` could actually serve such a user. On
2026-09-07 it could not: a user whose only provider was `openai-chatgpt` got
**zero** roles resolved out of thirteen -- every role fell through to nothing,
because no shipped matrix named that provider. It is a separate provider
MODULE from `openai` (the OAuth/ChatGPT-subscription backend vs the API-key
backend), so `find_provider_by_type` matched it neither by name nor via the
module-type fallback. The failure was silent: routing simply set no
preference and the agent used the session default.

The fix is `PROVIDER_FAMILY_ALIASES` in the resolver: `provider: openai` now
matches either backend, API key first. So the `openai-chatgpt` case below is
the load-bearing one -- it passes ONLY because the alias works, since no
shipped matrix names that provider directly any more (and
`test_no_matrix_names_the_chatgpt_backend_directly` pins that).

The golden-fixture test in `test_default_resolution_unchanged.py` cannot catch
this class. It resolves every matrix against a roster where EVERY provider is
mounted at once, so a role always finds *some* candidate -- exactly the
condition that hides a single-provider hole.

WHAT IS DELIBERATELY EXEMPT

`image-gen` is Gemini-only in every shipped matrix: no other provider exposes
an image-generation endpoint through this bundle. An agent asking for it falls
back through its own `model_role` list (`[image-gen, creative, general]`) and
lands on a real model, which is the documented contract. That exemption is
named per provider below rather than blanket-skipped, so a role quietly
dropping out of coverage still fails here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTING_DIR = REPO_ROOT / "routing"

sys.path.insert(0, str(REPO_ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing.resolver import (  # noqa: E402
    resolve_model_role,
)

# The matrix a consumer gets when it configures nothing. Asserted below against
# both places that default is declared, so this constant cannot drift silently.
DEFAULT_MATRIX = "balanced"

# A fixed roster per provider, taken from live `list_models()` output on
# 2026-09-07. Trimmed to the ids these matrices can select, PLUS the near-miss
# ids a glob could wrongly prefer -- the `-fast` variants are here on purpose.
PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
        "claude-fable-5-1",
    ],
    "openai": [
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
    ],
    "openai-chatgpt": [
        "gpt-6-astra",
        "gpt-6-astra-fast",
        "gpt-5.6-sol",
        "gpt-5.6-sol-fast",
        "gpt-5.6-terra",
        "gpt-5.6-terra-fast",
        "gpt-5.6-luna",
        "gpt-5.6-luna-fast",
        "gpt-5.5",
        "gpt-5.5-fast",
        "gpt-5.4-mini",
    ],
    "gemini": [
        "gemini-3.1-pro-preview",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-3-pro-image",
        "gemini-2.5-flash",
        "gemini-omni-flash-preview",
    ],
    "github-copilot": [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4.5",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
    ],
}

# Roles a given provider legitimately cannot serve from `balanced`, with the
# reason. An empty set means "must serve every role".
EXEMPT: dict[str, set[str]] = {
    "anthropic": {"image-gen"},
    "openai": {"image-gen"},
    "openai-chatgpt": {"image-gen"},
    "github-copilot": {"image-gen"},
    "gemini": set(),  # gemini IS the image-gen provider
}


def _providers(name: str) -> dict[str, Any]:
    provider = MagicMock()
    provider.list_models = AsyncMock(return_value=list(PROVIDER_MODELS[name]))
    return {name: provider}


def _roles(matrix_name: str) -> dict[str, Any]:
    data = yaml.safe_load(
        (ROUTING_DIR / f"{matrix_name}.yaml").read_text(encoding="utf-8")
    )
    return data["roles"]


def test_default_matrix_is_balanced_in_both_places() -> None:
    """The behaviour every other test here assumes, asserted rather than implied.

    Two independent declarations, because a consumer bundle can omit the
    config block entirely and still has to land somewhere sensible.
    """
    behaviour = yaml.safe_load(
        (REPO_ROOT / "behaviors" / "routing.yaml").read_text(encoding="utf-8")
    )
    declared = [
        hook.get("config", {}).get("default_matrix")
        for hook in behaviour.get("hooks", [])
        if hook.get("module") == "hooks-routing"
    ]
    assert declared == [DEFAULT_MATRIX], (
        f"behaviors/routing.yaml no longer defaults to {DEFAULT_MATRIX!r}: {declared}"
    )

    source = (
        REPO_ROOT
        / "modules"
        / "hooks-routing"
        / "amplifier_module_hooks_routing"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    assert f'config.get("default_matrix", "{DEFAULT_MATRIX}")' in source, (
        f"hooks-routing's code default is no longer {DEFAULT_MATRIX!r}. A consumer "
        "that omits the config block falls back to it, so the two must agree."
    )

    assert (ROUTING_DIR / f"{DEFAULT_MATRIX}.yaml").exists()


@pytest.mark.parametrize("provider_name", sorted(PROVIDER_MODELS))
def test_provider_alone_routes_every_role_of_the_default_matrix(
    provider_name: str,
) -> None:
    """One provider, mounted alone, must resolve every non-exempt role."""
    roles = _roles(DEFAULT_MATRIX)
    providers = _providers(provider_name)

    async def _run() -> dict[str, Any]:
        return {
            role: await resolve_model_role([role], roles, providers) for role in roles
        }

    resolved = asyncio.run(_run())
    exempt = EXEMPT[provider_name]

    unresolved = {r for r, got in resolved.items() if not got}
    assert unresolved == exempt, (
        f"with ONLY {provider_name!r} configured, {DEFAULT_MATRIX}.yaml leaves "
        f"these roles unrouted: {sorted(unresolved)} (expected exactly "
        f"{sorted(exempt)}). A role that resolves to nothing is silent -- the "
        "agent falls back to the session default provider and no error is "
        "raised, so this assertion is the only thing that notices."
    )

    # The resolved candidate reports the MOUNT it matched, which for an
    # aliased family is the mounted name (`openai-chatgpt`), reached through a
    # candidate that says `provider: openai`.
    for role, got in resolved.items():
        if role in exempt:
            continue
        assert got[0]["provider"] == provider_name, (
            f"role {role!r} resolved to provider {got[0]['provider']!r} when only "
            f"{provider_name!r} was mounted"
        )


@pytest.mark.parametrize("matrix_name", ["balanced", "quality", "economy", "openai"])
def test_openai_globs_are_suffix_free_and_never_select_a_fast_variant(
    matrix_name: str,
) -> None:
    """The `-fast` trap, asserted on the one glob vocabulary both backends share.

    The ChatGPT backend serves `gpt-5.6-terra` AND `gpt-5.6-terra-fast`. A
    trailing `*` matches both, they tie on version, and the resolver's
    tie-break prefers the LONGER name -- so `gpt-?.?-terra*` silently selects
    the `-fast` variant. (Same shape as `gpt-5.6-sol-fast` on GitHub Copilot.)

    Since `provider: openai` now reaches the chatgpt backend through the family
    alias, every openai candidate's glob is resolved against the chatgpt model
    list in production whenever that is the mounted backend. So the assertion
    is exactly that: mount ONLY chatgpt, resolve every openai candidate, and
    require the clean id every time.

    CANDIDATE globs only. The preset `tier_ladder` keeps its `*` on purpose:
    it CLASSIFIES an already-chosen model rather than SELECTING one, so it
    must still match a hand-pinned suffixed id.
    """
    roles = _roles(matrix_name)
    providers = _providers("openai-chatgpt")
    named = [
        (role, c)
        for role, r in roles.items()
        for c in r["candidates"]
        if c.get("provider") == "openai"
    ]
    assert named, f"{matrix_name}.yaml names no openai candidate"

    for role, candidate in named:
        assert not candidate["model"].endswith("*"), (
            f"{matrix_name}.yaml role {role!r}: openai model "
            f"{candidate['model']!r} ends in '*'. On the ChatGPT backend that "
            "resolves to the '-fast' variant. Drop the trailing '*'."
        )

    async def _run() -> dict[str, Any]:
        return {
            role: await resolve_model_role([role], roles, providers)
            for role, _ in named
        }

    for role, got in asyncio.run(_run()).items():
        assert got, f"{matrix_name}.yaml role {role!r} did not resolve via the alias"
        assert not got[0]["model"].endswith("-fast"), (
            f"{matrix_name}.yaml role {role!r} resolved to {got[0]['model']!r}"
        )


def test_no_matrix_names_the_chatgpt_backend_directly() -> None:
    """DRY guard: the family alias makes a `provider: openai-chatgpt` candidate
    redundant, and 49 of them were removed on 2026-09-07. One creeping back in
    would mean a role that has to be edited twice again."""
    offenders = [
        f"{path.name}:{role}"
        for path in sorted(ROUTING_DIR.glob("*.yaml"))
        for role, data in yaml.safe_load(path.read_text(encoding="utf-8"))[
            "roles"
        ].items()
        for c in data["candidates"]
        if c.get("provider") == "openai-chatgpt"
    ]
    assert not offenders, (
        f"these candidates name openai-chatgpt directly: {offenders}. "
        "`provider: openai` already reaches that backend via "
        "PROVIDER_FAMILY_ALIASES -- one candidate serves both bills."
    )
