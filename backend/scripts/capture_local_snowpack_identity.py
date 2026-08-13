#!/usr/bin/env python3
"""Capture an independently probed identity for one local SNOWPACK image.

This is local candidate evidence only.  It records the Docker image ID, a
streamed ``docker save`` archive hash, the binary hash/version probed inside
the image, and the embedded source-commit manifest.  It never promotes a
local image to an approved hosted runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.snowpack_toolchain_identity import is_real_image_id, is_real_sha256


class CaptureError(RuntimeError):
    """Raised when local image identity cannot be captured without guessing."""


def _run(command: list[str], *, text: bool = True) -> str | bytes:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=text,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise CaptureError(f"command failed: {command[0]}") from exc
    return result.stdout


def _image_inspect(image: str) -> dict[str, Any]:
    raw = _run(["docker", "image", "inspect", image])
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CaptureError("docker image inspect did not return JSON") from exc
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise CaptureError("docker image inspect returned an unexpected shape")
    return values[0]


def _archive_sha256(image: str) -> str:
    digest = hashlib.sha256()
    try:
        process = subprocess.Popen(
            ["docker", "save", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise CaptureError("could not start docker save") from exc
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    stderr = process.stderr.read() if process.stderr is not None else b""
    return_code = process.wait()
    if return_code != 0:
        raise CaptureError(f"docker save failed with exit code {return_code}: {stderr[:160]!r}")
    return digest.hexdigest()


def _embedded_manifest(image: str) -> dict[str, Any]:
    raw = _run([
        "docker", "run", "--rm", "--entrypoint", "/bin/cat", image,
        "/opt/snowpack/toolchain-manifest.json",
    ])
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        # The existing local smoke image was built before Dockerfile.snowpack
        # corrected its shell newline quoting.  Its binary_version field has
        # literal newlines and is therefore invalid JSON, but the commit
        # identities before that field are still recoverable.  Keep this
        # exceptional status visible in the replacement manifest and rely on
        # the independent in-container version/hash probes below.
        if not isinstance(raw, str):
            raise CaptureError("embedded toolchain manifest is not valid text")
        recovered: dict[str, Any] = {"embedded_manifest_parse_status": "invalid_json_legacy"}
        for key in ("schema_version", "toolchain_id", "meteoio_commit", "snowpack_commit"):
            match = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', raw)
            if match is None or not match.group(1).strip():
                raise CaptureError(f"embedded toolchain manifest is invalid and lacks {key}")
            recovered[key] = match.group(1)
        return recovered
    if not isinstance(value, dict):
        raise CaptureError("embedded toolchain manifest must be an object")
    return value


def _binary_version(image: str) -> str:
    raw = _run([
        "docker", "run", "--rm", "--entrypoint", "/opt/snowpack/bin/snowpack", image,
        "--version",
    ])
    version = raw.strip() if isinstance(raw, str) else raw.decode("utf-8", "replace").strip()
    if not version:
        raise CaptureError("SNOWPACK version probe returned no output")
    return version[:200]


def _binary_sha256(image: str) -> str:
    raw = _run([
        "docker", "run", "--rm", "--entrypoint", "sha256sum", image,
        "/opt/snowpack/bin/snowpack",
    ])
    line = raw.strip() if isinstance(raw, str) else raw.decode("utf-8", "replace").strip()
    digest = line.split()[0] if line.split() else ""
    if not is_real_sha256(digest):
        raise CaptureError("SNOWPACK binary probe did not return a SHA-256 digest")
    return digest.lower()


def capture(image: str) -> dict[str, Any]:
    inspected = _image_inspect(image)
    image_id = inspected.get("Id")
    if not is_real_image_id(image_id):
        raise CaptureError("Docker inspect did not return a real image ID")

    repository_digest = ""
    repo_digests = inspected.get("RepoDigests")
    if isinstance(repo_digests, list):
        for value in repo_digests:
            if isinstance(value, str) and "@sha256:" in value:
                repository_name = value.split("@", 1)[0]
                # Docker can expose a local tag as ``name@sha256:...`` in
                # RepoDigests.  That is still local image identity, not a
                # separately authenticated registry digest.
                if "/" not in repository_name:
                    continue
                candidate = "sha256:" + value.rsplit("@sha256:", 1)[1]
                if is_real_image_id(candidate):
                    repository_digest = candidate
                    break

    embedded = _embedded_manifest(image)
    binary_version = _binary_version(image)
    binary_sha256 = _binary_sha256(image)
    archive_sha256 = _archive_sha256(image)
    for key in ("toolchain_id", "meteoio_commit", "snowpack_commit"):
        if not isinstance(embedded.get(key), str) or not embedded[key].strip():
            raise CaptureError(f"embedded toolchain manifest is missing {key}")

    result = dict(embedded)
    result.update(
        {
            "schema_version": "snowpack_toolchain_manifest_v1",
            "binary_path": "/opt/snowpack/bin/snowpack",
            "binary_sha256": binary_sha256,
            "binary_version": binary_version,
            "image_id": image_id,
            "image_archive_sha256": archive_sha256,
            "image_repository_digest": repository_digest,
            "image_identity_source": (
                "registry_digest_and_archive" if repository_digest else "local_id_and_archive"
            ),
            "image_reference": image,
            "capture_method": "docker_image_inspect_save_and_in_container_probes",
            "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "runtime_scope": "local_unapproved_candidate",
            "research_only": True,
            "production_eligible": False,
            "hosted_approved": False,
        }
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = capture(args.image)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except CaptureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "local_toolchain_identity_captured",
        "image_id": result["image_id"],
        "image_archive_sha256": result["image_archive_sha256"],
        "binary_sha256": result["binary_sha256"],
        "binary_version": result["binary_version"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
