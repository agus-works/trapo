from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from trapo.ingest.lmstudio_client import LmStudioClient, PageRegionClient
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    DEFAULT_LMSTUDIO_MODEL,
    DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
    LmStudioOptions,
    LmStudioRegionCandidate,
)
from trapo.ingest.page_images import RenderedPageImage


SMOKE_PAGE_WIDTH = 640
SMOKE_PAGE_HEIGHT = 360
SMOKE_RENDER_MAX_SIDE = 640


@dataclass(frozen=True)
class LmStudioSmokeResult:
    base_url: str
    model: str
    region_count: int
    elapsed_seconds: float
    page_sha256: str
    raw_response: dict[str, Any]
    regions: list[LmStudioRegionCandidate]


def run_lmstudio_smoke(
    *,
    options: LmStudioOptions,
    client: PageRegionClient | None = None,
) -> LmStudioSmokeResult:
    """Run a one-page schema-validity and bbox smoke test against LM Studio."""
    lmstudio = client or LmStudioClient(
        base_url=options.base_url,
        model=options.model,
        timeout_seconds=options.timeout_seconds,
    )
    close_client = client is None
    page = smoke_page(max_side=options.image_max_side)
    started_at = time.perf_counter()
    try:
        parsed, raw_response = lmstudio.detect_page_regions(
            page,
            prompt=smoke_prompt(page),
            max_tokens=options.max_tokens,
            temperature=options.temperature,
        )
    finally:
        if close_client:
            lmstudio.close()
    elapsed_seconds = time.perf_counter() - started_at
    if not parsed.regions:
        raise RuntimeError("LM Studio returned a schema-valid response but no regions.")
    return LmStudioSmokeResult(
        base_url=options.base_url,
        model=options.model,
        region_count=len(parsed.regions),
        elapsed_seconds=elapsed_seconds,
        page_sha256=page.image_sha256,
        raw_response=raw_response,
        regions=parsed.regions,
    )


def smoke_page(*, max_side: int = SMOKE_RENDER_MAX_SIDE) -> RenderedPageImage:
    image = Image.new("RGB", (SMOKE_PAGE_WIDTH, SMOKE_PAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((32, 28, 608, 332), outline="black", width=3)
    draw.text((64, 64), "TRAPO SMOKE TEST", fill="black")
    draw.text((64, 112), "Total: 42.00", fill="black")
    draw.rectangle((64, 164, 300, 244), outline="black", width=2)
    draw.text((84, 190), "BOX TARGET", fill="black")
    render = _resize(image, max_side=max_side)
    output = BytesIO()
    render.save(output, format="PNG", optimize=True)
    image_bytes = output.getvalue()
    return RenderedPageImage(
        page_no=1,
        width=float(image.width),
        height=float(image.height),
        render_width=render.width,
        render_height=render.height,
        mime_type="image/png",
        image_bytes=image_bytes,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
    )


def smoke_prompt(page: RenderedPageImage) -> str:
    return (
        "This is a Trapo LM Studio smoke-test page. Detect the visible document "
        "regions, especially the title text `TRAPO SMOKE TEST`, the text "
        "`Total: 42.00`, and the bordered `BOX TARGET` area.\n\n"
        f"Page number: {page.page_no}\n"
        f"Display size: {page.width:g} x {page.height:g}\n"
        f"Prompt image size: {page.render_width} x {page.render_height}\n\n"
        "Return at least one region. Return `box_2d` as [y0, left, y1, right] "
        "integer coordinates on the native Gemma 0-1000 visual grid. Use y=0 "
        "at the bottom edge and y=1000 at the top edge. Clip coordinates to "
        "0..1000 and keep y0 < y1 and left < right."
    )


def _resize(image: Image.Image, *, max_side: int) -> Image.Image:
    if max_side <= 0 or max(image.size) <= max_side:
        return image.copy()
    scale = max_side / max(image.size)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def default_smoke_options(
    *,
    base_url: str = DEFAULT_LMSTUDIO_BASE_URL,
    model: str = DEFAULT_LMSTUDIO_MODEL,
    timeout_seconds: float = DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
    image_max_side: int = SMOKE_RENDER_MAX_SIDE,
    max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
) -> LmStudioOptions:
    return LmStudioOptions(
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
        image_max_side=image_max_side,
        max_tokens=max_tokens,
        include_evidence=False,
    )
