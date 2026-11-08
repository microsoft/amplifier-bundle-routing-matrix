"""The runtime source policy and the reproducible test lock serve different jobs."""
from pathlib import Path
import re
import tomllib

from amplifier_foundation import (
    is_glob_pattern,
    match_model_pattern,
    model_matches_pattern,
    model_pattern_sort_key,
    select_model_pattern,
)

MODULE = Path(__file__).resolve().parents[1] / "modules/hooks-routing"
URL = "https://github.com/microsoft/amplifier-foundation"


def test_runtime_tracks_foundation_main_without_a_global_source_override():
    metadata = tomllib.loads((MODULE / "pyproject.toml").read_text())
    requirements = [v for v in metadata["project"]["dependencies"]
                    if v.startswith("amplifier-foundation")]
    assert requirements == [f"amplifier-foundation @ git+{URL}@main"]
    assert "amplifier-foundation" not in metadata.get("tool", {}).get("uv", {}).get("sources", {})


def test_lock_records_exact_revision_without_changing_runtime_policy():
    lock = tomllib.loads((MODULE / "uv.lock").read_text())
    foundation = next(p for p in lock["package"] if p["name"] == "amplifier-foundation")
    assert re.fullmatch(re.escape(URL) + r"\?rev=main#[a-f0-9]{40}", foundation["source"]["git"])
    routing = next(p for p in lock["package"] if p["name"] == "amplifier-module-hooks-routing")
    requirement = next(r for r in routing["metadata"]["requires-dist"] if r["name"] == "amplifier-foundation")
    assert requirement["git"] == f"{URL}?rev=main"


def test_installed_foundation_has_required_public_api_not_only_shared_version():
    assert is_glob_pattern("MODEL-*")
    assert model_matches_pattern("Model-10", "MODEL-*")
    assert match_model_pattern("model-*", ["model-9", "Model-10"]) == ["Model-10", "model-9"]
    assert select_model_pattern("model-*", ["model-9", "Model-10"]) == "Model-10"
    assert model_pattern_sort_key("model-10") > model_pattern_sort_key("model-9")
