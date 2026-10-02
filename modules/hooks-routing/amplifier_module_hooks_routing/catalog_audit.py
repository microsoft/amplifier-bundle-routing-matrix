"""Catalog freshness checks; no inference, configuration writes or model policy."""

from __future__ import annotations

import asyncio
import fnmatch
import re
from typing import Any

from .resolver import _is_glob, _version_sort_key


def _family(model: str) -> str | None:
    """Only compare standard IDs within a named class, never cross tiers."""
    match = re.fullmatch(r"gpt-\d+(?:\.\d+)?-(sol|terra|luna)", model)
    if match:
        return "gpt-" + match[1]
    match = re.fullmatch(r"claude-(sonnet|opus|haiku)-\d+(?:[.-]\d+)*", model)
    if match:
        return "claude-" + match[1]
    match = re.fullmatch(
        r"gemini-\d+(?:\.\d+)?-(flash|flash-lite|pro|pro-preview|pro-image|flash-image)", model
    )
    if match:
        return "gemini-" + ("pro" if match[1] == "pro-preview" else match[1])
    return None


def _freshness_key(model: str) -> tuple:
    """Compare Pro GA/preview as peers; prefer GA on an equal release version."""
    if _family(model) == "gemini-pro":
        return (_version_sort_key(model.removesuffix("-preview")), not model.endswith("-preview"))
    return (_version_sort_key(model), True)


async def collect_catalogs(providers: dict[str, Any], timeout: float = 60) -> dict[str, dict]:
    """Fetch actual provider menus; callers must disable static/cache fallback.

    Serialize only public model IDs/capabilities and exception class names.
    Never serialize provider objects, config, exception text or request headers.
    """
    catalogs = {}
    for name, provider in providers.items():
        try:
            models = await asyncio.wait_for(provider.list_models(), timeout)
            catalogs[name] = {
                "status": "ok" if models else "empty",
                "models": [
                    {"id": m.id, "capabilities": list(getattr(m, "capabilities", []))}
                    for m in models
                ],
            }
        except Exception as error:
            catalogs[name] = {"status": "error", "error_type": type(error).__name__, "models": []}
    return catalogs


def audit_matrix_catalogs(matrices: dict[str, dict], catalogs: dict[str, dict]) -> dict:
    """Validate all candidates on requested backends, including lower fallbacks.

    Unrequested providers are outside this check, not evidence of availability.
    Exact-pin acceptance in the runtime resolver intentionally remains unchanged.
    """
    issues, checked = [], 0
    for backend, catalog in catalogs.items():
        if catalog.get("status") != "ok" or not catalog.get("models"):
            issues.append({"kind": "catalog_unavailable", "provider": backend})
            continue
        models = {m["id"]: m for m in catalog["models"]}
        names = list(models)
        for matrix_name, matrix in matrices.items():
            allowlist = matrix.get("provider_module_allowlist")
            if allowlist is not None and f"provider-{backend}" not in allowlist:
                continue
            for role, definition in matrix["roles"].items():
                for index, candidate in enumerate(definition["candidates"]):
                    wanted = candidate["provider"]
                    if backend != wanted and not (wanted == "openai" and backend == "openai-chatgpt"):
                        continue
                    checked += 1
                    pattern = candidate["model"]
                    context = {"provider": backend, "matrix": matrix_name, "role": role,
                               "candidate": index + 1, "pattern": pattern}
                    matches = [m for m in names if fnmatch.fnmatch(m.lower(), pattern.lower())]
                    if not matches:
                        issues.append({"kind": "missing_glob" if _is_glob(pattern) else "missing_pin",
                                       **context})
                        continue
                    selected = max(matches, key=_version_sort_key)
                    family = _family(selected)
                    peers = [m for m in names if family and _family(m) == family]
                    if peers:
                        latest = max(peers, key=_freshness_key)
                        if _freshness_key(latest) > _freshness_key(selected):
                            issues.append({"kind": "stale_model", **context,
                                           "selected": selected, "latest": latest})
                    if role == "vision" and "vision" not in models[selected].get("capabilities", []):
                        issues.append({"kind": "vision_not_advertised", **context, "selected": selected})
    return {"checked_candidates": checked, "issues": issues,
            "status": "fail" if issues or not checked else "pass"}