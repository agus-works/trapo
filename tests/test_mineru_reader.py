from __future__ import annotations

import os
from pathlib import Path

from trapo.ingest.mineru_reader import (
    MINERU_PROCESSING_WINDOW_ENV,
    read_with_mineru,
    read_with_mineru_batch,
)

EXPECTED_BATCH_ITEMS = 2


def _install_fake_mineru(monkeypatch) -> dict[str, object]:
    captured: dict[str, object] = {}
    suffixes: list[str] = []

    class FakeCommonModule:
        @staticmethod
        def read_fn(path: Path, suffix: str) -> bytes:
            suffixes.append(suffix)
            return Path(path).read_bytes()

        @staticmethod
        def do_parse(
            output_dir: str,
            names: list[str],
            file_bytes: list[bytes],
            languages: list[str],
            **_kwargs: object,
        ) -> None:
            captured["names"] = list(names)
            captured["languages"] = list(languages)
            captured["byte_lengths"] = [len(value) for value in file_bytes]
            captured["processing_window"] = os.environ.get(MINERU_PROCESSING_WINDOW_ENV)

            output_root = Path(output_dir)
            for name in names:
                (output_root / f"{name}.md").write_text(
                    f"markdown:{name}", encoding="utf-8"
                )
                (output_root / f"{name}_middle.json").write_text(
                    '{"pdf_info": []}', encoding="utf-8"
                )

    class FakeEnumModule:
        class MakeMode:
            MM_MD = "MM_MD"

    class FakeSuffixModule:
        @staticmethod
        def guess_suffix_by_path(_path: Path) -> str:
            return ".pdf"

    def fake_import(name: str):
        if name == "mineru.cli.common":
            return FakeCommonModule
        if name == "mineru.utils.enum_class":
            return FakeEnumModule
        if name == "mineru.utils.guess_suffix_or_lang":
            return FakeSuffixModule
        raise ImportError(name)

    captured["suffixes"] = suffixes
    monkeypatch.setattr(
        "trapo.ingest.mineru_reader.importlib.import_module", fake_import
    )
    return captured


def test_read_with_mineru_batch_handles_duplicate_stems(monkeypatch, tmp_path) -> None:
    captured = _install_fake_mineru(monkeypatch)

    first = tmp_path / "a" / "report.pdf"
    second = tmp_path / "b" / "report.pdf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    results = read_with_mineru_batch([first, second])

    assert set(results.keys()) == {first, second}
    assert results[first].data["source"] == str(first)
    assert results[second].data["source"] == str(second)
    names = captured["names"]
    assert isinstance(names, list)
    assert len(names) == EXPECTED_BATCH_ITEMS
    assert names[0] != names[1]
    assert captured["processing_window"] == "16"


def test_read_with_mineru_batch_rejects_duplicate_paths(monkeypatch, tmp_path) -> None:
    _install_fake_mineru(monkeypatch)

    sample = tmp_path / "report.pdf"
    sample.write_bytes(b"single")

    try:
        read_with_mineru_batch([sample, sample])
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("Expected duplicate path validation to fail")


def test_read_with_mineru_single_file_compatibility(monkeypatch, tmp_path) -> None:
    captured = _install_fake_mineru(monkeypatch)

    sample = tmp_path / "single.pdf"
    sample.write_bytes(b"single-content")

    result = read_with_mineru(sample)

    assert result.text.startswith("markdown:")
    assert result.data["source"] == str(sample)
    assert captured["languages"] == ["en"]


def test_read_with_mineru_batch_scopes_processing_window(monkeypatch, tmp_path) -> None:
    captured = _install_fake_mineru(monkeypatch)
    sample = tmp_path / "single.pdf"
    sample.write_bytes(b"single-content")

    result = read_with_mineru_batch([sample], processing_window_size=3)

    assert result[sample].text.startswith("markdown:")
    assert captured["processing_window"] == "3"
