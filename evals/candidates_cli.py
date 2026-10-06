"""Thin saved-input-only subset CLI; no providers, credentials or configuration."""

import json
from pathlib import Path

import click

try:
    from . import candidates
except ImportError:  # Direct script invocation from any working directory.
    import candidates


@click.group()
def main():
    """Offline refresh subsets only. Never discovers a live catalog or executes."""


@main.command("subset")
@click.option("--snapshot", type=click.Path(path_type=Path), required=True)
@click.option("--receipts", type=click.Path(path_type=Path), required=True)
@click.option("--conditions", type=click.Path(path_type=Path), required=True)
@click.option("--incumbent", required=True, help="Exact incumbent model ID.")
def subset_command(snapshot, receipts, conditions, incumbent):
    """Read saved JSON, print fresh model subset/counts; no private envelope IDs."""
    try:
        report = candidates.plan_refresh(
            json.loads(snapshot.read_text(encoding="utf-8")),
            json.loads(receipts.read_text(encoding="utf-8")),
            json.loads(conditions.read_text(encoding="utf-8")),
            incumbent,
        )
        # No binding, endpoint, condition/config values or private receipt IDs.
        output = {
            "fresh_model_ids": report["fresh_model_ids"],
            "reuse_count": len(report["reuse_ids"]),
            "regrade_count": len(report["regrade_ids"]),
            "disposition_counts": {
                kind: sum(value == kind for value in report["dispositions"].values())
                for kind in candidates.DISPOSITIONS
            },
            "discovery_freshness": report["discovery_freshness"],
            "execution_supported": False,
        }
        click.echo(json.dumps(output, indent=2, allow_nan=False))
    except (ValueError, OSError, TypeError, AttributeError):
        click.echo(json.dumps({"error": "malformed_or_unreadable_inputs"}))
        raise click.exceptions.Exit(2) from None


if __name__ == "__main__":
    main()
