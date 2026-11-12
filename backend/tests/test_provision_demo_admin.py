from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.scripts.provision_demo_admin import (
    SupabaseAdminEnv,
    SupabaseAuthAdminClient,
    build_admin_payload,
    create_or_update_demo_admin,
    load_admin_env,
)


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f'http {self.status_code}')

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, *, pages=None, created=None, updated=None) -> None:
        self.pages = pages or []
        self.created = created or {}
        self.updated = updated or {}
        self.get_calls = []
        self.post_calls = []
        self.put_calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_calls.append((url, headers, params, timeout))
        page = int(params.get('page', 1)) if params else 1
        try:
            payload = self.pages[page - 1]
        except IndexError:
            payload = {'users': []}
        return _FakeResponse(payload)

    def post(self, url, headers=None, json=None, timeout=None):
        self.post_calls.append((url, headers, json, timeout))
        return _FakeResponse(self.created)

    def put(self, url, headers=None, json=None, timeout=None):
        self.put_calls.append((url, headers, json, timeout))
        return _FakeResponse(self.updated)


class ProvisionDemoAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_file = Path(self.temp_dir.name) / '.env'
        self.env_file.write_text(
            'SUPABASE_URL=https://example.supabase.co\n'
            'SUPABASE_SERVICE_ROLE_KEY=service-role-secret\n',
            encoding='utf-8',
        )
        self.original_password = os.environ.get('DEMO_ADMIN_PASSWORD')
        os.environ['DEMO_ADMIN_PASSWORD'] = 'demo-password'

    def tearDown(self) -> None:
        if self.original_password is None:
            os.environ.pop('DEMO_ADMIN_PASSWORD', None)
        else:
            os.environ['DEMO_ADMIN_PASSWORD'] = self.original_password
        self.temp_dir.cleanup()

    def test_load_admin_env_supports_standard_supabase_keys(self) -> None:
        env = load_admin_env(self.env_file)
        self.assertEqual(
            env,
            SupabaseAdminEnv(
                supabase_url='https://example.supabase.co',
                service_role_key='service-role-secret',
            ),
        )

    def test_build_admin_payload_sets_confirmed_admin_role(self) -> None:
        payload = build_admin_payload('admin@insight-hub.local', 'secret')
        self.assertEqual(payload['email'], 'admin@insight-hub.local')
        self.assertEqual(payload['password'], 'secret')
        self.assertTrue(payload['email_confirm'])
        self.assertEqual(payload['app_metadata']['roles'], ['admin'])

    def test_create_or_update_demo_admin_creates_missing_user(self) -> None:
        session = _FakeSession(
            pages=[{'users': []}],
            created={
                'id': 'user-1',
                'email': 'admin@insight-hub.local',
                'app_metadata': {'roles': ['admin']},
            },
        )

        result = create_or_update_demo_admin(
            env_file=self.env_file,
            email='admin@insight-hub.local',
            password_env='DEMO_ADMIN_PASSWORD',
            session=session,
        )

        self.assertEqual(result['action'], 'created')
        self.assertEqual(result['user_id'], 'user-1')
        self.assertEqual(result['app_metadata_roles'], ['admin'])
        self.assertEqual(len(session.post_calls), 1)
        self.assertEqual(len(session.put_calls), 0)

    def test_create_or_update_demo_admin_updates_existing_user(self) -> None:
        session = _FakeSession(
            pages=[{
                'users': [{
                    'id': 'user-2',
                    'email': 'admin@insight-hub.local',
                    'app_metadata': {'roles': ['viewer']},
                }],
            }],
            updated={
                'id': 'user-2',
                'email': 'admin@insight-hub.local',
                'app_metadata': {'roles': ['admin']},
            },
        )

        result = create_or_update_demo_admin(
            env_file=self.env_file,
            email='admin@insight-hub.local',
            password_env='DEMO_ADMIN_PASSWORD',
            session=session,
        )

        self.assertEqual(result['action'], 'updated')
        self.assertEqual(result['user_id'], 'user-2')
        self.assertEqual(result['app_metadata_roles'], ['admin'])
        self.assertEqual(len(session.post_calls), 0)
        self.assertEqual(len(session.put_calls), 1)

    def test_auth_admin_client_finds_user_by_email_case_insensitively(self) -> None:
        env = SupabaseAdminEnv(
            supabase_url='https://example.supabase.co',
            service_role_key='service-role-secret',
        )
        session = _FakeSession(
            pages=[{
                'users': [{
                    'id': 'user-3',
                    'email': 'Admin@Insight-Hub.Local',
                }],
            }],
        )
        client = SupabaseAuthAdminClient(env, session=session)

        user = client.find_user_by_email('admin@insight-hub.local')

        self.assertIsNotNone(user)
        self.assertEqual(user['id'], 'user-3')


if __name__ == '__main__':
    unittest.main()
