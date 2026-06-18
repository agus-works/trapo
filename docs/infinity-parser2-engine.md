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

The package currently depends on a newer `transformers` line than MinerU, so it
is not declared as a base Trapo dependency. Trapo first uses an in-process
`infinity_parser2` import when available; otherwise it falls back to an isolated
`uvx --from infinity-parser2` subprocess so the Infinity dependency set does not
replace MinerU's pinned runtime.

## Caveats

Infinity Parser2 currently focuses on English and Chinese documents, may degrade
on multilingual content, and does not preserve fine-grained text styling such
as bold or italic. Complex charts and rotated tables can still need comparison
against Docling, MinerU, LM Studio, and fused overlays.
