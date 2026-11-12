from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from backend.reproduction.swiss_ravafcast.constants import (
    DATA_ROOT,
    ENVIDAT_CKAN_PACKAGE_SHOW,
    ENVIDAT_PACKAGE_ID,
    RF1_RESOURCE_KEY,
    RF2_RESOURCE_KEY,
)
from backend.reproduction.swiss_ravafcast.manifest import (
    build_manifest_payload,
    build_resource,
    write_manifest,
)

# P6: The DOI-based ENVIDAT_PACKAGE_ID from constants.py ('doi:10.16904/envidat.330')
# returns 404 from the EnviDat CKAN API. The slug and UUID both work.
# We cannot modify constants.py (denylisted), so we override the default here.
# Verified UUID: 54d7dc19-e70c-4998-bfb6-caffe41c83e6
# Verified slug: weather-snowpack-danger_ratings-data
ENVIDAT_WORKING_PACKAGE_ID = 'weather-snowpack-danger_ratings-data'
ENVIDAT_FALLBACK_PACKAGE_IDS = [
    ENVIDAT_WORKING_PACKAGE_ID,
    '54d7dc19-e70c-4998-bfb6-caffe41c83e6',  # UUID fallback
    ENVIDAT_PACKAGE_ID,  # DOI-based (known 404, kept for documentation)
]


RESOURCE_PATTERNS = {
    RF1_RESOURCE_KEY: ('rf1', 'forecast'),
    RF2_RESOURCE_KEY: ('rf2', 'tidy'),
}


def discover_envidat_resources(*, package_id: str = ENVIDAT_WORKING_PACKAGE_ID) -> list[dict[str, Any]]:
    """Discover EnviDat resources for the Swiss RAvaFcast dataset.

    P6 fix: The DOI-based package_id from constants.py returns 404.
    The default is now the slug 'weather-snowpack-danger_ratings-data'.
    Falls back to UUID and DOI-based ID if the slug fails.
    """
    # Try the provided package_id first, then fall back to known working IDs
    candidate_ids = [package_id] + [
        pid for pid in ENVIDAT_FALLBACK_PACKAGE_IDS if pid != package_id
    ]

    last_error: Exception | None = None
    for pid in candidate_ids:
        try:
            response = requests.get(
                ENVIDAT_CKAN_PACKAGE_SHOW,
                params={'id': pid},
                timeout=30,
            )
            if response.status_code == 404:
                last_error = RuntimeError(f'EnviDat package_show returned 404 for {pid}')
                continue
            response.raise_for_status()
            payload = response.json()
            if not payload.get('success'):
                last_error = RuntimeError(f'EnviDat package_show failed for {pid}')
                continue
            result = payload.get('result')
            if not isinstance(result, dict):
                last_error = RuntimeError('EnviDat package_show response missing result object')
                continue
            resources = result.get('resources')
            if not isinstance(resources, list):
                last_error = RuntimeError('EnviDat package_show response missing resources list')
                continue
            return [resource for resource in resources if isinstance(resource, dict)]
        except requests.RequestException as exc:
            last_error = exc
            continue

    raise RuntimeError(
        f'EnviDat package_show failed for all candidate IDs: {candidate_ids}'
    ) from last_error


def select_resource_url(resources: list[dict[str, Any]], *, resource_key: str) -> str:
    patterns = RESOURCE_PATTERNS[resource_key]
    for resource in resources:
        searchable = ' '.join(
            str(resource.get(field) or '')
            for field in ('name', 'description', 'url', 'format')
        ).lower()
        if all(pattern in searchable for pattern in patterns):
            url = str(resource.get('url') or '')
            if not url.startswith(('http://', 'https://')):
                raise RuntimeError(f'EnviDat resource {resource_key} has no HTTP URL')
            return url
    raise RuntimeError(f'Could not locate EnviDat resource for {resource_key}')


def filename_from_url(url: str, *, fallback: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    return name or fallback


def download_resource(url: str, output_path: Path, *, max_attempts: int = 4) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(f'{output_path.suffix}.tmp')
    last_error: Exception | None = None
    for _attempt in range(max(1, max_attempts)):
        existing_bytes = tmp_path.stat().st_size if tmp_path.exists() else 0
        headers = {'Range': f'bytes={existing_bytes}-'} if existing_bytes else None
        mode = 'ab' if existing_bytes else 'wb'
        try:
            with requests.get(url, stream=True, timeout=120, headers=headers) as response:
                if existing_bytes and response.status_code == 200:
                    # Server ignored Range, so restart cleanly.
                    existing_bytes = 0
                    mode = 'wb'
                response.raise_for_status()
                with tmp_path.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            tmp_path.replace(output_path)
            return
        except requests.RequestException as exc:
            last_error = exc
            continue
    raise RuntimeError(f'failed to download {url} after {max_attempts} attempts') from last_error


def _expected_sha(args: argparse.Namespace, resource_key: str) -> str | None:
    if resource_key == RF1_RESOURCE_KEY:
        return args.rf1_sha256
    if resource_key == RF2_RESOURCE_KEY:
        return args.rf2_sha256
    return None


def _resolve_urls(args: argparse.Namespace) -> dict[str, str]:
    if args.rf1_url and args.rf2_url:
        return {
            RF1_RESOURCE_KEY: args.rf1_url,
            RF2_RESOURCE_KEY: args.rf2_url,
        }
    resources = discover_envidat_resources(package_id=args.package_id)
    return {
        RF1_RESOURCE_KEY: args.rf1_url or select_resource_url(resources, resource_key=RF1_RESOURCE_KEY),
        RF2_RESOURCE_KEY: args.rf2_url or select_resource_url(resources, resource_key=RF2_RESOURCE_KEY),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Download Swiss EnviDat RF1/RF2 CSVs for research-only RAvaFcast reproduction.'
    )
    parser.add_argument('--package-id', default=ENVIDAT_WORKING_PACKAGE_ID,
                        help='EnviDat package ID (slug, UUID, or DOI). Default: working slug.')
    parser.add_argument('--rf1-url')
    parser.add_argument('--rf2-url')
    parser.add_argument('--rf1-sha256')
    parser.add_argument('--rf2-sha256')
    parser.add_argument('--output-root', type=Path, default=DATA_ROOT)
    parser.add_argument('--manifest-output', type=Path)
    parser.add_argument('--download-retries', type=int, default=4)
    parser.add_argument(
        '--allow-unpinned-first-download',
        action='store_true',
        help='Allow first-run checksum recording when reviewed checksums are not available yet.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.allow_unpinned_first_download and (not args.rf1_sha256 or not args.rf2_sha256):
        parser.error('provide --rf1-sha256 and --rf2-sha256, or pass --allow-unpinned-first-download')

    urls = _resolve_urls(args)
    resources = []
    for resource_key, url in urls.items():
        filename = filename_from_url(url, fallback=f'{resource_key}.csv')
        output_path = args.output_root / filename
        download_resource(url, output_path, max_attempts=args.download_retries)
        resource = build_resource(
            resource_key=resource_key,
            path=output_path,
            source_url=url,
            expected_sha256=_expected_sha(args, resource_key),
        )
        if resource.checksum_status == 'mismatch':
            raise RuntimeError(f'checksum mismatch for {resource_key}: {output_path}')
        resources.append(resource)

    manifest = build_manifest_payload(resources=resources)
    manifest_output = args.manifest_output or (args.output_root / 'swiss_ravafcast_data_manifest.json')
    write_manifest(manifest, manifest_output)
    print(manifest_output)
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
