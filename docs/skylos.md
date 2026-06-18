# Skylos checks

Trapo uses [Skylos](https://skylos.dev) as a required project dependency for
local-first dead-code, security, secrets, quality, and dependency checks. CI
runs the Skylos report after the Python, SCC, and Bun checks. Existing accepted
findings are tracked in [EXCEPTIONS.md](../EXCEPTIONS.md); strict enforcement
should only be enabled after that baseline has been burned down or converted to
machine-readable suppressions.

## Install

Install the normal project dependencies:

```powershell
uv sync
```

To test against the sibling Skylos checkout during local development:

```powershell
uv run --with-editable ..\skylos trapo skylos-check --strict
```

## Run

Run the comprehensive report:

```powershell
uv run trapo skylos-check 2>&1 | tee .\.logs\skylos-report.log
```

The wrapper writes:

- `.logs/skylos-report.json` for machine-readable findings.
- `.logs/skylos-report.sarif.json` for code-scanning tools.

Use `--strict` when validating that the repository is ready for clean-state
enforcement:

```powershell
uv run trapo skylos-check --strict 2>&1 | tee .\.logs\skylos-strict.log
```

Use `--no-sca` only when the network-backed dependency vulnerability scan is not
available:

```powershell
uv run trapo skylos-check --no-sca
```

## Public-source readiness

Before publishing, run the normal project checks and then the Skylos scan:

```powershell
uv run ruff format --check . 2>&1 | tee .\.logs\ruff-format.log
uvx pyrefly check --summarize-errors 2>&1 | tee .\.logs\pyrefly.log
uv run ruff check . 2>&1 | tee .\.logs\ruff-check.log
uv run pytest 2>&1 | tee .\.logs\pytest.log
Push-Location web
bun run format:check 2>&1 | tee ..\.logs\web-format.log
bun run lint 2>&1 | tee ..\.logs\web-lint.log
bun run typecheck 2>&1 | tee ..\.logs\web-typecheck.log
bun run build 2>&1 | tee ..\.logs\web-build.log
Pop-Location
uv run trapo skylos-check 2>&1 | tee .\.logs\skylos-report.log
```

Fix true findings. Record accepted false positives, intentional dynamic entry
points, or deferred risks in [EXCEPTIONS.md](../EXCEPTIONS.md). Each exception
must include the rule or category, the file, the reason, and the next review
trigger.

The CI workflow runs on every push and pull request. It checks Python format,
lint, types, tests, frontend format, frontend lint, frontend types, and frontend
build. It also writes SCC file-size and Skylos reports so the current backlog
stays visible. Steps continue after failures so the build summary shows every
result; the final aggregation step fails the job when any required command
fails. The workflow writes a GitHub Actions step summary instead of uploading
artifacts.

Treat [EXCEPTIONS.md](../EXCEPTIONS.md) as the baseline ledger: new true
security, secrets, dependency, or dead-code findings should be fixed before
merge, and the baseline should shrink as quality cleanup lands.

## Configuration

Skylos configuration lives in `[tool.skylos]` in `pyproject.toml`. Generated
frontend clients, build outputs, caches, and sample ingestion fixtures are
excluded so the scan focuses on maintained source. The `[tool.skylos.gate]`
thresholds describe the target clean state; enforcement is controlled by the
`trapo skylos-check --strict` flag.

The Trapo wrapper always passes `--no-upload` and `--no-provenance` so local and
CI scans do not upload source, metadata, or AI-provenance data to external
services.
