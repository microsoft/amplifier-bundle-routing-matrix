#!/usr/bin/env python3
"""$0 evidence: what does a candidate preset matrix actually route, and is it
DIFFERENT from what the shipped `openai` matrix routes today?

WHY THIS EXISTS
---------------
`161-preset-validation` measured four presets against the PRE-#55 world, where
the shipped `openai` matrix had no `preset:` block and a terra-rooted session
sent 9-31% of its tree requests to sol. #55 (`320f24e`) landed knob-consistent
delegation as the DEFAULT for OpenAI roots. So the question "does preset X beat
what ships today?" has a different answer than it had on 2026-09-02 morning,
and the cheapest way to find out which presets are still DISTINCT is to ask the
resolver itself -- no API spend, no container, fully reproducible.

This walks the real code path (`matrix_loader.parse_preset` ->
`knob_consistency.plan_candidates` -> `resolver.resolve_model_role`) with a
fixed fake provider roster, so the answer is a function of the MATRICES and the
CODE only.

A preset whose per-role (model, effort) plan is IDENTICAL to the shipped
matrix's, at the root the user would actually run it at, is a second name for
the default. Shipping it would be a rename, not a win -- and that is a DROP
reason that costs $0 to establish and can be re-run by anyone.

Usage:
    PYTHONPATH=modules/hooks-routing python3 docs/lanes/ytg-presets-revision/tools/plan_equivalence.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
ROUTING_DIR = REPO_ROOT / "routing"
sys.path.insert(0, str(REPO_ROOT / "modules" / "hooks-routing"))

from amplifier_module_hooks_routing.knob_consistency import (  # noqa: E402
    CallerContext,
    EscalationState,
    parse_preset,
)
from amplifier_module_hooks_routing.resolver import (  # noqa: E402
    resolve_model_role,
)

# Same roster the repo's own golden-fixture test uses, for the same reason:
# the recording must be a function of code + matrices, never of what a live
# provider happened to list on the day.
FAKE_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-fable-5-1",
    ],
    "openai": [
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.6-mini",
        "gpt-5.6-nano",
        "gpt-5.6",
        "gpt-5.5",
    ],
    "gemini": ["gemini-3-pro-preview", "gemini-3-flash-preview"],
    "github-copilot": ["claude-sonnet-4.6", "claude-opus-4.6", "gpt-5.5"],
    "ollama": ["qwen3.6-35b", "llama4-70b"],
}

ROLES = [
    "general",
    "fast",
    "coding",
    "ui-coding",
    "security-audit",
    "reasoning",
    "critique",
    "creative",
    "writing",
    "research",
    "vision",
    "image-gen",
    "critical-ops",
]


def _providers() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, models in FAKE_MODELS.items():
        p = MagicMock()
        p.list_models = AsyncMock(return_value=list(models))
        out[name] = p
    return out


async def plan(
    matrix_path: Path, caller: CallerContext | None
) -> dict[str, dict[str, Any]]:
    """Per-role (provider, model, effort) this matrix routes to, for `caller`."""
    data = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    roles = data.get("roles") or {}
    preset = parse_preset(data)
    esc = EscalationState(max_uses=preset.escalate_max_uses) if preset else None
    out: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        if role not in roles:
            out[role] = {"resolved": None, "note": "role absent from matrix"}
            continue
        res = await resolve_model_role(
            [role],
            roles,
            _providers(),
            caller_context=caller,
            preset=preset,
            escalations=esc,
        )
        top = res[0] if res else None
        out[role] = (
            {
                "provider": top.get("provider"),
                "model": top.get("model"),
                "effort": (top.get("config") or {}).get("reasoning_effort"),
            }
            if top
            else {"resolved": None}
        )
    return out


def diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {r: {"A": a.get(r), "B": b.get(r)} for r in ROLES if a.get(r) != b.get(r)}


CALLERS = {
    "terra@medium": CallerContext("openai", "gpt-5.6-terra", "medium"),
    "terra@high": CallerContext("openai", "gpt-5.6-terra", "high"),
    "luna@medium": CallerContext("openai", "gpt-5.6-luna", "medium"),
    "sol@high": CallerContext("openai", "gpt-5.6-sol", "high"),
    "COLD (no caller)": None,
}


def main() -> int:
    targets = sys.argv[1:] or ["openai.yaml"]
    shipped = ROUTING_DIR / "openai.yaml"
    report: dict[str, Any] = {"callers": {}}
    for cname, caller in CALLERS.items():
        base = asyncio.run(plan(shipped, caller))
        entry: dict[str, Any] = {"shipped_openai": base, "vs": {}}
        for t in targets:
            p = ROUTING_DIR / t
            if not p.exists():
                p = Path(t)
            if not p.exists():
                entry["vs"][t] = {"error": "matrix not found"}
                continue
            other = asyncio.run(plan(p, caller))
            d = diff(base, other)
            entry["vs"][t] = {
                "identical_to_shipped_openai": not d,
                "differing_roles": d,
                "plan": other,
            }
        report["callers"][cname] = entry
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
