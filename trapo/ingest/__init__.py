from __future__ import annotations

__all__ = ["IngestOptions", "ingest_directory"]


def __getattr__(name: str) -> object:
    if name in __all__:
        # Keep package import light; the pipeline imports Docling-facing modules.
        from trapo.ingest import pipeline  # noqa: PLC0415

        return getattr(pipeline, name)
    raise AttributeError(name)
