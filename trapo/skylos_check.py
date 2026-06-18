from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from trapo.filesystem_safety import read_text_file


DEFAULT_SKYLOS_REPORT_PATH = Path(".logs/skylos-report.json")
DEFAULT_SKYLOS_SARIF_PATH = Path(".logs/skylos-report.sarif.json")
MAX_SKYLOS_REPORT_BYTES = 20 * 1024 * 1024
SKYLOS_FINDING_KEYS = (
    "unused_functions",
    "unused_imports",
    "unused_variables",
    "unused_parameters",
    "unused_classes",
    "unused_files",
    "unused_fixtures",
    "danger",
    "quality",
    "secrets",
    "custom_rules",
    "dependency_vulnerabilities",
)


class SkylosUnavailableError(RuntimeError):
    """Raised when the Skylos package is not installed in the active environment."""


@dataclass(frozen=True)
class SkylosCheckOptions:
    path: Path = Path(".")
    output: Path = DEFAULT_SKYLOS_REPORT_PATH
    sarif: Path = DEFAULT_SKYLOS_SARIF_PATH
    confidence: int = 60
    strict: bool = False
    include_sca: bool = True


@dataclass(frozen=True)
class SkylosCheckResult:
    command: tuple[str, ...]
    output: Path
    sarif: Path
    returncode: int
    counts: dict[str, int]
    stdout: str
    stderr: str

    @property
    def total_findings(self) -> int:
        return sum(self.counts.values())


def run_skylos_check(options: SkylosCheckOptions) -> SkylosCheckResult:
    if importlib.util.find_spec("skylos.cli") is None:
        raise SkylosUnavailableError(
            "Skylos is not installed. Run `uv sync --group qa` or "
            "`uv run --group qa trapo skylos-check`."
        )

    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.sarif.parent.mkdir(parents=True, exist_ok=True)
    command = _build_skylos_command(options)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    return SkylosCheckResult(
        command=tuple(command),
        output=options.output,
        sarif=options.sarif,
        returncode=completed.returncode,
        counts=_read_counts(options.output),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _build_skylos_command(options: SkylosCheckOptions) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "skylos.cli",
        str(options.path),
        "--format",
        "json",
        "--output",
        str(options.output),
        "--sarif",
        str(options.sarif),
        "--confidence",
        str(options.confidence),
        "--no-upload",
        "--no-provenance",
    ]
    if options.include_sca:
        command.append("-a")
    else:
        command.extend(["--danger", "--secrets", "--quality"])

    if options.strict:
        command.extend(["--gate", "--strict"])
    else:
        command.append("--force")
    return command


def _read_counts(report_path: Path) -> dict[str, int]:
    try:
        payload = json.loads(
            read_text_file(
                report_path,
                root=report_path.parent,
                max_bytes=MAX_SKYLOS_REPORT_BYTES,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return {}

    counts: dict[str, int] = {}
    for key in SKYLOS_FINDING_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            counts[key] = len(value)
    return counts
