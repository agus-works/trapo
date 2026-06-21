# Linting notes

Trapo enables Ruff's Pyflakes, selected pycodestyle, and Pylint-derived rules in
`pyproject.toml`. Prefer small refactors and named constants when they improve
readability. Use targeted suppressions only when the rule conflicts with a
framework contract, import-time performance boundary, or guard-heavy parser.

## Intentional suppressions

- `trapo/cli.py` `ingest` and `pipeline_read`: `PLR0913` is suppressed because
  Typer command handlers need explicit parameters for generated CLI help and
  shell completion.
- `trapo/cli.py` `skylos_check`: `PLR0913` is suppressed because the Typer
  wrapper exposes Skylos scan controls as explicit CLI options instead of an
  opaque passthrough string.
- `trapo/ingest/pipeline.py` `ingest_directory`: `PLR0912` is suppressed while
  the ingest loop coordinates Docling, MinerU, and Infinity per-engine failure
  handling. A future engine-dispatch abstraction should remove this exception.
- `trapo/ingest/pipeline.py` `_process_docling`: `PLR0913` is suppressed because
  the helper keeps the runtime config, run context, file identity, options, and logger
  explicit at the call site.
- `trapo/ingest/normalized_pipelines.py` `process_docling_normalized` and
  `process_mineru_normalized`: `PLR0913` is suppressed because normalized
  engines share the ingest run context, file identity, options, and logger used
  by the base engine steps.
- `trapo/ingest/__init__.py`: `PLC0415` is suppressed for the lazy pipeline
  export so importing `trapo.ingest` does not initialize Docling-facing modules.
- `trapo/ingest/docling_reader.py`: `PLC0415` is suppressed for Docling imports
  because they initialize heavyweight OCR/model plumbing and should load only
  when ingest needs them.
- `trapo/migrations/runner.py`: `PLC0415` is suppressed because migration
  versions import `Migration` from the runner, so eager import would create a
  circular dependency.
- `trapo/observability.py`: `PLC0415` is suppressed for optional Logfire and
  OpenTelemetry imports, and `PLR0913` is suppressed for telemetry event
  functions whose keyword-only dimensions keep call sites explicit.
- `trapo/diagnostics.py` `DiagnosticSpanHandle`: `PLR0902` is suppressed
  because the dataclass intentionally mirrors OpenTelemetry span state for the
  local DuckDB diagnostics projection.
- `trapo/server/__init__.py`: `PLC0415` is suppressed to keep package import
  light until callers actually construct the FastAPI app.
- `trapo/server/diagnostics.py` `diagnostic_trace` and `_diagnostic_events`:
  `PLR0913` is suppressed because the API exposes explicit indexed filters for
  run, file, page, status, text search, and limit.
- `trapo/server/provenance.py` `_add_table_candidates`: `PLR0912` is suppressed
  because Docling table JSON has related table, row, and cell shapes that are
  clearer when normalized together.
- `trapo/annotation/docling/regions.py` `rebuild_docling_output_regions`:
  `PLR0913` is suppressed because the same persistence helper writes both base
  Docling and normalized page-image Docling regions while keeping engine,
  provider, model, source metadata, and chunk-linking explicit.
- `trapo/annotation/mineru/regions.py` `rebuild_mineru_document_regions`:
  `PLR0913` is suppressed because the same persistence helper writes base MinerU
  and normalized page-image MinerU regions while keeping target pages, engine,
  provider, and model explicit.
- `trapo/server/provenance.py` `_candidate_from_mistral_pdf_element`: `PLR0911`
  is suppressed because the OCR element parser uses guard clauses for untrusted
  provider metadata.
- `trapo/server/provenance.py` `_pdf_tokens_by_page`: `PLC0415` is suppressed
  because `pdfplumber` is an optional fallback path for PDF token matching.
