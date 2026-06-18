from __future__ import annotations

import json
from typing import Any

from PIL import Image

from trapo.ingest.lmstudio_models import (
    LmStudioOptions,
    LmStudioPageResponse,
    LmStudioRegionCandidate,
)
from trapo.ingest.lmstudio_reader import read_with_lmstudio
from trapo.ingest.page_images import RenderedPageImage, iter_rendered_pages

FIRST_TIFF_WIDTH = 40.0
FIRST_TIFF_HEIGHT = 20.0
SECOND_TIFF_WIDTH = 30.0
TIFF_RENDER_WIDTH = 20
RECEIPT_WIDTH = 120.0
RECEIPT_HEIGHT = 60.0
RECEIPT_RENDER_WIDTH = 80
TOTAL_BOX = [100, 250, 300, 750]


def test_iter_rendered_pages_splits_multipage_tiff(tmp_path) -> None:
    path = tmp_path / "scan.tiff"
    first = Image.new(
        "RGB", (int(FIRST_TIFF_WIDTH), int(FIRST_TIFF_HEIGHT)), color=(255, 255, 255)
    )
    second = Image.new("RGB", (int(SECOND_TIFF_WIDTH), 10), color=(240, 240, 240))
    first.save(path, save_all=True, append_images=[second])

    pages = list(iter_rendered_pages(path, max_side=TIFF_RENDER_WIDTH))

    assert [page.page_no for page in pages] == [1, 2]
    assert pages[0].width == FIRST_TIFF_WIDTH
    assert pages[0].height == FIRST_TIFF_HEIGHT
    assert pages[0].render_width == TIFF_RENDER_WIDTH
    assert pages[1].width == SECOND_TIFF_WIDTH
    assert pages[1].render_width == TIFF_RENDER_WIDTH


def test_read_with_lmstudio_uses_fake_client_and_keeps_images_out_of_output(
    tmp_path,
) -> None:
    path = tmp_path / "receipt.png"
    Image.new(
        "RGB", (int(RECEIPT_WIDTH), int(RECEIPT_HEIGHT)), color=(255, 255, 255)
    ).save(path)
    client = _FakeLmStudioClient()
    logs: list[str] = []

    result = read_with_lmstudio(
        path,
        options=LmStudioOptions(
            model="test-vision-model",
            image_max_side=RECEIPT_RENDER_WIDTH,
            render_dpi=144,
            annotation_engine="lmstudio_strict",
            prompt_profile="strict",
            profile_instructions="Strict profile instructions.",
        ),
        evidence_by_page={
            1: [
                {
                    "region_id": "docling-1",
                    "engine": "docling",
                    "box_2d": [100, 100, 200, 500],
                }
            ]
        },
        log=logs.append,
        client=client,
    )

    assert result.model == "test-vision-model"
    assert result.text == "Total 42.00"
    assert result.data["engine"] == "lmstudio_strict"
    assert result.data["prompt_profile"] == "strict"
    assert result.data["box_2d_coord_origin"] == "BOTTOMLEFT"
    assert client.closed is False
    assert client.prompt_count == 1
    assert "docling-1" in client.last_prompt
    assert "Strict profile instructions." in client.last_prompt
    assert result.data["pages"][0]["width"] == RECEIPT_WIDTH
    assert result.data["pages"][0]["height"] == RECEIPT_HEIGHT
    assert result.data["pages"][0]["regions"][0]["box_2d"] == TOTAL_BOX
    assert "data:image" not in json.dumps(result.data)
    assert any("page=1" in message for message in logs)


def test_read_with_lmstudio_continues_after_page_failure(tmp_path) -> None:
    path = tmp_path / "scan.tiff"
    first = Image.new("RGB", (120, 60), color=(255, 255, 255))
    second = Image.new("RGB", (120, 60), color=(240, 240, 240))
    third = Image.new("RGB", (120, 60), color=(245, 245, 245))
    first.save(path, format="TIFF", save_all=True, append_images=[second, third])
    logs: list[str] = []

    result = read_with_lmstudio(
        path,
        options=LmStudioOptions(
            model="test-vision-model",
            image_max_side=RECEIPT_RENDER_WIDTH,
        ),
        log=logs.append,
        client=_FailingLmStudioClient(fail_page_no=2),
    )

    assert result.text == "Total 42.00\nTotal 42.00"
    assert result.data["page_error_count"] == 1
    assert [page["page_no"] for page in result.data["pages"]] == [1, 2, 3]
    assert result.data["pages"][1]["status"] == "error"
    assert result.data["pages"][1]["error_type"] == "RuntimeError"
    assert any("LM Studio page failed: page=2" in message for message in logs)


class _FakeLmStudioClient:
    def __init__(self) -> None:
        self.prompt_count = 0
        self.last_prompt = ""
        self.closed = False

    def detect_page_regions(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageResponse, dict[str, Any]]:
        assert max_tokens > 0
        assert temperature == 0.0
        assert page.render_width == RECEIPT_RENDER_WIDTH
        self.prompt_count += 1
        self.last_prompt = prompt
        return (
            LmStudioPageResponse(
                page_summary="receipt",
                regions=[
                    LmStudioRegionCandidate(
                        label="total",
                        region_kind="text",
                        text="Total 42.00",
                        box_2d=TOTAL_BOX,
                        confidence=0.9,
                    )
                ],
            ),
            {"usage": {"total_tokens": 12}},
        )

    def close(self) -> None:
        self.closed = True


class _FailingLmStudioClient(_FakeLmStudioClient):
    def __init__(self, *, fail_page_no: int) -> None:
        super().__init__()
        self.fail_page_no = fail_page_no

    def detect_page_regions(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageResponse, dict[str, Any]]:
        if page.page_no == self.fail_page_no:
            raise RuntimeError("synthetic page failure")
        return super().detect_page_regions(
            page,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
