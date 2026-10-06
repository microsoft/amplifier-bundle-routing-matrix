"""Inert task staging and immutable snapshots; never import solver Python."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

TASK_VERSION = "interval-repair-v1"
GRADER_VERSION = "interval-repair-grader/v1"
TASK_DIRECTORY = Path(__file__).parent / "tasks" / TASK_VERSION
SOLVER_FILES = ("instructions.txt", "intervals.py", "test_public.py")
ARTIFACT_FILES = ("intervals.py", "test_public.py", "test_regression.py")
FILE_LIMITS = {
    "instructions.txt": 16_384,
    "intervals.py": 65_536,
    "test_public.py": 16_384,
    "test_regression.py": 65_536,
}
MAX_ARTIFACT_BYTES = 147_456


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def files_hash(files: tuple[tuple[str, bytes], ...]) -> str:
    return sha256(canonical_json({name: sha256(data) for name, data in files}))


@contextmanager
def _directory(path):
    """Open every ancestor without following links; pin the final directory fd."""
    if ".." in Path(path).parts:
        raise ValueError("parent traversal is not accepted")
    absolute = Path(os.path.abspath(os.fspath(path)))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _read_at(fd: int, name: str, limit: int) -> bytes:
    opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(opened)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("artifact must contain regular files without hardlinks")
        if not 0 < before.st_size <= limit:
            raise ValueError("file size outside limit")
        with os.fdopen(os.dup(opened), "rb") as stream:
            content = stream.read(limit + 1)
        after = os.fstat(opened)

        def identity(s):
            return s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

        if identity(before) != identity(after) or len(content) != before.st_size:
            raise ValueError("file changed during snapshot")
        return content
    finally:
        os.close(opened)


def _read_tree(path, names) -> tuple[tuple[str, bytes], ...]:
    try:
        with _directory(path) as fd:
            if set(os.listdir(fd)) != set(names):
                raise ValueError("missing or unknown task path")
            result = tuple(
                (name, _read_at(fd, name, FILE_LIMITS[name])) for name in sorted(names)
            )
            if set(os.listdir(fd)) != set(names):
                raise ValueError("tree changed during snapshot")
            return result
    except OSError:
        raise ValueError("unsafe or unreadable task tree") from None


# Only byte reads of authored sources; pin the import-time files so a long-lived
# controller cannot claim newer on-disk code as its own executed version.
_TASK_SOURCE = _read_tree(TASK_DIRECTORY, SOLVER_FILES)
BUGGY_SOURCE = dict(_TASK_SOURCE)["intervals.py"]
with _directory(Path(__file__).parent) as _fd:
    _GRADER_SOURCE = tuple(
        (name, _read_at(_fd, name, 262_144))
        for name in ("interval_repair.py", "repair_assessor.py")
    )


def source_binding() -> tuple[tuple[str, str], ...]:
    """Version and byte locks, not qualification or publication permission."""
    task = _read_tree(TASK_DIRECTORY, SOLVER_FILES)
    with _directory(Path(__file__).parent) as fd:
        grader = tuple(
            (name, _read_at(fd, name, 262_144))
            for name in ("interval_repair.py", "repair_assessor.py")
        )
    if task != _TASK_SOURCE or grader != _GRADER_SOURCE:
        raise ValueError("task/grader source changed since import")
    return tuple(
        sorted(
            {
                "task_version": TASK_VERSION,
                "grader_version": GRADER_VERSION,
                "task_sha256": files_hash(task),
                "grader_sha256": files_hash(grader),
            }.items()
        )
    )


@dataclass(frozen=True)
class Artifact:
    files: tuple[tuple[str, bytes], ...]
    binding: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if type(self.files) is not tuple or type(self.binding) is not tuple:
            raise ValueError("artifact must be immutable")
        if any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not bytes
            for item in self.files
        ):
            raise ValueError("artifact requires named immutable bytes")
        if tuple(name for name, _ in self.files) != ARTIFACT_FILES:
            raise ValueError("artifact paths must be exact and ordered")
        for name, data in self.files:
            if not 0 < len(data) <= FILE_LIMITS[name]:
                raise ValueError("artifact file size outside limit")
        if sum(len(data) for _, data in self.files) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact total size outside limit")
        if any(
            type(item) is not tuple
            or len(item) != 2
            or any(type(value) is not str for value in item)
            for item in self.binding
        ):
            raise ValueError("binding must be immutable strings")

    @property
    def sha256(self) -> str:
        return files_hash(self.files)


def stage_task(destination) -> tuple[tuple[str, str], ...]:
    """Create a NEW task directory containing exactly the three public files."""
    source = _read_tree(TASK_DIRECTORY, SOLVER_FILES)
    binding = source_binding()
    if files_hash(source) != dict(binding)["task_sha256"]:
        raise ValueError("task changed during staging")
    if ".." in Path(destination).parts:
        raise ValueError("parent traversal is not accepted")
    target = Path(os.path.abspath(os.fspath(destination)))
    created = False
    written = []
    try:
        with _directory(target.parent) as parent_fd:
            os.mkdir(target.name, mode=0o700, dir_fd=parent_fd)
            created = True
            fd = os.open(
                target.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                for name, data in source:
                    out = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=fd,
                    )
                    written.append(name)
                    with os.fdopen(out, "wb") as stream:
                        stream.write(data)
            except BaseException:
                for name in written:
                    os.unlink(name, dir_fd=fd)
                os.rmdir(target.name, dir_fd=parent_fd)
                raise
            finally:
                os.close(fd)
    except OSError:
        message = (
            "task staging failed" if created else "destination must be new and safe"
        )
        raise ValueError(message) from None
    return binding


def snapshot_artifact(
    directory, *, expected_binding: tuple[tuple[str, str], ...] | None = None
) -> Artifact:
    """Copy closed-path bytes; forbid changed public files and symlink ancestors."""
    binding = source_binding()
    if expected_binding is not None and binding != expected_binding:
        raise ValueError("task/grader source binding changed")
    all_files = _read_tree(directory, (*SOLVER_FILES, "test_regression.py"))
    public = dict(_read_tree(TASK_DIRECTORY, SOLVER_FILES))
    received = dict(all_files)
    for name in ("instructions.txt", "test_public.py"):
        if received[name] != public[name]:
            raise ValueError("protected public file changed")
    return Artifact(tuple((name, received[name]) for name in ARTIFACT_FILES), binding)
