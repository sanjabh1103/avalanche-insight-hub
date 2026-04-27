from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.common.sequence_features import STATIC_SEQUENCE_FEATURES, build_training_branch_arrays

try:  # pragma: no cover - optional dependency at import time
    import torch
    from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
except Exception:  # pragma: no cover - optional dependency
    torch = None
    DataLoader = None
    Dataset = object
    WeightedRandomSampler = None


@dataclass(frozen=True)
class MTSNormalizationStats:
    hourly_mean: np.ndarray
    hourly_std: np.ndarray
    daily_mean: np.ndarray
    daily_std: np.ndarray
    static_mean: np.ndarray
    static_std: np.ndarray


def _sequence_norm_stats(array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = array.mean(axis=(0, 1), keepdims=True)
    std = array.std(axis=(0, 1), keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


def _vector_norm_stats(array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = array.mean(axis=0, keepdims=True)
    std = array.std(axis=0, keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


class MTSAvalancheDataset(Dataset):
    def __init__(
        self,
        *,
        hourly: np.ndarray,
        daily: np.ndarray,
        static: np.ndarray,
        labels: np.ndarray,
        sample_weights: np.ndarray,
        hourly_mean: np.ndarray | None = None,
        hourly_std: np.ndarray | None = None,
        daily_mean: np.ndarray | None = None,
        daily_std: np.ndarray | None = None,
        static_mean: np.ndarray | None = None,
        static_std: np.ndarray | None = None,
    ) -> None:
        self.hourly = np.asarray(hourly, dtype=np.float32)
        self.daily = np.asarray(daily, dtype=np.float32)
        self.static = np.asarray(static, dtype=np.float32)
        self.labels = np.asarray(labels, dtype=np.float32)
        self.sample_weights = np.asarray(sample_weights, dtype=np.float32)
        self.hourly_mean = None if hourly_mean is None else np.asarray(hourly_mean, dtype=np.float32)
        self.hourly_std = None if hourly_std is None else np.asarray(hourly_std, dtype=np.float32)
        self.daily_mean = None if daily_mean is None else np.asarray(daily_mean, dtype=np.float32)
        self.daily_std = None if daily_std is None else np.asarray(daily_std, dtype=np.float32)
        self.static_mean = None if static_mean is None else np.asarray(static_mean, dtype=np.float32)
        self.static_std = None if static_std is None else np.asarray(static_std, dtype=np.float32)

    def __len__(self) -> int:
        return int(self.labels.shape[0])

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        if torch is None:  # pragma: no cover - exercised only when torch missing
            raise RuntimeError('MTS-LSTM dataset requires torch')
        hourly = self.hourly[idx]
        daily = self.daily[idx]
        static = self.static[idx]
        if self.hourly_mean is not None and self.hourly_std is not None:
            hourly = (hourly - self.hourly_mean[0]) / self.hourly_std[0]
        if self.daily_mean is not None and self.daily_std is not None:
            daily = (daily - self.daily_mean[0]) / self.daily_std[0]
        if self.static_mean is not None and self.static_std is not None:
            static = (static - self.static_mean[0]) / self.static_std[0]
        return {
            'hourly': torch.tensor(hourly, dtype=torch.float32),
            'daily': torch.tensor(daily, dtype=torch.float32),
            'static': torch.tensor(static, dtype=torch.float32),
            'label': torch.tensor(self.labels[idx], dtype=torch.float32),
            'sample_weight': torch.tensor(self.sample_weights[idx], dtype=torch.float32),
        }


def build_mts_lstm_dataset(
    frame: pd.DataFrame,
    *,
    region_centers: dict[str, tuple[float, float]],
    dynamic_features: list[str],
    static_features: list[str] | None,
    hourly_steps: int,
    daily_steps: int,
    normalization_stats: MTSNormalizationStats | None = None,
) -> MTSAvalancheDataset:
    static_names = static_features or list(STATIC_SEQUENCE_FEATURES)
    branches = build_training_branch_arrays(
        frame,
        region_centers=region_centers,
        dynamic_features=dynamic_features,
        static_features=static_names,
        hourly_steps=hourly_steps,
        daily_steps=daily_steps,
    )
    labels = frame['label'].astype(float).to_numpy(dtype=np.float32)
    sample_weights = frame.get('training_weight', pd.Series(1.0, index=frame.index)).astype(float).to_numpy(dtype=np.float32)
    dataset_kwargs: dict[str, np.ndarray] = {}
    if normalization_stats is not None:
        dataset_kwargs = {
            'hourly_mean': normalization_stats.hourly_mean,
            'hourly_std': normalization_stats.hourly_std,
            'daily_mean': normalization_stats.daily_mean,
            'daily_std': normalization_stats.daily_std,
            'static_mean': normalization_stats.static_mean,
            'static_std': normalization_stats.static_std,
        }
    return MTSAvalancheDataset(
        hourly=branches.hourly,
        daily=branches.daily,
        static=branches.static,
        labels=labels,
        sample_weights=sample_weights,
        **dataset_kwargs,
    )


def build_mts_lstm_weighted_sampler(labels: np.ndarray, sample_weights: np.ndarray) -> WeightedRandomSampler | None:
    if torch is None or WeightedRandomSampler is None:
        return None
    y = np.asarray(labels).astype(int)
    weights = np.asarray(sample_weights, dtype=np.float32)
    if y.size == 0:
        return None
    unique, counts = np.unique(y, return_counts=True)
    class_counts = {int(label): int(count) for label, count in zip(unique, counts, strict=True)}
    if 0 not in class_counts or 1 not in class_counts:
        return None
    total_rows = int(y.size)
    class_factors = {label: total_rows / (2.0 * count) for label, count in class_counts.items()}
    sampler_weights = np.asarray(
        [float(weights[idx]) * float(class_factors[int(label)]) for idx, label in enumerate(y)],
        dtype=np.float32,
    )
    return WeightedRandomSampler(
        weights=torch.tensor(sampler_weights, dtype=torch.double),
        num_samples=total_rows,
        replacement=True,
    )


def build_mts_lstm_dataloaders(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    region_centers: dict[str, tuple[float, float]],
    dynamic_features: list[str],
    static_features: list[str] | None,
    hourly_steps: int,
    daily_steps: int,
    batch_size: int,
) -> tuple[DataLoader, DataLoader, MTSNormalizationStats]:
    if torch is None or DataLoader is None:
        raise RuntimeError('MTS-LSTM dataloaders require torch')

    train_raw_dataset = build_mts_lstm_dataset(
        train_df,
        region_centers=region_centers,
        dynamic_features=dynamic_features,
        static_features=static_features,
        hourly_steps=hourly_steps,
        daily_steps=daily_steps,
        normalization_stats=None,
    )
    hourly_mean, hourly_std = _sequence_norm_stats(train_raw_dataset.hourly)
    daily_mean, daily_std = _sequence_norm_stats(train_raw_dataset.daily)
    static_mean, static_std = _vector_norm_stats(train_raw_dataset.static)
    stats = MTSNormalizationStats(
        hourly_mean=hourly_mean,
        hourly_std=hourly_std,
        daily_mean=daily_mean,
        daily_std=daily_std,
        static_mean=static_mean,
        static_std=static_std,
    )
    train_dataset = MTSAvalancheDataset(
        hourly=train_raw_dataset.hourly,
        daily=train_raw_dataset.daily,
        static=train_raw_dataset.static,
        labels=train_raw_dataset.labels,
        sample_weights=train_raw_dataset.sample_weights,
        hourly_mean=stats.hourly_mean,
        hourly_std=stats.hourly_std,
        daily_mean=stats.daily_mean,
        daily_std=stats.daily_std,
        static_mean=stats.static_mean,
        static_std=stats.static_std,
    )
    validation_raw_dataset = build_mts_lstm_dataset(
        validation_df,
        region_centers=region_centers,
        dynamic_features=dynamic_features,
        static_features=static_features,
        hourly_steps=hourly_steps,
        daily_steps=daily_steps,
        normalization_stats=None,
    )
    validation_dataset = MTSAvalancheDataset(
        hourly=validation_raw_dataset.hourly,
        daily=validation_raw_dataset.daily,
        static=validation_raw_dataset.static,
        labels=validation_raw_dataset.labels,
        sample_weights=validation_raw_dataset.sample_weights,
        hourly_mean=stats.hourly_mean,
        hourly_std=stats.hourly_std,
        daily_mean=stats.daily_mean,
        daily_std=stats.daily_std,
        static_mean=stats.static_mean,
        static_std=stats.static_std,
    )
    train_batch_size = max(1, min(int(batch_size), len(train_dataset)))
    validation_batch_size = max(1, min(int(batch_size), len(validation_dataset)))
    sampler = build_mts_lstm_weighted_sampler(train_dataset.labels, train_dataset.sample_weights)
    train_loader = DataLoader(
        train_dataset,
        batch_size=train_batch_size,
        sampler=sampler,
        shuffle=bool(sampler is None),
        drop_last=False,
        num_workers=0,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=validation_batch_size,
        shuffle=False,
        drop_last=False,
        num_workers=0,
    )
    return train_loader, validation_loader, stats
