# Infinity Parser2 Engine

Trapo can use `infly/Infinity-Parser2-Flash` through the
`infinity_parser2` Python package as an additional document parser.

## Engine IDs

- Annotation engine: `infinity`
- Page Markdown engine: `infinity_markdown`

`--annotation-engines all` includes `infinity`. `--page-markdown-engines all`
includes `infinity_markdown`. The normal defaults remain `docling,mineru` for
annotations and `markitdown` for page Markdown.

## Ingest Shape

The annotation engine reads normalized preview JPGs so its boxes align with the
web preview. Raw parser output is stored in `ocr_documents`, while normalized
layout boxes are stored in `document_regions` and participate in region-term
search and fusion.

Infinity Parser2 returns `[x1, y1, x2, y2]` boxes in the coordinate space of the
rendered preview image it parsed. Trapo stores that preview page size in region
metadata and the region API normalizes `infinity` overlays against that metadata,
not the source PDF point size. This avoids global offset and scale drift when a
source page such as `3482x2612` is rendered to a preview image such as
`1600x1200`.

The Markdown engine reads the same page Markdown JPEG artifacts used by other
page-image Markdown generators. Infinity Parser2 expects filesystem paths, so
this engine creates cache artifacts even when general page Markdown caching is
disabled.

## CLI Controls

```text
--infinity-model
--infinity-backend
--infinity-batch-size
--infinity-device
--infinity-torch-dtype
```

Defaults are `infly/Infinity-Parser2-Flash`, `vllm-engine`, batch size `1`,
device `cuda`, and torch dtype `bfloat16`. The device and dtype options apply
to the `transformers` backend.

`--infinity-model infinity-parser2-flash` is accepted as a short alias for
`infly/Infinity-Parser2-Flash`. Explicit Hugging Face IDs and local model paths
are passed through unchanged.

Use `--infinity-backend lmstudio` when Infinity Parser2 Flash is hosted by the
local LM Studio OpenAI-compatible API at `http://localhost:1234/v1`. In that
mode, the same short model alias is preserved as the LM Studio model ID.

The package currently depends on a newer `transformers` line than MinerU, so it
is not declared as a base Trapo dependency. Trapo first uses an in-process
`infinity_parser2` import when available; otherwise it falls back to an isolated
`uvx --from infinity-parser2` subprocess so the Infinity dependency set does not
replace MinerU's pinned runtime.

The isolated fallback installs `torch`, `torchvision`, and `accelerate`
explicitly because `qwen_vl_utils` imports TorchVision during package startup
and the local Transformers backend uses device mapping. On Windows with Python
3.14, `vllm` does not currently have a compatible wheel chain, so the fallback
maps requested `vllm-engine` runs to Infinity Parser2's local `transformers`
backend. Use `vllm-server` only when a separate compatible vLLM server is
already running.

## Error Isolation

Infinity Parser2 receives Trapo-rendered JPG page artifacts instead of source
PDFs, so page images are generated and normalized once before engine execution.
If a multi-page Infinity batch fails, Trapo retries each page in that batch with
the already-created parser instance and records only the failed page as an
engine error. Successful pages in the same file still persist annotation regions
or page Markdown.

## Example

```powershell
uv sync && uv run trapo init --db quack:localhost:9494 && uv run trapo status --db quack:localhost:9494 && uv run trapo ingest "C:\Users\Bangonkali\Desktop\test\ontology-works\demo-04" --db quack:localhost:9494 --annotation-engines infinity --page-markdown-engines infinity_markdown --infinity-backend lmstudio --infinity-model infinity-parser2-flash --verbose
```

## Caveats

Infinity Parser2 currently focuses on English and Chinese documents, may degrade
on multilingual content, and does not preserve fine-grained text styling such
as bold or italic. Complex charts and rotated tables can still need comparison
against Docling, MinerU, LM Studio, and fused overlays.
