from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr
from typing import TextIO


_TRANSFORMERS_ALIAS_PREFIX = "Accessing `"
_TRANSFORMERS_LAMBDA_ALIAS_FRAGMENT = "Returning `LambdaRuntimeClient` instead"
_TRANSFORMERS_ALIAS_REMOVAL_FRAGMENT = "this alias will be removed"
_PDF_FONTBBOX_FRAGMENT = (
    "Could not get FontBBox from font descriptor because None cannot be parsed "
    "as 4 floats"
)
_FILTER_INSTALLED = False


class TransformersLambdaAliasFilter(logging.Filter):
    """Drop noisy Transformers image-processor alias warnings."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith("transformers"):
            return True
        message = record.getMessage()
        return not (
            message.startswith(_TRANSFORMERS_ALIAS_PREFIX)
            and _TRANSFORMERS_LAMBDA_ALIAS_FRAGMENT in message
            and _TRANSFORMERS_ALIAS_REMOVAL_FRAGMENT in message
        )


class PdfFontBBoxFilter(logging.Filter):
    """Drop repeated malformed-PDF FontBBox warnings from PDF dependencies."""

    def filter(self, record: logging.LogRecord) -> bool:
        return _PDF_FONTBBOX_FRAGMENT not in record.getMessage()


class _FilteredStderr:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        filtered = "".join(
            line for line in text.splitlines(keepends=True) if _keep_stderr_line(line)
        )
        if filtered:
            try:
                self._stream.write(filtered)
            except OSError:
                return len(text)
        return len(text)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except OSError:
            return

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def _keep_stderr_line(line: str) -> bool:
    return _PDF_FONTBBOX_FRAGMENT not in line


@contextmanager
def suppress_noisy_pdf_stderr() -> Iterator[None]:
    """Filter known noisy PDF parser stderr without hiding other engine output."""
    with _suppress_noisy_pdf_stderr_fd():
        with redirect_stderr(_FilteredStderr(sys.stderr)):
            yield


@contextmanager
def _suppress_noisy_pdf_stderr_fd() -> Iterator[None]:
    try:
        saved_fd = os.dup(2)
        read_fd, write_fd = os.pipe()
    except OSError:
        yield
        return

    reader = threading.Thread(
        target=_forward_filtered_stderr,
        args=(read_fd, saved_fd),
        daemon=True,
    )
    try:
        reader.start()
        os.dup2(write_fd, 2)
        os.close(write_fd)
        yield
    finally:
        try:
            try:
                sys.stderr.flush()
            except OSError:
                pass
        finally:
            os.dup2(saved_fd, 2)
            reader.join(timeout=1.0)
            os.close(saved_fd)


def _forward_filtered_stderr(read_fd: int, target_fd: int) -> None:
    try:
        while chunk := os.read(read_fd, 8192):
            text = chunk.decode(errors="replace")
            filtered = "".join(
                line
                for line in text.splitlines(keepends=True)
                if _keep_stderr_line(line)
            )
            if filtered:
                os.write(target_fd, filtered.encode(errors="replace"))
    finally:
        os.close(read_fd)


def configure_third_party_logging() -> None:
    """Install targeted third-party log filters used by CLI and server startup."""
    global _FILTER_INSTALLED  # noqa: PLW0603
    if _FILTER_INSTALLED:
        return
    logging.getLogger("transformers").addFilter(TransformersLambdaAliasFilter())
    logging.getLogger().addFilter(PdfFontBBoxFilter())
    _FILTER_INSTALLED = True
