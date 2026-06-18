from __future__ import annotations

from io import BytesIO
import json

from fastapi.testclient import TestClient
from PIL import Image
from pytest import approx

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.document_markdown import (
    BEST_AVAILABLE_MARKDOWN_ENGINE,
    MARKITDOWN_MARKDOWN_ENGINE,
    MarkdownRegionMapping,
    PageMarkdown,
    upsert_page_markdown,
)
from trapo.document_regions import rebuild_document_regions
from trapo.migrations import apply_migrations
from trapo.page_orientation import (
    PageOrientationOverrideUpdate,
    upsert_page_orientation_override,
)
from trapo.server import create_app
import trapo.server.app as server_app

HTTP_FORBIDDEN = 403
HTTP_OK = 200
MANUAL_ROTATION_DEGREES = 90


def _seed_document(connection, pdf_path) -> None:
    docling_json = {
        "pages": {"1": {"page_no": 1, "size": {"width": 100.0, "height": 200.0}}},
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Cloud service 0.50 USD",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "left": 10.0,
                            "top": 120.0,
                            "right": 70.0,
                            "bottom": 100.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            }
        ],
    }
    connection.execute(
        "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (1, ?, 'done')",
        [str(pdf_path.parent)],
    )
    connection.execute(
        """
        INSERT INTO files (
            file_hash, filename, extension, size_bytes, modified_at, created_at
        )
        VALUES (
            'hash1', 'invoice.pdf', '.pdf', ?,
            TIMESTAMP '2024-01-02 03:04:05',
            TIMESTAMP '2024-01-01 02:03:04'
        )
        """,
        [pdf_path.stat().st_size],
    )
    connection.execute(
        "INSERT INTO file_locations (file_hash, path) VALUES ('hash1', ?)",
        [str(pdf_path)],
    )
    connection.execute(
        """
        INSERT INTO docling_documents
            (file_hash, ingest_run_id, text, docling_json, status, error)
        VALUES ('hash1', 1, 'Cloud service 0.50 USD', ?::JSON, 'ok', NULL)
        """,
        [json.dumps(docling_json)],
    )
    connection.execute(
        """
        INSERT INTO document_chunks
            (chunk_id, file_hash, chunk_index, text, char_count, metadata_json)
        VALUES (10, 'hash1', 0, 'Cloud service 0.50 USD', 22, '{}'::JSON)
        """
    )
    rebuild_document_regions(connection, "hash1")


def _seed_image_document(connection, image_path) -> None:
    docling_json = {
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Image receipt total 42.00",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "left": 20.0,
                            "top": 30.0,
                            "right": 100.0,
                            "bottom": 70.0,
                            "coord_origin": "TOPLEFT",
                        },
                    }
                ],
            }
        ],
    }
    connection.execute(
        "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (2, ?, 'done')",
        [str(image_path.parent)],
    )
    connection.execute(
        """
        INSERT INTO files (file_hash, filename, extension, size_bytes)
        VALUES ('image-hash', 'receipt.webp', '.webp', ?)
        """,
        [image_path.stat().st_size],
    )
    connection.execute(
        "INSERT INTO file_locations (file_hash, path) VALUES ('image-hash', ?)",
        [str(image_path)],
    )
    connection.execute(
        """
        INSERT INTO docling_documents
            (file_hash, ingest_run_id, text, docling_json, status, error)
        VALUES ('image-hash', 2, 'Image receipt total 42.00', ?::JSON, 'ok', NULL)
        """,
        [json.dumps(docling_json)],
    )
    connection.execute(
        """
        INSERT INTO document_chunks
            (chunk_id, file_hash, chunk_index, text, char_count, metadata_json)
        VALUES (20, 'image-hash', 0, 'Image receipt total 42.00', 25, '{}'::JSON)
        """
    )
    rebuild_document_regions(connection, "image-hash")


def test_documents_and_regions_api_expose_docling_overlays(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)

    client = TestClient(create_app(db_path))

    documents_response = client.get("/api/documents")
    assert documents_response.status_code == HTTP_OK
    summary = documents_response.json()[0]
    assert summary["file_hash"] == "hash1"
    assert summary["chunk_count"] == 1
    assert summary["region_count"] >= 1
    assert summary["created_at"] == "2024-01-01T02:03:04"
    assert summary["modified_at"] == "2024-01-02T03:04:05"

    regions_response = client.get("/api/documents/hash1/regions")
    assert regions_response.status_code == HTTP_OK
    payload = regions_response.json()
    assert payload["document"]["pages"] == [
        {"page_no": 1, "width": 100.0, "height": 200.0}
    ]
    assert len(payload["overlays"]) >= 1
    overlay = payload["overlays"][0]
    assert overlay["bbox"] == {
        "left_pct": 10.0,
        "top_pct": 40.0,
        "width_pct": 60.0,
        "height_pct": 10.0,
    }
    assert "fact_ids" not in overlay


def test_document_detail_uses_alternate_lmstudio_profile_pages(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "strict.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))
    lmstudio_output = {
        "engine": "lmstudio_strict",
        "pages": [{"page_no": 1, "width": 300.0, "height": 400.0, "regions": []}],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        connection.execute(
            "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (3, ?, 'done')",
            [str(pdf_path.parent)],
        )
        connection.execute(
            """
            INSERT INTO files (file_hash, filename, extension, size_bytes)
            VALUES ('strict-hash', 'strict.pdf', '.pdf', ?)
            """,
            [pdf_path.stat().st_size],
        )
        connection.execute(
            "INSERT INTO file_locations (file_hash, path) VALUES ('strict-hash', ?)",
            [str(pdf_path)],
        )
        connection.execute(
            """
            INSERT INTO ocr_documents (
                file_hash, annotation_engine, ingest_run_id, text, output_json, status,
                reader_provider, reader_model, metadata_json
            )
            VALUES (
                'strict-hash', 'lmstudio_strict', 3, '', ?::JSON, 'ok',
                'local-lmstudio', 'test-model', '{}'::JSON
            )
            """,
            [json.dumps(lmstudio_output)],
        )

    client = TestClient(create_app(db_path))

    documents_response = client.get("/api/documents")
    assert documents_response.status_code == HTTP_OK
    assert documents_response.json()[0]["lmstudio_status"] == "ok"
    detail_response = client.get("/api/documents/strict-hash")
    assert detail_response.status_code == HTTP_OK
    assert detail_response.json()["pages"] == [
        {"page_no": 1, "width": 300.0, "height": 400.0}
    ]


def test_annotation_visibility_api_persists_hidden_override(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)

    client = TestClient(create_app(db_path))
    overlay_id = client.get("/api/documents/hash1/regions").json()["overlays"][0][
        "overlay_id"
    ]

    response = client.put(
        "/api/documents/hash1/annotations/visibility",
        json={"overrides": [{"overlay_id": overlay_id, "hidden": True}]},
    )
    assert response.status_code == HTTP_OK
    assert response.json()["updated"] == 1

    payload = client.get("/api/documents/hash1/regions").json()
    assert payload["overlays"][0]["hidden"] is True


def test_document_markdown_api_returns_pages_and_region_mappings(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)
        region_row = connection.execute(
            "SELECT region_id FROM document_regions WHERE file_hash = 'hash1' LIMIT 1"
        ).fetchone()
        assert region_row is not None
        region_id = str(region_row[0])
        upsert_page_markdown(
            connection,
            PageMarkdown(
                file_hash="hash1",
                page_no=1,
                markdown_model="test-model",
                markdown_text="Cloud service 0.50 USD",
                page_width=100.0,
                page_height=200.0,
                mappings=[
                    MarkdownRegionMapping(
                        anchor_id="md-p1-r1",
                        region_id=region_id,
                        char_start=0,
                        char_end=13,
                        confidence=0.95,
                        markdown_excerpt="Cloud service",
                    )
                ],
            ),
        )

    client = TestClient(create_app(db_path))

    response = client.get("/api/documents/hash1/markdown")
    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["document"]["file_hash"] == "hash1"
    assert payload["markdown_engine"] == BEST_AVAILABLE_MARKDOWN_ENGINE
    assert payload["pages"][0]["markdown_text"] == "Cloud service 0.50 USD"
    assert payload["pages"][0]["mappings"] == [
        {
            "anchor_id": "md-p1-r1",
            "region_id": region_id,
            "char_start": 0,
            "char_end": 13,
            "confidence": 0.95,
            "markdown_excerpt": "Cloud service",
            "metadata": {},
        }
    ]


def test_document_markdown_api_returns_plain_markdown_without_mappings(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)
        upsert_page_markdown(
            connection,
            PageMarkdown(
                file_hash="hash1",
                page_no=1,
                markdown_model="test-model",
                markdown_text="Cloud service 0.50 USD",
                page_width=100.0,
                page_height=200.0,
                mappings=[],
            ),
        )

    client = TestClient(create_app(db_path))

    response = client.get("/api/documents/hash1/markdown")
    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["pages"][0]["markdown_text"] == "Cloud service 0.50 USD"
    assert payload["pages"][0]["mappings"] == []


def test_document_markdown_api_filters_by_page_no(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)
        for page_no, text in [(1, "First page"), (2, "Second page")]:
            upsert_page_markdown(
                connection,
                PageMarkdown(
                    file_hash="hash1",
                    page_no=page_no,
                    markdown_model="test-model",
                    markdown_text=text,
                ),
            )

    client = TestClient(create_app(db_path))

    response = client.get("/api/documents/hash1/markdown?page_no=2")
    assert response.status_code == HTTP_OK
    payload = response.json()
    assert [page["page_no"] for page in payload["pages"]] == [2]
    assert payload["pages"][0]["markdown_text"] == "Second page"


def test_document_markdown_api_best_available_uses_markitdown_backup(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)
        upsert_page_markdown(
            connection,
            PageMarkdown(
                file_hash="hash1",
                page_no=1,
                markdown_model="test-model",
                markdown_text="LM Studio page",
            ),
        )
        upsert_page_markdown(
            connection,
            PageMarkdown(
                file_hash="hash1",
                page_no=2,
                markdown_engine=MARKITDOWN_MARKDOWN_ENGINE,
                markdown_provider="local-markitdown",
                markdown_model="markitdown-ocr",
                markdown_text="MarkItDown backup page",
            ),
        )

    client = TestClient(create_app(db_path))

    response = client.get(
        "/api/documents/hash1/markdown"
        f"?markdown_engine={BEST_AVAILABLE_MARKDOWN_ENGINE}&page_no=2"
    )
    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["markdown_engine"] == BEST_AVAILABLE_MARKDOWN_ENGINE
    assert payload["pages"][0]["markdown_text"] == "MarkItDown backup page"
    assert payload["pages"][0]["markdown_provider"] == "local-markitdown"
    assert (
        payload["pages"][0]["metadata"]["source_markdown_engine"]
        == MARKITDOWN_MARKDOWN_ENGINE
    )
    assert [engine["markdown_engine"] for engine in payload["available_engines"]] == [
        BEST_AVAILABLE_MARKDOWN_ENGINE,
        "lmstudio_markdown",
        "infinity_markdown",
        MARKITDOWN_MARKDOWN_ENGINE,
        "markitdown_cu",
    ]


def test_document_markdown_api_fallback_to_ocr(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)
        connection.execute(
            """
            INSERT INTO document_preview_images (
                file_hash, page_no, variant, page_width, page_height,
                render_width, render_height, mime_type, image_bytes,
                image_sha256, cache_path
            )
            VALUES (
                'hash1', 1, 'normalized', 100.0, 200.0,
                100, 200, 'image/jpeg', 1234,
                'sha1', 'path1'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ocr_documents (
                file_hash, annotation_engine, ingest_run_id, text, output_json, status,
                reader_provider, reader_model, metadata_json
            )
            VALUES (
                'hash1', 'docling', 1, 'Mock OCR Text from Docling', '{}'::JSON, 'ok',
                'local-docling', 'docling-model', '{}'::JSON
            )
            """
        )

    client = TestClient(create_app(db_path))

    response = client.get("/api/documents/hash1/markdown")
    assert response.status_code == HTTP_OK
    payload = response.json()
    assert len(payload["pages"]) == 1
    assert payload["pages"][0]["markdown_text"] == "Mock OCR Text from Docling"
    assert payload["pages"][0]["metadata"]["fallback"] is True
    assert payload["pages"][0]["metadata"]["source_engine"] == "docling"


def test_annotation_settings_api_updates_overlay_style(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)

    client = TestClient(create_app(db_path))
    settings = client.get("/api/annotation-settings").json()["settings"]
    docling_text = next(
        setting
        for setting in settings
        if setting["annotation_engine"] == "docling"
        and setting["region_kind"] == "text"
    )
    docling_text["style"] = {
        **docling_text["style"],
        "fill_color": "#123456",
        "stroke_color": "#123456",
    }

    response = client.put("/api/annotation-settings", json={"settings": [docling_text]})
    assert response.status_code == HTTP_OK

    payload = client.get("/api/documents/hash1/regions").json()
    assert payload["overlays"][0]["style"]["stroke_color"] == "#123456"


def test_documents_api_exposes_ocr_errors(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)
        connection.execute(
            """
            INSERT INTO ocr_documents (
                file_hash, annotation_engine, ingest_run_id, status, error,
                reader_provider, reader_model
            )
            VALUES (
                'hash1', 'mineru', 1, 'error', 'MinerU import failed',
                'local-mineru', 'mineru-pipeline'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ocr_documents (
                file_hash, annotation_engine, ingest_run_id, status, error,
                reader_provider, reader_model
            )
            VALUES (
                'hash1', 'fusion', 1, 'error', 'Fusion had no page geometry',
                'trapo', 'trapo-region-fusion-v1'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ocr_documents (
                file_hash, annotation_engine, ingest_run_id, status, error,
                reader_provider, reader_model
            )
            VALUES (
                'hash1', 'lmstudio', 1, 'error', 'LM Studio server is not running',
                'local-lmstudio', 'google/gemma-4-26b-a4b-qat'
            )
            """
        )

    client = TestClient(create_app(db_path))

    summary = client.get("/api/documents").json()[0]
    assert summary["mineru_status"] == "error"
    assert summary["mineru_error"] == "MinerU import failed"
    assert summary["lmstudio_status"] == "error"
    assert summary["lmstudio_error"] == "LM Studio server is not running"
    assert summary["fusion_status"] == "error"
    assert summary["fusion_error"] == "Fusion had no page geometry"

    payload = client.get("/api/documents/hash1/regions").json()
    assert payload["document"]["mineru_status"] == "error"
    assert payload["document"]["mineru_error"] == "MinerU import failed"
    assert payload["document"]["lmstudio_status"] == "error"
    assert payload["document"]["lmstudio_error"] == "LM Studio server is not running"
    assert payload["document"]["fusion_status"] == "error"
    assert payload["document"]["fusion_error"] == "Fusion had no page geometry"


def test_document_pdf_api_streams_pdf_with_mime_type(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)

    client = TestClient(create_app(db_path))

    pdf_response = client.get("/api/documents/hash1/pdf")
    assert pdf_response.status_code == HTTP_OK
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF-1.4")


def test_document_asset_api_rejects_paths_outside_source_root(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside_path = tmp_path / "outside.pdf"
    outside_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path), source_root=str(source_root))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, outside_path)

    client = TestClient(create_app(db_path, config=config))

    response = client.get("/api/documents/hash1/pdf")

    assert response.status_code == HTTP_FORBIDDEN
    assert "outside the configured source root" in response.json()["detail"]


def test_image_asset_and_regions_api_use_image_preview_dimensions(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "receipt.webp"
    Image.new("RGB", (200, 100), color=(120, 40, 80)).save(image_path, format="WEBP")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)

    client = TestClient(create_app(db_path))

    asset_response = client.get("/api/documents/image-hash/asset")
    assert asset_response.status_code == HTTP_OK
    assert asset_response.headers["content-type"] == "image/png"
    assert asset_response.content.startswith(b"\x89PNG")

    regions_response = client.get("/api/documents/image-hash/regions")
    assert regions_response.status_code == HTTP_OK
    payload = regions_response.json()
    assert payload["document"]["pages"] == [
        {"page_no": 1, "width": 200.0, "height": 100.0}
    ]
    assert payload["overlays"][0]["bbox"] == {
        "left_pct": 10.0,
        "top_pct": 30.0,
        "width_pct": 40.0,
        "height_pct": 40.0,
    }


def test_preview_image_cache_api_builds_and_streams_thumbnail_variants(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "receipt.webp"
    Image.new("RGB", (200, 100), color=(120, 40, 80)).save(image_path, format="WEBP")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)

    client = TestClient(create_app(db_path))

    metadata_response = client.get("/api/documents/image-hash/preview-images")
    assert metadata_response.status_code == HTTP_OK
    payload = metadata_response.json()
    variants = {image["variant"] for image in payload["images"]}
    assert {"normalized", "thumb_sm", "thumb_md", "thumb_lg", "thumb_xl"} <= variants

    thumb_response = client.get("/api/documents/image-hash/preview-images/thumb_md/1")
    assert thumb_response.status_code == HTTP_OK
    assert thumb_response.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(thumb_response.content)) as thumbnail:
        assert thumbnail.size == (96, 48)


def test_image_asset_and_regions_api_use_page_rotation_override(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "sideways.jpg"
    Image.new("RGB", (200, 100), color=(120, 40, 80)).save(image_path, format="JPEG")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)
        upsert_page_orientation_override(
            connection,
            override=PageOrientationOverrideUpdate(
                file_hash="image-hash",
                page_no=1,
                clockwise_degrees=MANUAL_ROTATION_DEGREES,
            ),
        )

    client = TestClient(create_app(db_path))

    asset_response = client.get("/api/documents/image-hash/asset")
    assert asset_response.status_code == HTTP_OK
    with Image.open(BytesIO(asset_response.content)) as preview:
        assert preview.size == (100, 200)

    payload = client.get("/api/documents/image-hash/regions").json()
    assert payload["document"]["pages"] == [
        {"page_no": 1, "width": 100.0, "height": 200.0}
    ]
    assert payload["overlays"][0]["bbox"] == {
        "left_pct": 30.0,
        "top_pct": 10.0,
        "width_pct": 40.0,
        "height_pct": 40.0,
    }


def test_image_regions_api_prefers_exif_display_dimensions_over_docling_pages(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (64, 32), color=(120, 40, 80))
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, format="JPEG", exif=exif)
    config = RuntimeConfig.from_env(db_path=str(db_path))
    docling_json = {
        "pages": {"1": {"page_no": 1, "size": {"width": 64.0, "height": 32.0}}},
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Rotated image text",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "left": 10.0,
                            "top": 5.0,
                            "right": 30.0,
                            "bottom": 20.0,
                            "coord_origin": "TOPLEFT",
                        },
                    }
                ],
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        connection.execute(
            "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (3, ?, 'done')",
            [str(image_path.parent)],
        )
        connection.execute(
            """
            INSERT INTO files (file_hash, filename, extension, size_bytes)
            VALUES ('rotated-image-hash', 'rotated.jpg', '.jpg', ?)
            """,
            [image_path.stat().st_size],
        )
        connection.execute(
            "INSERT INTO file_locations (file_hash, path) VALUES ('rotated-image-hash', ?)",
            [str(image_path)],
        )
        connection.execute(
            """
            INSERT INTO docling_documents
                (file_hash, ingest_run_id, text, docling_json, status, error)
            VALUES ('rotated-image-hash', 3, 'Rotated image text', ?::JSON, 'ok', NULL)
            """,
            [json.dumps(docling_json)],
        )
        rebuild_document_regions(connection, "rotated-image-hash")

    client = TestClient(create_app(db_path))
    asset_response = client.get("/api/documents/rotated-image-hash/asset")
    assert asset_response.status_code == HTTP_OK
    assert asset_response.headers["content-type"] == "image/png"
    with Image.open(BytesIO(asset_response.content)) as preview:
        assert preview.size == (32, 64)

    payload = client.get("/api/documents/rotated-image-hash/regions").json()
    overlay = payload["overlays"][0]

    assert payload["document"]["pages"] == [
        {"page_no": 1, "width": 32.0, "height": 64.0}
    ]
    assert overlay["bbox"]["left_pct"] == approx(37.5)
    assert overlay["bbox"]["top_pct"] == approx(15.625)
    assert overlay["bbox"]["width_pct"] == approx(46.875)
    assert overlay["bbox"]["height_pct"] == approx(31.25)


def test_regions_api_repairs_mineru_content_bbox_to_image_preview_dimensions(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "receipt.webp"
    Image.new("RGB", (200, 100), color=(120, 40, 80)).save(image_path, format="WEBP")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, annotation_engine, annotation_provider,
                annotation_model, page_no, source_ref, label, text, context_text,
                raw_bbox_json, region_kind, metadata_json
            )
            VALUES (
                'mineru-old-source-box', 'image-hash', 'mineru', 'local-mineru',
                'pipeline', 1, 'mineru:content:0', 'text', 'Image receipt total',
                'Image receipt total', ?::JSON, 'text', ?::JSON
            )
            """,
            [
                json.dumps(
                    {
                        "left": 9.671,
                        "top": 14.994,
                        "right": 242.793,
                        "bottom": 92.988,
                        "coord_origin": "TOPLEFT",
                    }
                ),
                json.dumps(
                    {
                        "source": "content_list",
                        "model": "pipeline",
                        "raw_item": {
                            "type": "text",
                            "text": "Image receipt total",
                            "bbox": [19, 119, 477, 738],
                            "page_idx": 0,
                        },
                    }
                ),
            ],
        )

    client = TestClient(create_app(db_path))

    payload = client.get("/api/documents/image-hash/regions").json()
    mineru_overlay = next(
        overlay
        for overlay in payload["overlays"]
        if overlay["annotation_engine"] == "mineru"
    )

    assert mineru_overlay["bbox"]["left_pct"] == approx(1.9)
    assert mineru_overlay["bbox"]["top_pct"] == approx(11.9)
    assert mineru_overlay["bbox"]["width_pct"] == approx(45.8)
    assert mineru_overlay["bbox"]["height_pct"] == approx(61.9)


def test_regions_api_rotates_mineru_repaired_bbox_for_page_rotation_override(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "sideways.webp"
    Image.new("RGB", (200, 100), color=(120, 40, 80)).save(image_path, format="WEBP")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)
        upsert_page_orientation_override(
            connection,
            override=PageOrientationOverrideUpdate(
                file_hash="image-hash",
                page_no=1,
                clockwise_degrees=MANUAL_ROTATION_DEGREES,
            ),
        )
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, annotation_engine, annotation_provider,
                annotation_model, page_no, source_ref, label, text, context_text,
                raw_bbox_json, region_kind, metadata_json
            )
            VALUES (
                'mineru-rotated-source-box', 'image-hash', 'mineru', 'local-mineru',
                'pipeline', 1, 'mineru:content:0', 'text', 'Rotated MinerU text',
                'Rotated MinerU text', ?::JSON, 'text', ?::JSON
            )
            """,
            [
                json.dumps(
                    {
                        "left": 20.0,
                        "top": 20.0,
                        "right": 60.0,
                        "bottom": 40.0,
                        "coord_origin": "TOPLEFT",
                    }
                ),
                json.dumps(
                    {
                        "source": "content_list",
                        "model": "pipeline",
                        "raw_item": {
                            "type": "text",
                            "text": "Rotated MinerU text",
                            "bbox": [100, 200, 300, 400],
                            "page_idx": 0,
                        },
                    }
                ),
            ],
        )

    client = TestClient(create_app(db_path))
    payload = client.get("/api/documents/image-hash/regions").json()
    mineru_overlay = next(
        overlay
        for overlay in payload["overlays"]
        if overlay["overlay_id"].endswith("mineru-rotated-source-box")
    )

    assert mineru_overlay["bbox"]["left_pct"] == approx(60.0)
    assert mineru_overlay["bbox"]["top_pct"] == approx(10.0)
    assert mineru_overlay["bbox"]["width_pct"] == approx(20.0)
    assert mineru_overlay["bbox"]["height_pct"] == approx(20.0)


def test_regions_api_does_not_double_rotate_mineru_content_bbox_for_exif_images(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (64, 32), color=(120, 40, 80))
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, format="JPEG", exif=exif)
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, annotation_engine, annotation_provider,
                annotation_model, page_no, source_ref, label, text, context_text,
                raw_bbox_json, region_kind, metadata_json
            )
            VALUES (
                'mineru-exif-display-box', 'image-hash', 'mineru', 'local-mineru',
                'pipeline', 1, 'mineru:content:0', 'text', 'Image receipt total',
                'Image receipt total', ?::JSON, 'text', ?::JSON
            )
            """,
            [
                json.dumps(
                    {
                        "left": 1.0,
                        "top": 2.0,
                        "right": 3.0,
                        "bottom": 4.0,
                        "coord_origin": "TOPLEFT",
                    }
                ),
                json.dumps(
                    {
                        "source": "content_list",
                        "model": "pipeline",
                        "raw_item": {
                            "type": "text",
                            "text": "Image receipt total",
                            "bbox": [100, 200, 500, 600],
                            "page_idx": 0,
                        },
                    }
                ),
            ],
        )

    client = TestClient(create_app(db_path))
    payload = client.get("/api/documents/image-hash/regions").json()
    mineru_overlay = next(
        overlay
        for overlay in payload["overlays"]
        if overlay["annotation_engine"] == "mineru"
    )

    assert payload["document"]["pages"] == [
        {"page_no": 1, "width": 32.0, "height": 64.0}
    ]
    assert mineru_overlay["bbox"]["left_pct"] == approx(10.0)
    assert mineru_overlay["bbox"]["top_pct"] == approx(20.0)
    assert mineru_overlay["bbox"]["width_pct"] == approx(40.0)
    assert mineru_overlay["bbox"]["height_pct"] == approx(40.0)


def test_regions_api_does_not_rotate_display_space_engine_boxes_for_exif_images(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (64, 32), color=(120, 40, 80))
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, format="JPEG", exif=exif)
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_image_document(connection, image_path)
        for region_id, engine in (
            ("lmstudio-display-box", "lmstudio"),
            ("fusion-display-box", "fusion"),
        ):
            connection.execute(
                """
                INSERT INTO document_regions (
                    region_id, file_hash, annotation_engine, annotation_provider,
                    annotation_model, page_no, source_ref, label, text, context_text,
                    raw_bbox_json, region_kind, metadata_json
                )
                VALUES (
                    ?, 'image-hash', ?, 'local', 'model', 1, ?, 'text',
                    'Display-space text', 'Display-space text', ?::JSON, 'text', '{}'::JSON
                )
                """,
                [
                    region_id,
                    engine,
                    f"{engine}:display:0",
                    json.dumps(
                        {
                            "left": 3.2,
                            "top": 12.8,
                            "right": 16.0,
                            "bottom": 38.4,
                            "coord_origin": "TOPLEFT",
                        }
                    ),
                ],
            )

    client = TestClient(create_app(db_path))
    payload = client.get("/api/documents/image-hash/regions").json()
    overlays = {
        overlay["annotation_engine"]: overlay
        for overlay in payload["overlays"]
        if overlay["overlay_id"]
        in {"region:lmstudio-display-box", "region:fusion-display-box"}
    }

    assert overlays["lmstudio"]["bbox"] == {
        "left_pct": approx(10.0),
        "top_pct": approx(20.0),
        "width_pct": approx(40.0),
        "height_pct": approx(40.0),
    }
    assert overlays["fusion"]["bbox"] == overlays["lmstudio"]["bbox"]


def test_status_api_reports_ingest_and_search_counts(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_document(connection, pdf_path)

    client = TestClient(create_app(db_path))

    response = client.get("/api/status")
    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["files"] == 1
    assert payload["chunks"] == 1
    assert payload["regions"] >= 1


def test_create_app_instruments_fastapi_with_runtime_config(
    monkeypatch, tmp_path
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path), source_root=str(tmp_path))
    captured: dict[str, object] = {}

    def fake_instrument_fastapi_app(app, runtime_config, **_kwargs) -> None:
        captured["app"] = app
        captured["config"] = runtime_config

    monkeypatch.setattr(
        server_app, "instrument_fastapi_app", fake_instrument_fastapi_app
    )

    app = server_app.create_app(db_path, config=config)

    assert captured["app"] is app
    assert captured["config"] is config
