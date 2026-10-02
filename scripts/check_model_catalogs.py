"""Thin catalog-only CLI. Install requested provider modules before running."""

import asyncio
import json
import logging
import os
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import click
import yaml

from amplifier_module_hooks_routing.catalog_audit import audit_matrix_catalogs, collect_catalogs


def make_provider(name):
    if name == "openai":
        from amplifier_module_provider_openai import OpenAIProvider
        return OpenAIProvider(os.environ.get("OPENAI_API_KEY", ""))
    if name == "anthropic":
        from amplifier_module_provider_anthropic import AnthropicProvider
        # Audit the full menu before the provider's lexical family prefilter.
        return AnthropicProvider(os.environ.get("ANTHROPIC_API_KEY", ""), config={"filtered": False})
    if name == "gemini":
        from amplifier_module_provider_gemini import GeminiProvider
        return GeminiProvider(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", ""))
    from amplifier_module_provider_github_copilot import GitHubCopilotProvider
    return GitHubCopilotProvider()


async def check(names, routing_dir):
    providers = {}
    catalogs = {}
    with ExitStack() as stack:
        if "github-copilot" in names:
            # A cached catalog cannot certify today's pin availability.
            stack.enter_context(patch(
                "amplifier_module_provider_github_copilot.provider.read_cache", return_value=None
            ))
            stack.enter_context(patch("amplifier_module_provider_github_copilot.provider.write_cache"))
        for name in names:
            try:
                providers[name] = make_provider(name)
            except Exception as error:
                catalogs[name] = {"status": "error", "error_type": type(error).__name__, "models": []}
        try:
            catalogs.update(await collect_catalogs(providers))
        finally:
            for provider in providers.values():
                try:
                    await asyncio.wait_for(provider.close(), 10)
                except Exception:
                    pass
    matrices = {p.stem: yaml.safe_load(p.read_text()) for p in routing_dir.glob("*.yaml")}
    if not matrices:
        raise click.ClickException("No routing matrices found")
    report = audit_matrix_catalogs(matrices, catalogs)
    # Public CI must not upload account-specific inventories or private new IDs.
    # Detailed comparisons remain in-memory; emit only repo-owned patterns.
    for issue in report["issues"]:
        issue.pop("selected", None)
        issue.pop("latest", None)
    report.update(
        observed_at=datetime.now(timezone.utc).isoformat(),
        coverage={name: {"status": data["status"], "count": len(data["models"])}
                  for name, data in catalogs.items()},
    )
    return report


@click.command()
@click.option("--provider", "providers", multiple=True, required=True,
              type=click.Choice(["openai", "anthropic", "gemini", "github-copilot"]))
@click.option("--routing-dir", type=click.Path(path_type=Path, file_okay=False, exists=True),
              default=Path(__file__).resolve().parents[1] / "routing")
def main(providers, routing_dir):
    """Fail on missing/stale candidates using fresh menus, without calling an LLM."""
    # Provider exception text can contain endpoints; expose sanitized JSON only.
    logging.disable(logging.CRITICAL)
    report = asyncio.run(check(tuple(dict.fromkeys(providers)), routing_dir))
    click.echo(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()