from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.reproduction.swiss_ravafcast.constants import (
    DATASET_DOI,
    ENVIDAT_DATASET_PAGE,
    REPRODUCTION_SCHEMA_VERSION,
    REQUIRED_RESOURCE_KEYS,
    USAGE_BOUNDARY,
)


@dataclass(frozen=True)
class SwissDataResource:
    resource_key: str
    filename: str
    source_url: str
    local_path: str
    sha256: str
    byte_size: int
    checksum_status: str
    usage_boundary: str = USAGE_BOUNDARY
    expected_sha256: str | None = None
    license_note: str = 'WSL/EnviDat terms; research reproduction only until reviewed.'

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_resource(
    *,
    resource_key: str,
    path: Path,
    source_url: str,
    expected_sha256: str | None = None,
) -> SwissDataResource:
    actual_sha = compute_sha256(path)
    checksum_status = 'verified' if expected_sha256 and actual_sha == expected_sha256 else 'unverified_recorded'
    if expected_sha256 and actual_sha != expected_sha256:
        checksum_status = 'mismatch'
    return SwissDataResource(
        resource_key=resource_key,
        filename=path.name,
        source_url=source_url,
        local_path=str(path),
        sha256=actual_sha,
        byte_size=path.stat().st_size,
        checksum_status=checksum_status,
        expected_sha256=expected_sha256,
    )


def build_manifest_payload(
    *,
    resources: list[SwissDataResource],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    payload = {
        'schema_version': REPRODUCTION_SCHEMA_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'dataset': {
            'doi': DATASET_DOI,
            'source_page': ENVIDAT_DATASET_PAGE,
            'title': 'Weather, snowpack, and danger ratings data for automated avalanche danger prediction',
        },
        'generated_at': generated_at.isoformat(),
        'resources': [resource.as_dict() for resource in resources],
        'required_resource_keys': list(REQUIRED_RESOURCE_KEYS),
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
    }
    validate_manifest_payload(payload)
    return payload


def validate_manifest_payload(payload: dict[str, Any]) -> None:
    if payload.get('schema_version') != REPRODUCTION_SCHEMA_VERSION:
        raise ValueError('unexpected Swiss reproduction manifest schema_version')
    if payload.get('usage_boundary') != USAGE_BOUNDARY:
        raise ValueError('Swiss reproduction manifest must be research_only')
    if payload.get('production_scoring_allowed') is not False:
        raise ValueError('Swiss reproduction manifest must block production scoring')
    if payload.get('model_status_mutation_allowed') is not False:
        raise ValueError('Swiss reproduction manifest must block model status mutation')

    resources = payload.get('resources')
    if not isinstance(resources, list):
        raise ValueError('Swiss reproduction manifest resources must be a list')
    resource_keys = {item.get('resource_key') for item in resources if isinstance(item, dict)}
    missing = set(REQUIRED_RESOURCE_KEYS) - resource_keys
    if missing:
        raise ValueError(f'Swiss reproduction manifest missing required resources: {sorted(missing)}')
    for resource in resources:
        if not isinstance(resource, dict):
            raise ValueError('Swiss reproduction manifest resource must be an object')
        if resource.get('usage_boundary') != USAGE_BOUNDARY:
            raise ValueError('Swiss reproduction resource must be research_only')
        if resource.get('checksum_status') == 'mismatch':
            raise ValueError(f"checksum mismatch for {resource.get('resource_key')}")


def write_manifest(payload: dict[str, Any], output_path: Path) -> None:
    validate_manifest_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


def read_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    validate_manifest_payload(payload)
    return payload

