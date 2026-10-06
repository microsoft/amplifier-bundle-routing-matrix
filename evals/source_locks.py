"""Inert source inventories, shared without importing task reference code."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from live_transport import fingerprint, require

SOURCE_LABELS = frozenset(
    {
        "core_native",
        "core_python",
        "foundation",
        "loop",
        "context",
        "provider",
        "shim",
        "routing",
        "sdk",
        "httpx",
        "task",
        "protocol",
        "assessor",
    }
)
TREE_LABELS = SOURCE_LABELS - {"core_native", "task"}


@dataclass(frozen=True)
class SourceLock:
    label: str
    path: Path
    sha256: str

    def validate(self):
        require(re.fullmatch(r"[0-9a-f]{64}", self.sha256) is not None, "source_digest")
        require(
            self.path.is_dir() if self.label in TREE_LABELS else self.path.is_file(),
            "source_inventory_shape",
        )
        require(source_digest(self.path) == self.sha256, "source_changed")


def source_digest(path: Path) -> str:
    """Bounded explicit executable inventory; never an ambient repository census."""
    require(path.resolve() == path and not path.is_symlink(), "source_symlink")
    if path.is_file():
        require(path.stat().st_size <= 1024 * 1024 * 1024, "source_inventory_size")
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    require(path.is_dir(), "source_directory")
    ignored = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".cache"}
    inventory = []
    total = 0
    for file in sorted(path.rglob("*")):
        rel = file.relative_to(path)
        if any(part in ignored for part in rel.parts):
            continue
        require(not file.is_symlink(), "source_symlink")
        if not file.is_file() or file.suffix in {".pyc", ".pyo"}:
            continue
        total += file.stat().st_size
        require(
            total <= 1024 * 1024 * 1024 and len(inventory) < 8192,
            "source_inventory_size",
        )
        with file.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory.append(
            {
                "path": rel.as_posix(),
                "sha256": digest,
            }
        )
    require(bool(inventory), "source_empty_inventory")
    return fingerprint(inventory)
