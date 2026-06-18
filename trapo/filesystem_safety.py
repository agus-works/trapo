from __future__ import annotations

import os
from pathlib import Path


def ensure_regular_file(
    path: Path,
    *,
    root: Path | None = None,
    max_bytes: int | None = None,
) -> Path:
    if path.is_symlink():
        raise ValueError(f"Refusing to read symlink: {path}")
    resolved = path.resolve(strict=True)
    if root is not None:
        resolved.relative_to(root.resolve(strict=True))
    if not resolved.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    if max_bytes is not None and resolved.stat().st_size > max_bytes:
        raise ValueError(f"Refusing to read oversized file: {path}")
    return resolved


def read_bytes_file(
    path: Path,
    *,
    root: Path | None = None,
    max_bytes: int | None = None,
) -> bytes:
    resolved = ensure_regular_file(path, root=root, max_bytes=max_bytes)
    limit = max_bytes + 1 if max_bytes is not None else -1
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(resolved, flags)
    with os.fdopen(fd, "rb") as handle:
        content = handle.read(limit)
    if max_bytes is not None and len(content) > max_bytes:
        raise ValueError(f"Refusing to read oversized file: {path}")
    return content


def read_text_file(
    path: Path,
    *,
    root: Path | None = None,
    max_bytes: int | None = None,
    encoding: str = "utf-8",
) -> str:
    return read_bytes_file(path, root=root, max_bytes=max_bytes).decode(encoding)


def write_bytes_file(
    path: Path,
    content: bytes,
    *,
    root: Path | None = None,
) -> Path:
    target = ensure_safe_output_file(path, root=root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o666)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    return target


def write_text_file(
    path: Path,
    content: str,
    *,
    root: Path | None = None,
    encoding: str = "utf-8",
) -> Path:
    return write_bytes_file(path, content.encode(encoding), root=root)


def ensure_safe_output_file(path: Path, *, root: Path | None = None) -> Path:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise ValueError(f"Refusing to write through symlink directory: {parent}")
    resolved_parent = parent.resolve(strict=True)
    if root is not None:
        resolved_parent.relative_to(root.resolve(strict=True))
    target = resolved_parent / path.name
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise ValueError(f"Refusing to overwrite unsafe path: {path}")
    return target
