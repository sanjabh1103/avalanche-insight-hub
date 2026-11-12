"""Content resolver for hash verification against actual bytes.

This module resolves declared hashes against actual file content.
It bridges the gap between format-only hash validation (64-char hex)
and content-bound verification (actual bytes match declared hash).

Per Codex audit P4: hashes must be verified against actual content,
not just format-checked.

The resolver:
- Loads actual bytes from file paths
- Computes SHA-256 of the bytes
- Compares against declared hashes
- Rejects mismatches, symlinks, path substitution, and missing files
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ContentResolutionError(ValueError):
    """Raised when content resolution fails."""


@dataclass
class ContentVerificationResult:
    """Result of a content verification check."""

    verified: bool
    declared_hash: str
    actual_hash: str
    path: str
    error: str = ""


class ContentResolver:
    """Resolves declared hashes against actual file content.

    This resolver is intentionally bounded — it only handles file-based
    content. For database or API-bound content, a separate resolver
    would be needed.
    """

    def __init__(self, base_path: Path | None = None):
        configured = Path(base_path or Path.cwd())
        if configured.is_symlink():
            raise ContentResolutionError(
                f"base_path must not be a symlink: {configured}"
            )
        self.base_path = configured.resolve()
        self._resolved: dict[str, ContentVerificationResult] = {}

    def _safe_path(self, relative_path: str) -> Path:
        """Resolve a packet path while preserving the configured root.

        Validation happens before any filesystem read. Parent symlinks are
        rejected as well as a symlink at the final component, because a
        trusted-looking relative path must not be redirectable between the
        check and the byte read.
        """
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ContentResolutionError("relative_path must be a non-empty string")
        if "\x00" in relative_path:
            raise ContentResolutionError("relative_path contains a NUL byte")
        candidate_input = Path(relative_path)
        if candidate_input.is_absolute():
            raise ContentResolutionError(
                f"absolute paths are rejected: {relative_path}"
            )
        if any(part == ".." for part in candidate_input.parts):
            raise ContentResolutionError(
                f"parent traversal is rejected: {relative_path}"
            )
        candidate = self.base_path / candidate_input
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(self.base_path)
        except ValueError as exc:
            raise ContentResolutionError(
                f"resolved path escapes base_path: {relative_path}"
            ) from exc

        # Check every existing path component, not only the leaf.
        current = self.base_path
        for part in candidate.relative_to(self.base_path).parts:
            current = current / part
            if current.is_symlink():
                raise ContentResolutionError(
                    f"symlink rejected (including parent component): {current}"
                )
        return resolved

    @staticmethod
    def _validate_declared_hash(declared_hash: str) -> None:
        if not isinstance(declared_hash, str) or len(declared_hash) != 64:
            raise ContentResolutionError("declared_hash must be a 64-character SHA-256 hash")
        try:
            int(declared_hash, 16)
        except ValueError as exc:
            raise ContentResolutionError("declared_hash must contain only hexadecimal characters") from exc

    def resolve_and_verify(
        self,
        declared_hash: str,
        relative_path: str,
        *,
        allow_symlink: bool = False,
    ) -> ContentVerificationResult:
        """Resolve a path and verify its content hash matches the declared hash.

        Args:
            declared_hash: The expected SHA-256 hash (64-char hex)
            relative_path: Path relative to base_path
            allow_symlink: If False, reject symlinks (path substitution attack)

        Returns:
            ContentVerificationResult with verified=True if hash matches

        Raises:
            ContentResolutionError: if file is missing, symlink rejected,
                or hash doesn't match
        """
        # Validate declared hash format
        self._validate_declared_hash(declared_hash)

        # Resolve path and reject absolute/traversal/symlink substitution.
        # ``allow_symlink`` is retained for API compatibility but is no longer
        # accepted for packet-bound verification.
        if allow_symlink:
            raise ContentResolutionError("allow_symlink=True is not permitted for packet content")
        full_path = self._safe_path(relative_path)

        # Check file exists
        if not full_path.exists():
            raise ContentResolutionError(
                f"file not found: {full_path}"
            )

        # Check it's a regular file (not a directory or device)
        if not full_path.is_file():
            raise ContentResolutionError(
                f"path is not a regular file: {full_path}"
            )

        # Read and hash the actual content
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(full_path, flags)
            try:
                stat_result = os.fstat(fd)
                if not stat.S_ISREG(stat_result.st_mode):
                    raise ContentResolutionError(
                        f"path is not a regular file: {full_path}"
                    )
                with os.fdopen(fd, "rb") as stream:
                    actual_bytes = stream.read()
                fd = -1
            finally:
                if fd >= 0:
                    os.close(fd)
        except OSError as exc:
            raise ContentResolutionError(
                f"cannot read file {full_path}: {exc}"
            )

        actual_hash = hashlib.sha256(actual_bytes).hexdigest()

        # Compare
        verified = actual_hash.lower() == declared_hash.lower()
        result = ContentVerificationResult(
            verified=verified,
            declared_hash=declared_hash.lower(),
            actual_hash=actual_hash,
            path=str(full_path),
            error="" if verified else f"hash mismatch: declared={declared_hash}, actual={actual_hash}",
        )
        self._resolved[str(full_path)] = result

        if not verified:
            raise ContentResolutionError(result.error)

        return result

    def verify_bytes(
        self,
        declared_hash: str,
        actual_bytes: bytes,
    ) -> ContentVerificationResult:
        """Verify that actual bytes match a declared hash.

        This is used for in-memory content (e.g., JSON payloads).
        """
        self._validate_declared_hash(declared_hash)
        actual_hash = hashlib.sha256(actual_bytes).hexdigest()
        verified = actual_hash.lower() == declared_hash.lower()
        result = ContentVerificationResult(
            verified=verified,
            declared_hash=declared_hash.lower(),
            actual_hash=actual_hash,
            path="<in-memory>",
            error="" if verified else f"hash mismatch: declared={declared_hash}, actual={actual_hash}",
        )
        if not verified:
            raise ContentResolutionError(result.error)
        return result

    def verify_json_payload(
        self,
        declared_hash: str,
        payload: dict[str, Any],
    ) -> ContentVerificationResult:
        """Verify that a JSON-serializable payload matches a declared hash.

        The payload is canonicalized (sorted keys) before hashing.
        """
        import json
        canonical = json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
        return self.verify_bytes(declared_hash, canonical)

    def load_json_and_verify(
        self,
        declared_hash: str,
        relative_path: str,
    ) -> tuple[dict[str, Any], ContentVerificationResult]:
        """Read, hash, and parse one JSON file as a single content operation."""
        full_path = self._safe_path(relative_path)
        if not full_path.exists() or not full_path.is_file():
            raise ContentResolutionError(f"path is not a regular file: {full_path}")
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(full_path, flags)
            try:
                with os.fdopen(fd, "rb") as stream:
                    raw = stream.read()
                fd = -1
            finally:
                if fd >= 0:
                    os.close(fd)
        except OSError as exc:
            raise ContentResolutionError(f"cannot read file {full_path}: {exc}") from exc
        result = self.verify_bytes(declared_hash, raw)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContentResolutionError(f"invalid JSON content at {full_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ContentResolutionError(f"JSON content at {full_path} must be an object")
        return payload, result

    @property
    def resolved_count(self) -> int:
        return len(self._resolved)

    def get_all_results(self) -> dict[str, ContentVerificationResult]:
        return dict(self._resolved)
