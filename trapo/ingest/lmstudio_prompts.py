from __future__ import annotations

import json

from trapo.ingest.page_images import RenderedPageImage


SYSTEM_PROMPT = (
    "You are Trapo's document layout annotation engine. Return precise document "
    "regions only. Do not invent content that is not visible in the page image."
)
ORIENTATION_SYSTEM_PROMPT = (
    "You are Trapo's document orientation checker. Return only the rotation "
    "needed to make visible document text upright."
)
MARKDOWN_SYSTEM_PROMPT = (
    "Transcribe the visible page to concise Markdown. Use only visible content."
)


def page_prompt(
    page: RenderedPageImage,
    evidence: list[dict[str, object]],
    *,
    profile_instructions: str = "",
) -> str:
    evidence_json = json.dumps(evidence[:80], ensure_ascii=False)
    profile_text = (
        f"\nProfile instructions:\n{profile_instructions.strip()}\n"
        if profile_instructions.strip()
        else ""
    )
    return (
        "Detect every visible logical document region on this page.\n"
        f"Page number: {page.page_no}\n"
        f"Display size: {page.width:g} x {page.height:g}\n"
        f"Prompt image size: {page.render_width} x {page.render_height}\n\n"
        f"{profile_text}"
        "Return `box_2d` as [y0, left, y1, right] integer coordinates on the "
        "native Gemma 0-1000 visual grid. Use x=0 at the left edge and x=1000 "
        "at the right edge. Use y=0 at the bottom edge and y=1000 at the top "
        "edge. A region visually near the top of the page should therefore have "
        "high y values close to 1000. Clip coordinates to 0..1000, keep y0 < y1 "
        "and left < right, and prefer tight boxes around the visible region. "
        "Copy legible text into `text` exactly as seen.\n\n"
        "Use these region kinds when they fit: text, title, table, table_cell, "
        "formula, image, chart, code, list, header, footer, footnote, "
        "page_number, signature, checkbox, stamp, other.\n\n"
        "Docling/MinerU candidate boxes are hints only. Use the image as the "
        "final authority. If a hint is useful, copy its region id into "
        "`source_region_ids`.\n\n"
        f"Candidate evidence JSON:\n{evidence_json}"
    )


def orientation_prompt(page: RenderedPageImage) -> str:
    return (
        "The prompt image is a 2x2 comparison sheet. Each quadrant shows the "
        "same document page rotated by a candidate clockwise correction and "
        "labeled 0, 90, 180, or 270. Ignore the quadrant labels as document "
        "content. Choose the label whose quadrant makes the dominant readable "
        "document text upright for a human reader.\n\n"
        f"Page number: {page.page_no}\n"
        f"Comparison sheet size: {page.render_width} x {page.render_height}\n\n"
        "Return the chosen label as clockwise_degrees. Use confidence below 0.5 "
        "if no quadrant has reliable readable document text."
    )


def page_markdown_prompt(page: RenderedPageImage) -> str:
    return (
        f"Page {page.page_no}; image {page.render_width}x{page.render_height}px.\n"
        "Return only Markdown. Keep reading order, headings, lists, and tables "
        "when clear. Stop after the visible page content."
    )
