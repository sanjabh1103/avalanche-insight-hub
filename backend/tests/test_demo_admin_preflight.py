from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.demo_admin_preflight import hydrate_demo_admin_password, run_demo_admin_preflight


class DemoAdminPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_file = Path(self.temp_dir.name) / '.env'
        self.original_password = os.environ.get('DEMO_ADMIN_PASSWORD')
        os.environ.pop('DEMO_ADMIN_PASSWORD', None)

    def tearDown(self) -> None:
        if self.original_password is None:
            os.environ.pop('DEMO_ADMIN_PASSWORD', None)
        else:
            os.environ['DEMO_ADMIN_PASSWORD'] = self.original_password
        self.temp_dir.cleanup()

    @patch('backend.scripts.demo_admin_preflight.create_or_update_demo_admin')
    def test_run_demo_admin_preflight_uses_shell_password_when_present(
        self,
        create_or_update_demo_admin_mock,
    ) -> None:
        self.env_file.write_text('', encoding='utf-8')
        os.environ['DEMO_ADMIN_PASSWORD'] = 'shell-secret'
        create_or_update_demo_admin_mock.return_value = {'action': 'updated'}

        result = run_demo_admin_preflight(
            env_file=self.env_file,
            email='admin@insight-hub.local',
            password_env='DEMO_ADMIN_PASSWORD',
        )

        self.assertEqual(result, {'action': 'updated'})
        self.assertEqual(os.environ['DEMO_ADMIN_PASSWORD'], 'shell-secret')
        create_or_update_demo_admin_mock.assert_called_once()

    @patch('backend.scripts.demo_admin_preflight.create_or_update_demo_admin')
    def test_run_demo_admin_preflight_hydrates_password_from_env_file(
        self,
        create_or_update_demo_admin_mock,
    ) -> None:
        self.env_file.write_text('DEMO_ADMIN_PASSWORD=env-file-secret\n', encoding='utf-8')
        create_or_update_demo_admin_mock.return_value = {'action': 'created'}

        result = run_demo_admin_preflight(
            env_file=self.env_file,
            email='admin@insight-hub.local',
            password_env='DEMO_ADMIN_PASSWORD',
        )

        self.assertEqual(result, {'action': 'created'})
        self.assertEqual(os.environ['DEMO_ADMIN_PASSWORD'], 'env-file-secret')
        create_or_update_demo_admin_mock.assert_called_once()

    def test_hydrate_demo_admin_password_fails_when_missing_everywhere(self) -> None:
        self.env_file.write_text('SUPABASE_URL=https://example.supabase.co\n', encoding='utf-8')

        with self.assertRaisesRegex(RuntimeError, 'DEMO_ADMIN_PASSWORD is required'):
            hydrate_demo_admin_password(
                env_file=self.env_file,
                password_env='DEMO_ADMIN_PASSWORD',
            )


if __name__ == '__main__':
    unittest.main()
