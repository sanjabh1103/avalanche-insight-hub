from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
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
    _load_truth_mask_from_ref,
    compute_sar_normalization,
    load_sar_training_manifest,
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
DEFAULT_POSTPROCESS_RECALL_FLOOR = 0.50
EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION = 'european_sar_prediction_artifact_v1'
SAR_VALIDATION_ERROR_DIAGNOSTICS_VERSION = 'sar_validation_error_diagnostics_v1'


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
class PostprocessConfig:
    min_component_area_px: int = 0
    opening_size_px: int = 0
    apply_to_threshold_selection: bool = False
    recall_floor: float = DEFAULT_POSTPROCESS_RECALL_FLOOR

    @property
    def enabled(self) -> bool:
        return self.min_component_area_px > 0 or self.opening_size_px > 1


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
    focal_tversky_alpha: float
    focal_tversky_beta: float
    focal_tversky_gamma: float
    postprocess: PostprocessConfig


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _timestamp_slug() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _loss_from_name(
    loss_name: str,
    *,
    focal_tversky_alpha: float = 0.7,
    focal_tversky_beta: float = 0.3,
    focal_tversky_gamma: float = 1.33,
) -> nn.Module:
    if loss_name == 'focal_tversky':
        return FocalTverskyLoss(
            alpha=focal_tversky_alpha,
            beta=focal_tversky_beta,
            gamma=focal_tversky_gamma,
        )
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
    *,
    min_component_area_px: int = 0,
    opening_size_px: int = 0,
) -> None:
    probabilities = np.asarray(probabilities, dtype=np.float32)
    targets = np.asarray(targets, dtype=bool)
    for threshold, aggregate in counts.items():
        predictions = probabilities >= float(threshold)
        predictions = _postprocess_binary_mask(
            predictions,
            min_component_area_px=min_component_area_px,
            opening_size_px=opening_size_px,
        )
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
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1),
        'iou': float(iou),
        'false_positive_rate': float(false_positive_rate),
    }


def _f_beta_score(precision: float, recall: float, beta: float) -> float:
    beta_sq = float(beta) ** 2
    return (1.0 + beta_sq) * precision * recall / max((beta_sq * precision) + recall, 1e-9)


def _postprocess_binary_mask(
    predictions: np.ndarray,
    *,
    min_component_area_px: int = 0,
    opening_size_px: int = 0,
) -> np.ndarray:
    processed = np.asarray(predictions, dtype=bool)
    if opening_size_px <= 1 and min_component_area_px <= 0:
        return processed

    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - scipy is part of backend requirements
        raise RuntimeError('scipy is required for SAR validation post-processing') from exc

    if opening_size_px > 1:
        structure = np.ones((int(opening_size_px), int(opening_size_px)), dtype=bool)
        processed = ndimage.binary_opening(processed, structure=structure)

    if min_component_area_px > 0:
        labeled, component_count = ndimage.label(processed)
        if component_count:
            sizes = np.bincount(labeled.ravel())
            keep = sizes >= int(min_component_area_px)
            keep[0] = False
            processed = keep[labeled]

    return np.asarray(processed, dtype=bool)


def _component_summaries(
    mask: np.ndarray,
    *,
    scene_id: str,
    patch_id: str,
    component_type: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    binary = np.asarray(mask, dtype=bool)
    if not np.any(binary):
        return []
    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - scipy is part of backend requirements
        raise RuntimeError('scipy is required for SAR validation component diagnostics') from exc
    labeled, component_count = ndimage.label(binary)
    if component_count <= 0:
        return []
    sizes = np.bincount(labeled.ravel())
    rows = [
        {
            'scene_id': scene_id,
            'patch_id': patch_id,
            'component_type': component_type,
            'component_index': int(index),
            'pixel_count': int(sizes[index]),
        }
        for index in range(1, component_count + 1)
        if int(sizes[index]) > 0
    ]
    return sorted(rows, key=lambda row: row['pixel_count'], reverse=True)[:limit]


def _postprocess_candidates(config: PostprocessConfig | None) -> list[dict[str, int]]:
    if config is None or not config.enabled or not config.apply_to_threshold_selection:
        return [{'opening_size_px': 0, 'min_component_area_px': 0}]

    opening_candidates = [0]
    if config.opening_size_px > 1:
        opening_candidates.append(int(config.opening_size_px))

    area_candidates = [0]
    if config.min_component_area_px > 0:
        area_candidates.extend([
            max(1, int(config.min_component_area_px) // 4),
            max(1, int(config.min_component_area_px) // 2),
            int(config.min_component_area_px),
        ])

    candidates: list[dict[str, int]] = []
    for opening_size_px in sorted(set(opening_candidates)):
        for min_component_area_px in sorted(set(area_candidates)):
            candidates.append({
                'opening_size_px': opening_size_px,
                'min_component_area_px': min_component_area_px,
            })
    return candidates


def _select_best_threshold(
    counts: dict[float, dict[str, int]],
    *,
    f_beta: float,
    precision_floor: float,
) -> tuple[float, dict[str, Any]]:
    metrics_by_threshold: list[dict[str, Any]] = []
    for threshold, threshold_counts in sorted(counts.items()):
        metrics = _metrics_from_counts(threshold_counts)
        precision = metrics['precision']
        recall = metrics['recall']
        f_beta_score = _f_beta_score(precision, recall, f_beta)
        metrics_by_threshold.append({
            'threshold': float(threshold),
            **metrics,
            'f_beta': float(f_beta_score),
            'f0_5': float(_f_beta_score(precision, recall, 0.5)),
        })
    eligible = [entry for entry in metrics_by_threshold if entry['precision'] >= precision_floor]
    if eligible:
        best = max(eligible, key=lambda entry: (entry['recall'], entry['f_beta'], entry['precision']))
    else:
        best = max(metrics_by_threshold, key=lambda entry: (entry['f_beta'], entry['precision'], entry['recall']))
    recall_axis = np.asarray([entry['recall'] for entry in metrics_by_threshold], dtype=np.float32)
    precision_axis = np.asarray([entry['precision'] for entry in metrics_by_threshold], dtype=np.float32)
    order = np.argsort(recall_axis)
    trapezoid = getattr(np, 'trapezoid', None)
    if callable(trapezoid):
        auprc = float(trapezoid(precision_axis[order], recall_axis[order]))
    else:  # pragma: no cover - NumPy < 2 compatibility
        auprc = float(np.trapz(precision_axis[order], recall_axis[order]))
    return float(best['threshold']), {
        'best': best,
        'auprc': auprc,
        'threshold_metrics': metrics_by_threshold,
        'precision_floor_met': bool(eligible),
        'max_precision': float(max(metrics_by_threshold, key=lambda entry: entry['precision'])['precision']),
        'best_precision_threshold': float(max(metrics_by_threshold, key=lambda entry: entry['precision'])['threshold']),
    }


def _select_best_postprocessed_threshold(
    counts_by_candidate: dict[tuple[int, int], dict[float, dict[str, int]]],
    *,
    f_beta: float,
    precision_floor: float,
    recall_floor: float,
) -> tuple[float, dict[str, Any]]:
    candidate_results: list[dict[str, Any]] = []
    eligible_results: list[dict[str, Any]] = []
    for (opening_size_px, min_component_area_px), counts in sorted(counts_by_candidate.items()):
        threshold, selection = _select_best_threshold(
            counts,
            f_beta=f_beta,
            precision_floor=precision_floor,
        )
        threshold_metrics = selection['threshold_metrics']
        eligible_rows = [
            row
            for row in threshold_metrics
            if float(row['precision']) >= float(precision_floor)
            and float(row['recall']) >= float(recall_floor)
        ]
        best_candidate_row = max(threshold_metrics, key=lambda row: (float(row['f0_5']), float(row['precision']), float(row['recall'])))
        candidate_summary = {
            'opening_size_px': int(opening_size_px),
            'min_component_area_px': int(min_component_area_px),
            'best_threshold': float(threshold),
            'best_metrics': selection['best'],
            'best_f0_5_metrics': best_candidate_row,
            'auprc': float(selection['auprc']),
            'precision_floor_met': bool(eligible_rows),
            'recall_floor_met': bool(eligible_rows),
            'max_precision': selection['max_precision'],
            'best_precision_threshold': selection['best_precision_threshold'],
            'threshold_metrics': threshold_metrics,
        }
        candidate_results.append(candidate_summary)
        if eligible_rows:
            selected_row = max(eligible_rows, key=lambda row: (float(row['f0_5']), float(row['recall']), float(row['precision'])))
            eligible_results.append({**candidate_summary, 'selected_metrics': selected_row})

    if eligible_results:
        selected = min(
            eligible_results,
            key=lambda item: (
                int(item['opening_size_px']),
                int(item['min_component_area_px']),
                -float(item['selected_metrics']['f0_5']),
            ),
        )
        selected_metrics = dict(selected['selected_metrics'])
        selection_reason = 'precision_floor_and_recall_floor_met'
        precision_floor_met = True
    else:
        selected = max(
            candidate_results,
            key=lambda item: (
                float(item['best_f0_5_metrics']['f0_5']),
                float(item['best_f0_5_metrics']['precision']),
                float(item['best_f0_5_metrics']['recall']),
            ),
        )
        selected_metrics = dict(selected['best_f0_5_metrics'])
        selection_reason = 'best_f0_5_without_precision_and_recall_floor'
        precision_floor_met = False

    selected_metrics['postprocess_opening_size_px'] = int(selected['opening_size_px'])
    selected_metrics['postprocess_min_component_area_px'] = int(selected['min_component_area_px'])
    max_precision_result = max(candidate_results, key=lambda item: float(item['max_precision']))
    return float(selected_metrics['threshold']), {
        'best': selected_metrics,
        'auprc': float(selected['auprc']),
        'threshold_metrics': selected['threshold_metrics'],
        'precision_floor_met': precision_floor_met,
        'max_precision': float(max_precision_result['max_precision']),
        'best_precision_threshold': float(max_precision_result['best_precision_threshold']),
        'postprocess_evaluation': {
            'enabled': True,
            'selection_reason': selection_reason,
            'precision_floor': float(precision_floor),
            'recall_floor': float(recall_floor),
            'selected': {
                'opening_size_px': int(selected['opening_size_px']),
                'min_component_area_px': int(selected['min_component_area_px']),
                'threshold': float(selected_metrics['threshold']),
                'precision': float(selected_metrics['precision']),
                'recall': float(selected_metrics['recall']),
                'f0_5': float(selected_metrics['f0_5']),
            },
            'candidate_count': len(candidate_results),
            'candidates': [
                {
                    'opening_size_px': int(item['opening_size_px']),
                    'min_component_area_px': int(item['min_component_area_px']),
                    'best_threshold': float(item['best_threshold']),
                    'max_precision': float(item['max_precision']),
                    'best_precision_threshold': float(item['best_precision_threshold']),
                    'best_f0_5': float(item['best_f0_5_metrics']['f0_5']),
                    'best_f0_5_threshold': float(item['best_f0_5_metrics']['threshold']),
                    'auprc': float(item['auprc']),
                    'precision_floor_met': bool(item['precision_floor_met']),
                }
                for item in candidate_results
            ],
        },
    }


def _scene_breakdown(
    loader: DataLoader,
    model: nn.Module,
    *,
    device: str,
    threshold: float,
    min_component_area_px: int = 0,
    opening_size_px: int = 0,
) -> list[dict[str, Any]]:
    scene_counts: dict[str, dict[str, int]] = {}
    scene_regions: dict[str, str] = {}
    scene_sources: dict[str, str] = {}
    model.eval()
    with torch.no_grad():
        for batch in loader:
            pre = batch['pre'].to(device)
            post = batch['post'].to(device)
            logits = model(pre, post)
            probabilities = torch.sigmoid(logits).detach().cpu().numpy()[:, 0]
            targets = batch['mask'].detach().cpu().numpy()[:, 0] >= 0.5
            scene_ids = batch['scene_id']
            region_keys = batch.get('region_key') or ['unknown'] * len(scene_ids)
            source_datasets = batch.get('source_dataset') or ['unknown'] * len(scene_ids)
            for index, scene_id in enumerate(scene_ids):
                key = str(scene_id)
                counts = scene_counts.setdefault(key, {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'positive_pixels': 0, 'predicted_pixels': 0, 'total_pixels': 0})
                scene_regions.setdefault(key, str(region_keys[index]))
                scene_sources.setdefault(key, str(source_datasets[index]))
                predictions = probabilities[index] >= threshold
                predictions = _postprocess_binary_mask(
                    predictions,
                    min_component_area_px=min_component_area_px,
                    opening_size_px=opening_size_px,
                )
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
            'region_key': scene_regions.get(scene_id, 'unknown'),
            'source_dataset': scene_sources.get(scene_id, 'unknown'),
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
    threshold_metrics: list[dict[str, Any]] | None = None,
    validation_metrics: dict[str, Any] | None = None,
    precision_floor: float = DEFAULT_PRECISION_FLOOR,
    recall_floor: float | None = None,
    selection_floor_met: bool | None = None,
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
    metric_candidates = [
        row
        for row in (threshold_metrics or [])
        if isinstance(row, dict)
    ]
    if not metric_candidates and isinstance(validation_metrics, dict):
        metric_candidates = [validation_metrics]
    if metric_candidates:
        best_precision = max(
            metric_candidates,
            key=lambda row: (float(row.get('precision') or 0.0), float(row.get('recall') or 0.0)),
        )
        max_precision = float(best_precision.get('precision') or 0.0)
        best_precision_threshold = float(best_precision.get('threshold') or 0.0)
        best_precision_recall = float(best_precision.get('recall') or 0.0)
        selected_metrics = validation_metrics if isinstance(validation_metrics, dict) else best_precision
        selected_precision = float(selected_metrics.get('precision') or 0.0)
        selected_recall = float(selected_metrics.get('recall') or 0.0)
        selected_threshold = float(selected_metrics.get('threshold') or best_precision_threshold)
        max_precision_floor_met = max_precision >= float(precision_floor)
        selected_precision_floor_met = selected_precision >= float(precision_floor)
        selected_recall_floor_met = (
            selected_recall >= float(recall_floor)
            if recall_floor is not None
            else True
        )
        if selection_floor_met is not None:
            combined_floor_met = bool(selection_floor_met)
        elif recall_floor is not None:
            combined_floor_met = any(
                float(row.get('precision') or 0.0) >= float(precision_floor)
                and float(row.get('recall') or 0.0) >= float(recall_floor)
                for row in metric_candidates
            )
        else:
            combined_floor_met = max_precision_floor_met
        precision_floor_met = selected_precision_floor_met
        recall_floor_met = selected_recall_floor_met
    else:
        max_precision = 0.0
        best_precision_threshold = 0.0
        best_precision_recall = 0.0
        selected_precision = 0.0
        selected_recall = 0.0
        selected_threshold = 0.0
        max_precision_floor_met = True
        precision_floor_met = True
        combined_floor_met = True
        recall_floor_met = True
    if not combined_floor_met:
        reason = 'precision_floor_not_met'
        if not bool(precision_floor_met):
            reason = 'precision_floor_not_met'
        elif recall_floor is not None and not bool(recall_floor_met):
            reason = 'recall_floor_not_met'
        elif recall_floor is not None and max_precision_floor_met:
            reason = 'recall_floor_not_met'
        failures.append({
            'scene_id': None,
            'reason': reason,
            'precision_floor': float(precision_floor),
            'recall_floor': float(recall_floor) if recall_floor is not None else None,
            'max_precision': max_precision,
            'best_precision_threshold': best_precision_threshold,
            'best_precision_recall': best_precision_recall,
            'precision_floor_met': bool(precision_floor_met),
            'recall_floor_met': bool(recall_floor_met),
            'joint_floor_met': bool(combined_floor_met),
            'selected_precision': selected_precision,
            'selected_recall': selected_recall,
            'selected_threshold': selected_threshold,
        })
    blocked_gate = None
    if failures:
        reasons = {str(failure.get('reason')) for failure in failures}
        if reasons == {'precision_floor_not_met'}:
            blocked_gate = 'precision_floor'
        elif reasons == {'recall_floor_not_met'}:
            blocked_gate = 'recall_floor'
        elif reasons == {'inflated_positive_rate'}:
            blocked_gate = 'validation_positive_rate'
        else:
            blocked_gate = 'multiple_validation_gates'
    return {
        'passed': not failures,
        'blocked_gate': blocked_gate,
        'failures': failures,
        'precision_floor': float(precision_floor),
        'recall_floor': float(recall_floor) if recall_floor is not None else None,
        'precision_floor_met': bool(precision_floor_met),
        'recall_floor_met': bool(recall_floor_met),
        'joint_floor_met': bool(combined_floor_met),
        'selected_precision': selected_precision,
        'selected_recall': selected_recall,
        'selected_threshold': selected_threshold,
        'max_precision': max_precision,
        'max_precision_floor_met': bool(max_precision_floor_met),
        'best_precision_threshold': best_precision_threshold,
        'best_precision_recall': best_precision_recall,
    }


def _checkpoint_payload(checkpoint_path: Path, *, device: str) -> dict[str, Any]:
    payload = torch.load(checkpoint_path, map_location=device)
    if not isinstance(payload, dict):
        raise RuntimeError('SAR checkpoint payload must be a dictionary')
    return payload


def _checkpoint_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get('metadata')
    return metadata if isinstance(metadata, dict) else {}


def _normalization_from_checkpoint(payload: dict[str, Any]) -> dict[str, torch.Tensor] | None:
    metadata = _checkpoint_metadata(payload)
    normalization = metadata.get('normalization')
    if not isinstance(normalization, dict):
        return None
    mean = normalization.get('img_mean')
    std = normalization.get('img_std')
    if mean is None or std is None:
        return None
    return {
        'img_mean': torch.as_tensor(mean, dtype=torch.float32),
        'img_std': torch.clamp(torch.as_tensor(std, dtype=torch.float32), min=1e-6),
    }


def _load_strict_checkpoint_model(
    *,
    checkpoint_path: Path,
    model_family: str,
    patch_size: int,
    device: str,
) -> tuple[nn.Module, dict[str, Any]]:
    payload = _checkpoint_payload(checkpoint_path, device=device)
    model = build_model_architecture(model_family, image_size=patch_size).to(device)
    state_dict = _state_dict_from_payload(payload)
    load_result = model.load_state_dict(state_dict, strict=True)
    if getattr(load_result, 'missing_keys', None) or getattr(load_result, 'unexpected_keys', None):
        raise RuntimeError('SAR checkpoint failed strict validation load')
    return model, payload


def _checkpoint_path_from_request(request: dict[str, Any]) -> Path:
    raw_path = (
        request.get('checkpoint_path')
        or request.get('model_checkpoint_path')
        or request.get('initial_checkpoint_path')
    )
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError('SAR checkpoint evaluation requires checkpoint_path, model_checkpoint_path, or initial_checkpoint_path')
    checkpoint_path = Path(raw_path.strip()).expanduser()
    if not checkpoint_path.exists():
        raise FileNotFoundError(f'SAR checkpoint not found: {checkpoint_path}')
    return checkpoint_path


def _dataset_for_checkpoint_evaluation(
    request: dict[str, Any],
    *,
    artifact_dir: Path,
    config: TrainingConfig,
    checkpoint_payload: dict[str, Any],
) -> tuple[dict[str, Any], Path, SarPatchDataset, SarPatchDataset | None, dict[str, torch.Tensor]]:
    training_manifest_source = request.get('training_manifest') or request.get('training_manifest_path')
    if not training_manifest_source:
        raise ValueError('SAR checkpoint evaluation requires training_manifest or training_manifest_path')
    dataset_root = _materialized_dataset_root(request, artifact_dir)
    dataset_audit = materialize_sar_training_dataset(
        manifest_source=training_manifest_source,
        output_root=dataset_root,
        patch_size=config.patch_size,
        stride=config.stride,
    )
    train_dataset: SarPatchDataset | None = None
    normalization = _normalization_from_checkpoint(checkpoint_payload)
    if normalization is None:
        train_dataset = SarPatchDataset(dataset_root, split='train', augment=False)
        normalization = compute_sar_normalization(train_dataset)
    val_dataset = SarPatchDataset(dataset_root, split='val', normalization=normalization, augment=False)
    return dataset_audit, dataset_root, val_dataset, train_dataset, normalization


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
    postprocess: PostprocessConfig | None = None,
) -> dict[str, Any]:
    model.eval()
    candidates = _postprocess_candidates(postprocess)
    counts_by_candidate = {
        (int(candidate['opening_size_px']), int(candidate['min_component_area_px'])): _build_counts_template(threshold_grid)
        for candidate in candidates
    }
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
                for (opening_size_px, min_component_area_px), threshold_counts in counts_by_candidate.items():
                    _update_threshold_counts(
                        threshold_counts,
                        probabilities[index],
                        targets[index],
                        min_component_area_px=min_component_area_px,
                        opening_size_px=opening_size_px,
                    )
            batch_size = int(mask.shape[0])
            running_loss += float(loss.item()) * batch_size
            seen += batch_size
    if postprocess is not None and postprocess.enabled and postprocess.apply_to_threshold_selection:
        best_threshold, selection = _select_best_postprocessed_threshold(
            counts_by_candidate,
            f_beta=f_beta,
            precision_floor=precision_floor,
            recall_floor=postprocess.recall_floor,
        )
    else:
        threshold_counts = counts_by_candidate[(0, 0)]
        best_threshold, selection = _select_best_threshold(
            threshold_counts,
            f_beta=f_beta,
            precision_floor=precision_floor,
        )
        selection['postprocess_evaluation'] = {
            'enabled': False,
            'selection_reason': 'disabled',
            'precision_floor': float(precision_floor),
            'recall_floor': float(postprocess.recall_floor if postprocess is not None else DEFAULT_POSTPROCESS_RECALL_FLOOR),
            'selected': {
                'opening_size_px': 0,
                'min_component_area_px': 0,
                'threshold': float(best_threshold),
                'precision': float(selection['best']['precision']),
                'recall': float(selection['best']['recall']),
                'f0_5': float(selection['best']['f0_5']),
            },
            'candidate_count': 1,
            'candidates': [],
        }
    return {
        'loss': running_loss / max(seen, 1),
        'best_threshold': best_threshold,
        'auprc': float(selection['auprc']),
        'best_metrics': selection['best'],
        'threshold_metrics': selection['threshold_metrics'],
        'postprocess_evaluation': selection['postprocess_evaluation'],
        'precision_floor_met': bool(selection['precision_floor_met']),
        'max_precision': float(selection['max_precision']),
        'best_precision_threshold': float(selection['best_precision_threshold']),
    }


def _training_config_from_request(request: dict[str, Any]) -> TrainingConfig:
    model_family = normalize_model_family(str(request.get('model_family') or 'swinunet_tiny_diff'))
    patch_size = int(request.get('patch_size') or 128)
    stride = int(request.get('stride') or 64)
    candidate_model_version = str(request.get('candidate_model_version') or f'{model_family}_shadow_candidate_{_timestamp_slug()}')
    threshold_grid = np.asarray(request.get('threshold_grid') or DEFAULT_THRESHOLD_GRID.tolist(), dtype=np.float32)
    postprocess = PostprocessConfig(
        min_component_area_px=max(0, int(request.get('postprocess_min_component_area_px') or 0)),
        opening_size_px=max(0, int(request.get('postprocess_opening_size_px') or 0)),
        apply_to_threshold_selection=bool(request.get('postprocess_apply_to_threshold_selection')),
        recall_floor=float(request.get('postprocess_recall_floor') or DEFAULT_POSTPROCESS_RECALL_FLOOR),
    )
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
        focal_tversky_alpha=float(request.get('focal_tversky_alpha') or 0.7),
        focal_tversky_beta=float(request.get('focal_tversky_beta') or 0.3),
        focal_tversky_gamma=float(request.get('focal_tversky_gamma') or 1.33),
        postprocess=postprocess,
    )


def _materialized_dataset_root(request: dict[str, Any], artifact_dir: Path) -> Path:
    raw_root = request.get('materialized_dataset_root')
    if not isinstance(raw_root, str) or not raw_root.strip():
        return artifact_dir / 'sar_training_dataset'
    candidate = Path(raw_root.strip()).expanduser()
    if candidate.is_absolute():
        return candidate
    return artifact_dir / candidate


def _source_key_from_dataset_audit(dataset_audit: dict[str, Any]) -> str | None:
    source_counts = dataset_audit.get('source_dataset_scene_counts')
    if isinstance(source_counts, dict) and len(source_counts) == 1:
        return str(next(iter(source_counts))).strip() or None
    return None


def _region_metrics(scene_breakdown: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    region_counts: dict[str, dict[str, int]] = {}
    for scene in scene_breakdown:
        region = str(scene.get('region_key') or 'unknown')
        counts = region_counts.setdefault(region, {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0})
        for key in counts:
            counts[key] += int(scene.get(key) or 0)
    return {
        region: _metrics_from_counts(counts)
        for region, counts in sorted(region_counts.items())
    }


def _build_validation_prediction_artifact(
    *,
    request: dict[str, Any],
    config: TrainingConfig,
    dataset_audit: dict[str, Any],
    best_validation: dict[str, Any],
    scene_breakdown: list[dict[str, Any]],
    quality_gate: dict[str, Any],
    evaluation_mode: str = 'patch_level',
) -> dict[str, Any]:
    source_key = str(request.get('source_key') or '').strip() or _source_key_from_dataset_audit(dataset_audit)
    metrics = best_validation['best_metrics']
    return {
        'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
        'source_key': source_key,
        'dataset_version': dataset_audit['dataset_version'],
        'model_family': config.model_family,
        'model_version': config.candidate_model_version,
        'candidate_model_version': config.candidate_model_version,
        'evaluation_mode': evaluation_mode,
        'split': 'val',
        'threshold': float(best_validation['best_threshold']),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'license_review_id': str(request.get('license_review_id') or '').strip() or None,
        'status': 'computed',
        'metrics': {
            'threshold': float(best_validation['best_threshold']),
            'auprc': float(best_validation['auprc']),
            **metrics,
        },
        'postprocess_evaluation': best_validation.get('postprocess_evaluation'),
        'scene_breakdown': scene_breakdown,
        'region_breakdown': _region_metrics(scene_breakdown),
        'evaluated_scene_ids': dataset_audit['val_events'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
        'quality_gate': quality_gate,
    }


def evaluate_sar_checkpoint(
    request: dict[str, Any],
    *,
    artifact_root: Path,
    device: str = 'cpu',
) -> dict[str, Any]:
    if not torch:
        raise RuntimeError('torch is required for SAR checkpoint evaluation')
    checkpoint_path = _checkpoint_path_from_request(request)
    config = _training_config_from_request(request)
    artifact_dir = create_artifact_dir(artifact_root)
    model, checkpoint_payload = _load_strict_checkpoint_model(
        checkpoint_path=checkpoint_path,
        model_family=config.model_family,
        patch_size=config.patch_size,
        device=device,
    )
    dataset_audit, dataset_root, val_dataset, _train_dataset, normalization = _dataset_for_checkpoint_evaluation(
        request,
        artifact_dir=artifact_dir,
        config=config,
        checkpoint_payload=checkpoint_payload,
    )
    val_loader = DataLoader(val_dataset, batch_size=max(1, config.batch_size), shuffle=False, num_workers=0)
    criterion = _loss_from_name(
        config.loss_name,
        focal_tversky_alpha=config.focal_tversky_alpha,
        focal_tversky_beta=config.focal_tversky_beta,
        focal_tversky_gamma=config.focal_tversky_gamma,
    ).to(device)
    validation = _validate(
        val_loader,
        model,
        device=device,
        criterion=criterion,
        threshold_grid=config.threshold_grid,
        f_beta=config.f_beta,
        precision_floor=config.precision_floor,
        postprocess=config.postprocess,
    )
    scene_breakdown = _scene_breakdown(
        val_loader,
        model,
        device=device,
        threshold=float(validation['best_threshold']),
        min_component_area_px=int(validation['best_metrics'].get('postprocess_min_component_area_px') or 0),
        opening_size_px=int(validation['best_metrics'].get('postprocess_opening_size_px') or 0),
    )
    quality_gate = _validation_quality_gate(
        scene_breakdown,
        max_positive_rate_ratio=config.max_validation_positive_rate_ratio,
        max_positive_rate_absolute=config.max_validation_positive_rate_absolute,
        threshold_metrics=validation['threshold_metrics'],
        validation_metrics=validation['best_metrics'],
        precision_floor=config.precision_floor,
        recall_floor=(
            config.postprocess.recall_floor
            if config.postprocess is not None
            and config.postprocess.enabled
            and config.postprocess.apply_to_threshold_selection
            else None
        ),
        selection_floor_met=validation.get('precision_floor_met'),
    )
    metrics_payload = {
        'status': 'ok' if quality_gate['passed'] else 'completed_with_validation_gate_failure',
        'request_type': 'evaluate_sar_checkpoint',
        'evaluation_mode': 'patch_level',
        'model_family': config.model_family,
        'candidate_model_version': config.candidate_model_version,
        'checkpoint_path': str(checkpoint_path),
        'dataset_version': dataset_audit['dataset_version'],
        'epochs_completed': 0,
        'epochs_requested': 0,
        'loss': config.loss_name,
        'patch_size': config.patch_size,
        'stride': config.stride,
        'best_threshold': float(validation['best_threshold']),
        'validation_metrics': validation['best_metrics'],
        'validation_auprc': float(validation['auprc']),
        'threshold_metrics': validation['threshold_metrics'],
        'postprocess_evaluation': validation['postprocess_evaluation'],
        'scene_breakdown': scene_breakdown,
        'quality_gate': quality_gate,
        'dataset_audit': dataset_audit,
        'materialized_dataset_root': str(dataset_root),
        'normalization_source': 'checkpoint' if _normalization_from_checkpoint(checkpoint_payload) is not None else 'train_split',
        'normalization': {
            'img_mean': normalization['img_mean'].tolist(),
            'img_std': normalization['img_std'].tolist(),
        },
    }
    prediction_artifact_path: str | None = None
    if bool(request.get('export_validation_prediction_artifact')):
        prediction_artifact = _build_validation_prediction_artifact(
            request=request,
            config=config,
            dataset_audit=dataset_audit,
            best_validation=validation,
            scene_breakdown=scene_breakdown,
            quality_gate=quality_gate,
        )
        prediction_artifact_path = str(artifact_dir / 'european_sar_prediction_artifact.json')
        dump_json(Path(prediction_artifact_path), prediction_artifact)
        metrics_payload['sar_prediction_artifact_path'] = prediction_artifact_path
        metrics_payload['sar_prediction_artifact'] = prediction_artifact
    dump_json(artifact_dir / 'sar_training_metrics.json', metrics_payload)
    report = {
        'status': metrics_payload['status'],
        'request_type': 'evaluate_sar_checkpoint',
        'evaluation_mode': 'patch_level',
        'artifact_dir': str(artifact_dir),
        'candidate_model_version': config.candidate_model_version,
        'model_family': config.model_family,
        'checkpoint_path': str(checkpoint_path),
        'best_threshold': float(validation['best_threshold']),
        'validation_auprc': float(validation['auprc']),
        'validation_metrics': validation['best_metrics'],
        'postprocess_evaluation': validation['postprocess_evaluation'],
        'quality_gate_passed': bool(quality_gate['passed']),
        'blocked_gate': quality_gate['blocked_gate'],
        'scene_gate_failures': quality_gate['failures'],
        'dataset_version': dataset_audit['dataset_version'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
        'materialized_dataset_root': str(dataset_root),
    }
    if prediction_artifact_path is not None:
        report['sar_prediction_artifact_path'] = prediction_artifact_path
    dump_json(artifact_dir / 'evaluate_sar_checkpoint_manifest.json', report)
    return report


def _audit_from_sar_training_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    scenes = [scene for scene in manifest.get('scenes', []) if isinstance(scene, dict)]
    train_scenes = [scene for scene in scenes if str(scene.get('split') or '').strip().lower() == 'train']
    val_scenes = [scene for scene in scenes if str(scene.get('split') or '').strip().lower() == 'val']
    source_counts: dict[str, int] = {}
    region_counts: dict[str, int] = {}
    for scene in scenes:
        source = str(scene.get('source_dataset') or 'unknown').strip() or 'unknown'
        region = str(scene.get('region_key') or 'unknown').strip() or 'unknown'
        source_counts[source] = source_counts.get(source, 0) + 1
        region_counts[region] = region_counts.get(region, 0) + 1
    return {
        'dataset_version': str(manifest.get('dataset_version') or 'sar-training-v1'),
        'train_scene_count': len(train_scenes),
        'val_scene_count': len(val_scenes),
        'scene_count': len(scenes),
        'train_events': sorted(str(scene.get('scene_id') or '') for scene in train_scenes if scene.get('scene_id')),
        'val_events': sorted(str(scene.get('scene_id') or '') for scene in val_scenes if scene.get('scene_id')),
        'source_dataset_scene_counts': dict(sorted(source_counts.items())),
        'region_scene_counts': dict(sorted(region_counts.items())),
    }


def _finalize_threshold_selection(
    counts_by_candidate: dict[tuple[int, int], dict[float, dict[str, int]]],
    *,
    config: TrainingConfig,
) -> dict[str, Any]:
    if config.postprocess is not None and config.postprocess.enabled and config.postprocess.apply_to_threshold_selection:
        best_threshold, selection = _select_best_postprocessed_threshold(
            counts_by_candidate,
            f_beta=config.f_beta,
            precision_floor=config.precision_floor,
            recall_floor=config.postprocess.recall_floor,
        )
    else:
        threshold_counts = counts_by_candidate[(0, 0)]
        best_threshold, selection = _select_best_threshold(
            threshold_counts,
            f_beta=config.f_beta,
            precision_floor=config.precision_floor,
        )
        selection['postprocess_evaluation'] = {
            'enabled': False,
            'selection_reason': 'disabled',
            'precision_floor': float(config.precision_floor),
            'recall_floor': float(config.postprocess.recall_floor if config.postprocess is not None else DEFAULT_POSTPROCESS_RECALL_FLOOR),
            'selected': {
                'opening_size_px': 0,
                'min_component_area_px': 0,
                'threshold': float(best_threshold),
                'precision': float(selection['best']['precision']),
                'recall': float(selection['best']['recall']),
                'f0_5': float(selection['best']['f0_5']),
            },
            'candidate_count': 1,
            'candidates': [],
        }
    return {
        'best_threshold': float(best_threshold),
        'auprc': float(selection['auprc']),
        'best_metrics': selection['best'],
        'threshold_metrics': selection['threshold_metrics'],
        'postprocess_evaluation': selection['postprocess_evaluation'],
        'precision_floor_met': bool(selection['precision_floor_met']),
        'max_precision': float(selection['max_precision']),
        'best_precision_threshold': float(selection['best_precision_threshold']),
    }


def _scene_blended_scene_breakdown(
    evaluated_scenes: list[dict[str, Any]],
    *,
    threshold: float,
    min_component_area_px: int,
    opening_size_px: int,
) -> list[dict[str, Any]]:
    breakdown: list[dict[str, Any]] = []
    for item in evaluated_scenes:
        probabilities = np.asarray(item['probabilities'], dtype=np.float32)
        target = np.asarray(item['truth'], dtype=bool)
        prediction = probabilities >= float(threshold)
        prediction = _postprocess_binary_mask(
            prediction,
            min_component_area_px=min_component_area_px,
            opening_size_px=opening_size_px,
        )
        counts = {
            'tp': int(np.sum(prediction & target)),
            'fp': int(np.sum(prediction & ~target)),
            'fn': int(np.sum(~prediction & target)),
            'tn': int(np.sum(~prediction & ~target)),
        }
        metrics = _metrics_from_counts(counts)
        positive_pixels = int(np.sum(target))
        predicted_pixels = int(np.sum(prediction))
        total_pixels = int(target.size)
        truth_positive_rate = positive_pixels / max(total_pixels, 1)
        predicted_positive_rate = predicted_pixels / max(total_pixels, 1)
        positive_rate_ratio = predicted_positive_rate / max(truth_positive_rate, 1e-6)
        scene = item['scene']
        breakdown.append({
            'scene_id': str(scene.get('scene_id') or ''),
            'region_key': str(scene.get('region_key') or 'unknown'),
            'source_dataset': str(scene.get('source_dataset') or 'unknown'),
            **metrics,
            'positive_pixels': positive_pixels,
            'predicted_pixels': predicted_pixels,
            'total_pixels': total_pixels,
            'truth_positive_rate': float(truth_positive_rate),
            'predicted_positive_rate': float(predicted_positive_rate),
            'positive_rate_ratio': float(positive_rate_ratio),
        })
    return sorted(breakdown, key=lambda row: str(row['scene_id']))


def evaluate_sar_checkpoint_scene_blended(
    request: dict[str, Any],
    *,
    artifact_root: Path,
    device: str = 'cpu',
) -> dict[str, Any]:
    if not torch:
        raise RuntimeError('torch is required for SAR checkpoint evaluation')
    checkpoint_path = _checkpoint_path_from_request(request)
    config = _training_config_from_request(request)
    training_manifest_source = request.get('training_manifest') or request.get('training_manifest_path')
    if not training_manifest_source:
        raise ValueError('SAR scene-blended checkpoint evaluation requires training_manifest or training_manifest_path')

    from backend.sar_unet_worker import build_unet_model, predict_scene_probability_mask

    artifact_dir = create_artifact_dir(artifact_root)
    manifest = load_sar_training_manifest(training_manifest_source)
    dataset_audit = _audit_from_sar_training_manifest(manifest)
    val_scenes = [
        scene for scene in manifest['scenes']
        if str(scene.get('split') or '').strip().lower() == 'val'
    ]
    if not val_scenes:
        raise ValueError('SAR scene-blended checkpoint evaluation requires at least one val scene')

    loaded_model = build_unet_model(
        checkpoint_path,
        device=device,
        model_family=config.model_family,
        image_size=config.patch_size,
        promoted=True,
    )
    candidates = _postprocess_candidates(config.postprocess)
    counts_by_candidate = {
        (int(candidate['opening_size_px']), int(candidate['min_component_area_px'])): _build_counts_template(config.threshold_grid)
        for candidate in candidates
    }
    evaluated_scenes: list[dict[str, Any]] = []
    for scene in val_scenes:
        probabilities = predict_scene_probability_mask(loaded_model, scene, device=device)
        truth = _load_truth_mask_from_ref(str(scene['truth_mask_ref'])) >= 0.5
        if probabilities.shape != truth.shape:
            raise ValueError(
                f'scene "{scene.get("scene_id")}" prediction/truth shape mismatch: '
                f'{probabilities.shape} vs {truth.shape}',
            )
        for (opening_size_px, min_component_area_px), threshold_counts in counts_by_candidate.items():
            _update_threshold_counts(
                threshold_counts,
                probabilities,
                truth,
                min_component_area_px=min_component_area_px,
                opening_size_px=opening_size_px,
            )
        evaluated_scenes.append({
            'scene': scene,
            'probabilities': probabilities,
            'truth': truth,
        })

    validation = _finalize_threshold_selection(counts_by_candidate, config=config)
    selected_metrics = validation['best_metrics']
    scene_breakdown = _scene_blended_scene_breakdown(
        evaluated_scenes,
        threshold=float(validation['best_threshold']),
        min_component_area_px=int(selected_metrics.get('postprocess_min_component_area_px') or 0),
        opening_size_px=int(selected_metrics.get('postprocess_opening_size_px') or 0),
    )
    quality_gate = _validation_quality_gate(
        scene_breakdown,
        max_positive_rate_ratio=config.max_validation_positive_rate_ratio,
        max_positive_rate_absolute=config.max_validation_positive_rate_absolute,
        threshold_metrics=validation['threshold_metrics'],
        validation_metrics=validation['best_metrics'],
        precision_floor=config.precision_floor,
        recall_floor=(
            config.postprocess.recall_floor
            if config.postprocess is not None
            and config.postprocess.enabled
            and config.postprocess.apply_to_threshold_selection
            else None
        ),
        selection_floor_met=validation.get('precision_floor_met'),
    )
    status = 'ok' if quality_gate['passed'] else 'completed_with_validation_gate_failure'
    metrics_payload = {
        'status': status,
        'request_type': 'evaluate_sar_checkpoint',
        'evaluation_mode': 'scene_blended',
        'model_family': config.model_family,
        'candidate_model_version': config.candidate_model_version,
        'checkpoint_path': str(checkpoint_path),
        'dataset_version': dataset_audit['dataset_version'],
        'epochs_completed': 0,
        'epochs_requested': 0,
        'loss': config.loss_name,
        'patch_size': config.patch_size,
        'stride': config.stride,
        'best_threshold': float(validation['best_threshold']),
        'validation_metrics': validation['best_metrics'],
        'validation_auprc': float(validation['auprc']),
        'threshold_metrics': validation['threshold_metrics'],
        'postprocess_evaluation': validation['postprocess_evaluation'],
        'scene_breakdown': scene_breakdown,
        'region_breakdown': _region_metrics(scene_breakdown),
        'quality_gate': quality_gate,
        'dataset_audit': dataset_audit,
        'training_manifest_path': str(training_manifest_source),
        'normalization_source': 'checkpoint' if loaded_model.normalization is not None else 'none',
    }
    prediction_artifact_path: str | None = None
    if bool(request.get('export_validation_prediction_artifact')):
        prediction_artifact = _build_validation_prediction_artifact(
            request=request,
            config=config,
            dataset_audit=dataset_audit,
            best_validation=validation,
            scene_breakdown=scene_breakdown,
            quality_gate=quality_gate,
            evaluation_mode='scene_blended',
        )
        prediction_artifact_path = str(artifact_dir / 'european_sar_prediction_artifact.json')
        dump_json(Path(prediction_artifact_path), prediction_artifact)
        metrics_payload['sar_prediction_artifact_path'] = prediction_artifact_path
        metrics_payload['sar_prediction_artifact'] = prediction_artifact
    dump_json(artifact_dir / 'sar_training_metrics.json', metrics_payload)
    report = {
        'status': status,
        'request_type': 'evaluate_sar_checkpoint',
        'evaluation_mode': 'scene_blended',
        'artifact_dir': str(artifact_dir),
        'candidate_model_version': config.candidate_model_version,
        'model_family': config.model_family,
        'checkpoint_path': str(checkpoint_path),
        'best_threshold': float(validation['best_threshold']),
        'validation_auprc': float(validation['auprc']),
        'validation_metrics': validation['best_metrics'],
        'postprocess_evaluation': validation['postprocess_evaluation'],
        'quality_gate_passed': bool(quality_gate['passed']),
        'blocked_gate': quality_gate['blocked_gate'],
        'scene_gate_failures': quality_gate['failures'],
        'dataset_version': dataset_audit['dataset_version'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
    }
    if prediction_artifact_path is not None:
        report['sar_prediction_artifact_path'] = prediction_artifact_path
    dump_json(artifact_dir / 'evaluate_sar_checkpoint_scene_blended_manifest.json', report)
    return report


def build_sar_validation_error_diagnostics(
    request: dict[str, Any],
    *,
    artifact_root: Path,
    device: str = 'cpu',
    max_components: int = 10,
) -> dict[str, Any]:
    checkpoint_path = _checkpoint_path_from_request(request)
    config = _training_config_from_request(request)
    artifact_dir = create_artifact_dir(artifact_root)
    model, checkpoint_payload = _load_strict_checkpoint_model(
        checkpoint_path=checkpoint_path,
        model_family=config.model_family,
        patch_size=config.patch_size,
        device=device,
    )
    dataset_audit, dataset_root, val_dataset, _train_dataset, _normalization = _dataset_for_checkpoint_evaluation(
        request,
        artifact_dir=artifact_dir,
        config=config,
        checkpoint_payload=checkpoint_payload,
    )
    threshold = float(request.get('threshold') or request.get('best_threshold') or 0.5)
    min_component_area_px = int(request.get('postprocess_min_component_area_px') or 0)
    opening_size_px = int(request.get('postprocess_opening_size_px') or 0)
    loader = DataLoader(val_dataset, batch_size=max(1, config.batch_size), shuffle=False, num_workers=0)
    scene_counts: dict[str, dict[str, Any]] = {}
    largest_fn_components: list[dict[str, Any]] = []
    largest_fp_components: list[dict[str, Any]] = []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            pre = batch['pre'].to(device)
            post = batch['post'].to(device)
            logits = model(pre, post)
            probabilities = torch.sigmoid(logits).detach().cpu().numpy()[:, 0]
            targets = batch['mask'].detach().cpu().numpy()[:, 0] >= 0.5
            scene_ids = batch['scene_id']
            patch_ids = batch['patch_id']
            region_keys = batch.get('region_key') or ['unknown'] * len(scene_ids)
            for index, scene_id_value in enumerate(scene_ids):
                scene_id = str(scene_id_value)
                patch_id = str(patch_ids[index])
                target = targets[index]
                prediction = probabilities[index] >= threshold
                prediction = _postprocess_binary_mask(
                    prediction,
                    min_component_area_px=min_component_area_px,
                    opening_size_px=opening_size_px,
                )
                false_negative = ~prediction & target
                false_positive = prediction & ~target
                stats = scene_counts.setdefault(scene_id, {
                    'scene_id': scene_id,
                    'region_key': str(region_keys[index]),
                    'tp': 0,
                    'fp': 0,
                    'fn': 0,
                    'tn': 0,
                    'positive_pixels': 0,
                    'predicted_pixels': 0,
                    'total_pixels': 0,
                    'patch_count': 0,
                    'patches_with_false_negatives': 0,
                    'patches_with_false_positives': 0,
                })
                tp = int(np.sum(prediction & target))
                fp = int(np.sum(false_positive))
                fn = int(np.sum(false_negative))
                tn = int(np.sum(~prediction & ~target))
                stats['tp'] += tp
                stats['fp'] += fp
                stats['fn'] += fn
                stats['tn'] += tn
                stats['positive_pixels'] += int(np.sum(target))
                stats['predicted_pixels'] += int(np.sum(prediction))
                stats['total_pixels'] += int(target.size)
                stats['patch_count'] += 1
                stats['patches_with_false_negatives'] += int(fn > 0)
                stats['patches_with_false_positives'] += int(fp > 0)
                largest_fn_components.extend(_component_summaries(
                    false_negative,
                    scene_id=scene_id,
                    patch_id=patch_id,
                    component_type='false_negative',
                    limit=max_components,
                ))
                largest_fp_components.extend(_component_summaries(
                    false_positive,
                    scene_id=scene_id,
                    patch_id=patch_id,
                    component_type='false_positive',
                    limit=max_components,
                ))
    scene_diagnostics: list[dict[str, Any]] = []
    for stats in scene_counts.values():
        metrics = _metrics_from_counts({key: int(stats[key]) for key in ('tp', 'fp', 'fn', 'tn')})
        positive_pixels = int(stats['positive_pixels'])
        predicted_pixels = int(stats['predicted_pixels'])
        total_pixels = int(stats['total_pixels'])
        scene_diagnostics.append({
            **stats,
            **metrics,
            'false_negative_share_of_truth': int(stats['fn']) / max(positive_pixels, 1),
            'false_positive_share_of_predictions': int(stats['fp']) / max(predicted_pixels, 1),
            'truth_positive_rate': positive_pixels / max(total_pixels, 1),
            'predicted_positive_rate': predicted_pixels / max(total_pixels, 1),
        })
    scene_diagnostics = sorted(scene_diagnostics, key=lambda row: (int(row['fn']), int(row['fp'])), reverse=True)
    largest_fn_components = sorted(largest_fn_components, key=lambda row: row['pixel_count'], reverse=True)[:max_components]
    largest_fp_components = sorted(largest_fp_components, key=lambda row: row['pixel_count'], reverse=True)[:max_components]
    aggregate = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
    for scene in scene_diagnostics:
        for key in aggregate:
            aggregate[key] += int(scene[key])
    metrics = _metrics_from_counts(aggregate)
    precision_floor = float(request.get('precision_floor') or config.precision_floor)
    recall_floor = float(request.get('postprocess_recall_floor') or DEFAULT_POSTPROCESS_RECALL_FLOOR)
    recommended_next_step = (
        'lower_threshold_or_recall_balanced_finetune'
        if metrics['precision'] >= precision_floor and metrics['recall'] < recall_floor
        else 'precision_first_diagnostics'
        if metrics['precision'] < precision_floor
        else 'eligible_for_heldout_check'
    )
    diagnostics = {
        'version': SAR_VALIDATION_ERROR_DIAGNOSTICS_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'model_family': config.model_family,
        'model_version': config.candidate_model_version,
        'checkpoint_path': str(checkpoint_path),
        'dataset_version': dataset_audit['dataset_version'],
        'threshold': threshold,
        'postprocess_min_component_area_px': min_component_area_px,
        'postprocess_opening_size_px': opening_size_px,
        'precision_floor': precision_floor,
        'recall_floor': recall_floor,
        'metrics': metrics,
        'recommended_next_step': recommended_next_step,
        'scene_diagnostics': scene_diagnostics,
        'largest_false_negative_components': largest_fn_components,
        'largest_false_positive_components': largest_fp_components,
        'materialized_dataset_root': str(dataset_root),
    }
    dump_json(artifact_dir / 'sar_validation_error_diagnostics.json', diagnostics)
    manifest = {
        'status': 'ok',
        'request_type': 'sar_validation_error_diagnostics',
        'artifact_dir': str(artifact_dir),
        'diagnostics_path': str(artifact_dir / 'sar_validation_error_diagnostics.json'),
        'model_version': config.candidate_model_version,
        'threshold': threshold,
        'metrics': metrics,
        'recommended_next_step': recommended_next_step,
    }
    dump_json(artifact_dir / 'sar_validation_error_diagnostics_manifest.json', manifest)
    return manifest


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
    dataset_root = _materialized_dataset_root(request, artifact_dir)
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
    criterion = _loss_from_name(
        config.loss_name,
        focal_tversky_alpha=config.focal_tversky_alpha,
        focal_tversky_beta=config.focal_tversky_beta,
        focal_tversky_gamma=config.focal_tversky_gamma,
    ).to(device)
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
            postprocess=config.postprocess,
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
        min_component_area_px=int(best_validation['best_metrics'].get('postprocess_min_component_area_px') or 0),
        opening_size_px=int(best_validation['best_metrics'].get('postprocess_opening_size_px') or 0),
    )
    quality_gate = _validation_quality_gate(
        scene_breakdown,
        max_positive_rate_ratio=config.max_validation_positive_rate_ratio,
        max_positive_rate_absolute=config.max_validation_positive_rate_absolute,
        threshold_metrics=best_validation['threshold_metrics'],
        validation_metrics=best_validation['best_metrics'],
        precision_floor=config.precision_floor,
        recall_floor=(
            config.postprocess.recall_floor
            if config.postprocess is not None
            and config.postprocess.enabled
            and config.postprocess.apply_to_threshold_selection
            else None
        ),
        selection_floor_met=best_validation.get('precision_floor_met'),
    )
    checkpoint_metadata = {
        'model_family': config.model_family,
        'candidate_model_version': config.candidate_model_version,
        'dataset_version': dataset_audit['dataset_version'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
        'loss': config.loss_name,
        'loss_parameters': {
            'focal_tversky_alpha': config.focal_tversky_alpha,
            'focal_tversky_beta': config.focal_tversky_beta,
            'focal_tversky_gamma': config.focal_tversky_gamma,
        },
        'best_threshold': float(best_validation['best_threshold']),
        'validation_metrics': best_validation['best_metrics'],
        'validation_auprc': float(best_validation['auprc']),
        'postprocess_evaluation': best_validation['postprocess_evaluation'],
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

    status = 'ok' if quality_gate['passed'] else 'completed_with_validation_gate_failure'
    metrics_payload = {
        'status': status,
        'evaluation_mode': 'patch_level',
        'candidate_model_version': config.candidate_model_version,
        'model_family': config.model_family,
        'patch_size': config.patch_size,
        'stride': config.stride,
        'epochs_requested': config.epochs,
        'epochs_completed': len(train_loss_history),
        'loss': config.loss_name,
        'loss_parameters': {
            'focal_tversky_alpha': config.focal_tversky_alpha,
            'focal_tversky_beta': config.focal_tversky_beta,
            'focal_tversky_gamma': config.focal_tversky_gamma,
        },
        'best_threshold': float(best_validation['best_threshold']),
        'validation_auprc': float(best_validation['auprc']),
        'validation_metrics': best_validation['best_metrics'],
        'threshold_metrics': best_validation['threshold_metrics'],
        'postprocess_evaluation': best_validation['postprocess_evaluation'],
        'scene_breakdown': scene_breakdown,
        'quality_gate': quality_gate,
        'train_loss_history': train_loss_history,
        'val_loss_history': val_loss_history,
        'dataset_audit': dataset_audit,
        'materialized_dataset_root': str(dataset_root),
        'initial_checkpoint': initial_checkpoint,
        'model_checkpoint_path': str(checkpoint_path),
    }
    prediction_artifact_path: str | None = None
    if bool(request.get('export_validation_prediction_artifact')):
        prediction_artifact = _build_validation_prediction_artifact(
            request=request,
            config=config,
            dataset_audit=dataset_audit,
            best_validation=best_validation,
            scene_breakdown=scene_breakdown,
            quality_gate=quality_gate,
        )
        prediction_artifact_path = str(artifact_dir / 'european_sar_prediction_artifact.json')
        dump_json(Path(prediction_artifact_path), prediction_artifact)
        metrics_payload['sar_prediction_artifact_path'] = prediction_artifact_path
        metrics_payload['sar_prediction_artifact'] = prediction_artifact
    dump_json(artifact_dir / 'sar_training_metrics.json', metrics_payload)
    report = {
        'status': status,
        'request_type': 'train_sar_unet',
        'evaluation_mode': 'patch_level',
        'artifact_dir': str(artifact_dir),
        'candidate_model_version': config.candidate_model_version,
        'model_family': config.model_family,
        'model_checkpoint_path': str(checkpoint_path),
        'best_threshold': float(best_validation['best_threshold']),
        'validation_auprc': float(best_validation['auprc']),
        'validation_metrics': best_validation['best_metrics'],
        'postprocess_evaluation': best_validation['postprocess_evaluation'],
        'quality_gate_passed': bool(quality_gate['passed']),
        'blocked_gate': quality_gate['blocked_gate'],
        'scene_gate_failures': quality_gate['failures'],
        'dataset_version': dataset_audit['dataset_version'],
        'train_events': dataset_audit['train_events'],
        'val_events': dataset_audit['val_events'],
        'materialized_dataset_root': str(dataset_root),
    }
    if prediction_artifact_path is not None:
        report['sar_prediction_artifact_path'] = prediction_artifact_path
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
    for arg_name in (
        'focal_tversky_alpha',
        'focal_tversky_beta',
        'focal_tversky_gamma',
        'postprocess_min_component_area_px',
        'postprocess_opening_size_px',
        'postprocess_recall_floor',
    ):
        if hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                request[arg_name] = value
    if getattr(args, 'postprocess_apply_to_threshold_selection', False):
        request['postprocess_apply_to_threshold_selection'] = True
    if args.initial_checkpoint_path:
        request['initial_checkpoint_path'] = str(args.initial_checkpoint_path)
    if getattr(args, 'materialized_dataset_root', None):
        request['materialized_dataset_root'] = str(args.materialized_dataset_root)
    if getattr(args, 'source_key', None):
        request['source_key'] = str(args.source_key)
    if getattr(args, 'license_review_id', None):
        request['license_review_id'] = str(args.license_review_id)
    if getattr(args, 'export_validation_prediction_artifact', False):
        request['export_validation_prediction_artifact'] = True
    return request
