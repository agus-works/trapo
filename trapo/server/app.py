from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
import mimetypes
from pathlib import Path
import threading

from fastapi import Depends, FastAPI, HTTPException, status as http_status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from trapo.annotation.docling.regions import persisted_region_overlays
from trapo.annotation.mineru.regions import extract_mineru_pages
from trapo.annotation_settings import (
    read_annotation_settings,
    upsert_annotation_settings,
)
from trapo.assets import (
    image_page_info,
    image_preview_content,
    is_preview_path,
    media_type_for_path,
)
from trapo.bootstrap import initialize_database
from trapo.config import RuntimeConfig
from trapo.db import DuckConnection, open_connection, table_exists
from trapo.document_markdown import (
    BEST_AVAILABLE_MARKDOWN_ENGINE,
    MarkdownEngineStatus,
    PageMarkdown,
    read_document_markdown,
    read_document_markdown_engines,
)
from trapo.lmstudio_pages import extract_lmstudio_pages
from trapo.observability import instrument_fastapi_app
from trapo.page_orientation import read_page_rotation_degrees
from trapo.search import (
    CommandAction,
    CommandSearchResult,
    GlobalSearchResult,
    SearchHighlight,
    search_commands,
    search_global,
)
from trapo.server.diagnostics import diagnostic_runs, diagnostic_trace
from trapo.server.diagnostic_models import (
    DiagnosticRunRecord,
    DiagnosticTracePayload,
)
from trapo.server.models import (
    AnnotationSettingsPayload,
    AnnotationVisibilityResponse,
    AnnotationVisibilityUpdate,
    CommandActionRecord,
    CommandSearchResultRecord,
    DatabaseStatusResponse,
    DocumentDetail,
    DocumentMarkdownPayload,
    DocumentPreviewImagesPayload,
    DocumentRegionsPayload,
    DocumentSummary,
    GlobalSearchResultRecord,
    HealthResponse,
    MarkdownEngineRecord,
    MarkdownRegionSpan,
    PageInfo,
    PageMarkdownRecord,
    SearchHighlightRecord,
)
from trapo.server.preview_images import preview_image_for_file, preview_images_payload
from trapo.server.provenance import extract_pages
from trapo.status import read_database_status


@dataclass(frozen=True)
class DiagnosticTraceQuery:
    ingest_run_id: int | None = None
    file_hash: str | None = None
    page_no: int | None = None
    status: str | None = None
    q: str | None = None
    limit: int = 5000


def create_app(
    db_path: str | Path,
    *,
    static_dir: str | Path | None = None,
    config: RuntimeConfig | None = None,
    runtime_id: str | None = None,
    source_root: str | None = None,
) -> FastAPI:
    runtime_db_path = str(db_path)
    runtime_config = config or RuntimeConfig.from_env(db_path=runtime_db_path)
    initialize_database(runtime_config)
    db_connection = open_connection(runtime_config.db_path)
    db_lock = threading.RLock()
    effective_source_root = source_root or runtime_config.source_root
    enforced_source_root = (
        Path(effective_source_root).resolve()
        if source_root is not None or config is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            db_connection.close()

    app = FastAPI(title="Trapo", version="0.1.0", lifespan=lifespan)
    instrument_fastapi_app(app, runtime_config)
    app.state.db_connection = db_connection
    app.state.db_path = runtime_config.db_path
    app.state.db_lock = db_lock

    def connection() -> DuckConnection:
        return db_connection

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            db_path=runtime_config.db_path,
            runtime_id=runtime_id,
            source_root=effective_source_root,
        )

    @app.get("/api/status", response_model=DatabaseStatusResponse)
    def database_status() -> DatabaseStatusResponse:
        with db_lock:
            status = read_database_status(
                db_connection,
                runtime_config.db_path,
                runtime_id=runtime_id,
                source_root=effective_source_root,
            )
        return DatabaseStatusResponse(
            db_path=status.db_path,
            schema_version=status.schema_version,
            files=status.files,
            chunks=status.chunks,
            regions=status.regions,
            terms=status.terms,
            failed_docs=status.failed_docs,
            runtime_id=status.runtime_id,
            source_root=status.source_root,
        )

    @app.get("/api/commands/search", response_model=list[CommandSearchResultRecord])
    def command_search(
        q: str | None = None, limit: int = 20
    ) -> list[CommandSearchResultRecord]:
        return [
            _command_search_response(result)
            for result in search_commands(q, limit=limit)
        ]

    @app.get("/api/search", response_model=list[GlobalSearchResultRecord])
    def global_search(
        q: str | None = None, limit: int = 30
    ) -> list[GlobalSearchResultRecord]:
        with db_lock:
            results = search_global(db_connection, q, limit=limit)
        return [_global_search_response(result) for result in results]

    @app.get("/api/diagnostics/runs", response_model=list[DiagnosticRunRecord])
    def diagnostics_runs(
        limit: int = 50, con: DuckConnection = Depends(connection)
    ) -> list[DiagnosticRunRecord]:
        with db_lock:
            return diagnostic_runs(con, limit=limit)

    @app.get("/api/diagnostics/trace", response_model=DiagnosticTracePayload)
    def diagnostics_trace(
        params: DiagnosticTraceQuery = Depends(),
        con: DuckConnection = Depends(connection),
    ) -> DiagnosticTracePayload:
        with db_lock:
            return diagnostic_trace(
                con,
                ingest_run_id=params.ingest_run_id,
                file_hash=params.file_hash,
                page_no=params.page_no,
                status=params.status,
                q=params.q,
                limit=params.limit,
            )

    @app.get("/api/documents", response_model=list[DocumentSummary])
    def documents(con: DuckConnection = Depends(connection)) -> list[DocumentSummary]:
        with db_lock:
            return _document_summaries(con)

    @app.get("/api/documents/{file_hash}", response_model=DocumentDetail)
    def document(
        file_hash: str, con: DuckConnection = Depends(connection)
    ) -> DocumentDetail:
        with db_lock:
            return _document_detail(con, file_hash)

    @app.get(
        "/api/documents/{file_hash}/regions", response_model=DocumentRegionsPayload
    )
    def document_regions(
        file_hash: str, con: DuckConnection = Depends(connection)
    ) -> DocumentRegionsPayload:
        with db_lock:
            return _document_regions(con, file_hash)

    @app.get(
        "/api/documents/{file_hash}/markdown", response_model=DocumentMarkdownPayload
    )
    def document_markdown(
        file_hash: str,
        markdown_engine: str = BEST_AVAILABLE_MARKDOWN_ENGINE,
        page_no: int | None = None,
        con: DuckConnection = Depends(connection),
    ) -> DocumentMarkdownPayload:
        with db_lock:
            return _document_markdown(
                con,
                file_hash,
                markdown_engine=markdown_engine,
                page_no=page_no,
            )

    @app.get(
        "/api/documents/{file_hash}/preview-images",
        response_model=DocumentPreviewImagesPayload,
    )
    def document_preview_images(
        file_hash: str,
        con: DuckConnection = Depends(connection),
    ) -> DocumentPreviewImagesPayload:
        with db_lock:
            detail = _document_detail(con, file_hash)
            _, path = _document_asset_path(con, file_hash, enforced_source_root)
            return preview_images_payload(con, file_hash, detail, path)

    @app.get(
        "/api/documents/{file_hash}/preview-images/{variant}/{page_no}",
        response_model=None,
    )
    def document_preview_image(
        file_hash: str,
        variant: str,
        page_no: int,
        con: DuckConnection = Depends(connection),
    ) -> FileResponse:
        with db_lock:
            _, path = _document_asset_path(con, file_hash, enforced_source_root)
            image = preview_image_for_file(con, file_hash, variant, page_no, path)
        return FileResponse(
            image.cache_path,
            media_type=image.mime_type,
            filename=f"{file_hash}-{page_no}-{variant}.jpg",
        )

    @app.get("/api/annotation-settings", response_model=AnnotationSettingsPayload)
    def annotation_settings(
        con: DuckConnection = Depends(connection),
    ) -> AnnotationSettingsPayload:
        with db_lock:
            return AnnotationSettingsPayload(settings=read_annotation_settings(con))

    @app.put("/api/annotation-settings", response_model=AnnotationSettingsPayload)
    def update_annotation_settings(
        payload: AnnotationSettingsPayload,
        con: DuckConnection = Depends(connection),
    ) -> AnnotationSettingsPayload:
        with db_lock:
            upsert_annotation_settings(con, payload.settings)
            return AnnotationSettingsPayload(settings=read_annotation_settings(con))

    @app.put(
        "/api/documents/{file_hash}/annotations/visibility",
        response_model=AnnotationVisibilityResponse,
    )
    def update_annotation_visibility(
        file_hash: str,
        payload: AnnotationVisibilityUpdate,
        con: DuckConnection = Depends(connection),
    ) -> AnnotationVisibilityResponse:
        with db_lock:
            _document_summary(con, file_hash)
            updated = _update_annotation_visibility(con, file_hash, payload)
        return AnnotationVisibilityResponse(updated=updated)

    @app.get("/api/documents/{file_hash}/asset", response_model=None)
    def document_asset(
        file_hash: str, con: DuckConnection = Depends(connection)
    ) -> Response:
        with db_lock:
            filename, path = _document_asset_path(con, file_hash, enforced_source_root)
            rotation_degrees = read_page_rotation_degrees(con, file_hash, page_no=1)
        image_preview = image_preview_content(path, rotation_degrees=rotation_degrees)
        if image_preview is not None:
            return Response(
                content=image_preview.content, media_type=image_preview.media_type
            )
        return FileResponse(
            path, media_type=media_type_for_path(path), filename=filename
        )

    @app.get("/api/documents/{file_hash}/pdf")
    def document_pdf(
        file_hash: str, con: DuckConnection = Depends(connection)
    ) -> FileResponse:
        with db_lock:
            filename, path = _document_asset_path(con, file_hash, enforced_source_root)
        return FileResponse(
            path, media_type=media_type_for_path(path), filename=filename
        )

    if static_dir is not None:
        static_path = Path(static_dir)
        if static_path.exists():
            _register_static_asset_mime_types()
            app.mount("/", SpaStaticFiles(directory=static_path, html=True), name="web")

    return app


def _command_search_response(result: CommandSearchResult) -> CommandSearchResultRecord:
    return CommandSearchResultRecord(
        command_id=result.command_id,
        label=result.label,
        description=result.description,
        group=result.group,
        score=result.score,
        action=_command_action_response(result.action),
        highlights=[
            _search_highlight_response(highlight) for highlight in result.highlights
        ],
        shortcut=result.shortcut,
    )


def _command_action_response(action: CommandAction) -> CommandActionRecord:
    return CommandActionRecord(
        type=action.type,
        route=action.route,
        search=action.search,
    )


def _global_search_response(result: GlobalSearchResult) -> GlobalSearchResultRecord:
    return GlobalSearchResultRecord(
        result_id=result.result_id,
        source_type=result.source_type,
        source_id=result.source_id,
        label=result.label,
        snippet=result.snippet,
        route=result.route,
        score=result.score,
        rank_source=result.rank_source,
        navigation_granularity=result.navigation_granularity,
        highlights=[
            _search_highlight_response(highlight) for highlight in result.highlights
        ],
        file_hash=result.file_hash,
        chunk_id=result.chunk_id,
        region_id=result.region_id,
        page_no=result.page_no,
        word_id=result.word_id,
        char_start=result.char_start,
        char_end=result.char_end,
        metadata=result.metadata,
    )


def _search_highlight_response(highlight: SearchHighlight) -> SearchHighlightRecord:
    return SearchHighlightRecord(
        field=highlight.field,
        start=highlight.start,
        end=highlight.end,
        match_kind=highlight.match_kind,
        source=highlight.source,
        score_contribution=highlight.score_contribution,
    )


def _document_summaries(con: DuckConnection) -> list[DocumentSummary]:
    rows = con.execute(
        """
        SELECT
            f.file_hash,
            f.filename,
            f.extension,
            f.size_bytes,
            f.modified_at,
            f.created_at,
            any_value(l.path) AS path,
            any_value(d.status) AS docling_status,
            any_value(d.error) AS docling_error,
            (
                SELECT any_value(od.status)
                FROM ocr_documents od
                WHERE od.file_hash = f.file_hash
                  AND od.annotation_engine = 'mineru'
            ) AS mineru_status,
            (
                SELECT any_value(od.error)
                FROM ocr_documents od
                WHERE od.file_hash = f.file_hash
                  AND od.annotation_engine = 'mineru'
            ) AS mineru_error,
            (
                SELECT od.status
                FROM ocr_documents od
                WHERE od.file_hash = f.file_hash
                  AND (od.annotation_engine = 'lmstudio' OR od.annotation_engine LIKE 'lmstudio_%')
                ORDER BY CASE WHEN od.annotation_engine = 'lmstudio' THEN 0 ELSE 1 END,
                         od.annotation_engine
                LIMIT 1
            ) AS lmstudio_status,
            (
                SELECT od.error
                FROM ocr_documents od
                WHERE od.file_hash = f.file_hash
                  AND (od.annotation_engine = 'lmstudio' OR od.annotation_engine LIKE 'lmstudio_%')
                ORDER BY CASE WHEN od.annotation_engine = 'lmstudio' THEN 0 ELSE 1 END,
                         od.annotation_engine
                LIMIT 1
            ) AS lmstudio_error,
            (
                SELECT any_value(od.status)
                FROM ocr_documents od
                WHERE od.file_hash = f.file_hash
                  AND od.annotation_engine = 'fusion'
            ) AS fusion_status,
            (
                SELECT any_value(od.error)
                FROM ocr_documents od
                WHERE od.file_hash = f.file_hash
                  AND od.annotation_engine = 'fusion'
            ) AS fusion_error,
            (SELECT count(*) FROM document_chunks c WHERE c.file_hash = f.file_hash) AS chunk_count,
            (SELECT count(*) FROM document_regions r WHERE r.file_hash = f.file_hash) AS region_count
        FROM files f
        LEFT JOIN file_locations l ON l.file_hash = f.file_hash
        LEFT JOIN docling_documents d ON d.file_hash = f.file_hash
        GROUP BY f.file_hash, f.filename, f.extension, f.size_bytes, f.modified_at, f.created_at
        ORDER BY f.filename
        """
    ).fetchall()
    return [_summary_from_row(row) for row in rows]


def _summary_from_row(row: tuple[object, ...]) -> DocumentSummary:
    return DocumentSummary(
        file_hash=str(row[0]),
        filename=str(row[1]),
        extension=str(row[2]) if row[2] is not None else None,
        size_bytes=_int_value(row[3]),
        modified_at=_datetime_value(row[4]),
        created_at=_datetime_value(row[5]),
        path=str(row[6]) if row[6] is not None else None,
        docling_status=str(row[7]) if row[7] is not None else None,
        docling_error=str(row[8]) if row[8] is not None else None,
        mineru_status=str(row[9]) if row[9] is not None else None,
        mineru_error=str(row[10]) if row[10] is not None else None,
        lmstudio_status=str(row[11]) if row[11] is not None else None,
        lmstudio_error=str(row[12]) if row[12] is not None else None,
        fusion_status=str(row[13]) if row[13] is not None else None,
        fusion_error=str(row[14]) if row[14] is not None else None,
        chunk_count=_int_value(row[15]),
        region_count=_int_value(row[16]),
    )


def _document_summary(con: DuckConnection, file_hash: str) -> DocumentSummary:
    matches = [item for item in _document_summaries(con) if item.file_hash == file_hash]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Document not found: {file_hash}")
    return matches[0]


def _document_detail(con: DuckConnection, file_hash: str) -> DocumentDetail:
    summary = _document_summary(con, file_hash)
    pages = _image_preview_pages(con, summary)
    docling_json = con.execute(
        "SELECT docling_json FROM docling_documents WHERE file_hash = ?",
        [file_hash],
    ).fetchone()
    if not pages:
        pages = extract_pages(docling_json[0] if docling_json else None)
    if not pages and table_exists(con, "ocr_documents"):
        mineru_json = con.execute(
            """
            SELECT output_json
            FROM ocr_documents
            WHERE file_hash = ? AND annotation_engine = 'mineru' AND status = 'ok'
            """,
            [file_hash],
        ).fetchone()
        pages = extract_mineru_pages(mineru_json[0] if mineru_json else None)
    if not pages and table_exists(con, "ocr_documents"):
        lmstudio_json = con.execute(
            """
            SELECT output_json
            FROM ocr_documents
            WHERE file_hash = ?
              AND (annotation_engine = 'lmstudio' OR annotation_engine LIKE 'lmstudio_%')
              AND status = 'ok'
            ORDER BY CASE WHEN annotation_engine = 'lmstudio' THEN 0 ELSE 1 END,
                     annotation_engine
            LIMIT 1
            """,
            [file_hash],
        ).fetchone()
        pages = extract_lmstudio_pages(lmstudio_json[0] if lmstudio_json else None)
    return DocumentDetail(**summary.model_dump(), pages=pages)


def _image_preview_pages(
    con: DuckConnection, summary: DocumentSummary
) -> list[PageInfo]:
    if not summary.path:
        return []
    rotation_degrees = read_page_rotation_degrees(con, summary.file_hash, page_no=1)
    image_page = image_page_info(Path(summary.path), rotation_degrees=rotation_degrees)
    return [image_page] if image_page is not None else []


def _document_regions(con: DuckConnection, file_hash: str) -> DocumentRegionsPayload:
    detail = _document_detail(con, file_hash)
    pages_by_no = {page.page_no: page for page in detail.pages}
    overlays = persisted_region_overlays(con, file_hash, pages_by_no)
    return DocumentRegionsPayload(document=detail, overlays=overlays)


def _document_markdown(
    con: DuckConnection,
    file_hash: str,
    *,
    markdown_engine: str,
    page_no: int | None = None,
) -> DocumentMarkdownPayload:
    if page_no is not None and page_no <= 0:
        raise HTTPException(
            status_code=400, detail="Markdown page must be greater than zero."
        )
    detail = _document_detail(con, file_hash)
    pages = read_document_markdown(
        con,
        file_hash,
        markdown_engine=markdown_engine,
        page_no=page_no,
    )
    return DocumentMarkdownPayload(
        document=detail,
        markdown_engine=markdown_engine,
        available_engines=[
            _markdown_engine_response(engine)
            for engine in read_document_markdown_engines(con, file_hash)
        ],
        pages=[_page_markdown_response(page) for page in pages],
    )


def _markdown_engine_response(engine: MarkdownEngineStatus) -> MarkdownEngineRecord:
    return MarkdownEngineRecord(
        markdown_engine=engine.markdown_engine,
        label=engine.label,
        markdown_provider=engine.markdown_provider,
        markdown_model=engine.markdown_model,
        status=engine.status,
        error=engine.error,
        page_count=engine.page_count,
        is_virtual=engine.is_virtual,
        metadata=engine.metadata,
    )


def _page_markdown_response(page: PageMarkdown) -> PageMarkdownRecord:
    return PageMarkdownRecord(
        page_no=page.page_no,
        markdown_engine=page.markdown_engine,
        markdown_provider=page.markdown_provider,
        markdown_model=page.markdown_model,
        markdown_text=page.markdown_text,
        page_width=page.page_width,
        page_height=page.page_height,
        render_sha256=page.render_sha256,
        metadata=page.metadata,
        mappings=[
            MarkdownRegionSpan(
                anchor_id=mapping.anchor_id,
                region_id=mapping.region_id,
                char_start=mapping.char_start,
                char_end=mapping.char_end,
                confidence=mapping.confidence,
                markdown_excerpt=mapping.markdown_excerpt,
                metadata=mapping.metadata,
            )
            for mapping in page.mappings
        ],
    )


def _document_asset_path(
    con: DuckConnection, file_hash: str, source_root: Path | None
) -> tuple[str, Path]:
    row = con.execute(
        """
        SELECT f.filename, l.path
        FROM files f
        JOIN file_locations l ON l.file_hash = f.file_hash
        WHERE f.file_hash = ?
        ORDER BY l.last_seen_at DESC
        LIMIT 1
        """,
        [file_hash],
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Document not found: {file_hash}")
    path = Path(str(row[1]))
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Document asset path no longer exists: {path}"
        )
    _validate_document_asset_path(path, source_root)
    if not is_preview_path(path):
        raise HTTPException(
            status_code=415,
            detail=f"Document preview is not supported for: {path.suffix}",
        )
    return str(row[0]), path


def _validate_document_asset_path(path: Path, source_root: Path | None) -> None:
    if source_root is None:
        return
    if path.is_symlink():
        raise HTTPException(status_code=403, detail="Document asset path is a symlink.")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(source_root)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=403,
            detail="Document asset path is outside the configured source root.",
        ) from exc


def _update_annotation_visibility(
    con: DuckConnection,
    file_hash: str,
    payload: AnnotationVisibilityUpdate,
) -> int:
    if not table_exists(con, "annotation_visibility_overrides"):
        return 0
    updated = 0
    for override in payload.overrides:
        con.execute(
            """
            INSERT INTO annotation_visibility_overrides (file_hash, overlay_id, hidden)
            VALUES (?, ?, ?)
            ON CONFLICT (file_hash, overlay_id) DO UPDATE SET
                hidden = excluded.hidden,
                updated_at = now()
            """,
            [file_hash, override.overlay_id, override.hidden],
        )
        updated += 1
    return updated


def _int_value(value: object) -> int:
    result = 0
    if isinstance(value, bool | int | float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            result = 0
    return result


def _datetime_value(value: object) -> datetime | None:
    result = None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            result = None
    return result


def _register_static_asset_mime_types() -> None:
    mimetypes.add_type("text/javascript", ".mjs")


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if _is_api_static_path(path, scope):
            raise StarletteHTTPException(status_code=http_status.HTTP_404_NOT_FOUND)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if (
                exc.status_code == http_status.HTTP_404_NOT_FOUND
                and _should_serve_spa_index(path, scope)
            ):
                return await super().get_response("index.html", scope)
            raise


def _should_serve_spa_index(path: str, scope: Scope) -> bool:
    if scope.get("method") not in {"GET", "HEAD"}:
        return False
    normalized_path = path.strip("/")
    if not normalized_path or _is_api_static_path(path, scope):
        return False
    return Path(normalized_path).suffix == ""


def _is_api_static_path(path: str, scope: Scope) -> bool:
    normalized_path = path.strip("/")
    normalized_scope_path = str(scope.get("path", "")).strip("/")
    return normalized_path.startswith("api/") or normalized_scope_path.startswith(
        "api/"
    )
