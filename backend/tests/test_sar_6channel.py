"""Tests for F3: mSAFE 6-Channel FCNN SAR Upgrade."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from backend.common.sar_six_channel_synthetic import (
    generate_synthetic_2channel_pair,
    generate_synthetic_6channel_patch,
)
from backend.common.sar_model_family import (
    SAR_DEFAULT_INPUT_CHANNELS,
    SAR_SUPPORTED_CHANNEL_COUNTS,
    build_model_architecture,
    build_resnet34_unet_model,
)


class TestSyntheticDataGenerator:
    def test_6channel_patch_shape(self):
        input_6ch, mask = generate_synthetic_6channel_patch(size=128, seed=42)
        assert input_6ch.shape == (6, 128, 128)
        assert mask.shape == (1, 128, 128)
        assert input_6ch.dtype == np.float32
        assert mask.dtype == np.float32

    def test_6channel_patch_reproducible(self):
        a1, m1 = generate_synthetic_6channel_patch(size=64, seed=99)
        a2, m2 = generate_synthetic_6channel_patch(size=64, seed=99)
        np.testing.assert_array_equal(a1, a2)
        np.testing.assert_array_equal(m1, m2)

    def test_6channel_different_seeds(self):
        a1, _ = generate_synthetic_6channel_patch(size=64, seed=1)
        a2, _ = generate_synthetic_6channel_patch(size=64, seed=2)
        assert not np.array_equal(a1, a2)

    def test_2channel_pair_shape(self):
        pre, post, mask = generate_synthetic_2channel_pair(size=128, seed=42)
        assert pre.shape == (2, 128, 128)
        assert post.shape == (2, 128, 128)
        assert mask.shape == (1, 128, 128)

    def test_mask_is_binary(self):
        _, mask = generate_synthetic_6channel_patch(size=64, seed=7)
        unique = np.unique(mask)
        assert set(unique.tolist()).issubset({0.0, 1.0})

    def test_mask_has_positive_pixels(self):
        for seed in range(10):
            _, mask = generate_synthetic_6channel_patch(size=128, seed=seed)
            assert mask.sum() > 0, f'seed={seed} produced empty mask'

    def test_coherence_in_valid_range(self):
        input_6ch, _ = generate_synthetic_6channel_patch(size=64, seed=42)
        coherence = input_6ch[3]
        assert coherence.min() >= 0.0
        assert coherence.max() <= 1.0

    def test_slope_non_negative(self):
        input_6ch, _ = generate_synthetic_6channel_patch(size=64, seed=42)
        slope = input_6ch[4]
        assert slope.min() >= 0.0


class TestSarModelFamilyParameterized:
    def test_default_channels_is_2(self):
        assert SAR_DEFAULT_INPUT_CHANNELS == 2

    def test_supported_channel_counts(self):
        assert SAR_SUPPORTED_CHANNEL_COUNTS == {2, 6}

    def test_build_resnet34_unet_2ch(self):
        try:
            import segmentation_models_pytorch  # noqa: F401
        except ImportError:
            pytest.skip('segmentation_models_pytorch not installed')
        model = build_resnet34_unet_model(in_channels=2)
        assert model is not None

    def test_build_resnet34_unet_6ch(self):
        try:
            import segmentation_models_pytorch  # noqa: F401
        except ImportError:
            pytest.skip('segmentation_models_pytorch not installed')
        model = build_resnet34_unet_model(in_channels=6)
        assert model is not None

    def test_build_resnet34_unet_invalid_channels(self):
        with pytest.raises(ValueError, match='Unsupported'):
            build_resnet34_unet_model(in_channels=3)

    def test_build_model_architecture_passes_channels(self):
        try:
            import segmentation_models_pytorch  # noqa: F401
        except ImportError:
            pytest.skip('segmentation_models_pytorch not installed')
        model = build_model_architecture('resnet34_unet', in_channels=6)
        assert model is not None


class TestSarPatchDataset6Channel:
    def _create_minimal_dataset(self, tmp_path: Path, num_records: int = 4) -> Path:
        """Create a minimal patch dataset on disk for testing."""
        try:
            from rasterio.io import MemoryFile
            from rasterio.transform import from_origin
        except ImportError:
            pytest.skip('rasterio not installed')

        import torch  # noqa: F401
        from backend.common.sar_training_dataset import SarPatchRecord

        patch_root = tmp_path / '128'
        records = []
        for i in range(num_records):
            patch_dir = patch_root / 'train' / f'event_{i}' / f'patch_{i}'
            patch_dir.mkdir(parents=True, exist_ok=True)

            pre, post, mask = generate_synthetic_2channel_pair(size=128, seed=i)

            for name, data in [('pre.tif', pre), ('post.tif', post)]:
                path = patch_dir / name
                with MemoryFile() as memfile:
                    with memfile.open(
                        driver='GTiff',
                        height=128,
                        width=128,
                        count=data.shape[0],
                        dtype='float32',
                        transform=from_origin(0, 128, 1, 1),
                    ) as dst:
                        dst.write(data)
                    path.write_bytes(memfile.read())

            mask_path = patch_dir / 'mask.tif'
            mask_2d = mask[0].astype('uint8')
            with MemoryFile() as memfile:
                with memfile.open(
                    driver='GTiff',
                    height=128,
                    width=128,
                    count=1,
                    dtype='uint8',
                    transform=from_origin(0, 128, 1, 1),
                ) as dst:
                    dst.write(mask_2d, 1)
                mask_path.write_bytes(memfile.read())

            records.append(SarPatchRecord(
                split='train',
                event_id=f'evt_{i}',
                scene_id=f'scn_{i}',
                source_dataset='synthetic',
                region_key='test',
                patch_id=f'patch_{i}',
                pre_path=str(patch_dir / 'pre.tif'),
                post_path=str(patch_dir / 'post.tif'),
                mask_path=str(mask_path),
                positive_pixels=int(mask.sum()),
                total_pixels=mask.size,
            ).as_dict())

        patch_index_path = tmp_path / 'patch_index.json'
        patch_index_path.write_text(json.dumps(records, indent=2))
        return tmp_path

    def test_6channel_dataset_load(self, tmp_path):
        try:
            import torch  # noqa: F401
            from backend.common.sar_training_dataset import SarPatchDataset
        except ImportError:
            pytest.skip('torch or rasterio not installed')

        dataset_root = self._create_minimal_dataset(tmp_path)
        dataset = SarPatchDataset(dataset_root, split='train', six_channel=True)
        assert len(dataset) == 4

        item = dataset[0]
        assert 'input' in item
        assert 'pre' not in item
        assert 'post' not in item
        assert item['input'].shape == (6, 128, 128)
        assert item['mask'].shape == (1, 128, 128)

    def test_2channel_backward_compatibility(self, tmp_path):
        try:
            import torch  # noqa: F401
            from backend.common.sar_training_dataset import SarPatchDataset
        except ImportError:
            pytest.skip('torch or rasterio not installed')

        dataset_root = self._create_minimal_dataset(tmp_path)
        dataset = SarPatchDataset(dataset_root, split='train', six_channel=False)
        item = dataset[0]
        assert 'pre' in item
        assert 'post' in item
        assert 'input' not in item
        assert item['pre'].shape == (2, 128, 128)
        assert item['post'].shape == (2, 128, 128)

    def test_6channel_normalization(self, tmp_path):
        try:
            import torch  # noqa: F401
            from backend.common.sar_training_dataset import SarPatchDataset, compute_sar_normalization
        except ImportError:
            pytest.skip('torch or rasterio not installed')

        dataset_root = self._create_minimal_dataset(tmp_path)
        dataset = SarPatchDataset(dataset_root, split='train', six_channel=True)
        norm = compute_sar_normalization(dataset)
        assert norm['img_mean'].shape == (6,)
        assert norm['img_std'].shape == (6,)
        # All std values should be positive
        assert (norm['img_std'] > 0).all()

    def test_2channel_normalization_backward_compat(self, tmp_path):
        try:
            import torch  # noqa: F401
            from backend.common.sar_training_dataset import SarPatchDataset, compute_sar_normalization
        except ImportError:
            pytest.skip('torch or rasterio not installed')

        dataset_root = self._create_minimal_dataset(tmp_path)
        dataset = SarPatchDataset(dataset_root, split='train', six_channel=False)
        norm = compute_sar_normalization(dataset)
        assert norm['img_mean'].shape == (2,)
        assert norm['img_std'].shape == (2,)


class TestSwinUNet6Channel:
    def test_six_channel_forward_pass(self):
        try:
            import torch  # noqa: F401
            from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet
        except ImportError:
            pytest.skip('torch or timm not installed')

        model = ChangeDetectionSwinUNet(
            img_size=128,
            sar_in_channels=6,
            six_channel=True,
            use_aux=False,
            model_size='tiny',
            fusion_type='diff',
        )
        model.eval()

        input_6ch = torch.randn(1, 6, 128, 128)
        with torch.no_grad():
            output = model(input_6ch)
        assert output.shape == (1, 1, 128, 128)

    def test_six_channel_predict(self):
        try:
            import torch  # noqa: F401
            from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet
        except ImportError:
            pytest.skip('torch or timm not installed')

        model = ChangeDetectionSwinUNet(
            img_size=128,
            sar_in_channels=6,
            six_channel=True,
        )
        input_6ch = torch.randn(1, 6, 128, 128)
        output = model.predict(input_6ch)
        assert output.shape == (1, 1, 128, 128)

    def test_2channel_backward_compat(self):
        try:
            import torch  # noqa: F401
            from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet
        except ImportError:
            pytest.skip('torch or timm not installed')

        model = ChangeDetectionSwinUNet(
            img_size=128,
            sar_in_channels=2,
            six_channel=False,
            use_aux=False,
            model_size='tiny',
            fusion_type='diff',
        )
        model.eval()

        pre = torch.randn(1, 2, 128, 128)
        post = torch.randn(1, 2, 128, 128)
        with torch.no_grad():
            output = model(pre, post)
        assert output.shape == (1, 1, 128, 128)

    def test_six_channel_x2_is_none(self):
        try:
            import torch  # noqa: F401
            from backend.models.swinunet_tiny_diff import ChangeDetectionSwinUNet
        except ImportError:
            pytest.skip('torch or timm not installed')

        model = ChangeDetectionSwinUNet(
            img_size=128,
            sar_in_channels=6,
            six_channel=True,
        )
        model.eval()
        input_6ch = torch.randn(1, 6, 128, 128)
        # Should not raise when x2=None
        with torch.no_grad():
            output = model(input_6ch, x2=None)
        assert output.shape == (1, 1, 128, 128)


class TestTrainingPipeline6Channel:
    def test_train_one_epoch_6channel(self):
        try:
            import torch  # noqa: F401
            import torch.nn as nn  # noqa: F401
            from torch.utils.data import DataLoader, Dataset
            from backend.sar_unet_training import _train_one_epoch
        except ImportError:
            pytest.skip('torch not installed')

        class MockDataset(Dataset):
            def __len__(self):
                return 4

            def __getitem__(self, idx):
                return {
                    'input': torch.randn(6, 64, 64),
                    'mask': torch.zeros(1, 64, 64),
                }

        class MockModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv = nn.Conv2d(6, 1, 3, padding=1)

            def forward(self, x, x2=None):
                return self.conv(x)

        loader = DataLoader(MockDataset(), batch_size=2)
        model = MockModel()
        optimizer = torch.optim.Adam(model.parameters())
        criterion = nn.BCEWithLogitsLoss()

        loss = _train_one_epoch(loader, model, device='cpu', optimizer=optimizer, criterion=criterion, six_channel=True)
        assert isinstance(loss, float)
        assert loss >= 0

    def test_train_one_epoch_2channel_backward_compat(self):
        try:
            import torch  # noqa: F401
            import torch.nn as nn  # noqa: F401
            from torch.utils.data import DataLoader, Dataset
            from backend.sar_unet_training import _train_one_epoch
        except ImportError:
            pytest.skip('torch not installed')

        class MockDataset(Dataset):
            def __len__(self):
                return 4

            def __getitem__(self, idx):
                return {
                    'pre': torch.randn(2, 64, 64),
                    'post': torch.randn(2, 64, 64),
                    'mask': torch.zeros(1, 64, 64),
                }

        class MockModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv = nn.Conv2d(2, 1, 3, padding=1)

            def forward(self, x1, x2):
                return self.conv(x1)

        loader = DataLoader(MockDataset(), batch_size=2)
        model = MockModel()
        optimizer = torch.optim.Adam(model.parameters())
        criterion = nn.BCEWithLogitsLoss()

        loss = _train_one_epoch(loader, model, device='cpu', optimizer=optimizer, criterion=criterion, six_channel=False)
        assert isinstance(loss, float)
        assert loss >= 0
