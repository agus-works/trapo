from __future__ import annotations

import hashlib

import pytest

from trapo.hash import sha256_file


def test_sha256_file_is_stable(tmp_path) -> None:
    file_path = tmp_path / "example.txt"
    file_path.write_text("hello trapo", encoding="utf-8")

    assert sha256_file(file_path) == hashlib.sha256(b"hello trapo").hexdigest()


def test_sha256_file_rejects_non_regular_paths(tmp_path) -> None:
    with pytest.raises(ValueError, match="regular files"):
        sha256_file(tmp_path)
