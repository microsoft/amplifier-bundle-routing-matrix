"""Thin Click entry point; independent qualification is required before spending."""

import asyncio
import os
from pathlib import Path

import click

from live_smoke import (
    CellSpec,
    Ledger,
    ROOT_MODEL,
    SmokeBlocked,
    canonical,
    load_campaign,
    preflight,
    prepare_output,
    report,
    require,
    run_cell,
)
from live_transport import AdmissionAuthority, STANDARD_ENDPOINT


@click.group()
def cli():
    pass


def emit(value):
    click.echo(canonical(value).decode())


def operation(name, spec_path, output_dir):
    try:
        spec = load_campaign(Path(spec_path))
    except (SmokeBlocked, OSError, ValueError, TypeError, KeyError):
        emit({"error": "invalid_smoke_input"})
        raise click.exceptions.Exit(2) from None
    try:
        output = prepare_output(spec, Path(output_dir))
        ledger = Ledger(output / "campaign.jsonl", spec.lock, spec.limits)
        if name == "report":
            emit(report(ledger))
            return
        readiness = preflight(spec)
        if name == "preflight":
            # Repeated preflight retains every observation without resetting cells.
            with ledger.transaction():
                ledger._append({"event": "preflight", "receipt": readiness})
            emit(readiness)
            if not readiness["ready"]:
                raise click.exceptions.Exit(1)
            return
        require(readiness["ready"], "preflight_blocked")
        require(
            any(
                e["event"] == "preflight" and e["receipt"]["ready"]
                for e in ledger.events()
            ),
            "preflight_receipt_required",
        )
        authority = AdmissionAuthority(
            ledger,
            spec.quote,
            STANDARD_ENDPOINT,
            spec.endpoint_qualified,
            spec.binding_qualified,
        )
        # Dedicated runtime-only input, not ambient OPENAI variables; never argv/logs.
        credential = os.environ.get("SMOKE_OPENAI_CREDENTIAL")
        require(
            isinstance(credential, str) and bool(credential),
            "credential_handle_missing",
        )
        cells = ("A0",) if name == "run-baseline" else spec.pair_order
        if name == "run-pair":
            events = ledger.events()
            require(
                any(
                    e["event"] == "cell_end"
                    and e["cell_id"] == "A0"
                    and e["receipt"]["instrumentation"] == "valid"
                    for e in events
                ),
                "baseline_acceptance_required",
            )
            require(
                not any(
                    e["event"] == "cell_start" and e["cell_id"] in cells for e in events
                ),
                "pair_once_only",
            )
        for cell in cells:
            receipt = asyncio.run(
                run_cell(
                    CellSpec(cell, "gpt-6-astra" if cell == "B1" else ROOT_MODEL),
                    authority,
                    output,
                    spec,
                    credential,
                )
            )
            if receipt.instrumentation != "valid":
                emit(report(ledger))
                raise click.exceptions.Exit(1)
        emit(report(ledger))
    except SmokeBlocked as exc:
        emit({"error": str(exc), "status": "blocked"})
        raise click.exceptions.Exit(1) from None
    except (OSError, ValueError, TypeError, KeyError):
        emit({"error": "invalid_smoke_input"})
        raise click.exceptions.Exit(2) from None


def command(name):
    @cli.command(name)
    @click.option("--spec", "spec_path", required=True, type=click.Path())
    @click.option("--output-dir", required=True, type=click.Path())
    def invoke(spec_path, output_dir):
        operation(name, spec_path, output_dir)


for _name in ("preflight", "run-baseline", "run-pair", "report"):
    command(_name)


if __name__ == "__main__":
    cli()
