from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.trigger_and_poll_sar_training import load_training_request, main


class TriggerAndPollSarTrainingTests(unittest.TestCase):
    def test_load_training_request_requires_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / 'request.json'
            request_path.write_text(json.dumps({'model_family': 'swinunet_tiny_diff'}), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'requires training_manifest_path'):
                load_training_request(request_path)

    def test_main_writes_blocked_artifact_when_remote_submission_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
                'source_key': 'avalcd_zenodo_v1',
                'candidate_model_version': 'avalcd-shadow-unit',
                'license_review_id': 'license-review-unit',
                'validation_scene_ids': ['livigno_20250318', 'nuuk_20210411'],
            }), encoding='utf-8')

            with patch(
                'backend.scripts.trigger_and_poll_sar_training.trigger_and_poll_sar_training',
                side_effect=RuntimeError('workspace billing cycle spend limit reached'),
            ):
                exit_code = main([
                    '--env-file', str(root / '.env'),
                    '--request', str(request_path),
                    '--output', str(output_path),
                ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload['status'], 'blocked_remote_training')
            self.assertEqual(payload['version'], 'european_sar_prediction_artifact_v1')
            self.assertEqual(payload['source_key'], 'avalcd_zenodo_v1')
            self.assertEqual(payload['model_version'], 'avalcd-shadow-unit')
            self.assertEqual(payload['license_review_id'], 'license-review-unit')
            self.assertEqual(payload['evaluated_scene_ids'], ['livigno_20250318', 'nuuk_20210411'])
            self.assertEqual(payload['request_type'], 'train_sar_unet')
            self.assertEqual(payload['request_path'], str(request_path))
            self.assertIn('spend limit', payload['error'])


if __name__ == '__main__':
    unittest.main()
