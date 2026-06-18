# Migrations

Trapo uses a small, code-defined migration framework in
[`trapo/migrations`](../trapo/migrations). Migrations are ordered, checksummed,
and recorded in the `schema_migrations` table.

## Baseline

The schema starts with a baseline migration and then additive feature
migrations:

- `0001_ingest_search_schema` — creates the ingest and search schema
  (`app_metadata`, `ingest_runs`, `files`, `file_locations`, `docling_documents`,
  `document_chunks`, `document_regions`, `document_terms`) plus secondary
  indexes. See [schema.md](schema.md).
- `0002_provider_annotation_schema` — adds provider-aware OCR output storage
  (`ocr_documents`), annotation engine columns on regions and terms, DB-backed
  annotation visibility overrides, and DB-backed annotation style settings.
- `0003_page_orientation_overrides` — stores image page rotation corrections
  used by normalized preview pixels and overlay normalization.
- `0004_page_markdown` — stores per-page Markdown output and Markdown-to-region
  span mappings.
- `0005_preview_image_cache` — stores metadata for normalized page JPGs and
  thumbnail variants served from `.cache/trapo/preview`.
- `0006_markdown_generator_status` — records per-document status for each
  page Markdown generator so partial runs can be diagnosed quickly.
- `0007_ingest_diagnostics` — records OTEL-shaped ingest diagnostic spans and
  events for in-product flamegraph and waterfall debugging.

Trapo focuses on local Docling/MinerU ingest and document search, so the schema
no longer contains the legacy ontology, embedding, finance, chat, work-queue,
retrieval, graph, or evaluation tables.

## Applying migrations

`trapo init`, `trapo migrate`, and `trapo serve` all apply pending migrations.

```sh
uv run trapo migrate --db trapo.duckdb
```

## Compatibility

There is no backwards compatibility with pre-simplification databases. A DuckDB
file created by an older Trapo version records migration ids that this baseline
does not define; opening it raises a clear error
(`Database uses unsupported legacy or unknown migrations`). Create a fresh
database with `trapo init` or re-ingest the source directory.

## Adding a migration

Append a `Migration` to `MIGRATIONS` in
[`trapo/migrations/versions.py`](../trapo/migrations/versions.py). Each migration
has a stable `migration_id`, a description, and an `apply` callable. The runner
records a checksum so applied migrations cannot silently change.
