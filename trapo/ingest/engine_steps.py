from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trapo.annotation.infinity.regions import rebuild_infinity_document_regions
from trapo.annotation.fusion import FUSION_MODEL, FUSION_PROVIDER
from trapo.annotation.fusion.profiles import FusionProfile, requested_fusion_profiles
from trapo.annotation.fusion.regions import rebuild_fused_document_regions
from trapo.annotation.lmstudio.regions import rebuild_lmstudio_document_regions
from trapo.annotation.mineru.regions import rebuild_mineru_document_regions
from trapo.db import DuckConnection, table_exists
from trapo.ingest.lmstudio_evidence import lmstudio_evidence_by_page
from trapo.ingest.infinity_models import (
    INFINITY_ENGINE,
    InfinityOptions,
)
from trapo.ingest.infinity_reader import read_regions_with_infinity
from trapo.ingest.lmstudio_models import LmStudioOptions
from trapo.ingest.lmstudio_profiles import (
    LmStudioProfileRunSummary,
    LmStudioPromptProfile,
    requested_lmstudio_profiles,
)
from trapo.ingest.lmstudio_reader import read_with_lmstudio
from trapo.ingest.mineru_reader import read_with_mineru
from trapo.ingest.normalized_pages import normalized_metadata, normalized_preview_pages
from trapo.ingest.ocr_storage import record_ocr_error, record_ocr_success
from trapo.ingest.options import IngestOptions
from trapo.ingest.target_pages import (
    image_rotation_degrees_by_page,
    target_pages_for_regions,
)
from trapo.observability import span_set_attributes, traced_span


def process_mineru(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    log(
        "Reading with MinerU: "
        f"{path} backend={options.mineru_backend} "
        f"method={options.mineru_parse_method} "
        f"window={options.mineru_processing_window_size}"
    )
    with traced_span(
        "trapo.ingest.mineru_read",
        attributes={
            "file.hash": file_hash,
            "mineru.backend": options.mineru_backend,
            "mineru.parse_method": options.mineru_parse_method,
            "mineru.processing_window_size": options.mineru_processing_window_size,
        },
    ):
        read_result = read_with_mineru(
            path,
            backend=options.mineru_backend,
            parse_method=options.mineru_parse_method,
            language=options.mineru_language,
            formula_enable=True,
            table_enable=True,
            processing_window_size=options.mineru_processing_window_size,
        )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine="mineru",
        text=read_result.text,
        output_json=read_result.data,
        reader_provider=read_result.provider,
        reader_model=read_result.model,
        metadata={
            "backend": options.mineru_backend,
            "parse_method": options.mineru_parse_method,
            "language": options.mineru_language,
            "processing_window_size": options.mineru_processing_window_size,
        },
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={"file.hash": file_hash, "annotation.engine": "mineru"},
    ) as region_span:
        region_count = rebuild_mineru_document_regions(
            connection,
            file_hash,
            read_result.data,
            target_pages=target_pages_for_regions(connection, path, file_hash),
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored MinerU: regions={region_count}")
    return region_count


def process_infinity(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    with traced_span(
        "trapo.ingest.normalized_pages",
        attributes={"file.hash": file_hash, "annotation.engine": INFINITY_ENGINE},
    ) as pages_span:
        pages = normalized_preview_pages(connection, path, file_hash, log)
        span_set_attributes(pages_span, {"page.count": len(pages)})
    if not pages:
        raise ValueError(f"No normalized preview pages were rendered for: {path}")
    log(
        "Reading normalized JPGs with Infinity Parser2: "
        f"{path} pages={len(pages)} model={options.infinity_model} "
        f"backend={options.infinity_backend}"
    )
    infinity_options = InfinityOptions(
        model=options.infinity_model,
        backend=options.infinity_backend,
        batch_size=options.infinity_batch_size,
        device=options.infinity_device,
        torch_dtype=options.infinity_torch_dtype,
    )
    with traced_span(
        "trapo.ingest.infinity_read",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": INFINITY_ENGINE,
            "page.count": len(pages),
            "infinity.model": options.infinity_model,
            "infinity.backend": options.infinity_backend,
            "infinity.batch_size": options.infinity_batch_size,
        },
    ):
        read_result = read_regions_with_infinity(
            pages,
            source_path=path,
            options=infinity_options,
            log=log,
        )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine=INFINITY_ENGINE,
        text=read_result.text,
        output_json=read_result.data,
        reader_provider=read_result.provider,
        reader_model=read_result.model,
        metadata={
            **normalized_metadata(pages),
            "model": options.infinity_model,
            "backend": options.infinity_backend,
            "batch_size": options.infinity_batch_size,
            "device": options.infinity_device,
            "torch_dtype": options.infinity_torch_dtype,
            "page_error_count": read_result.data.get("page_error_count", 0),
        },
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={"file.hash": file_hash, "annotation.engine": INFINITY_ENGINE},
    ) as region_span:
        region_count = rebuild_infinity_document_regions(
            connection,
            file_hash,
            read_result.data,
            annotation_model=options.infinity_model,
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored Infinity Parser2: pages={len(pages)} regions={region_count}")
    return region_count


def process_lmstudio_profiles(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> LmStudioProfileRunSummary:
    region_count = 0
    error_count = 0
    for profile in requested_lmstudio_profiles(options.lmstudio_profiles):
        try:
            region_count += process_lmstudio(
                connection,
                path,
                file_hash,
                run_id,
                options,
                profile,
                log,
            )
        except Exception as exc:
            error_count += 1
            record_ocr_error(
                connection,
                file_hash,
                run_id,
                annotation_engine=profile.annotation_engine,
                reader_provider="local-lmstudio",
                reader_model=options.lmstudio_model,
                exc=exc,
            )
            log(f"LM Studio failed for {path}: profile={profile.name} error={exc}")
    return LmStudioProfileRunSummary(region_count=region_count, error_count=error_count)


def process_lmstudio(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    profile: LmStudioPromptProfile,
    log: Callable[[str], None],
) -> int:
    log(
        "Reading with LM Studio: "
        f"{path} profile={profile.name} model={options.lmstudio_model} "
        f"base_url={options.lmstudio_base_url}"
    )
    target_pages = target_pages_for_regions(connection, path, file_hash)
    evidence_by_page = (
        lmstudio_evidence_by_page(connection, file_hash, target_pages)
        if options.lmstudio_include_evidence
        else {}
    )
    lmstudio_options = LmStudioOptions(
        base_url=options.lmstudio_base_url,
        model=options.lmstudio_model,
        timeout_seconds=options.lmstudio_timeout_seconds,
        render_dpi=options.lmstudio_render_dpi,
        image_max_side=options.lmstudio_image_max_side,
        max_tokens=options.lmstudio_max_tokens,
        box_origin=options.lmstudio_box_origin,
        include_evidence=options.lmstudio_include_evidence,
        image_rotation_degrees_by_page=image_rotation_degrees_by_page(target_pages),
        annotation_engine=profile.annotation_engine,
        prompt_profile=profile.name,
        profile_instructions=profile.instructions,
    )
    with traced_span(
        "trapo.ingest.lmstudio_read",
        attributes={
            "file.hash": file_hash,
            "lmstudio.model": options.lmstudio_model,
            "lmstudio.base_url": options.lmstudio_base_url,
            "lmstudio.render_dpi": options.lmstudio_render_dpi,
            "lmstudio.image_max_side": options.lmstudio_image_max_side,
            "lmstudio.include_evidence": options.lmstudio_include_evidence,
            "lmstudio.profile": profile.name,
            "annotation.engine": profile.annotation_engine,
        },
    ):
        read_result = read_with_lmstudio(
            path,
            options=lmstudio_options,
            evidence_by_page=evidence_by_page,
            log=log,
        )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine=profile.annotation_engine,
        text=read_result.text,
        output_json=read_result.data,
        reader_provider=read_result.provider,
        reader_model=read_result.model,
        metadata={
            "base_url": options.lmstudio_base_url,
            "model": options.lmstudio_model,
            "render_dpi": options.lmstudio_render_dpi,
            "image_max_side": options.lmstudio_image_max_side,
            "max_tokens": options.lmstudio_max_tokens,
            "box_origin": options.lmstudio_box_origin,
            "include_evidence": options.lmstudio_include_evidence,
            "profile": profile.metadata(),
            "page_error_count": read_result.data.get("page_error_count", 0),
        },
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": profile.annotation_engine,
        },
    ) as region_span:
        region_count = rebuild_lmstudio_document_regions(
            connection,
            file_hash,
            read_result.data,
            annotation_engine=profile.annotation_engine,
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored LM Studio: profile={profile.name} regions={region_count}")
    return region_count


def lmstudio_profile_engines(options: IngestOptions) -> list[str]:
    return [
        profile.annotation_engine
        for profile in requested_lmstudio_profiles(options.lmstudio_profiles)
    ]


def process_fusion(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    fusion_profile: FusionProfile,
    log: Callable[[str], None],
) -> int:
    log(f"Fusing annotation regions: {path} profile={fusion_profile.name}")
    pages = target_pages_for_regions(connection, path, file_hash) or []
    with traced_span(
        "trapo.ingest.fuse_regions",
        attributes={
            "file.hash": file_hash,
            "fusion.model": FUSION_MODEL,
            "fusion.profile": fusion_profile.name,
        },
    ) as fusion_span:
        result = rebuild_fused_document_regions(
            connection, file_hash, pages, profile=fusion_profile
        )
        span_set_attributes(
            fusion_span,
            {
                "region.count": result.region_count,
                "source.region_count": result.data.get("source_region_count", 0),
            },
        )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine=fusion_profile.annotation_engine,
        text=result.text,
        output_json=result.data,
        reader_provider=FUSION_PROVIDER,
        reader_model=FUSION_MODEL,
        metadata={
            "profile": fusion_profile.metadata(),
            "source_engines": result.data.get("source_engines", []),
            "source_region_count": result.data.get("source_region_count", 0),
        },
    )
    log(
        "Stored fused regions: "
        f"profile={fusion_profile.name} regions={result.region_count} "
        f"source_regions={result.data.get('source_region_count', 0)}"
    )
    return result.region_count


def pending_fusion_profiles(
    connection: DuckConnection,
    file_hash: str,
    *,
    pending_engines: list[str],
    options: IngestOptions,
) -> list[FusionProfile]:
    if not options.fuse_regions:
        return []
    profiles = requested_fusion_profiles(options.fusion_profiles)
    return [
        profile
        for profile in profiles
        if options.reprocess
        or bool(pending_engines)
        or not _engine_complete(connection, file_hash, profile.annotation_engine)
    ]


def _engine_complete(
    connection: DuckConnection, file_hash: str, annotation_engine: str
) -> bool:
    if not table_exists(connection, "ocr_documents"):
        return False
    row = connection.execute(
        """
        SELECT status
        FROM ocr_documents
        WHERE file_hash = ? AND annotation_engine = ?
        """,
        [file_hash, annotation_engine],
    ).fetchone()
    return bool(row and str(row[0]) == "ok")
