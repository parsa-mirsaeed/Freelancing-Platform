from __future__ import annotations

import hashlib
import socket
import struct
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScanResult:
    safe: bool
    sha256: str
    reason: str | None = None


class FileScanner:
    def scan(self, chunks: Iterable[bytes], *, mime_type: str) -> ScanResult:
        raise NotImplementedError


class BasicFileScanner(FileScanner):
    def scan(self, chunks: Iterable[bytes], *, mime_type: str) -> ScanResult:
        digest = hashlib.sha256()
        prefix = b""
        saw_nul = False
        for chunk in chunks:
            digest.update(chunk)
            if len(prefix) < 16:
                prefix += chunk[: 16 - len(prefix)]
            if b"\x00" in chunk[:4096]:
                saw_nul = True
        reason = _magic_mismatch(prefix, mime_type, saw_nul=saw_nul)
        return ScanResult(safe=reason is None, sha256=digest.hexdigest(), reason=reason)


class ClamAVScanner(FileScanner):
    def __init__(self, *, host: str, port: int, timeout_seconds: float = 15.0) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def scan(self, chunks: Iterable[bytes], *, mime_type: str) -> ScanResult:
        digest = hashlib.sha256()
        prefix = b""
        saw_nul = False
        with socket.create_connection(
            (self.host, self.port), timeout=self.timeout_seconds
        ) as connection:
            connection.sendall(b"zINSTREAM\0")
            for chunk in chunks:
                digest.update(chunk)
                if len(prefix) < 16:
                    prefix += chunk[: 16 - len(prefix)]
                if b"\x00" in chunk[:4096]:
                    saw_nul = True
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
            connection.sendall(struct.pack("!I", 0))
            response = connection.recv(4096).decode("utf-8", errors="replace")

        magic_reason = _magic_mismatch(prefix, mime_type, saw_nul=saw_nul)
        if magic_reason is not None:
            return ScanResult(False, digest.hexdigest(), magic_reason)
        if "FOUND" in response:
            return ScanResult(False, digest.hexdigest(), response.strip()[:240])
        if "OK" not in response:
            return ScanResult(
                False, digest.hexdigest(), "virus scanner returned an invalid response"
            )
        return ScanResult(True, digest.hexdigest())


def _magic_mismatch(prefix: bytes, mime_type: str, *, saw_nul: bool) -> str | None:
    if mime_type == "application/pdf" and not prefix.startswith(b"%PDF-"):
        return "declared PDF does not have a PDF signature"
    if mime_type == "image/png" and not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "declared PNG does not have a PNG signature"
    if mime_type in {"image/jpeg", "image/jpg"} and not prefix.startswith(b"\xff\xd8\xff"):
        return "declared JPEG does not have a JPEG signature"
    if mime_type.startswith("text/") and saw_nul:
        return "declared text file contains binary NUL bytes"
    return None
