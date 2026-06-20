# LM Studio Annotation Engine

This design uses LM Studio as a third local annotation backend alongside
Docling and MinerU. It is intended for a single-user Windows workstation where
LM Studio owns GPU loading and offload for `google/gemma-4-26b-a4b-qat`.

## Approach

1. Render every supported file into page images.
   - PDFs use PDFium via `pypdfium2`, one rendered page per request.
   - TIFF, GIF, WEBP, JPEG, and PNG use Pillow `ImageSequence`, so multi-frame
     formats are split page-by-page or frame-by-frame.
   - EXIF orientation is applied before sending the image to the model.

2. Run a typed per-page LM Studio request.
   - Endpoint: OpenAI-compatible `/v1/chat/completions`.
   - Payload: one image plus a prompt.
   - Response: JSON schema with page `regions`.
   - Coordinates: `box_2d = [y0, left, y1, right]` on a `[0,1000]` grid.
   - The observed `google/gemma-4-26b-a4b-qat` LM Studio convention uses
     bottom-origin y values, so Trapo defaults `--lmstudio-box-origin
     bottomleft` and converts to displayed top-left coordinates at write time.

3. Feed prior engines as evidence, not truth.
   - Docling and MinerU regions are converted to the same `[0,1000]` grid.
   - The prompt tells the model to use those boxes as hints while treating the
     actual page image as authoritative.
   - Missing Docling or MinerU output is normal; the LM Studio pass can still run.

4. Persist like any other engine.
   - Raw LM Studio output is stored in `ocr_documents` under
     `annotation_engine = 'lmstudio'` for the balanced profile.
   - Optional prompt profiles write separate engine labels:
     `lmstudio_strict` and `lmstudio_recall`.
   - Normalized regions are stored in `document_regions`.
   - Region terms are rebuilt from the unified region table.

5. Build the fused overlay.
   - Trapo clusters Docling, MinerU, and LM Studio boxes by page and region kind.
   - Tight consensus boxes are preferred over broad outliers.
   - Single-engine boxes are preserved when the other engines have no matching
     result.
   - The balanced fused overlay is stored as `annotation_engine = 'fusion'`.
   - Alternative profiles can also be stored as `fusion_conservative` and
     `fusion_recall` with `--fusion-profiles all`.

6. Generate page Markdown.
   - The page Markdown pass runs by default after raw annotation engines and
     fusion so persisted Markdown is available with the preview.
   - Use `--no-page-markdown` to skip this pass for OCR-only ingest runs.
   - PDF pages and image frames are rendered into Markdown-specific JPEG prompt
     artifacts by default (`120` DPI, max side `1280`, quality `82`) and cached
     under `.cache/trapo/page-markdown/` for inspection and reuse.
   - Non-JPEG raster sources are converted to JPEG. Multi-page TIFF files are
     split into one JPEG per frame.
   - A single call asks LM Studio for raw page Markdown from only the page image
     and a short prompt, with no embedded region ids, HTML, or hints from other
     OCR engines.
   - Successful pages persist immediately; later page failures do not discard
     page Markdown that was already stored.
   - Markdown is stored in `document_page_markdown`.
   - See [page-markdown-pipeline.md](page-markdown-pipeline.md) for the detailed
     call shapes, Mermaid diagrams, evidence selection rules, and PDF context
     overflow fix.

## Supported Engines And Model Context

Trapo supports the following LM Studio-backed generation surfaces:

| Surface | Engine or option | Purpose | LM Studio model source |
| --- | --- | --- | --- |
| Annotation | `lmstudio` | Balanced region extraction used by default for LM Studio annotations. | `--lmstudio-model` |
| Annotation | `lmstudio_strict` | Stricter optional prompt profile from `--lmstudio-profiles strict` or `all`. | `--lmstudio-model` |
| Annotation | `lmstudio_recall` | Higher-recall optional prompt profile from `--lmstudio-profiles recall` or `all`. | `--lmstudio-model` |
| Markdown | `lmstudio_markdown` | Direct page-image-to-Markdown generation. | `--lmstudio-model` |
| Markdown OCR plugin | `markitdown` with `--markitdown-lmstudio-ocr` | MarkItDown conversion with local LM Studio OCR assistance. | `--lmstudio-model` |

These surfaces require a vision-capable LM Studio model. On the local
workstation, Trapo treats these LM Studio model IDs as supported for annotation
and Markdown generation:

| LM Studio model ID | Type | Max load context tokens |
| --- | --- | ---: |
| `google/gemma-4-26b-a4b-qat` | VLM | `262144` |
| `qwen/qwen3.5-27b` | VLM | `262144` |
| `qwen/qwen3.5-35b-a3b` | VLM | `262144` |
| `nvidia/nemotron-3-nano-omni` | VLM | `262144` |
| `qwen/qwen3-vl-8b` | VLM | `262144` |
| `infinity-parser2-flash` | VLM | `262144` |
| `qwen/qwen3-vl-30b` | VLM | `262144` |
| `allenai/olmocr-2-7b` | VLM | `128000` |

Non-vision models in the same LM Studio install, such as `granite-4.1-8b`,
`granite-4.1-30b`, and embedding models, are not supported for these image
annotation or image Markdown surfaces.

Before ingest, Trapo queries LM Studio's native model API and loads the selected
`--lmstudio-model` with the largest known context length. The native API value
is preferred when available, and Trapo also keeps the table above as a guard so
known supported models are not accidentally loaded at smaller contexts. For
`google/gemma-4-26b-a4b-qat`, that means the load request must use `262144`
context tokens rather than LM Studio's low default such as `4096`.

## Why This Shape

- The LM Studio model can refine or challenge Docling/MinerU layout results
  without forcing a new storage model.
- Fused regions keep source engine IDs and contribution flags, so the combined
  result is auditable and can be compared against raw Docling, MinerU, and
  LM Studio overlays.
- Fused raw output includes an `agreement_summary` with per-engine coverage,
  single-engine-only regions, multi-engine regions, and support combinations.
  This gives a lightweight quality signal for choosing profiles without adding
  another storage table.
- Fusion profiles let the same raw engine outputs produce multiple candidate
  overlays without rerunning OCR/VLM inference:
  `conservative` resists broad boxes, `balanced` is the default, and `recall`
  allows looser consensus for documents where one engine misses regions.
- LM Studio prompt profiles let the same page image and evidence hints produce
  alternative candidate overlays. The default `balanced` profile remains the
  canonical `lmstudio` source for fusion; `strict` and `recall` are stored
  separately for side-by-side review.
- `trapo annotation-report <file-hash>` summarizes stored engine/profile status,
  region counts, page counts, elapsed LM Studio time, and fusion agreement for
  one document so prompt/fusion profiles can be compared without ad hoc SQL.
- Page-by-page requests keep memory and logs understandable on a local machine.
- Each LM Studio chat-completion request writes built-in diagnostics events for
  the prompt, parameters, sanitized payload, prompt attachment path, raw
  successful result, HTTP status code, and error response body. Prompt images are
  linked from the filesystem instead of embedded as base64 in DuckDB.
- A strict schema makes bad model output fail visibly instead of quietly drawing
  incorrect overlays.
- The Markdown pass stores readable Markdown separately from overlay regions, so
  generated text remains useful even when overlay data changes.
- The `[0,1000]` grid makes boxes independent of prompt image resize while still
  mapping back to PDF points or displayed image pixels. Persisting the y-axis
  origin keeps the conversion explicit if a future model follows top-left
  coordinates instead.

## Current Caveats

- LM Studio must already be running. By default, Trapo asks LM Studio to load
  the target vision model at its maximum supported context before ingest.
- GPU optimization is configured in LM Studio, not inside Trapo.
- `--lmstudio-timeout` defaults to 240 seconds in the CLI and is used as the per-page read
  timeout for non-streamed generation. Trapo keeps connect, write, and pool
  waits short, so this mainly gives LM Studio enough time to finish slow vision
  pages after the request has been accepted.
- `trapo lmstudio-smoke` sends a generated one-page document through the same
  strict JSON region path and fails if LM Studio is unreachable, returns invalid
  schema, or returns no regions.
- Physically rotated images without EXIF can use `trapo set-page-rotation`.
  When LM Studio is requested, `--lmstudio-orientation auto` is enabled by
  default and runs a small strict-JSON orientation preflight before the region
  pass. Accepted decisions write `page_orientation_overrides` with
  `source = 'lmstudio'`; manual overrides are left untouched. The stored
  override is applied to page images before LM Studio vision calls, to preview
  pixels, and to all overlay normalization. If Gemma reports an uncertain
  orientation, Trapo may still store a `docling_layout_heuristic` override from
  Docling's vertical text-box layout before the LM Studio region pass. The
  fallback maps left-side vertical text to 270 degrees clockwise and right-side
  vertical text to 90 degrees clockwise.
- The current implementation is one typed page-agent with multiple prompt
  profiles. Future variants can add Pydantic-AI reviewer agents or voting
  passes while still writing alternatives under separate engine labels or
  metadata.
- Page Markdown generation adds one additional LM Studio call per page and is
  enabled by default so the split Markdown/preview review surface is populated
  during normal ingest. Use `--no-page-markdown` to disable it for faster runs.
- The detailed page-Markdown pipeline notes document why PDFs were not skipped,
  why oversized evidence caused LM Studio `400` responses, and how compact
  preferred evidence keeps the requests within model context limits.
- At ingest start, Trapo can use LM Studio's native REST API to load the
  configured model at its advertised maximum context length. This is enabled by
  default through `--lmstudio-max-context` and can be skipped with
  `--lmstudio-no-max-context`. The OpenAI-compatible chat endpoint cannot set
  context per request, so this preflight is the current way to maximize local
  context before chat calls run. Response `usage.total_tokens` remains the
  actual tokens consumed by a call, not the configured context capacity. For
  page Markdown, the default output-token setting auto-expands to the detected
  context budget; explicit lower `--page-markdown-max-tokens` values are
  preserved.
