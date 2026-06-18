from __future__ import annotations

from io import BytesIO
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageDraw

from trapo.ingest.lmstudio_client import LmStudioClient
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE,
    DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE,
    LmStudioOptions,
    LmStudioPageOrientationResponse,
)
from trapo.ingest.lmstudio_prompts import orientation_prompt
from trapo.ingest.page_images import RenderedPageImage, iter_rendered_pages
from trapo.page_orientation import (
    PageOrientationOverrideUpdate,
    normalize_clockwise_degrees,
)


class PageOrientationClient(Protocol):
    def detect_page_orientation(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageOrientationResponse, dict[str, Any]]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class LmStudioOrientationReadResult:
    overrides: list[PageOrientationOverrideUpdate]
    data: dict[str, Any]


@dataclass(frozen=True)
class LmStudioOrientationRequest:
    file_hash: str
    options: LmStudioOptions
    min_confidence: float = DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE
    max_side: int = DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE
    max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    skip_pages: set[int] | None = None


def detect_lmstudio_page_orientations(
    path: Path,
    *,
    request: LmStudioOrientationRequest,
    log: Callable[[str], None] | None = None,
    client: PageOrientationClient | None = None,
) -> LmStudioOrientationReadResult:
    """Detect page rotations for image inputs before the full LM Studio region pass."""
    lmstudio = client or LmStudioClient(
        base_url=request.options.base_url,
        model=request.options.model,
        timeout_seconds=request.options.timeout_seconds,
    )
    close_client = client is None
    skipped_pages = request.skip_pages or set()
    overrides: list[PageOrientationOverrideUpdate] = []
    page_outputs: list[dict[str, Any]] = []
    try:
        for page in iter_rendered_pages(path, max_side=request.max_side):
            if page.page_no in skipped_pages:
                _log_orientation_skip(log, page.page_no)
                continue
            orientation_page = _orientation_choice_page(page)
            _log_orientation_start(log, page)
            started_at = time.perf_counter()
            parsed, raw_response = lmstudio.detect_page_orientation(
                orientation_page,
                prompt=orientation_prompt(orientation_page),
                max_tokens=request.max_tokens,
                temperature=request.options.temperature,
            )
            elapsed_seconds = time.perf_counter() - started_at
            degrees = normalize_clockwise_degrees(parsed.clockwise_degrees)
            accepted = _accepted_orientation(parsed, degrees, request.min_confidence)
            _log_orientation_done(
                log, page.page_no, degrees, parsed.confidence, accepted
            )
            if accepted:
                overrides.append(
                    PageOrientationOverrideUpdate(
                        file_hash=request.file_hash,
                        page_no=page.page_no,
                        clockwise_degrees=degrees,
                        source="lmstudio",
                        confidence=parsed.confidence,
                        metadata={
                            "model": request.options.model,
                            "render_width": page.render_width,
                            "render_height": page.render_height,
                            "render_sha256": page.image_sha256,
                            "orientation_sheet_width": orientation_page.render_width,
                            "orientation_sheet_height": orientation_page.render_height,
                            "orientation_sheet_sha256": orientation_page.image_sha256,
                            "text_orientation": parsed.text_orientation,
                            "rationale": parsed.rationale,
                            "warnings": parsed.warnings,
                            "raw_response": raw_response,
                        },
                    )
                )
            page_outputs.append(
                {
                    "page_no": page.page_no,
                    "width": page.width,
                    "height": page.height,
                    "render_width": page.render_width,
                    "render_height": page.render_height,
                    "render_sha256": page.image_sha256,
                    "orientation_sheet_width": orientation_page.render_width,
                    "orientation_sheet_height": orientation_page.render_height,
                    "orientation_sheet_sha256": orientation_page.image_sha256,
                    "clockwise_degrees": degrees,
                    "confidence": parsed.confidence,
                    "accepted": accepted,
                    "text_orientation": parsed.text_orientation,
                    "rationale": parsed.rationale,
                    "warnings": parsed.warnings,
                    "elapsed_seconds": elapsed_seconds,
                    "raw_response": raw_response,
                }
            )
    finally:
        if close_client:
            lmstudio.close()

    return LmStudioOrientationReadResult(
        overrides=overrides,
        data={
            "engine": "lmstudio_orientation",
            "model": request.options.model,
            "source": str(path),
            "min_confidence": request.min_confidence,
            "max_side": request.max_side,
            "max_tokens": request.max_tokens,
            "pages": page_outputs,
        },
    )


def _accepted_orientation(
    parsed: LmStudioPageOrientationResponse,
    degrees: int,
    min_confidence: float,
) -> bool:
    has_reason = parsed.text_orientation != "unknown" or bool(parsed.rationale.strip())
    return parsed.confidence >= min_confidence and (degrees != 0 or has_reason)


def _orientation_choice_page(page: RenderedPageImage) -> RenderedPageImage:
    with Image.open(BytesIO(page.image_bytes)) as image:
        source = image.convert("RGB")
        choices = [
            (0, source.copy()),
            (90, source.transpose(Image.Transpose.ROTATE_270)),
            (180, source.transpose(Image.Transpose.ROTATE_180)),
            (270, source.transpose(Image.Transpose.ROTATE_90)),
        ]
    label_height = 34
    gutter = 12
    cell_width = max(image.width for _degrees, image in choices)
    cell_height = max(image.height for _degrees, image in choices) + label_height
    sheet = Image.new(
        "RGB",
        (cell_width * 2 + gutter, cell_height * 2 + gutter),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (degrees, image) in enumerate(choices):
        column = index % 2
        row = index // 2
        left = column * (cell_width + gutter)
        top = row * (cell_height + gutter)
        draw.text((left + 8, top + 8), f"{degrees}", fill=(0, 0, 0))
        paste_left = left + (cell_width - image.width) // 2
        paste_top = (
            top + label_height + (cell_height - label_height - image.height) // 2
        )
        sheet.paste(image, (paste_left, paste_top))
    output = BytesIO()
    sheet.save(output, format="PNG", optimize=True)
    image_bytes = output.getvalue()
    return RenderedPageImage(
        page_no=page.page_no,
        width=page.width,
        height=page.height,
        render_width=sheet.width,
        render_height=sheet.height,
        mime_type="image/png",
        image_bytes=image_bytes,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
    )


def _log_orientation_start(
    log: Callable[[str], None] | None, page: RenderedPageImage
) -> None:
    if log is not None:
        log(
            "Detecting image orientation with LM Studio: "
            f"page={page.page_no} render={page.render_width}x{page.render_height}"
        )


def _log_orientation_done(
    log: Callable[[str], None] | None,
    page_no: int,
    degrees: int,
    confidence: float,
    accepted: bool,
) -> None:
    if log is not None:
        status = "accepted" if accepted else "ignored"
        log(
            "LM Studio orientation result: "
            f"page={page_no} clockwise={degrees} confidence={confidence:.2f} {status}"
        )


def _log_orientation_skip(log: Callable[[str], None] | None, page_no: int) -> None:
    if log is not None:
        log(
            f"Skipping LM Studio orientation detection: page={page_no} already has override"
        )
