#!/usr/bin/env python3
"""Census of session lifecycle events across the committed capture corpus.

$0 -- reads only capture files that already exist. Answers three questions
model_performance-fde turns on:

1. How many ROOT sessions resume, and how many lifecycle legs ran with
   hooks-routing's session:start handler never invoked?
2. Do a resumed DELEGATE child's legs fire session:start (making 74w's fix
   live there) or session:resume (making it inert)?
3. Is `turn_count` a sound discriminator between the kernel's lifecycle
   session:resume and session_spawner.py:1763's observability emit?

Usage:
    python3 lifecycle_census.py <treatment-validation-dir>
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys


def main(root: str) -> int:
    base = pathlib.Path(root)
    if not base.is_dir():
        print(f"not a directory: {base}", file=sys.stderr)
        return 2

    stats: collections.Counter[str] = collections.Counter()
    shapes: collections.Counter[tuple[str, bool]] = collections.Counter()
    files = 0

    for f in base.rglob("events.jsonl"):
        # context-intelligence/ mirrors the same stream; counting both double-counts.
        if "context-intelligence" in f.parts:
            continue
        files += 1
        counts: collections.Counter[str] = collections.Counter()
        resume_payload_keys: list[list[str]] = []
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"session:' not in line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                t = e.get("event") or e.get("type") or e.get("event_type") or ""
                if not (isinstance(t, str) and t.startswith("session:")):
                    continue
                counts[t] += 1
                if t == "session:resume":
                    resume_payload_keys.append(sorted((e.get("data") or {}).keys()))
        if not counts:
            continue

        # A delegate child is the only session that forks into existence.
        kind = "delegate_child" if counts.get("session:fork") else "root"
        stats[f"{kind}_total"] += 1
        if counts.get("session:resume"):
            stats[f"{kind}_resumed"] += 1
        if kind == "root" and counts.get("session:resume"):
            stats["root_resumed_legs"] += counts.get("session:end", 0)
            stats["root_resumed_starts"] += counts.get("session:start", 0)
        for keys in resume_payload_keys:
            shapes[(kind, "turn_count" in keys)] += 1

    print(f"events.jsonl files scanned (excluding context-intelligence mirrors): {files}")
    print()
    print("--- Q1: root sessions ---")
    print(f"  root sessions                     : {stats['root_total']}")
    print(f"  ... that resumed at least once    : {stats['root_resumed']}")
    legs = stats["root_resumed_legs"]
    starts = stats["root_resumed_starts"]
    if legs:
        pct = 100.0 * (legs - starts) / legs
        print(f"  lifecycle legs across those       : {legs}")
        print(f"  legs that fired session:start     : {starts}")
        print(f"  legs with the handler NOT invoked : {legs - starts}  ({pct:.1f}%)")
    print()
    print("--- Q2: delegate children ---")
    print(f"  delegate child sessions           : {stats['delegate_child_total']}")
    print(f"  ... that resumed at least once    : {stats['delegate_child_resumed']}")
    print("  (their resumed legs fire fork -> resume -> START; see")
    print("   delegate-resume-order.txt for the verbatim ordering)")
    print()
    print("--- Q3: is `turn_count` a sound discriminator? ---")
    for (kind, has_tc), n in sorted(shapes.items()):
        print(f"  {kind:15s} session:resume with turn_count={str(has_tc):5s}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
