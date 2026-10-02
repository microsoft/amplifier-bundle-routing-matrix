"""Public CLI output must not expose private catalogs or SDK exception text."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import yaml
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "hooks-routing"))


def cli_module():
    spec = importlib.util.spec_from_file_location("catalog_cli", ROOT / "scripts/check_model_catalogs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_only_emits_repo_patterns_not_private_ids(tmp_path, monkeypatch):
    module = cli_module()
    path = tmp_path / "test.yaml"
    path.write_text(yaml.safe_dump({"roles": {"general": {"candidates": [
        {"provider": "openai", "model": "gpt-5.6-luna"},
    ]}}}))
    provider = SimpleNamespace(
        list_models=AsyncMock(return_value=[
            SimpleNamespace(id="gpt-5.6-luna", capabilities=[]),
            SimpleNamespace(id="gpt-99-luna", capabilities=[]),
            SimpleNamespace(id="private-project-model", capabilities=[]),
        ]),
        close=AsyncMock(),
    )
    monkeypatch.setattr(module, "make_provider", lambda name: provider)
    result = CliRunner().invoke(module.main, ["--provider", "openai", "--routing-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "stale_model" in result.output and "gpt-5.6-luna" in result.output
    assert "gpt-99-luna" not in result.output and "private-project-model" not in result.output


def test_cli_does_not_print_sensitive_error_body(tmp_path, monkeypatch):
    module = cli_module()
    (tmp_path / "test.yaml").write_text(yaml.safe_dump({"roles": {"general": {"candidates": [
        {"provider": "openai", "model": "gpt-6-luna"},
    ]}}}))
    provider = SimpleNamespace(
        list_models=AsyncMock(side_effect=RuntimeError("sensitive SDK exception body")),
        close=AsyncMock(),
    )
    monkeypatch.setattr(module, "make_provider", lambda name: provider)
    result = CliRunner().invoke(module.main, ["--provider", "openai", "--routing-dir", str(tmp_path)])
    assert result.exit_code == 1 and "catalog_unavailable" in result.output
    assert "sensitive SDK exception body" not in result.output