"""Tests for F9: SAM-SAR Foundation Model Pipeline."""
from __future__ import annotations

import unittest
import os
import numpy as np

# Ensure SAM is disabled for tests (testing scaffold + fallback)
os.environ['SAM_ENABLED'] = 'false'


class LoRAConfigTests(unittest.TestCase):
    """Tests for LoRA configuration."""

    def test_default_config(self) -> None:
        from backend.common.sam_lora_adapter import LoRAConfig
        cfg = LoRAConfig(rank=4)
        self.assertEqual(cfg.rank, 4)
        self.assertAlmostEqual(cfg.scaling, 0.25)  # alpha/rank = 1/4

    def test_custom_rank(self) -> None:
        from backend.common.sam_lora_adapter import LoRAConfig
        cfg = LoRAConfig(rank=8, alpha=2.0)
        self.assertAlmostEqual(cfg.scaling, 0.25)  # 2/8

    def test_target_modules(self) -> None:
        from backend.common.sam_lora_adapter import LoRAConfig
        cfg = LoRAConfig()
        self.assertIn('q_proj', cfg.target_modules)
        self.assertIn('v_proj', cfg.target_modules)


class LoRALayerTests(unittest.TestCase):
    """Tests for individual LoRA layers."""

    def test_layer_initialization(self) -> None:
        from backend.common.sam_lora_adapter import LoRALayer
        layer = LoRALayer(
            name='test',
            d_in=64,
            d_out=128,
            rank=4,
            scaling=0.25,
            lora_A=np.random.randn(4, 64).astype(np.float32),
            lora_B=np.zeros((128, 4), dtype=np.float32),
        )
        self.assertEqual(layer.trainable_param_count, 4 * 64 + 128 * 4)

    def test_forward_without_frozen_weight(self) -> None:
        from backend.common.sam_lora_adapter import LoRALayer
        layer = LoRALayer(
            name='test',
            d_in=32,
            d_out=16,
            rank=4,
            scaling=0.5,
            lora_A=np.random.randn(4, 32).astype(np.float32) * 0.01,
            lora_B=np.zeros((16, 4), dtype=np.float32),
        )
        x = np.random.randn(10, 32).astype(np.float32)
        out = layer.forward(x)
        self.assertEqual(out.shape, (10, 16))
        # B is zero, so output should be zero
        np.testing.assert_allclose(out, 0.0, atol=1e-6)

    def test_forward_with_frozen_weight(self) -> None:
        from backend.common.sam_lora_adapter import LoRALayer
        frozen = np.random.randn(16, 32).astype(np.float32)
        layer = LoRALayer(
            name='test',
            d_in=32,
            d_out=16,
            rank=4,
            scaling=0.5,
            lora_A=np.random.randn(4, 32).astype(np.float32) * 0.01,
            lora_B=np.zeros((16, 4), dtype=np.float32),
            frozen_weight=frozen,
        )
        x = np.random.randn(5, 32).astype(np.float32)
        out = layer.forward(x)
        expected = x @ frozen.T
        np.testing.assert_allclose(out, expected, atol=1e-5)

    def test_delta_weight(self) -> None:
        from backend.common.sam_lora_adapter import LoRALayer
        A = np.ones((4, 32), dtype=np.float32)
        B = np.ones((16, 4), dtype=np.float32)
        layer = LoRALayer(
            name='test', d_in=32, d_out=16, rank=4, scaling=0.5,
            lora_A=A, lora_B=B,
        )
        delta = layer.get_delta_weight()
        self.assertEqual(delta.shape, (16, 32))
        # delta = scaling * B @ A = 0.5 * ones(16,4) @ ones(4,32) = 0.5 * ones(16,32) * 4
        np.testing.assert_allclose(delta, 0.5 * 4.0 * np.ones((16, 32)), atol=1e-5)

    def test_merge_weights(self) -> None:
        from backend.common.sam_lora_adapter import LoRALayer
        frozen = np.ones((16, 32), dtype=np.float32)
        A = np.ones((4, 32), dtype=np.float32)
        B = np.ones((16, 4), dtype=np.float32)
        layer = LoRALayer(
            name='test', d_in=32, d_out=16, rank=4, scaling=0.5,
            lora_A=A, lora_B=B, frozen_weight=frozen,
        )
        merged = layer.merge_weights()
        expected = frozen + 0.5 * 4.0 * np.ones((16, 32))
        np.testing.assert_allclose(merged, expected, atol=1e-5)


class SamLoRAAdapterTests(unittest.TestCase):
    """Tests for the SAM LoRA adapter."""

    def test_initialize_creates_layers(self) -> None:
        from backend.common.sam_lora_adapter import SamLoRAAdapter, LoRAConfig
        adapter = SamLoRAAdapter(
            embed_dim=128, num_heads=4, num_layers=2,
            config=LoRAConfig(rank=4),
        )
        adapter.initialize()
        # 4 target modules * 2 layers = 8 LoRA layers
        self.assertEqual(len(adapter.layers), 8)

    def test_trainable_param_count_under_1m(self) -> None:
        from backend.common.sam_lora_adapter import SamLoRAAdapter, LoRAConfig
        adapter = SamLoRAAdapter(
            embed_dim=768, num_heads=12, num_layers=12,
            config=LoRAConfig(rank=4),
        )
        adapter.initialize()
        param_count = adapter.trainable_param_count
        self.assertLess(param_count, 1_000_000, f'LoRA params {param_count} should be < 1M')

    def test_export_import_weights(self) -> None:
        from backend.common.sam_lora_adapter import SamLoRAAdapter, LoRAConfig
        adapter = SamLoRAAdapter(
            embed_dim=64, num_heads=4, num_layers=2,
            config=LoRAConfig(rank=4),
        )
        adapter.initialize()
        # Modify some weights
        for layer in adapter.layers.values():
            layer.lora_B = np.random.randn(*layer.lora_B.shape).astype(np.float32) * 0.1

        exported = adapter.export_lora_weights()
        self.assertEqual(len(exported), 8)

        # Create new adapter and import
        adapter2 = SamLoRAAdapter(
            embed_dim=64, num_heads=4, num_layers=2,
            config=LoRAConfig(rank=4),
        )
        adapter2.initialize()
        adapter2.import_lora_weights(exported)

        # Verify weights match
        for name in adapter.layers:
            np.testing.assert_allclose(
                adapter.layers[name].lora_A,
                adapter2.layers[name].lora_A,
            )
            np.testing.assert_allclose(
                adapter.layers[name].lora_B,
                adapter2.layers[name].lora_B,
            )

    def test_encode_patch(self) -> None:
        from backend.common.sam_lora_adapter import SamLoRAAdapter, LoRAConfig
        adapter = SamLoRAAdapter(
            embed_dim=64, num_heads=4, num_layers=2,
            config=LoRAConfig(rank=4),
        )
        patch = np.random.randn(16, 16, 2).astype(np.float32)
        features = adapter.encode_patch(patch)
        self.assertEqual(features.ndim, 2)
        self.assertEqual(features.shape[-1], 64)

    def test_is_sam_available_false_by_default(self) -> None:
        from backend.common.sam_lora_adapter import SamLoRAAdapter
        adapter = SamLoRAAdapter(embed_dim=64, num_heads=4, num_layers=2)
        self.assertFalse(adapter.is_sam_available())


class SamSarPipelineTests(unittest.TestCase):
    """Tests for the SAM-SAR pipeline."""

    def test_pipeline_fallback_to_dummy(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        self.assertFalse(pipeline.is_sam_active)
        self.assertEqual(pipeline.active_backend, 'dummy')

        patch = np.random.randn(32, 32, 2).astype(np.float32)
        mask = pipeline.annotate(patch)
        self.assertEqual(mask.mask.shape, (32, 32))
        self.assertEqual(mask.source, 'dummy')
        self.assertGreater(mask.confidence, 0.0)

    def test_pipeline_with_unet_fallback(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        pipeline.set_unet_available(True)
        self.assertEqual(pipeline.active_backend, 'unet_fallback')

        patch = np.random.randn(32, 32, 2).astype(np.float32)
        mask = pipeline.annotate(patch)
        self.assertEqual(mask.source, 'unet_fallback')
        self.assertEqual(mask.mask.shape, (32, 32))

    def test_sam_annotate_convenience(self) -> None:
        from backend.sam_sar_pipeline import sam_annotate
        patch = np.random.randn(16, 16).astype(np.float32)
        mask = sam_annotate(patch, prompt_point=(8, 8))
        self.assertEqual(mask.mask.shape, (16, 16))
        self.assertIn(mask.source, ('sam_lora', 'unet_fallback', 'dummy'))

    def test_batch_annotate(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        patches = [np.random.randn(16, 16, 2).astype(np.float32) for _ in range(3)]
        masks = pipeline.batch_annotate(patches)
        self.assertEqual(len(masks), 3)
        for m in masks:
            self.assertEqual(m.mask.shape, (16, 16))

    def test_batch_annotate_with_prompts(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline, SAMPrompt
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        patches = [np.random.randn(16, 16, 2).astype(np.float32) for _ in range(2)]
        prompts = [
            SAMPrompt(prompt_type='point', points=[(8, 8)], labels=[1]),
            SAMPrompt(prompt_type='auto'),
        ]
        masks = pipeline.batch_annotate(patches, prompts=prompts)
        self.assertEqual(len(masks), 2)

    def test_batch_annotate_mismatched_lengths(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline, SAMPrompt
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        patches = [np.random.randn(16, 16).astype(np.float32) for _ in range(2)]
        prompts = [SAMPrompt(prompt_type='auto')]
        with self.assertRaises(ValueError):
            pipeline.batch_annotate(patches, prompts=prompts)

    def test_get_status(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        status = pipeline.get_status()
        self.assertIn('sam_enabled', status)
        self.assertIn('active_backend', status)
        self.assertIn('lora_trainable_params', status)

    def test_2d_patch_handling(self) -> None:
        from backend.sam_sar_pipeline import SamSarPipeline
        pipeline = SamSarPipeline(embed_dim=64, num_heads=4, num_layers=2)
        patch_2d = np.random.randn(24, 24).astype(np.float32)
        mask = pipeline.annotate(patch_2d)
        self.assertEqual(mask.mask.shape, (24, 24))


if __name__ == '__main__':
    unittest.main()
