from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scripts.materialize_authoritative_prediction_masks import materialize_authoritative_prediction_masks


class MaterializeAuthoritativePredictionMasksTests(unittest.TestCase):
    @patch('backend.scripts.materialize_authoritative_prediction_masks.run_segmentation')
    @patch('backend.scripts.materialize_authoritative_prediction_masks.reference_item_to_scene')
    @patch('backend.scripts.materialize_authoritative_prediction_masks.load_reference_bundle')
    @patch('backend.scripts.materialize_authoritative_prediction_masks._apply_rollout_env')
    def test_materialize_authoritative_prediction_masks_iterates_scenes_and_collects_uploads(
        self,
        _apply_env_mock,
        load_reference_bundle_mock,
        reference_item_to_scene_mock,
        run_segmentation_mock,
    ) -> None:
        load_reference_bundle_mock.return_value = ({'id': 'set-1'}, [{'id': 'a'}, {'id': 'b'}])
        reference_item_to_scene_mock.side_effect = [
            {'scene_id': 'scene-a'},
            {'scene_id': 'scene-b'},
        ]
        run_segmentation_mock.side_effect = [
            {'status': 'ok', 'detections_count': 1, 'mask_asset_refs': ['sar-masks/a.tif']},
            {'status': 'ok', 'detections_count': 0, 'mask_asset_refs': ['sar-masks/b.tif']},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / 'coldstart.pt'
            model_path.write_bytes(b'pt')
            result = materialize_authoritative_prediction_masks(
                env_file=Path('.env'),
                reference_set_key='snowslide-heldout-v1',
                prediction_model_version='swin_transformer_v2_tiny_coldstart_v1',
                local_model_path=model_path,
                model_family='swinunet_tiny_diff',
                artifact_root=Path(tmpdir) / 'artifacts',
                device='mps',
                threshold=0.5,
                hazard_type='avalanche',
            )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 2)
        self.assertEqual(result['uploaded_prediction_masks'], 2)
        self.assertEqual(result['mask_asset_refs'], ['sar-masks/a.tif', 'sar-masks/b.tif'])
        self.assertEqual(run_segmentation_mock.call_count, 2)


if __name__ == '__main__':
    unittest.main()
