"""Thin parent Click entry. Trusted factory owns independent isolation acceptance."""

import asyncio
import importlib
import json

import click

from anchors_campaign import VERSION
from repair_assessor import strict_json


@click.group()
def main():
    """Private Anchors campaign, never a shipping routing-policy editor."""


@main.command()
@click.option(
    "--private-config", type=click.Path(exists=True, dir_okay=False), required=True
)
@click.option(
    "--parent-factory",
    required=True,
    help="Trusted installed module:function(config) -> awaitable report.",
)
def run(private_config, parent_factory):
    """Execute inside an existing parent DTU, with parent-owned selected config.

    Factory constructs Campaign, accepted BubblewrapSandbox, IsolatedAssessor
    and calls run_campaign. It may not accept solver-authored qualification.
    """
    try:
        with open(private_config, "rb") as stream:
            config = strict_json(stream.read(1_048_577), 1_048_576)
        module, name = parent_factory.split(":")
        factory = getattr(importlib.import_module(module), name)
        result = asyncio.run(factory(config))
        # Report is stored privately by library; stdout is a bounded status only.
        click.echo(
            json.dumps(
                {
                    "version": VERSION,
                    "cells": len(result["cells"]),
                    "complete": all(
                        c.get("instrumentation") == "valid" for c in result["cells"]
                    ),
                }
            )
        )
    except Exception:
        click.echo('{"error":"campaign_refused"}')
        raise click.exceptions.Exit(1) from None


if __name__ == "__main__":
    main()
