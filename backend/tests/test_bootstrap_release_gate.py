from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.bootstrap_release_gate import (
    build_github_secret_values,
    build_modal_secret_values,
    build_supabase_secret_values,
    deploy_worker,
    load_rollout_env,
    refs_ready,
    seed_heldout,
    sync_secrets,
    validate_rollout_env,
)


class BootstrapReleaseGateTests(unittest.TestCase):
    def _write_env(
        self,
        root: Path,
        *,
        include_admin: bool = True,
        include_weights: bool = False,
    ) -> Path:
        gee_key = root / 'gee-service-account.json'
        gee_key.write_text(
            json.dumps({
                'type': 'service_account',
                'project_id': 'test-project',
                'private_key_id': 'private-key-id',
                'private_key': '-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n',
                'client_email': 'gee@example.com',
            }),
            encoding='utf-8',
        )
        lines = [
            'VITE_SUPABASE_URL=https://supabase.example.test',
            'VITE_SUPABASE_PUBLISHABLE_KEY=anon-public-key',
            'SUPABASE_SERVICE_ROLE_KEY=service-role-secret',
            'GEE_SERVICE_ACCOUNT_EMAIL=gee@example.com',
            f'GEE_KEY_FILE={gee_key.name}',
            'MODAL_WORKER_TOKEN=worker-token-secret',
            'MODAL_TOKEN_ID=modal-token-id',
            'MODAL_TOKEN_SECRET=modal-token-secret',
            'GEMINI_API_KEY=gemini-secret',
            'NEWSDATA_API_KEY=newsdata-secret',
        ]
        if include_admin:
            lines.append('ADMIN_USER_EMAILS=ops@example.com')
        if include_weights:
            lines.append('SAR_UNET_MODEL_PATH=/artifacts/checkpoints/sar.ckpt')
        env_path = root / '.env'
        env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return env_path

    def test_validate_rollout_env_uses_aliases_without_echoing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = self._write_env(Path(tmpdir))

            result = validate_rollout_env(env_path)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['rollout_state'], 'refs_ready_only')
        self.assertIn('SUPABASE_URL<-VITE_SUPABASE_URL', result['resolved_aliases'])
        self.assertIn('SUPABASE_ANON_KEY<-VITE_SUPABASE_PUBLISHABLE_KEY', result['resolved_aliases'])
        dumped = json.dumps(result)
        self.assertNotIn('service-role-secret', dumped)
        self.assertNotIn('worker-token-secret', dumped)
        self.assertIn('SAR_UNET_MODEL_PATH is not configured', result['next_blocker'])

    def test_secret_builders_include_expected_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = load_rollout_env(self._write_env(Path(tmpdir), include_weights=True))

        github_values = build_github_secret_values(env, modal_worker_url='https://worker.modal.run')
        modal_values = build_modal_secret_values(env)
        supabase_values = build_supabase_secret_values(env, modal_worker_url='https://worker.modal.run')

        self.assertEqual(github_values['SUPABASE_URL'], 'https://supabase.example.test')
        self.assertEqual(github_values['MODAL_WORKER_URL'], 'https://worker.modal.run')
        self.assertIn('GEE_SERVICE_ACCOUNT_JSON', github_values)
        self.assertTrue(github_values['GEE_SERVICE_ACCOUNT_JSON'].startswith('{'))
        self.assertEqual(modal_values['SAR_UNET_MODEL_PATH'], '/artifacts/checkpoints/sar.ckpt')
        self.assertEqual(supabase_values['SUPABASE_ANON_KEY'], 'anon-public-key')
        self.assertEqual(supabase_values['ADMIN_USER_EMAILS'], 'ops@example.com')

    @patch('backend.scripts.bootstrap_release_gate.shutil.which', return_value='/usr/bin/mock')
    def test_sync_secrets_dry_run_builds_expected_commands(self, _which_mock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = self._write_env(Path(tmpdir))

            result = sync_secrets(
                env_file=env_path,
                repo='sanjabh1103/avalanche-insight-hub',
                project_ref='fzheroisjhxnairglelv',
                apply=False,
            )

        self.assertEqual(result['status'], 'dry_run')
        self.assertIn('SUPABASE_URL', result['github_secret_names'])
        self.assertIn('MODAL_WORKER_TOKEN', result['supabase_secret_names'])
        self.assertTrue(any(command.startswith('modal secret create avalanche-supabase-secrets --from-json') for command in result['commands_planned']))
        self.assertIn('gh secret set SUPABASE_URL --repo sanjabh1103/avalanche-insight-hub', result['commands_planned'])

    def test_sync_secrets_requires_admin_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = self._write_env(Path(tmpdir), include_admin=False)

            with self.assertRaisesRegex(ValueError, 'ADMIN_USER_EMAILS or ADMIN_USER_IDS'):
                sync_secrets(
                    env_file=env_path,
                    repo='sanjabh1103/avalanche-insight-hub',
                    project_ref='fzheroisjhxnairglelv',
                    apply=False,
                )

    def test_seed_heldout_rejects_mock_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = self._write_env(root)
            mock_archive = root / 'snowslide_mock.zip'
            mock_archive.write_bytes(b'not-real')

            with self.assertRaisesRegex(ValueError, 'synthetic or mock SnowSlide archives'):
                seed_heldout(
                    env_file=env_path,
                    source_zip=mock_archive,
                    set_key='snowslide-heldout-v1',
                    source_version='2026-04-25',
                    apply=False,
                )

    @patch('backend.scripts.bootstrap_release_gate.shutil.which', return_value=None)
    def test_deploy_worker_requires_clis(self, _which_mock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = self._write_env(Path(tmpdir))

            with self.assertRaisesRegex(RuntimeError, 'missing required CLI tool'):
                deploy_worker(
                    env_file=env_path,
                    repo='sanjabh1103/avalanche-insight-hub',
                    project_ref='fzheroisjhxnairglelv',
                    apply=False,
                )

    @patch('backend.scripts.bootstrap_release_gate.shutil.which', return_value='/usr/bin/mock')
    def test_refs_ready_finishes_in_refs_ready_only_state_without_weights(self, _which_mock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = self._write_env(root, include_weights=False)
            source_zip = root / 'real-snowslide.zip'
            source_zip.write_bytes(b'PK\x03\x04')

            result = refs_ready(
                env_file=env_path,
                source_zip=source_zip,
                set_key='snowslide-heldout-v1',
                source_version='2026-04-25',
                repo='sanjabh1103/avalanche-insight-hub',
                project_ref='fzheroisjhxnairglelv',
                apply=False,
            )

        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['rollout_state'], 'refs_ready_only')
        self.assertIn('evaluate_release', result['blocked_steps'])
        self.assertEqual(result['seed_heldout']['status'], 'dry_run')
        self.assertEqual(result['deploy_worker']['status'], 'dry_run')


if __name__ == '__main__':
    unittest.main()
