from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MODAL_APP_NAME = 'avalanche-modal-worker'
DEFAULT_VOLUME_NAME = 'avalanche-artifacts'
PARTIAL_ARTIFACT_FILENAMES = {
    'sar_training_metrics.json',
    'train_sar_unet_manifest.json',
    'sar_model.pt',
    'european_sar_prediction_artifact.json',
}
OBSERVABILITY_FILENAMES = {
    'train_sar_unet_status.json',
    'train_sar_unet_error.json',
}


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload if isinstance(payload, dict) else {'raw': payload}


def _run_modal_command(
    command: list[str],
    *,
    modal_profile: str,
    modal_bin: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    env = os.environ.copy()
    env['MODAL_PROFILE'] = modal_profile
    completed = subprocess.run(
        [modal_bin, *command],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        'command': [modal_bin, *command],
        'returncode': completed.returncode,
        'stdout': completed.stdout,
        'stderr': completed.stderr,
    }


def _parse_volume_entries(command_result: dict[str, Any]) -> list[dict[str, Any]]:
    if int(command_result.get('returncode') or 0) != 0:
        return []
    stdout = str(command_result.get('stdout') or '').strip()
    if not stdout:
        return []
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            entries.append(item)
        else:
            entries.append({'name': str(item)})
    return entries


def _entry_name(entry: dict[str, Any]) -> str:
    for key in ('filename', 'Filename', 'name', 'Name', 'path', 'Path'):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).name
    return ''


def _summarize_logs(command_result: dict[str, Any], *, artifact_dir: str | None, candidate_model_version: str | None) -> dict[str, Any]:
    stdout = str(command_result.get('stdout') or '')
    lines = [line for line in stdout.splitlines() if line.strip()]
    filters = [item for item in (artifact_dir, Path(artifact_dir).name if artifact_dir else None, candidate_model_version) if item]
    matched_lines = [
        line
        for line in lines
        if any(str(filter_value) in line for filter_value in filters)
    ]
    return {
        'returncode': int(command_result.get('returncode') or 0),
        'line_count': len(lines),
        'last_lines': lines[-40:],
        'matched_lines': matched_lines[-40:],
        'stderr': str(command_result.get('stderr') or ''),
    }


def inspect_modal_sar_training_run(
    *,
    modal_profile: str,
    volume_name: str = DEFAULT_VOLUME_NAME,
    artifact_dir: str | None = None,
    local_result_path: Path | None = None,
    app_name: str = DEFAULT_MODAL_APP_NAME,
    modal_bin: str = 'modal',
    since: str = '4h',
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('inspection requires --modal-profile')
    local_result = _read_json(local_result_path)
    if artifact_dir is None and isinstance(local_result, dict):
        raw_artifact_dir = local_result.get('artifact_dir')
        if isinstance(raw_artifact_dir, str) and raw_artifact_dir.strip():
            artifact_dir = raw_artifact_dir.strip()
    candidate_model_version = None
    if isinstance(local_result, dict):
        raw_candidate = local_result.get('candidate_model_version') or local_result.get('model_version')
        if isinstance(raw_candidate, str) and raw_candidate.strip():
            candidate_model_version = raw_candidate.strip()

    logs_result = _run_modal_command(
        ['app', 'logs', app_name, '--since', since, '--timestamps', '--show-container-id'],
        modal_profile=profile,
        modal_bin=modal_bin,
        timeout_seconds=timeout_seconds,
    )
    containers_result = _run_modal_command(
        ['container', 'list'],
        modal_profile=profile,
        modal_bin=modal_bin,
        timeout_seconds=timeout_seconds,
    )
    volume_result: dict[str, Any] | None = None
    volume_entries: list[dict[str, Any]] = []
    if artifact_dir:
        volume_path = str(artifact_dir).strip()
        if volume_path.startswith('/artifacts/'):
            volume_path = volume_path[len('/artifacts'):]
        volume_path = '/' + volume_path.lstrip('/')
        volume_result = _run_modal_command(
            ['volume', 'ls', volume_name, volume_path, '--json'],
            modal_profile=profile,
            modal_bin=modal_bin,
            timeout_seconds=timeout_seconds,
        )
        volume_entries = _parse_volume_entries(volume_result)

    entry_names = sorted({name for name in (_entry_name(entry) for entry in volume_entries) if name})
    partial_names = sorted(name for name in entry_names if name in PARTIAL_ARTIFACT_FILENAMES)
    observability_names = sorted(name for name in entry_names if name in OBSERVABILITY_FILENAMES)
    active_container_text = f"{containers_result.get('stdout') or ''}\n{containers_result.get('stderr') or ''}"
    return {
        'version': 'modal_sar_training_inspection_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'modal_profile': profile,
        'app_name': app_name,
        'volume_name': volume_name,
        'artifact_dir': artifact_dir,
        'local_result_path': str(local_result_path) if local_result_path else None,
        'local_result': local_result,
        'logs_summary': _summarize_logs(
            logs_result,
            artifact_dir=artifact_dir,
            candidate_model_version=candidate_model_version,
        ),
        'volume_listing': {
            'command': volume_result.get('command') if volume_result else None,
            'returncode': volume_result.get('returncode') if volume_result else None,
            'entry_count': len(volume_entries),
            'entry_names': entry_names,
            'partial_artifacts': bool(partial_names),
            'partial_artifact_names': partial_names,
            'observability_artifacts': bool(observability_names),
            'observability_artifact_names': observability_names,
            'stderr': volume_result.get('stderr') if volume_result else None,
        },
        'containers': {
            'command': containers_result['command'],
            'returncode': containers_result['returncode'],
            'stdout': containers_result['stdout'],
            'stderr': containers_result['stderr'],
            'active_container_hint': bool(active_container_text.strip()) and 'None' not in active_container_text,
        },
        'mutated_volume': False,
        'downloaded_model_files': False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Inspect a Modal SAR training run without mutating the artifact volume.')
    parser.add_argument('--modal-profile', required=True)
    parser.add_argument('--volume-name', default=DEFAULT_VOLUME_NAME)
    parser.add_argument('--artifact-dir')
    parser.add_argument('--local-result', type=Path)
    parser.add_argument('--app-name', default=DEFAULT_MODAL_APP_NAME)
    parser.add_argument('--modal-bin', default='modal')
    parser.add_argument('--since', default='4h')
    parser.add_argument('--timeout-seconds', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = inspect_modal_sar_training_run(
            modal_profile=args.modal_profile,
            volume_name=args.volume_name,
            artifact_dir=args.artifact_dir,
            local_result_path=args.local_result,
            app_name=args.app_name,
            modal_bin=args.modal_bin,
            since=args.since,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        report = {
            'version': 'modal_sar_training_inspection_v1',
            'status': 'failed',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'modal_profile': str(args.modal_profile),
            'error': str(exc),
        }
        _write_json(args.output, report)
        return 1
    _write_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
