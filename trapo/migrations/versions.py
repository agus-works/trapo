from __future__ import annotations

from trapo.db import DuckConnection
from trapo.migrations.runner import Migration, MigrationContext


def _create_ingest_diagnostics_tables(connection: DuckConnection) -> None:
    connection.execute("CREATE SEQUENCE IF NOT EXISTS diagnostic_event_id_seq START 1")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_diagnostic_spans (
            span_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            parent_span_id TEXT,
            ingest_run_id BIGINT,
            file_hash TEXT,
            page_no INTEGER,
            name TEXT NOT NULL,
            pipeline_step TEXT NOT NULL,
            category TEXT NOT NULL,
            annotation_engine TEXT,
            status TEXT NOT NULL,
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP NOT NULL,
            duration_ms DOUBLE NOT NULL,
            attributes_json JSON NOT NULL DEFAULT '{}'::JSON,
            error_type TEXT,
            error_message TEXT,
            error_stack TEXT,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_diagnostic_events (
            event_id BIGINT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            span_id TEXT,
            ingest_run_id BIGINT,
            file_hash TEXT,
            page_no INTEGER,
            timestamp TIMESTAMP NOT NULL,
            event_type TEXT NOT NULL,
            name TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT,
            attributes_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_diag_spans_run
        ON ingest_diagnostic_spans(ingest_run_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_diag_spans_file_page
        ON ingest_diagnostic_spans(file_hash, page_no)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_diag_spans_status
        ON ingest_diagnostic_spans(status)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_diag_spans_tree
        ON ingest_diagnostic_spans(trace_id, parent_span_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_diag_events_scope
        ON ingest_diagnostic_events(ingest_run_id, file_hash, page_no)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_diag_events_span
        ON ingest_diagnostic_events(span_id)
        """
    )


def initial_schema(connection: DuckConnection, context: MigrationContext) -> None:
    """Create the ingest and search schema.

    Trapo focuses on local Docling ingestion and document search. The schema
    stores raw Docling output, deterministic chunks, page regions with bounding
    boxes, and region-level terms used for full-text and word-level search.
    """
    connection.execute("CREATE SEQUENCE IF NOT EXISTS warning_id_seq START 1")
    connection.execute("CREATE SEQUENCE IF NOT EXISTS ingest_run_id_seq START 1")
    connection.execute("CREATE SEQUENCE IF NOT EXISTS chunk_id_seq START 1")
    connection.execute("CREATE SEQUENCE IF NOT EXISTS diagnostic_event_id_seq START 1")

    connection.execute(
        """
        CREATE TABLE app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    metadata = {
        "schema_version": "0001_ingest_search_schema",
    }
    for key, value in metadata.items():
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            [key, value],
        )

    connection.execute(
        """
        CREATE TABLE ingest_runs (
            ingest_run_id BIGINT PRIMARY KEY,
            source_directory TEXT NOT NULL,
            options_json JSON,
            started_at TIMESTAMP DEFAULT current_timestamp,
            finished_at TIMESTAMP,
            status TEXT NOT NULL,
            error TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE files (
            file_hash TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            extension TEXT,
            size_bytes BIGINT NOT NULL,
            modified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT current_timestamp,
            first_seen_at TIMESTAMP DEFAULT current_timestamp,
            last_seen_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE file_locations (
            file_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            first_seen_at TIMESTAMP DEFAULT current_timestamp,
            last_seen_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, path)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE docling_documents (
            file_hash TEXT PRIMARY KEY,
            ingest_run_id BIGINT NOT NULL,
            text TEXT,
            docling_json JSON,
            status TEXT NOT NULL,
            error TEXT,
            reader_provider TEXT,
            reader_model TEXT,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE ocr_documents (
            file_hash TEXT NOT NULL,
            annotation_engine TEXT NOT NULL,
            ingest_run_id BIGINT NOT NULL,
            text TEXT,
            output_json JSON,
            status TEXT NOT NULL,
            error TEXT,
            reader_provider TEXT,
            reader_model TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, annotation_engine)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE document_chunks (
            chunk_id BIGINT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            metadata_json JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (file_hash, chunk_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE document_regions (
            region_id TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            annotation_engine TEXT NOT NULL DEFAULT 'docling',
            annotation_provider TEXT NOT NULL DEFAULT 'local-docling',
            annotation_model TEXT NOT NULL DEFAULT 'docling',
            chunk_id BIGINT,
            chunk_index INTEGER,
            page_no INTEGER NOT NULL,
            source_ref TEXT,
            parent_ref TEXT,
            label TEXT,
            text TEXT NOT NULL,
            context_text TEXT,
            raw_bbox_json JSON NOT NULL,
            region_kind TEXT NOT NULL,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE document_terms (
            document_term_id UUID PRIMARY KEY,
            file_hash TEXT NOT NULL,
            page_no INTEGER,
            region_id TEXT,
            annotation_engine TEXT NOT NULL DEFAULT 'docling',
            chunk_id BIGINT,
            text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            bbox_json JSON,
            char_start INTEGER,
            char_end INTEGER,
            metadata_json JSON NOT NULL,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE annotation_visibility_overrides (
            file_hash TEXT NOT NULL,
            overlay_id TEXT NOT NULL,
            hidden BOOLEAN NOT NULL,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, overlay_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE annotation_style_settings (
            annotation_engine TEXT NOT NULL,
            region_kind TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            stroke_color TEXT NOT NULL,
            fill_color TEXT NOT NULL,
            stroke_opacity DOUBLE NOT NULL,
            fill_opacity DOUBLE NOT NULL,
            stroke_width DOUBLE NOT NULL,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (annotation_engine, region_kind, label)
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_locations_file_hash ON file_locations(file_hash)"
    )
    connection.execute(
        "CREATE INDEX idx_ocr_documents_file ON ocr_documents(file_hash)"
    )
    connection.execute(
        "CREATE INDEX idx_document_regions_file ON document_regions(file_hash)"
    )
    connection.execute(
        "CREATE INDEX idx_document_regions_engine ON document_regions(file_hash, annotation_engine)"
    )
    connection.execute(
        "CREATE INDEX idx_document_regions_chunk ON document_regions(chunk_id)"
    )
    connection.execute(
        "CREATE INDEX idx_document_terms_source ON document_terms(file_hash, page_no, region_id)"
    )
    connection.execute(
        "CREATE INDEX idx_document_terms_chunk ON document_terms(chunk_id)"
    )
    connection.execute(
        "CREATE INDEX idx_annotation_visibility_file ON annotation_visibility_overrides(file_hash)"
    )
    connection.execute(
        """
        CREATE TABLE page_orientation_overrides (
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            clockwise_degrees INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            confidence DOUBLE,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, page_no)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_page_orientation_file
        ON page_orientation_overrides(file_hash)
        """
    )
    connection.execute(
        """
        CREATE TABLE document_preview_images (
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            variant TEXT NOT NULL,
            page_width DOUBLE NOT NULL,
            page_height DOUBLE NOT NULL,
            render_width INTEGER NOT NULL,
            render_height INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            image_bytes BIGINT NOT NULL,
            image_sha256 TEXT NOT NULL,
            cache_path TEXT NOT NULL,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, page_no, variant)
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_preview_images_file ON document_preview_images(file_hash)"
    )
    _create_ingest_diagnostics_tables(connection)


def provider_annotation_schema(
    connection: DuckConnection, context: MigrationContext
) -> None:
    """Add provider-aware annotation storage and viewer preferences."""
    del context
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ocr_documents (
            file_hash TEXT NOT NULL,
            annotation_engine TEXT NOT NULL,
            ingest_run_id BIGINT NOT NULL,
            text TEXT,
            output_json JSON,
            status TEXT NOT NULL,
            error TEXT,
            reader_provider TEXT,
            reader_model TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, annotation_engine)
        )
        """
    )
    for column_sql in (
        "annotation_engine TEXT",
        "annotation_provider TEXT",
        "annotation_model TEXT",
        "metadata_json JSON",
    ):
        connection.execute(
            f"ALTER TABLE document_regions ADD COLUMN IF NOT EXISTS {column_sql}"
        )
    connection.execute(
        """
        UPDATE document_regions
        SET
            annotation_engine = coalesce(annotation_engine, 'docling'),
            annotation_provider = coalesce(annotation_provider, 'local-docling'),
            annotation_model = coalesce(annotation_model, 'docling'),
            metadata_json = coalesce(metadata_json, '{}'::JSON)
        """
    )
    connection.execute(
        "ALTER TABLE document_terms ADD COLUMN IF NOT EXISTS annotation_engine TEXT"
    )
    connection.execute(
        "UPDATE document_terms SET annotation_engine = coalesce(annotation_engine, 'docling')"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS annotation_visibility_overrides (
            file_hash TEXT NOT NULL,
            overlay_id TEXT NOT NULL,
            hidden BOOLEAN NOT NULL,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, overlay_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS annotation_style_settings (
            annotation_engine TEXT NOT NULL,
            region_kind TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            stroke_color TEXT NOT NULL,
            fill_color TEXT NOT NULL,
            stroke_opacity DOUBLE NOT NULL,
            fill_opacity DOUBLE NOT NULL,
            stroke_width DOUBLE NOT NULL,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (annotation_engine, region_kind, label)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ocr_documents_file ON ocr_documents(file_hash)"
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_regions_engine
        ON document_regions(file_hash, annotation_engine)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_annotation_visibility_file
        ON annotation_visibility_overrides(file_hash)
        """
    )
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0002_provider_annotation_schema', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


def page_orientation_schema(
    connection: DuckConnection, context: MigrationContext
) -> None:
    """Add page display rotation overrides for image previews and overlays."""
    del context
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_orientation_overrides (
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            clockwise_degrees INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            confidence DOUBLE,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, page_no)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_page_orientation_file
        ON page_orientation_overrides(file_hash)
        """
    )
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0003_page_orientation_overrides', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


def page_markdown_schema(connection: DuckConnection, context: MigrationContext) -> None:
    """Add per-page Markdown output and region span mapping storage."""
    del context
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_page_markdown (
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            markdown_engine TEXT NOT NULL,
            markdown_provider TEXT NOT NULL,
            markdown_model TEXT NOT NULL,
            markdown_text TEXT NOT NULL,
            page_width DOUBLE,
            page_height DOUBLE,
            render_sha256 TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, page_no, markdown_engine)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_page_markdown_regions (
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            markdown_engine TEXT NOT NULL,
            anchor_id TEXT NOT NULL,
            region_id TEXT NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            confidence DOUBLE,
            markdown_excerpt TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, page_no, markdown_engine, anchor_id, region_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_page_markdown_file
        ON document_page_markdown(file_hash)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_page_markdown_regions_region
        ON document_page_markdown_regions(file_hash, region_id)
        """
    )
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0004_page_markdown', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


def preview_image_cache_schema(
    connection: DuckConnection, context: MigrationContext
) -> None:
    """Add normalized preview image and thumbnail cache metadata."""
    del context
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_preview_images (
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            variant TEXT NOT NULL,
            page_width DOUBLE NOT NULL,
            page_height DOUBLE NOT NULL,
            render_width INTEGER NOT NULL,
            render_height INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            image_bytes BIGINT NOT NULL,
            image_sha256 TEXT NOT NULL,
            cache_path TEXT NOT NULL,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, page_no, variant)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_preview_images_file
        ON document_preview_images(file_hash)
        """
    )
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0005_preview_image_cache', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


def markdown_generator_status_schema(
    connection: DuckConnection, context: MigrationContext
) -> None:
    """Add per-file Markdown generator status metadata."""
    del context
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_markdown_generators (
            file_hash TEXT NOT NULL,
            markdown_engine TEXT NOT NULL,
            ingest_run_id BIGINT NOT NULL,
            markdown_provider TEXT NOT NULL,
            markdown_model TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            page_count INTEGER NOT NULL DEFAULT 0,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (file_hash, markdown_engine)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_markdown_generators_file
        ON document_markdown_generators(file_hash)
        """
    )
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0006_markdown_generator_status', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


def ingest_diagnostics_schema(
    connection: DuckConnection, context: MigrationContext
) -> None:
    """Add OTEL-shaped ingest diagnostics spans and events."""
    del context
    _create_ingest_diagnostics_tables(connection)
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0007_ingest_diagnostics', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


def ingest_work_planner_schema(
    connection: DuckConnection, context: MigrationContext
) -> None:
    """Add persisted ingest planning, artifact, and model lease state."""
    del context
    connection.execute("CREATE SEQUENCE IF NOT EXISTS ingest_work_unit_id_seq START 1")
    connection.execute(
        "CREATE SEQUENCE IF NOT EXISTS ingest_model_lease_id_seq START 1"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_work_units (
            work_unit_id BIGINT PRIMARY KEY,
            ingest_run_id BIGINT NOT NULL,
            work_key TEXT NOT NULL,
            file_hash TEXT,
            page_no INTEGER,
            phase TEXT NOT NULL,
            engine TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            profile TEXT,
            execution_key TEXT NOT NULL,
            artifact_variant TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            duration_ms DOUBLE,
            result_json JSON NOT NULL DEFAULT '{}'::JSON,
            error TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (ingest_run_id, work_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_page_artifacts (
            ingest_run_id BIGINT NOT NULL,
            file_hash TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            variant TEXT NOT NULL,
            page_width DOUBLE,
            page_height DOUBLE,
            render_width INTEGER NOT NULL,
            render_height INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            image_sha256 TEXT NOT NULL,
            cache_path TEXT,
            source_variant TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (ingest_run_id, file_hash, page_no, variant)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_model_leases (
            lease_id BIGINT PRIMARY KEY,
            ingest_run_id BIGINT NOT NULL,
            execution_key TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            requested_context_tokens INTEGER,
            verified_context_tokens INTEGER,
            status TEXT NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            duration_ms DOUBLE,
            error TEXT,
            metadata_json JSON NOT NULL DEFAULT '{}'::JSON,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_work_units_run_status
        ON ingest_work_units(ingest_run_id, status)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_work_units_scope
        ON ingest_work_units(ingest_run_id, file_hash, page_no)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_work_units_execution
        ON ingest_work_units(ingest_run_id, execution_key, phase)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_page_artifacts_scope
        ON ingest_page_artifacts(ingest_run_id, file_hash, page_no)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_model_leases_run
        ON ingest_model_leases(ingest_run_id, execution_key)
        """
    )
    connection.execute(
        """
        UPDATE app_metadata
        SET value = '0008_ingest_work_planner', updated_at = current_timestamp
        WHERE key = 'schema_version'
        """
    )


MIGRATIONS = [
    Migration(
        migration_id="0001_ingest_search_schema",
        description="Create Docling ingest and document search schema.",
        risky=False,
        warning=None,
        apply=initial_schema,
    ),
    Migration(
        migration_id="0002_provider_annotation_schema",
        description="Add provider-aware OCR documents, annotation styling, and visibility overrides.",
        risky=False,
        warning=None,
        apply=provider_annotation_schema,
    ),
    Migration(
        migration_id="0003_page_orientation_overrides",
        description="Add page display rotation overrides for image previews and overlays.",
        risky=False,
        warning=None,
        apply=page_orientation_schema,
    ),
    Migration(
        migration_id="0004_page_markdown",
        description="Add per-page Markdown output and region span mappings.",
        risky=False,
        warning=None,
        apply=page_markdown_schema,
    ),
    Migration(
        migration_id="0005_preview_image_cache",
        description="Add normalized preview image and thumbnail cache metadata.",
        risky=False,
        warning=None,
        apply=preview_image_cache_schema,
    ),
    Migration(
        migration_id="0006_markdown_generator_status",
        description="Add per-file Markdown generator status metadata.",
        risky=False,
        warning=None,
        apply=markdown_generator_status_schema,
    ),
    Migration(
        migration_id="0007_ingest_diagnostics",
        description="Add OTEL-shaped ingest diagnostics spans and events.",
        risky=False,
        warning=None,
        apply=ingest_diagnostics_schema,
    ),
    Migration(
        migration_id="0008_ingest_work_planner",
        description="Add persisted ingest work planning and model lease state.",
        risky=False,
        warning=None,
        apply=ingest_work_planner_schema,
    ),
]
