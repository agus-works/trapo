from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from trapo.ingest.lmstudio_models import (
    LmStudioOptions,
    LmStudioPageOrientationResponse,
)
from trapo.ingest.lmstudio_orientation import (
    LmStudioOrientationRequest,
    detect_lmstudio_page_orientations,
)
from trapo.ingest.page_images import RenderedPageImage


ORIENTATION_ROTATION_DEGREES = 270
ORIENTATION_CONFIDENCE = 0.91
ORIENTATION_MIN_CONFIDENCE = 0.6


class FakeOrientationClient:
    def __init__(self, response: LmStudioPageOrientationResponse) -> None:
        self.response = response
        self.calls = 0
        self.closed = False

    def detect_page_orientation(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageOrientationResponse, dict[str, Any]]:
        assert "comparison sheet" in prompt
        assert max_tokens > 0
        assert temperature == 0.0
        self.calls += 1
        return self.response, {"id": f"orientation-{page.page_no}"}

    def close(self) -> None:
        self.closed = True


def test_detect_lmstudio_page_orientations_returns_confident_override(tmp_path) -> None:
    path = _write_image(tmp_path / "sideways.jpg")
    client = FakeOrientationClient(
        LmStudioPageOrientationResponse(
            clockwise_degrees=ORIENTATION_ROTATION_DEGREES,
            confidence=ORIENTATION_CONFIDENCE,
            text_orientation="rotated_clockwise",
            rationale="Text is sideways.",
        )
    )

    result = detect_lmstudio_page_orientations(
        path,
        request=LmStudioOrientationRequest(
            file_hash="hash1",
            options=LmStudioOptions(),
            min_confidence=ORIENTATION_MIN_CONFIDENCE,
        ),
        client=client,
    )

    assert client.calls == 1
    assert client.closed is False
    assert len(result.overrides) == 1
    override = result.overrides[0]
    assert override.file_hash == "hash1"
    assert override.page_no == 1
    assert override.clockwise_degrees == ORIENTATION_ROTATION_DEGREES
    assert override.source == "lmstudio"
    assert override.confidence == ORIENTATION_CONFIDENCE
    assert result.data["pages"][0]["accepted"] is True


def test_detect_lmstudio_page_orientations_filters_low_confidence(tmp_path) -> None:
    path = _write_image(tmp_path / "unclear.jpg")
    client = FakeOrientationClient(
        LmStudioPageOrientationResponse(
            clockwise_degrees=ORIENTATION_ROTATION_DEGREES,
            confidence=0.2,
            text_orientation="unknown",
        )
    )

    result = detect_lmstudio_page_orientations(
        path,
        request=LmStudioOrientationRequest(
            file_hash="hash1",
            options=LmStudioOptions(),
            min_confidence=ORIENTATION_MIN_CONFIDENCE,
        ),
        client=client,
    )

    assert result.overrides == []
    assert result.data["pages"][0]["accepted"] is False


def test_detect_lmstudio_page_orientations_skips_manual_pages(tmp_path) -> None:
    path = _write_image(tmp_path / "manual.jpg")
    client = FakeOrientationClient(
        LmStudioPageOrientationResponse(
            clockwise_degrees=ORIENTATION_ROTATION_DEGREES,
            confidence=ORIENTATION_CONFIDENCE,
        )
    )

    result = detect_lmstudio_page_orientations(
        path,
        request=LmStudioOrientationRequest(
            file_hash="hash1",
            options=LmStudioOptions(),
            skip_pages={1},
        ),
        client=client,
    )

    assert client.calls == 0
    assert result.overrides == []
    assert result.data["pages"] == []


def _write_image(path: Path) -> Path:
    Image.new("RGB", (64, 32), color=(42, 84, 126)).save(path, format="JPEG")
    return path
