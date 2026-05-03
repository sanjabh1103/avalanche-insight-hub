from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from backend.scripts.adapt_coldstart_swin_checkpoint import (
    adapt_coldstart_swin_checkpoint,
    adapt_patch_embed_weight,
    build_coldstart_state_dict,
)


class AdaptColdstartSwinCheckpointTests(unittest.TestCase):
    def test_adapt_patch_embed_weight_reduces_rgb_stem_to_two_channel_sar_stem(self) -> None:
        source = torch.arange(96 * 3 * 4 * 4, dtype=torch.float32).reshape(96, 3, 4, 4)

        adapted = adapt_patch_embed_weight(source)

        self.assertEqual(tuple(adapted.shape), (96, 2, 2, 2))
        self.assertTrue(torch.allclose(adapted[:, 0], adapted[:, 1]))

    def test_build_coldstart_state_dict_rewrites_matching_encoder_keys_only(self) -> None:
        source_state_dict = {
            'patch_embed.proj.weight': torch.ones((96, 3, 4, 4), dtype=torch.float32),
            'layers_0.blocks.0.attn.qkv.weight': torch.ones((288, 96), dtype=torch.float32),
            'head.weight': torch.ones((1000, 768), dtype=torch.float32),
            'layers_3.blocks.0.attn.qkv.weight': torch.ones((2304, 768), dtype=torch.float32),
        }
        target_state_dict = {
            'sar_encoder.model.patch_embed.proj.weight': torch.zeros((96, 2, 2, 2), dtype=torch.float32),
            'sar_encoder.model.layers_0.blocks.0.attn.qkv.weight': torch.zeros((288, 96), dtype=torch.float32),
            'fusion_stages.0.fusion.0.weight': torch.zeros((96, 96, 3, 3), dtype=torch.float32),
        }

        result = build_coldstart_state_dict(
            source_state_dict=source_state_dict,
            target_state_dict=target_state_dict,
        )

        self.assertEqual(
            sorted(result['state_dict']),
            sorted([
                'sar_encoder.model.patch_embed.proj.weight',
                'sar_encoder.model.layers_0.blocks.0.attn.qkv.weight',
            ]),
        )
        self.assertIn('head.weight', result['dropped_source_keys'])
        self.assertIn('layers_3.blocks.0.attn.qkv.weight', result['dropped_source_keys'])
        self.assertNotIn('sar_encoder.model.patch_embed.proj.weight', result['missing_target_keys'])

    @patch('backend.scripts.adapt_coldstart_swin_checkpoint.build_unet_model')
    @patch('backend.scripts.adapt_coldstart_swin_checkpoint.ChangeDetectionSwinUNet')
    @patch('backend.scripts.adapt_coldstart_swin_checkpoint.timm.create_model')
    def test_adapt_coldstart_checkpoint_updates_env_and_writes_checkpoint(
        self,
        timm_create_model_mock,
        target_model_mock,
        build_unet_model_mock,
    ) -> None:
        class _FakeSourceModel:
            def state_dict(self):
                return {
                    'patch_embed.proj.weight': torch.ones((96, 3, 4, 4), dtype=torch.float32),
                    'patch_embed.proj.bias': torch.ones((96,), dtype=torch.float32),
                    'layers_0.blocks.0.attn.qkv.weight': torch.ones((288, 96), dtype=torch.float32),
                }

        class _FakeTargetModel:
            def state_dict(self):
                return {
                    'sar_encoder.model.patch_embed.proj.weight': torch.zeros((96, 2, 2, 2), dtype=torch.float32),
                    'sar_encoder.model.patch_embed.proj.bias': torch.zeros((96,), dtype=torch.float32),
                    'sar_encoder.model.layers_0.blocks.0.attn.qkv.weight': torch.zeros((288, 96), dtype=torch.float32),
                    'fusion_stages.0.fusion.0.weight': torch.zeros((96, 96, 3, 3), dtype=torch.float32),
                }

        timm_create_model_mock.return_value = _FakeSourceModel()
        target_model_mock.return_value = _FakeTargetModel()
        build_unet_model_mock.return_value = SimpleNamespace(
            model_family='swinunet_tiny_diff',
            checkpoint_key_mismatch={
                'has_mismatch': True,
                'missing_count': 1,
                'unexpected_count': 0,
                'matched_provided_key_count': 3,
                'provided_match_ratio': 1.0,
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = root / '.env'
            env_path.write_text('SAR_UNET_PROMOTED=false\n', encoding='utf-8')
            output_path = root / 'weights' / 'coldstart.pt'

            result = adapt_coldstart_swin_checkpoint(
                output=output_path,
                env_file=env_path,
                env_model_path='/artifacts/models/swin_transformer_v2_tiny_coldstart_v1.pt',
            )

            self.assertEqual(result['status'], 'ok')
            self.assertTrue(output_path.exists())
            payload = torch.load(output_path, map_location='cpu')
            self.assertIn('state_dict', payload)
            self.assertIn('sar_encoder.model.patch_embed.proj.weight', payload['state_dict'])
            env_text = env_path.read_text(encoding='utf-8')
            self.assertIn('SAR_UNET_MODEL_PATH="/artifacts/models/swin_transformer_v2_tiny_coldstart_v1.pt"', env_text)
            self.assertIn('SAR_UNET_MODEL_FAMILY="swinunet_tiny_diff"', env_text)
            self.assertIn('SAR_UNET_MODEL_VERSION="swin_transformer_v2_tiny_coldstart_v1"', env_text)


if __name__ == '__main__':
    unittest.main()
