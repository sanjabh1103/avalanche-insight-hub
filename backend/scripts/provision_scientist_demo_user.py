"""Provision a scientist-only Supabase Auth demo user.

This script is intentionally local-operator only. It never prints generated
passwords or elevated Supabase keys, and it writes only scientist login
credentials to an ignored local env file.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_EMAIL = 'scientist@insight-hub.local'
DEFAULT_ENV_OUTPUT = '.env.scientist.local'
MANAGEMENT_API_BASE = 'https://api.supabase.com'


class ProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseConnection:
    url: str
    project_ref: str
    admin_key: str
    admin_key_source: str


@dataclass(frozen=True)
class ProvisionedScientistUser:
    email: str
    user_id: str
    created: bool
    env_path: Path
    admin_key_source: str

    def safe_summary(self) -> dict[str, Any]:
        return {
            'email': self.email,
            'user_id': self.user_id,
            'created': self.created,
            'env_path': str(self.env_path),
            'admin_key_source': self.admin_key_source,
            'password_written': True,
            'password_printed': False,
        }


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_value(name: str, file_values: dict[str, str]) -> str | None:
    return os.environ.get(name) or file_values.get(name)


def _project_ref_from_url(supabase_url: str) -> str:
    parsed = urlparse(supabase_url)
    host = parsed.netloc
    if not host.endswith('.supabase.co'):
        raise ProvisioningError(f'Cannot infer Supabase project ref from URL host: {host}')
    return host.split('.', 1)[0]


def _random_password(length: int = 28) -> str:
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*()-_=+'
    while True:
        candidate = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(char.islower() for char in candidate)
            and any(char.isupper() for char in candidate)
            and any(char.isdigit() for char in candidate)
            and any(char in '!@#$%^&*()-_=+' for char in candidate)
        ):
            return candidate


def _management_headers(access_token: str) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }


def _extract_key_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key_name in ('api_key', 'key', 'secret', 'value', 'token'):
            value = payload.get(key_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = payload.get('apiKey') or payload.get('api_key')
        if isinstance(nested, dict):
            return _extract_key_from_payload(nested)
    return None


def _find_admin_key_in_keys_payload(payload: Any) -> str | None:
    items = payload if isinstance(payload, list) else payload.get('api_keys', []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return None
    preferred_names = ('service_role', 'secret', 'sb_secret')
    for item in items:
        if not isinstance(item, dict):
            continue
        searchable = ' '.join(str(item.get(key) or '').lower() for key in ('name', 'type', 'role', 'id'))
        if any(name in searchable for name in preferred_names):
            found = _extract_key_from_payload(item)
            if found:
                return found
    return None


def _get_admin_key_from_management_api(project_ref: str, access_token: str) -> tuple[str, str]:
    headers = _management_headers(access_token)
    candidate_paths = (
        f'/v1/projects/{project_ref}/api-keys',
        f'/v1/projects/{project_ref}/api-keys?reveal=true',
        f'/v1/projects/{project_ref}/legacy-api-keys',
    )
    for path in candidate_paths:
        response = requests.get(f'{MANAGEMENT_API_BASE}{path}', headers=headers, timeout=30)
        if response.ok:
            key = _find_admin_key_in_keys_payload(response.json())
            if key:
                return key, 'supabase_management_api_existing_key'

    create_payloads = (
        {
            'name': 'scientist-demo-provisioner',
            'type': 'secret',
        },
        {
            'name': 'scientist-demo-provisioner',
            'key_type': 'secret',
        },
    )
    for payload in create_payloads:
        response = requests.post(
            f'{MANAGEMENT_API_BASE}/v1/projects/{project_ref}/api-keys',
            headers=headers,
            json=payload,
            timeout=30,
        )
        if response.ok:
            key = _extract_key_from_payload(response.json())
            if key:
                return key, 'supabase_management_api_created_secret_key'

    raise ProvisioningError(
        'No Supabase service/secret key found in environment and Management API did not return/create one. '
        'Provide SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY locally.'
    )


def resolve_supabase_connection(
    *,
    env_files: tuple[Path, ...] = (Path('.env.scientist.local'), Path('.env.local'), Path('.env.netlify')),
) -> SupabaseConnection:
    file_values: dict[str, str] = {}
    for path in env_files:
        file_values.update(_load_env_file(path))

    supabase_url = (
        _env_value('SUPABASE_URL', file_values)
        or _env_value('VITE_SUPABASE_URL', file_values)
    )
    if not supabase_url:
        raise ProvisioningError('SUPABASE_URL or VITE_SUPABASE_URL is required')

    project_ref = _project_ref_from_url(supabase_url)
    admin_key = (
        _env_value('SUPABASE_SERVICE_ROLE_KEY', file_values)
        or _env_value('SUPABASE_SECRET_KEY', file_values)
    )
    if admin_key:
        return SupabaseConnection(
            url=supabase_url.rstrip('/'),
            project_ref=project_ref,
            admin_key=admin_key,
            admin_key_source='local_env',
        )

    access_token = _env_value('SUPABASE_ACCESS_TOKEN', file_values)
    if not access_token:
        raise ProvisioningError('SUPABASE_SERVICE_ROLE_KEY, SUPABASE_SECRET_KEY, or SUPABASE_ACCESS_TOKEN is required')

    resolved_key, source = _get_admin_key_from_management_api(project_ref, access_token)
    return SupabaseConnection(
        url=supabase_url.rstrip('/'),
        project_ref=project_ref,
        admin_key=resolved_key,
        admin_key_source=source,
    )


def _auth_headers(admin_key: str) -> dict[str, str]:
    return {
        'apikey': admin_key,
        'Authorization': f'Bearer {admin_key}',
        'Content-Type': 'application/json',
    }


def _find_user_by_email(connection: SupabaseConnection, email: str) -> dict[str, Any] | None:
    page = 1
    while page <= 20:
        response = requests.get(
            f'{connection.url}/auth/v1/admin/users',
            headers=_auth_headers(connection.admin_key),
            params={'page': str(page), 'per_page': '100'},
            timeout=30,
        )
        if not response.ok:
            raise ProvisioningError(f'Failed to list users: HTTP {response.status_code}')
        payload = response.json()
        users = payload.get('users') if isinstance(payload, dict) else payload
        if not isinstance(users, list):
            return None
        for user in users:
            if isinstance(user, dict) and str(user.get('email') or '').lower() == email.lower():
                return user
        if len(users) < 100:
            return None
        page += 1
    return None


def _create_or_update_user(
    connection: SupabaseConnection,
    *,
    email: str,
    password: str,
) -> tuple[str, bool]:
    payload = {
        'email': email,
        'password': password,
        'email_confirm': True,
        'app_metadata': {'roles': ['scientist']},
        'user_metadata': {
            'display_name': 'Scientist Demo User',
            'purpose': 'scientist_validation_demo',
        },
    }
    existing = _find_user_by_email(connection, email)
    if existing and existing.get('id'):
        response = requests.put(
            f"{connection.url}/auth/v1/admin/users/{existing['id']}",
            headers=_auth_headers(connection.admin_key),
            json=payload,
            timeout=30,
        )
        if not response.ok:
            raise ProvisioningError(f'Failed to update scientist user: HTTP {response.status_code}')
        return str(existing['id']), False

    response = requests.post(
        f'{connection.url}/auth/v1/admin/users',
        headers=_auth_headers(connection.admin_key),
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise ProvisioningError(f'Failed to create scientist user: HTTP {response.status_code}')
    created = response.json()
    user_id = created.get('id') or created.get('user', {}).get('id')
    if not user_id:
        raise ProvisioningError('Supabase Auth did not return a user id')
    return str(user_id), True


def _write_scientist_env(
    path: Path,
    *,
    supabase_url: str,
    email: str,
    password: str,
    user_id: str,
) -> None:
    content = (
        '# Local scientist demo credentials. Do not commit or paste into chat.\n'
        f'SUPABASE_URL={supabase_url}\n'
        f'SCIENTIST_DEMO_EMAIL={email}\n'
        f'SCIENTIST_DEMO_PASSWORD={password}\n'
        f'SCIENTIST_DEMO_USER_ID={user_id}\n'
    )
    tmp_path = path.with_suffix(f'{path.suffix}.tmp')
    tmp_path.write_text(content, encoding='utf-8')
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def provision_scientist_demo_user(
    *,
    email: str = DEFAULT_EMAIL,
    env_output: Path = Path(DEFAULT_ENV_OUTPUT),
    password: str | None = None,
) -> ProvisionedScientistUser:
    connection = resolve_supabase_connection()
    generated_password = password or _random_password()
    user_id, created = _create_or_update_user(
        connection,
        email=email,
        password=generated_password,
    )
    _write_scientist_env(
        env_output,
        supabase_url=connection.url,
        email=email,
        password=generated_password,
        user_id=user_id,
    )
    return ProvisionedScientistUser(
        email=email,
        user_id=user_id,
        created=created,
        env_path=env_output,
        admin_key_source=connection.admin_key_source,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Provision a scientist-only Supabase Auth demo user.')
    parser.add_argument('--email', default=DEFAULT_EMAIL)
    parser.add_argument('--env-output', default=DEFAULT_ENV_OUTPUT)
    args = parser.parse_args(argv)

    result = provision_scientist_demo_user(
        email=args.email,
        env_output=Path(args.env_output),
    )
    print(json.dumps(result.safe_summary(), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
