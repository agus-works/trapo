from __future__ import annotations

import sys
from pathlib import Path

from trapo.skylos_check import SkylosCheckOptions, _build_skylos_command, _read_counts


def test_report_only_command_runs_all_checks_without_upload(tmp_path) -> None:
    report_path = tmp_path / "skylos.json"
    sarif_path = tmp_path / "skylos.sarif.json"

    command = _build_skylos_command(
        SkylosCheckOptions(output=report_path, sarif=sarif_path)
    )

    assert command[:3] == [sys.executable, "-m", "skylos.cli"]
    assert "-a" in command
    assert "--force" in command
    assert "--gate" not in command
    assert "--no-upload" in command
    assert "--no-provenance" in command
    assert str(report_path) in command
    assert str(sarif_path) in command


def test_strict_command_uses_skylos_gate(tmp_path) -> None:
    command = _build_skylos_command(
        SkylosCheckOptions(
            path=Path("src"),
            output=tmp_path / "skylos.json",
            sarif=tmp_path / "skylos.sarif.json",
            strict=True,
            include_sca=False,
        )
    )

    assert "-a" not in command
    assert "--danger" in command
    assert "--secrets" in command
    assert "--quality" in command
    assert "--force" not in command
    assert "--gate" in command
    assert "--strict" in command


def test_read_counts_returns_category_lengths(tmp_path) -> None:
    report_path = tmp_path / "skylos.json"
    report_path.write_text(
        '{"danger": [{}, {}], "quality": [{}], "unused_functions": []}',
        encoding="utf-8",
    )

    assert _read_counts(report_path) == {
        "unused_functions": 0,
        "danger": 2,
        "quality": 1,
    }
