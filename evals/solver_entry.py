"""Credentialless solver process entry; stdin spec plus opaque IPC capability only."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import sys
from pathlib import Path

from anchors_adapter import AnchorsRun
from anchors_bridge import receiver_factory
from anchors_campaign import VERSION, load_sources
from anchors_transport import AnchorsLedger, Authority, Limits
from live_transport import canonical, require
from repair_assessor import strict_json


async def solve(
    spec, capability, *, root=Path("/work"), socket_path=Path("/ipc/controller.sock")
):
    require(
        type(spec) is dict
        and set(spec)
        == {
            "version",
            "campaign_id",
            "cell_id",
            "sources",
            "root_model",
            "worker_model",
            "root_effort",
            "worker_effort",
            "endpoint",
            "limits",
        }
        and spec["version"] == VERSION,
        "solver_spec",
    )
    require(type(capability) is str and 32 <= len(capability) <= 128, "ipc_capability")
    # This exact fresh env is also enforced by the parent's sandbox launcher.
    require(
        set(os.environ)
        <= {"PATH", "HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE", "LC_ALL"}
        and os.environ.get("LC_ALL") == "C.UTF-8",
        "solver_environment",
    )
    sources = load_sources(spec["sources"])
    sources.validate()
    sources.validate_runtime()
    limits = Limits(**spec["limits"])
    ledger = AnchorsLedger(
        root / "shadow-ledger", "shadow-" + spec["campaign_id"], limits
    )
    # The inherited adapter ledger requires A0. This is local shadow state only;
    # the IPC controller binds the real scheduled cell independently.
    ledger.start_cell("A0")
    if spec["cell_id"] != "A0":
        ledger.finish_cell("A0", {"instrumentation": "valid"})
        ledger.start_cell(spec["cell_id"])
    matrix = root / "matrix"
    matrix.mkdir(mode=0o700)
    run = AnchorsRun(
        sources,
        Authority(ledger, None, spec["endpoint"], True, True),
        root / "repo",
        matrix,
        spec["cell_id"],
        spec["root_model"],
        spec["worker_model"],
        spec["root_effort"],
        spec["worker_effort"],
        receiver_factory(socket_path, spec["campaign_id"], capability),
    )
    try:
        artifact = await run.run()
    finally:
        cleanup = await run.close()
    return {
        "version": VERSION,
        "artifact": {
            name: base64.b64encode(data).decode("ascii")
            for name, data in artifact.files
        },
        "binding": dict(artifact.binding),
        "resolution": run.resolution,
        "cleanup": cleanup,
    }


def main():
    os.umask(0o077)
    # No argv/env capability, root reply, provider config or framework logs.
    try:
        value = strict_json(sys.stdin.buffer.read(1_048_577), 1_048_576)
        require(
            type(value) is dict and set(value) == {"spec", "capability"}, "solver_input"
        )
        with open(os.devnull, "w") as sink:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                result = asyncio.run(solve(value["spec"], value["capability"]))
        raw = canonical(result)
        require(len(raw) <= 400_000, "solver_output")
        sys.stdout.buffer.write(raw)
        return 0
    except BaseException:
        sys.stderr.write('{"error":"solver_refused"}\n')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
