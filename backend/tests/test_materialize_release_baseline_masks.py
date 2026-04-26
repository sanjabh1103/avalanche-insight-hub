from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from backend.scripts.materialize_release_baseline_masks import materialize_baseline_masks


class MaterializeReleaseBaselineMasksTests(unittest.TestCase):
    @staticmethod
    def _reference_bundle() -> tuple[dict[str, object], list[dict[str, object]]]:
        return (
            {
                'id': 'set-1',
                'set_key': 'snowslide-v1',
                'source_version': '2026-04-25',
                'split_name': 'validation',
                'status': 'draft',
            },
            [{
                'id': 'item-1',
                'reference_set_id': 'set-1',
                'external_scene_id': 'S1A_001',
                'region_key': 'colorado_rockies',
                'bbox': [-106.6, 39.4, -106.4, 39.6],
                'stack_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz',
                'truth_mask_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif',
                'metadata': {'split': 'validation'},
            }],
        )

    @patch('backend.scripts.materialize_release_baseline_masks.activate_reference_set', return_value={'status': 'active'})
    @patch('backend.scripts.materialize_release_baseline_masks.rest_upsert')
    @patch('backend.scripts.materialize_release_baseline_masks.storage_upload_bytes')
    @patch('backend.scripts.materialize_release_baseline_masks.encode_mask_geotiff', return_value=b'tiff-bytes')
    @patch('backend.scripts.materialize_release_baseline_masks.load_scene_stack', return_value=np.array([
        [[-20.0, -20.0], [-10.0, -10.0]],
        [[-24.0, -24.0], [-10.0, -10.0]],
    ], dtype=np.float32))
    @patch('backend.scripts.materialize_release_baseline_masks.load_reference_bundle')
    def test_materialize_baseline_masks_uploads_and_activates_reference_set(
        self,
        load_reference_bundle_mock,
        load_scene_stack_mock,
        encode_mask_geotiff_mock,
        storage_upload_bytes_mock,
        rest_upsert_mock,
        activate_reference_set_mock,
    ) -> None:
        load_reference_bundle_mock.return_value = self._reference_bundle()

        result = materialize_baseline_masks(reference_set_key='snowslide-v1')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['baseline_rows_materialized'], 1)
        storage_upload_bytes_mock.assert_called_once()
        rest_upsert_mock.assert_called_once()
        activate_reference_set_mock.assert_called_once_with('snowslide-v1')

    @patch('backend.scripts.materialize_release_baseline_masks.activate_reference_set')
    @patch('backend.scripts.materialize_release_baseline_masks.rest_upsert')
    @patch('backend.scripts.materialize_release_baseline_masks.storage_upload_bytes')
    @patch('backend.scripts.materialize_release_baseline_masks.encode_mask_geotiff', return_value=b'tiff-bytes')
    @patch('backend.scripts.materialize_release_baseline_masks.load_scene_stack', return_value=np.array([
        [[-20.0, -20.0], [-10.0, -10.0]],
        [[-24.0, -24.0], [-10.0, -10.0]],
    ], dtype=np.float32))
    @patch('backend.scripts.materialize_release_baseline_masks.load_reference_bundle')
    def test_materialize_baseline_masks_no_activate_leaves_set_in_draft(
        self,
        load_reference_bundle_mock,
        _load_scene_stack_mock,
        _encode_mask_geotiff_mock,
        storage_upload_bytes_mock,
        rest_upsert_mock,
        activate_reference_set_mock,
    ) -> None:
        load_reference_bundle_mock.return_value = self._reference_bundle()

        result = materialize_baseline_masks(reference_set_key='snowslide-v1', activate=False)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['reference_set_status'], 'draft')
        storage_upload_bytes_mock.assert_called_once()
        rest_upsert_mock.assert_called_once()
        activate_reference_set_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
