# Exceptions

This file tracks accepted findings from Skylos and other public-source readiness
checks. Keep it small and current: fix true issues, remove stale exceptions, and
record only findings that have a concrete reason to remain.

## Active Exceptions

Reviewed on 2026-06-16 against `.logs/skylos-report.json`, generated with:

```powershell
uv run --group qa --no-sync trapo skylos-check
```

Current report-only baseline:

- Skylos findings: 428
- Danger: 74
- Dependency vulnerabilities: 1
- Quality: 353
- Secrets/PII: no findings in the current Skylos report

### Skylos Danger

- Check: `SKY-D211` SQL injection, 8 findings
  File: `trapo/db.py`, `trapo/document_markdown.py`,
  `trapo/ingest/lmstudio_orientation.py`, `trapo/migrations/versions.py`,
  `trapo/preview_cache.py`, `trapo/search_chunks.py`
  Status: false-positive
  Reason: Untrusted values are passed through DuckDB parameter binding. The
  flagged dynamic SQL fragments are fixed internal predicates, fixed migration
  column definitions, generated placeholder lists, or helper queries that take
  table/column/sequence identifiers from application constants rather than user
  input.
  Review trigger: Any change that accepts user-controlled SQL, table names,
  column names, sequence names, or arbitrary filter fragments.

- Check: `SKY-D215` path traversal, 8 findings
  File: `trapo/bootstrap.py`, `trapo/filesystem_safety.py`,
  `trapo/migrations/runner.py`, `trapo/preview_cache.py`
  Status: intentional
  Reason: The database and cache paths are local operator configuration, not
  browser-supplied paths. Document asset serving now enforces configured source
  root containment, hashing rejects non-regular inputs, ingest skips symlinked
  files, and `trapo/filesystem_safety.py` is the centralized guard that validates
  rooted regular files before no-follow reads and writes where the platform
  supports it.
  Review trigger: Any move from local single-user operation to remote or
  multi-user configuration, or any new API that accepts filesystem paths.

- Check: `SKY-D216` SSRF, 6 findings
  File: `trapo/ingest/lmstudio_client.py`,
  `trapo/ingest/lmstudio_context.py`
  Status: intentional, mitigated
  Reason: LM Studio endpoints are local CLI/config inputs for a local LLM
  workflow. `trapo/ingest/lmstudio_urls.py` now normalizes the base URL and
  rejects non-HTTP(S) schemes, missing hosts, credentials, query strings, and
  fragments before any HTTPX call.
  Review trigger: Exposing LM Studio URL selection through the FastAPI server,
  accepting URLs from untrusted users, or supporting non-local hosted model
  endpoints by default.

- Check: `SKY-D248` hardcoded internal URL, 1 finding
  File: `web/vite.config.ts`
  Status: intentional
  Reason: The hardcoded loopback URL is a Vite development-only proxy target for
  the local FastAPI server. It is not bundled into the production API client.
  Review trigger: Supporting non-local development backends or public hosted
  deployments from the same Vite config.

- Check: `SKY-D253` timing-unsafe comparison, 13 findings
  File: `web/src/documents/**`, `web/src/queries/hooks.ts`
  Status: false-positive
  Reason: `file_hash` and `fileHash` are document content identifiers used for
  routing, selection, and cache keys in browser state. They are not credentials,
  bearer tokens, MACs, or authorization secrets.
  Review trigger: Any use of document hashes as access tokens, secret material,
  authorization decisions, or equality checks on credentials.

- Check: `SKY-D260` prompt-injection string, 7 findings
  File: `trapo/cli.py`
  Status: false-positive
  Reason: The flagged strings are static Typer help text containing phrases such
  as "Maximum LM Studio output tokens"; they are not model prompts, user
  instructions, or content sent to an LLM.
  Review trigger: Moving CLI help text into LLM prompts or prompt templates.

- Check: `SKY-D324` and `SKY-D325` symlink-following file operations, 31 findings
  File: `tests/**`
  Status: false-positive
  Reason: The remaining findings are pytest fixture reads/writes under isolated
  `tmp_path` directories. Production cache/artifact paths were hardened with
  rooted regular-file checks and bounded reads.
  Review trigger: Any production `SKY-D324` or `SKY-D325` finding in a future
  report.

### Skylos SCA

- Check: `dependency_vulnerabilities`, `torch@2.12.0`
  File: `pyproject.toml`
  Status: deferred
  Reason: `torch` is required by the local Docling/MinerU OCR stack and GPU
  setup, even though Trapo does not call Torch directly. `uv lock
  --upgrade-package torch --upgrade-package torchvision` found no newer
  installable version in the configured indexes. Skylos reports the advisory as
  severity `UNKNOWN`.
  Review trigger: Any new Torch/Torchvision release in the configured PyPI and
  CUDA indexes, or before enabling `trapo skylos-check --strict` in CI.

### Skylos Quality

- Check: ingest page Markdown optional LM Studio generator
  File: `trapo/ingest/page_markdown_step.py`
  Status: intentional
  Reason: `lmstudio_markdown` depends on the locally selected LM Studio vision
  model. With reasoning-heavy models such as `google/gemma-4-26b-a4b-qat`, LM
  Studio can spend the response budget on reasoning tokens and return empty
  Markdown. Trapo defaults page Markdown to the local MarkItDown generator so a
  full ingest can complete without diagnostics errors. The MarkItDown LM Studio
  OCR plugin is also disabled by default for the same reason.
  `lmstudio_markdown` remains available through `--page-markdown-engines`, and
  the MarkItDown OCR plugin remains available through
  `--markitdown-lmstudio-ocr`; optional generator failures record partial
  metadata when individual pages fail.
  Review trigger: Changing the default LM Studio model, adding a non-reasoning
  Markdown model profile, or introducing a streaming/raw Markdown endpoint that
  reliably suppresses reasoning output.

- Check: `quality`, 353 findings
  File: repository-wide
  Status: deferred
  Reason: Quality rules are being used as a public-source readiness backlog, not
  a blocking gate yet. CI runs Ruff formatting, Ruff linting, Pyrefly type
  checks, pytest, frontend Biome checks, TypeScript checks, Vite build, and the
  Skylos report. The largest buckets are long functions, architecture-distance
  advisories, clone/complexity advisories, and layering suggestions in existing
  ingestion/server/UI surfaces.
  Review trigger: Burn down before changing CI to `trapo skylos-check --strict`;
  otherwise do not increase the quality count when touching related modules.

- Check: `SKY-F102` mutating routes without auth guard
  File: `trapo/server/app.py`
  Status: intentional
  Reason: Trapo is currently a local single-user document analysis application.
  The flagged routes update local annotation settings and visibility state.
  Review trigger: Binding the API beyond loopback, adding hosted deployment
  support, or introducing multiple users.

- Check: `SKY-R101` missing mypy/pyright policy
  File: `pyproject.toml`
  Status: false-positive
  Reason: The project standard is `pyrefly`, enforced locally and in GitHub
  Actions with `uvx pyrefly check --summarize-errors`.
  Review trigger: Removing Pyrefly or adopting mypy/pyright.

- Check: `SKY-R104` missing pre-commit policy
  File: repository root
  Status: deferred
  Reason: GitHub Actions is the enforced contributor gate. A pre-commit policy
  would be useful developer ergonomics but is not required for the initial
  public-source gate.
  Review trigger: Before the first public release, or when adding contributor
  onboarding docs.

- Check: `SKY-U005` unused dependencies
  File: `pyproject.toml`
  Status: intentional
  Reason: `ray`, `torch`, and `torchvision` are runtime dependencies of the
  local MinerU/Docling OCR stack and GPU acceleration path, even when Trapo code
  does not import them directly.
  Review trigger: Replacing MinerU/Docling, removing GPU OCR support, or
  confirming upstream packages no longer need these dependencies.

## Exception Format

Use this format when an exception is needed:

```text
- Check: <tool/rule/category>
  File: <path>
  Status: false-positive | intentional | deferred
  Reason: <why this is acceptable>
  Review trigger: <date, dependency upgrade, refactor, or issue>
```
