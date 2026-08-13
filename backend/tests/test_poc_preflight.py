"""Tests for POC preflight checks."""

from __future__ import annotations

import unittest
from collections import namedtuple
from unittest.mock import patch, MagicMock

from backend.common.poc_preflight import (
    PreflightStatus,
    PreflightResult,
    supabase_storage_preflight,
    supabase_project_identity_check,
    docker_daemon_preflight,
    disk_preflight,
    modal_preflight,
    run_all_preflights,
    _redact,
)


class FakeResponse:
    def __init__(self, status_code: int, *, text: str = '', content: bytes = b'') -> None:
        self.status_code = status_code
        self.text = text
        self.content = content

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class RedactTests(unittest.TestCase):
    def test_redact_short_value(self) -> None:
        self.assertEqual(_redact('abc'), 'abc***')

    def test_redact_long_value(self) -> None:
        result = _redact('abcdefghijklmnop')
        self.assertIn('abcdefgh', result)
        self.assertIn('redacted', result)

    def test_redact_empty(self) -> None:
        self.assertEqual(_redact(''), '<empty>')


class SupabaseStoragePreflightTests(unittest.TestCase):
    @patch('backend.common.poc_preflight.requests.get')
    def test_pass_on_200(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(200, text='[]')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key_1234567890',
        )
        self.assertTrue(result.is_pass)
        self.assertEqual(result.http_status, 200)

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_401(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(401, text='Unauthorized')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_bad_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.http_status, 401)
        self.assertEqual(result.error_class, 'AuthRejected')

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_402_quota(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(402, text='Quota exceeded')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'QuotaBlocked')

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_403(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(403, text='Forbidden')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'Forbidden')

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_404(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(404, text='Not found')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'NotFound')

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_500(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(500, text='Internal error')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'ServerError')

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_connection_error(self, mock_get: MagicMock) -> None:
        import requests as req
        mock_get.side_effect = req.ConnectionError('DNS failed')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'ConnectionError')

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_timeout(self, mock_get: MagicMock) -> None:
        import requests as req
        mock_get.side_effect = req.Timeout('timed out')
        result = supabase_storage_preflight(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            service_role_key='sbp_test_key',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'Timeout')

    def test_not_run_when_credentials_missing(self) -> None:
        result = supabase_storage_preflight(
            supabase_url=None,
            service_role_key=None,
        )
        self.assertEqual(result.status, PreflightStatus.NOT_RUN)
        self.assertIn('not set', result.detail)

    @patch('backend.common.poc_preflight.requests.get')
    def test_project_ref_mismatch_blocks(self, mock_get: MagicMock) -> None:
        result = supabase_storage_preflight(
            supabase_url='https://wrongproject.supabase.co',
            service_role_key='sbp_test_key',
            expected_project_ref='eyyellmffzzujyssaayb',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'ProjectRefMismatch')
        mock_get.assert_not_called()


class SupabaseProjectIdentityTests(unittest.TestCase):
    def test_pass_when_ref_matches(self) -> None:
        result = supabase_project_identity_check(
            supabase_url='https://eyyellmffzzujyssaayb.supabase.co',
            expected_project_ref='eyyellmffzzujyssaayb',
        )
        self.assertTrue(result.is_pass)

    def test_blocked_when_ref_mismatches(self) -> None:
        result = supabase_project_identity_check(
            supabase_url='https://wrongproject.supabase.co',
            expected_project_ref='eyyellmffzzujyssaayb',
        )
        self.assertTrue(result.is_blocked)

    def test_not_run_when_url_missing(self) -> None:
        result = supabase_project_identity_check(
            supabase_url=None,
            expected_project_ref='eyyellmffzzujyssaayb',
        )
        self.assertEqual(result.status, PreflightStatus.NOT_RUN)


DiskUsage = namedtuple('DiskUsage', ['total', 'used', 'free'])


class DockerPreflightTests(unittest.TestCase):
    @patch('backend.common.poc_preflight.subprocess.run')
    @patch('backend.common.poc_preflight.shutil.disk_usage')
    @patch('backend.common.poc_preflight.shutil.which')
    def test_pass_when_docker_reachable_and_disk_ok(
        self, mock_which: MagicMock, mock_du: MagicMock, mock_run: MagicMock,
    ) -> None:
        mock_which.return_value = '/usr/local/bin/docker'
        mock_du.return_value = DiskUsage(total=100*1024**3, used=80*1024**3, free=20*1024**3)
        mock_run.return_value = MagicMock(returncode=0, stdout='28.1.1', stderr='')

        result = docker_daemon_preflight(min_disk_gb=5.0)
        self.assertTrue(result.is_pass)
        self.assertIn('28.1.1', result.detail)

    @patch('backend.common.poc_preflight.shutil.which')
    def test_blocked_when_docker_not_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        result = docker_daemon_preflight()
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'DockerNotFound')

    @patch('backend.common.poc_preflight.subprocess.run')
    @patch('backend.common.poc_preflight.shutil.which')
    def test_blocked_when_docker_daemon_unreachable(
        self, mock_which: MagicMock, mock_run: MagicMock,
    ) -> None:
        mock_which.return_value = '/usr/local/bin/docker'
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='Cannot connect to Docker daemon')
        result = docker_daemon_preflight()
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'DockerDaemonUnreachable')


class DiskPreflightTests(unittest.TestCase):
    @patch('backend.common.poc_preflight.shutil.disk_usage')
    def test_pass_when_sufficient_disk(self, mock_du: MagicMock) -> None:
        mock_du.return_value = DiskUsage(total=100*1024**3, used=50*1024**3, free=50*1024**3)
        result = disk_preflight(min_gb=5.0)
        self.assertTrue(result.is_pass)

    @patch('backend.common.poc_preflight.shutil.disk_usage')
    def test_blocked_when_insufficient_disk(self, mock_du: MagicMock) -> None:
        mock_du.return_value = DiskUsage(total=100*1024**3, used=98*1024**3, free=2*1024**3)
        result = disk_preflight(min_gb=5.0)
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'InsufficientDisk')


class ModalPreflightTests(unittest.TestCase):
    @patch('backend.common.poc_preflight.requests.get')
    def test_pass_on_200(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(200)
        result = modal_preflight(
            modal_token_id='ak-test1234',
            modal_token_secret='as-test1234',
            modal_worker_url='https://modal.example.com',
        )
        self.assertTrue(result.is_pass)

    @patch('backend.common.poc_preflight.requests.get')
    def test_pass_on_401_auth_required(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(401, text='Unauthorized')
        result = modal_preflight(
            modal_token_id='ak-test1234',
            modal_token_secret='as-test1234',
            modal_worker_url='https://modal.example.com',
        )
        self.assertTrue(result.is_pass)
        self.assertIn('auth required', result.detail)

    @patch('backend.common.poc_preflight.requests.get')
    def test_blocked_on_500(self, mock_get: MagicMock) -> None:
        mock_get.return_value = FakeResponse(500, text='Server error')
        result = modal_preflight(
            modal_token_id='ak-test1234',
            modal_token_secret='as-test1234',
            modal_worker_url='https://modal.example.com',
        )
        self.assertTrue(result.is_blocked)
        self.assertEqual(result.error_class, 'ModalServerError')

    def test_not_run_when_credentials_missing(self) -> None:
        result = modal_preflight(
            modal_token_id=None,
            modal_token_secret=None,
            modal_worker_url='https://modal.example.com',
        )
        self.assertEqual(result.status, PreflightStatus.NOT_RUN)

    def test_not_run_when_url_missing(self) -> None:
        result = modal_preflight(
            modal_token_id='ak-test1234',
            modal_token_secret='as-test1234',
            modal_worker_url=None,
        )
        self.assertEqual(result.status, PreflightStatus.NOT_RUN)


class RunAllPreflightsTests(unittest.TestCase):
    @patch('backend.common.poc_preflight.requests.get')
    @patch('backend.common.poc_preflight.subprocess.run')
    @patch('backend.common.poc_preflight.shutil.disk_usage')
    @patch('backend.common.poc_preflight.shutil.which')
    def test_all_pass_returns_pass_overall(
        self, mock_which: MagicMock, mock_du: MagicMock, mock_run: MagicMock, mock_get: MagicMock,
    ) -> None:
        mock_which.return_value = '/usr/local/bin/docker'
        mock_du.return_value = DiskUsage(total=100*1024**3, used=50*1024**3, free=50*1024**3)
        mock_run.return_value = MagicMock(returncode=0, stdout='28.1.1', stderr='')
        mock_get.return_value = FakeResponse(200, text='[]')

        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://eyyellmffzzujyssaayb.supabase.co',
            'SUPABASE_SERVICE_ROLE_KEY': 'sbp_test_key_1234567890',
            'MODAL_TOKEN_ID': 'ak-test1234',
            'MODAL_TOKEN_SECRET': 'as-test1234',
            'MODAL_WORKER_URL': 'https://modal.example.com',
        }):
            report = run_all_preflights(
                expected_supabase_project_ref='eyyellmffzzujyssaayb',
            )

        self.assertEqual(report.overall_status, PreflightStatus.PASS)
        self.assertTrue(report.all_pass)

    def test_missing_credentials_returns_not_run_overall(self) -> None:
        with patch.dict('os.environ', {}, clear=True):
            report = run_all_preflights(check_docker=False, check_modal=False)
        # With no credentials, Supabase is not_run, disk should pass or block
        # depending on actual disk, but overall should not be PASS
        self.assertNotEqual(report.overall_status, PreflightStatus.PASS)


if __name__ == '__main__':
    unittest.main()
