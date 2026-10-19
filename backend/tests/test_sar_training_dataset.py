from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.common.avalcd_manifest import build_avalcd_scene_manifest, encode_patch_payload
from backend.common.sar_training_dataset import (
    load_sar_training_manifest,
    materialize_sar_training_dataset,
)


class SarTrainingDatasetTests(unittest.TestCase):
    def test_load_sar_training_manifest_rejects_heldout_leakage(self) -> None:
        manifest = {
            'version': 'sar_training_manifest_v1',
            'dataset_version': 'unit-test-v1',
            'scenes': [{
                'source_dataset': 'snowslide',
                'event_id': 'evt-heldout',
                'scene_id': 'scene-heldout',
                'region_key': 'livigno',
                'split': 'train',
                'stack_ref': '/tmp/stack.npz',
                'truth_mask_ref': '/tmp/mask.npz',
                'reference_set_key': 'snowslide-heldout-v1',
            }],
        }

        with self.assertRaisesRegex(ValueError, 'must use split=authoritative_test'):
            load_sar_training_manifest(manifest)

    def test_materialize_sar_training_dataset_builds_manifest_backed_patches_and_excludes_authoritative_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            train_scene_root = root / 'train_scene'
            train_scene_root.mkdir(parents=True, exist_ok=True)
            heldout_scene_root = root / 'heldout_scene'
            heldout_scene_root.mkdir(parents=True, exist_ok=True)

            train_stack = np.stack([
                np.ones((4, 4), dtype=np.float32) * 1.0,
                np.ones((4, 4), dtype=np.float32) * 2.0,
                np.ones((4, 4), dtype=np.float32) * 3.0,
                np.ones((4, 4), dtype=np.float32) * 4.0,
            ], axis=0)
            truth_mask = np.zeros((4, 4), dtype=np.float32)
            truth_mask[1:3, 1:3] = 1.0

            scene_manifest, patch_entries = build_avalcd_scene_manifest(
                train_stack,
                bbox=(-106.6, 39.4, -106.4, 39.6),
                patch_size=4,
                stride=4,
            )
            manifest_path = train_scene_root / 'stack_manifest.json'
            manifest_path.write_text(json.dumps(scene_manifest, indent=2, sort_keys=True), encoding='utf-8')
            for patch in patch_entries:
                patch_path = train_scene_root / str(patch['filename'])
                patch_path.parent.mkdir(parents=True, exist_ok=True)
                patch_path.write_bytes(encode_patch_payload(patch['stack']))

            truth_mask_path = train_scene_root / 'truth_mask.npz'
            np.savez_compressed(truth_mask_path, mask=truth_mask)

            heldout_stack_path = heldout_scene_root / 'stack.npz'
            heldout_truth_path = heldout_scene_root / 'truth_mask.npz'
            np.savez_compressed(heldout_stack_path, stack=train_stack)
            np.savez_compressed(heldout_truth_path, mask=truth_mask)

            dataset_manifest = {
                'version': 'sar_training_manifest_v1',
                'dataset_version': 'sar-unit-v1',
                'scenes': [
                    {
                        'source_dataset': 'avalcd',
                        'event_id': 'evt-train-1',
                        'scene_id': 'scene-train-1',
                        'region_key': 'livigno',
                        'split': 'train',
                        'stack_ref': str(manifest_path),
                        'truth_mask_ref': str(truth_mask_path),
                    },
                    {
                        'source_dataset': 'snowslide',
                        'event_id': 'evt-heldout-1',
                        'scene_id': 'scene-heldout-1',
                        'region_key': 'livigno',
                        'split': 'authoritative_test',
                        'stack_ref': str(heldout_stack_path),
                        'truth_mask_ref': str(heldout_truth_path),
                        'reference_set_key': 'snowslide-heldout-v1',
                        'authoritative': True,
                    },
                ],
            }

            audit = materialize_sar_training_dataset(
                manifest_source=dataset_manifest,
                output_root=root / 'materialized',
                patch_size=4,
                stride=4,
            )

            self.assertEqual(audit['status'], 'ok')
            self.assertEqual(audit['split_scene_counts']['train'], 1)
            self.assertEqual(audit['split_scene_counts']['authoritative_test'], 1)
            self.assertEqual(audit['split_patch_counts']['train'], 1)
            self.assertEqual(audit['split_patch_counts']['authoritative_test'], 0)
            self.assertEqual(audit['authoritative_test_scene_ids'], ['scene-heldout-1'])
            self.assertEqual(audit['train_events'], ['evt-train-1'])

            patch_root = Path(audit['patch_root'])
            patch_dir = patch_root / 'train' / 'evt_train_1' / 'scene_train_1__r000000_c000000'
            self.assertTrue((patch_dir / 'pre.tif').exists())
            self.assertTrue((patch_dir / 'post.tif').exists())
            self.assertTrue((patch_dir / 'mask.tif').exists())

            patch_index = json.loads((root / 'materialized' / 'patch_index.json').read_text(encoding='utf-8'))
            self.assertEqual(len(patch_index), 1)
            self.assertEqual(patch_index[0]['scene_id'], 'scene-train-1')


if __name__ == '__main__':
    unittest.main()
