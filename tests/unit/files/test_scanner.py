from __future__ import annotations

import hashlib

import pytest

from app.files.scanner import BasicFileScanner

pytestmark = pytest.mark.unit


def test_basic_scanner_checks_magic_and_hash() -> None:
    payload = b"%PDF-1.7\ncontent"
    result = BasicFileScanner().scan([payload], mime_type="application/pdf")
    assert result.safe is True
    assert result.sha256 == hashlib.sha256(payload).hexdigest()

    mismatch = BasicFileScanner().scan([b"not-a-pdf"], mime_type="application/pdf")
    assert mismatch.safe is False
    assert mismatch.reason is not None
