from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.sar_release_manifest import (
    ReleaseManifestOptions,
    build_release_manifest,
    build_release_manifest_from_reference_set,
)


class SarReleaseManifestTests(unittest.TestCase):
    def test_build_release_manifest_derives_default_refs_under_bucket_convention(self) -> None:
        manifest = build_release_manifest(
            [{
                'scene_id': 'S1A_001',
                'region_key': 'colorado_rockies',
                'truth_mask_format': '.npy',
            }],
            options=ReleaseManifestOptions(
                split='release-20260425',
                bucket='sar-masks',
                validate_refs=False,
            ),
        )

        scene = manifest['scenes'][0]
        self.assertEqual(
            scene['prediction_mask'],
            'sar-masks/heldout/release-20260425/colorado_rockies/S1A_001/prediction_mask.tif',
        )
        self.assertEqual(
            scene['baseline_mask'],
            'sar-masks/heldout/release-20260425/colorado_rockies/S1A_001/baseline_mask.tif',
        )
        self.assertEqual(
            scene['truth_mask'],
            'sar-masks/heldout/release-20260425/colorado_rockies/S1A_001/truth_mask.npy',
        )

    def test_build_release_manifest_rejects_missing_truth_source(self) -> None:
        with self.assertRaisesRegex(ValueError, 'truth_mask or truth_mask_format'):
            build_release_manifest(
                [{
                    'scene_id': 'S1A_001',
                    'region_key': 'colorado_rockies',
                }],
                options=ReleaseManifestOptions(
                    split='release-20260425',
                    validate_refs=False,
                ),
            )

    def test_build_release_manifest_rejects_cross_region_duplicate_scene_id(self) -> None:
        with self.assertRaisesRegex(ValueError, 'appears in multiple regions'):
            build_release_manifest(
                [
                    {
                        'scene_id': 'S1A_001',
                        'region_key': 'colorado_rockies',
                        'truth_mask_format': '.npy',
                    },
                    {
                        'scene_id': 'S1A_001',
                        'region_key': 'utah_wasatch',
                        'truth_mask_format': '.npy',
                    },
                ],
                options=ReleaseManifestOptions(
                    split='release-20260425',
                    validate_refs=False,
                ),
            )

    @patch('backend.sar_unet_worker._load_mask_array')
    def test_build_release_manifest_validates_refs_when_enabled(self, load_mask_array_mock) -> None:
        load_mask_array_mock.return_value = [[1.0]]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prediction = root / 'prediction.npy'
            truth = root / 'truth.npy'
            baseline = root / 'baseline.npy'
            prediction.write_bytes(b'ignored')
            truth.write_bytes(b'ignored')
            baseline.write_bytes(b'ignored')

            manifest = build_release_manifest(
                [{
                    'scene_id': 'S1A_001',
                    'region_key': 'colorado_rockies',
                    'prediction_mask': str(prediction),
                    'truth_mask': str(truth),
                    'baseline_mask': str(baseline),
                }],
                options=ReleaseManifestOptions(
                    split='release-20260425',
                    validate_refs=True,
                ),
            )

        self.assertEqual(manifest['scenes'][0]['prediction_mask'], str(prediction))
        self.assertEqual(load_mask_array_mock.call_count, 3)

    @patch('backend.sar_release_manifest.load_reference_bundle')
    def test_build_release_manifest_from_reference_set_derives_prediction_refs(self, load_reference_bundle_mock) -> None:
        load_reference_bundle_mock.return_value = (
            {
                'id': 'set-1',
                'set_key': 'snowslide-validation-v1',
                'source_name': 'snowslide_slf',
                'source_version': '2026-04-25',
                'split_name': 'validation+test',
                'authoritative': True,
            },
            [{
                'id': 'item-1',
                'external_scene_id': 'S1A_001',
                'region_key': 'colorado_rockies',
                'scene_time': '2026-02-10T00:00:00+00:00',
                'bbox': [-106.6, 39.4, -106.4, 39.6],
                'stack_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz',
                'truth_mask_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif',
                'baseline_mask_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/baseline_mask.tif',
                'metadata': {'split': 'validation'},
            }],
        )

        manifest = build_release_manifest_from_reference_set(
            reference_set_key='snowslide-validation-v1',
            options=ReleaseManifestOptions(
                baseline_margin=0.05,
                validate_refs=False,
                prediction_model_version='sar_unet_resnet34_shadow_v1',
                authoritative_only=True,
            ),
        )

        scene = manifest['scenes'][0]
        self.assertEqual(scene['truth_mask'], 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif')
        self.assertEqual(scene['baseline_mask'], 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/baseline_mask.tif')
        self.assertEqual(
            scene['prediction_mask'],
            'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/predictions/sar_unet_resnet34_shadow_v1/prediction_mask.tif',
        )
        self.assertTrue(manifest['authoritative'])

    @patch('backend.sar_release_manifest.load_reference_bundle')
    def test_build_release_manifest_from_reference_set_rejects_missing_baseline(self, load_reference_bundle_mock) -> None:
        load_reference_bundle_mock.return_value = (
            {
                'id': 'set-1',
                'set_key': 'snowslide-validation-v1',
                'source_name': 'snowslide_slf',
                'source_version': '2026-04-25',
                'split_name': 'validation',
                'authoritative': True,
            },
            [{
                'id': 'item-1',
                'external_scene_id': 'S1A_001',
                'region_key': 'colorado_rockies',
                'scene_time': '2026-02-10T00:00:00+00:00',
                'bbox': [-106.6, 39.4, -106.4, 39.6],
                'stack_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/stack.npz',
                'truth_mask_asset_ref': 'sar-masks/heldout/snowslide/2026-04-25/validation/colorado_rockies/S1A_001/truth_mask.tif',
                'baseline_mask_asset_ref': None,
                'metadata': {'split': 'validation'},
            }],
        )

        with self.assertRaisesRegex(ValueError, 'without baseline_mask'):
            build_release_manifest_from_reference_set(
                reference_set_key='snowslide-validation-v1',
                options=ReleaseManifestOptions(
                    baseline_margin=0.05,
                    validate_refs=False,
                    prediction_model_version='sar_unet_resnet34_shadow_v1',
                    authoritative_only=True,
                ),
            )


if __name__ == '__main__':
    unittest.main()
