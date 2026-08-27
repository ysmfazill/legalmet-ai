"""Storage-adapter tests — the path-traversal guard and idempotent semantics.

The intake pipeline hands the :class:`StorageService` server-generated keys, but
the adapter must nonetheless keep every object inside the storage root no matter
what key it is given. These tests assert that guarantee directly, with no HTTP
or database.
"""
from __future__ import annotations

import tempfile

import pytest

from app.core.errors import NotFoundError
from app.services.storage.local import LocalStorage


def _storage() -> LocalStorage:
    return LocalStorage(tempfile.mkdtemp(prefix="legalmet-storage-test-"))


def test_round_trip_and_idempotent_delete() -> None:
    s = _storage()
    key = s.save(key="inspections/x/a.png", data=b"hello", content_type="image/png")
    assert key == "inspections/x/a.png"
    assert s.read(key=key) == b"hello"
    assert s.exists(key=key) is True

    s.delete(key=key)
    assert s.exists(key=key) is False
    # Deleting an already-gone object is a successful no-op.
    s.delete(key=key)


def test_forward_slash_traversal_is_blocked() -> None:
    s = _storage()
    for evil in ("../../escape.png", "../../../etc/passwd", "inspections/../../../out.png"):
        with pytest.raises(NotFoundError):
            s.save(key=evil, data=b"x", content_type="image/png")
        with pytest.raises(NotFoundError):
            s.read(key=evil)


def test_backslashes_are_sanitised_into_the_root() -> None:
    """Backslashes are not path separators here — they are sanitised to '_', so a
    Windows-style traversal collapses to a single in-root filename (never an
    escape)."""
    s = _storage()
    key = s.save(key="..\\..\\win.png", data=b"z", content_type="image/png")
    assert s.exists(key=key) is True
    assert s.read(key=key) == b"z"


def test_read_missing_object_raises_not_found() -> None:
    s = _storage()
    with pytest.raises(NotFoundError):
        s.read(key="inspections/missing.png")
