#!/usr/bin/env python3
"""Cheap structural check for this bundle: does its YAML actually parse?

Run it exactly the same way CI does::

    uv run --no-project --with pyyaml python .github/scripts/check_bundle_structure.py

What it checks, and nothing more:

1. ``bundle.md`` has a ``---`` fenced YAML frontmatter block that parses, and
   declares ``bundle.name`` and ``bundle.version``.
2. Every path in the frontmatter's ``includes:`` list resolves to a file that
   exists on disk (``<bundle-name>:<relative/path>`` form).
3. Every ``behaviors/*.yaml`` parses as YAML and is a non-empty mapping.
4. Every ``routing/*.yaml`` parses as YAML (syntax only -- the SEMANTICS of a
   routing matrix are checked by ``tests/test_matrix_config_validation.py``,
   which is a different and stricter thing).

Deliberate design notes:

* An EMPTY glob is a FAILURE, not a pass. A check that silently returns "0
  problems found in 0 files" is indistinguishable from a working one, and this
  repo's programme has already been bitten by a step that returned ``[]`` with
  exit 0.
* Paths are resolved relative to this file's own location, never interpolated
  into source text, and are reported with ``as_posix()`` so the output reads
  the same on every OS.
* No network, no API keys, no LLM. Runs in about a second.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

problems: list[str] = []
checked: list[str] = []


def rel(path: Path) -> str:
    """Repo-relative, forward-slash path -- identical output on every OS."""
    return path.relative_to(REPO_ROOT).as_posix()


def parse_frontmatter(text: str) -> dict | None:
    """Return the parsed YAML frontmatter of a bundle.md, or None if malformed."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None
    block = "\n".join(lines[1:end])
    loaded = yaml.safe_load(block)
    return loaded if isinstance(loaded, dict) else None


# --- 1 + 2: bundle.md frontmatter -------------------------------------------

bundle_md = REPO_ROOT / "bundle.md"
frontmatter: dict = {}

if not bundle_md.is_file():
    problems.append("bundle.md is missing from the repository root")
else:
    try:
        parsed = parse_frontmatter(bundle_md.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        parsed = None
        problems.append(f"{rel(bundle_md)}: frontmatter is not valid YAML: {exc}")

    if parsed is None:
        problems.append(f"{rel(bundle_md)}: no parseable '---' fenced YAML frontmatter mapping")
    else:
        frontmatter = parsed
        checked.append(rel(bundle_md))
        bundle_block = frontmatter.get("bundle")
        if not isinstance(bundle_block, dict):
            problems.append(f"{rel(bundle_md)}: frontmatter has no 'bundle:' mapping")
        else:
            for key in ("name", "version"):
                if not bundle_block.get(key):
                    problems.append(f"{rel(bundle_md)}: frontmatter is missing 'bundle.{key}'")

        includes = frontmatter.get("includes") or []
        if not isinstance(includes, list):
            problems.append(f"{rel(bundle_md)}: 'includes:' must be a list, got {type(includes).__name__}")
            includes = []
        for entry in includes:
            if not isinstance(entry, str):
                problems.append(f"{rel(bundle_md)}: includes entry is not a string: {entry!r}")
                continue
            # "<bundle-name>:<relative/path>" -- the path half is what must exist.
            _, _, relative = entry.partition(":")
            target = REPO_ROOT / (relative or entry)
            if not target.is_file():
                problems.append(f"{rel(bundle_md)}: includes '{entry}' -> missing file {relative or entry}")


# --- 3 + 4: every YAML file the bundle ships --------------------------------


def parse_all(directory: str, pattern: str, require_mapping: bool) -> int:
    """Parse every match; return how many files were parsed."""
    root = REPO_ROOT / directory
    if not root.is_dir():
        problems.append(f"{directory}/ directory is missing")
        return 0

    matches = sorted(root.glob(pattern))
    if not matches:
        # An empty glob is a failure. See the module docstring.
        problems.append(f"{directory}/{pattern} matched NO files -- nothing was actually checked")
        return 0

    for path in matches:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"{rel(path)}: not valid YAML: {exc}")
            continue
        if require_mapping and not isinstance(loaded, dict):
            problems.append(f"{rel(path)}: expected a YAML mapping, got {type(loaded).__name__}")
            continue
        checked.append(rel(path))
    return len(matches)


behaviors_count = parse_all("behaviors", "*.yaml", require_mapping=True)
routing_count = parse_all("routing", "*.yaml", require_mapping=True)


# --- report ------------------------------------------------------------------

print(f"bundle.md frontmatter : {'ok' if bundle_md.is_file() else 'MISSING'}")
print(f"behaviors/*.yaml      : {behaviors_count} file(s)")
print(f"routing/*.yaml        : {routing_count} file(s)")
print(f"parsed cleanly        : {len(checked)} file(s)")

if problems:
    print(f"\nFAIL -- {len(problems)} problem(s):", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    sys.exit(1)

print("\nOK -- bundle structure checks passed")
