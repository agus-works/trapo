from __future__ import annotations

from pathlib import Path

from trapo.config import RuntimeConfig
from trapo.ingest.docling_reader import (
    DoclingReaderOptions,
    DoclingReadResult,
    read_with_docling,
)


def read_document(
    path: Path,
    config: RuntimeConfig,
    *,
    options: DoclingReaderOptions | None = None,
) -> DoclingReadResult:
    return read_with_docling(path, options=options)
