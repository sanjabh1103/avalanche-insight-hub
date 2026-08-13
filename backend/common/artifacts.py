from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = Path(os.environ.get('ARTIFACT_ROOT', ROOT / 'backend' / 'artifacts'))
ARTIFACT_RUN_PATTERN = re.compile(r'^\d{8}T\d{6}Z$')


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def is_artifact_run_dir(path: Path) -> bool:
    return path.is_dir() and bool(ARTIFACT_RUN_PATTERN.fullmatch(path.name))


def latest_artifact_dir(root: Path | None = None) -> Path:
    artifact_root = root or DEFAULT_ARTIFACT_ROOT
    candidates = sorted([path for path in artifact_root.iterdir() if is_artifact_run_dir(path)]) if artifact_root.exists() else []
    if not candidates:
        raise FileNotFoundError(f'No artifact directories found in {artifact_root}')
    return candidates[-1]


def resolve_artifact_dir(
    root: Path | None = None,
    requested: str | Path | None = None,
    *,
    require_model: bool = False,
) -> Path:
    artifact_root = (root or DEFAULT_ARTIFACT_ROOT).expanduser().resolve()
    if requested is None or not str(requested).strip():
        artifact_dir = latest_artifact_dir(artifact_root)
    else:
        raw_candidate = Path(str(requested).strip()).expanduser()
        candidate = (artifact_root / raw_candidate) if not raw_candidate.is_absolute() else raw_candidate
        artifact_dir = candidate.resolve()
        try:
            artifact_dir.relative_to(artifact_root)
        except ValueError as exc:
            raise ValueError(f'artifact_dir must resolve under {artifact_root}') from exc
        if not artifact_dir.exists():
            raise FileNotFoundError(f'artifact_dir not found: {artifact_dir}')
        if not is_artifact_run_dir(artifact_dir):
            raise ValueError(f'artifact_dir must point to an artifact run directory: {artifact_dir}')
    if require_model and not (artifact_dir / 'model.joblib').is_file():
        raise FileNotFoundError(f'model.joblib not found under artifact_dir: {artifact_dir}')
    return artifact_dir


def create_artifact_dir(root: Path | None = None) -> Path:
    artifact_root = root or DEFAULT_ARTIFACT_ROOT
    artifact_dir = artifact_root / timestamp_slug()
    artifact_dir.mkdir(parents=True, exist_ok=False)
    return artifact_dir


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def dump_joblib(path: Path, payload: Any) -> None:
    joblib.dump(payload, path)


def load_joblib(path: Path) -> Any:
    return joblib.load(path)
