from __future__ import annotations

from fastapi.testclient import TestClient

from trapo.config import RuntimeConfig
from trapo.document_regions import rebuild_document_terms
from trapo.search import search_commands
from trapo.server import create_app

HTTP_OK = 200
SEARCH_CHUNK_ID = 10
SEARCH_PAGE_NO = 2
ANNOTATION_PAGE_NO = 3
MARKDOWN_PAGE_NO = 4


def test_command_search_finds_document_navigation_command() -> None:
    results = search_commands("documents", limit=5)

    assert any(result.command_id == "nav.documents" for result in results)
    documents = next(
        result for result in results if result.command_id == "nav.documents"
    )
    assert documents.action.type == "navigate"
    assert documents.action.route == "/"


def test_command_search_api_returns_navigate_actions(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    app = create_app(db_path, config=config)

    with TestClient(app) as client:
        response = client.get("/api/commands/search", params={"q": "open documents"})

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload[0]["action"]["type"] == "navigate"
    assert any(item["command_id"] == "nav.documents" for item in payload)


def test_global_search_api_returns_document_navigation_and_highlights(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    app = create_app(db_path, config=config)

    with TestClient(app) as client:
        connection = app.state.db_connection
        connection.execute(
            """
            INSERT INTO files (file_hash, filename, extension, size_bytes)
            VALUES ('file-1', 'invoice.pdf', '.pdf', 100)
            """
        )
        connection.execute(
            """
            INSERT INTO file_locations (file_hash, path)
            VALUES ('file-1', 'C:/docs/invoice.pdf')
            """
        )
        connection.execute(
            """
            INSERT INTO document_chunks
                (chunk_id, file_hash, chunk_index, text, char_count, metadata_json)
            VALUES
                (10, 'file-1', 0, 'Invoice total amount due USD 12.50', 34, '{}'::JSON)
            """
        )
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, chunk_id, chunk_index, page_no,
                source_ref, parent_ref, label, text, context_text,
                raw_bbox_json, region_kind
            )
            VALUES (
                'region-1', 'file-1', 10, 0, 2,
                'ref-1', NULL, 'text', 'Invoice total amount due USD 12.50',
                NULL, '{"left": 10, "top": 20, "right": 200, "bottom": 40}'::JSON, 'text'
            )
            """
        )
        rebuild_document_terms(connection, "file-1")

        response = client.get("/api/search", params={"q": "total", "limit": 10})

    assert response.status_code == HTTP_OK
    payload = response.json()
    chunk = next(item for item in payload if item["source_type"] == "document_chunk")
    assert chunk["file_hash"] == "file-1"
    assert chunk["chunk_id"] == SEARCH_CHUNK_ID
    assert chunk["page_no"] == SEARCH_PAGE_NO
    assert chunk["navigation_granularity"] in {"word", "region", "chunk"}
    assert chunk["highlights"]
    assert chunk["route"]["to"] == "/"
    assert chunk["route"]["search"]["file"] == "file-1"
    assert chunk["route"]["search"]["highlight"] == "total"
    assert chunk["route"]["search"]["overlay"].startswith("region:")


def test_global_search_api_returns_annotation_region_matches(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    app = create_app(db_path, config=config)

    with TestClient(app) as client:
        connection = app.state.db_connection
        connection.execute(
            """
            INSERT INTO files (file_hash, filename, extension, size_bytes)
            VALUES ('file-annotation', 'annotation.pdf', '.pdf', 100)
            """
        )
        connection.execute(
            """
            INSERT INTO file_locations (file_hash, path)
            VALUES ('file-annotation', 'C:/docs/annotation.pdf')
            """
        )
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, annotation_engine, annotation_provider,
                annotation_model, page_no, source_ref, label, text, context_text,
                raw_bbox_json, region_kind, metadata_json
            )
            VALUES (
                'region-annotation', 'file-annotation', 'mineru', 'local-mineru',
                'pipeline', 3, 'mineru:page:3:text:1', 'body',
                'The annotation mentions Microsoft Azure credits.',
                'OCR annotation context',
                '{"left": 10, "top": 20, "right": 200, "bottom": 40}'::JSON,
                'text', '{}'::JSON
            )
            """
        )

        response = client.get("/api/search", params={"q": "azure", "limit": 10})

    assert response.status_code == HTTP_OK
    payload = response.json()
    region = next(item for item in payload if item["source_type"] == "document_region")
    assert region["file_hash"] == "file-annotation"
    assert region["page_no"] == ANNOTATION_PAGE_NO
    assert region["region_id"] == "region-annotation"
    assert region["route"]["search"]["overlay"] == "region:region-annotation"
    assert region["route"]["search"]["highlight"] == "azure"
    assert region["metadata"]["annotation_engine"] == "mineru"


def test_global_search_api_returns_page_markdown_matches(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    app = create_app(db_path, config=config)

    with TestClient(app) as client:
        connection = app.state.db_connection
        connection.execute(
            """
            INSERT INTO files (file_hash, filename, extension, size_bytes)
            VALUES ('file-markdown', 'markdown.pdf', '.pdf', 100)
            """
        )
        connection.execute(
            """
            INSERT INTO file_locations (file_hash, path)
            VALUES ('file-markdown', 'C:/docs/markdown.pdf')
            """
        )
        connection.execute(
            """
            INSERT INTO document_page_markdown (
                file_hash, page_no, markdown_engine, markdown_provider,
                markdown_model, markdown_text, metadata_json
            )
            VALUES (
                'file-markdown', 4, 'lmstudio_markdown', 'local-lmstudio',
                'test-model', '# Vendor Notes\n\nMicrosoft renewal terms apply.',
                '{}'::JSON
            )
            """
        )

        response = client.get("/api/search", params={"q": "microsoft", "limit": 10})

    assert response.status_code == HTTP_OK
    payload = response.json()
    markdown = next(item for item in payload if item["source_type"] == "page_markdown")
    assert markdown["file_hash"] == "file-markdown"
    assert markdown["page_no"] == MARKDOWN_PAGE_NO
    assert markdown["navigation_granularity"] == "record"
    assert markdown["route"]["search"] == {
        "file": "file-markdown",
        "highlight": "microsoft",
        "page": MARKDOWN_PAGE_NO,
        "view": "split",
    }
    assert markdown["highlights"][0]["field"] == "snippet"


def test_global_search_api_returns_file_matches(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    app = create_app(db_path, config=config)

    with TestClient(app) as client:
        connection = app.state.db_connection
        connection.execute(
            """
            INSERT INTO files (file_hash, filename, extension, size_bytes)
            VALUES ('file-2', 'budget-report.pdf', '.pdf', 100)
            """
        )
        connection.execute(
            """
            INSERT INTO file_locations (file_hash, path)
            VALUES ('file-2', 'C:/docs/budget-report.pdf')
            """
        )

        response = client.get("/api/search", params={"q": "budget", "limit": 10})

    assert response.status_code == HTTP_OK
    payload = response.json()
    file_result = next(item for item in payload if item["source_type"] == "file")
    assert file_result["file_hash"] == "file-2"
    assert file_result["route"]["search"]["file"] == "file-2"
