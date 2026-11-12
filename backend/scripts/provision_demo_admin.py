from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


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


@dataclass(frozen=True)
class SupabaseAdminEnv:
    supabase_url: str
    service_role_key: str


def load_admin_env(env_file: Path) -> SupabaseAdminEnv:
    raw_values = parse_env_file(env_file.expanduser().resolve())
    supabase_url = raw_values.get('SUPABASE_URL') or raw_values.get('VITE_SUPABASE_URL')
    service_role_key = raw_values.get('SUPABASE_SERVICE_ROLE_KEY')
    if not supabase_url or not service_role_key:
        raise RuntimeError('SUPABASE_URL/VITE_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required')
    return SupabaseAdminEnv(
        supabase_url=supabase_url.rstrip('/'),
        service_role_key=service_role_key,
    )


class SupabaseAuthAdminClient:
    def __init__(self, env: SupabaseAdminEnv, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._base_url = f'{env.supabase_url}/auth/v1/admin'
        self._headers = {
            'apikey': env.service_role_key,
            'Authorization': f'Bearer {env.service_role_key}',
            'Content-Type': 'application/json',
        }

    def list_users(self, *, page: int = 1, per_page: int = 200) -> list[dict[str, Any]]:
        response = self._session.get(
            f'{self._base_url}/users',
            headers=self._headers,
            params={'page': page, 'per_page': per_page},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get('users'), list):
            return payload['users']
        if isinstance(payload, list):
            return payload
        raise RuntimeError('Unexpected list users response shape from Supabase Auth Admin API')

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._session.post(
            f'{self._base_url}/users',
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def update_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._session.put(
            f'{self._base_url}/users/{user_id}',
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized_email = email.strip().lower()
        page = 1
        per_page = 200
        while True:
            users = self.list_users(page=page, per_page=per_page)
            if not users:
                return None
            for user in users:
                user_email = str(user.get('email') or '').strip().lower()
                if user_email == normalized_email:
                    return user
            if len(users) < per_page:
                return None
            page += 1


def build_admin_payload(email: str, password: str) -> dict[str, Any]:
    return {
        'email': email,
        'password': password,
        'email_confirm': True,
        'app_metadata': {
            'roles': ['admin'],
        },
    }


def create_or_update_demo_admin(
    *,
    env_file: Path,
    email: str,
    password_env: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    password = os.environ.get(password_env)
    if not password:
        raise RuntimeError(f'{password_env} is required in the environment')

    env = load_admin_env(env_file)
    client = SupabaseAuthAdminClient(env, session=session)
    payload = build_admin_payload(email=email, password=password)
    existing_user = client.find_user_by_email(email)

    if existing_user is None:
        user = client.create_user(payload)
        action = 'created'
    else:
        user = client.update_user(str(existing_user['id']), payload)
        action = 'updated'

    roles = []
    app_metadata = user.get('app_metadata')
    if isinstance(app_metadata, dict):
        raw_roles = app_metadata.get('roles')
        if isinstance(raw_roles, list):
            roles = [str(role) for role in raw_roles if isinstance(role, (str, int, float))]

    return {
        'user_id': user.get('id'),
        'email': user.get('email'),
        'action': action,
        'app_metadata_roles': roles,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Create or update the demo admin account in Supabase Auth.')
    parser.add_argument('--env-file', type=Path, required=True, help='Path to the environment file containing Supabase credentials.')
    parser.add_argument('--email', required=True, help='Demo admin email address to create or update.')
    parser.add_argument(
        '--password-env',
        required=True,
        help='Environment variable name that contains the demo admin password.',
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = create_or_update_demo_admin(
        env_file=args.env_file,
        email=args.email,
        password_env=args.password_env,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
