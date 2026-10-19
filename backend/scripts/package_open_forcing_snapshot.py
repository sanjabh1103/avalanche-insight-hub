#!/usr/bin/env python3
"""Create a deterministic, content-addressed archive of a verified snapshot.

The command never fetches data, changes the source bundle, or uploads it. It
first runs the offline replay validator, then writes a reproducible tar.gz and
sidecar manifest suitable for an approved artifact store or shared drive.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.scripts.replay_open_forcing_snapshot import replay_bundle


SCHEMA_VERSION = "open-forcing-archive/v1"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _archive_bytes(root: Path) -> bytes:
    """Return a stable USTAR/GZIP archive with normalized metadata."""

    members = sorted(path for path in root.rglob("*") if path.is_file())
    if not members:
        raise RuntimeError("snapshot bundle contains no regular files")
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for path in members:
                if path.is_symlink():
                    raise RuntimeError(f"snapshot bundle contains a symlink: {path}")
                relative = path.relative_to(root).as_posix()
                data = path.read_bytes()
                info = tarfile.TarInfo(name=f"{root.name}/{relative}")
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def package_snapshot(root: Path, output: Path, manifest_output: Path | None = None) -> dict[str, Any]:
    root = root.expanduser().resolve()
    output = output.expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"snapshot root is not a directory: {root}")
    if output == root or root in output.parents:
        raise RuntimeError("archive output must be outside the snapshot root")
    if output.exists():
        raise RuntimeError(f"archive already exists; refusing overwrite: {output}")
    sidecar = (manifest_output or output.with_suffix(output.suffix + ".json")).expanduser().resolve()
    if sidecar == output:
        raise RuntimeError("archive and sidecar manifest must be different paths")
    if sidecar.exists():
        raise RuntimeError(f"archive manifest already exists; refusing overwrite: {sidecar}")
    manifest_path = root / "snapshot_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("snapshot_manifest.json is required")

    replay = replay_bundle(root)
    archive = _archive_bytes(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(archive)
    manifest_record = json.loads(manifest_path.read_text())
    handoff = {
        "schema_version": SCHEMA_VERSION,
        "bundle_name": root.name,
        "archive_filename": output.name,
        "archive_sha256": _sha256_bytes(archive),
        "archive_bytes": len(archive),
        "source_manifest_sha256": _sha256_bytes(manifest_path.read_bytes()),
        "manifest_hash": manifest_record["manifest_hash"],
        "replay_id": manifest_record["replay_id"],
        "replay_verification": replay,
        "synthetic_inputs_present": False,
        "training_eligible": False,
        "production_eligible": False,
        "distribution_status": "LOCAL_ARCHIVE_NOT_DISTRIBUTION_CLEARED",
        "upload_required": True,
    }
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_bytes(_canonical_json(handoff) + b"\n")
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args()
    result = package_snapshot(args.root, args.output, args.manifest_output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
