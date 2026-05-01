from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from backend.common.artifacts import create_artifact_dir, dump_json
from backend.common.sar_model_family import build_model_architecture, normalize_model_family
from backend.common.sar_training_dataset import (
    BalancedPositivePatchSampler,
    SarPatchDataset,
    compute_sar_normalization,
    materialize_sar_training_dataset,
)


DEFAULT_TRAIN_SAR_EPOCHS = 8
DEFAULT_TRAIN_SAR_BATCH_SIZE = 8
DEFAULT_TRAIN_SAR_LR = 1e-4
DEFAULT_TRAIN_SAR_PATIENCE = 4
DEFAULT_F_BETA = 1.5
DEFAULT_PRECISION_FLOOR = 0.05
DEFAULT_THRESHOLD_GRID = np.linspace(0.05, 0.95, 19, dtype=np.float32)
DEFAULT_MAX_VALIDATION_POSITIVE_RATE_RATIO = 20.0
DEFAULT_MAX_VALIDATION_POSITIVE_RATE_ABSOLUTE = 0.15


class DiceLoss(nn.Module):
    def __init__(self, eps: float = 1e-6, ignore_empty: bool = False) -> None:
        super().__init__()
        self.eps = eps
        self.ignore_empty = ignore_empty

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        probs = torch.sigmoid(logits)
        target = target.float()
        probs = probs.contiguous().view(-1)
        target = target.contiguous().view(-1)
        if self.ignore_empty and target.sum() < 0.5:
            return (probs.sum() / (probs.numel() + self.eps)).clamp(0, 1)
        intersection = (probs * target).sum()
        denominator = probs.sum() + target.sum()
        dice = (2.0 * intersection + self.eps) / (denominator + self.eps)
        return 1.0 - dice


class BCEDiceLoss(nn.Module):
    def __init__(
        self,
        *,
        bce_weight: float = 0.5,
        dice_weight: float = 0.5,
        pos_weight: float = 3.0,
        ignore_empty: bool = False,
    ) -> None:
        super().__init__()
        self.bce_weight = float(bce_weight)
        self.dice_weight = float(dice_weight)
        self.register_buffer('pos_weight', torch.tensor([float(pos_weight)], dtype=torch.float32))
        self.dice = DiceLoss(ignore_empty=ignore_empty)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        target = target.float()
        bce = nn.functional.binary_cross_entropy_with_logits(logits, target, pos_weight=self.pos_weight)
        dice = self.dice(logits, target)
        return (self.bce_weight * bce) + (self.dice_weight * dice)


class FocalTverskyLoss(nn.Module):
    def __init__(
        self,
        *,
        alpha: float = 0.7,
        beta: float = 0.3,
        gamma: float = 1.33,
        eps: float = 1e-7,
    ) -> None:
        super().__init__()
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.gamma = float(gamma)
        self.eps = float(eps)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        probs = torch.sigmoid(logits)
        targets = targets.float()
        dims = tuple(range(2, probs.ndim))
        true_positive = (probs * targets).sum(dim=dims)
        false_positive = (probs * (1.0 - targets)).sum(dim=dims)
        false_negative = ((1.0 - probs) * targets).sum(dim=dims)
        tversky = (true_positive + self.eps) / (
            true_positive + (self.alpha * false_negative) + (self.beta * false_positive) + self.eps
        )
        return torch.pow(1.0 - tversky, self.gamma).mean()


@dataclass(frozen=True)
class TrainingConfig:
    model_family: str
    patch_size: int
    stride: int
    epochs: int
    batch_size: int
    learning_rate: float
    patience: int
    loss_name: str
    candidate_model_version: str
    f_beta: float
    precision_floor: float
    threshold_grid: np.ndarray
    max_validation_positive_rate_ratio: float
    max_validation_positive_rate_absolute: float


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _timestamp_slug() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _loss_from_name(loss_name: str) -> nn.Module:
    if loss_name == 'focal_tversky':
        return FocalTverskyLoss()
    if loss_name == 'bce_dice':
        return BCEDiceLoss(ignore_empty=True)
    if loss_name == 'bce':
        return nn.BCEWithLogitsLoss()
    raise ValueError(f'unsupported SAR loss "{loss_name}"')


def _state_dict_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ('state_dict', 'model_state_dict', 'model'):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        return payload
    raise RuntimeError('checkpoint payload must be a dict or contain a nested state_dict')


def _load_initial_checkpoint(
    model: nn.Module,
    *,
    checkpoint_path: Path | None,
    device: str,
) -> dict[str, Any] | None:
    if checkpoint_path is None:
        return None
    if not checkpoint_path.exists():
        raise FileNotFoundError(f'initial SAR checkpoint not found: {checkpoint_path}')
    payload = torch.load(checkpoint_path, map_location=device)
    state_dict = _state_dict_from_payload(payload)
    load_result = model.load_state_dict(state_dict, strict=False)
    missing_keys = [str(item) for item in (getattr(load_result, 'missing_keys', None) or [])]
    unexpected_keys = [str(item) for item in (getattr(load_result, 'unexpected_keys', None) or [])]
    return {
        'checkpoint_path': str(checkpoint_path),
        'missing_keys': missing_keys,
        'unexpected_keys': unexpected_keys,
        'missing_count': len(missing_keys),
        'unexpected_count': len(unexpected_keys),
        'has_mismatch': bool(missing_keys or unexpected_keys),
    }


def _build_counts_template(threshold_grid: np.ndarray) -> dict[float, dict[str, int]]:
    return {
        float(threshold): {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
        for threshold in threshold_grid.tolist()
    }


def _update_threshold_counts(
    counts: dict[float, dict[str, int]],
    probabilities: np.ndarray,
    targets: np.ndarray,
) -> None:
    probabilities = np.asarray(probabilities, dtype=np.float32)
    targets = np.asarray(targets, dtype=bool)
    for threshold, aggregate in counts.items():
        predictions = probabilities >= float(threshold)
        aggregate['tp'] += int(np.sum(predictions & targets))
        aggregate['fp'] += int(np.sum(predictions & ~targets))
        aggregate['fn'] += int(np.sum(~predictions & targets))
        aggregate['tn'] += int(np.sum(~predictions & ~targets))


def _metrics_from_counts(counts: dict[str, int]) -> dict[str, float]:
    tp = int(counts['tp'])
    fp = int(counts['fp'])
    fn = int(counts['fn'])
    tn = int(counts['tn'])
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2.0 * precision * recall) / max(precision + recall, 1e-9)
    false_positive_rate = fp / max(fp + tn, 1)
    iou = tp / max(tp + fp + fn, 1)
    return {
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1),
        'iou': float(iou),
        'false_positive_rate': float(false_positive_rate),
    }


def _select_best_threshold(
    counts: dict[float, dict[str, int]],
    *,
    f_beta: float,
    precision_floor: float,
) -> tuple[float, dict[str, Any]]:
    beta_sq = float(f_beta) ** 2
    metrics_by_threshold: list[dict[str, Any]] = []
    for threshold, threshold_counts in sorted(counts.items()):
        metrics = _metrics_from_counts(threshold_counts)
        precision = metrics['precision']
        recall = metrics['recall']
        f_beta_score = (
            (1.0 + beta_sq) * precision * recall / max((beta_sq * precision) + recall, 1e-9)
        )
        metrics_by_threshold.append({
            'threshold': float(threshold),
            **metrics,
            'f_beta': float(f_beta_score),
        })
    eligible = [entry for entry in metrics_by_threshold if entry['precision'] >= precision_floor]
    if eligible:
        best = max(eligible, key=lambda entry: (entry['recall'], entry['f_beta'], entry['precision']))
    else:
        best = max(metrics_by_threshold, key=lambda entry: (entry['f_beta'], entry['precision'], entry['recall']))
    recall_axis = np.asarray([entry['recall'] for entry in metrics_by_threshold], dtype=np.float32)
    precision_axis = np.asarray([entry['precision'] for entry in metrics_by_threshold], dtype=np.float32)
    order = np.argsort(recall_axis)
    auprc = float(np.trapz(precision_axis[order], recall_axis[order]))
    return float(best['threshold']), {
        'best': best,
        'auprc': auprc,
        'threshold_metrics': metrics_by_threshold,
    }


def _scene_breakdown(
    loader: DataLoader,
    model: nn.Module,
    *,
    device: str,
    threshold: float,
) -> list[dict[str, Any]]:
    scene_counts: dict[str, dict[str, int]] = {}
    model.eval()
    with torch.no_grad():
        for batch in loader:
            pre = batch['pre'].to(device)
            post = batch['post'].to(device)
            logits = model(pre, post)
            probabilities = torch.sigmoid(logits).detach().cpu().numpy()[:, 0]
            targets = batch['mask'].detach().cpu().numpy()[:, 0] >= 0.5
            scene_ids = batch['scene_id']
            for index, scene_id in enumerate(scene_ids):
                key = str(scene_id)
                counts = scene_counts.setdefault(key, {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'positive_pixels': 0, 'predicted_pixels': 0, 'total_pixels': 0})
                predictions = probabilities[index] >= threshold
                target = targets[index]
                counts['tp'] += int(np.sum(predictions & target))
                counts['fp'] += int(np.sum(predictions & ~target))
                counts['fn'] += int(np.sum(~predictions & target))
                counts['tn'] += int(np.sum(~predictions & ~target))
                counts['positive_pixels'] += int(np.sum(target))
                counts['predicted_pixels'] += int(np.sum(predictions))
                counts['total_pixels'] += int(target.size)
    breakdown: list[dict[str, Any]] = []
    for scene_id, counts in sorted(scene_counts.items()):
        metrics = _metrics_from_counts(counts)
        truth_positive_rate = counts['positive_pixels'] / max(counts['total_pixels'], 1)
        predicted_positive_rate = counts['predicted_pixels'] / max(counts['total_pixels'], 1)
        positive_rate_ratio = predicted_positive_rate / max(truth_positive_rate, 1e-6)
        breakdown.append({
            'scene_id': scene_id,
            **metrics,
            'truth_positive_rate': float(truth_positive_rate),
            'predicted_positive_rate': float(predicted_positive_rate),
            'positive_rate_ratio': float(positive_rate_ratio),
        })
    return breakdown


def _validation_quality_gate(
    scene_breakdown: list[dict[str, Any]],
    *,
    max_positive_rate_ratio: float,
    max_positive_rate_absolute: float,
) -> dict[str, Any]:
    failures = [
        {
            'scene_id': str(scene['scene_id']),
            'reason': 'inflated_positive_rate',
            'predicted_positive_rate': float(scene['predicted_positive_rate']),
            'truth_positive_rate': float(scene['truth_positive_rate']),
            'positive_rate_ratio': float(scene['positive_rate_ratio']),
        }
        for scene in scene_breakdown
        if float(scene['predicted_positive_rate']) > max_positive_rate_absolute
        and float(scene['positive_rate_ratio']) > max_positive_rate_ratio
    ]
    return {
        'passed': not failures,
        'blocked_gate': None if not failures else 'validation_positive_rate',
        'failures': failures,
    }


def _save_checkpoint(
    model: nn.Module,
    *,
    checkpoint_path: Path,
    metadata: dict[str, Any],
) -> None:
    payload = {
        'state_dict': model.state_dict(),
        'metadata': metadata,
    }
    torch.save(payload, checkpoint_path)


def _assert_clean_checkpoint_load(
    checkpoint_path: Path,
    *,
    model_family: str,
    patch_size: int,
    device: str,
) -> None:
    model = build_model_architecture(model_family, image_size=patch_size)
    state_dict = _state_dict_from_payload(torch.load(checkpoint_path, map_location=device))
    load_result = model.load_state_dict(state_dict, strict=True)
    if getattr(load_result, 'missing_keys', None) or getattr(load_result, 'unexpected_keys', None):
        raise RuntimeError('trained SAR checkpoint failed strict clean-load validation')


def _train_one_epoch(
    loader: DataLoader,
    model: nn.Module,
    *,
    device: str,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
) -> float:
    model.train()
    running_loss = 0.0
    seen = 0
    for batch in loader:
        pre = batch['pre'].to(device)
        post = batch['post'].to(device)
        mask = batch['mask'].to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(pre, post)
        loss = criterion(logits, mask)
        loss.backward()
        optimizer.step()
        batch_size = int(mask.shape[0])
        running_loss += float(loss.item()) * batch_size
        seen += batch_size
    return running_loss / max(seen, 1)


def _validate(
    loader: DataLoader,
    model: nn.Module,
    *,
    device: str,
    criterion: nn.Module,
    threshold_grid: np.ndarray,
    f_beta: float,
    precision_floor: float,
) -> dict[str, Any]:
    model.eval()
    threshold_counts = _build_counts_template(threshold_grid)
    running_loss = 0.0
    seen = 0
    with torch.no_grad():
        for batch in loader:
            pre = batch['pre'].to(device)
            post = batch['post'].to(device)
            mask = batch['mask'].to(device)
            logits = model(pre, post)
            loss = criterion(logits, mask)
            probabilities = torch.sigmoid(logits).detach().cpu().numpy()[:, 0]
            targets = mask.detach().cpu().numpy()[:, 0] >= 0.5
            for index in range(probabilities.shape[0]):
                _update_threshold_counts(threshold_counts, probabilities[index], targets[index])
            batch_size = int(mask.shape[0])
            running_loss += float(loss.item()) * batch_size
            seen += batch_size
    best_threshold, selection = _select_best_threshold(
        threshold_counts,
        f_beta=f_beta,
        precision_floor=precision_floor,
    )
    return {
        'loss': running_loss / max(seen, 1),
        'best_threshold': best_threshold,
        'auprc': float(selection['auprc']),
        'best_metrics': selection['best'],
        'threshold_metrics': selection['threshold_metrics'],
    }


def _training_config_from_request(request: dict[str, Any]) -> TrainingConfig:
    model_family = normalize_model_family(str(request.get('model_family') or 'swinunet_tiny_diff'))
    patch_size = int(request.get('patch_size') or 128)
    stride = int(request.get('stride') or 64)
    candidate_model_version = str(request.get('candidate_model_version') or f'{model_family}_shadow_candidate_{_timestamp_slug()}')
    threshold_grid = np.asarray(request.get('threshold_grid') or DEFAULT_THRESHOLD_GRID.tolist(), dtype=np.float32)
    return TrainingConfig(
        model_family=model_family,
        patch_size=patch_size,
        stride=stride,
        epochs=int(request.get('epochs') or DEFAULT_TRAIN_SAR_EPOCHS),
        batch_size=int(request.get('batch_size') or DEFAULT_TRAIN_SAR_BATCH_SIZE),
        learning_rate=float(request.get('learning_rate') or DEFAULT_TRAIN_SAR_LR),
        patience=int(request.get('patience') or DEFAULT_TRAIN_SAR_PATIENCE),
        loss_name=str(request.get('loss') or 'focal_tversky'),
        candidate_model_version=candidate_model_version,
        f_beta=float(request.get('f_beta') or DEFAULT_F_BETA),
        precision_floor=float(request.get('precision_floor') or DEFAULT_PRECISION_FLOOR),
        threshold_grid=threshold_grid,
        max_validation_positive_rate_ratio=float(
            request.get('max_validation_positive_rate_ratio') or DEFAULT_MAX_VALIDATION_POSITIVE_RATE_RATIO
        ),
        max_validation_positive_rate_absolute=float(
            request.get('max_validation_positive_rate_absolute') or DEFAULT_MAX_VALIDATION_POSITIVE_RATE_ABSOLUTE
        ),
    )


def train_sar_unet(
    request: dict[str, Any],
    *,
    artifact_root: Path,
    device: str = 'cpu',
) -> dict[str, Any]:
    if not torch:
        raise RuntimeError('torch is required for SAR training')
    training_manifest_source = request.get('training_manifest') or request.get('training_manifest_path')
    if not training_manifest_source:
        raise ValueError('train-sar-unet requires training_manifest or training_manifest_path')

    config = _training_config_from_request(request)
    artifact_dir = create_artifact_dir(artifact_root)
    dataset_root = artifact_dir / 'sar_training_dataset'
    seed = int(request.get('seed') or 42)
    _set_seed(seed)

    dataset_audit = materialize_sar_training_dataset(
        manifest_source=training_manifest_source,
        output_root=dataset_root,
        patch_size=config.patch_size,
        stride=config.stride,
    )

    train_dataset = SarPatchDataset(dataset_root, split='train', augment=True)
    normalization = compute_sar_normalization(train_dataset)
    val_dataset = SarPatchDataset(dataset_root, split='val', normalization=normalization, augment=False)
    train_dataset.normalization = normalization
    sampler = BalancedPositivePatchSampler(
        train_dataset,
        negative_ratio=int(request.get('negative_ratio') or 1),
        seed=seed,
    )
    train_loader = DataLoader(train_dataset, batch_size=config.batch_size, sampler=sampler, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=max(1, config.batch_size), shuffle=False, num_workers=0)

    model = build_model_architecture(config.model_family, image_size=config.patch_size).to(device)
    initial_checkpoint_path = None
    raw_initial_checkpoint = request.get('initial_checkpoint_path')
    if isinstance(raw_initial_checkpoint, str) and raw_initial_checkpoint.strip():
        initial_checkpoint_path = Path(raw_initial_checkpoint.strip()).expanduser()
    initial_checkpoint = _load_initial_checkpoint(
        model,
        checkpoint_path=initial_checkpoint_path,
        device=device,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=1e-4)
    criterion = _loss_from_name(config.loss_name).to(device)
    best_validation: dict[str, Any] | None = None
    best_state_dict: dict[str, Any] | None = None
    epochs_without_improvement = 0
    train_loss_history: list[float] = []
    val_loss_history: list[float] = []

    for epoch in range(config.epochs):
        train_loss = _train_one_epoch(
            train_loader,
            model,
            device=device,
            optimizer=optimizer,
            criterion=criterion,
        )
        validation = _validate(
            val_loader,
            model,
            device=device,
            criterion=criterion,
            threshold_grid=config.threshold_grid,
            f_beta=config.f_beta,
            precision_floor=config.precision_floor,
        )
        train_loss_history.append(float(train_loss))
        val_loss_history.append(float(validation['loss']))
        if best_validation is None or float(validation['auprc']) > float(best_validation['auprc']):
            best_validation = validation
            best_state_dict = {key: value.detach().cpu() for key, value in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.patience:
                break

    if best_validation is None or best_state_dict is None:
        raise RuntimeError('SAR training did not produce a validation candidate')

    checkpoint_path = artifact_dir / 'sar_model.pt'
    model.load_state_dict(best_state_dict, strict=True)
    scene_breakdown = _scene_breakdown(
        val_loader,
        model,
        device=device,
        threshold=float(best_validation['best_threshold']),
    )
    quality_gate = _validation_quality_gate(
        scene_breakdown,
        max_positive_rate_ratio=config.max_validation_positive_rate_ratio,
        max_positive_rate_absolute=config.max_validation_positive_rate_absolute,
    )
    checkpoint_metadata = {
        'model_family': config.model_family,
        'candidate_model_version': config.candidate_model_version,
        'dataset_version': dataset_audit['dataset_version'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
        'loss': config.loss_name,
        'best_threshold': float(best_validation['best_threshold']),
        'validation_metrics': best_validation['best_metrics'],
        'validation_auprc': float(best_validation['auprc']),
        'initial_checkpoint': initial_checkpoint,
        'normalization': {
            'img_mean': normalization['img_mean'].tolist(),
            'img_std': normalization['img_std'].tolist(),
        },
    }
    _save_checkpoint(model, checkpoint_path=checkpoint_path, metadata=checkpoint_metadata)
    _assert_clean_checkpoint_load(
        checkpoint_path,
        model_family=config.model_family,
        patch_size=config.patch_size,
        device=device,
    )

    metrics_payload = {
        'status': 'ok',
        'candidate_model_version': config.candidate_model_version,
        'model_family': config.model_family,
        'patch_size': config.patch_size,
        'stride': config.stride,
        'epochs_requested': config.epochs,
        'epochs_completed': len(train_loss_history),
        'loss': config.loss_name,
        'best_threshold': float(best_validation['best_threshold']),
        'validation_auprc': float(best_validation['auprc']),
        'validation_metrics': best_validation['best_metrics'],
        'threshold_metrics': best_validation['threshold_metrics'],
        'scene_breakdown': scene_breakdown,
        'quality_gate': quality_gate,
        'train_loss_history': train_loss_history,
        'val_loss_history': val_loss_history,
        'dataset_audit': dataset_audit,
        'initial_checkpoint': initial_checkpoint,
        'model_checkpoint_path': str(checkpoint_path),
    }
    dump_json(artifact_dir / 'sar_training_metrics.json', metrics_payload)
    status = 'ok' if quality_gate['passed'] else 'completed_with_validation_gate_failure'
    report = {
        'status': status,
        'request_type': 'train_sar_unet',
        'artifact_dir': str(artifact_dir),
        'candidate_model_version': config.candidate_model_version,
        'model_family': config.model_family,
        'model_checkpoint_path': str(checkpoint_path),
        'best_threshold': float(best_validation['best_threshold']),
        'validation_auprc': float(best_validation['auprc']),
        'validation_metrics': best_validation['best_metrics'],
        'quality_gate_passed': bool(quality_gate['passed']),
        'blocked_gate': quality_gate['blocked_gate'],
        'scene_gate_failures': quality_gate['failures'],
        'dataset_version': dataset_audit['dataset_version'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
    }
    dump_json(artifact_dir / 'train_sar_unet_manifest.json', report)
    return report


def build_cli_request(args: Any) -> dict[str, Any]:
    request = {
        'training_manifest_path': str(args.training_manifest),
        'model_family': args.model_family,
        'patch_size': args.patch_size,
        'stride': args.stride,
        'epochs': args.epochs,
        'batch_size': args.batch_size,
        'learning_rate': args.learning_rate,
        'patience': args.patience,
        'loss': args.loss,
        'candidate_model_version': args.candidate_model_version,
        'seed': args.seed,
        'f_beta': args.f_beta,
        'precision_floor': args.precision_floor,
    }
    if args.initial_checkpoint_path:
        request['initial_checkpoint_path'] = str(args.initial_checkpoint_path)
    return request
