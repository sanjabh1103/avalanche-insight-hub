from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from backend.common.regions import repo_root


DEFAULT_OUTPUT = Path('backend/data/models/swin_transformer_v2_tiny.pt')
ALLOWED_MODEL_FAMILIES = {'resnet34_unet', 'swinunet_tiny_diff'}


def validate_model_url(model_url: str) -> str:
    parsed = urlparse(str(model_url).strip())
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError('model-url must be a direct https URL')
    return parsed.geturl()


def _looks_like_html_or_xml(payload: bytes) -> bool:
    prefix = payload[:512].lstrip().lower()
    return (
        prefix.startswith(b'<!doctype html')
        or prefix.startswith(b'<html')
        or prefix.startswith(b'<?xml')
        or prefix.startswith(b'<error>')
    )


def download_model_payload(model_url: str) -> bytes:
    response = requests.get(validate_model_url(model_url), timeout=300)
    if not response.ok:
        raise RuntimeError(f'model download failed ({response.status_code}): {response.text[:400]}')
    payload = response.content
    if not payload:
        raise RuntimeError('model download returned an empty payload')
    content_type = str(response.headers.get('Content-Type') or '').lower()
    if 'text/html' in content_type or 'application/xml' in content_type or _looks_like_html_or_xml(payload):
        raise RuntimeError('downloaded payload does not look like a model checkpoint')
    return payload


def write_bytes_atomic(output_path: Path, payload: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix='.tmp', delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(output_path)


def _quote_env_value(value: str) -> str:
    return json.dumps(value)


def update_env_file(env_file: Path, updates: dict[str, str]) -> None:
    env_file = env_file.expanduser().resolve()
    lines = env_file.read_text(encoding='utf-8').splitlines() if env_file.exists() else []
    updated_lines: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            updated_lines.append(line)
            continue
        key, _value = line.split('=', 1)
        normalized_key = key.strip()
        if normalized_key in updates:
            updated_lines.append(f'{normalized_key}={_quote_env_value(updates[normalized_key])}')
            seen.add(normalized_key)
        else:
            updated_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            updated_lines.append(f'{key}={_quote_env_value(value)}')

    env_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=env_file.parent, suffix='.env.tmp', mode='w', encoding='utf-8', delete=False) as handle:
        handle.write('\n'.join(updated_lines).rstrip() + '\n')
        temp_path = Path(handle.name)
    temp_path.replace(env_file)


def _env_relative_path(output_path: Path, env_file: Path) -> str:
    try:
        return os.path.relpath(output_path, start=env_file.parent)
    except ValueError:
        return str(output_path)


def _resolve_output_path(output: Path) -> Path:
    expanded = output.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (repo_root() / expanded).resolve()


def _normalize_model_family(model_family: str | None) -> str | None:
    if model_family is None:
        return None
    resolved = str(model_family).strip()
    if resolved not in ALLOWED_MODEL_FAMILIES:
        raise ValueError(
            f'unsupported model family "{resolved}"; expected one of: {", ".join(sorted(ALLOWED_MODEL_FAMILIES))}',
        )
    return resolved


def fetch_sota_sar_weights(
    *,
    model_url: str,
    output: Path = DEFAULT_OUTPUT,
    env_file: Path = Path('.env'),
    model_family: str | None = None,
    model_version: str | None = None,
    env_model_path: str | None = None,
) -> dict[str, Any]:
    resolved_output = _resolve_output_path(output)
    resolved_env_file = env_file.expanduser().resolve()
    payload = download_model_payload(model_url)
    write_bytes_atomic(resolved_output, payload)

    env_updates = {
        'SAR_UNET_MODEL_PATH': str(env_model_path).strip()
        if env_model_path is not None and str(env_model_path).strip()
        else _env_relative_path(resolved_output, resolved_env_file),
    }
    normalized_family = _normalize_model_family(model_family)
    if normalized_family is not None:
        env_updates['SAR_UNET_MODEL_FAMILY'] = normalized_family
    if model_version is not None:
        env_updates['SAR_UNET_MODEL_VERSION'] = str(model_version).strip()
    update_env_file(resolved_env_file, env_updates)

    return {
        'status': 'ok',
        'output_path': str(resolved_output),
        'output_size_bytes': len(payload),
        'env_file': str(resolved_env_file),
        'env_updates': env_updates,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Download a signed SAR checkpoint and wire SAR_UNET_MODEL_PATH in .env')
    parser.add_argument('--model-url', required=True)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--model-family')
    parser.add_argument('--model-version')
    parser.add_argument('--env-model-path')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = fetch_sota_sar_weights(
        model_url=args.model_url,
        output=args.output,
        env_file=args.env_file,
        model_family=args.model_family,
        model_version=args.model_version,
        env_model_path=args.env_model_path,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
