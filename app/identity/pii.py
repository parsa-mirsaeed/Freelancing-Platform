from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import string
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

_NONCE_BYTES = 12
_KEY_BYTES = 32
_VERSION = "v1"
_KEY_ID_CHARS = frozenset(string.ascii_letters + string.digits + "._-")


@dataclass(frozen=True, slots=True)
class PiiCipher:
    active_key_id: str
    keys: Mapping[str, bytes]
    lookup_key: bytes

    @classmethod
    def from_config(cls, encryption_keys: str, lookup_key: str) -> PiiCipher:
        parsed: dict[str, bytes] = {}
        active_key_id: str | None = None
        for raw_entry in encryption_keys.split(","):
            entry = raw_entry.strip()
            if not entry:
                continue
            key_id, separator, encoded_key = entry.partition(":")
            if not separator or not _valid_key_id(key_id):
                raise ValueError("PII encryption key entries must use key-id:base64-key format")
            if key_id in parsed:
                raise ValueError(f"Duplicate PII encryption key id: {key_id}")
            parsed[key_id] = _decode_key(encoded_key, name=f"PII encryption key {key_id}")
            if active_key_id is None:
                active_key_id = key_id
        if active_key_id is None:
            raise ValueError("At least one PII encryption key is required")
        return cls(
            active_key_id=active_key_id,
            keys=parsed,
            lookup_key=_decode_key(lookup_key, name="PII lookup key"),
        )

    def encrypt(self, value: str, *, context: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(self.keys[self.active_key_id]).encrypt(
            nonce,
            value.encode("utf-8"),
            _aad(context),
        )
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
        return f"{_VERSION}:{self.active_key_id}:{payload}"

    def decrypt(self, value: str, *, context: str) -> str:
        version, separator, remainder = value.partition(":")
        key_id, second_separator, encoded_payload = remainder.partition(":")
        if version != _VERSION or not separator or not second_separator:
            raise ValueError("Unsupported PII ciphertext envelope")
        key = self.keys.get(key_id)
        if key is None:
            raise ValueError(f"PII ciphertext references unavailable key id: {key_id}")
        try:
            payload = _decode_payload(encoded_payload)
            if len(payload) <= _NONCE_BYTES:
                raise ValueError("Invalid PII ciphertext payload")
            plaintext = AESGCM(key).decrypt(
                payload[:_NONCE_BYTES],
                payload[_NONCE_BYTES:],
                _aad(context),
            )
        except (InvalidTag, binascii.Error, ValueError) as exc:
            raise ValueError("Invalid PII ciphertext") from exc
        return plaintext.decode("utf-8")

    def blind_index(self, value: str, *, context: str) -> str:
        material = context.encode("utf-8") + b"\0" + value.encode("utf-8")
        return hmac.new(self.lookup_key, material, hashlib.sha256).hexdigest()

    def needs_rotation(self, value: str) -> bool:
        version, separator, remainder = value.partition(":")
        key_id, second_separator, _payload = remainder.partition(":")
        if version != _VERSION or not separator or not second_separator:
            raise ValueError("Unsupported PII ciphertext envelope")
        return key_id != self.active_key_id

    def rewrap(self, value: str, *, context: str) -> str:
        if not self.needs_rotation(value):
            return value
        return self.encrypt(self.decrypt(value, context=context), context=context)


@lru_cache(maxsize=16)
def pii_cipher_from_config(encryption_keys: str, lookup_key: str) -> PiiCipher:
    return PiiCipher.from_config(encryption_keys, lookup_key)


def current_pii_cipher() -> PiiCipher:
    return pii_cipher_from_config(
        str(current_app.config["PII_ENCRYPTION_KEYS"]),
        str(current_app.config["PII_LOOKUP_KEY"]),
    )


def _aad(context: str) -> bytes:
    return f"freelancing-platform:pii:{context}:{_VERSION}".encode()


def _decode_key(value: str, *, name: str) -> bytes:
    try:
        decoded = _decode_base64(value)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{name} must be URL-safe base64") from exc
    if len(decoded) != _KEY_BYTES:
        raise ValueError(f"{name} must decode to exactly {_KEY_BYTES} bytes")
    return decoded


def _decode_payload(value: str) -> bytes:
    return _decode_base64(value)


def _decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode((value + padding).encode("ascii"), altchars=b"-_", validate=True)


def _valid_key_id(value: str) -> bool:
    return 1 <= len(value) <= 40 and all(char in _KEY_ID_CHARS for char in value)
