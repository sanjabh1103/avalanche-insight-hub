from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from backend.common.features import FEATURE_COLUMNS
from backend.common.regions import load_regions
from backend.common.risk_math import clamp01
from backend.common.sequence_features import (
    DEFAULT_DAILY_STEPS,
    DEFAULT_HOURLY_STEPS,
    DYNAMIC_SEQUENCE_FEATURES,
    STATIC_SEQUENCE_FEATURES,
    SequenceBranches,
)
from backend.data.mts_lstm_loader import build_mts_lstm_dataloaders, build_mts_lstm_dataset

try:  # pragma: no cover - optional dependency at import time
    import torch
    _HAS_TORCH = True
except Exception:  # pragma: no cover - optional dependency
    torch = None
    _HAS_TORCH = False

if _HAS_TORCH:
    from backend.models.mts_lstm import BranchedMTSLSTM
else:  # pragma: no cover - exercised only when torch missing
    BranchedMTSLSTM = None


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ('1', 'true', 'yes')


TRAIN_MTS_LSTM_HEAD = _flag('TRAIN_MTS_LSTM_HEAD', _flag('TRAIN_LSTM_HEAD', True))
USE_MTS_LSTM_HEAD = _flag('USE_MTS_LSTM_HEAD', _flag('USE_LSTM_HEAD', True))
MTS_LSTM_EPOCHS = int(os.getenv('MTS_LSTM_EPOCHS', '50'))
MTS_LSTM_LR = float(os.getenv('MTS_LSTM_LR', '0.001'))
MTS_DROPOUT = float(os.getenv('MTS_LSTM_DROPOUT', '0.15'))
MTS_EARLY_STOPPING = _flag('MTS_LSTM_EARLY_STOPPING', True)
MTS_MIN_EPOCHS_BEFORE_EARLY_STOPPING = int(os.getenv('MTS_LSTM_MIN_EPOCHS_BEFORE_EARLY_STOPPING', '10'))
MTS_EARLY_STOPPING_PATIENCE = int(os.getenv('MTS_LSTM_EARLY_STOPPING_PATIENCE', '7'))
MTS_VALIDATE_EVERY = max(1, int(os.getenv('MTS_LSTM_VALIDATE_EVERY', '1')))
MTS_MC_DROPOUT_SAMPLES = int(os.getenv('MTS_MC_DROPOUT_SAMPLES', '8'))
MTS_ENSEMBLE_SAMPLES = int(os.getenv('MTS_ENSEMBLE_SAMPLES', '4'))
MTS_MIN_UNCERTAINTY_STD = float(os.getenv('MTS_MIN_UNCERTAINTY_STD', '0.005'))
MTS_HOURLY_STEPS = int(os.getenv('MTS_HOURLY_STEPS', str(DEFAULT_HOURLY_STEPS)))
MTS_DAILY_STEPS = int(os.getenv('MTS_DAILY_STEPS', str(DEFAULT_DAILY_STEPS)))
MTS_LSTM_BATCH_SIZE = int(os.getenv('MTS_LSTM_BATCH_SIZE', '32'))
MTS_RUNTIME_PROVIDER = os.getenv('MTS_RUNTIME_PROVIDER', 'local').strip() or 'local'
MTS_MIN_CALIBRATION_ROWS = int(os.getenv('MTS_MIN_CALIBRATION_ROWS', '10'))
MTS_SAR_RELEASE_GATE_PASSED = _flag('SAR_RELEASE_GATE_PASSED', False)
MTS_SAR_VOLUME_MIN_EVENTS = int(os.getenv('MTS_SAR_VOLUME_MIN_EVENTS', '50'))
MTS_SAR_VOLUME_MIN_REGIONS = int(os.getenv('MTS_SAR_VOLUME_MIN_REGIONS', '3'))
MTS_SAR_VOLUME_MIN_SCENE_DATES = int(os.getenv('MTS_SAR_VOLUME_MIN_SCENE_DATES', '14'))

SHADOW_QUALITY_RULE = 'strict_pss_gt_rf_and_brier_lte_rf'
PRODUCTION_ELIGIBILITY_RULE = 'strict_pss_gt_rf_and_brier_lte_rf_plus_sar_release_and_volume'


@dataclass
class LSTMHead:
    model: Any
    dynamic_features: list[str]
    static_features: list[str]
    hourly_mean: np.ndarray
    hourly_std: np.ndarray
    daily_mean: np.ndarray
    daily_std: np.ndarray
    static_mean: np.ndarray
    static_std: np.ndarray
    metadata: dict[str, Any]
    calibrator: Any | None = None
    evaluation_payload: dict[str, Any] | None = None

    def _normalize(self, branches: SequenceBranches) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        hourly = ((branches.hourly - self.hourly_mean) / self.hourly_std).astype(np.float32)
        daily = ((branches.daily - self.daily_mean) / self.daily_std).astype(np.float32)
        static = ((branches.static - self.static_mean) / self.static_std).astype(np.float32)
        return hourly, daily, static

    def _predict_stochastic_outputs(
        self,
        branches: SequenceBranches,
        *,
        samples: int,
        seed_base: int | None = None,
    ) -> np.ndarray:
        if torch is None or getattr(self, 'model', None) is None:
            raise RuntimeError('MTS-LSTM inference requires torch and a trained model')

        hourly, daily, static = self._normalize(branches)
        hourly_tensor = torch.tensor(hourly, dtype=torch.float32)
        daily_tensor = torch.tensor(daily, dtype=torch.float32)
        static_tensor = torch.tensor(static, dtype=torch.float32)
        outputs: list[np.ndarray] = []
        with torch.no_grad():
            for sample_idx in range(samples):
                if seed_base is not None:
                    torch.manual_seed(int(seed_base + sample_idx))
                if samples > 1:
                    self.model.train()
                else:
                    self.model.eval()
                logits = self.model(hourly_tensor, daily_tensor, static_tensor).detach().cpu().numpy()
                prob = 1.0 / (1.0 + np.exp(-logits.reshape(-1)))
                outputs.append(prob)
        self.model.eval()
        return np.asarray(outputs, dtype=np.float32)

    def apply_probability_calibration(self, probabilities: np.ndarray) -> np.ndarray:
        if self.calibrator is None:
            return np.asarray(probabilities, dtype=np.float32)
        calibrated = self.calibrator.predict(np.asarray(probabilities, dtype=np.float32))
        return np.clip(np.asarray(calibrated, dtype=np.float32), 0.0, 1.0)

    def predict_sequence(
        self,
        branches: SequenceBranches,
        *,
        mc_samples: int | None = None,
        apply_calibration: bool = True,
    ) -> tuple[np.ndarray, np.ndarray]:
        samples = max(1, int(mc_samples or 1))
        stacked = self._predict_stochastic_outputs(branches, samples=samples)
        mean_prob = stacked.mean(axis=0)
        if apply_calibration:
            mean_prob = self.apply_probability_calibration(mean_prob)
        return mean_prob, stacked.std(axis=0)

    def predict_sequence_seeded_ensemble(
        self,
        branches: SequenceBranches,
        *,
        ensemble_samples: int,
        seed_base: int,
        apply_calibration: bool = True,
    ) -> tuple[np.ndarray, np.ndarray]:
        stacked = self._predict_stochastic_outputs(
            branches,
            samples=max(1, int(ensemble_samples)),
            seed_base=int(seed_base),
        )
        mean_prob = stacked.mean(axis=0)
        if apply_calibration:
            mean_prob = self.apply_probability_calibration(mean_prob)
        return mean_prob, stacked.std(axis=0)


def split_validation_and_calibration_frame(
    calib_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if calib_df.empty:
        return calib_df.copy(), calib_df.iloc[0:0].copy(), {
            'calibration_applied': False,
            'calibration_reason': 'empty_calibration_frame',
        }

    ordered = calib_df.sort_values('timestamp').reset_index(drop=True) if 'timestamp' in calib_df.columns else calib_df.reset_index(drop=True)
    split_idx = max(1, len(ordered) // 2)
    validation_df = ordered.iloc[:split_idx].copy()
    calibration_df = ordered.iloc[split_idx:].copy()

    def _slice_is_usable(frame: pd.DataFrame) -> bool:
        if len(frame) < MTS_MIN_CALIBRATION_ROWS:
            return False
        if 'label' not in frame.columns:
            return False
        return len(np.unique(frame['label'].astype(int))) >= 2

    if not _slice_is_usable(validation_df) or not _slice_is_usable(calibration_df):
        return ordered.copy(), ordered.iloc[0:0].copy(), {
            'calibration_applied': False,
            'calibration_reason': 'insufficient_validation_or_calibration_slice',
        }

    return validation_df, calibration_df, {
        'calibration_applied': True,
        'calibration_reason': None,
    }


def fit_isotonic_probability_calibrator(
    labels: np.ndarray,
    raw_probabilities: np.ndarray,
) -> tuple[Any | None, dict[str, Any]]:
    labels_arr = np.asarray(labels).astype(int)
    raw_prob_arr = np.asarray(raw_probabilities, dtype=np.float32)
    if labels_arr.size < MTS_MIN_CALIBRATION_ROWS or len(np.unique(labels_arr)) < 2:
        return None, {
            'calibration_applied': False,
            'calibration_method': 'unavailable',
            'calibration_reason': 'insufficient_calibration_rows_or_classes',
        }
    try:
        from sklearn.isotonic import IsotonicRegression

        calibrator = IsotonicRegression(
            y_min=0.0,
            y_max=1.0,
            increasing=True,
            out_of_bounds='clip',
        )
        calibrator.fit(raw_prob_arr, labels_arr)
        return calibrator, {
            'calibration_applied': True,
            'calibration_method': 'isotonic',
            'calibration_reason': None,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return None, {
            'calibration_applied': False,
            'calibration_method': 'unavailable',
            'calibration_reason': str(exc),
        }

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


def _peirce_skill_score_max(y_true: np.ndarray, y_prob: np.ndarray) -> tuple[float, float]:
    from sklearn.metrics import roc_curve

    y_true_arr = np.asarray(y_true).astype(int)
    y_prob_arr = np.asarray(y_prob).astype(float)
    if y_true_arr.size == 0 or len(np.unique(y_true_arr)) < 2:
        return 0.0, 0.5
    fpr, tpr, thresholds = roc_curve(y_true_arr, y_prob_arr)
    j_scores = tpr - fpr
    idx = int(np.argmax(j_scores))
    return float(j_scores[idx]), float(thresholds[idx])


def build_dataset_snapshot_id(dataset_manifest: dict[str, Any] | None) -> str:
    if not isinstance(dataset_manifest, dict):
        return 'unknown'
    version = str(dataset_manifest.get('training_dataset_version') or 'unknown')
    newest_timestamp = dataset_manifest.get('newest_timestamp')
    if isinstance(newest_timestamp, str) and newest_timestamp:
        return f'{version}:{newest_timestamp}'
    return version


def assess_production_gates(
    *,
    lstm_pss: float,
    lstm_brier: float,
    rf_pss: float,
    rf_brier: float,
    sar_release_gate_passed: bool,
    sar_unet_promoted_count: int,
    sar_unet_promoted_region_count: int,
    sar_unet_promoted_scene_date_count: int,
) -> dict[str, Any]:
    shadow_quality_gate_passed = bool(lstm_pss > rf_pss and lstm_brier <= rf_brier)
    sar_volume_gate_passed = bool(
        sar_unet_promoted_count >= MTS_SAR_VOLUME_MIN_EVENTS
        and sar_unet_promoted_region_count >= MTS_SAR_VOLUME_MIN_REGIONS
        and sar_unet_promoted_scene_date_count >= MTS_SAR_VOLUME_MIN_SCENE_DATES
    )
    production_eligibility_gate_passed = bool(
        shadow_quality_gate_passed and sar_release_gate_passed and sar_volume_gate_passed
    )
    return {
        'shadow_quality_gate_passed': shadow_quality_gate_passed,
        'sar_release_gate_passed': bool(sar_release_gate_passed),
        'sar_volume_gate_passed': sar_volume_gate_passed,
        'production_eligibility_gate_passed': production_eligibility_gate_passed,
        'promotion_gate_passed': production_eligibility_gate_passed,
        'shadow_quality_rule': SHADOW_QUALITY_RULE,
        'promotion_rule': SHADOW_QUALITY_RULE,
        'production_eligibility_rule': PRODUCTION_ELIGIBILITY_RULE,
        'sar_volume_thresholds': {
            'min_promoted_events': MTS_SAR_VOLUME_MIN_EVENTS,
            'min_region_keys': MTS_SAR_VOLUME_MIN_REGIONS,
            'min_scene_dates': MTS_SAR_VOLUME_MIN_SCENE_DATES,
        },
    }


def fit_lstm_head(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    calibration_df: pd.DataFrame,
    test_df: pd.DataFrame,
    rf_metrics: dict[str, Any],
    seed: int,
    selected_features: list[str] | None = None,
    dataset_manifest: dict[str, Any] | None = None,
    sar_volume_stats: dict[str, Any] | None = None,
    runtime_provider: str | None = None,
    sar_release_gate_passed: bool | None = None,
    requested_dataset_snapshot_id: str | None = None,
) -> LSTMHead | None:
    if not TRAIN_MTS_LSTM_HEAD:
        return None

    try:
        from sklearn.metrics import brier_score_loss
    except Exception as exc:  # pragma: no cover - defensive
        return LSTMHead(
            model=None,
            dynamic_features=list(DYNAMIC_SEQUENCE_FEATURES),
            static_features=list(STATIC_SEQUENCE_FEATURES),
            hourly_mean=np.zeros((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            hourly_std=np.ones((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            daily_mean=np.zeros((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            daily_std=np.ones((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            static_mean=np.zeros((1, len(STATIC_SEQUENCE_FEATURES)), dtype=np.float32),
            static_std=np.ones((1, len(STATIC_SEQUENCE_FEATURES)), dtype=np.float32),
            metadata={'enabled': False, 'error': f'metric_unavailable: {exc}', 'seed': seed},
        )

    if torch is None or BranchedMTSLSTM is None:
        return LSTMHead(
            model=None,
            dynamic_features=list(DYNAMIC_SEQUENCE_FEATURES),
            static_features=list(STATIC_SEQUENCE_FEATURES),
            hourly_mean=np.zeros((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            hourly_std=np.ones((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            daily_mean=np.zeros((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            daily_std=np.ones((1, 1, len(DYNAMIC_SEQUENCE_FEATURES)), dtype=np.float32),
            static_mean=np.zeros((1, len(STATIC_SEQUENCE_FEATURES)), dtype=np.float32),
            static_std=np.ones((1, len(STATIC_SEQUENCE_FEATURES)), dtype=np.float32),
            metadata={'enabled': False, 'error': 'torch_unavailable', 'seed': seed},
        )

    torch.manual_seed(seed)
    np.random.seed(seed)

    dynamic_features = [
        feature for feature in (selected_features or FEATURE_COLUMNS)
        if feature in DYNAMIC_SEQUENCE_FEATURES
    ] or list(DYNAMIC_SEQUENCE_FEATURES)
    static_features = list(STATIC_SEQUENCE_FEATURES)
    region_centers = {region.key: (float(region.center[0]), float(region.center[1])) for region in load_regions()}

    train_loader, validation_loader, normalization_stats = build_mts_lstm_dataloaders(
        train_df=train_df,
        validation_df=validation_df,
        region_centers=region_centers,
        dynamic_features=dynamic_features,
        static_features=static_features,
        hourly_steps=MTS_HOURLY_STEPS,
        daily_steps=MTS_DAILY_STEPS,
        batch_size=MTS_LSTM_BATCH_SIZE,
    )

    def _dataset_branches(frame: pd.DataFrame) -> tuple[SequenceBranches, np.ndarray]:
        dataset = build_mts_lstm_dataset(
            frame,
            region_centers=region_centers,
            dynamic_features=dynamic_features,
            static_features=static_features,
            hourly_steps=MTS_HOURLY_STEPS,
            daily_steps=MTS_DAILY_STEPS,
            normalization_stats=normalization_stats,
        )
        return SequenceBranches(
            hourly=np.asarray(dataset.hourly, dtype=np.float32),
            daily=np.asarray(dataset.daily, dtype=np.float32),
            static=np.asarray(dataset.static, dtype=np.float32),
        ), np.asarray(dataset.labels, dtype=np.int32)

    hourly_mean = normalization_stats.hourly_mean
    hourly_std = normalization_stats.hourly_std
    daily_mean = normalization_stats.daily_mean
    daily_std = normalization_stats.daily_std
    static_mean = normalization_stats.static_mean
    static_std = normalization_stats.static_std

    model = BranchedMTSLSTM(
        hourly_input_size=len(dynamic_features),
        daily_input_size=len(dynamic_features),
        static_input_size=len(static_features),
        dropout=MTS_DROPOUT,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=MTS_LSTM_LR)
    positives = max(1, int((train_df['label'] == 1).sum()))
    negatives = max(1, int((train_df['label'] == 0).sum()))
    pos_weight = torch.tensor([negatives / positives], dtype=torch.float32)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight, reduction='none')

    epochs_requested = max(1, MTS_LSTM_EPOCHS)
    best_state: dict[str, Any] | None = None
    best_validation_loss = float('inf')
    epochs_without_improvement = 0
    epochs_completed = 0
    early_stopped = False

    model.train()
    for epoch in range(epochs_requested):
        for batch in train_loader:
            optimizer.zero_grad()
            logits = model(batch['hourly'], batch['daily'], batch['static'])
            weighted_loss = loss_fn(logits, batch['label']) * batch['sample_weight']
            loss = weighted_loss.mean()
            loss.backward()
            optimizer.step()
        epochs_completed = epoch + 1

        should_validate = (epochs_completed % MTS_VALIDATE_EVERY == 0) or epochs_completed == epochs_requested
        if not should_validate:
            continue
        model.eval()
        validation_loss_total = 0.0
        validation_items = 0
        with torch.no_grad():
            for batch in validation_loader:
                validation_logits = model(batch['hourly'], batch['daily'], batch['static'])
                batch_loss = (loss_fn(validation_logits, batch['label']) * batch['sample_weight']).mean()
                batch_count = int(batch['label'].shape[0])
                validation_loss_total += float(batch_loss.item()) * batch_count
                validation_items += batch_count
        validation_loss = float(validation_loss_total / max(1, validation_items))
        model.train()

        if validation_loss < best_validation_loss - 1e-6:
            best_validation_loss = validation_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if (
            MTS_EARLY_STOPPING
            and epochs_completed >= max(1, MTS_MIN_EPOCHS_BEFORE_EARLY_STOPPING)
            and epochs_without_improvement >= max(1, MTS_EARLY_STOPPING_PATIENCE)
        ):
            early_stopped = True
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    dataset_snapshot_id = build_dataset_snapshot_id(dataset_manifest)
    effective_requested_snapshot = str(requested_dataset_snapshot_id or dataset_snapshot_id)
    runtime_provider_value = str(runtime_provider or MTS_RUNTIME_PROVIDER or 'local')
    fallback_positive_count = int(
        (train_df['label'] == 1).sum()
        + (validation_df['label'] == 1).sum()
        + (calibration_df['label'] == 1).sum()
        + (test_df['label'] == 1).sum()
    )
    fallback_negative_count = int(
        (train_df['label'] == 0).sum()
        + (validation_df['label'] == 0).sum()
        + (calibration_df['label'] == 0).sum()
        + (test_df['label'] == 0).sum()
    )
    positive_count = int(dataset_manifest.get('positive_count', fallback_positive_count)) if isinstance(dataset_manifest, dict) else fallback_positive_count
    negative_count = int(dataset_manifest.get('negative_count', fallback_negative_count)) if isinstance(dataset_manifest, dict) else fallback_negative_count
    row_count = positive_count + negative_count
    sar_stats = sar_volume_stats if isinstance(sar_volume_stats, dict) else {}
    sar_unet_shadow_count = int(sar_stats.get('sar_unet_shadow_count') or 0)
    sar_unet_promoted_count = int(sar_stats.get('sar_unet_promoted_count') or 0)
    sar_unet_promoted_region_count = int(sar_stats.get('sar_unet_promoted_region_count') or 0)
    sar_unet_promoted_scene_date_count = int(sar_stats.get('sar_unet_promoted_scene_date_count') or 0)
    head = LSTMHead(
        model=model,
        dynamic_features=dynamic_features,
        static_features=static_features,
        hourly_mean=hourly_mean,
        hourly_std=hourly_std,
        daily_mean=daily_mean,
        daily_std=daily_std,
        static_mean=static_mean,
        static_std=static_std,
        metadata={
            'enabled': True,
            'dynamic_model_type': 'mts_lstm_v1',
            'dynamic_model_version': f'mts-lstm-{seed}',
            'surrogate_model_role': 'tree_shap_surrogate',
            'dynamic_features': dynamic_features,
            'static_features': static_features,
            'hourly_steps': MTS_HOURLY_STEPS,
            'daily_steps': MTS_DAILY_STEPS,
            'uncertainty_method': 'mc_dropout_v1',
            'uncertainty_floor_std': MTS_MIN_UNCERTAINTY_STD,
            'uncertainty_fallback_method': 'seeded_dropout_ensemble_v1',
            'runtime_provider': runtime_provider_value,
            'epochs': epochs_completed,
            'epochs_requested': epochs_requested,
            'epochs_completed': epochs_completed,
            'early_stopped': early_stopped,
            'early_stopping_enabled': MTS_EARLY_STOPPING,
            'early_stopping_patience': MTS_EARLY_STOPPING_PATIENCE,
            'minimum_epochs_before_early_stopping': MTS_MIN_EPOCHS_BEFORE_EARLY_STOPPING,
            'validation_interval_epochs': MTS_VALIDATE_EVERY,
            'validation_loss_best': None if best_validation_loss == float('inf') else best_validation_loss,
            'seed': seed,
            'dataset_snapshot_id': dataset_snapshot_id,
            'requested_dataset_snapshot_id': effective_requested_snapshot,
            'row_count': row_count,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'validation_row_count': int(len(validation_df)),
            'calibration_row_count': int(len(calibration_df)),
            'test_row_count': int(len(test_df)),
            'sar_unet_shadow_count': sar_unet_shadow_count,
            'sar_unet_promoted_count': sar_unet_promoted_count,
            'sar_unet_promoted_region_count': sar_unet_promoted_region_count,
            'sar_unet_promoted_scene_date_count': sar_unet_promoted_scene_date_count,
        },
    )

    calibration_metadata: dict[str, Any] = {
        'calibration_applied': False,
        'calibration_method': 'unavailable',
        'calibration_reason': 'calibration_frame_missing',
    }
    if not calibration_df.empty:
        calibration_branches, y_calibration = _dataset_branches(calibration_df)
        calibration_mean_prob, _ = head.predict_sequence(
            calibration_branches,
            mc_samples=MTS_MC_DROPOUT_SAMPLES,
            apply_calibration=False,
        )
        calibrator, calibration_metadata = fit_isotonic_probability_calibrator(
            y_calibration,
            calibration_mean_prob,
        )
        head.calibrator = calibrator
    else:
        head.calibrator = None

    test_branches, y_test = _dataset_branches(test_df)
    raw_mean_prob, std_prob = head.predict_sequence(
        test_branches,
        mc_samples=MTS_MC_DROPOUT_SAMPLES,
        apply_calibration=False,
    )
    calibrated_mean_prob = head.apply_probability_calibration(raw_mean_prob)
    lstm_pss_uncalibrated, threshold_uncalibrated = _peirce_skill_score_max(y_test, raw_mean_prob)
    lstm_brier_uncalibrated = float(brier_score_loss(y_test, raw_mean_prob))
    lstm_pss, threshold = _peirce_skill_score_max(y_test, calibrated_mean_prob)
    lstm_brier = float(brier_score_loss(y_test, calibrated_mean_prob))
    rf_pss = float(rf_metrics.get('pss_holdout', 0.0) or 0.0)
    rf_brier = float(rf_metrics.get('brier_score', 1.0) or 1.0)
    gate_summary = assess_production_gates(
        lstm_pss=lstm_pss,
        lstm_brier=lstm_brier,
        rf_pss=rf_pss,
        rf_brier=rf_brier,
        sar_release_gate_passed=bool(MTS_SAR_RELEASE_GATE_PASSED if sar_release_gate_passed is None else sar_release_gate_passed),
        sar_unet_promoted_count=sar_unet_promoted_count,
        sar_unet_promoted_region_count=sar_unet_promoted_region_count,
        sar_unet_promoted_scene_date_count=sar_unet_promoted_scene_date_count,
    )
    head.metadata.update({
        'calibration_method': calibration_metadata.get('calibration_method'),
        'calibration_applied': bool(calibration_metadata.get('calibration_applied')),
        'calibration_reason': calibration_metadata.get('calibration_reason'),
        'pss_holdout': lstm_pss,
        'pss_optimal_threshold': threshold,
        'brier_score': lstm_brier,
        'pss_holdout_calibrated': lstm_pss,
        'pss_optimal_threshold_calibrated': threshold,
        'brier_score_calibrated': lstm_brier,
        'pss_holdout_uncalibrated': lstm_pss_uncalibrated,
        'pss_optimal_threshold_uncalibrated': threshold_uncalibrated,
        'brier_score_uncalibrated': lstm_brier_uncalibrated,
        'rf_pss_holdout': rf_pss,
        'rf_brier_score': rf_brier,
        'mean_uncertainty_std': float(std_prob.mean()) if std_prob.size else 0.0,
        'uncertainty_validation_passed': bool(std_prob.size and float(std_prob.mean()) >= MTS_MIN_UNCERTAINTY_STD),
        'calibration_improved': bool(
            calibration_metadata.get('calibration_applied')
            and lstm_brier < lstm_brier_uncalibrated
        ),
        **gate_summary,
        'shadow_mode_default': not bool(gate_summary['production_eligibility_gate_passed']),
    })
    head.evaluation_payload = {
        'test_prob_uncalibrated': np.asarray(raw_mean_prob, dtype=np.float32),
        'test_prob_calibrated': np.asarray(calibrated_mean_prob, dtype=np.float32),
        'test_labels': np.asarray(y_test, dtype=np.int32),
    }
    return head


def predict_production_probability(
    rf_probability: float,
    lstm_head: LSTMHead | None,
    branches: SequenceBranches | None,
    *,
    allow_dynamic_inference: bool | None = None,
) -> tuple[float, dict[str, Any] | None]:
    if not USE_MTS_LSTM_HEAD or lstm_head is None or getattr(lstm_head, 'model', None) is None or branches is None:
        return clamp01(rf_probability), None

    batch_branches = SequenceBranches(
        hourly=np.asarray([branches.hourly], dtype=np.float32),
        daily=np.asarray([branches.daily], dtype=np.float32),
        static=np.asarray([branches.static], dtype=np.float32),
    )
    try:
        mean_prob, std_prob = lstm_head.predict_sequence(
            batch_branches,
            mc_samples=MTS_MC_DROPOUT_SAMPLES,
        )
    except Exception as exc:
        print(
            f"[lstm_model] dynamic inference fallback to RF: {exc}",
            file=sys.stderr,
        )
        return clamp01(rf_probability), {
            'enabled': True,
            'dynamic_model_type': 'mts_lstm_v1',
            'dynamic_model_version': lstm_head.metadata.get('dynamic_model_version'),
            'surrogate_model_role': 'tree_shap_surrogate',
            'promotion_gate_passed': bool(lstm_head.metadata.get('promotion_gate_passed')),
            'shadow_mode_active': True,
            'dynamic_probability': None,
            'active_probability': clamp01(rf_probability),
            'uncertainty_method': 'tree_variance_gaussian_shadow',
            'uncertainty_std': None,
            'uncertainty_floor_std': MTS_MIN_UNCERTAINTY_STD,
            'candidate_ready_for_activation': bool(lstm_head.metadata.get('production_eligibility_gate_passed')),
            'fallback_reason': 'dynamic_inference_error',
            'fallback_error': str(exc),
        }
    dynamic_probability = clamp01(float(mean_prob[0]))
    uncertainty_std = float(std_prob[0]) if std_prob.size else 0.0
    uncertainty_method = 'mc_dropout_v1'
    confidence_lower = clamp01(dynamic_probability - 1.96 * uncertainty_std)
    confidence_upper = clamp01(dynamic_probability + 1.96 * uncertainty_std)
    promotion_gate_passed = bool(lstm_head.metadata.get('promotion_gate_passed'))
    dynamic_is_active = promotion_gate_passed if allow_dynamic_inference is None else bool(allow_dynamic_inference and promotion_gate_passed)
    if dynamic_is_active and uncertainty_std < MTS_MIN_UNCERTAINTY_STD:
        try:
            ensemble_mean, ensemble_std = lstm_head.predict_sequence_seeded_ensemble(
                batch_branches,
                ensemble_samples=MTS_ENSEMBLE_SAMPLES,
                seed_base=int(lstm_head.metadata.get('seed', 42)),
            )
            uncertainty_std = max(float(ensemble_std[0]) if ensemble_std.size else 0.0, MTS_MIN_UNCERTAINTY_STD)
            confidence_lower = clamp01(dynamic_probability - 1.96 * uncertainty_std)
            confidence_upper = clamp01(dynamic_probability + 1.96 * uncertainty_std)
            uncertainty_method = 'seeded_dropout_ensemble_v1'
        except Exception as exc:
            print(
                f"[lstm_model] seeded ensemble fallback failed, using uncertainty floor: {exc}",
                file=sys.stderr,
            )
            uncertainty_std = MTS_MIN_UNCERTAINTY_STD
            confidence_lower = clamp01(dynamic_probability - 1.96 * uncertainty_std)
            confidence_upper = clamp01(dynamic_probability + 1.96 * uncertainty_std)
    active_probability = dynamic_probability if dynamic_is_active else clamp01(rf_probability)
    context: dict[str, Any] = {
        'enabled': True,
        'dynamic_model_type': 'mts_lstm_v1',
        'dynamic_model_version': lstm_head.metadata.get('dynamic_model_version'),
        'surrogate_model_role': 'tree_shap_surrogate',
        'promotion_gate_passed': promotion_gate_passed,
        'shadow_mode_active': not dynamic_is_active,
        'dynamic_probability': dynamic_probability,
        'active_probability': active_probability,
        'uncertainty_method': uncertainty_method if dynamic_is_active else 'tree_variance_gaussian_shadow',
        'uncertainty_std': uncertainty_std,
        'uncertainty_floor_std': MTS_MIN_UNCERTAINTY_STD,
        'candidate_ready_for_activation': bool(lstm_head.metadata.get('production_eligibility_gate_passed')),
    }
    if dynamic_is_active:
        context['confidence_lower'] = confidence_lower
        context['confidence_upper'] = confidence_upper
    return active_probability, context
