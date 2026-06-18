from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PIL import Image
import pytest

from trapo.document_markdown import is_usable_markdown_text
from trapo.ingest.lmstudio_client import LmStudioClient, LmStudioStructuredOutputError
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    LmStudioMarkdownOptions,
    LmStudioPageMarkdownResponse,
)
from trapo.ingest import markitdown_markdown as markitdown_module
from trapo.ingest.markdown_reader import read_markdown_with_lmstudio
from trapo.ingest.markitdown_markdown import _split_page_sections
from trapo.ingest.options import IngestOptions
from trapo.ingest.page_markdown_images import (
    DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    MarkdownRenderOptions,
    iter_markdown_page_images,
)
from trapo.ingest.page_images import RenderedPageImage

RENDER_WIDTH = 80
TIFF_FRAME_COUNT = 2


def test_read_markdown_with_lmstudio_generates_pages(tmp_path) -> None:
    path = tmp_path / "receipt.png"
    Image.new("RGB", (120, 60), color=(255, 255, 255)).save(path)
    client = _FakeMarkdownClient()

    result = read_markdown_with_lmstudio(
        path,
        file_hash="hash1",
        options=LmStudioMarkdownOptions(
            model="test-vision-model",
            image_max_side=RENDER_WIDTH,
            cache_enabled=False,
            markdown_max_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
        ),
        evidence_by_page={},
        client=client,
    )

    pages = result.pages
    assert result.errors == []
    assert len(pages) == 1
    page = pages[0]
    assert page.file_hash == "hash1"
    assert page.markdown_text == "# Receipt\n\nTotal 42.00"
    assert page.markdown_model == "test-vision-model"
    assert len(page.mappings) == 0
    assert client.markdown_prompt_count == 1
    assert client.closed is False


def test_read_markdown_with_lmstudio_persists_pages_incrementally(tmp_path) -> None:
    path = tmp_path / "receipt.png"
    Image.new("RGB", (120, 60), color=(255, 255, 255)).save(path)
    client = _FakeMarkdownClient()
    persisted: list[str] = []

    result = read_markdown_with_lmstudio(
        path,
        file_hash="hash1",
        options=LmStudioMarkdownOptions(
            model="test-vision-model",
            image_max_side=RENDER_WIDTH,
            cache_enabled=False,
            markdown_max_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
        ),
        evidence_by_page={1: [{"region_id": "region-a", "text": "Total 42.00"}]},
        client=client,
        on_page=lambda page: persisted.append(page.markdown_text),
    )

    pages = result.pages
    assert result.errors == []
    assert len(pages) == 1
    assert persisted == ["# Receipt\n\nTotal 42.00"]


def test_read_markdown_with_lmstudio_rejects_placeholder_plain_markdown(
    tmp_path,
) -> None:
    path = tmp_path / "receipt.png"
    Image.new("RGB", (120, 60), color=(255, 255, 255)).save(path)
    persisted: list[str] = []

    class _PlaceholderMarkdownClient(_FakeMarkdownClient):
        def generate_page_markdown(
            self,
            page: RenderedPageImage,
            *,
            prompt: str,
            max_tokens: int,
            temperature: float,
        ) -> tuple[LmStudioPageMarkdownResponse, dict[str, Any]]:
            return LmStudioPageMarkdownResponse(markdown="n/a"), {
                "usage": {"total_tokens": 15}
            }

    result = read_markdown_with_lmstudio(
        path,
        file_hash="hash1",
        options=LmStudioMarkdownOptions(
            model="test-vision-model",
            image_max_side=RENDER_WIDTH,
            cache_enabled=False,
            markdown_max_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
        ),
        evidence_by_page={1: [{"region_id": "region-a", "text": "Total 42.00"}]},
        client=_PlaceholderMarkdownClient(),
        on_plain_page=lambda page: persisted.append(page.markdown_text),
    )

    assert result.pages == []
    assert result.errors[0]["page_no"] == 1
    assert result.errors[0]["error_type"] == "LmStudioStructuredOutputError"
    assert persisted == []


def test_read_markdown_with_lmstudio_continues_after_page_error(tmp_path) -> None:
    path = tmp_path / "scan.tiff"
    first = Image.new("RGB", (120, 60), color=(255, 255, 255))
    second = Image.new("RGB", (80, 40), color=(240, 240, 240))
    third = Image.new("RGB", (100, 50), color=(245, 245, 245))
    first.save(path, format="TIFF", save_all=True, append_images=[second, third])
    client = _FailingPageMarkdownClient(fail_page_no=2)

    result = read_markdown_with_lmstudio(
        path,
        file_hash="hash1",
        options=LmStudioMarkdownOptions(
            model="test-vision-model",
            image_max_side=RENDER_WIDTH,
            cache_enabled=False,
            markdown_max_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
        ),
        evidence_by_page={},
        client=client,
    )

    assert [page.page_no for page in result.pages] == [1, 3]
    assert [error["page_no"] for error in result.errors] == [2]


def test_iter_markdown_page_images_writes_jpeg_cache(tmp_path) -> None:
    path = tmp_path / "receipt.png"
    Image.new("RGB", (120, 60), color=(255, 255, 255)).save(path)
    cache_root = tmp_path / "cache"
    options = MarkdownRenderOptions(
        file_hash="hash1",
        image_max_side=RENDER_WIDTH,
        cache_root=str(cache_root),
    )

    first = list(iter_markdown_page_images(path, options=options))
    second = list(iter_markdown_page_images(path, options=options))

    assert len(first) == 1
    assert first[0].page.mime_type == "image/jpeg"
    assert first[0].page.render_width == RENDER_WIDTH
    assert first[0].cache_hit is False
    assert first[0].image_path is not None
    assert first[0].image_path.suffix == ".jpg"
    assert first[0].image_path.exists()
    assert first[0].metadata_path is not None
    assert first[0].metadata_path.exists()
    assert first[0].metadata["image_format"] == "JPEG"
    assert first[0].metadata["jpeg_quality"] == DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY

    assert len(second) == 1
    assert second[0].cache_hit is True
    assert second[0].page.image_sha256 == first[0].page.image_sha256


def test_iter_markdown_page_images_converts_multipage_tiff_to_jpeg(tmp_path) -> None:
    path = tmp_path / "scan.tiff"
    first = Image.new("RGB", (120, 60), color=(255, 255, 255))
    second = Image.new("RGB", (80, 40), color=(240, 240, 240))
    first.save(path, format="TIFF", save_all=True, append_images=[second])

    pages = list(
        iter_markdown_page_images(
            path,
            options=MarkdownRenderOptions(
                file_hash="hash1",
                cache_enabled=False,
                image_format="PNG",
                image_max_side=RENDER_WIDTH,
            ),
        )
    )

    assert len(pages) == TIFF_FRAME_COUNT
    assert [page.page.page_no for page in pages] == [1, 2]
    assert all(page.page.mime_type == "image/jpeg" for page in pages)
    assert all(page.metadata["image_format"] == "JPEG" for page in pages)
    assert all(page.metadata["requested_image_format"] == "PNG" for page in pages)


def test_markitdown_image_inputs_are_cached_jpeg_pages(tmp_path, monkeypatch) -> None:
    path = tmp_path / "scan.tiff"
    first = Image.new("RGB", (120, 60), color=(255, 255, 255))
    second = Image.new("RGB", (80, 40), color=(240, 240, 240))
    first.save(path, format="TIFF", save_all=True, append_images=[second])
    converter = _FakeMarkItDown()
    monkeypatch.setattr(
        markitdown_module,
        "_create_markitdown_converter",
        lambda options, use_cu: (converter, {"mode": "fake"}),
    )

    markdown, metadata = markitdown_module._convert_with_markitdown(
        path,
        file_hash="hash1",
        options=IngestOptions(
            page_markdown_cache_root=str(tmp_path / "cache"),
            page_markdown_image_max_side=RENDER_WIDTH,
        ),
        use_cu=False,
        image_rotation_degrees_by_page={},
        log=None,
    )

    assert len(converter.paths) == TIFF_FRAME_COUNT
    assert all(path.suffix == ".jpg" for path in converter.paths)
    assert all(path.exists() for path in converter.paths)
    assert "<!-- page 1 -->" in markdown
    assert "<!-- page 2 -->" in markdown
    assert metadata["normalized_image_input"] is True
    inputs = metadata["markitdown_inputs"]
    assert isinstance(inputs, list)
    assert isinstance(inputs[0], dict)
    assert inputs[0]["normalized_image"] is True


def test_lmstudio_markdown_call_uses_raw_markdown_response() -> None:
    page = RenderedPageImage(
        page_no=1,
        width=120,
        height=60,
        render_width=80,
        render_height=40,
        mime_type="image/jpeg",
        image_bytes=b"fake-jpeg",
        image_sha256="abc",
    )
    http_client = _FakeHttpClient("```markdown\n# Receipt\n\nTotal 42.00\n```")
    client = LmStudioClient(model="test-model", http_client=http_client)

    response, _raw = client.generate_page_markdown(
        page,
        prompt="Return only Markdown.",
        max_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
        temperature=0.0,
    )

    assert response.markdown == "# Receipt\n\nTotal 42.00"
    assert http_client.last_payload is not None
    assert "response_format" not in http_client.last_payload


def test_is_usable_markdown_text_rejects_placeholders() -> None:
    assert is_usable_markdown_text("# Receipt\n\nTotal 42.00") is True
    assert is_usable_markdown_text("n/a") is False
    assert is_usable_markdown_text("   ") is False


def test_markitdown_page_split_accepts_heading_and_comment_markers() -> None:
    pages = _split_page_sections(
        "## Page 1\n\nFirst\n\n<!-- page 2 -->\n\nSecond\n\n### Page 3\n\nThird"
    )

    assert pages == {1: "First", 2: "Second", 3: "Third"}


class _FakeMarkdownClient:
    def __init__(self) -> None:
        self.markdown_prompt_count = 0
        self.mapping_prompt_count = 0
        self.closed = False

    def generate_page_markdown(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageMarkdownResponse, dict[str, Any]]:
        assert page.render_width == RENDER_WIDTH
        assert "region-a" not in prompt
        assert max_tokens == DEFAULT_LMSTUDIO_CONTEXT_TOKENS
        assert temperature == 0.0
        self.markdown_prompt_count += 1
        return LmStudioPageMarkdownResponse(markdown="# Receipt\n\nTotal 42.00"), {}

    def close(self) -> None:
        self.closed = True


class _FailingPageMarkdownClient(_FakeMarkdownClient):
    def __init__(self, *, fail_page_no: int) -> None:
        super().__init__()
        self.fail_page_no = fail_page_no

    def generate_page_markdown(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageMarkdownResponse, dict[str, Any]]:
        if page.page_no == self.fail_page_no:
            raise RuntimeError("synthetic page failure")
        return super().generate_page_markdown(
            page,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )


class _FakeMarkItDown:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def convert(self, path: Path) -> SimpleNamespace:
        self.paths.append(path)
        return SimpleNamespace(markdown=f"# Converted {len(self.paths)}")


class _FakeHttpResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeHttpClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_payload: dict[str, Any] | None = None

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> _FakeHttpResponse:
        assert url.endswith("/chat/completions")
        assert headers["Content-Type"] == "application/json"
        self.last_payload = dict(json)
        return _FakeHttpResponse(self._content)

    def close(self) -> None:
        return None


def test_lmstudio_structured_output_error_is_raiseable() -> None:
    with pytest.raises(LmStudioStructuredOutputError, match="page_markdown_mapping"):
        raise LmStudioStructuredOutputError(
            stage="page_markdown_mapping",
            model="test-vision-model",
            raw_content='{"mappings": [',
            response_metadata={"stats": {"stop_reason": "maxPredictedTokensReached"}},
            reason="EOF while parsing a string",
        )
