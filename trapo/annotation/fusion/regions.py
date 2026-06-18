from __future__ import annotations

import json

from trapo.db import DuckConnection, table_exists
from trapo.annotation.docling.regions import (
    persisted_region_overlays,
    rebuild_document_terms,
)
from trapo.annotation.fusion.algorithm import (
    candidates_from_overlays,
    fused_region_id,
    fuse_candidates,
    fusion_data,
)
from trapo.annotation.fusion.profiles import FusionProfile, resolve_fusion_profile
from trapo.annotation.fusion.models import (
    FUSION_MODEL,
    FUSION_PROVIDER,
    FusedRegion,
    FusionResult,
)
from trapo.server.models import PageInfo


def rebuild_fused_document_regions(
    connection: DuckConnection,
    file_hash: str,
    pages: list[PageInfo],
    *,
    profile: FusionProfile | str = "balanced",
) -> FusionResult:
    """Build and persist deterministic fused regions from available engines."""
    fusion_profile = (
        resolve_fusion_profile(profile) if isinstance(profile, str) else profile
    )
    if not table_exists(connection, "document_regions"):
        return FusionResult(
            text="",
            data=fusion_data(file_hash, [], [], fusion_profile),
            region_count=0,
        )
    _delete_fusion_regions(connection, file_hash, fusion_profile.annotation_engine)
    pages_by_no = {page.page_no: page for page in pages}
    overlays = persisted_region_overlays(connection, file_hash, pages_by_no)
    candidates = candidates_from_overlays(overlays, pages_by_no)
    fused_regions = fuse_candidates(candidates, fusion_profile)
    for region in fused_regions:
        _insert_fused_region(connection, file_hash, region, fusion_profile)
    rebuild_document_terms(connection, file_hash)
    text = "\n".join(region.text for region in fused_regions if region.text.strip())
    return FusionResult(
        text=text,
        data=fusion_data(file_hash, candidates, fused_regions, fusion_profile),
        region_count=len(fused_regions),
    )


def _insert_fused_region(
    connection: DuckConnection,
    file_hash: str,
    region: FusedRegion,
    profile: FusionProfile,
) -> None:
    connection.execute(
        """
        INSERT INTO document_regions (
            region_id, file_hash, annotation_engine, annotation_provider,
            annotation_model, chunk_id, chunk_index, page_no, source_ref,
            parent_ref, label, text, context_text, raw_bbox_json,
            region_kind, metadata_json
        )
        VALUES (
            ?, ?, ?, 'trapo', ?, NULL, NULL, ?, ?,
            NULL, ?, ?, ?, ?::JSON, ?, ?::JSON
        )
        ON CONFLICT (region_id) DO UPDATE SET
            annotation_engine = excluded.annotation_engine,
            annotation_provider = excluded.annotation_provider,
            annotation_model = excluded.annotation_model,
            page_no = excluded.page_no,
            source_ref = excluded.source_ref,
            label = excluded.label,
            text = excluded.text,
            context_text = excluded.context_text,
            raw_bbox_json = excluded.raw_bbox_json,
            region_kind = excluded.region_kind,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            fused_region_id(file_hash, region, profile),
            file_hash,
            profile.annotation_engine,
            FUSION_MODEL,
            region.page_no,
            region.source_ref,
            region.label,
            region.text,
            region.text,
            json.dumps(region.raw_bbox.model_dump()),
            region.region_kind,
            json.dumps(region.metadata),
        ],
    )


def _delete_fusion_regions(
    connection: DuckConnection,
    file_hash: str,
    annotation_engine: str,
) -> None:
    if table_exists(connection, "document_terms"):
        connection.execute(
            "DELETE FROM document_terms WHERE file_hash = ? AND annotation_engine = ?",
            [file_hash, annotation_engine],
        )
    connection.execute(
        "DELETE FROM document_regions WHERE file_hash = ? AND annotation_engine = ?",
        [file_hash, annotation_engine],
    )


__all__ = [
    "FUSION_MODEL",
    "FUSION_PROVIDER",
    "rebuild_fused_document_regions",
]
