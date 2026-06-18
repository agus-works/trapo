from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from trapo.diagnostics import diagnostic_context_active
from trapo.filesystem_safety import write_bytes_file
from trapo.ingest.page_images import RenderedPageImage


DEFAULT_LLM_DIAGNOSTICS_CACHE_ROOT = ".cache/trapo/llm-diagnostics"
IMAGE_URL_BLOCK_TYPE = "image_url"


def attachment_metadata(
    page: RenderedPageImage | None,
    stage: str,
    model: str,
) -> dict[str, object] | None:
    if page is None:
        return None
    source_path = _source_attachment_path(page)
    file_path = source_path or _write_attachment(page, stage, model)
    return {
        "file_path": str(file_path.resolve()) if file_path is not None else None,
        "mime_type": page.mime_type,
        "sha256": page.image_sha256,
        "bytes": len(page.image_bytes),
        "data_url_chars": len(page.data_url),
        "render_width": page.render_width,
        "render_height": page.render_height,
        "page_no": page.page_no,
    }


def sanitized_payload(
    payload: dict[str, Any],
    attachment: dict[str, object] | None,
) -> dict[str, Any]:
    return {
        key: _sanitize_payload_value(value, attachment)
        for key, value in payload.items()
        if key != "response_format" or value is not None
    }


def _source_attachment_path(page: RenderedPageImage) -> Path | None:
    attachment_path = getattr(page, "attachment_path", None)
    if not attachment_path:
        return None
    return Path(str(attachment_path)).resolve(strict=False)


def _write_attachment(
    page: RenderedPageImage,
    stage: str,
    model: str,
) -> Path | None:
    if not diagnostic_context_active():
        return None
    root = Path(
        os.getenv(
            "TRAPO_LLM_DIAGNOSTICS_CACHE_ROOT",
            DEFAULT_LLM_DIAGNOSTICS_CACHE_ROOT,
        )
    )
    suffix = _mime_suffix(page.mime_type)
    safe_stage = _safe_path_part(stage)
    safe_model = _safe_path_part(model)
    path = (
        root
        / safe_model
        / page.image_sha256[:2]
        / f"{safe_stage}-page-{page.page_no:04d}-{page.image_sha256}{suffix}"
    )
    return write_bytes_file(path, page.image_bytes, root=root)


def _sanitize_payload_value(
    value: Any,
    attachment: dict[str, object] | None,
) -> Any:
    result = value
    if isinstance(value, list):
        result = [_sanitize_payload_value(item, attachment) for item in value]
    elif isinstance(value, dict):
        result = _sanitize_payload_dict(value, attachment)
    elif isinstance(value, str) and value.startswith("data:image"):
        result = "[diagnostic attachment on filesystem]"
    return result


def _sanitize_payload_dict(
    value: dict[str, Any],
    attachment: dict[str, object] | None,
) -> dict[str, Any]:
    if _is_image_url_block(value):
        return {
            "type": IMAGE_URL_BLOCK_TYPE,
            "image_url": {
                "url": "[diagnostic attachment on filesystem]",
                "attachment": attachment,
            },
        }
    return {
        str(key): _sanitize_payload_value(item, attachment)
        for key, item in value.items()
    }


def _is_image_url_block(value: dict[str, Any]) -> bool:
    if value.get("type") != IMAGE_URL_BLOCK_TYPE:
        return False
    image_url = value.get("image_url")
    return isinstance(image_url, dict) and isinstance(image_url.get("url"), str)


def _mime_suffix(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type.lower(), ".bin")


def _safe_path_part(value: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in value.lower())
    collapsed = "-".join(part for part in safe.split("-") if part)
    return collapsed[:96] or "unknown"
