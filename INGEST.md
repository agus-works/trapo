# Ingest Engine Analysis

Scope: exact local revisions only.

| Engine | Local repo | Requested revision | Verified commit |
|---|---|---|---|
| Docling | `$env:USERPROFILE\Desktop\Projects\docling` | `v2.101.0` | `0fd58662b075bd9e266634eb4bd05c51a098aa92` |
| MinerU | `$env:USERPROFILE\Desktop\Projects\MinerU` | `mineru-3.2.3-released` | `0a1b03d7d41dac0bb7ab8e91630aee403ef142e0` |

Legend: ✅ supported, ❌ not supported, ⭕ experimental.

Primary source files:

- Docling: `docling/datamodel/base_models.py`, `docling/document_converter.py`, `docs/usage/supported_formats.md`, `docling/pipeline/asr_pipeline.py`.
- MinerU: `mineru/cli/common.py`, `mineru/utils/guess_suffix_or_lang.py`, `mineru/cli/fast_api.py`, `docs/en/usage/quick_usage.md`, `docs/en/reference/output_files.md`.
- Infinity Parser2: `infly/Infinity-Parser2-Flash` through the local
  `infinity_parser2` package, the isolated `uvx --from infinity-parser2`
  fallback, or LM Studio when `--infinity-backend lmstudio` is selected. Trapo
  stores Infinity Parser2 document regions under `annotation_engine =
  'infinity'` and page Markdown under `markdown_engine = 'infinity_markdown'`.
  Use `--no-page-markdown` to skip the Markdown pass entirely.

## Supported Input Types

| File type / MIME type | Description | Name | Docling | MinerU |
|---|---|---:|:---:|:---:|
| `.pdf` / `application/pdf` | Portable Document Format. MinerU PDF/image pipeline and Docling standard PDF pipeline. | PDF | ✅ | ✅ |
| `.docx` / `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Microsoft Word OOXML document. | DOCX | ✅ | ✅ |
| `.dotx`, `.docm`, `.dotm` / OOXML Word template or macro variants | Word template and macro-enabled OOXML variants. | Word OOXML variants | ✅ | ❌ |
| `.pptx` / `application/vnd.openxmlformats-officedocument.presentationml.presentation` | Microsoft PowerPoint OOXML presentation. | PPTX | ✅ | ✅ |
| `.potx`, `.ppsx`, `.pptm`, `.potm`, `.ppsm` / OOXML PowerPoint template/slideshow/macro variants | PowerPoint OOXML template, slideshow, and macro-enabled variants. | PowerPoint OOXML variants | ✅ | ❌ |
| `.xlsx` / `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Microsoft Excel OOXML workbook. | XLSX | ✅ | ✅ |
| `.xlsm` / OOXML Excel macro-enabled workbook | Excel macro-enabled workbook. | XLSM | ✅ | ❌ |
| `.html`, `.htm` / `text/html` | HTML document. | HTML | ✅ | ❌ |
| `.xhtml` / `application/xhtml+xml` | XHTML document. | XHTML | ✅ | ❌ |
| `.md` / `text/markdown`, `text/x-markdown` | Markdown document. | Markdown | ✅ | ❌ |
| `.txt`, `.text` / `text/plain` | Plain text; Docling treats supported plain text as Markdown unless content detection selects USPTO text. | Plain text | ✅ | ❌ |
| `.qmd`, `.rmd`, `.Rmd` / `text/plain` | Quarto/R Markdown-style plain text markdown variants. | Markdown variants | ✅ | ❌ |
| `.adoc`, `.asciidoc`, `.asc` / `text/asciidoc` | AsciiDoc structured text. | AsciiDoc | ✅ | ❌ |
| `.csv` / `text/csv` | Comma-separated values. | CSV | ✅ | ❌ |
| `.epub` / `application/epub+zip` | Electronic publication archive. | EPUB | ✅ | ❌ |
| `.tex`, `.latex` / `text/x-tex`, `application/x-tex`, `text/x-latex` | LaTeX source document. | LaTeX | ✅ | ❌ |
| `.json` / `application/json` | JSON-serialized Docling Document. | Docling JSON | ✅ | ❌ |
| `.dclg`, `.dclg.xml` / `application/xml` | DocLang XML. | DocLang XML | ✅ | ❌ |
| `.xml`, `.txt` / `application/xml`, `text/plain` | USPTO patent XML/text detected by content. | USPTO XML | ✅ | ❌ |
| `.xml`, `.nxml` / `application/xml` | JATS article XML detected by content/doctype. | JATS XML | ✅ | ❌ |
| `.xml`, `.xbrl` / `application/xml`, `application/xhtml+xml` | XBRL filing XML detected by content. | XBRL XML | ✅ | ❌ |
| `.tar.gz` / `application/mets+xml` after METS/GBS detection | Google Books METS/GBS archive. | METS GBS | ✅ | ❌ |
| `.eml` / `message/rfc822` | RFC 822 email file. The exact code registry has `.eml`; docs mention `.msg`, but no `.msg` mapping or test exists in this pinned code. | Email | ✅ | ❌ |
| `.png` / `image/png` | PNG image. MinerU converts image bytes to a single-page PDF before parsing. | PNG | ✅ | ✅ |
| `.jpg`, `.jpeg` / `image/jpeg` | JPEG image. | JPEG | ✅ | ✅ |
| `.jp2` / `image/jp2` or JPEG 2000 MIME variants | JPEG 2000 image. | JPEG 2000 | ❌ | ✅ |
| `.tif`, `.tiff` / `image/tiff` | TIFF image. MinerU allowlist uses the detected label `tiff`. | TIFF | ✅ | ✅ |
| `.bmp` / `image/bmp` | Bitmap image. | BMP | ✅ | ✅ |
| `.webp` / `image/webp` | WebP image. | WEBP | ✅ | ✅ |
| `.gif` / `image/gif` | GIF image. Docling has a MIME mapping for `image/gif`, but `.gif` is not in its extension allowlist; direct MIME detection can still classify it as image. | GIF | ✅ | ✅ |
| `.wav` / `audio/x-wav`, `audio/wav` | Audio transcription through Docling ASR pipeline. Requires ASR dependencies. | WAV | ✅ | ❌ |
| `.mp3` / `audio/mpeg`, `audio/mp3` | Audio transcription through Docling ASR pipeline. Requires ASR dependencies. | MP3 | ✅ | ❌ |
| `.m4a` / `audio/mp4`, `audio/m4a` | Audio transcription through Docling ASR pipeline. Requires ASR dependencies. | M4A | ✅ | ❌ |
| `.aac` / `audio/aac` | Audio transcription through Docling ASR pipeline. Requires ASR dependencies. | AAC | ✅ | ❌ |
| `.ogg` / `audio/ogg` | Audio transcription through Docling ASR pipeline. Requires ASR dependencies. | OGG | ✅ | ❌ |
| `.flac` / `audio/flac`, `audio/x-flac` | Audio transcription through Docling ASR pipeline. Requires ASR dependencies. | FLAC | ✅ | ❌ |
| `.mp4` / `video/mp4` or `audio/mp4` | Video/audio media; Docling extracts/transcribes audio track, requiring ASR dependencies and ffmpeg. | MP4 | ✅ | ❌ |
| `.avi` / `video/avi`, `video/x-msvideo` | Video media; Docling extracts/transcribes audio track, requiring ASR dependencies and ffmpeg. | AVI | ✅ | ❌ |
| `.mov` / `video/quicktime` | Video media; Docling extracts/transcribes audio track, requiring ASR dependencies and ffmpeg. | MOV | ✅ | ❌ |
| `.vtt` / `text/vtt` | Web Video Text Tracks timed text. | WebVTT | ✅ | ❌ |

No input file type in these pinned code paths is explicitly marked experimental. MinerU `content_list_v2.json` is marked as a development output structure, so treat that output schema as experimental even though the input types are stable.

## Output Schema Surfaces

### Docling

Docling routes all supported inputs through `DocumentConverter` and emits a `ConversionResult`, which extends `ConversionAssets`.

Raw Docling assets to preserve:

- `version`: component versions and platform information.
- `timestamp`: save timestamp when serialized.
- `status`, `errors`: conversion state and structured errors.
- `pages`: per-page `Page` models with `page_no`, `size`, parsed page data, predictions, assembled page units, and cached page image state when available.
- `timings`: profiling items by stage.
- `confidence`: aggregate and per-page parse/layout/table/OCR confidence scores.
- `document`: lossless `DoclingDocument` export.
- `input`: `InputDocument` metadata, including path, document hash, format, size, page count, limits, backend options.
- `assembled`: intermediate assembled elements/body/headers.

Docling input-specific behavior:

- PDF, image, and METS/GBS inputs use the standard PDF-style pipeline and can expose pages, layout predictions, OCR/text cells, tables, pictures, item provenance, and page bounding boxes.
- DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, CSV, EPUB, LaTeX, email, schema XML, and Docling JSON normalize into the same `DoclingDocument` shape. Page geometry and bounding boxes are present only when the backend can derive them.
- Audio media uses `AsrPipeline`; resulting document text items carry `TrackSource` with `start_time`, `end_time`, and optional speaker. The ASR model can produce word timestamps internally; preserve the raw ASR response if word-level timing is needed later.
- WebVTT produces text items with timed `TrackSource` ranges.

Core `DoclingDocument` structures to index:

- `origin`: filename, MIME type, binary hash.
- `body`, `furniture`, `groups`: reading-order and hierarchy trees through JSON references.
- `texts`: text-bearing items such as titles, paragraphs, list items, captions, formulas, code, references, headers, and footers.
- `tables`: table items and table cell structures.
- `pictures`: image/picture items, captions, classifications, descriptions, and image refs.
- `key_value_items`: key-value regions when emitted.
- `pages`: page metadata when present in the exported document.
- `prov` on document items: page number, bounding box, and character-span provenance where emitted.

### MinerU

MinerU validates uploads through detected suffix labels from `guess_suffix_by_path`/`guess_suffix_by_bytes`; it uses explicit allowlists for PDF, images, and Office types.

Raw MinerU artifacts to preserve for every run:

- `{stem}_middle.json`: primary structured intermediate result.
- `{stem}_model.json`: raw model or converter output when requested.
- `{stem}_content_list.json`: flat readable content blocks in reading order.
- `{stem}_content_list_v2.json`: page-grouped development output; preserve but version-gate readers.
- `{stem}.md`: final markdown.
- `{stem}_origin.<mode>`: original input copied as PDF or Office file when requested.
- `images/*`: extracted crops, rendered assets, tables, charts, equations, and embedded media.
- `{stem}_layout.pdf` and `{stem}_span.pdf`: visual debugging PDFs when produced. `span.pdf` is pipeline-only.

MinerU input-specific behavior:

- PDF: processed directly by pipeline, VLM, or hybrid backends after PDFium rewrite/validation.
- Image: converted to a single-page PDF at `DEFAULT_PDF_IMAGE_DPI = 200`, then processed through the PDF path.
- DOCX/PPTX/XLSX: handled by the office backend and emitted as `_backend: "office"` middle JSON.
- Trapo's local reader can submit multiple files in one MinerU parse call. To avoid collisions when different directories contain the same filename stem, Trapo uses synthetic internal output stems per item and maps the generated artifacts back to the original source path before persistence.

MinerU coordinate and schema details:

- Pipeline `model.json`: list of detections with `cls_id`, `label`, `score`, `bbox`, and reading `index`.
- Pipeline `middle.json`: top-level `pdf_info`, `_backend`, `_version_name`. Each page can contain `preproc_blocks`, `page_idx`, `page_size`, `layout_bboxes`, `images`, `tables`, `interline_equations`, `discarded_blocks`, and `para_blocks`.
- Pipeline hierarchy: page -> level 1 visual blocks (`table`, `image`, `chart`) -> level 2 blocks -> `lines` -> `spans`. Text and equation spans carry `content`; image/table/chart spans carry `image_path`.
- VLM `model.json`: pages -> blocks with `type`, `bbox`, `angle`, `content`, and optional `score`, `block_tags`, `content_tags`, `format`. VLM model coordinates are normalized `[0,1]`.
- VLM `middle.json`: similar to pipeline, plus `angle` fields on blocks and additional list/code/discarded block types.
- `content_list.json`: flat reading-order blocks with `page_idx`, `bbox` normalized to `[0,1000]`, and content-specific fields such as `text`, `img_path`, `table_body`, `image_caption`, `table_footnote`, `code_body`, `list_items`.
- `content_list_v2.json`: page-grouped lists of `{type, content, bbox, anchor}` with structured spans. Treat as experimental/development.
- Image inputs use two page spaces: MinerU's generated PDF page (for example, a 1415x350 PNG saved at 200 DPI becomes about 509x126 PDF points) and Trapo's displayed original image page. Store and serve MinerU boxes in the displayed page space, while preserving the original `content_list` or `middle.json` bbox in metadata.
- For raster image previews, prefer the image's display metadata over engine page metadata. EXIF orientation is an explicit display transform and can be applied to source-space boxes. The preview API renders the first image frame as a normalized PNG so the browser and overlay layer use the same oriented pixels. Pixel-only rotation without EXIF is not knowable from dimensions alone; fixing that requires OCR/image orientation detection or a persisted user rotation override. Store overrides in `page_orientation_overrides.clockwise_degrees`; the value is applied after EXIF orientation and before serving preview pixels, normalizing Docling/Infinity boxes, and repairing MinerU boxes. If Docling produced many tall vertical text boxes on one side of a no-EXIF image, Trapo stores a `docling_layout_heuristic` override before MinerU and Infinity regions run; left-side vertical text maps to a 270 degree clockwise correction, while right-side vertical text maps to 90 degrees.

### Normalized page-image engines

`--annotation-engines normalized` expands to `docling_normalized` and
`mineru_normalized`. These engines use the cached `document_preview_images`
`normalized` JPG variant as their OCR input instead of the original source file.
That gives both readers the same display-oriented page pixels used by the web
preview and overlay math.

- Multipage PDFs and Pillow-exposed multipage raster inputs are split into one
  cached JPG per page or frame before the normalized engines run.
- Docling receives all normalized page JPG paths through `convert_all`, so model
  weights stay loaded and each file is processed as one batch.
- MinerU receives all normalized page JPG paths in one `do_parse` call using
  synthetic output stems, the same collision-safe batch path used by the base
  MinerU reader.
- Results are persisted to `ocr_documents` and `document_regions` under the
  normalized engine names, leaving base `docling` and `mineru` rows available
  for comparison.
- The `all` alias expands to `docling,mineru,infinity`; request
  `normalized` explicitly when page-image OCR overlays are needed.

### OCR memory controls

Trapo uses reliability-first defaults for local OCR on workstation-sized
ingests. Docling page preprocessing and the OCR, layout, and table stages
default to batch size `1`, with a bounded inter-stage queue of `8`. MinerU runs
inside a scoped `MINERU_PROCESSING_WINDOW_SIZE` default of `16` instead of the
upstream default `64`. These settings reduce allocation spikes like
RapidOCR/ONNX `bad allocation` and Docling `std::bad_alloc` failures on large
PDFs, while still allowing callers to raise throughput explicitly:

- `--docling-page-batch-size`
- `--docling-ocr-batch-size`
- `--docling-layout-batch-size`
- `--docling-table-batch-size`
- `--docling-queue-max-size`
- `--mineru-processing-window-size`

Malformed PDF font descriptors can emit repeated `FontBBox` parser warnings
directly to stderr. Trapo filters only that exact known-noisy message around
Docling and MinerU engine calls; real stage failures and other stderr output
remain visible and are persisted through ingest error handling.

### Infinity Parser2

Infinity Parser2 is the active local VLM/parser backend. It stores normalized
document regions in `document_regions` and raw parser output in `ocr_documents`
under `annotation_engine = 'infinity'`.

- The annotation engine reads normalized preview JPG artifacts so its boxes
  align with the web preview.
- Parser boxes are stored with the parsed page dimensions in metadata, and the
  region API normalizes overlays against those dimensions.
- Page Markdown uses the same page artifact cache and stores rows under
  `markdown_engine = 'infinity_markdown'`.
- `--infinity-backend lmstudio` routes Infinity Parser2 Flash through LM
  Studio's OpenAI-compatible API. In that mode, Trapo uses LM Studio's native
  model API to load `infinity-parser2-flash` at the allowlisted maximum context
  before the chat calls run.
- `--lmstudio-timeout` controls the non-streamed read timeout for LM
  Studio-backed Infinity calls. Connection, write, and pool timeouts remain
  short so unreachable LM Studio servers fail promptly while slow generations
  can complete.
- If an Infinity batch fails, Trapo retries pages independently where possible
  and records failed pages without discarding successful pages from the same
  document.
- Active region comparison is per-engine: Docling, MinerU, and Infinity rows
  remain separate so the viewer and reports can compare their outputs directly.

## DuckDB Persistence Plan

Persist raw outputs first, then build optimized indexes from immutable raw records. Raw records are the audit trail; indexed records are disposable and can be rebuilt.

Recommended storage layers:

- Content-addressed blob store on disk for original files, raw engine artifacts, images, PDFs, and large JSON. Store SHA-256/BLAKE3, byte size, MIME, and relative blob path in DuckDB.
- DuckDB JSON columns for parseable raw artifacts small enough to query directly.
- Exploded JSON node index for all raw JSON artifacts: `run_id`, `artifact_name`, `json_pointer`, `parent_pointer`, `key`, `ordinal`, `value_type`, scalar text/number/bool values, and raw JSON fragment hash.
- Typed search/location tables generated from raw JSON nodes.

Core tables:

- `source_files`: file hash, path hash, absolute path, normalized path, filename, extension, MIME, size, mtime, discovered time.
- `file_paths`: many paths per file hash, including historical path changes.
- `ingest_runs`: engine, engine version/tag/commit, backend/pipeline, options JSON, status, timings, error summary.
- `raw_artifacts`: run, artifact kind, artifact name, MIME, content hash, blob path, JSON payload, schema version.
- `pages`: run, file, page index, page label, width, height, coordinate units, default rotation, page image asset.
- `elements`: engine-neutral block/item table with JSON pointer, parent pointer, reading order, label/type/subtype, text, markdown, HTML, content JSON, confidence.
- `bboxes`: page, owning element/span/cell, x0/y0/x1/y1, coordinate origin, coordinate space (`absolute_page`, `normalized_0_1`, `normalized_0_1000`), rotation angle, source JSON pointer.
- `spans`: text-bearing spans/lines/captions/formulas/code fragments with order, text, style JSON, confidence, hyperlink metadata, source pointer.
- `tokens`: derived token/word occurrences with normalized term, char offsets, page/time references, and smallest known bbox. If an engine lacks word boxes, inherit the span or line bbox and mark `bbox_granularity`.
- `tables`: table elements with HTML, markdown, structured data JSON, row/column counts.
- `table_cells`: row/column positions, row/column spans, text, bbox, source pointer.
- `media_assets`: original files, page renders, extracted images, table crops, chart crops, equation crops, audio/video originals, with hashes and dimensions.
- `transcript_segments`: audio/VTT/ASR segments with start/end seconds, speaker, text, source pointer.
- `transcript_words`: word timestamps when the raw engine output provides them.
- `relationships`: parent/child, caption-of, footnote-of, table-cell-of, image-of, page-contains, hyperlink-to, and derived duplicate/hash relationships.
- `metadata`: engine/file/document metadata as key-value rows plus original JSON pointer.

FTS strategy:

- Build `search_units` as the canonical FTS source table. One row should represent the smallest useful retrievable unit: tokenized word, span, line, table cell, caption, paragraph, formula, code block, page header/footer, discarded block, or transcript segment.
- Include `unit_id`, `run_id`, `file_id`, `engine`, `page_id`, `element_id`, `span_id`, `table_cell_id`, `transcript_segment_id`, `text`, `normalized_text`, `language`, `unit_type`, `reading_order`, `bbox_id`, `start_time`, `end_time`, and `source_json_pointer`.
- Create DuckDB FTS indexes over `search_units.text` and optionally over `source_files.filename`, captions, table cell text, and metadata values.
- For exact word search, query FTS first, then join to `tokens` and `bboxes` to highlight the smallest known location. Fall back from word bbox -> span bbox -> line bbox -> element bbox -> page if precision is unavailable.
- Keep embeddings out of ingest for now. Future VSS/RAG should derive chunks from `search_units` and typed relationships without reparsing raw engine artifacts.

Implementation rules for our ingest layer:

- Always run the requested engines that support the input type; record
  unsupported or failed status explicitly when one engine cannot parse the file.
- Always preserve the original source file and every raw engine artifact before normalization.
- Store engine options and environment details, because OCR/ASR/layout output changes with backend, model, device, DPI, language, OCR mode, table/formula options, and VLM settings.
- Normalize coordinate systems at write time but keep original coordinates in raw JSON. Store both original and normalized bbox values when possible.
- Never discard `discarded_blocks`, page furniture, headers, footers, captions, footnotes, OCR cells, confidence scores, timings, or errors; they are searchable metadata.
- Make indexed tables rebuildable from `raw_artifacts` plus `source_files`.
