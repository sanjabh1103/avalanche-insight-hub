from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.build_avalcd_shadow_split_manifest import (
    DEFAULT_TRAIN_SCENES,
    DEFAULT_VAL_SCENES,
    build_avalcd_shadow_split_manifest,
)


class BuildAvalcdShadowSplitManifestTests(unittest.TestCase):
    def test_builds_deterministic_train_val_manifest_and_remote_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            assembled_root = root / 'assembled'
            assembled_root.mkdir()
            source_manifest_path = root / 'source_sar_manifest.json'
            output_path = root / 'out' / 'sar_training_manifest.json'
            runtime_root = '/artifacts/european-shadow-sar/avalcd-shadow-v1/assembled'

            scenes = []
            for scene_id in sorted(DEFAULT_TRAIN_SCENES | DEFAULT_VAL_SCENES):
                scene_dir = assembled_root / 'validation' / scene_id / scene_id
                scene_dir.mkdir(parents=True)
                stack_ref = scene_dir / 'stack_manifest.json'
                truth_ref = scene_dir / 'truth_mask.tif'
                stack_ref.write_text('{}', encoding='utf-8')
                truth_ref.write_bytes(b'tiff-placeholder')
                scenes.append({
                    'source_dataset': 'avalcd_zenodo_v1',
                    'event_id': scene_id,
                    'scene_id': scene_id,
                    'region_key': scene_id.split('_', 1)[0],
                    'split': 'val',
                    'stack_ref': str(stack_ref),
                    'truth_mask_ref': str(truth_ref),
                })

            source_manifest_path.write_text(json.dumps({
                'version': 'sar_training_manifest_v1',
                'dataset_version': 'avalcd-source-unit',
                'scenes': scenes,
            }), encoding='utf-8')

            result = build_avalcd_shadow_split_manifest(
                source_manifest=source_manifest_path,
                local_assembled_root=assembled_root,
                runtime_assembled_root=runtime_root,
                snapshot_id='avalcd-shadow-train5-val2-unit',
                license_review_id='license-review-avalcd-unit',
                output=output_path,
            )

            manifest = json.loads(output_path.read_text(encoding='utf-8'))
            request = json.loads((output_path.parent / 'train_sar_unet_request.json').read_text(encoding='utf-8'))
            split_by_scene = {scene['scene_id']: scene['split'] for scene in manifest['scenes']}

            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['train_scene_count'], 5)
            self.assertEqual(result['val_scene_count'], 2)
            self.assertEqual(manifest['version'], 'sar_training_manifest_v1')
            self.assertEqual(manifest['license_review_id'], 'license-review-avalcd-unit')
            self.assertEqual(manifest['split_policy']['train_scene_ids'], sorted(DEFAULT_TRAIN_SCENES))
            self.assertEqual(manifest['split_policy']['val_scene_ids'], sorted(DEFAULT_VAL_SCENES))
            self.assertEqual({scene_id for scene_id, split in split_by_scene.items() if split == 'train'}, DEFAULT_TRAIN_SCENES)
            self.assertEqual({scene_id for scene_id, split in split_by_scene.items() if split == 'val'}, DEFAULT_VAL_SCENES)
            for scene in manifest['scenes']:
                self.assertTrue(scene['stack_ref'].startswith(runtime_root + '/'))
                self.assertTrue(scene['truth_mask_ref'].startswith(runtime_root + '/'))
                self.assertNotIn(str(assembled_root), scene['stack_ref'])
                self.assertEqual(scene['metadata']['shadow_split_policy'], 'avalcd_train5_val2_v1')
                self.assertEqual(scene['metadata']['license_review_id'], 'license-review-avalcd-unit')
            self.assertEqual(
                request['training_manifest_path'],
                '/artifacts/european-shadow-sar/avalcd-shadow-v1/manifests/avalcd_shadow_train5_val2.json',
            )
            self.assertEqual(request['materialized_dataset_root'], '/tmp/avalcd-shadow-train5-val2')
            self.assertEqual(request['precision_floor'], 0.6)
            self.assertEqual(request['train_scene_ids'], sorted(DEFAULT_TRAIN_SCENES))
            self.assertEqual(request['validation_scene_ids'], sorted(DEFAULT_VAL_SCENES))
            self.assertTrue(request['export_validation_prediction_artifact'])

    def test_rejects_missing_required_avalcd_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            assembled_root = root / 'assembled'
            assembled_root.mkdir()
            source_manifest_path = root / 'source_sar_manifest.json'
            output_path = root / 'out' / 'sar_training_manifest.json'
            scenes = [
                {
                    'source_dataset': 'avalcd_zenodo_v1',
                    'event_id': scene_id,
                    'scene_id': scene_id,
                    'region_key': 'unit',
                    'split': 'val',
                    'stack_ref': str(assembled_root / scene_id / 'stack_manifest.json'),
                    'truth_mask_ref': str(assembled_root / scene_id / 'truth_mask.tif'),
                }
                for scene_id in sorted(DEFAULT_TRAIN_SCENES)
            ]
            source_manifest_path.write_text(json.dumps({
                'version': 'sar_training_manifest_v1',
                'dataset_version': 'avalcd-source-unit',
                'scenes': scenes,
            }), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'missing required AvalCD scenes'):
                build_avalcd_shadow_split_manifest(
                    source_manifest=source_manifest_path,
                    local_assembled_root=assembled_root,
                    runtime_assembled_root='/artifacts/european-shadow-sar/avalcd-shadow-v1/assembled',
                    snapshot_id='avalcd-shadow-train5-val2-unit',
                    license_review_id='license-review-avalcd-unit',
                    output=output_path,
                )


if __name__ == '__main__':
    unittest.main()
