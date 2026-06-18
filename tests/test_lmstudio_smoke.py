from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

import trapo.cli as trapo_cli
from trapo.cli import app
from trapo.ingest.lmstudio_models import LmStudioPageResponse, LmStudioRegionCandidate
from trapo.ingest.lmstudio_smoke import (
    LmStudioSmokeResult,
    default_smoke_options,
    run_lmstudio_smoke,
    smoke_page,
)
from trapo.ingest.lmstudio_client import (
    DEFAULT_LMSTUDIO_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_LMSTUDIO_POOL_TIMEOUT_SECONDS,
    DEFAULT_LMSTUDIO_WRITE_TIMEOUT_SECONDS,
    lmstudio_http_timeout,
)
from trapo.ingest.page_images import RenderedPageImage


SMOKE_REGION_BOX = [650, 100, 850, 600]
SMOKE_ELAPSED_SECONDS = 0.25
SMOKE_TEST_MAX_SIDE = 320
SMOKE_TEST_RENDER_HEIGHT = 180
TEST_LMSTUDIO_TIMEOUT_SECONDS = 900.0


def test_run_lmstudio_smoke_uses_schema_client_and_requires_regions() -> None:
    client = _FakeSmokeClient()

    result = run_lmstudio_smoke(
        options=default_smoke_options(model="test-model"), client=client
    )

    assert result.model == "test-model"
    assert result.base_url == "http://localhost:1234/v1"
    assert result.region_count == 1
    assert result.regions[0].box_2d == SMOKE_REGION_BOX
    assert client.closed is False
    assert client.prompt_count == 1
    assert "TRAPO SMOKE TEST" in client.last_prompt


def test_smoke_page_respects_max_side() -> None:
    page = smoke_page(max_side=SMOKE_TEST_MAX_SIDE)

    assert page.render_width == SMOKE_TEST_MAX_SIDE
    assert page.render_height == SMOKE_TEST_RENDER_HEIGHT
    assert page.mime_type == "image/png"
    assert page.data_url.startswith("data:image/png;base64,")


def test_lmstudio_http_timeout_uses_long_read_window() -> None:
    timeout = lmstudio_http_timeout(TEST_LMSTUDIO_TIMEOUT_SECONDS)

    assert timeout.connect == DEFAULT_LMSTUDIO_CONNECT_TIMEOUT_SECONDS
    assert timeout.read == TEST_LMSTUDIO_TIMEOUT_SECONDS
    assert timeout.write == DEFAULT_LMSTUDIO_WRITE_TIMEOUT_SECONDS
    assert timeout.pool == DEFAULT_LMSTUDIO_POOL_TIMEOUT_SECONDS


def test_lmstudio_smoke_cli_prints_result(monkeypatch, tmp_path) -> None:
    runner = CliRunner()

    def fake_run_lmstudio_smoke(*, options):
        return LmStudioSmokeResult(
            base_url=options.base_url,
            model=options.model,
            region_count=1,
            elapsed_seconds=SMOKE_ELAPSED_SECONDS,
            page_sha256="abc123",
            raw_response={"usage": {"total_tokens": 12}},
            regions=[
                LmStudioRegionCandidate(
                    label="title",
                    region_kind="title",
                    text="TRAPO SMOKE TEST",
                    box_2d=SMOKE_REGION_BOX,
                    confidence=0.9,
                )
            ],
        )

    monkeypatch.setattr(trapo_cli, "run_lmstudio_smoke", fake_run_lmstudio_smoke)

    result = runner.invoke(
        app,
        [
            "lmstudio-smoke",
            "--db",
            str(tmp_path / "trapo.duckdb"),
            "--lmstudio-model",
            "test-model",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "LM Studio smoke ok: model=test-model" in result.output
    assert "regions=1" in result.output
    assert "TRAPO SMOKE TEST" in result.output


class _FakeSmokeClient:
    def __init__(self) -> None:
        self.closed = False
        self.prompt_count = 0
        self.last_prompt = ""

    def detect_page_regions(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageResponse, dict[str, Any]]:
        assert page.page_no == 1
        assert max_tokens > 0
        assert temperature == 0.0
        self.prompt_count += 1
        self.last_prompt = prompt
        return (
            LmStudioPageResponse(
                regions=[
                    LmStudioRegionCandidate(
                        label="title",
                        region_kind="title",
                        text="TRAPO SMOKE TEST",
                        box_2d=SMOKE_REGION_BOX,
                    )
                ]
            ),
            {"id": "chatcmpl-smoke"},
        )

    def close(self) -> None:
        self.closed = True
