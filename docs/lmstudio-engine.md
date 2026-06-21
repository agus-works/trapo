# LM Studio Backend

LM Studio is no longer an annotation engine in Trapo. The previous direct
layout-extraction mechanism, prompt profiles, orientation preflight, standalone
Markdown generator, smoke command, and region-combination flow have been
removed.

The supported LM Studio use is now narrow: LM Studio can host Infinity Parser2
Flash for the active `infinity` annotation engine and `infinity_markdown` page
Markdown generator.

## Active Shape

Use LM Studio only through Infinity Parser2:

```sh
uv run trapo ingest ./documents --db trapo.duckdb \
  --annotation-engines infinity \
  --page-markdown-engines infinity_markdown \
  --infinity-backend lmstudio \
  --infinity-model infinity-parser2-flash
```

In this mode:

- `ocr_documents.annotation_engine` is `infinity`
- `document_regions.annotation_engine` is `infinity`
- `document_page_markdown.markdown_engine` is `infinity_markdown`
- diagnostic model leases use provider `lmstudio` because LM Studio owns model
  loading and context for the local backend

Docling and MinerU remain independent local engines. The `all` annotation alias
expands to `docling,mineru,infinity`.

## Context Loading

Before running LM Studio-backed Infinity work, Trapo uses LM Studio's native
model API to load the target model at the allowlisted maximum context:

1. Normalize `--lmstudio-base-url` to the native LM Studio API root.
2. Read model metadata from `/api/v1/models`.
3. Best-effort unload other active models.
4. Load `infinity-parser2-flash` with its allowlisted context length.
5. Verify the loaded context before issuing OpenAI-compatible chat requests.

`infinity-parser2-flash` is allowlisted at `262144` context tokens in
`trapo/ingest/lmstudio_supported_models.py`. If LM Studio reports the target
model already loaded below the known maximum, Trapo unloads that target instance
first and reloads it with the maximum context. Use `--lmstudio-no-max-context`
only when you intentionally want to skip this preflight.

The OpenAI-compatible chat endpoint cannot set context per request, so model
lease preflight is the source of truth for local context sizing. Response
`usage.total_tokens` remains the actual tokens consumed by a call, not the
configured context capacity.

## Diagnostics

LM Studio-backed Infinity calls still write local diagnostic events:

- `llm.request`
- `llm.response`
- `llm.error`

These events keep prompt text, request parameters, sanitized payload JSON,
filesystem prompt-attachment paths, raw successful assistant responses, HTTP
status codes, and error response bodies in DuckDB for the diagnostics details
pane. Prompt images are linked from the filesystem instead of embedded as base64
in the database.

These diagnostics intentionally contain prompt and model output text. Keep them
local, do not forward them to shared telemetry systems, and clear
`.cache/trapo/llm-diagnostics/` when the prompt images are no longer needed.

## Legacy Data

Older databases can still contain rows from retired local-VLM and combined
overlay experiments. Active APIs filter those rows out so current search,
overlays, Markdown fallback, reports, and diagnostics are based on Docling,
MinerU, and Infinity only.
