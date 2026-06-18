from __future__ import annotations

import json
from typing import Any

from trapo.db import DuckConnection, table_exists


def record_ocr_success(  # noqa: PLR0913
    connection: DuckConnection,
    file_hash: str,
    run_id: int,
    *,
    annotation_engine: str,
    text: str,
    output_json: dict[str, Any],
    reader_provider: str,
    reader_model: str,
    metadata: dict[str, object],
) -> None:
    if not table_exists(connection, "ocr_documents"):
        return
    connection.execute(
        """
        INSERT INTO ocr_documents (
            file_hash, annotation_engine, ingest_run_id, text, output_json, status,
            error, reader_provider, reader_model, metadata_json
        )
        VALUES (?, ?, ?, ?, ?::JSON, 'ok', NULL, ?, ?, ?::JSON)
        ON CONFLICT (file_hash, annotation_engine) DO UPDATE SET
            ingest_run_id = excluded.ingest_run_id,
            text = excluded.text,
            output_json = excluded.output_json,
            status = excluded.status,
            error = excluded.error,
            reader_provider = excluded.reader_provider,
            reader_model = excluded.reader_model,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            file_hash,
            annotation_engine,
            run_id,
            text,
            json.dumps(output_json),
            reader_provider,
            reader_model,
            json.dumps(metadata),
        ],
    )


def record_ocr_error(  # noqa: PLR0913
    connection: DuckConnection,
    file_hash: str,
    run_id: int,
    *,
    annotation_engine: str,
    reader_provider: str,
    reader_model: str,
    exc: Exception,
) -> None:
    if not table_exists(connection, "ocr_documents"):
        return
    connection.execute(
        """
        INSERT INTO ocr_documents (
            file_hash, annotation_engine, ingest_run_id, text, output_json, status,
            error, reader_provider, reader_model, metadata_json
        )
        VALUES (?, ?, ?, NULL, NULL, 'error', ?, ?, ?, '{}'::JSON)
        ON CONFLICT (file_hash, annotation_engine) DO UPDATE SET
            ingest_run_id = excluded.ingest_run_id,
            text = excluded.text,
            output_json = excluded.output_json,
            status = excluded.status,
            error = excluded.error,
            reader_provider = excluded.reader_provider,
            reader_model = excluded.reader_model,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [file_hash, annotation_engine, run_id, str(exc), reader_provider, reader_model],
    )


def record_docling_error(
    connection: DuckConnection,
    file_hash: str,
    run_id: int,
    exc: Exception,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO docling_documents
            (
                file_hash, ingest_run_id, text, docling_json, status, error,
                reader_provider, reader_model
            )
        VALUES (?, ?, NULL, NULL, 'error', ?, 'local-docling', 'docling')
        """,
        [file_hash, run_id, str(exc)],
    )
    record_ocr_error(
        connection,
        file_hash,
        run_id,
        annotation_engine="docling",
        reader_provider="local-docling",
        reader_model="docling",
        exc=exc,
    )
