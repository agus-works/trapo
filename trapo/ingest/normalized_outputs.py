from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from trapo.ingest.docling_reader import DoclingReadResult
from trapo.ingest.mineru_reader import MinerUReadResult
from trapo.ingest.normalized_pages import NormalizedPreviewPage
from trapo.ingest.options import IngestOptions


def combined_docling_output(
    pages: list[NormalizedPreviewPage],
    results: dict[Path, DoclingReadResult],
    *,
    source_path: Path,
) -> tuple[str, dict[str, Any]]:
    combined: dict[str, Any] = {
        "source": str(source_path),
        "normalized_input": True,
        "pages": {},
        "texts": [],
        "tables": [],
        "normalized_page_outputs": [],
    }
    markdown_pages: list[str] = []
    for page in pages:
        result = results[page.image_path]
        page_data = _remap_page_numbers(result.data, page.page_no)
        combined["pages"][str(page.page_no)] = _docling_page(page_data, page)
        _extend_list(combined, page_data, "texts")
        _extend_list(combined, page_data, "tables")
        combined["normalized_page_outputs"].append(
            {
                "page_no": page.page_no,
                "image_sha256": page.image_sha256,
                "output": page_data,
            }
        )
        if result.text.strip():
            markdown_pages.append(
                f"<!-- page {page.page_no} -->\n{result.text.strip()}"
            )
    return "\n\n".join(markdown_pages), combined


def combined_mineru_output(
    pages: list[NormalizedPreviewPage],
    results: dict[Path, MinerUReadResult],
    *,
    options: IngestOptions,
    source_path: Path,
) -> tuple[str, dict[str, Any]]:
    middle_json: dict[str, Any] = {"pdf_info": []}
    output: dict[str, Any] = {
        "backend": options.mineru_backend,
        "parse_method": options.mineru_parse_method,
        "source": str(source_path),
        "normalized_input": True,
        "middle_json": middle_json,
        "content_list": [],
        "content_list_v2": [],
        "normalized_page_outputs": [],
    }
    markdown_pages: list[str] = []
    for page in pages:
        result = results[page.image_path]
        page_data = _remap_mineru_page(result.data, page)
        middle_json["pdf_info"].extend(_mineru_pdf_info(page_data, page))
        _extend_list(output, page_data, "content_list")
        _extend_list(output, page_data, "content_list_v2")
        output["normalized_page_outputs"].append(
            {
                "page_no": page.page_no,
                "image_sha256": page.image_sha256,
                "output": page_data,
            }
        )
        if result.text.strip():
            markdown_pages.append(
                f"<!-- page {page.page_no} -->\n{result.text.strip()}"
            )
    output = {
        key: value for key, value in output.items() if value not in ([], {}, None)
    }
    return "\n\n".join(markdown_pages), output


def _docling_page(data: dict[str, Any], page: NormalizedPreviewPage) -> dict[str, Any]:
    pages = data.get("pages")
    if isinstance(pages, dict):
        page_data = next(
            (item for item in pages.values() if isinstance(item, dict)), {}
        )
    elif isinstance(pages, list):
        page_data = next((item for item in pages if isinstance(item, dict)), {})
    else:
        page_data = {}
    result = copy.deepcopy(page_data)
    result["page_no"] = page.page_no
    result.setdefault("size", {"width": page.page.width, "height": page.page.height})
    return result


def _mineru_pdf_info(
    data: dict[str, Any], page: NormalizedPreviewPage
) -> list[dict[str, Any]]:
    middle_json = data.get("middle_json")
    pdf_info = middle_json.get("pdf_info") if isinstance(middle_json, dict) else None
    entries = (
        [item for item in pdf_info if isinstance(item, dict)]
        if isinstance(pdf_info, list)
        else []
    )
    if not entries:
        entries = [{}]
    result: list[dict[str, Any]] = []
    for entry in entries:
        item = copy.deepcopy(entry)
        item["page_idx"] = page.page_no - 1
        item["page_size"] = [page.page.width, page.page.height]
        result.append(item)
    return result


def _remap_page_numbers(value: object, page_no: int) -> Any:
    return _remap_key(value, "page_no", page_no)


def _remap_mineru_page(
    data: dict[str, Any], page: NormalizedPreviewPage
) -> dict[str, Any]:
    remapped = _remap_key(data, "page_idx", page.page_no - 1)
    if isinstance(remapped, dict):
        return remapped
    return {}


def _remap_key(value: object, key_name: str, replacement: int) -> Any:
    if isinstance(value, dict):
        return {
            key: replacement
            if key == key_name
            else _remap_key(child, key_name, replacement)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_remap_key(item, key_name, replacement) for item in value]
    return copy.deepcopy(value)


def _extend_list(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    value = source.get(key)
    if isinstance(value, list):
        target.setdefault(key, []).extend(value)
