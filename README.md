# Trapo

Trapo ingests documents from a directory with local [Docling](https://github.com/docling-project/docling),
local [MinerU](https://github.com/opendatalab/MinerU), and
[Infinity Parser2](https://github.com/infiniflow/infinity-parser2), stores raw
OCR output, deterministic text chunks, page regions with bounding boxes, and
word-level terms in DuckDB, then serves a VS Code-style web UI and a small API
for browsing and searching those documents.

Trapo recursively scans files, stores SHA-256 file hashes and metadata, reads
each file with the requested annotation engines, persists chunks and page
regions, and exposes full-text and word-level search over the ingested corpus.
PDF plus PNG, JPEG, BMP, WEBP, TIFF, and GIF image previews can show
provider-derived region overlays.

## Prerequisites

- `uv`
- `bun` for the browser frontend
- LM Studio only when using `--infinity-backend lmstudio`

On native Windows with Python 3.14.5, the editable local Ray source build needs
the same toolchain environment that was used for this checkout:

```powershell
$env:BAZEL_PATH = "$env:USERPROFILE\.local\tools\bazel\bazel-7.5.0-windows-x86_64.exe"
$env:BAZEL_SH = "C:\Program Files\Git\bin\bash.exe"
$env:PATH = "C:\Program Files\Git\usr\bin;$env:PATH"
$env:BAZEL_VC = "C:\Program Files\Microsoft Visual Studio\18\Community\VC"
$env:BAZEL_VC_FULL_VERSION = "14.51.36231"
$env:BAZEL_WINSDK_FULL_VERSION = "10.0.26100.0"
$env:BAZEL_ARGS = "-c fastbuild --jobs=8"
$env:RAY_BUILD_REDIS = "0"
$env:RAY_INSTALL_JAVA = "0"
$env:RAY_DISABLE_EXTRA_CPP = "1"
uv sync
```

## Quickstart

```sh
uv sync
uv run trapo ingest ./documents --db trapo.duckdb
uv run trapo serve --src ./documents --db trapo.duckdb
```

The serve entrypoint defaults to:

```text
db:   trapo.duckdb
host: 0.0.0.0
port: 8765
src:  .
```

Relative `--db` and `--src` values are resolved from the launch directory. The
source root controls which files Trapo may read and preview; it does not move the
DuckDB file. `serve` runs as a single foreground server process; press `Ctrl+C`
to stop it. `serve` initializes or migrates the target DuckDB file before the API
starts.

Check database state:

```sh
uv run trapo status --db trapo.duckdb
```

## Commands

### Initialize or upgrade a database

```sh
uv run trapo init --db trapo.duckdb
```

### Apply migrations

```sh
uv run trapo migrate --db trapo.duckdb
```

### Ingest files

```sh
uv run trapo ingest ./documents --db trapo.duckdb
```

Useful options:

```sh
uv run trapo ingest ./documents --db trapo.duckdb --reprocess
uv run trapo ingest ./documents --db trapo.duckdb --verbose
uv run trapo ingest ./documents --db trapo.duckdb --chunker chars --max-chars 2000 --overlap-chars 200
uv run trapo ingest ./documents --db trapo.duckdb --chunker docling-hybrid --max-chunk-tokens 600
uv run trapo ingest ./documents --db trapo.duckdb --docling-device cpu --docling-num-threads 8
uv run trapo ingest ./documents --db trapo.duckdb --annotation-engines docling,mineru
uv run trapo ingest ./documents --db trapo.duckdb --annotation-engines normalized
uv run trapo ingest ./documents --db trapo.duckdb --annotation-engines all
uv run trapo ingest ./documents --db trapo.duckdb --annotation-engines infinity --page-markdown-engines infinity_markdown
uv run trapo ingest ./documents --db trapo.duckdb --annotation-engines all --infinity-backend lmstudio --infinity-model infinity-parser2-flash
uv run trapo ingest ./documents --db trapo.duckdb --annotation-engines docling
uv run trapo set-page-rotation <file-hash> 90 --page 1 --db trapo.duckdb
```

`pipeline read` (alias `pipeline docling`) runs the same local Docling read flow:

```sh
uv run trapo pipeline read ./documents --db trapo.duckdb --chunker docling-hybrid --max-chunk-tokens 600
```

Ingestion stores:

- file hash, filename, file metadata, and every observed path;
- Docling, MinerU, and Infinity Parser2 text/structured output linked to the file hash;
- document chunks with Docling chunk metadata in `document_chunks.metadata_json`;
- persisted provider-aware page regions with bounding boxes (`document_regions`);
- cached normalized page JPGs and thumbnail variants (`document_preview_images`);
- region-level word terms with bounding boxes (`document_terms`).

Trapo uses Docling for search chunking and can store MinerU and Infinity
Parser2 annotations for comparison. MinerU is invoked through a local import
when available; if MinerU is not installed in the active Python environment, the
MinerU run is recorded as an OCR error while Docling can still complete. This
checkout uses editable local path dependencies for `../MinerU` and
`../ray/python`. The local MinerU metadata is patched for Python 3.14.5, and the
local Ray checkout builds on native Windows when Bazel, Git Bash, MSVC, the
Windows SDK, and Git's `unzip.exe` are available during `uv sync`.

The preview surface supports `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tif`,
`.tiff`, and `.gif` with the same overlay coordinate model as PDFs. For image
inputs, MinerU converts the image into a generated PDF before OCR; Trapo maps
MinerU's generated-PDF/content-list coordinates back onto the original image
preview dimensions before serving overlays. Trapo also prefers image preview
metadata over engine-reported page sizes for raster assets, so EXIF-oriented
JPEGs use the same page frame as the browser image. Image preview responses are
rendered server-side as normalized PNGs for the first image frame, which keeps
EXIF display orientation consistent across browsers and overlay math.

Images whose pixels are physically sideways and have no EXIF orientation can
use `trapo set-page-rotation` to store a manual clockwise rotation. Trapo can
also infer a no-EXIF sideways page from Docling's tall vertical text boxes
before MinerU and Infinity region rebuilds. Left-side vertical text is corrected
with a 270 degree clockwise override; right-side vertical text is corrected with
a 90 degree clockwise override.

The `normalized` annotation-engine alias expands to `docling_normalized` and
`mineru_normalized`. Those pipelines run Docling and MinerU over cached
display-oriented JPG pages instead of the source PDF/image. Multipage PDFs and
Pillow-exposed multipage images are split into one normalized page image per
reader input, and each reader is called in a batch for the file. The base
`all` alias expands to `docling,mineru,infinity`; request `normalized`
explicitly when you want cache-backed page-image OCR overlays.

The default chunker is `docling-hybrid`, which uses Docling's structure-aware
chunks. The fallback `chars` chunker is available for debugging.

Infinity Parser2 can run through its Python package or through LM Studio:

```sh
uv run trapo ingest ./documents --db trapo.duckdb \
  --annotation-engines infinity \
  --page-markdown-engines infinity_markdown \
  --infinity-backend lmstudio \
  --infinity-model infinity-parser2-flash
```

When `--infinity-backend lmstudio` is selected, Trapo uses LM Studio's native
model API to load `infinity-parser2-flash` at the allowlisted maximum context
before calling the OpenAI-compatible chat endpoint. The default local endpoint
is `http://localhost:1234/v1`, `--lmstudio-timeout` controls non-streamed read
timeout, and failures are recorded against the Infinity work unit while any
successful Docling or MinerU output from the same run is kept.

Run `uv run trapo annotation-report <file-hash> --db trapo.duckdb` to compare
stored engine status, region counts, page counts, and reader metadata for one
document.

Docling GPU acceleration is controlled with
`--docling-device auto|cpu|cuda|cuda:N|mps|xpu` (default `auto`, which picks the
GPU when one is available and falls back to CPU otherwise). On Windows the
project pins the CUDA 13.0 PyTorch build (`torch`/`torchvision` from the
`pytorch-cu130` index in `pyproject.toml`) so `uv sync` installs a CUDA-enabled
PyTorch automatically; CUDA still requires a compatible NVIDIA driver. Linux and
macOS use the default PyPI wheels.

Within a single ingest run, Docling model weights (layout, table, and RapidOCR)
load once: the `DocumentConverter` is cached per accelerator and batch option
set and reused across every file instead of being rebuilt per document.

For large or image-heavy PDFs, Trapo defaults to conservative OCR batching to
avoid Docling/RapidOCR and MinerU allocation spikes. Increase these only when
the workstation has enough free memory:

```sh
uv run trapo ingest ./documents --db trapo.duckdb \
  --docling-page-batch-size 1 \
  --docling-ocr-batch-size 1 \
  --docling-layout-batch-size 1 \
  --docling-table-batch-size 1 \
  --docling-queue-max-size 8 \
  --mineru-processing-window-size 16
```

The repeated `Could not get FontBBox...` warning from malformed PDF font
metadata is filtered from engine stderr/logging while OCR is running; other
warnings and stage failures are still emitted and recorded.

### Serve the web UI and API

```sh
uv run trapo serve --src ./documents --db trapo.duckdb --host 127.0.0.1 --port 8765
```

The web UI is a VS Code-style document explorer: a file tree, a virtualized
PDF/image preview with selectable region overlays, a focused per-page Markdown
pane, a details pane for the selected region, annotation provider grouping for
Docling, MinerU, and Infinity, hide/show switches for engines
and individual overlays, tabbed ingest diagnostics for Progress, Performance,
Models, and Waterfall views, a settings page for provider/kind colors, and a
`Ctrl+K` command center for searching documents and navigating to a specific
file, page, or region. Preview zoom and 90-degree rotation controls are stored
in the URL (`zoom`, `rotation`) and transform the cached page image and overlay
layer together so scroll/pan and overlay hit targets stay aligned. Long
documents mount only the visible preview pages, while the Markdown pane requests
only the active page and prefetches nearby pages. The document explorer expands
only the active document/page path by default; annotation provider groups stay
collapsed until opened or until a specific region is selected. Details view
includes sortable name, type, size, OCR status, date modified, and date created
columns. The preview pane
uses normal mouse-wheel scrolling for zoomed pages, while Ctrl+wheel performs
cursor-centered zoom and keeps native horizontal/vertical scrollbars available.

## API

The FastAPI server exposes a small read-only surface:

- `GET /api/health`
- `GET /api/status`
- `GET /api/search?q=&limit=` — full-text and word-level document search
- `GET /api/commands/search?q=&limit=` — command palette search
- `GET /api/documents` — document summaries, including size and created/modified
  timestamps
- `GET /api/documents/{file_hash}` — document detail and pages
- `GET /api/documents/{file_hash}/regions` — page region overlays
- `GET /api/documents/{file_hash}/preview-images` — cached normalized page image
  and thumbnail metadata
- `GET /api/documents/{file_hash}/preview-images/{variant}/{page}` — cached JPG
  bytes for `normalized`, `thumb_sm`, `thumb_md`, `thumb_lg`, or `thumb_xl`
- `GET /api/documents/{file_hash}/markdown?page_no=` — persisted page Markdown;
  omit `page_no` for the full document payload
- `GET /api/documents/{file_hash}/asset` — compatibility endpoint for direct PDF
  bytes or normalized image preview PNG bytes
- `GET /api/documents/{file_hash}/pdf` — compatibility alias for preview bytes
- `GET /api/annotation-settings` — overlay style settings
- `PUT /api/annotation-settings` — update overlay style settings
- `PUT /api/documents/{file_hash}/annotations/visibility` — persist hidden state
  for one or more overlays

## Frontend client generation

The TypeScript client is generated from the FastAPI OpenAPI schema:

```sh
cd web
bun install
bun run generate-api   # writes openapi/trapo.openapi.json and regenerates the orval client
bun run build          # generate-api + routes + tsc + vite build
```

## Storybook UI development

Storybook is onboarded in the React app so UI design can be iterated without
running the full FastAPI server or exposing local corpus data. Stories live under
`web/src/stories` and are organized by component family or feature:

- `Design System/Component Inventory` lists the current web component surface.
- `Design System/UI Primitives` covers shared Radix/shadcn-style primitives.
- `Design System/Workbench Components` covers the VS Code-style panes, trees,
  tabs, status bar, inspectors, and dense table.
- `Features/Documents` covers document top bar, preview toolbar, and overlay
  details.
- `Features/Diagnostics` covers Progress, Performance, Models, Waterfall, and
  failure detail panes.

Run Storybook:

```sh
cd web
bun install
bun run storybook
```

Build Storybook for validation:

```sh
cd web
bun run build-storybook
```

Storybook fixtures must stay anonymized. Do not copy filenames, hashes, paths,
OCR text, stack traces, or user corpus values from a running Trapo instance into
stories. Use synthetic data in `web/src/stories/fixtures` instead.

## License

Copyright © 2026 Agus Works.

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Search

Search runs over DuckDB:

- a full-text index over `document_chunks.text` (DuckDB FTS), with a `LIKE` scan
  fallback;
- region-level word terms (`document_terms`) for word-precise navigation;
- annotation region text, labels, and context (`document_regions`);
- persisted per-page Markdown text (`document_page_markdown`);
- file names and paths.

Search results route to the document explorer with `file`, `page`, and `overlay`
context so the UI can focus the matching region. Results also include
`highlight=<query>` route state, which the Markdown preview uses to mark matching
text inside the rendered page.

## Observability

Trapo emits OpenTelemetry traces, logs, and metrics when an OTLP collector is
reachable. See [docs/otel.md](docs/otel.md). Observability fails open: if the
collector is unavailable, Trapo continues without exporting telemetry.

The local Docker stack is unified in [docker-compose.yml](docker-compose.yml):

```sh
docker compose up -d
uv run trapo init --db quack:localhost:9494
uv run trapo ingest ./documents --db quack:localhost:9494
uv run trapo serve --src ./documents --db quack:localhost:9494
docker compose down
```

It starts Grafana LGTM and a DuckDB Quack server on `quack:localhost:9494`.
Set `TRAPO_QUACK_TOKEN` to override the development token used by compose and
the Trapo client.

## Quality Gates

GitHub Actions runs the CI quality gates on every push and pull request. The
workflow checks Python formatting, linting, Pyrefly types, pytest, SCC file-size
reporting, Bun frontend formatting, linting, type checking, production build,
and the Skylos report command. The run writes a GitHub Actions step summary; it
does not publish build artifacts or deploy anything.

## Documentation

- [docs/schema.md](docs/schema.md) — DuckDB schema for ingest and search.
- [docs/migrations.md](docs/migrations.md) — migration framework and baseline.
- [docs/otel.md](docs/otel.md) — OpenTelemetry configuration.
- [docs/lmstudio-engine.md](docs/lmstudio-engine.md) — LM Studio backend for Infinity Parser2.
- [docs/storybook.md](docs/storybook.md) — component-first UI development with anonymized fixtures.
- [docs/skylos.md](docs/skylos.md) — dead-code, security, secrets, quality, and SCA checks.
- [INGEST.md](INGEST.md) — Docling, MinerU, and Infinity input and storage notes.
