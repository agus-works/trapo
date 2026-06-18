# OpenTelemetry

Trapo reports local traces, structured application logs, and basic metrics to
the Grafana LGTM Docker image when the OTLP endpoint is reachable. The unified
compose file also runs the local DuckDB Quack endpoint. It is intended for local
development and debugging, not production.

## Start the Local Stack

```sh
docker compose up -d
uv run trapo init --db quack:localhost:9494
```

Services:

- Grafana: `http://localhost:3000`
- DuckDB Quack: `quack:localhost:9494`
- OTLP/HTTP: `http://localhost:4318`
- OTLP/gRPC: `http://localhost:4317`
- Tempo: `http://localhost:3200`
- Loki: available through Grafana Explore
- Pyroscope: `http://localhost:4040`
- Prometheus: `http://localhost:9090`

Trapo defaults to `TRAPO_OTEL_ENDPOINT=http://localhost:4318`, so commands run
from the host report to this stack when observability is enabled.

The Quack service serves the repository-local `trapo.duckdb` file from inside
the DuckDB container and uses `TRAPO_QUACK_TOKEN` for local authentication. When
the environment variable is unset, compose and Trapo both use the development
token `trapo-local-quack-token`.

Use the shared DuckDB service from host commands by passing the Quack URI:

```sh
uv run trapo migrate --db quack:localhost:9494
uv run trapo ingest ./documents --db quack:localhost:9494
uv run trapo serve --src ./documents --db quack:localhost:9494
```

Quack is still beta in DuckDB 1.5.x. It is useful here because the ingest CLI
and the API server become separate DuckDB clients attached to the same server
process, so the web UI can query status and diagnostics while ingestion writes.

## What To Look At

- Tempo shows root traces for FastAPI requests and CLI command runs such as
  `uv run trapo ingest ...`.
- Ingest command traces include child spans for per-file processing, Docling
  reads, chunking, and region rebuilds.
- Loki shows Trapo structured application logs, including ingest progress.
- Prometheus/Grafana show FastAPI instrumentation metrics plus Trapo command
  metrics such as `trapo_command_runs_total` and `trapo_command_duration_ms`.

Start with Explore against the Loki datasource and search for `trapo`, then
filter by resource service name `trapo`. For traces, use the Tempo datasource
and filter on service name `trapo`.

Profiles are intentionally optional for now. The local stack exposes Pyroscope
at `http://localhost:4040`, but Trapo does not enable continuous profiling by
default because it adds runtime overhead and the useful profile labels need to
be designed around real ingest workloads. Prefer stabilizing traces, logs, and
metrics first; add Pyroscope profiling behind an explicit environment flag when
there is a concrete performance investigation.

## Stop the Stack

```sh
docker compose down
```

Remove persisted local telemetry data:

```sh
docker compose down -v
```

## Trapo Environment

Defaults:

```sh
TRAPO_OTEL_ENABLED=true
TRAPO_OTEL_EXPORTER=otlp
TRAPO_OTEL_ENDPOINT=http://localhost:4318
TRAPO_OTEL_SERVICE_NAME=trapo
TRAPO_OTEL_CONSOLE=false
TRAPO_QUACK_TOKEN=trapo-local-quack-token
```

Set `TRAPO_OTEL_ENABLED=false` to disable instrumentation. Observability fails
open: if the local LGTM stack is not running, Trapo commands continue and
exporter failures do not block ingestion or the server.

The HTTPX instrumentation hook is optional and fails independently. If the hook
cannot be installed, Trapo still keeps OTLP export, command spans, FastAPI spans,
logs, and metrics enabled.

## Span Content

Trapo-created spans export metadata such as HTTP route, command name, file hash,
status, chunk counts, region counts, and durations. They do not export document
text or file contents. Treat the local LGTM stack as developer-only telemetry
and avoid sending it sensitive documents.

## Built-in Ingest Diagnostics

Ingest also records a local DuckDB projection of Trapo-created spans in
`ingest_diagnostic_spans` and `ingest_diagnostic_events`. This data follows the
OpenTelemetry trace shape (`trace_id`, `span_id`, `parent_span_id`, timestamps,
attributes, status, and events) but stays available even when the OTLP collector
is offline. The web app uses it for the post-run diagnostics flamegraph and
file/page waterfall views.

The local diagnostics store is intentionally post-run for v1. It records
timings and sanitized failure details for pipeline steps, engines, provider
calls, preview rendering, normalized page processing, page Markdown, and region
rebuilds. LM Studio calls additionally record local-only diagnostic details:
prompt text, request parameters, sanitized payload JSON, filesystem paths for
prompt attachments, raw successful assistant responses, HTTP status codes, and
error response bodies. Attachment images are written under
`.cache/trapo/llm-diagnostics/` when the rendered prompt image is not already
available through a caller-provided path. Base64 image data URLs are not stored
in DuckDB.

These LLM diagnostics intentionally contain prompt and model output text. Keep
them local, do not forward them to shared telemetry systems, and clear
`.cache/trapo/llm-diagnostics/` when the prompt images are no longer needed.
