#!/usr/bin/env python3
"""Record environment info for reproducibility.

Includes provenance: commit SHA, lock file SHA, config hashes,
Python version, platform, and installed packages.
"""
import hashlib
from importlib.metadata import distributions
import json
import platform
import subprocess
import sys
from pathlib import Path


def _git_head_sha(repo_path: str = ".") -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path, stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return None


def _file_sha256(path: str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return None


def _config_hash(repo_path: str = ".") -> str | None:
    parts = []
    for name in ("config.toml", "constants.toml"):
        p = Path(repo_path) / name
        if p.exists():
            parts.append(f"{name}={_file_sha256(str(p))}")
    if not parts:
        return None
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def record_env_info(output_path: str = "backend/env_info.json", repo_path: str = ".") -> dict:
    lock_file_path = str(Path(repo_path) / "backend" / "locks" / "core-py312.txt")
    info = {
        "commit_sha": _git_head_sha(repo_path),
        "lock_sha": _file_sha256(lock_file_path),
        "lock_file_path": lock_file_path,
        "config_hash": _config_hash(repo_path),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "platform_machine": platform.machine(),
        "platform_processor": platform.processor(),
        "packages": {},
    }
    for dist in distributions():
        name = dist.metadata.get('Name') or dist.name
        if name:
            info["packages"][name] = dist.version
    Path(output_path).write_text(json.dumps(info, indent=2, sort_keys=True))
    print(f"Environment info written to {output_path}")
    return info


if __name__ == "__main__":
    record_env_info()
