from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from backend.scripts.provision_demo_admin import create_or_update_demo_admin, parse_env_file


def hydrate_demo_admin_password(*, env_file: Path, password_env: str) -> str:
    password = os.environ.get(password_env)
    if password:
        return password
    env_path = env_file.expanduser().resolve()
    if env_path.exists():
        file_values = parse_env_file(env_path)
        file_password = file_values.get(password_env)
        if file_password:
            os.environ[password_env] = file_password
            return file_password
    raise RuntimeError(f'{password_env} is required in the environment or {env_file}')


def run_demo_admin_preflight(
    *,
    env_file: Path,
    email: str,
    password_env: str,
) -> dict[str, Any]:
    hydrate_demo_admin_password(env_file=env_file, password_env=password_env)
    return create_or_update_demo_admin(
        env_file=env_file,
        email=email,
        password_env=password_env,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Hydrate the demo admin password and provision the demo admin account.')
    parser.add_argument('--env-file', type=Path, default=Path('.env'), help='Env file that may contain DEMO_ADMIN_PASSWORD and Supabase credentials.')
    parser.add_argument('--email', default='admin@insight-hub.local', help='Demo admin email address to create or update.')
    parser.add_argument('--password-env', default='DEMO_ADMIN_PASSWORD', help='Environment variable name that contains the demo admin password.')
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_demo_admin_preflight(
        env_file=args.env_file,
        email=args.email,
        password_env=args.password_env,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
