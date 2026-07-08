# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Artifact Blob Pipeline - Compression, Encryption, Local Store
# Description:  gzip + AES-256-GCM sealing and the local filesystem blob store
# Role:         Content-at-rest layer underneath the artifact memory service
# Usage:        Used by ArtifactMemoryService for every capture and read
# Author:       Muxi Framework Team
#
# Artifact Memory Phase 1 storage pipeline (PRD "Storage Pipeline"):
#
#   content -> gzip (level 6) -> encrypt (AES-256-GCM) -> write blob
#           -> SHA-256 checksum of the stored blob -> metadata row
#
# Encryption keys are never user-managed. The per-user key is derived with
# HKDF-SHA256 from the immutable ``formation_instance_id`` (IKM) salted by
# the user id, with the fixed info string ``muxi-artifact-encryption-v1``
# (PRD "Encryption Key Derivation"). Per-user keys mean direct blob-store
# access cannot decrypt another user's artifacts.
#
# The sealed blob layout is ``nonce (12 bytes) || AES-GCM ciphertext``.
# With encryption disabled the blob is the bare gzip stream (its magic
# bytes make the two layouts self-describing, but the metadata row is the
# source of truth -- the formation config decides, not the bytes).
#
# Local store layout (PRD "Storage Pipeline"):
#   {base}/{user_id}/{public_id[:2]}/{public_id}.bin
# User ids are sanitized for path safety and every resolved path is
# verified to stay under the base directory (no traversal).
# =============================================================================

import gzip
import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Fixed HKDF info string (PRD "Encryption Key Derivation"). Versioned so a
# future derivation change can coexist with v1 blobs.
HKDF_INFO = b"muxi-artifact-encryption-v1"

# AES-256-GCM parameters.
KEY_LENGTH_BYTES = 32
NONCE_LENGTH_BYTES = 12

# gzip level 6 (PRD "Storage Pipeline": zlib default trade-off).
GZIP_COMPRESSION_LEVEL = 6

# Path-safety: anything outside this set in a user id is replaced so ids
# like "user/../../etc" cannot escape the per-user directory.
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def derive_user_key(formation_instance_id: str, user_id: str) -> bytes:
    """Derive the per-user AES-256 key via HKDF-SHA256 (PRD derivation)."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH_BYTES,
        salt=str(user_id).encode("utf-8"),
        info=HKDF_INFO,
    )
    return hkdf.derive(str(formation_instance_id).encode("utf-8"))


def seal_content(raw: bytes, key: Optional[bytes]) -> Tuple[bytes, int]:
    """
    Compress (and encrypt, when a key is given) raw artifact content.

    Returns:
        (blob, compressed_bytes) -- ``compressed_bytes`` is the gzipped
        size recorded in the metadata row; ``blob`` is what hits storage.
    """
    compressed = gzip.compress(raw, compresslevel=GZIP_COMPRESSION_LEVEL)
    if key is None:
        return compressed, len(compressed)
    nonce = os.urandom(NONCE_LENGTH_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, compressed, None)
    return nonce + ciphertext, len(compressed)


def open_content(blob: bytes, key: Optional[bytes]) -> bytes:
    """Reverse ``seal_content``: decrypt (when keyed) and decompress."""
    if key is not None:
        nonce, ciphertext = blob[:NONCE_LENGTH_BYTES], blob[NONCE_LENGTH_BYTES:]
        blob = AESGCM(key).decrypt(nonce, ciphertext, None)
    return gzip.decompress(blob)


def blob_checksum(blob: bytes) -> str:
    """SHA-256 hex digest of the stored blob (integrity check)."""
    return hashlib.sha256(blob).hexdigest()


def sanitize_path_component(component: str) -> str:
    """Make one path component filesystem-safe (no separators/traversal)."""
    safe = _UNSAFE_PATH_CHARS.sub("_", str(component))
    # A dot-only component ("." / "..") would still traverse; neutralize it.
    return safe if safe.strip(".") else "_"


class LocalBlobStore:
    """Local filesystem blob store (PRD local storage layout)."""

    def __init__(self, base_path: Path):
        """
        Initialize the store rooted at ``base_path``.

        The directory is created lazily on first write so a formation that
        never produces artifacts never grows an empty ``artifacts/`` dir.
        """
        self.base_path = Path(base_path)

    def ref_for(self, user_id: str, public_id: str) -> str:
        """Relative storage ref: {user}/{prefix}/{public_id}.bin."""
        safe_user = sanitize_path_component(user_id)
        return f"{safe_user}/{public_id[:2]}/{public_id}.bin"

    def _resolve(self, ref: str) -> Path:
        """Resolve a ref under the base dir, refusing traversal escapes."""
        base = self.base_path.resolve()
        path = (base / ref).resolve()
        if base != path and base not in path.parents:
            raise ValueError(f"Storage ref escapes the artifact store: {ref!r}")
        return path

    def write(self, ref: str, blob: bytes) -> None:
        """Write one blob, creating parent directories as needed."""
        path = self._resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)

    def read(self, ref: str) -> bytes:
        """Read one blob; raises FileNotFoundError when missing."""
        return self._resolve(ref).read_bytes()

    def delete(self, ref: str) -> None:
        """Delete one blob; missing blobs are ignored (idempotent sweep)."""
        self._resolve(ref).unlink(missing_ok=True)
