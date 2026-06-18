from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

import trapo.server
from trapo.annotation_report import (
    format_annotation_comparison_report,
    read_annotation_comparison_report,
)
from trapo.bootstrap import initialize_database
from trapo.config import (
    DEFAULT_DB_PATH,
    DEFAULT_SERVE_DB_PATH,
    DEFAULT_SERVE_HOST,
    DEFAULT_SERVE_PORT,
    DEFAULT_SOURCE_ROOT,
    RuntimeConfig,
)
from trapo.db import connect, is_quack_uri, table_exists
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    DEFAULT_LMSTUDIO_MODEL,
    DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE,
    DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE,
    DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
)
from trapo.ingest.lmstudio_profiles import DEFAULT_LMSTUDIO_PROFILE
from trapo.ingest.lmstudio_smoke import (
    SMOKE_RENDER_MAX_SIDE,
    default_smoke_options,
    run_lmstudio_smoke,
)
from trapo.ingest.page_markdown_images import (
    DEFAULT_PAGE_MARKDOWN_CACHE_ROOT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE,
    DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    DEFAULT_PAGE_MARKDOWN_RENDER_DPI,
)
from trapo.ingest.pipeline import IngestOptions, ingest_directory
from trapo.ingest.options import (
    DEFAULT_DOCLING_BATCH_SIZE,
    DEFAULT_DOCLING_QUEUE_MAX_SIZE,
    DEFAULT_MINERU_PROCESSING_WINDOW_SIZE,
)
from trapo.migrations import apply_migrations
from trapo.observability import configure_observability, traced_command
from trapo.page_orientation import (
    PageOrientationOverrideUpdate,
    normalize_clockwise_degrees,
    upsert_page_orientation_override,
)
from trapo.server.runtime import resolve_launch_path, resolve_source_root
from trapo.skylos_check import (
    DEFAULT_SKYLOS_REPORT_PATH,
    DEFAULT_SKYLOS_SARIF_PATH,
    SkylosCheckOptions,
    SkylosUnavailableError,
    run_skylos_check,
)
from trapo.status import DatabaseStatus, read_database_status

app = typer.Typer(
    help="Ingest documents with local Docling and search them through DuckDB.",
    pretty_exceptions_show_locals=False,
)
pipeline_app = typer.Typer(
    help="Run document ingestion phases.", pretty_exceptions_show_locals=False
)
app.add_typer(pipeline_app, name="pipeline")


@dataclass(frozen=True)
class IngestCommandOptions:
    db: str
    reprocess: bool
    chunker: str
    max_chunk_tokens: int
    max_chars: int
    overlap_chars: int
    docling_device: str
    docling_num_threads: int
    docling_page_batch_size: int
    docling_ocr_batch_size: int
    docling_layout_batch_size: int
    docling_table_batch_size: int
    docling_queue_max_size: int
    annotation_engines: str
    mineru_backend: str
    mineru_parse_method: str
    mineru_language: str
    mineru_processing_window_size: int
    lmstudio_base_url: str
    lmstudio_model: str
    lmstudio_timeout_seconds: float
    lmstudio_render_dpi: int
    lmstudio_image_max_side: int
    lmstudio_max_tokens: int
    lmstudio_box_origin: str
    lmstudio_include_evidence: bool
    lmstudio_profiles: str
    lmstudio_orientation: str
    lmstudio_orientation_min_confidence: float
    lmstudio_orientation_max_side: int
    lmstudio_orientation_max_tokens: int
    lmstudio_maximize_context: bool
    page_markdown: bool
    page_markdown_engines: str
    page_markdown_render_dpi: int
    page_markdown_image_max_side: int
    page_markdown_image_format: str
    page_markdown_jpeg_quality: int
    page_markdown_cache: bool
    page_markdown_cache_root: str
    page_markdown_max_tokens: int
    markitdown_lmstudio_ocr: bool
    markitdown_content_understanding: bool
    markitdown_cu_endpoint: str
    markitdown_cu_analyzer: str
    fuse_regions: bool
    fusion_profiles: str
    verbosity: int


def _config(db: str, *, source_root: str | None = None) -> RuntimeConfig:
    config = RuntimeConfig.from_env(db_path=db, source_root=source_root)
    configure_observability(config, warning_sink=typer.echo)
    return config


def _command_attributes(
    config: RuntimeConfig, **attributes: object
) -> dict[str, object]:
    command_attributes: dict[str, object] = {
        "db.path": config.db_path,
        "source.root": config.source_root,
        "otel.exporter": config.otel_exporter,
    }
    command_attributes.update(
        {key: value for key, value in attributes.items() if value is not None}
    )
    return command_attributes


def _print_database_status(status: DatabaseStatus) -> None:
    typer.echo(f"Database: {status.db_path}")
    if status.source_root:
        typer.echo(f"Source root: {status.source_root}")
    typer.echo(f"Schema version: {status.schema_version or 'unknown'}")
    typer.echo(f"Files: {status.files}")
    typer.echo(f"Chunks: {status.chunks}")
    typer.echo(f"Regions: {status.regions}")
    typer.echo(f"Terms: {status.terms}")
    typer.echo(f"Failed docs: {status.failed_docs}")


@app.command()
def init(
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
) -> None:
    """Create or upgrade a Trapo database."""
    config = _config(db)
    with traced_command("init", attributes=_command_attributes(config)):
        initialization = initialize_database(config)
        typer.echo(f"Database ready: {db}")
        for message in initialization.migration_messages:
            typer.echo(f"Migration note: {message}")


@app.command()
def migrate(
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
) -> None:
    """Apply pending schema migrations."""
    config = _config(db)
    with traced_command("migrate", attributes=_command_attributes(config)):
        with connect(config.db_path) as connection:
            messages = apply_migrations(connection, config)
        if not messages:
            typer.echo("No pending migrations.")
        for message in messages:
            typer.echo(f"Migration note: {message}")


@app.command()
def status(
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
) -> None:
    """Show database ingestion and search status."""
    config = _config(db)
    with traced_command("status", attributes=_command_attributes(config)):
        with connect(config.db_path) as connection:
            if not table_exists(connection, "app_metadata"):
                typer.echo("Database is not initialized. Run: trapo init")
                raise typer.Exit(code=1)
            apply_migrations(connection, config)
            _print_database_status(read_database_status(connection, config.db_path))


@app.command("set-page-rotation")
def set_page_rotation(
    file_hash: Annotated[str, typer.Argument(help="Document file hash to rotate.")],
    degrees: Annotated[
        int,
        typer.Argument(help="Clockwise page rotation: 0, 90, 180, or 270."),
    ],
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
    page: Annotated[int, typer.Option("--page", help="One-based page number.")] = 1,
) -> None:
    """Store a display rotation override for image preview pages and overlays."""
    config = _config(db)
    with traced_command(
        "set-page-rotation",
        attributes=_command_attributes(
            config,
            file_hash=file_hash,
            page=page,
            clockwise_degrees=degrees,
        ),
    ):
        try:
            normalized_degrees = normalize_clockwise_degrees(degrees)
            with connect(config.db_path) as connection:
                apply_migrations(connection, config)
                upsert_page_orientation_override(
                    connection,
                    override=PageOrientationOverrideUpdate(
                        file_hash=file_hash,
                        page_no=page,
                        clockwise_degrees=normalized_degrees,
                    ),
                )
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
    typer.echo(
        f"Page rotation stored: file_hash={file_hash} page={page} clockwise={normalized_degrees}"
    )


@app.command("annotation-report")
def annotation_report(
    file_hash: Annotated[str, typer.Argument(help="Document file hash to compare.")],
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
) -> None:
    """Compare stored annotation engines and profiles for one document."""
    config = _config(db)
    with traced_command(
        "annotation-report",
        attributes=_command_attributes(config, file_hash=file_hash),
    ):
        with connect(config.db_path) as connection:
            if not table_exists(connection, "app_metadata"):
                typer.echo("Database is not initialized. Run: trapo init")
                raise typer.Exit(code=1)
            apply_migrations(connection, config)
            report = read_annotation_comparison_report(connection, file_hash)
        if not report.engines:
            typer.echo(f"No annotation outputs found for file_hash={file_hash}")
            raise typer.Exit(code=1)
        typer.echo(format_annotation_comparison_report(report))


@app.command("lmstudio-smoke")
def lmstudio_smoke(  # noqa: PLR0913
    db: Annotated[
        str,
        typer.Option("--db", help="DuckDB path used for runtime configuration."),
    ] = DEFAULT_DB_PATH,
    lmstudio_base_url: Annotated[
        str,
        typer.Option(
            "--lmstudio-base-url", help="LM Studio OpenAI-compatible base URL."
        ),
    ] = DEFAULT_LMSTUDIO_BASE_URL,
    lmstudio_model: Annotated[
        str,
        typer.Option("--lmstudio-model", help="LM Studio vision model identifier."),
    ] = DEFAULT_LMSTUDIO_MODEL,
    lmstudio_timeout_seconds: Annotated[
        float,
        typer.Option(
            "--lmstudio-timeout", help="LM Studio smoke request timeout in seconds."
        ),
    ] = DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
    lmstudio_image_max_side: Annotated[
        int,
        typer.Option(
            "--lmstudio-image-max-side",
            help="Maximum synthetic page side sent to LM Studio.",
        ),
    ] = SMOKE_RENDER_MAX_SIDE,
    lmstudio_max_tokens: Annotated[
        int,
        typer.Option(
            "--lmstudio-max-tokens",
            help="Maximum LM Studio output tokens for the smoke page.",
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
) -> None:
    """Verify LM Studio connectivity and schema-valid bbox output."""
    config = _config(db)
    with traced_command(
        "lmstudio-smoke",
        attributes=_command_attributes(
            config,
            lmstudio_model=lmstudio_model,
            lmstudio_base_url=lmstudio_base_url,
        ),
    ):
        try:
            result = run_lmstudio_smoke(
                options=default_smoke_options(
                    base_url=lmstudio_base_url,
                    model=lmstudio_model,
                    timeout_seconds=lmstudio_timeout_seconds,
                    image_max_side=lmstudio_image_max_side,
                    max_tokens=lmstudio_max_tokens,
                )
            )
        except Exception as exc:
            typer.echo(f"LM Studio smoke failed: {exc}")
            raise typer.Exit(code=1) from exc
    typer.echo(
        "LM Studio smoke ok: "
        f"model={result.model} base_url={result.base_url} "
        f"regions={result.region_count} elapsed={result.elapsed_seconds:.2f}s "
        f"page_sha256={result.page_sha256}"
    )
    for region in result.regions:
        typer.echo(
            "  region: "
            f"kind={region.region_kind} label={region.label} "
            f"text={region.text!r} box_2d={region.box_2d} "
            f"confidence={region.confidence}"
        )


@app.command("skylos-check")
def skylos_check(  # noqa: PLR0913
    path: Annotated[
        Path, typer.Argument(help="Project path to scan with Skylos.")
    ] = Path("."),
    output: Annotated[
        Path,
        typer.Option("--output", help="JSON report path for Skylos findings."),
    ] = DEFAULT_SKYLOS_REPORT_PATH,
    sarif: Annotated[
        Path,
        typer.Option("--sarif", help="SARIF report path for code-scanning tools."),
    ] = DEFAULT_SKYLOS_SARIF_PATH,
    confidence: Annotated[
        int,
        typer.Option("--confidence", help="Minimum Skylos confidence threshold."),
    ] = 60,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict/--report-only",
            help="Fail when Skylos gate thresholds are exceeded.",
        ),
    ] = False,
    include_sca: Annotated[
        bool,
        typer.Option(
            "--sca/--no-sca",
            help="Include dependency vulnerability scanning in the Skylos run.",
        ),
    ] = True,
) -> None:
    """Run Trapo's comprehensive local Skylos audit."""
    try:
        result = run_skylos_check(
            SkylosCheckOptions(
                path=path,
                output=output,
                sarif=sarif,
                confidence=confidence,
                strict=strict,
                include_sca=include_sca,
            )
        )
    except SkylosUnavailableError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"Skylos report: {result.output}")
    typer.echo(f"Skylos SARIF: {result.sarif}")
    typer.echo(f"Skylos findings: {result.total_findings}")
    for category, count in sorted(result.counts.items()):
        if count:
            typer.echo(f"  {category}: {count}")

    if result.returncode != 0:
        if result.stderr.strip():
            typer.echo(result.stderr.strip())
        raise typer.Exit(code=result.returncode)


@app.command()
# Typer command handlers need explicit parameters so the CLI help stays complete.
def ingest(  # noqa: PLR0913
    directory: Annotated[Path, typer.Argument(help="Directory to scan recursively.")],
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess", help="Re-read files and replace chunks for known hashes."
        ),
    ] = False,
    chunker: Annotated[
        str,
        typer.Option("--chunker", help="Chunker strategy: docling-hybrid or chars."),
    ] = "docling-hybrid",
    max_chunk_tokens: Annotated[
        int,
        typer.Option(
            "--max-chunk-tokens",
            help="Approximate token budget for docling-hybrid chunks.",
        ),
    ] = 1200,
    max_chars: Annotated[
        int,
        typer.Option(
            "--max-chars", help="Maximum characters per chunk for the chars chunker."
        ),
    ] = 4000,
    overlap_chars: Annotated[
        int,
        typer.Option(
            "--overlap-chars", help="Overlapping characters between char chunks."
        ),
    ] = 400,
    docling_device: Annotated[
        str,
        typer.Option(
            "--docling-device",
            help="Docling accelerator: auto, cpu, cuda, cuda:N, mps, or xpu.",
        ),
    ] = "auto",
    docling_num_threads: Annotated[
        int,
        typer.Option(
            "--docling-num-threads",
            help="Docling CPU thread count for model inference.",
        ),
    ] = 4,
    docling_page_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-page-batch-size",
            help="Docling pages processed in one preprocessing batch.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_ocr_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-ocr-batch-size",
            help="Docling OCR stage batch size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_layout_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-layout-batch-size",
            help="Docling layout stage batch size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_table_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-table-batch-size",
            help="Docling table stage batch size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_queue_max_size: Annotated[
        int,
        typer.Option(
            "--docling-queue-max-size",
            help="Docling inter-stage queue limit for threaded PDF processing.",
        ),
    ] = DEFAULT_DOCLING_QUEUE_MAX_SIZE,
    annotation_engines: Annotated[
        str,
        typer.Option(
            "--annotation-engines",
            help="Comma-separated annotation engines: docling, mineru, lmstudio, or all.",
        ),
    ] = "docling,mineru",
    mineru_backend: Annotated[
        str,
        typer.Option("--mineru-backend", help="MinerU backend, for example pipeline."),
    ] = "pipeline",
    mineru_parse_method: Annotated[
        str,
        typer.Option("--mineru-method", help="MinerU parse method: auto, txt, or ocr."),
    ] = "auto",
    mineru_language: Annotated[
        str,
        typer.Option("--mineru-lang", help="MinerU OCR language hint."),
    ] = "en",
    mineru_processing_window_size: Annotated[
        int,
        typer.Option(
            "--mineru-processing-window-size",
            help="MinerU processing window size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_MINERU_PROCESSING_WINDOW_SIZE,
    lmstudio_base_url: Annotated[
        str,
        typer.Option(
            "--lmstudio-base-url", help="LM Studio OpenAI-compatible base URL."
        ),
    ] = "http://localhost:1234/v1",
    lmstudio_model: Annotated[
        str,
        typer.Option("--lmstudio-model", help="LM Studio vision model identifier."),
    ] = "google/gemma-4-26b-a4b-qat",
    lmstudio_timeout_seconds: Annotated[
        float,
        typer.Option(
            "--lmstudio-timeout", help="LM Studio per-page request timeout in seconds."
        ),
    ] = 240.0,
    lmstudio_render_dpi: Annotated[
        int,
        typer.Option(
            "--lmstudio-render-dpi", help="PDF render DPI for LM Studio page images."
        ),
    ] = 200,
    lmstudio_image_max_side: Annotated[
        int,
        typer.Option(
            "--lmstudio-image-max-side",
            help="Maximum rendered image side sent to LM Studio.",
        ),
    ] = 2048,
    lmstudio_max_tokens: Annotated[
        int,
        typer.Option(
            "--lmstudio-max-tokens", help="Maximum LM Studio output tokens per page."
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    lmstudio_box_origin: Annotated[
        str,
        typer.Option(
            "--lmstudio-box-origin",
            help="LM Studio y-axis origin for box_2d values: bottomleft or topleft.",
        ),
    ] = "bottomleft",
    lmstudio_include_evidence: Annotated[
        bool,
        typer.Option(
            "--lmstudio-evidence/--lmstudio-no-evidence",
            help="Include Docling/MinerU region hints in LM Studio page prompts.",
        ),
    ] = False,
    lmstudio_profiles: Annotated[
        str,
        typer.Option(
            "--lmstudio-profiles",
            help="Comma-separated LM Studio prompt profiles: balanced, strict, recall, or all.",
        ),
    ] = DEFAULT_LMSTUDIO_PROFILE,
    lmstudio_orientation: Annotated[
        str,
        typer.Option(
            "--lmstudio-orientation", help="Image orientation preflight: auto or off."
        ),
    ] = "auto",
    lmstudio_orientation_min_confidence: Annotated[
        float,
        typer.Option(
            "--lmstudio-orientation-min-confidence",
            help="Minimum confidence required to store an automatic rotation override.",
        ),
    ] = DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE,
    lmstudio_orientation_max_side: Annotated[
        int,
        typer.Option(
            "--lmstudio-orientation-max-side",
            help="Maximum rendered image side for LM Studio orientation preflight.",
        ),
    ] = DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE,
    lmstudio_orientation_max_tokens: Annotated[
        int,
        typer.Option(
            "--lmstudio-orientation-max-tokens",
            help="Maximum LM Studio output tokens for orientation preflight.",
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    lmstudio_maximize_context: Annotated[
        bool,
        typer.Option(
            "--lmstudio-max-context/--lmstudio-no-max-context",
            help="Best-effort load of the LM Studio model at its advertised maximum context before ingest.",
        ),
    ] = True,
    page_markdown: Annotated[
        bool,
        typer.Option(
            "--page-markdown/--no-page-markdown",
            help="Generate lightweight per-page Markdown.",
        ),
    ] = True,
    page_markdown_engines: Annotated[
        str,
        typer.Option(
            "--page-markdown-engines",
            help="Comma-separated Markdown generators: lmstudio_markdown, markitdown, markitdown_cu, or all.",
        ),
    ] = "markitdown",
    page_markdown_render_dpi: Annotated[
        int,
        typer.Option(
            "--page-markdown-render-dpi",
            help="PDF render DPI for page Markdown images.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_RENDER_DPI,
    page_markdown_image_max_side: Annotated[
        int,
        typer.Option(
            "--page-markdown-image-max-side",
            help="Maximum rendered page side sent to LM Studio for page Markdown.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE,
    page_markdown_image_format: Annotated[
        str,
        typer.Option(
            "--page-markdown-image-format",
            help="Prompt image format for page Markdown. Values other than JPEG are coerced to JPEG.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    page_markdown_jpeg_quality: Annotated[
        int,
        typer.Option(
            "--page-markdown-jpeg-quality",
            help="JPEG quality for page Markdown prompt images.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    page_markdown_cache: Annotated[
        bool,
        typer.Option(
            "--page-markdown-cache/--no-page-markdown-cache",
            help="Cache page Markdown prompt images under .cache for inspection and reuse.",
        ),
    ] = True,
    page_markdown_cache_root: Annotated[
        str,
        typer.Option(
            "--page-markdown-cache-root",
            help="Directory for cached page Markdown prompt images and metadata.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_CACHE_ROOT,
    page_markdown_max_tokens: Annotated[
        int,
        typer.Option(
            "--page-markdown-max-tokens",
            help=(
                "Maximum LM Studio output tokens for each generated Markdown page. "
                "The default auto-expands to the detected LM Studio context budget."
            ),
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    markitdown_lmstudio_ocr: Annotated[
        bool,
        typer.Option(
            "--markitdown-lmstudio-ocr/--no-markitdown-lmstudio-ocr",
            help="Give MarkItDown's OCR plugin the configured LM Studio vision model.",
        ),
    ] = False,
    markitdown_content_understanding: Annotated[
        bool,
        typer.Option(
            "--markitdown-cu/--no-markitdown-cu",
            help="Enable MarkItDown Azure Content Understanding when an endpoint is configured.",
        ),
    ] = False,
    markitdown_cu_endpoint: Annotated[
        str,
        typer.Option(
            "--markitdown-cu-endpoint",
            help="Azure Content Understanding endpoint for MarkItDown.",
        ),
    ] = "",
    markitdown_cu_analyzer: Annotated[
        str,
        typer.Option(
            "--markitdown-cu-analyzer",
            help="Optional Azure Content Understanding analyzer id.",
        ),
    ] = "",
    fuse_regions: Annotated[
        bool,
        typer.Option(
            "--fuse-regions/--no-fuse-regions",
            help="Build deterministic fused overlays from available annotation engines.",
        ),
    ] = True,
    fusion_profiles: Annotated[
        str,
        typer.Option(
            "--fusion-profiles",
            help="Comma-separated fusion profiles: conservative, balanced, recall, or all.",
        ),
    ] = "balanced",
    verbosity: Annotated[
        int,
        typer.Option(
            "--verbose",
            "-v",
            count=True,
            help="Increase verbosity. Use -v, -vv, or -vvv.",
        ),
    ] = 0,
) -> None:
    """Read files with local annotation engines and store chunks, regions, and terms."""
    _run_ingest(
        directory=directory,
        command_name="ingest",
        command_options=IngestCommandOptions(
            db=db,
            reprocess=reprocess,
            chunker=chunker,
            max_chunk_tokens=max_chunk_tokens,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            docling_device=docling_device,
            docling_num_threads=docling_num_threads,
            docling_page_batch_size=docling_page_batch_size,
            docling_ocr_batch_size=docling_ocr_batch_size,
            docling_layout_batch_size=docling_layout_batch_size,
            docling_table_batch_size=docling_table_batch_size,
            docling_queue_max_size=docling_queue_max_size,
            annotation_engines=annotation_engines,
            mineru_backend=mineru_backend,
            mineru_parse_method=mineru_parse_method,
            mineru_language=mineru_language,
            mineru_processing_window_size=mineru_processing_window_size,
            lmstudio_base_url=lmstudio_base_url,
            lmstudio_model=lmstudio_model,
            lmstudio_timeout_seconds=lmstudio_timeout_seconds,
            lmstudio_render_dpi=lmstudio_render_dpi,
            lmstudio_image_max_side=lmstudio_image_max_side,
            lmstudio_max_tokens=lmstudio_max_tokens,
            lmstudio_box_origin=lmstudio_box_origin,
            lmstudio_include_evidence=lmstudio_include_evidence,
            lmstudio_profiles=lmstudio_profiles,
            lmstudio_orientation=lmstudio_orientation,
            lmstudio_orientation_min_confidence=lmstudio_orientation_min_confidence,
            lmstudio_orientation_max_side=lmstudio_orientation_max_side,
            lmstudio_orientation_max_tokens=lmstudio_orientation_max_tokens,
            lmstudio_maximize_context=lmstudio_maximize_context,
            page_markdown=page_markdown,
            page_markdown_engines=page_markdown_engines,
            page_markdown_render_dpi=page_markdown_render_dpi,
            page_markdown_image_max_side=page_markdown_image_max_side,
            page_markdown_image_format=page_markdown_image_format,
            page_markdown_jpeg_quality=page_markdown_jpeg_quality,
            page_markdown_cache=page_markdown_cache,
            page_markdown_cache_root=page_markdown_cache_root,
            page_markdown_max_tokens=page_markdown_max_tokens,
            markitdown_lmstudio_ocr=markitdown_lmstudio_ocr,
            markitdown_content_understanding=markitdown_content_understanding,
            markitdown_cu_endpoint=markitdown_cu_endpoint,
            markitdown_cu_analyzer=markitdown_cu_analyzer,
            fuse_regions=fuse_regions,
            fusion_profiles=fusion_profiles,
            verbosity=verbosity,
        ),
    )


@pipeline_app.command("read")
@pipeline_app.command("docling")
# Typer command handlers need explicit parameters so the CLI help stays complete.
def pipeline_read(  # noqa: PLR0913
    directory: Annotated[Path, typer.Argument(help="Directory to scan recursively.")],
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_DB_PATH,
    reprocess: Annotated[
        bool,
        typer.Option(
            "--reprocess", help="Re-read files and replace chunks for known hashes."
        ),
    ] = False,
    chunker: Annotated[
        str,
        typer.Option("--chunker", help="Chunker strategy: docling-hybrid or chars."),
    ] = "docling-hybrid",
    max_chunk_tokens: Annotated[
        int,
        typer.Option(
            "--max-chunk-tokens",
            help="Approximate token budget for docling-hybrid chunks.",
        ),
    ] = 1200,
    max_chars: Annotated[
        int,
        typer.Option(
            "--max-chars", help="Maximum characters per chunk for the chars chunker."
        ),
    ] = 4000,
    overlap_chars: Annotated[
        int,
        typer.Option(
            "--overlap-chars", help="Overlapping characters between char chunks."
        ),
    ] = 400,
    docling_device: Annotated[
        str,
        typer.Option(
            "--docling-device",
            help="Docling accelerator: auto, cpu, cuda, cuda:N, mps, or xpu.",
        ),
    ] = "auto",
    docling_num_threads: Annotated[
        int,
        typer.Option(
            "--docling-num-threads",
            help="Docling CPU thread count for model inference.",
        ),
    ] = 4,
    docling_page_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-page-batch-size",
            help="Docling pages processed in one preprocessing batch.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_ocr_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-ocr-batch-size",
            help="Docling OCR stage batch size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_layout_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-layout-batch-size",
            help="Docling layout stage batch size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_table_batch_size: Annotated[
        int,
        typer.Option(
            "--docling-table-batch-size",
            help="Docling table stage batch size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_DOCLING_BATCH_SIZE,
    docling_queue_max_size: Annotated[
        int,
        typer.Option(
            "--docling-queue-max-size",
            help="Docling inter-stage queue limit for threaded PDF processing.",
        ),
    ] = DEFAULT_DOCLING_QUEUE_MAX_SIZE,
    annotation_engines: Annotated[
        str,
        typer.Option(
            "--annotation-engines",
            help="Comma-separated annotation engines: docling, mineru, lmstudio, or all.",
        ),
    ] = "docling,mineru",
    mineru_backend: Annotated[
        str,
        typer.Option("--mineru-backend", help="MinerU backend, for example pipeline."),
    ] = "pipeline",
    mineru_parse_method: Annotated[
        str,
        typer.Option("--mineru-method", help="MinerU parse method: auto, txt, or ocr."),
    ] = "auto",
    mineru_language: Annotated[
        str,
        typer.Option("--mineru-lang", help="MinerU OCR language hint."),
    ] = "en",
    mineru_processing_window_size: Annotated[
        int,
        typer.Option(
            "--mineru-processing-window-size",
            help="MinerU processing window size. Lower values reduce memory use.",
        ),
    ] = DEFAULT_MINERU_PROCESSING_WINDOW_SIZE,
    lmstudio_base_url: Annotated[
        str,
        typer.Option(
            "--lmstudio-base-url", help="LM Studio OpenAI-compatible base URL."
        ),
    ] = "http://localhost:1234/v1",
    lmstudio_model: Annotated[
        str,
        typer.Option("--lmstudio-model", help="LM Studio vision model identifier."),
    ] = "google/gemma-4-26b-a4b-qat",
    lmstudio_timeout_seconds: Annotated[
        float,
        typer.Option(
            "--lmstudio-timeout", help="LM Studio per-page request timeout in seconds."
        ),
    ] = 240.0,
    lmstudio_render_dpi: Annotated[
        int,
        typer.Option(
            "--lmstudio-render-dpi", help="PDF render DPI for LM Studio page images."
        ),
    ] = 200,
    lmstudio_image_max_side: Annotated[
        int,
        typer.Option(
            "--lmstudio-image-max-side",
            help="Maximum rendered image side sent to LM Studio.",
        ),
    ] = 2048,
    lmstudio_max_tokens: Annotated[
        int,
        typer.Option(
            "--lmstudio-max-tokens", help="Maximum LM Studio output tokens per page."
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    lmstudio_box_origin: Annotated[
        str,
        typer.Option(
            "--lmstudio-box-origin",
            help="LM Studio y-axis origin for box_2d values: bottomleft or topleft.",
        ),
    ] = "bottomleft",
    lmstudio_include_evidence: Annotated[
        bool,
        typer.Option(
            "--lmstudio-evidence/--lmstudio-no-evidence",
            help="Include Docling/MinerU region hints in LM Studio page prompts.",
        ),
    ] = True,
    lmstudio_profiles: Annotated[
        str,
        typer.Option(
            "--lmstudio-profiles",
            help="Comma-separated LM Studio prompt profiles: balanced, strict, recall, or all.",
        ),
    ] = DEFAULT_LMSTUDIO_PROFILE,
    lmstudio_orientation: Annotated[
        str,
        typer.Option(
            "--lmstudio-orientation", help="Image orientation preflight: auto or off."
        ),
    ] = "auto",
    lmstudio_orientation_min_confidence: Annotated[
        float,
        typer.Option(
            "--lmstudio-orientation-min-confidence",
            help="Minimum confidence required to store an automatic rotation override.",
        ),
    ] = DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE,
    lmstudio_orientation_max_side: Annotated[
        int,
        typer.Option(
            "--lmstudio-orientation-max-side",
            help="Maximum rendered image side for LM Studio orientation preflight.",
        ),
    ] = DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE,
    lmstudio_orientation_max_tokens: Annotated[
        int,
        typer.Option(
            "--lmstudio-orientation-max-tokens",
            help="Maximum LM Studio output tokens for orientation preflight.",
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    lmstudio_maximize_context: Annotated[
        bool,
        typer.Option(
            "--lmstudio-max-context/--lmstudio-no-max-context",
            help="Best-effort load of the LM Studio model at its advertised maximum context before ingest.",
        ),
    ] = True,
    page_markdown: Annotated[
        bool,
        typer.Option(
            "--page-markdown/--no-page-markdown",
            help="Generate lightweight per-page Markdown.",
        ),
    ] = True,
    page_markdown_engines: Annotated[
        str,
        typer.Option(
            "--page-markdown-engines",
            help="Comma-separated Markdown generators: lmstudio_markdown, markitdown, markitdown_cu, or all.",
        ),
    ] = "markitdown",
    page_markdown_render_dpi: Annotated[
        int,
        typer.Option(
            "--page-markdown-render-dpi",
            help="PDF render DPI for page Markdown images.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_RENDER_DPI,
    page_markdown_image_max_side: Annotated[
        int,
        typer.Option(
            "--page-markdown-image-max-side",
            help="Maximum rendered page side sent to LM Studio for page Markdown.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE,
    page_markdown_image_format: Annotated[
        str,
        typer.Option(
            "--page-markdown-image-format",
            help="Prompt image format for page Markdown. Values other than JPEG are coerced to JPEG.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    page_markdown_jpeg_quality: Annotated[
        int,
        typer.Option(
            "--page-markdown-jpeg-quality",
            help="JPEG quality for page Markdown prompt images.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    page_markdown_cache: Annotated[
        bool,
        typer.Option(
            "--page-markdown-cache/--no-page-markdown-cache",
            help="Cache page Markdown prompt images under .cache for inspection and reuse.",
        ),
    ] = True,
    page_markdown_cache_root: Annotated[
        str,
        typer.Option(
            "--page-markdown-cache-root",
            help="Directory for cached page Markdown prompt images and metadata.",
        ),
    ] = DEFAULT_PAGE_MARKDOWN_CACHE_ROOT,
    page_markdown_max_tokens: Annotated[
        int,
        typer.Option(
            "--page-markdown-max-tokens",
            help=(
                "Maximum LM Studio output tokens for each generated Markdown page. "
                "The default auto-expands to the detected LM Studio context budget."
            ),
        ),
    ] = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    markitdown_lmstudio_ocr: Annotated[
        bool,
        typer.Option(
            "--markitdown-lmstudio-ocr/--no-markitdown-lmstudio-ocr",
            help="Give MarkItDown's OCR plugin the configured LM Studio vision model.",
        ),
    ] = False,
    markitdown_content_understanding: Annotated[
        bool,
        typer.Option(
            "--markitdown-cu/--no-markitdown-cu",
            help="Enable MarkItDown Azure Content Understanding when an endpoint is configured.",
        ),
    ] = False,
    markitdown_cu_endpoint: Annotated[
        str,
        typer.Option(
            "--markitdown-cu-endpoint",
            help="Azure Content Understanding endpoint for MarkItDown.",
        ),
    ] = "",
    markitdown_cu_analyzer: Annotated[
        str,
        typer.Option(
            "--markitdown-cu-analyzer",
            help="Optional Azure Content Understanding analyzer id.",
        ),
    ] = "",
    fuse_regions: Annotated[
        bool,
        typer.Option(
            "--fuse-regions/--no-fuse-regions",
            help="Build deterministic fused overlays from available annotation engines.",
        ),
    ] = True,
    fusion_profiles: Annotated[
        str,
        typer.Option(
            "--fusion-profiles",
            help="Comma-separated fusion profiles: conservative, balanced, recall, or all.",
        ),
    ] = "balanced",
    verbosity: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity."),
    ] = 0,
) -> None:
    """Hash files, run local annotation engines, chunk, and build search regions."""
    _run_ingest(
        directory=directory,
        command_name="pipeline.read",
        command_options=IngestCommandOptions(
            db=db,
            reprocess=reprocess,
            chunker=chunker,
            max_chunk_tokens=max_chunk_tokens,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            docling_device=docling_device,
            docling_num_threads=docling_num_threads,
            docling_page_batch_size=docling_page_batch_size,
            docling_ocr_batch_size=docling_ocr_batch_size,
            docling_layout_batch_size=docling_layout_batch_size,
            docling_table_batch_size=docling_table_batch_size,
            docling_queue_max_size=docling_queue_max_size,
            annotation_engines=annotation_engines,
            mineru_backend=mineru_backend,
            mineru_parse_method=mineru_parse_method,
            mineru_language=mineru_language,
            mineru_processing_window_size=mineru_processing_window_size,
            lmstudio_base_url=lmstudio_base_url,
            lmstudio_model=lmstudio_model,
            lmstudio_timeout_seconds=lmstudio_timeout_seconds,
            lmstudio_render_dpi=lmstudio_render_dpi,
            lmstudio_image_max_side=lmstudio_image_max_side,
            lmstudio_max_tokens=lmstudio_max_tokens,
            lmstudio_box_origin=lmstudio_box_origin,
            lmstudio_include_evidence=lmstudio_include_evidence,
            lmstudio_profiles=lmstudio_profiles,
            lmstudio_orientation=lmstudio_orientation,
            lmstudio_orientation_min_confidence=lmstudio_orientation_min_confidence,
            lmstudio_orientation_max_side=lmstudio_orientation_max_side,
            lmstudio_orientation_max_tokens=lmstudio_orientation_max_tokens,
            lmstudio_maximize_context=lmstudio_maximize_context,
            page_markdown=page_markdown,
            page_markdown_engines=page_markdown_engines,
            page_markdown_render_dpi=page_markdown_render_dpi,
            page_markdown_image_max_side=page_markdown_image_max_side,
            page_markdown_image_format=page_markdown_image_format,
            page_markdown_jpeg_quality=page_markdown_jpeg_quality,
            page_markdown_cache=page_markdown_cache,
            page_markdown_cache_root=page_markdown_cache_root,
            page_markdown_max_tokens=page_markdown_max_tokens,
            markitdown_lmstudio_ocr=markitdown_lmstudio_ocr,
            markitdown_content_understanding=markitdown_content_understanding,
            markitdown_cu_endpoint=markitdown_cu_endpoint,
            markitdown_cu_analyzer=markitdown_cu_analyzer,
            fuse_regions=fuse_regions,
            fusion_profiles=fusion_profiles,
            verbosity=verbosity,
        ),
    )


def _run_ingest(
    *,
    directory: Path,
    command_name: str,
    command_options: IngestCommandOptions,
) -> None:
    config = _config(command_options.db)
    with traced_command(
        command_name,
        attributes=_command_attributes(
            config,
            source_directory=str(directory),
            reprocess=command_options.reprocess,
            chunker=command_options.chunker,
            docling_device=command_options.docling_device,
            docling_num_threads=command_options.docling_num_threads,
            docling_page_batch_size=command_options.docling_page_batch_size,
            docling_ocr_batch_size=command_options.docling_ocr_batch_size,
            docling_layout_batch_size=command_options.docling_layout_batch_size,
            docling_table_batch_size=command_options.docling_table_batch_size,
            docling_queue_max_size=command_options.docling_queue_max_size,
            annotation_engines=command_options.annotation_engines,
            mineru_backend=command_options.mineru_backend,
            mineru_parse_method=command_options.mineru_parse_method,
            mineru_processing_window_size=command_options.mineru_processing_window_size,
            lmstudio_model=command_options.lmstudio_model,
            lmstudio_base_url=command_options.lmstudio_base_url,
            lmstudio_box_origin=command_options.lmstudio_box_origin,
            lmstudio_profiles=command_options.lmstudio_profiles,
            lmstudio_orientation=command_options.lmstudio_orientation,
            lmstudio_maximize_context=command_options.lmstudio_maximize_context,
            page_markdown=command_options.page_markdown,
            page_markdown_engines=command_options.page_markdown_engines,
            page_markdown_render_dpi=command_options.page_markdown_render_dpi,
            page_markdown_image_max_side=command_options.page_markdown_image_max_side,
            page_markdown_image_format=command_options.page_markdown_image_format,
            page_markdown_jpeg_quality=command_options.page_markdown_jpeg_quality,
            page_markdown_cache=command_options.page_markdown_cache,
            page_markdown_cache_root=command_options.page_markdown_cache_root,
            markitdown_lmstudio_ocr=command_options.markitdown_lmstudio_ocr,
            markitdown_content_understanding=command_options.markitdown_content_understanding,
            fuse_regions=command_options.fuse_regions,
            fusion_profiles=command_options.fusion_profiles,
        ),
    ):
        initialize_database(config)
        options = IngestOptions(
            reprocess=command_options.reprocess,
            chunker=command_options.chunker,
            max_chunk_tokens=command_options.max_chunk_tokens,
            max_chars=command_options.max_chars,
            overlap_chars=command_options.overlap_chars,
            docling_device=command_options.docling_device,
            docling_num_threads=command_options.docling_num_threads,
            docling_page_batch_size=command_options.docling_page_batch_size,
            docling_ocr_batch_size=command_options.docling_ocr_batch_size,
            docling_layout_batch_size=command_options.docling_layout_batch_size,
            docling_table_batch_size=command_options.docling_table_batch_size,
            docling_queue_max_size=command_options.docling_queue_max_size,
            annotation_engines=command_options.annotation_engines,
            mineru_backend=command_options.mineru_backend,
            mineru_parse_method=command_options.mineru_parse_method,
            mineru_language=command_options.mineru_language,
            mineru_processing_window_size=command_options.mineru_processing_window_size,
            lmstudio_base_url=command_options.lmstudio_base_url,
            lmstudio_model=command_options.lmstudio_model,
            lmstudio_timeout_seconds=command_options.lmstudio_timeout_seconds,
            lmstudio_render_dpi=command_options.lmstudio_render_dpi,
            lmstudio_image_max_side=command_options.lmstudio_image_max_side,
            lmstudio_max_tokens=command_options.lmstudio_max_tokens,
            lmstudio_box_origin=command_options.lmstudio_box_origin,
            lmstudio_include_evidence=command_options.lmstudio_include_evidence,
            lmstudio_profiles=command_options.lmstudio_profiles,
            lmstudio_orientation=command_options.lmstudio_orientation,
            lmstudio_orientation_min_confidence=command_options.lmstudio_orientation_min_confidence,
            lmstudio_orientation_max_side=command_options.lmstudio_orientation_max_side,
            lmstudio_orientation_max_tokens=command_options.lmstudio_orientation_max_tokens,
            lmstudio_maximize_context=command_options.lmstudio_maximize_context,
            page_markdown=command_options.page_markdown,
            page_markdown_engines=command_options.page_markdown_engines,
            page_markdown_render_dpi=command_options.page_markdown_render_dpi,
            page_markdown_image_max_side=command_options.page_markdown_image_max_side,
            page_markdown_image_format=command_options.page_markdown_image_format,
            page_markdown_jpeg_quality=command_options.page_markdown_jpeg_quality,
            page_markdown_cache=command_options.page_markdown_cache,
            page_markdown_cache_root=command_options.page_markdown_cache_root,
            page_markdown_max_tokens=command_options.page_markdown_max_tokens,
            markitdown_lmstudio_ocr=command_options.markitdown_lmstudio_ocr,
            markitdown_content_understanding=command_options.markitdown_content_understanding,
            markitdown_cu_endpoint=command_options.markitdown_cu_endpoint,
            markitdown_cu_analyzer=command_options.markitdown_cu_analyzer,
            fuse_regions=command_options.fuse_regions,
            fusion_profiles=command_options.fusion_profiles,
            verbosity=command_options.verbosity,
        )
        with connect(config.db_path) as connection:
            try:
                summary = ingest_directory(connection, directory, config, options)
            except ValueError as exc:
                typer.echo(str(exc))
                raise typer.Exit(code=1) from exc
        typer.echo(
            "Ingest complete: "
            f"{summary.files_processed} processed, {summary.files_skipped} skipped, "
            f"{summary.chunks_created} chunks, {summary.errors} errors."
        )


@app.command()
def serve(
    db: Annotated[
        str, typer.Option("--db", help="Target DuckDB database file.")
    ] = DEFAULT_SERVE_DB_PATH,
    source_root: Annotated[
        Path,
        typer.Option("--src", help="Source root Trapo may read and preview."),
    ] = Path(DEFAULT_SOURCE_ROOT),
    host: Annotated[
        str, typer.Option("--host", help="Host interface to bind.")
    ] = DEFAULT_SERVE_HOST,
    port: Annotated[
        int, typer.Option("--port", help="HTTP port to bind.")
    ] = DEFAULT_SERVE_PORT,
    frontend_dir: Annotated[
        Path | None,
        typer.Option(
            "--frontend-dir",
            help="Built Vite frontend directory. Defaults to web/dist when present.",
        ),
    ] = None,
) -> None:
    """Run the local Trapo web API and UI."""
    launch_dir = Path.cwd()
    try:
        resolved_source_root = resolve_source_root(source_root, launch_dir=launch_dir)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    resolved_db_path = (
        db if is_quack_uri(db) else str(resolve_launch_path(db, launch_dir=launch_dir))
    )
    config = _config(resolved_db_path, source_root=str(resolved_source_root))
    with traced_command(
        "serve",
        attributes=_command_attributes(
            config,
            host=host,
            port=port,
            frontend_dir=str(frontend_dir) if frontend_dir is not None else None,
        ),
    ):
        initialization = initialize_database(config)
        static_dir = frontend_dir
        if static_dir is None:
            candidate = Path(__file__).resolve().parent.parent / "web" / "dist"
            static_dir = candidate if candidate.exists() else None
        if static_dir is None:
            typer.echo(
                "Frontend build not found; serving API only. Run `npm run build` in web/ first."
            )
        else:
            typer.echo(f"Serving frontend from {static_dir}")
        for message in initialization.migration_messages:
            typer.echo(f"Migration note: {message}")
        typer.echo(f"Source root: {resolved_source_root}")
        typer.echo(f"Database: {resolved_db_path}")
        typer.echo(f"Serving Trapo at http://{host}:{port}")
        app_instance = trapo.server.create_app(
            resolved_db_path,
            static_dir=static_dir,
            config=config,
            source_root=str(resolved_source_root),
        )
    uvicorn.run(app_instance, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
