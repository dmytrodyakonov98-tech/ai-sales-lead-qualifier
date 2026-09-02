"""Immutable SHA-256 content-addressed storage."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .canonical import sha256_hex


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})$")


class ContentAddressedStore:
    """Store immutable bytes under paths derived only from their SHA-256."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def ref_for_hash(self, content_sha256: str) -> str:
        if not _HASH_RE.fullmatch(content_sha256):
            raise ValueError("invalid SHA-256")
        return f"sha256/{content_sha256[:2]}/{content_sha256[2:4]}/{content_sha256}"

    def resolve_ref(self, cas_ref: str) -> Path:
        match = _REF_RE.fullmatch(cas_ref)
        if match is None:
            raise ValueError("invalid CAS reference")
        first, second, digest = match.groups()
        if digest[:2] != first or digest[2:4] != second:
            raise ValueError("CAS reference does not match its digest")
        return self.root / "sha256" / first / second / digest

    def put(self, data: bytes) -> tuple[str, str]:
        content_sha256 = sha256_hex(data)
        cas_ref = self.ref_for_hash(content_sha256)
        destination = self.resolve_ref(cas_ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_hex(destination.read_bytes()) != content_sha256:
                raise RuntimeError("existing CAS object is corrupt")
            return content_sha256, cas_ref

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".cas-", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return content_sha256, cas_ref

    def get(self, content_sha256: str) -> bytes:
        return self.resolve_ref(self.ref_for_hash(content_sha256)).read_bytes()
