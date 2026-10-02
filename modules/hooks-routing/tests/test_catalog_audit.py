"""Freshness checks must fail closed without changing runtime pin semantics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from amplifier_module_hooks_routing.catalog_audit import audit_matrix_catalogs, collect_catalogs


def matrices(model, provider="github-copilot", role="general"):
    return {"test": {"roles": {role: {"candidates": [{"provider": provider, "model": model}]}}}}


def catalog(*models, status="ok"):
    return {"status": status, "models": [{"id": m, "capabilities": ["vision"]} for m in models]}


def test_absent_exact_pin_is_detected_even_though_runtime_accepts_it():
    result = audit_matrix_catalogs(matrices("missing"), {"github-copilot": catalog("other")})
    assert result["status"] == "fail"
    assert result["issues"][0]["kind"] == "missing_pin"


def test_stale_pin_compares_only_same_family():
    result = audit_matrix_catalogs(matrices("claude-sonnet-5"), {
        "github-copilot": catalog("claude-sonnet-5", "claude-sonnet-5.5", "claude-opus-9")
    })
    assert result["issues"][0]["latest"] == "claude-sonnet-5.5"


def test_terra_is_not_demoted_for_a_newer_sol():
    result = audit_matrix_catalogs(matrices("gpt-5.6-terra", "openai"), {
        "openai": catalog("gpt-5.6-terra", "gpt-6.1-sol")
    })
    assert result["status"] == "pass"


def test_old_luna_glob_is_detected():
    result = audit_matrix_catalogs(matrices("gpt-?.?-luna", "openai"), {
        "openai": catalog("gpt-5.6-luna", "gpt-6-luna")
    })
    assert result["issues"][0]["kind"] == "stale_model"


def test_new_luna_glob_excludes_fast():
    result = audit_matrix_catalogs(matrices("gpt-[0-9]*-luna", "openai"), {
        "openai-chatgpt": catalog("gpt-5.6-luna", "gpt-6-luna", "gpt-6-luna-fast")
    })
    assert result["status"] == "pass" and result["checked_candidates"] == 1


@pytest.mark.parametrize("status", ["error", "empty", "static-fallback"])
def test_unavailable_or_fallback_catalog_never_passes(status):
    result = audit_matrix_catalogs(matrices("any"), {"github-copilot": catalog("any", status=status)})
    assert result["status"] == "fail"
    assert result["issues"][0]["kind"] == "catalog_unavailable"


def test_no_requested_candidate_is_not_success():
    assert audit_matrix_catalogs({}, {"openai": catalog("gpt-6-luna")})["status"] == "fail"


def test_vision_requires_advertised_capability():
    data = catalog("claude-sonnet-5.5")
    data["models"][0]["capabilities"] = []
    result = audit_matrix_catalogs(matrices("claude-sonnet-5.5", role="vision"), {"github-copilot": data})
    assert result["issues"][0]["kind"] == "vision_not_advertised"


@pytest.mark.asyncio
async def test_collection_sanitizes_errors_and_records_real_model_ids():
    providers = {
        "bad": SimpleNamespace(list_models=AsyncMock(side_effect=RuntimeError("private credential"))),
        "good": SimpleNamespace(list_models=AsyncMock(return_value=[SimpleNamespace(id="model")])),
    }
    data = await collect_catalogs(providers)
    assert data["bad"] == {"status": "error", "error_type": "RuntimeError", "models": []}
    assert data["good"]["models"] == [{"id": "model", "capabilities": []}]


def test_gemini_standard_class_detects_new_generation_but_not_specialized_ids():
    result = audit_matrix_catalogs(matrices("gemini-[3-9]*-flash", "gemini"), {
        "gemini": catalog("gemini-3.8-flash", "gemini-10-flash",
                          "gemini-omni-100-flash", "gemini-100-flash-image")
    })
    assert result["issues"][0]["latest"] == "gemini-10-flash"