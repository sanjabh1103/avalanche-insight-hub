"""Fail-closed path policy for SNOWPACK release artifacts."""
from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when an artifact path violates the release path policy."""


def _reject_lexical_traversal(path: Path) -> None:
    raw = os.fspath(path)
    if "\x00" in raw:
        raise UnsafePathError("path contains a null byte")
    if "\\" in raw:
        raise UnsafePathError("backslash paths are not allowed")
    if ".." in path.parts:
        raise UnsafePathError("path contains lexical traversal")


def _is_benign_system_alias(path: Path) -> bool:
    """Allow only well-known macOS system aliases used for temp paths."""
    if sys.platform != 'darwin' or path not in {Path('/var'), Path('/tmp')}:
        return False
    try:
        return path.resolve() in {Path('/private/var'), Path('/private/tmp')}
    except OSError:
        return False


def _assert_no_symlink_chain(path: Path, *, stop: Path | None = None) -> None:
    current = Path(os.path.abspath(os.fspath(path)))
    stop_absolute = Path(os.path.abspath(os.fspath(stop))) if stop is not None else None
    while current != stop_absolute:
        if current.is_symlink() and not _is_benign_system_alias(current):
            raise UnsafePathError(f"symlinked path component: {current}")
        if current == current.parent:
            return
        current = current.parent


def ensure_safe_directory(path: Path, *, create: bool = False) -> Path:
    """Return a real directory after rejecting symlinked parents and targets.

    C0.30: Validates every parent of the path before mkdir, and rechecks
    after creation. A newly-created directory under a symlinked parent is
    rejected because the symlink could be replaced after creation.
    """
    path = Path(path)
    _reject_lexical_traversal(path)
    absolute = Path(os.path.abspath(os.fspath(path)))

    # C0.30: Walk every parent before any filesystem mutation.
    # Reject any symlink in the parent chain.
    parent = absolute.parent
    while parent != parent.parent:
        if parent.is_symlink() and not _is_benign_system_alias(parent):
            raise UnsafePathError(f"symlinked parent component: {parent}")
        parent = parent.parent

    if absolute.exists():
        if absolute.is_symlink():
            raise UnsafePathError(f"directory is a symlink: {absolute}")
        if not absolute.is_dir():
            raise UnsafePathError(f"path is not a directory: {absolute}")
    elif create:
        absolute.mkdir(parents=True, exist_ok=True)
        # C0.30: Recheck after creation — reject if a symlink was introduced
        # in the parent chain during the mkdir race window.
        parent = absolute.parent
        while parent != parent.parent:
            if parent.is_symlink() and not _is_benign_system_alias(parent):
                raise UnsafePathError(
                    f"symlinked parent detected after mkdir: {parent}"
                )
            parent = parent.parent
        if absolute.is_symlink():
            raise UnsafePathError(f"directory became a symlink after mkdir: {absolute}")
    else:
        raise UnsafePathError(f"directory does not exist: {absolute}")
    if absolute.is_symlink():
        raise UnsafePathError(f"directory became a symlink: {absolute}")
    return absolute.resolve()


def ensure_safe_file(path: Path, *, root: Path | None = None) -> Path:
    """Return a regular non-symlink file with a safe parent chain."""
    path = Path(path)
    _reject_lexical_traversal(path)
    absolute = Path(os.path.abspath(os.fspath(path)))
    if root is not None:
        root_absolute = Path(os.path.abspath(os.fspath(root)))
        _assert_no_symlink_chain(absolute, stop=root_absolute)
        root_resolved = ensure_safe_directory(root)
        try:
            absolute.resolve().relative_to(root_resolved)
        except ValueError as exc:
            raise UnsafePathError(f"file is outside root: {absolute}") from exc
    if not absolute.exists() or not absolute.is_file() or absolute.is_symlink():
        raise UnsafePathError(f"not a regular file: {absolute}")
    return absolute.resolve()


def validate_output_bundle_path(
    output_bundle: Path,
    approved_root: Path,
    *,
    create_approved_root: bool = False,
) -> tuple[Path, Path]:
    """Validate an output bundle is a non-root child of an approved root."""
    root = ensure_safe_directory(approved_root, create=create_approved_root)
    target = Path(output_bundle)
    _reject_lexical_traversal(target)
    target_absolute = Path(os.path.abspath(os.fspath(target)))
    root_absolute = Path(os.path.abspath(os.fspath(approved_root)))
    _assert_no_symlink_chain(target_absolute.parent, stop=root_absolute)
    target_resolved = target_absolute.resolve(strict=False)
    try:
        target_resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(
            f"output bundle {target_absolute} is outside approved root {root}"
        ) from exc
    if target_resolved == root:
        raise UnsafePathError("output bundle cannot be the approved root itself")
    if target_absolute.exists():
        if target_absolute.is_symlink():
            raise UnsafePathError(f"output bundle is a symlink: {target_absolute}")
        if not target_absolute.is_dir():
            raise UnsafePathError(f"output bundle is not a directory: {target_absolute}")
    return root, target_absolute


def create_staging_directory(output_bundle: Path, approved_root: Path) -> tuple[Path, Path]:
    """Create a unique staging directory beside the intended publication path."""
    root, target = validate_output_bundle_path(
        output_bundle, approved_root, create_approved_root=True
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_chain(
        target.parent,
        stop=Path(os.path.abspath(os.fspath(approved_root))),
    )
    staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    validate_output_bundle_path(staging, approved_root)
    staging.mkdir()
    return root, staging


def safe_remove_directory(path: Path, approved_root: Path) -> None:
    """Remove only a real child directory beneath an approved root."""
    root, target = validate_output_bundle_path(path, approved_root)
    if not target.exists():
        return
    if target == root or target.is_symlink() or not target.is_dir():
        raise UnsafePathError(f"refusing unsafe directory removal: {target}")
    shutil.rmtree(target)


def publish_staging_directory(staging: Path, output_bundle: Path, approved_root: Path) -> Path:
    """Atomically publish a validated staging directory beneath the root."""
    root, target = validate_output_bundle_path(output_bundle, approved_root)
    _, staging = validate_output_bundle_path(staging, approved_root)
    if not staging.is_dir() or staging.is_symlink():
        raise UnsafePathError(f"invalid staging directory: {staging}")
    backup: Path | None = None
    if target.exists():
        backup = target.parent / f".{target.name}.previous-{uuid.uuid4().hex}"
        validate_output_bundle_path(backup, approved_root)
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup is not None and backup.exists():
        safe_remove_directory(backup, approved_root)
    return target
