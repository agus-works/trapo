# DuckDB Schema

Trapo stores local Docling, MinerU, and Infinity Parser2 ingest output plus
search indexes in DuckDB.
The schema is intentionally small: raw OCR outputs, deterministic chunks, page
regions with bounding boxes, cache-backed normalized preview images,
provider-aware annotation settings, per-page Markdown equivalents, Markdown
generator status, local ingest diagnostics, and region-level terms for search.
Ingest diagnostics are stored as an OpenTelemetry-shaped trace projection so the
web UI can inspect pipeline timings and failures without requiring the external
Grafana/Tempo stack.

The schema is created by the baseline migration `0001_ingest_search_schema` plus
incremental provider, orientation, page-Markdown, preview-cache, Markdown
generator-status, and ingest-diagnostics migrations. See
[migrations.md](migrations.md).

## Tables

### `app_metadata`

Key/value store for database metadata. Holds `schema_version`.

| Column | Type | Notes |
| --- | --- | --- |
| `key` | TEXT | Primary key |
| `value` | TEXT | |
| `updated_at` | TIMESTAMP | |

### `ingest_runs`

One row per `trapo ingest` invocation.

| Column | Type | Notes |
| --- | --- | --- |
| `ingest_run_id` | BIGINT | Primary key (`ingest_run_id_seq`) |
| `source_directory` | TEXT | Scanned directory |
| `options_json` | JSON | Ingest options |
| `started_at` / `finished_at` | TIMESTAMP | |
| `status` | TEXT | `running`, `ok`, or `completed_with_errors` |
| `error` | TEXT | |

### `files`

One row per unique file hash.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Primary key (SHA-256) |
| `filename` | TEXT | |
| `extension` | TEXT | |
| `size_bytes` | BIGINT | |
| `modified_at` | TIMESTAMP | File mtime |
| `created_at` / `first_seen_at` / `last_seen_at` | TIMESTAMP | |

### `file_locations`

Every observed path for a file hash. A file may appear at multiple paths.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `path` | TEXT | Part of primary key |
| `first_seen_at` / `last_seen_at` | TIMESTAMP | |

### `docling_documents`

Compatibility table for the Docling output used by the structure-aware chunker
and search path.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Primary key |
| `ingest_run_id` | BIGINT | |
| `text` | TEXT | Docling markdown/text export |
| `docling_json` | JSON | Full Docling document export |
| `status` | TEXT | `ok` or `error` |
| `error` | TEXT | |
| `reader_provider` / `reader_model` | TEXT | `local-docling` / `docling` |
| `created_at` | TIMESTAMP | |

### `ocr_documents`

Provider-aware raw OCR/annotation output linked to a file hash.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `annotation_engine` | TEXT | Part of primary key; active engines are `docling`, `mineru`, `infinity`, and cache-backed normalized engines `docling_normalized` and `mineru_normalized` |
| `ingest_run_id` | BIGINT | |
| `text` | TEXT | Markdown/text export when available |
| `output_json` | JSON | Full provider output retained for later reprocessing |
| `status` / `error` | TEXT | `ok` or `error` plus failure detail |
| `reader_provider` / `reader_model` | TEXT | Local provider/model identity |
| `metadata_json` | JSON | Engine options such as device, backend, and language |
| `created_at` / `updated_at` | TIMESTAMP | |

### `document_chunks`

Deterministic chunks produced by the Docling hybrid chunker (or the `chars`
fallback). FTS is built over `text`.

| Column | Type | Notes |
| --- | --- | --- |
| `chunk_id` | BIGINT | Primary key (`chunk_id_seq`) |
| `file_hash` | TEXT | |
| `chunk_index` | INTEGER | Unique within a file |
| `text` | TEXT | Chunk text |
| `char_count` | INTEGER | |
| `metadata_json` | JSON | Chunker metadata, including Docling chunk meta |
| `created_at` | TIMESTAMP | |

### `document_regions`

Page regions with bounding boxes derived from Docling provenance, MinerU content
outputs, cache-backed normalized Docling/MinerU page-image outputs, and
Infinity Parser2 page-level outputs.
Used to draw overlays in PDF and supported image previews, and to anchor word
terms.

| Column | Type | Notes |
| --- | --- | --- |
| `region_id` | TEXT | Primary key (hash of file + bbox) |
| `file_hash` | TEXT | |
| `annotation_engine` | TEXT | Active engines are `docling`, `mineru`, `infinity`, `docling_normalized`, and `mineru_normalized`; legacy engine values are ignored by active APIs |
| `annotation_provider` / `annotation_model` | TEXT | Provider identity |
| `chunk_id` / `chunk_index` | BIGINT / INTEGER | Linked chunk, if any |
| `page_no` | INTEGER | |
| `source_ref` / `parent_ref` | TEXT | Provider refs |
| `label` | TEXT | Provider label |
| `text` / `context_text` | TEXT | |
| `raw_bbox_json` | JSON | `{left, top, right, bottom, coord_origin}` |
| `region_kind` | TEXT | `text`, `table`, `formula`, `image`, `header`, etc. |
| `metadata_json` | JSON | Raw provider item metadata |
| `created_at` / `updated_at` | TIMESTAMP | |

### `document_terms`

Region-level word terms with bounding boxes, used for word-precise search
navigation.

| Column | Type | Notes |
| --- | --- | --- |
| `document_term_id` | UUID | Primary key (UUIDv7) |
| `file_hash` | TEXT | |
| `page_no` | INTEGER | |
| `region_id` | TEXT | Source region |
| `annotation_engine` | TEXT | Source annotation engine |
| `chunk_id` | BIGINT | |
| `text` / `normalized_text` | TEXT | Token and casefolded token |
| `bbox_json` | JSON | Region bounding box |
| `char_start` / `char_end` | INTEGER | Token offsets within the region text |
| `metadata_json` | JSON | `bbox_granularity`, `region_kind` |
| `created_at` | TIMESTAMP | |

### `document_page_markdown`

Faithful per-page Markdown generated after annotation regions are available.
This is a document-level artifact rather than another overlay engine. The
current page Markdown pipeline stores readable raw Markdown only.

Pipeline details: [page-markdown-pipeline.md](page-markdown-pipeline.md)

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `page_no` | INTEGER | Part of primary key |
| `markdown_engine` | TEXT | Part of primary key; provider-specific engines such as `infinity_markdown`, `markitdown`, or `markitdown_cu` |
| `markdown_provider` / `markdown_model` | TEXT | Local provider/model identity |
| `markdown_text` | TEXT | Faithful Markdown for the visible page |
| `page_width` / `page_height` | DOUBLE | Display page dimensions used for the prompt image |
| `render_sha256` | TEXT | Hash of the prompt image used for generation |
| `metadata_json` | JSON | Prompt, timing, warning, and raw response metadata |
| `created_at` / `updated_at` | TIMESTAMP | |

The API also exposes `best_available_markdown` as a virtual read engine. It does
not create rows with that engine id; it selects the best persisted provider row
per page using the configured priority order.

### `document_markdown_generators`

One row per document and Markdown generator. This records whether a generator
completed or failed, which makes partial Markdown runs visible without scanning
all page rows.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `markdown_engine` | TEXT | Part of primary key; `infinity_markdown`, `markitdown`, or `markitdown_cu` |
| `ingest_run_id` | BIGINT | Ingest run that most recently attempted the generator |
| `markdown_provider` / `markdown_model` | TEXT | Provider/model identity |
| `status` | TEXT | `ok` or `error` |
| `error` | TEXT | Failure detail when `status = error` |
| `page_count` | INTEGER | Number of page Markdown rows written by that generator |
| `metadata_json` | JSON | Expected pages and generator-specific diagnostics |
| `created_at` / `updated_at` | TIMESTAMP | |

### `ingest_diagnostic_spans`

Post-run ingest pipeline spans used by the built-in diagnostics flamegraph. The
structure intentionally mirrors OpenTelemetry traces while staying local to
DuckDB.

| Column | Type | Notes |
| --- | --- | --- |
| `span_id` | TEXT | Primary key; OTEL span id when available |
| `trace_id` | TEXT | OTEL trace id when available, otherwise generated |
| `parent_span_id` | TEXT | Parent span for flamegraph nesting |
| `ingest_run_id` | BIGINT | Linked ingest run |
| `file_hash` / `page_no` | TEXT / INTEGER | Optional file/page scope |
| `name` / `pipeline_step` / `category` | TEXT | Span labels and grouping |
| `annotation_engine` | TEXT | Engine/profile when applicable |
| `status` | TEXT | `ok`, `error`, or `skipped` |
| `started_at` / `ended_at` / `duration_ms` | TIMESTAMP / DOUBLE | Timing |
| `attributes_json` | JSON | Sanitized span attributes |
| `error_type` / `error_message` / `error_stack` | TEXT | Failure detail |

### `ingest_diagnostic_events`

Log and exception events associated with diagnostic spans.
LM Studio-backed Infinity Parser2 chat-completion calls also write
`llm.request`, `llm.response`, and `llm.error` events. These events keep prompt
text, model parameters, sanitized payload JSON, filesystem prompt-attachment
paths, raw successful responses, and HTTP error bodies in `attributes_json` for
the diagnostics details pane.
Image data URLs are replaced by attachment metadata so the database does not
store base64 image payloads.

| Column | Type | Notes |
| --- | --- | --- |
| `event_id` | BIGINT | Primary key (`diagnostic_event_id_seq`) |
| `trace_id` / `span_id` | TEXT | Trace/span correlation |
| `ingest_run_id` / `file_hash` / `page_no` | BIGINT / TEXT / INTEGER | Scope |
| `timestamp` | TIMESTAMP | Event time |
| `event_type` / `name` / `severity` | TEXT | Event classification |
| `message` | TEXT | Truncated diagnostic message |
| `attributes_json` | JSON | Sanitized event attributes |

### `document_page_markdown_regions`

Legacy character-span mappings from Markdown text back to persisted annotation
regions. The current lightweight page Markdown pipeline does not populate this
table, but the schema remains so older databases can still be read.

Pipeline details: [page-markdown-pipeline.md](page-markdown-pipeline.md)

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `page_no` | INTEGER | Part of primary key |
| `markdown_engine` | TEXT | Part of primary key |
| `anchor_id` | TEXT | Part of primary key; stable Markdown span anchor |
| `region_id` | TEXT | Part of primary key; references `document_regions.region_id` |
| `char_start` / `char_end` | INTEGER | Zero-based Markdown character span, end exclusive |
| `confidence` | DOUBLE | Optional model confidence |
| `markdown_excerpt` | TEXT | Stored excerpt for debugging and UI tooltips |
| `metadata_json` | JSON | Rationale or validation metadata |
| `created_at` | TIMESTAMP | |

### `document_preview_images`

Metadata for normalized page JPGs and Windows-style thumbnail variants stored
under `.cache/trapo/preview`. The web preview and folder tile view reference
these cached API images instead of embedding source file bytes. The single-page
preview image endpoint can lazily populate just the requested page, so opening a
long cold document does not require rendering every page before the first view.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `page_no` | INTEGER | Part of primary key |
| `variant` | TEXT | Part of primary key; `normalized`, `thumb_sm`, `thumb_md`, `thumb_lg`, or `thumb_xl` |
| `page_width` / `page_height` | DOUBLE | Display page dimensions used by overlays |
| `render_width` / `render_height` | INTEGER | Cached JPG pixel dimensions |
| `mime_type` | TEXT | Currently `image/jpeg` |
| `image_bytes` | BIGINT | Encoded byte length |
| `image_sha256` | TEXT | Hash of the cached JPG |
| `cache_path` | TEXT | Local cache file path |
| `metadata_json` | JSON | Cache schema version and render metadata |
| `created_at` / `updated_at` | TIMESTAMP | |

### `page_orientation_overrides`

Optional display rotation overrides for image preview pages. These are applied
after EXIF orientation, in clockwise degrees, and affect page dimensions,
preview pixels, and overlay normalization. This table is the common storage
surface for manual corrections and Docling layout heuristic decisions for
no-EXIF sideways images.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `page_no` | INTEGER | Part of primary key |
| `clockwise_degrees` | INTEGER | `0`, `90`, `180`, or `270` |
| `source` | TEXT | `manual`, `docling_layout_heuristic`, or another detector id |
| `confidence` | DOUBLE | Optional detector confidence |
| `metadata_json` | JSON | Detector/agent metadata |
| `updated_at` | TIMESTAMP | |

### `annotation_visibility_overrides`

Persisted per-overlay hidden state used by the document viewer.

| Column | Type | Notes |
| --- | --- | --- |
| `file_hash` | TEXT | Part of primary key |
| `overlay_id` | TEXT | Part of primary key; matches API overlay ids |
| `hidden` | BOOLEAN | `true` hides the overlay until changed |
| `updated_at` | TIMESTAMP | |

### `annotation_style_settings`

DB-backed overlay colors and stroke/fill settings by engine and region kind.

| Column | Type | Notes |
| --- | --- | --- |
| `annotation_engine` | TEXT | Part of primary key |
| `region_kind` | TEXT | Part of primary key |
| `label` | TEXT | Optional provider label-specific override |
| `stroke_color` / `fill_color` | TEXT | Hex colors |
| `stroke_opacity` / `fill_opacity` | DOUBLE | `0.0` to `1.0` |
| `stroke_width` | DOUBLE | Overlay border width |
| `updated_at` | TIMESTAMP | |

### `ingest_work_units`

Per-run planner/executor state. Each row represents one planned unit such as a
file-level annotation engine, a Markdown generator, or an artifact render. The
final OCR/Markdown tables remain the canonical result store; this table is for
progress, retries, timings, and diagnostics.

| Column | Type | Notes |
| --- | --- | --- |
| `work_unit_id` | BIGINT | Primary key (`ingest_work_unit_id_seq`) |
| `ingest_run_id` / `work_key` | BIGINT / TEXT | Unique planned unit identity |
| `file_hash` / `page_no` | TEXT / INTEGER | Optional document/page scope |
| `phase` | TEXT | `orientation`, `artifact`, `annotation`, or `markdown` |
| `engine` / `provider` / `model` | TEXT | Executor identity |
| `profile` | TEXT | Optional executor profile |
| `execution_key` | TEXT | Sort key used for dependency/model batching |
| `artifact_variant` | TEXT | Optional required artifact variant |
| `status` | TEXT | `planned`, `running`, `ok`, `error`, or `skipped` |
| `attempt_count` | INTEGER | Number of executor attempts |
| `started_at` / `finished_at` / `duration_ms` | TIMESTAMP / TIMESTAMP / DOUBLE | Timing |
| `result_json` / `metadata_json` | JSON | Small result and planner metadata |
| `error` | TEXT | Failure detail |

### `ingest_page_artifacts`

Per-run page artifact index used by diagnostics and future resumable execution.
Public preview variants still live in `document_preview_images`; this table
references those cached paths and any model/Markdown prompt artifacts needed by
the planner.

| Column | Type | Notes |
| --- | --- | --- |
| `ingest_run_id` / `file_hash` / `page_no` / `variant` | BIGINT / TEXT / INTEGER / TEXT | Primary key |
| `page_width` / `page_height` | DOUBLE | Display page dimensions |
| `render_width` / `render_height` | INTEGER | Artifact pixel dimensions |
| `mime_type` / `image_sha256` | TEXT | Encoded artifact identity |
| `cache_path` | TEXT | Local artifact path when available |
| `source_variant` | TEXT | Related preview variant, if any |
| `metadata_json` | JSON | Render settings and cache metadata |
| `created_at` / `updated_at` | TIMESTAMP | |

### `ingest_model_leases`

One row per model/dependency activation window. LM Studio leases record the
requested and verified context lengths plus requested generation parameters such
as `repeat_penalty`, so low-context loads and chat-generation settings are
visible in the diagnostics UI.

| Column | Type | Notes |
| --- | --- | --- |
| `lease_id` | BIGINT | Primary key (`ingest_model_lease_id_seq`) |
| `ingest_run_id` / `execution_key` | BIGINT / TEXT | Batch scope |
| `provider` / `model` | TEXT | Activated dependency or model |
| `requested_context_tokens` / `verified_context_tokens` | INTEGER | LM Studio context data |
| `status` | TEXT | `running`, `ok`, or `error` |
| `started_at` / `finished_at` / `duration_ms` | TIMESTAMP / TIMESTAMP / DOUBLE | Timing |
| `error` | TEXT | Failure detail |
| `metadata_json` | JSON | Load status and batch metadata |

## Search indexes

- A DuckDB FTS index over `document_chunks.text` is created on demand
  (`PRAGMA create_fts_index`).
- `document_terms` provides word-level matches with bounding boxes.
- `document_regions` is scanned for annotation text, context text, labels, and
  source references so raw OCR/annotation results are searchable even when they
  are not linked to a Docling chunk.
- `document_page_markdown` is scanned for per-page Markdown search; matching
  results route with `highlight=<query>` so the Markdown preview can mark the
  rendered text.
- Secondary indexes cover `file_locations(file_hash)`,
  `ocr_documents(file_hash)`,
  `document_regions(file_hash)`, `document_regions(chunk_id)`,
  `document_regions(file_hash, annotation_engine)`,
  `document_page_markdown(file_hash)`,
  `document_markdown_generators(file_hash)`,
  `document_page_markdown_regions(file_hash, region_id)`,
  `document_preview_images(file_hash)`,
  `ingest_work_units(ingest_run_id, status)`,
  `ingest_work_units(ingest_run_id, file_hash, page_no)`,
  `ingest_work_units(ingest_run_id, execution_key, phase)`,
  `ingest_page_artifacts(ingest_run_id, file_hash, page_no)`,
  `ingest_model_leases(ingest_run_id, execution_key)`,
  `document_terms(file_hash, page_no, region_id)`, and `document_terms(chunk_id)`.
