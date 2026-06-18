from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from trapo.ingest.lmstudio_client import LmStudioClient, PageRegionClient
from trapo.ingest.lmstudio_models import (
    LMSTUDIO_ENGINE,
    LMSTUDIO_PROVIDER,
    LmStudioOptions,
    LmStudioPageResponse,
    LmStudioReadResult,
)
from trapo.ingest.lmstudio_prompts import page_prompt
from trapo.ingest.page_images import RenderedPageImage, iter_rendered_pages


def read_with_lmstudio(
    path: Path,
    *,
    options: LmStudioOptions,
    evidence_by_page: Mapping[int, list[dict[str, Any]]] | None = None,
    log: Callable[[str], None] | None = None,
    client: PageRegionClient | None = None,
) -> LmStudioReadResult:
    """Read one document through LM Studio vision calls, page by page."""
    page_outputs: list[dict[str, Any]] = []
    text_parts: list[str] = []
    lmstudio = client or LmStudioClient(
        base_url=options.base_url,
        model=options.model,
        timeout_seconds=options.timeout_seconds,
    )
    close_client = client is None
    try:
        for page in iter_rendered_pages(
            path,
            dpi=options.render_dpi,
            max_side=options.image_max_side,
            image_rotation_degrees_by_page=options.image_rotation_degrees_by_page,
        ):
            page_evidence = (
                list((evidence_by_page or {}).get(page.page_no, []))
                if options.include_evidence
                else []
            )
            _log_page_start(log, page, len(page_evidence))
            started_at = time.perf_counter()
            try:
                parsed, raw_response = lmstudio.detect_page_regions(
                    page,
                    prompt=page_prompt(
                        page,
                        page_evidence,
                        profile_instructions=options.profile_instructions,
                    ),
                    max_tokens=options.max_tokens,
                    temperature=options.temperature,
                )
            except Exception as exc:
                elapsed_seconds = time.perf_counter() - started_at
                page_outputs.append(
                    _page_error_output(page, len(page_evidence), elapsed_seconds, exc)
                )
                _log_page_error(log, page.page_no, elapsed_seconds, exc)
                continue
            elapsed_seconds = time.perf_counter() - started_at
            _log_page_done(log, page.page_no, len(parsed.regions), elapsed_seconds)
            text_parts.extend(
                region.text for region in parsed.regions if region.text.strip()
            )
            page_outputs.append(
                _page_output(
                    page, parsed, raw_response, len(page_evidence), elapsed_seconds
                )
            )
    finally:
        if close_client:
            lmstudio.close()
    if not any(page.get("status") != "error" for page in page_outputs):
        raise RuntimeError("LM Studio failed for every rendered page.")

    return LmStudioReadResult(
        text="\n".join(text_parts),
        model=options.model,
        data={
            "engine": options.annotation_engine or LMSTUDIO_ENGINE,
            "provider": LMSTUDIO_PROVIDER,
            "model": options.model,
            "base_url": options.base_url,
            "render_dpi": options.render_dpi,
            "image_max_side": options.image_max_side,
            "box_2d_coord_origin": options.box_origin,
            "include_evidence": options.include_evidence,
            "prompt_profile": options.prompt_profile,
            "profile_instructions": options.profile_instructions,
            "source": str(path),
            "page_error_count": sum(
                1 for page in page_outputs if page.get("status") == "error"
            ),
            "pages": page_outputs,
        },
    )


def _page_output(
    page: RenderedPageImage,
    parsed: LmStudioPageResponse,
    raw_response: dict[str, Any],
    evidence_count: int,
    elapsed_seconds: float,
) -> dict[str, Any]:
    return {
        "page_no": page.page_no,
        "width": page.width,
        "height": page.height,
        "render_width": page.render_width,
        "render_height": page.render_height,
        "render_mime_type": page.mime_type,
        "render_sha256": page.image_sha256,
        "page_summary": parsed.page_summary,
        "regions": [region.model_dump() for region in parsed.regions],
        "warnings": parsed.warnings,
        "evidence_count": evidence_count,
        "elapsed_seconds": elapsed_seconds,
        "raw_response": raw_response,
    }


def _page_error_output(
    page: RenderedPageImage,
    evidence_count: int,
    elapsed_seconds: float,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "status": "error",
        "page_no": page.page_no,
        "width": page.width,
        "height": page.height,
        "render_width": page.render_width,
        "render_height": page.render_height,
        "render_mime_type": page.mime_type,
        "render_sha256": page.image_sha256,
        "regions": [],
        "warnings": [],
        "evidence_count": evidence_count,
        "elapsed_seconds": elapsed_seconds,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _log_page_start(
    log: Callable[[str], None] | None,
    page: RenderedPageImage,
    evidence_count: int,
) -> None:
    if log is not None:
        log(
            "Reading with LM Studio: "
            f"page={page.page_no} render={page.render_width}x{page.render_height} "
            f"evidence={evidence_count}"
        )


def _log_page_done(
    log: Callable[[str], None] | None,
    page_no: int,
    region_count: int,
    elapsed_seconds: float,
) -> None:
    if log is not None:
        log(
            "Stored LM Studio page result: "
            f"page={page_no} regions={region_count} elapsed={elapsed_seconds:.2f}s"
        )


def _log_page_error(
    log: Callable[[str], None] | None,
    page_no: int,
    elapsed_seconds: float,
    exc: Exception,
) -> None:
    if log is not None:
        log(
            "LM Studio page failed: "
            f"page={page_no} elapsed={elapsed_seconds:.2f}s error={exc}"
        )
