from __future__ import annotations

import os
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
    build_training_branch_arrays,
)

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
MTS_RUNTIME_PROVIDER = os.getenv('MTS_RUNTIME_PROVIDER', 'local').strip() or 'local'
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

    def predict_sequence(self, branches: SequenceBranches, *, mc_samples: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        samples = max(1, int(mc_samples or 1))
        stacked = self._predict_stochastic_outputs(branches, samples=samples)
        return stacked.mean(axis=0), stacked.std(axis=0)

    def predict_sequence_seeded_ensemble(
        self,
        branches: SequenceBranches,
        *,
        ensemble_samples: int,
        seed_base: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        stacked = self._predict_stochastic_outputs(
            branches,
            samples=max(1, int(ensemble_samples)),
            seed_base=int(seed_base),
        )
        return stacked.mean(axis=0), stacked.std(axis=0)

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

    train_branches = build_training_branch_arrays(
        train_df,
        region_centers=region_centers,
        dynamic_features=dynamic_features,
        static_features=static_features,
        hourly_steps=MTS_HOURLY_STEPS,
        daily_steps=MTS_DAILY_STEPS,
    )
    test_branches = build_training_branch_arrays(
        test_df,
        region_centers=region_centers,
        dynamic_features=dynamic_features,
        static_features=static_features,
        hourly_steps=MTS_HOURLY_STEPS,
        daily_steps=MTS_DAILY_STEPS,
    )

    hourly_mean, hourly_std = _sequence_norm_stats(train_branches.hourly)
    daily_mean, daily_std = _sequence_norm_stats(train_branches.daily)
    static_mean, static_std = _vector_norm_stats(train_branches.static)

    x_train_hourly = torch.tensor((train_branches.hourly - hourly_mean) / hourly_std, dtype=torch.float32)
    x_train_daily = torch.tensor((train_branches.daily - daily_mean) / daily_std, dtype=torch.float32)
    x_train_static = torch.tensor((train_branches.static - static_mean) / static_std, dtype=torch.float32)
    y_train = torch.tensor(train_df['label'].astype(float).to_numpy(), dtype=torch.float32)
    sample_weights = torch.tensor(
        train_df.get('training_weight', pd.Series(1.0, index=train_df.index)).astype(float).to_numpy(),
        dtype=torch.float32,
    )
    x_test_hourly = torch.tensor((test_branches.hourly - hourly_mean) / hourly_std, dtype=torch.float32)
    x_test_daily = torch.tensor((test_branches.daily - daily_mean) / daily_std, dtype=torch.float32)
    x_test_static = torch.tensor((test_branches.static - static_mean) / static_std, dtype=torch.float32)
    y_test_tensor = torch.tensor(test_df['label'].astype(float).to_numpy(), dtype=torch.float32)
    validation_weights = torch.tensor(
        test_df.get('training_weight', pd.Series(1.0, index=test_df.index)).astype(float).to_numpy(),
        dtype=torch.float32,
    )

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
        optimizer.zero_grad()
        logits = model(x_train_hourly, x_train_daily, x_train_static)
        weighted_loss = loss_fn(logits, y_train) * sample_weights
        loss = weighted_loss.mean()
        loss.backward()
        optimizer.step()
        epochs_completed = epoch + 1

        should_validate = (epochs_completed % MTS_VALIDATE_EVERY == 0) or epochs_completed == epochs_requested
        if not should_validate:
            continue
        model.eval()
        with torch.no_grad():
            validation_logits = model(x_test_hourly, x_test_daily, x_test_static)
            validation_loss = float((loss_fn(validation_logits, y_test_tensor) * validation_weights).mean().item())
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
    positive_count = int(dataset_manifest.get('positive_count', int((train_df['label'] == 1).sum() + (test_df['label'] == 1).sum()))) if isinstance(dataset_manifest, dict) else int((train_df['label'] == 1).sum() + (test_df['label'] == 1).sum())
    negative_count = int(dataset_manifest.get('negative_count', int((train_df['label'] == 0).sum() + (test_df['label'] == 0).sum()))) if isinstance(dataset_manifest, dict) else int((train_df['label'] == 0).sum() + (test_df['label'] == 0).sum())
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
            'sar_unet_shadow_count': sar_unet_shadow_count,
            'sar_unet_promoted_count': sar_unet_promoted_count,
            'sar_unet_promoted_region_count': sar_unet_promoted_region_count,
            'sar_unet_promoted_scene_date_count': sar_unet_promoted_scene_date_count,
        },
    )

    y_test = test_df['label'].astype(int).to_numpy()
    mean_prob, std_prob = head.predict_sequence(test_branches, mc_samples=MTS_MC_DROPOUT_SAMPLES)
    lstm_pss, threshold = _peirce_skill_score_max(y_test, mean_prob)
    lstm_brier = float(brier_score_loss(y_test, mean_prob))
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
        'pss_holdout': lstm_pss,
        'pss_optimal_threshold': threshold,
        'brier_score': lstm_brier,
        'rf_pss_holdout': rf_pss,
        'rf_brier_score': rf_brier,
        'mean_uncertainty_std': float(std_prob.mean()) if std_prob.size else 0.0,
        'uncertainty_validation_passed': bool(std_prob.size and float(std_prob.mean()) >= MTS_MIN_UNCERTAINTY_STD),
        **gate_summary,
        'shadow_mode_default': not bool(gate_summary['production_eligibility_gate_passed']),
    })
    return head


def predict_production_probability(
    rf_probability: float,
    lstm_head: LSTMHead | None,
    branches: SequenceBranches | None,
) -> tuple[float, dict[str, Any] | None]:
    if not USE_MTS_LSTM_HEAD or lstm_head is None or getattr(lstm_head, 'model', None) is None or branches is None:
        return clamp01(rf_probability), None

    mean_prob, std_prob = lstm_head.predict_sequence(
        SequenceBranches(
            hourly=np.asarray([branches.hourly], dtype=np.float32),
            daily=np.asarray([branches.daily], dtype=np.float32),
            static=np.asarray([branches.static], dtype=np.float32),
        ),
        mc_samples=MTS_MC_DROPOUT_SAMPLES,
    )
    dynamic_probability = clamp01(float(mean_prob[0]))
    uncertainty_std = float(std_prob[0]) if std_prob.size else 0.0
    uncertainty_method = 'mc_dropout_v1'
    confidence_lower = clamp01(dynamic_probability - 1.96 * uncertainty_std)
    confidence_upper = clamp01(dynamic_probability + 1.96 * uncertainty_std)
    promotion_gate_passed = bool(lstm_head.metadata.get('promotion_gate_passed'))
    if promotion_gate_passed and uncertainty_std < MTS_MIN_UNCERTAINTY_STD:
        ensemble_mean, ensemble_std = lstm_head.predict_sequence_seeded_ensemble(
            SequenceBranches(
                hourly=np.asarray([branches.hourly], dtype=np.float32),
                daily=np.asarray([branches.daily], dtype=np.float32),
                static=np.asarray([branches.static], dtype=np.float32),
            ),
            ensemble_samples=MTS_ENSEMBLE_SAMPLES,
            seed_base=int(lstm_head.metadata.get('seed', 42)),
        )
        uncertainty_std = max(float(ensemble_std[0]) if ensemble_std.size else 0.0, MTS_MIN_UNCERTAINTY_STD)
        confidence_lower = clamp01(dynamic_probability - 1.96 * uncertainty_std)
        confidence_upper = clamp01(dynamic_probability + 1.96 * uncertainty_std)
        uncertainty_method = 'seeded_dropout_ensemble_v1'
    active_probability = dynamic_probability if promotion_gate_passed else clamp01(rf_probability)
    context: dict[str, Any] = {
        'enabled': True,
        'dynamic_model_type': 'mts_lstm_v1',
        'dynamic_model_version': lstm_head.metadata.get('dynamic_model_version'),
        'surrogate_model_role': 'tree_shap_surrogate',
        'promotion_gate_passed': promotion_gate_passed,
        'shadow_mode_active': not promotion_gate_passed,
        'dynamic_probability': dynamic_probability,
        'active_probability': active_probability,
        'uncertainty_method': uncertainty_method if promotion_gate_passed else 'tree_variance_gaussian_shadow',
        'uncertainty_std': uncertainty_std,
        'uncertainty_floor_std': MTS_MIN_UNCERTAINTY_STD,
    }
    if promotion_gate_passed:
        context['confidence_lower'] = confidence_lower
        context['confidence_upper'] = confidence_upper
    return active_probability, context
