"""Thin offline Click wrapper; deliberately no run command."""

import json
from pathlib import Path

import click
import evidence
import yaml


def _inputs(command):
    command = click.option(
        "--benchmark-root",
        type=click.Path(path_type=Path, file_okay=False),
        required=True,
        help="Explicit local benchmark tasks directory; never fetched or discovered.",
    )(command)
    return click.argument("manifest", type=click.Path(path_type=Path, dir_okay=False))(
        command
    )


def _emit(manifest, benchmark_root, operation, evidence_path=None):
    try:
        run_plan = evidence.plan(evidence.read_json(manifest), benchmark_root)
        report = (
            run_plan
            if operation == "plan"
            else evidence.readiness(run_plan)
            if operation == "readiness"
            else evidence.analyze(run_plan, evidence.read_json(evidence_path))
        )
        click.echo(json.dumps(report, indent=2, allow_nan=False))
        if operation == "readiness" and not report["ready"]:
            raise click.exceptions.Exit(1)
    except (ValueError, OSError, yaml.YAMLError, TypeError) as error:
        # Do not echo paths, inputs or provider/secret-bearing exception text.
        click.echo(
            json.dumps(
                {
                    "error": "malformed_or_unreadable_inputs",
                    "error_type": type(error).__name__,
                }
            )
        )
        raise click.exceptions.Exit(2) from error


@click.group()
def main():
    """Offline planner/readiness/analyzer. Never launches a model or DTU."""


@main.command("plan")
@_inputs
def plan_command(manifest, benchmark_root):
    """Validate MANIFEST and print a reproducible schedule."""
    _emit(manifest, benchmark_root, "plan")


@main.command("readiness")
@_inputs
def readiness_command(manifest, benchmark_root):
    """Print validity separately from unsupported execution (exit 1)."""
    _emit(manifest, benchmark_root, "readiness")


@main.command("analyze")
@_inputs
@click.argument(
    "evidence_path", metavar="EVIDENCE", type=click.Path(path_type=Path, dir_okay=False)
)
def analyze_command(manifest, evidence_path, benchmark_root):
    """Reconcile a normalized JSON evidence array, not raw events."""
    _emit(manifest, benchmark_root, "analyze", evidence_path)


if __name__ == "__main__":
    main()
