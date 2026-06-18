from __future__ import annotations

from pathlib import Path


def resolve_launch_path(path: str | Path, *, launch_dir: Path | None = None) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (launch_dir or Path.cwd()) / candidate
    return candidate.resolve(strict=False)


def resolve_source_root(path: str | Path, *, launch_dir: Path | None = None) -> Path:
    resolved = resolve_launch_path(path, launch_dir=launch_dir)
    if not resolved.exists():
        raise ValueError(f"Source root does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Source root is not a directory: {resolved}")
    return resolved
