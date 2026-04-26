from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.common.regions import repo_root


MODAL_SECRET_NAME = 'avalanche-supabase-secrets'
MODAL_APP_REF = 'backend/modal_worker_app.py'
MODAL_DEM_SOURCE_ROOT = 'backend/data/dem'
GITHUB_PRODUCTION_ENVIRONMENT = 'production'
MOCK_ARCHIVE_NAME = 'snowslide_mock.zip'


@dataclass(frozen=True)
class RolloutEnv:
    env_file: Path
    raw_values: dict[str, str]
    supabase_url: str | None
    supabase_service_role_key: str | None
    supabase_anon_key: str | None
    gee_service_account_email: str | None
    gee_key_file: Path | None
    gee_service_account_json: str | None
    modal_worker_token: str | None
    modal_token_id: str | None
    modal_token_secret: str | None
    modal_worker_url: str | None
    admin_user_ids: str | None
    admin_user_emails: str | None
    sar_unet_model_path: str | None
    gemini_api_key: str | None
    newsdata_api_key: str | None


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_wrapping_quotes(value)
    return values


def _resolve_path(env_file: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (env_file.parent / candidate).resolve()


def _load_gee_service_account_json(key_file: Path | None) -> str | None:
    if key_file is None or not key_file.exists():
        return None
    parsed = json.loads(key_file.read_text(encoding='utf-8'))
    return json.dumps(parsed, separators=(',', ':'))


def load_rollout_env(env_file: Path) -> RolloutEnv:
    resolved_env_file = env_file.expanduser().resolve()
    raw_values = parse_env_file(resolved_env_file)
    gee_key_file = _resolve_path(resolved_env_file, raw_values.get('GEE_KEY_FILE'))
    return RolloutEnv(
        env_file=resolved_env_file,
        raw_values=raw_values,
        supabase_url=raw_values.get('SUPABASE_URL') or raw_values.get('VITE_SUPABASE_URL'),
        supabase_service_role_key=raw_values.get('SUPABASE_SERVICE_ROLE_KEY'),
        supabase_anon_key=raw_values.get('SUPABASE_ANON_KEY') or raw_values.get('VITE_SUPABASE_PUBLISHABLE_KEY'),
        gee_service_account_email=raw_values.get('GEE_SERVICE_ACCOUNT_EMAIL'),
        gee_key_file=gee_key_file,
        gee_service_account_json=_load_gee_service_account_json(gee_key_file),
        modal_worker_token=raw_values.get('MODAL_WORKER_TOKEN'),
        modal_token_id=raw_values.get('MODAL_TOKEN_ID'),
        modal_token_secret=raw_values.get('MODAL_TOKEN_SECRET'),
        modal_worker_url=raw_values.get('MODAL_WORKER_URL'),
        admin_user_ids=raw_values.get('ADMIN_USER_IDS'),
        admin_user_emails=raw_values.get('ADMIN_USER_EMAILS'),
        sar_unet_model_path=raw_values.get('SAR_UNET_MODEL_PATH'),
        gemini_api_key=raw_values.get('GEMINI_API_KEY'),
        newsdata_api_key=raw_values.get('NEWSDATA_API_KEY'),
    )


def _required_now_missing(env: RolloutEnv) -> list[str]:
    missing: list[str] = []
    if not env.supabase_url:
        missing.append('SUPABASE_URL or VITE_SUPABASE_URL')
    if not env.supabase_service_role_key:
        missing.append('SUPABASE_SERVICE_ROLE_KEY')
    if not env.supabase_anon_key:
        missing.append('SUPABASE_ANON_KEY or VITE_SUPABASE_PUBLISHABLE_KEY')
    if not env.gee_service_account_email:
        missing.append('GEE_SERVICE_ACCOUNT_EMAIL')
    if env.gee_key_file is None:
        missing.append('GEE_KEY_FILE')
    elif not env.gee_key_file.exists():
        missing.append('GEE_KEY_FILE (existing file)')
    elif not env.gee_service_account_json:
        missing.append('GEE_SERVICE_ACCOUNT_JSON (derived from GEE_KEY_FILE)')
    return missing


def _required_rollout_missing(env: RolloutEnv) -> list[str]:
    missing: list[str] = []
    if not env.modal_worker_token:
        missing.append('MODAL_WORKER_TOKEN')
    if not env.modal_token_id:
        missing.append('MODAL_TOKEN_ID')
    if not env.modal_token_secret:
        missing.append('MODAL_TOKEN_SECRET')
    if not env.admin_user_ids and not env.admin_user_emails:
        missing.append('ADMIN_USER_EMAILS or ADMIN_USER_IDS')
    return missing


def validate_rollout_env(env_file: Path) -> dict[str, Any]:
    env = load_rollout_env(env_file)
    resolved_aliases: list[str] = []
    if 'SUPABASE_URL' not in env.raw_values and env.supabase_url:
        resolved_aliases.append('SUPABASE_URL<-VITE_SUPABASE_URL')
    if 'SUPABASE_ANON_KEY' not in env.raw_values and env.supabase_anon_key:
        resolved_aliases.append('SUPABASE_ANON_KEY<-VITE_SUPABASE_PUBLISHABLE_KEY')
    if env.gee_key_file is not None:
        resolved_aliases.append('GEE_SERVICE_ACCOUNT_JSON<-GEE_KEY_FILE')
    rollout_state = 'weights_ready' if env.sar_unet_model_path else 'refs_ready_only'
    next_blocker = None
    if not env.sar_unet_model_path:
        next_blocker = 'SAR_UNET_MODEL_PATH is not configured; held-out sar-segment and evaluate_release remain blocked'
    return {
        'status': 'ok' if not _required_now_missing(env) and not _required_rollout_missing(env) else 'invalid',
        'env_file': str(env.env_file),
        'missing_required_now': _required_now_missing(env),
        'missing_required_for_slice': _required_rollout_missing(env),
        'resolved_aliases': resolved_aliases,
        'rollout_state': rollout_state,
        'next_blocker': next_blocker,
    }


def build_github_secret_values(env: RolloutEnv, *, modal_worker_url: str | None = None) -> dict[str, str]:
    values = {
        'SUPABASE_URL': env.supabase_url or '',
        'SUPABASE_SERVICE_ROLE_KEY': env.supabase_service_role_key or '',
        'MODAL_TOKEN_ID': env.modal_token_id or '',
        'MODAL_TOKEN_SECRET': env.modal_token_secret or '',
        'MODAL_WORKER_TOKEN': env.modal_worker_token or '',
        'GEE_SERVICE_ACCOUNT_EMAIL': env.gee_service_account_email or '',
        'GEE_SERVICE_ACCOUNT_JSON': env.gee_service_account_json or '',
    }
    if env.gemini_api_key:
        values['GEMINI_API_KEY'] = env.gemini_api_key
    if env.newsdata_api_key:
        values['NEWSDATA_API_KEY'] = env.newsdata_api_key
    if modal_worker_url:
        values['MODAL_WORKER_URL'] = modal_worker_url
    return values


def build_modal_secret_values(env: RolloutEnv) -> dict[str, str]:
    values = {
        'SUPABASE_URL': env.supabase_url or '',
        'SUPABASE_SERVICE_ROLE_KEY': env.supabase_service_role_key or '',
        'MODAL_WORKER_TOKEN': env.modal_worker_token or '',
    }
    if env.sar_unet_model_path:
        values['SAR_UNET_MODEL_PATH'] = env.sar_unet_model_path
    return values


def build_supabase_secret_values(env: RolloutEnv, *, modal_worker_url: str | None = None) -> dict[str, str]:
    values = {
        'MODAL_WORKER_TOKEN': env.modal_worker_token or '',
        'SUPABASE_ANON_KEY': env.supabase_anon_key or '',
    }
    if env.admin_user_ids:
        values['ADMIN_USER_IDS'] = env.admin_user_ids
    if env.admin_user_emails:
        values['ADMIN_USER_EMAILS'] = env.admin_user_emails
    if modal_worker_url:
        values['MODAL_WORKER_URL'] = modal_worker_url
    return values


def _require_present(values: list[str], *, stage: str) -> None:
    if values:
        raise ValueError(f'{stage} is blocked until required settings are present: {", ".join(values)}')


def _require_cli_tools(names: tuple[str, ...]) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f'missing required CLI tool(s): {", ".join(missing)}')


def _describe_command(command: list[str]) -> str:
    return shlex.join(command)


def _run_checked(
    command: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f'command failed: {_describe_command(command)}\n'
            f'stdout:\n{result.stdout}\n'
            f'stderr:\n{result.stderr}'
        )
    return result


def _write_temp_json(payload: dict[str, str]) -> str:
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.json', delete=False) as handle:
        json.dump(payload, handle, sort_keys=True)
        return handle.name


def _write_temp_env(payload: dict[str, str]) -> str:
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.env', delete=False) as handle:
        for key, value in payload.items():
            handle.write(f'{key}={json.dumps(value)}\n')
        return handle.name


def _subprocess_env(env: RolloutEnv) -> dict[str, str]:
    child = os.environ.copy()
    child.update(env.raw_values)
    if env.supabase_url:
        child['SUPABASE_URL'] = env.supabase_url
    if env.supabase_service_role_key:
        child['SUPABASE_SERVICE_ROLE_KEY'] = env.supabase_service_role_key
    if env.supabase_anon_key:
        child['SUPABASE_ANON_KEY'] = env.supabase_anon_key
    if env.gee_service_account_email:
        child['GEE_SERVICE_ACCOUNT_EMAIL'] = env.gee_service_account_email
    if env.gee_key_file:
        child['GEE_KEY_FILE'] = str(env.gee_key_file)
    if env.gee_service_account_json:
        child['GEE_SERVICE_ACCOUNT_JSON'] = env.gee_service_account_json
    if env.modal_worker_token:
        child['MODAL_WORKER_TOKEN'] = env.modal_worker_token
    if env.modal_token_id:
        child['MODAL_TOKEN_ID'] = env.modal_token_id
    if env.modal_token_secret:
        child['MODAL_TOKEN_SECRET'] = env.modal_token_secret
    if env.sar_unet_model_path:
        child['SAR_UNET_MODEL_PATH'] = env.sar_unet_model_path
    return child


def _python_module_command(module: str, *args: str) -> list[str]:
    return [shutil.which('python3') or shutil.which('python') or 'python3', '-m', module, *args]


def _validate_source_zip(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.name == MOCK_ARCHIVE_NAME or resolved == repo_root() / MOCK_ARCHIVE_NAME:
        raise ValueError('synthetic or mock SnowSlide archives are not allowed for the release gate bootstrap')
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f'SnowSlide archive not found: {resolved}')
    if resolved.suffix.lower() != '.zip':
        raise ValueError(f'SnowSlide archive must be a .zip file: {resolved}')
    return resolved


def _extract_modal_worker_url(output: str) -> str | None:
    matches = re.findall(r'https://[^\s"\']+', output)
    for match in matches:
        if '.modal.' in match:
            return match.rstrip('/')
    return None


def _lookup_modal_worker_url(command_env: dict[str, str]) -> str | None:
    lookup = _run_checked(
        [
            shutil.which('python3') or shutil.which('python') or 'python3',
            '-c',
            (
                'import modal; '
                'print(modal.Function.from_name("avalanche-modal-worker", "worker_api").get_web_url())'
            ),
        ],
        env=command_env,
        cwd=repo_root(),
    )
    value = lookup.stdout.strip()
    return value or None


def sync_secrets(*, env_file: Path, repo: str, project_ref: str, apply: bool) -> dict[str, Any]:
    env = load_rollout_env(env_file)
    _require_present(_required_now_missing(env), stage='sync-secrets')
    _require_present(_required_rollout_missing(env), stage='sync-secrets')
    _require_cli_tools(('gh', 'modal', 'supabase'))

    github_values = build_github_secret_values(env)
    modal_values = build_modal_secret_values(env)
    supabase_values = build_supabase_secret_values(env)
    planned_commands = [
        *[_describe_command(['gh', 'secret', 'set', name, '--repo', repo]) for name in github_values],
        _describe_command(['modal', 'secret', 'create', MODAL_SECRET_NAME, '--from-json', '<temp.json>', '--force']),
        _describe_command(['supabase', 'secrets', 'set', '--env-file', '<temp.env>', '--project-ref', project_ref]),
    ]

    if not apply:
        return {
            'status': 'dry_run',
            'repo': repo,
            'project_ref': project_ref,
            'github_secret_names': sorted(github_values),
            'modal_secret_name': MODAL_SECRET_NAME,
            'modal_secret_keys': sorted(modal_values),
            'supabase_secret_names': sorted(supabase_values),
            'commands_planned': planned_commands,
        }

    for name, value in github_values.items():
        _run_checked(['gh', 'secret', 'set', name, '--repo', repo], input_text=value)

    modal_path = _write_temp_json(modal_values)
    supabase_path = _write_temp_env(supabase_values)
    try:
        _run_checked(['modal', 'secret', 'create', MODAL_SECRET_NAME, '--from-json', modal_path, '--force'])
        _run_checked(['supabase', 'secrets', 'set', '--env-file', supabase_path, '--project-ref', project_ref])
    finally:
        Path(modal_path).unlink(missing_ok=True)
        Path(supabase_path).unlink(missing_ok=True)

    return {
        'status': 'ok',
        'repo': repo,
        'project_ref': project_ref,
        'github_secret_names': sorted(github_values),
        'modal_secret_name': MODAL_SECRET_NAME,
        'supabase_secret_names': sorted(supabase_values),
    }


def seed_heldout(
    *,
    env_file: Path,
    source_zip: Path,
    set_key: str,
    source_version: str,
    apply: bool,
) -> dict[str, Any]:
    env = load_rollout_env(env_file)
    _require_present(_required_now_missing(env), stage='seed-heldout')
    resolved_zip = _validate_source_zip(source_zip)

    seed_command = _python_module_command(
        'backend.scripts.seed_snowslide_truth',
        '--source-zip',
        str(resolved_zip),
        '--set-key',
        set_key,
        '--source-version',
        source_version,
    )
    baseline_command = _python_module_command(
        'backend.scripts.materialize_release_baseline_masks',
        '--reference-set-key',
        set_key,
    )

    if not apply:
        return {
            'status': 'dry_run',
            'reference_set_key': set_key,
            'source_zip': str(resolved_zip),
            'commands_planned': [
                _describe_command(seed_command),
                _describe_command(baseline_command),
            ],
        }

    command_env = _subprocess_env(env)
    seed_result = _run_checked(seed_command, env=command_env, cwd=repo_root())
    baseline_result = _run_checked(baseline_command, env=command_env, cwd=repo_root())
    seed_payload = json.loads(seed_result.stdout.strip() or '{}')
    baseline_payload = json.loads(baseline_result.stdout.strip() or '{}')
    return {
        'status': 'ok',
        'reference_set_key': set_key,
        'source_zip': str(resolved_zip),
        'seed_result': seed_payload,
        'baseline_result': baseline_payload,
        'reference_set_status': baseline_payload.get('reference_set_status'),
    }


def _verify_github_environment(repo: str) -> None:
    _run_checked(['gh', 'api', f'repos/{repo}/environments/{GITHUB_PRODUCTION_ENVIRONMENT}'])


def deploy_worker(*, env_file: Path, repo: str, project_ref: str, apply: bool) -> dict[str, Any]:
    env = load_rollout_env(env_file)
    _require_present(_required_now_missing(env), stage='deploy-worker')
    _require_present(_required_rollout_missing(env), stage='deploy-worker')
    _require_cli_tools(('gh', 'modal', 'supabase'))

    planned_commands = [
        _describe_command(['gh', 'api', f'repos/{repo}/environments/{GITHUB_PRODUCTION_ENVIRONMENT}']),
        _describe_command(['modal', 'deploy', MODAL_APP_REF]),
        _describe_command(['modal', 'run', MODAL_APP_REF, '--source-root', MODAL_DEM_SOURCE_ROOT]),
        _describe_command(['gh', 'secret', 'set', 'MODAL_WORKER_URL', '--repo', repo]),
        _describe_command(['supabase', 'secrets', 'set', '--env-file', '<temp.env>', '--project-ref', project_ref]),
    ]
    rollout_state = 'weights_ready' if env.sar_unet_model_path else 'refs_ready_only'

    if not apply:
        return {
            'status': 'dry_run',
            'repo': repo,
            'project_ref': project_ref,
            'rollout_state': rollout_state,
            'commands_planned': planned_commands,
            'next_blocker': None if env.sar_unet_model_path else 'SAR_UNET_MODEL_PATH is missing; stop after refs-ready and do not run evaluate_release',
        }

    _verify_github_environment(repo)
    command_env = _subprocess_env(env)
    deploy_result = _run_checked(['modal', 'deploy', MODAL_APP_REF], env=command_env, cwd=repo_root())
    modal_worker_url = _extract_modal_worker_url(f'{deploy_result.stdout}\n{deploy_result.stderr}') or env.modal_worker_url
    if not modal_worker_url:
        modal_worker_url = _lookup_modal_worker_url(command_env)
    if not modal_worker_url:
        raise RuntimeError('unable to resolve MODAL_WORKER_URL from Modal deploy output')

    _run_checked(['modal', 'run', MODAL_APP_REF, '--source-root', MODAL_DEM_SOURCE_ROOT], env=command_env, cwd=repo_root())
    _run_checked(['gh', 'secret', 'set', 'MODAL_WORKER_URL', '--repo', repo], input_text=modal_worker_url)

    supabase_path = _write_temp_env(build_supabase_secret_values(env, modal_worker_url=modal_worker_url))
    try:
        _run_checked(['supabase', 'secrets', 'set', '--env-file', supabase_path, '--project-ref', project_ref])
    finally:
        Path(supabase_path).unlink(missing_ok=True)

    return {
        'status': 'ok',
        'repo': repo,
        'project_ref': project_ref,
        'modal_worker_url': modal_worker_url,
        'rollout_state': rollout_state,
        'next_blocker': None if env.sar_unet_model_path else 'SAR_UNET_MODEL_PATH is missing; refs are ready but evaluate_release remains blocked',
    }


def refs_ready(
    *,
    env_file: Path,
    source_zip: Path,
    set_key: str,
    source_version: str,
    repo: str,
    project_ref: str,
    apply: bool,
) -> dict[str, Any]:
    env = load_rollout_env(env_file)
    sync_result = sync_secrets(env_file=env_file, repo=repo, project_ref=project_ref, apply=apply)
    seed_result = seed_heldout(
        env_file=env_file,
        source_zip=source_zip,
        set_key=set_key,
        source_version=source_version,
        apply=apply,
    )
    deploy_result = deploy_worker(env_file=env_file, repo=repo, project_ref=project_ref, apply=apply)
    rollout_state = 'weights_ready' if env.sar_unet_model_path else 'refs_ready_only'
    return {
        'status': 'ok' if apply else 'dry_run',
        'reference_set_key': set_key,
        'source_version': source_version,
        'rollout_state': rollout_state,
        'sync_secrets': sync_result,
        'seed_heldout': seed_result,
        'deploy_worker': deploy_result,
        'blocked_steps': [] if env.sar_unet_model_path else [
            'held-out sar-segment',
            'evaluate_release',
            'promoted reruns',
            'train_mtslstm with sar_release_gate_passed=true',
        ],
    }


def _add_env_file_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--env-file', type=Path, default=Path('.env'), help='Local dotenv file to read explicitly')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Bootstrap the SnowSlide-held-out release gate rollout without exposing secrets')
    subparsers = parser.add_subparsers(dest='command', required=True)

    validate_parser = subparsers.add_parser('validate-env', help='Validate local rollout prerequisites from .env')
    _add_env_file_argument(validate_parser)

    sync_parser = subparsers.add_parser('sync-secrets', help='Sync rollout secrets to GitHub, Modal, and Supabase')
    _add_env_file_argument(sync_parser)
    sync_parser.add_argument('--repo', required=True, help='GitHub repository in owner/name form')
    sync_parser.add_argument('--project-ref', required=True, help='Supabase project ref')
    sync_parser.add_argument('--apply', action='store_true', help='Execute remote mutations instead of returning a dry-run plan')

    seed_parser = subparsers.add_parser('seed-heldout', help='Seed the authoritative SnowSlide held-out set from a local zip')
    _add_env_file_argument(seed_parser)
    seed_parser.add_argument('--source-zip', type=Path, required=True, help='Absolute or relative path to the real SnowSlide archive zip')
    seed_parser.add_argument('--set-key', required=True, help='Authoritative held-out reference-set key')
    seed_parser.add_argument('--source-version', required=True, help='External dataset version identifier')
    seed_parser.add_argument('--apply', action='store_true', help='Run the seed and baseline materialization CLIs')

    deploy_parser = subparsers.add_parser('deploy-worker', help='Deploy the Modal worker and seed DEMs into the persistent volume')
    _add_env_file_argument(deploy_parser)
    deploy_parser.add_argument('--repo', required=True, help='GitHub repository in owner/name form')
    deploy_parser.add_argument('--project-ref', required=True, help='Supabase project ref')
    deploy_parser.add_argument('--apply', action='store_true', help='Execute the deploy instead of returning a dry-run plan')

    refs_parser = subparsers.add_parser('refs-ready', help='Run secret sync, held-out seed, and worker deploy up to the refs-ready checkpoint')
    _add_env_file_argument(refs_parser)
    refs_parser.add_argument('--source-zip', type=Path, required=True, help='Absolute or relative path to the real SnowSlide archive zip')
    refs_parser.add_argument('--set-key', required=True, help='Authoritative held-out reference-set key')
    refs_parser.add_argument('--source-version', required=True, help='External dataset version identifier')
    refs_parser.add_argument('--repo', required=True, help='GitHub repository in owner/name form')
    refs_parser.add_argument('--project-ref', required=True, help='Supabase project ref')
    refs_parser.add_argument('--apply', action='store_true', help='Execute remote mutations instead of returning a dry-run plan')

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == 'validate-env':
        result = validate_rollout_env(args.env_file)
    elif args.command == 'sync-secrets':
        result = sync_secrets(
            env_file=args.env_file,
            repo=args.repo,
            project_ref=args.project_ref,
            apply=args.apply,
        )
    elif args.command == 'seed-heldout':
        result = seed_heldout(
            env_file=args.env_file,
            source_zip=args.source_zip,
            set_key=args.set_key,
            source_version=args.source_version,
            apply=args.apply,
        )
    elif args.command == 'deploy-worker':
        result = deploy_worker(
            env_file=args.env_file,
            repo=args.repo,
            project_ref=args.project_ref,
            apply=args.apply,
        )
    else:
        result = refs_ready(
            env_file=args.env_file,
            source_zip=args.source_zip,
            set_key=args.set_key,
            source_version=args.source_version,
            repo=args.repo,
            project_ref=args.project_ref,
            apply=args.apply,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
