from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.scripts.inspect_modal_sar_training_run import inspect_modal_sar_training_run, main


class InspectModalSarTrainingRunTests(unittest.TestCase):
    def test_empty_partial_directory_reports_no_partial_artifacts(self) -> None:
        calls: list[list[str]] = []

        def _fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
            calls.append(command)
            if command[1:3] == ['volume', 'ls']:
                return SimpleNamespace(returncode=0, stdout='[]', stderr='')
            if command[1:3] == ['container', 'list']:
                return SimpleNamespace(returncode=0, stdout='Active Containers in environment: None\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='checkpoint load started\n', stderr='')

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            'backend.scripts.inspect_modal_sar_training_run.subprocess.run',
            side_effect=_fake_run,
        ):
            root = Path(tmpdir)
            local_result_path = root / 'train_sar_unet_result.json'
            local_result_path.write_text(json.dumps({
                'status': 'blocked_remote_training_stopped_for_cost_guard',
                'candidate_model_version': 'avalcd-v5',
                'artifact_dir': '/artifacts/20260518T022355Z',
            }), encoding='utf-8')
            report = inspect_modal_sar_training_run(
                modal_profile='sanjabh1103_limit30',
                artifact_dir='/artifacts/20260518T022355Z',
                local_result_path=local_result_path,
                modal_bin='modal',
            )

        self.assertFalse(report['volume_listing']['partial_artifacts'])
        self.assertEqual(report['volume_listing']['entry_count'], 0)
        self.assertFalse(report['containers']['active_container_hint'])
        volume_call = next(call for call in calls if call[1:3] == ['volume', 'ls'])
        self.assertIn('/20260518T022355Z', volume_call)

    def test_main_writes_inspection_packet(self) -> None:
        def _fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
            if command[1:3] == ['volume', 'ls']:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps([{'Filename': 'train_sar_unet_status.json'}]),
                    stderr='',
                )
            if command[1:3] == ['container', 'list']:
                return SimpleNamespace(returncode=0, stdout='Active Containers in environment: None\n', stderr='')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            'backend.scripts.inspect_modal_sar_training_run.subprocess.run',
            side_effect=_fake_run,
        ):
            output_path = Path(tmpdir) / 'inspection.json'
            exit_code = main([
                '--modal-profile', 'sanjabh1103_limit30',
                '--artifact-dir', '/artifacts/20260518T022355Z',
                '--output', str(output_path),
            ])
            payload = json.loads(output_path.read_text(encoding='utf-8'))

        self.assertEqual(exit_code, 0)
        self.assertFalse(payload['volume_listing']['partial_artifacts'])
        self.assertTrue(payload['volume_listing']['observability_artifacts'])
        self.assertFalse(payload['mutated_volume'])
        self.assertFalse(payload['downloaded_model_files'])


if __name__ == '__main__':
    unittest.main()
