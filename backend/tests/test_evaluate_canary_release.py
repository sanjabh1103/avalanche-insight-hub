from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from backend.scripts.evaluate_canary_release import (
    build_canary_manifest,
    build_zero_prediction_geotiff,
    post_evaluate_release,
    seed_zero_prediction_masks,
)


class EvaluateCanaryReleaseTests(unittest.TestCase):
    @staticmethod
    def _truth_tiff_bytes() -> bytes:
        profile = {
            'driver': 'GTiff',
            'height': 3,
            'width': 4,
            'count': 1,
            'dtype': 'uint8',
            'crs': 'EPSG:2056',
            'transform': from_bounds(2774056.7739, 1175209.6314, 2791933.9989, 1194403.4519, 4, 3),
        }
        with MemoryFile() as memory_file:
            with memory_file.open(**profile) as dataset:
                dataset.write(np.array([
                    [1, 0, 1, 0],
                    [0, 1, 0, 1],
                    [1, 1, 0, 0],
                ], dtype=np.uint8), 1)
            return memory_file.read()

    @patch('backend.scripts.evaluate_canary_release.build_release_manifest_from_reference_set')
    @patch('backend.scripts.evaluate_canary_release.load_reference_bundle')
    def test_build_canary_manifest_rejects_authoritative_reference_sets(
        self,
        load_reference_bundle_mock,
        build_manifest_mock,
    ) -> None:
        load_reference_bundle_mock.return_value = ({'set_key': 'snowslide-heldout-v1', 'authoritative': True, 'status': 'active'}, [])

        with self.assertRaisesRegex(ValueError, 'authoritative'):
            build_canary_manifest(
                reference_set_key='snowslide-heldout-v1',
                prediction_model_version='sar_unet_resnet34_shadow_v1',
            )

        build_manifest_mock.assert_not_called()

    def test_build_zero_prediction_geotiff_preserves_truth_geometry(self) -> None:
        rendered = build_zero_prediction_geotiff(self._truth_tiff_bytes())

        with MemoryFile(self._truth_tiff_bytes()) as truth_file, MemoryFile(rendered) as rendered_file:
            with truth_file.open() as truth_ds, rendered_file.open() as rendered_ds:
                self.assertEqual(rendered_ds.crs, truth_ds.crs)
                self.assertEqual(rendered_ds.transform, truth_ds.transform)
                self.assertEqual(rendered_ds.width, truth_ds.width)
                self.assertEqual(rendered_ds.height, truth_ds.height)
                np.testing.assert_array_equal(
                    rendered_ds.read(1),
                    np.zeros((truth_ds.height, truth_ds.width), dtype=np.uint8),
                )

    @patch('backend.scripts.evaluate_canary_release.build_release_manifest_from_reference_set')
    @patch('backend.scripts.evaluate_canary_release.load_reference_bundle')
    def test_build_canary_manifest_rejects_active_reference_sets(
        self,
        load_reference_bundle_mock,
        build_manifest_mock,
    ) -> None:
        load_reference_bundle_mock.return_value = ({'set_key': 'canary-test-v1', 'authoritative': False, 'status': 'active'}, [])

        with self.assertRaisesRegex(ValueError, 'non-active'):
            build_canary_manifest(
                reference_set_key='canary-test-v1',
                prediction_model_version='sar_unet_resnet34_shadow_v1',
            )

        build_manifest_mock.assert_not_called()

    @patch('backend.scripts.evaluate_canary_release.storage_upload_bytes')
    @patch('backend.scripts.evaluate_canary_release.storage_download_bytes')
    def test_seed_zero_prediction_masks_uploads_to_derived_prediction_refs(
        self,
        storage_download_bytes_mock,
        storage_upload_bytes_mock,
    ) -> None:
        storage_download_bytes_mock.return_value = self._truth_tiff_bytes()
        storage_upload_bytes_mock.side_effect = lambda **kwargs: f"{kwargs['bucket']}/{kwargs['object_path']}"
        manifest = {
            'scenes': [{
                'scene_id': 'davos_2018',
                'region_key': 'davos',
                'truth_mask': 'sar-masks/heldout/snowslide/2026-04-27/validation/davos/davos_2018/truth_mask.tif',
                'prediction_mask': 'sar-masks/heldout/snowslide/2026-04-27/validation/davos/davos_2018/predictions/sar_unet_resnet34_shadow_v1/prediction_mask.tif',
            }],
        }

        uploaded_refs = seed_zero_prediction_masks(manifest)

        self.assertEqual(
            uploaded_refs,
            ['sar-masks/heldout/snowslide/2026-04-27/validation/davos/davos_2018/predictions/sar_unet_resnet34_shadow_v1/prediction_mask.tif'],
        )
        upload_kwargs = storage_upload_bytes_mock.call_args.kwargs
        self.assertEqual(upload_kwargs['bucket'], 'sar-masks')
        self.assertEqual(
            upload_kwargs['object_path'],
            'heldout/snowslide/2026-04-27/validation/davos/davos_2018/predictions/sar_unet_resnet34_shadow_v1/prediction_mask.tif',
        )
        self.assertEqual(upload_kwargs['content_type'], 'image/tiff')
        self.assertTrue(upload_kwargs['upsert'])

    @patch('backend.scripts.evaluate_canary_release.requests.post')
    def test_post_evaluate_release_sends_manual_scenes_manifest(self, requests_post_mock) -> None:
        response = Mock()
        response.ok = True
        response.json.return_value = {'status': 'ok', 'beats_baseline': False}
        requests_post_mock.return_value = response
        manifest = {
            'reference_set_key': 'canary-test-v1',
            'prediction_model_version': 'sar_unet_resnet34_shadow_v1',
            'scenes': [{
                'scene_id': 'davos_2018',
                'region_key': 'davos',
                'prediction_mask': 'sar-masks/.../prediction_mask.tif',
                'truth_mask': 'sar-masks/.../truth_mask.tif',
                'baseline_mask': 'sar-masks/.../baseline_mask.tif',
            }],
        }

        result = post_evaluate_release(
            worker_url='https://worker.modal.run',
            worker_token='secret-token',
            manifest=manifest,
        )

        self.assertEqual(result['status'], 'ok')
        post_kwargs = requests_post_mock.call_args.kwargs
        self.assertEqual(post_kwargs['headers']['Authorization'], 'Bearer secret-token')
        self.assertIn('scenes', post_kwargs['json'])
        self.assertEqual(post_kwargs['json']['request_type'], 'canary_evaluate_release')
        self.assertEqual(post_kwargs['json']['reference_set_key'], 'canary-test-v1')


if __name__ == '__main__':
    unittest.main()
