from __future__ import annotations

from typing import Any


def create_app(*args: Any, **kwargs: Any) -> Any:
    # Defer FastAPI app construction imports until callers actually serve the API.
    from trapo.server.app import create_app as _create_app  # noqa: PLC0415

    return _create_app(*args, **kwargs)


__all__ = ["create_app"]
