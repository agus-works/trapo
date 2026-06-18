from __future__ import annotations

import pytest

from trapo.filesystem_safety import read_text_file, write_text_file


def test_read_text_file_requires_root_containment(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError):
        read_text_file(outside, root=root, max_bytes=100)


def test_read_text_file_rejects_oversized_file(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "artifact.txt"
    path.write_text("too large", encoding="utf-8")

    with pytest.raises(ValueError, match="oversized"):
        read_text_file(path, root=root, max_bytes=4)


def test_write_text_file_rejects_output_outside_root(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        write_text_file(tmp_path / "outside.txt", "outside", root=root)
