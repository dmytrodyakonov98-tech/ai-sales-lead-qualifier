"""Canonical serialization and hashing primitives."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value with one stable byte representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for bytes."""

    return hashlib.sha256(data).hexdigest()


def hash_object(value: Any) -> str:
    """Hash a JSON-compatible value using the canonical representation."""

    return sha256_hex(canonical_bytes(value))
