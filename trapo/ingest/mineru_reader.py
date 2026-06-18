from __future__ import annotations

import hashlib
import json
import importlib
import os
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.filesystem_safety import read_text_file
from trapo.ingest.options import DEFAULT_MINERU_PROCESSING_WINDOW_SIZE
from trapo.logging_filters import suppress_noisy_pdf_stderr


MAX_MINERU_ARTIFACT_BYTES = 100 * 1024 * 1024
MINERU_PROCESSING_WINDOW_ENV = "MINERU_PROCESSING_WINDOW_SIZE"


@dataclass(frozen=True)
class MinerUReadResult:
    text: str
    data: dict[str, Any]
    provider: str = "local-mineru"
    model: str = "mineru"


_MINERU_LOCK = threading.Lock()


def read_with_mineru(  # noqa: PLR0913
    path: Path,
    *,
    backend: str = "pipeline",
    parse_method: str = "auto",
    language: str = "en",
    formula_enable: bool = True,
    table_enable: bool = True,
    processing_window_size: int = DEFAULT_MINERU_PROCESSING_WINDOW_SIZE,
) -> MinerUReadResult:
    """Read a single PDF/image through local MinerU without a remote service."""
    results = read_with_mineru_batch(
        [path],
        backend=backend,
        parse_method=parse_method,
        language=language,
        formula_enable=formula_enable,
        table_enable=table_enable,
        processing_window_size=processing_window_size,
    )
    return next(iter(results.values()))


def read_with_mineru_batch(  # noqa: PLR0913
    paths: list[Path],
    *,
    backend: str = "pipeline",
    parse_method: str = "auto",
    language: str = "en",
    formula_enable: bool = True,
    table_enable: bool = True,
    processing_window_size: int = DEFAULT_MINERU_PROCESSING_WINDOW_SIZE,
) -> dict[Path, MinerUReadResult]:
    """Read multiple PDFs/images through local MinerU in one parse call."""
    if not paths:
        return {}

    if len(set(paths)) != len(paths):
        raise ValueError("read_with_mineru_batch expects unique file paths")

    try:
        common_module = importlib.import_module("mineru.cli.common")
        enum_module = importlib.import_module("mineru.utils.enum_class")
        suffix_module = importlib.import_module("mineru.utils.guess_suffix_or_lang")
    except Exception as exc:
        raise RuntimeError(_mineru_unavailable_message(exc)) from exc

    do_parse = common_module.do_parse
    read_fn = common_module.read_fn
    make_mode = enum_module.MakeMode
    guess_suffix_by_path = suffix_module.guess_suffix_by_path

    output_names = [
        _mineru_output_name(path, index) for index, path in enumerate(paths)
    ]
    files_bytes: list[bytes] = []
    for path in paths:
        suffix = guess_suffix_by_path(path)
        files_bytes.append(read_fn(path, suffix))

    with tempfile.TemporaryDirectory(prefix="trapo-mineru-") as temp_dir:
        output_dir = Path(temp_dir)
        # MinerU model objects are process-global and expensive to initialize.
        # Serialize local calls so concurrent ingest cannot duplicate weight loads.
        with _MINERU_LOCK, _mineru_processing_window(processing_window_size):
            do_parse(
                str(output_dir),
                output_names,
                files_bytes,
                [language] * len(paths),
                backend=backend,
                parse_method=parse_method,
                formula_enable=formula_enable,
                table_enable=table_enable,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_dump_md=True,
                f_dump_middle_json=True,
                f_dump_model_output=True,
                f_dump_orig_pdf=False,
                f_dump_content_list=True,
                f_make_md_mode=make_mode.MM_MD,
                image_analysis=True,
            )

        results: dict[Path, MinerUReadResult] = {}
        for path, output_name in zip(paths, output_names, strict=True):
            data = _collect_output(output_dir, output_name)
            data.update(
                {
                    "backend": backend,
                    "parse_method": parse_method,
                    "source": str(path),
                }
            )
            text = str(data.get("markdown") or "")
            results[path] = MinerUReadResult(
                text=text, data=data, model=f"mineru-{backend}"
            )
    return results


@contextmanager
def _mineru_processing_window(processing_window_size: int) -> Iterator[None]:
    previous = os.environ.get(MINERU_PROCESSING_WINDOW_ENV)
    os.environ[MINERU_PROCESSING_WINDOW_ENV] = str(max(1, processing_window_size))
    try:
        with suppress_noisy_pdf_stderr():
            yield
    finally:
        if previous is None:
            os.environ.pop(MINERU_PROCESSING_WINDOW_ENV, None)
        else:
            os.environ[MINERU_PROCESSING_WINDOW_ENV] = previous


def _collect_output(output_dir: Path, stem: str) -> dict[str, Any]:
    files = {
        "markdown": _read_text(output_dir, _first_match(output_dir, f"{stem}.md")),
        "middle_json": _read_json(
            output_dir, _first_match(output_dir, f"{stem}_middle.json")
        ),
        "model_json": _read_json(
            output_dir, _first_match(output_dir, f"{stem}_model.json")
        ),
        "content_list": _read_json(
            output_dir, _first_match(output_dir, f"{stem}_content_list.json")
        ),
        "content_list_v2": _read_json(
            output_dir, _first_match(output_dir, f"{stem}_content_list_v2.json")
        ),
    }
    return {key: value for key, value in files.items() if value is not None}


def _first_match(output_dir: Path, filename: str) -> Path | None:
    matches = sorted(output_dir.rglob(filename))
    return matches[0] if matches else None


def _read_text(output_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    return read_text_file(
        path,
        root=output_dir,
        max_bytes=MAX_MINERU_ARTIFACT_BYTES,
    )


def _read_json(output_dir: Path, path: Path | None) -> object | None:
    if path is None:
        return None
    content = read_text_file(
        path,
        root=output_dir,
        max_bytes=MAX_MINERU_ARTIFACT_BYTES,
    )
    return json.loads(content)


def _mineru_output_name(path: Path, index: int) -> str:
    stem = path.stem.strip() or "document"
    safe_stem = "".join(char if char.isalnum() else "_" for char in stem)
    safe_stem = safe_stem.strip("_") or "document"
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    return f"{safe_stem[:40]}_{index:04d}_{digest}"


def _mineru_unavailable_message(exc: Exception) -> str:
    version = ".".join(str(part) for part in sys.version_info[:3])
    reason = f"{type(exc).__name__}: {exc}"
    if sys.version_info >= (3, 14):
        return (
            "MinerU is not importable in the active Trapo Python environment. "
            f"Trapo is running Python {version}; this setup expects the local "
            "../MinerU path dependency to be patched for Python 3.14 and synced "
            "with uv. Run `uv sync`, confirm the local MinerU checkout is "
            f"available, then reprocess this file. Import failure: {reason}"
        )
    return (
        "MinerU is not importable in the active Trapo Python environment. Install "
        "local MinerU with the pipeline dependencies, then reprocess this file. "
        f"Import failure: {reason}"
    )
