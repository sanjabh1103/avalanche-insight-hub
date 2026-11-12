"""Tests for POC artifact round-trip module."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.common.artifact_round_trip import (
    ArtifactProvider,
    RoundTripStatus,
    build_bundle_manifest,
    download_supabase_bundle,
    verify_bundle,
    upload_supabase_bundle,
    supabase_round_trip,
    local_round_trip,
    select_provider,
    execute_round_trip,
)
from backend.common.poc_preflight import PreflightResult, PreflightStatus
from backend.common.supabase_io import SupabaseError


def _make_source_dir(tmp: Path) -> Path:
    """Create a source directory with test artifact files."""
    src = tmp / 'source'
    src.mkdir()
    (src / 'native.pro').write_text('profile data line 1\nline 2\n', encoding='utf-8')
    (src / 'native.sno').write_text('snow profile\n', encoding='utf-8')
    (src / 'native.haz').write_text('hazard assessment\n', encoding='utf-8')
    (src / 'native.smet').write_text('meteo forcing\n', encoding='utf-8')
    (src / 'native.log').write_text('execution log\n', encoding='utf-8')
    return src


class BuildBundleManifestTests(unittest.TestCase):
    def test_manifest_includes_all_files_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
        self.assertEqual(manifest['file_count'], 5)
        for entry in manifest['files']:
            self.assertIn('path', entry)
            self.assertIn('sha256', entry)
            self.assertEqual(len(entry['sha256']), 64)
            self.assertGreater(entry['size_bytes'], 0)

    def test_manifest_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_bundle_manifest(Path(tmp))
        self.assertEqual(manifest['file_count'], 0)


class VerifyBundleTests(unittest.TestCase):
    def test_verify_passes_on_identical_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
            verified, mismatches = verify_bundle(src, manifest)
        self.assertTrue(verified)
        self.assertEqual(mismatches, [])

    def test_verify_detects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
            # Remove a file
            (src / 'native.pro').unlink()
            verified, mismatches = verify_bundle(src, manifest)
        self.assertFalse(verified)
        self.assertTrue(any('missing' in m for m in mismatches))

    def test_verify_detects_content_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
            # Corrupt a file with same-length content to trigger sha256 mismatch
            original = (src / 'native.pro').read_text()
            (src / 'native.pro').write_text('X' * len(original), encoding='utf-8')
            verified, mismatches = verify_bundle(src, manifest)
        self.assertFalse(verified)
        self.assertTrue(len(mismatches) > 0)

    def test_verify_rejects_path_traversal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'download'
            root.mkdir()
            manifest = {
                'schema_version': 'poc_artifact_bundle_v1',
                'file_count': 1,
                'files': [{'path': '../escape.txt', 'size_bytes': 1, 'sha256': 'a' * 64}],
            }
            verified, mismatches = verify_bundle(root, manifest)
        self.assertFalse(verified)
        self.assertTrue(any('manifest invalid' in item for item in mismatches))

    def test_verify_rejects_unlisted_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _make_source_dir(root)
            manifest = build_bundle_manifest(source)
            (source / 'unexpected.txt').write_text('extra', encoding='utf-8')
            verified, mismatches = verify_bundle(source, manifest)
        self.assertFalse(verified)
        self.assertTrue(any('unexpected.txt' in item for item in mismatches))


class LocalRoundTripTests(unittest.TestCase):
    def test_local_round_trip_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            result = local_round_trip(src)
        self.assertEqual(result.status, RoundTripStatus.SUCCESS)
        self.assertTrue(result.verified)
        self.assertEqual(len(result.uploaded_files), 5)

    def test_local_round_trip_empty_dir_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = local_round_trip(Path(tmp))
        self.assertEqual(result.status, RoundTripStatus.BLOCKED)
        self.assertEqual(result.error_class, 'EmptySource')


class SupabaseRoundTripTests(unittest.TestCase):
    def test_not_run_when_credentials_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            result = supabase_round_trip(
                src,
                supabase_url=None,
                service_role_key=None,
            )
        self.assertEqual(result.status, RoundTripStatus.NOT_RUN)

    @patch('backend.common.artifact_round_trip.storage_upload_bytes')
    @patch('backend.common.artifact_round_trip.storage_download_bytes')
    def test_supabase_round_trip_succeeds(
        self, mock_download: MagicMock, mock_upload: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
            manifest['object_prefix'] = 'test-run'

            # Upload always succeeds
            mock_upload.return_value = 'poc-artifacts/test'

            # Download returns the manifest first, then each file's bytes
            manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
            file_bytes = [manifest_bytes]
            for entry in manifest['files']:
                file_bytes.append((src / entry['path']).read_bytes())
            mock_download.side_effect = file_bytes

            result = supabase_round_trip(
                src,
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_test_key',
                bucket='poc-artifacts',
                object_prefix='test-run',
            )

        self.assertEqual(result.status, RoundTripStatus.SUCCESS)
        self.assertTrue(result.verified)
        self.assertEqual(len(result.uploaded_files), 6)  # 5 files + manifest

    @patch('backend.common.artifact_round_trip.storage_upload_bytes')
    def test_supabase_round_trip_blocked_on_upload_failure(
        self, mock_upload: MagicMock,
    ) -> None:
        mock_upload.side_effect = SupabaseError(401, 'Unauthorized')

        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            result = supabase_round_trip(
                src,
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_bad_key',
            )

        self.assertEqual(result.status, RoundTripStatus.BLOCKED)
        self.assertEqual(result.error_class, 'SupabaseError')

    @patch('backend.common.artifact_round_trip.storage_upload_bytes')
    def test_recursive_upload_includes_transport_manifest(
        self, mock_upload: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            (src / 'input-manifests').mkdir()
            (src / 'input-manifests' / 'decision.json').write_text('{}', encoding='utf-8')
            result = upload_supabase_bundle(
                src,
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_test_key',
                object_prefix='run-123',
            )
        self.assertEqual(result.status, RoundTripStatus.SUCCESS)
        self.assertFalse(result.verified)
        uploaded_paths = [call.kwargs['object_path'] for call in mock_upload.call_args_list]
        self.assertIn('run-123/_bundle_manifest.json', uploaded_paths)
        self.assertIn('run-123/input-manifests/decision.json', uploaded_paths)

    @patch('backend.common.artifact_round_trip.storage_download_bytes')
    def test_recursive_download_verifies_clean_bundle(
        self, mock_download: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
            manifest['object_prefix'] = 'run-123'
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode('utf-8')
            mock_download.side_effect = [
                manifest_bytes,
                *[(src / entry['path']).read_bytes() for entry in manifest['files']],
            ]
            result = download_supabase_bundle(
                Path(tmp) / 'downloaded',
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_test_key',
                object_prefix='run-123',
            )
        self.assertEqual(result.status, RoundTripStatus.SUCCESS)
        self.assertTrue(result.verified)
        self.assertEqual(len(result.downloaded_files), 6)

    @patch('backend.common.artifact_round_trip.storage_download_bytes')
    def test_download_rejects_unsafe_manifest_path(
        self, mock_download: MagicMock,
    ) -> None:
        unsafe_manifest = {
            'schema_version': 'poc_artifact_bundle_v1',
            'object_prefix': 'run-123',
            'file_count': 1,
            'files': [{'path': '../escape.txt', 'size_bytes': 1, 'sha256': 'a' * 64}],
        }
        mock_download.return_value = json.dumps(unsafe_manifest).encode('utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            result = download_supabase_bundle(
                Path(tmp) / 'downloaded',
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_test_key',
                object_prefix='run-123',
            )
        self.assertEqual(result.status, RoundTripStatus.BLOCKED)
        self.assertEqual(result.error_class, 'BundleValidationError')

    def test_download_rejects_nonempty_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'downloaded'
            output.mkdir()
            (output / 'stale.txt').write_text('stale', encoding='utf-8')
            result = download_supabase_bundle(
                output,
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_test_key',
                object_prefix='run-123',
            )
        self.assertEqual(result.status, RoundTripStatus.BLOCKED)
        self.assertEqual(result.error_class, 'UnsafeOutputDirectory')

    @patch('backend.common.artifact_round_trip.storage_upload_bytes')
    @patch('backend.common.artifact_round_trip.storage_download_bytes')
    def test_supabase_round_trip_blocked_on_download_failure(
        self, mock_download: MagicMock, mock_upload: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            manifest = build_bundle_manifest(src)
            manifest['object_prefix'] = 'poc-round-trip'

            mock_upload.return_value = 'poc-artifacts/test'
            manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
            mock_download.side_effect = [manifest_bytes, SupabaseError(404, 'Not found')]

            result = supabase_round_trip(
                src,
                supabase_url='https://test.supabase.co',
                service_role_key='sbp_test_key',
            )

        self.assertEqual(result.status, RoundTripStatus.BLOCKED)


class SelectProviderTests(unittest.TestCase):
    def test_prefers_supabase_when_preflight_passes(self) -> None:
        preflight = PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.PASS,
            detail='OK',
        )
        provider = select_provider(supabase_preflight_result=preflight)
        self.assertEqual(provider, ArtifactProvider.SUPABASE)

    def test_falls_back_to_local_when_supabase_blocked(self) -> None:
        preflight = PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail='401',
        )
        provider = select_provider(supabase_preflight_result=preflight)
        self.assertEqual(provider, ArtifactProvider.LOCAL_ONLY)

    def test_falls_back_to_local_when_no_preflight(self) -> None:
        provider = select_provider(supabase_preflight_result=None)
        self.assertEqual(provider, ArtifactProvider.LOCAL_ONLY)

    def test_respects_explicit_local_only_preference(self) -> None:
        preflight = PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.PASS,
            detail='OK',
        )
        provider = select_provider(
            prefer=ArtifactProvider.LOCAL_ONLY,
            supabase_preflight_result=preflight,
        )
        self.assertEqual(provider, ArtifactProvider.LOCAL_ONLY)

    def test_explicit_supabase_falls_back_when_preflight_blocked(self) -> None:
        preflight = PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail='401',
        )
        provider = select_provider(
            prefer=ArtifactProvider.SUPABASE,
            supabase_preflight_result=preflight,
        )
        self.assertEqual(provider, ArtifactProvider.LOCAL_ONLY)


class ExecuteRoundTripTests(unittest.TestCase):
    def test_local_round_trip_via_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            result = execute_round_trip(src, provider=ArtifactProvider.LOCAL_ONLY)
        self.assertEqual(result.status, RoundTripStatus.SUCCESS)
        self.assertEqual(result.provider, 'local_only')

    def test_falls_back_to_local_when_no_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source_dir(Path(tmp))
            result = execute_round_trip(src, supabase_preflight_result=None)
        self.assertEqual(result.status, RoundTripStatus.SUCCESS)
        self.assertEqual(result.provider, 'local_only')


if __name__ == '__main__':
    unittest.main()
