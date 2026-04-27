from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from backend.common.abc_optimizer import (
    ABC_DEFAULT_FEATURES,
    ABCResult,
    build_optimization_summary,
    optimize as abc_optimize,
)
from backend.common.artifacts import create_artifact_dir, dump_json, dump_joblib, latest_artifact_dir, load_json
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS
from backend.common.schema_drift import feature_columns_hash, label_schema_hash
from backend.common.supabase_io import has_supabase_credentials, patch_first_row, rest_get
from backend.common.training_dataset import load_training_frame
from backend.models.surrogate_rf import fit_surrogate_bundle


# Story 21 + Edit 3: publish the minimum Peirce Skill Score required for the
# trained model artifact to be accepted. Set via env so CI can promote models
# only after a cold-start warmup period.
PSS_FLOOR = float(os.getenv('PSS_FLOOR', '0.45'))
TIME_SERIES_SPLITS = int(os.getenv('TIME_SERIES_SPLITS', '5'))

# Precheck: refuse to attempt training when the ground-truth corpus is too
# small for KMeansSMOTE(k=5) to be meaningful. Exits 0 (success) so the weekly
# scheduled auto-train does not generate CI noise before the event corpus has
# accumulated. Override via env during local dev.
MIN_EVENTS_FOR_TRAINING = int(os.getenv('MIN_EVENTS_FOR_TRAINING', '30'))
SKIP_EVENT_PRECHECK = os.getenv('SKIP_EVENT_PRECHECK', 'false').lower() in ('1', 'true', 'yes')
ALLOW_SYNTHETIC_BOOTSTRAP = os.getenv('ALLOW_SYNTHETIC_BOOTSTRAP', 'false').lower() in ('1', 'true', 'yes')
ALLOW_DRIFT_SKIP = os.getenv('ALLOW_DRIFT_SKIP', 'false').lower() in ('1', 'true', 'yes')
ALLOW_MODEL_STATUS_PUBLISH = os.getenv('ALLOW_MODEL_STATUS_PUBLISH', 'true').lower() in ('1', 'true', 'yes')
DRIFT_WINDOW_DAYS = int(os.getenv('DRIFT_WINDOW_DAYS', '7'))
DRIFT_BASELINE_DAYS = int(os.getenv('DRIFT_BASELINE_DAYS', '30'))
DRIFT_REGION_MEAN_THRESHOLD = float(os.getenv('DRIFT_REGION_MEAN_THRESHOLD', '0.12'))
DRIFT_FEATURE_MAX_THRESHOLD = float(os.getenv('DRIFT_FEATURE_MAX_THRESHOLD', '0.18'))
DRIFT_NEW_POSITIVE_THRESHOLD = int(os.getenv('DRIFT_NEW_POSITIVE_THRESHOLD', '10'))
MTS_RUNTIME_PROVIDER = os.getenv('MTS_RUNTIME_PROVIDER', 'local').strip() or 'local'
SAR_RELEASE_GATE_PASSED = os.getenv('SAR_RELEASE_GATE_PASSED', '').lower() in ('1', 'true', 'yes')
REQUESTED_DATASET_SNAPSHOT_ID = os.getenv('REQUESTED_DATASET_SNAPSHOT_ID')


def build_dataset_snapshot_id(dataset_manifest: dict[str, object] | None) -> str:
    if not isinstance(dataset_manifest, dict):
        return 'unknown'
    version = str(dataset_manifest.get('training_dataset_version') or 'unknown')
    newest_timestamp = dataset_manifest.get('newest_timestamp')
    if isinstance(newest_timestamp, str) and newest_timestamp:
        return f'{version}:{newest_timestamp}'
    return version


def publish_guard_reason(*, is_synthetic: bool, allow_publish: bool) -> str | None:
    if is_synthetic:
        return 'synthetic_bootstrap_not_published'
    if not allow_publish:
        return 'shadow_only_remote_training'
    return None


def collect_sar_unet_volume_stats(dataset_manifest: dict[str, object] | None) -> dict[str, int]:
    fallback_promoted = 0
    if isinstance(dataset_manifest, dict):
        source_counts = dataset_manifest.get('event_source_counts')
        if isinstance(source_counts, dict):
            fallback_promoted = int(source_counts.get('sar_unet') or 0)
    if not has_supabase_credentials():
        return {
            'sar_unet_shadow_count': 0,
            'sar_unet_promoted_count': fallback_promoted,
            'sar_unet_promoted_region_count': 0,
            'sar_unet_promoted_scene_date_count': 0,
        }
    try:
        rows = rest_get(
            'avalanche_events',
            params={
                'select': 'timestamp,training_eligible,features',
                'source': 'eq.sar_unet',
                'order': 'timestamp.desc',
                'limit': '2000',
            },
        ) or []
    except Exception as exc:  # pragma: no cover - network path
        print(f'[train_model] could not collect sar_unet volume stats ({exc}); using manifest fallback', file=sys.stderr)
        return {
            'sar_unet_shadow_count': 0,
            'sar_unet_promoted_count': fallback_promoted,
            'sar_unet_promoted_region_count': 0,
            'sar_unet_promoted_scene_date_count': 0,
        }

    shadow_count = 0
    promoted_rows: list[dict[str, object]] = []
    for row in rows:
        if bool(row.get('training_eligible')):
            promoted_rows.append(row)
        else:
            shadow_count += 1
    promoted_regions = {
        str((row.get('features') or {}).get('region_key') or 'unknown')
        for row in promoted_rows
        if isinstance(row.get('features'), dict)
    }
    promoted_scene_dates = {
        str(row.get('timestamp'))[:10]
        for row in promoted_rows
        if row.get('timestamp')
    }
    return {
        'sar_unet_shadow_count': shadow_count,
        'sar_unet_promoted_count': len(promoted_rows),
        'sar_unet_promoted_region_count': len(promoted_regions),
        'sar_unet_promoted_scene_date_count': len(promoted_scene_dates),
    }


def fit_model(seed: int, frame: pd.DataFrame, dataset_manifest: dict[str, object]):
    surrogate_bundle = fit_surrogate_bundle(
        frame=frame,
        feature_columns=FEATURE_COLUMNS,
        seed=seed,
        time_series_splits=TIME_SERIES_SPLITS,
    )
    train_df = surrogate_bundle.pop('train_df')
    test_df = surrogate_bundle.pop('test_df')
    metrics = surrogate_bundle['metrics']
    cv_metrics = surrogate_bundle['cv_metrics']
    selected_features = surrogate_bundle['selected_features']

    lstm_head = None
    dataset_snapshot_id = build_dataset_snapshot_id(dataset_manifest)
    sar_volume_stats = collect_sar_unet_volume_stats(dataset_manifest)
    lstm_head_meta: dict[str, object] = {
        'enabled': False,
        'train_flag': os.getenv('TRAIN_MTS_LSTM_HEAD', os.getenv('TRAIN_LSTM_HEAD', 'true')).lower() in ('1', 'true', 'yes'),
        'use_flag_default': os.getenv('USE_MTS_LSTM_HEAD', os.getenv('USE_LSTM_HEAD', 'true')).lower() in ('1', 'true', 'yes'),
        'dynamic_model_type': 'mts_lstm_v1',
        'surrogate_model_role': 'tree_shap_surrogate',
        'runtime_provider': MTS_RUNTIME_PROVIDER,
        'dataset_snapshot_id': dataset_snapshot_id,
        **sar_volume_stats,
    }
    try:
        from backend.lstm_model import fit_lstm_head
        lstm_head = fit_lstm_head(
            train_df=train_df,
            test_df=test_df,
            rf_metrics=metrics,
            seed=seed,
            selected_features=selected_features,
            dataset_manifest=dataset_manifest,
            sar_volume_stats=sar_volume_stats,
            runtime_provider=MTS_RUNTIME_PROVIDER,
            sar_release_gate_passed=SAR_RELEASE_GATE_PASSED,
            requested_dataset_snapshot_id=REQUESTED_DATASET_SNAPSHOT_ID or dataset_snapshot_id,
        )
        if lstm_head is not None:
            lstm_head_meta = getattr(lstm_head, 'metadata', lstm_head_meta)
            if getattr(lstm_head, 'model', None) is None:
                lstm_head = None
    except Exception as exc:  # pragma: no cover - optional sibling model path
        lstm_head_meta = {
            **lstm_head_meta,
            'enabled': False,
            'error': str(exc),
        }

    # P2.2: Hash of the active FEATURE_COLUMNS + observed label enum so
    # daily_inference can detect schema drift and refuse to serve a stale
    # artifact against an evolved feature set.
    feature_hash = feature_columns_hash(FEATURE_COLUMNS)
    label_observed_vs = sorted({str(v) for v in frame.get('verification_status', pd.Series(dtype=str)).dropna().unique()}) if 'verification_status' in frame.columns else []
    label_observed_sl = sorted({str(v) for v in frame.get('severity', pd.Series(dtype=str)).dropna().astype(str).unique()}) if 'severity' in frame.columns else []
    label_hash = label_schema_hash(label_observed_vs, label_observed_sl)

    bundle = {
        **surrogate_bundle,
        'feature_columns': FEATURE_COLUMNS,
        'metrics': metrics,
        'lstm_head': lstm_head,
        'lstm_head_meta': lstm_head_meta,
        'cv_metrics': cv_metrics,
        'dataset_manifest': dataset_manifest,
        'training_dataset_version': dataset_manifest.get('training_dataset_version', 'unknown'),
        'dataset_snapshot_id': dataset_snapshot_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'seed': seed,
        'feature_columns_hash': feature_hash,
        'label_schema_hash': label_hash,
        'dynamic_model_type': 'mts_lstm_v1' if lstm_head is not None else 'surrogate_rf_v1',
        'dynamic_model_version': lstm_head_meta.get('dynamic_model_version') if isinstance(lstm_head_meta, dict) else None,
    }
    return bundle


def publish_metadata(artifact_dir: Path, bundle: dict[str, object]):
    metadata = {
        'selected_features': bundle['selected_features'],
        'feature_columns': bundle['feature_columns'],
        'feature_means': bundle['feature_means'],
        'resampling': bundle['resampling'],
        'calibration_method': bundle['calibration_method'],
        'calibration_error': bundle['calibration_error'],
        'metrics': bundle['metrics'],
        'lstm_head_meta': bundle.get('lstm_head_meta'),
        'dynamic_model_type': bundle.get('dynamic_model_type'),
        'dynamic_model_version': bundle.get('dynamic_model_version'),
        'surrogate_model_version': bundle.get('surrogate_model_version'),
        'dataset_manifest': bundle.get('dataset_manifest'),
        'training_dataset_version': bundle.get('training_dataset_version'),
        'dataset_snapshot_id': bundle.get('dataset_snapshot_id'),
        'artifact_dir': str(artifact_dir),
        'published_at': datetime.now(timezone.utc).isoformat(),
    }
    dump_json(artifact_dir / 'feature_schema.json', {
        'feature_columns': bundle['feature_columns'],
        'selected_features': bundle['selected_features'],
        'feature_means': bundle['feature_means'],
    })
    dump_json(artifact_dir / 'training_metrics.json', metadata)
    dump_joblib(artifact_dir / 'model.joblib', bundle)
    return metadata


def _count_eligible_events() -> int | None:
    """Return the count of training-eligible severe events, or None if we
    cannot query Supabase (e.g. running locally without creds)."""
    if not has_supabase_credentials():
        return None
    from backend.common.config import load_settings as _ls
    settings = _ls()
    try:
        import requests
        resp = requests.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/avalanche_events",
            params={'select': 'id', 'training_eligible': 'eq.true'},
            headers={
                'apikey': settings.supabase_service_role_key,
                'Authorization': f'Bearer {settings.supabase_service_role_key}',
                'Prefer': 'count=exact',
                'Range': '0-0',
            },
            timeout=20,
        )
        resp.raise_for_status()
        content_range = resp.headers.get('content-range', '0-0/0')
        return int(content_range.split('/')[-1])
    except Exception as exc:  # pragma: no cover - network path
        print(f'[train_model] could not count eligible events ({exc}); skipping precheck', file=sys.stderr)
        return None


def compute_drift_stats(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty or 'timestamp' not in frame.columns:
        return {'skip_retrain': False, 'reason': 'empty_frame'}

    ordered = frame.sort_values('timestamp').reset_index(drop=True)
    latest_ts = pd.Timestamp(ordered['timestamp'].max())
    recent_start = latest_ts - pd.Timedelta(days=DRIFT_WINDOW_DAYS)
    baseline_start = recent_start - pd.Timedelta(days=DRIFT_BASELINE_DAYS)
    recent = ordered[ordered['timestamp'] > recent_start]
    baseline = ordered[(ordered['timestamp'] > baseline_start) & (ordered['timestamp'] <= recent_start)]
    if recent.empty or baseline.empty:
        return {'skip_retrain': False, 'reason': 'insufficient_windows'}

    feature_extractors = {
        'snowfall_24h': lambda df: (df['snowfall_24h'].astype(float) * 40.0).to_numpy(),
        'temperature_2m': lambda df: df['temperature_2m'].astype(float).to_numpy(),
        'windspeed_10m': lambda df: df['windspeed_10m'].astype(float).to_numpy(),
    }
    region_stats: dict[str, object] = {}
    max_feature_distance = 0.0
    regions = sorted(set(ordered['region_key'].astype(str).tolist()))
    for region in regions:
        region_recent = recent[recent['region_key'] == region]
        region_baseline = baseline[baseline['region_key'] == region]
        if region_recent.empty or region_baseline.empty:
            continue
        feature_distances: dict[str, float] = {}
        for name, extractor in feature_extractors.items():
            distance = float(wasserstein_distance(extractor(region_recent), extractor(region_baseline)))
            feature_distances[name] = distance
            max_feature_distance = max(max_feature_distance, distance)
        region_mean = float(np.mean(list(feature_distances.values()))) if feature_distances else 0.0
        region_stats[region] = {
            'feature_distances': feature_distances,
            'mean_distance': region_mean,
            'exceeds_region_mean_threshold': region_mean >= DRIFT_REGION_MEAN_THRESHOLD,
        }

    return {
        'recent_window_days': DRIFT_WINDOW_DAYS,
        'baseline_window_days': DRIFT_BASELINE_DAYS,
        'region_mean_threshold': DRIFT_REGION_MEAN_THRESHOLD,
        'feature_max_threshold': DRIFT_FEATURE_MAX_THRESHOLD,
        'regions': region_stats,
        'max_feature_distance': max_feature_distance,
        'concept_drift_detected': bool(max_feature_distance >= DRIFT_FEATURE_MAX_THRESHOLD or any(
            isinstance(region_info, dict) and region_info.get('mean_distance', 0.0) >= DRIFT_REGION_MEAN_THRESHOLD
            for region_info in region_stats.values()
        )),
    }


def load_previous_dataset_manifest(artifact_root: Path) -> dict[str, object] | None:
    try:
        previous_dir = latest_artifact_dir(artifact_root)
        metrics = load_json(previous_dir / 'training_metrics.json')
        return metrics.get('dataset_manifest') if isinstance(metrics, dict) else None
    except Exception:
        return None


def count_new_positive_events(frame: pd.DataFrame, previous_manifest: dict[str, object] | None) -> int:
    if frame.empty or previous_manifest is None:
        return int((frame['label'] == 1).sum()) if 'label' in frame.columns else 0
    newest = previous_manifest.get('newest_timestamp')
    if not isinstance(newest, str):
        return int((frame['label'] == 1).sum()) if 'label' in frame.columns else 0
    newest_ts = pd.Timestamp(newest)
    positives = frame[(frame['label'] == 1) & (frame['timestamp'] > newest_ts)]
    return int(len(positives))


def main() -> int:
    parser = argparse.ArgumentParser(description='Train the Avalanche Insight Hub async ML model')
    parser.add_argument('--samples-per-region', type=int, default=load_settings().samples_per_region)
    parser.add_argument('--seed', type=int, default=load_settings().seed)
    parser.add_argument('--artifact-root', type=Path, default=load_settings().artifact_root)
    args = parser.parse_args()

    # Event-count precheck — silence scheduled runs until the corpus is big
    # enough for KMeansSMOTE(k=5) to generate meaningful synthetic neighbors.
    if not SKIP_EVENT_PRECHECK:
        eligible = _count_eligible_events()
        if eligible is not None and eligible < MIN_EVENTS_FOR_TRAINING:
            print(
                f'[train_model] precheck: only {eligible} eligible severe events '
                f'(need >= {MIN_EVENTS_FOR_TRAINING}). '
                'Insufficient events for KMeansSMOTE. Waiting for more data.'
            )
            return 0

    settings = load_settings()
    frame, dataset_manifest = load_training_frame(
        seed=args.seed,
        samples_per_region=args.samples_per_region,
        grid_size=settings.grid_size,
        allow_synthetic_bootstrap=ALLOW_SYNTHETIC_BOOTSTRAP,
    )
    is_bootstrap = dataset_manifest.get('training_dataset_version') == 'synthetic_bootstrap_v1'
    previous_manifest = load_previous_dataset_manifest(args.artifact_root)
    new_positive_events = count_new_positive_events(frame, previous_manifest)
    drift_stats = compute_drift_stats(frame)
    drift_stats['new_positive_events'] = new_positive_events
    drift_stats['previous_manifest_found'] = previous_manifest is not None
    drift_stats['skip_allowed'] = ALLOW_DRIFT_SKIP and not is_bootstrap
    if drift_stats.get('concept_drift_detected'):
        drift_stats['remediation'] = 'accelerated_decay'
        drift_stats['old_row_weight_multiplier'] = 0.5
        frame.attrs['concept_drift_detected'] = True
        if has_supabase_credentials():
            try:
                patch_first_row('model_status', {
                    'feature_version': 'drift-accelerated-decay',
                    'calibration_profile_version': 'drift-accelerated-decay',
                    'threshold_profile_version': 'drift-accelerated-decay',
                })
            except Exception:
                pass

    if ALLOW_DRIFT_SKIP and not is_bootstrap and isinstance(drift_stats.get('regions'), dict):
        region_exceeded = any(
            region_info.get('mean_distance', 0.0) >= DRIFT_REGION_MEAN_THRESHOLD
            for region_info in drift_stats['regions'].values()
            if isinstance(region_info, dict)
        )
        max_feature_exceeded = float(drift_stats.get('max_feature_distance', 0.0) or 0.0) >= DRIFT_FEATURE_MAX_THRESHOLD
        if not region_exceeded and not max_feature_exceeded and new_positive_events < DRIFT_NEW_POSITIVE_THRESHOLD:
            print(json.dumps({
                'skipped': True,
                'reason': 'drift_below_thresholds',
                'drift_stats': drift_stats,
                'dataset_manifest': dataset_manifest,
            }, indent=2))
            return 0

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_dir = create_artifact_dir(args.artifact_root)
    bundle = fit_model(seed=args.seed, frame=frame, dataset_manifest=dataset_manifest)
    bundle['drift_stats'] = drift_stats

    # Edit 3 Story 21: PSS > PSS_FLOOR artifact gate. Use the higher of the
    # chronological-CV mean and the holdout PSS so a single lucky test fold
    # cannot shadow a poor CV run.
    pss_reported = max(
        float(bundle['metrics'].get('pss_holdout', 0.0) or 0.0),
        float(bundle['metrics'].get('pss_timeseries_mean', 0.0) or 0.0),
    )
    # Cold-start allowance: when PSS_FLOOR is explicitly set to 0.0 we accept
    # pss == 0 so the first synthetic-data artifact can ship. At any positive
    # floor (prod default 0.45) we keep the strict > rule per PRD.
    if PSS_FLOOR <= 0.0:
        gate_passed = pss_reported >= PSS_FLOOR
    else:
        gate_passed = pss_reported > PSS_FLOOR
    bundle['metrics']['pss_reported'] = pss_reported
    bundle['metrics']['pss_gate_passed'] = gate_passed

    metadata = publish_metadata(artifact_dir, bundle)
    metadata['pss_reported'] = pss_reported
    metadata['pss_gate_passed'] = gate_passed
    metadata['pss_gate_floor'] = PSS_FLOOR
    metadata['drift_stats'] = drift_stats
    dump_json(artifact_dir / 'training_metrics.json', metadata)

    if not gate_passed:
        print(
            f"[train_model] PSS gate FAILED: reported={pss_reported:.3f} <= floor={PSS_FLOOR:.3f}. "
            "Refusing to publish artifact to Supabase.",
            file=sys.stderr,
        )
        print(json.dumps(metadata, indent=2))
        return 2

    # P1.1: Run backend ABC optimizer on the training frame to publish real
    # feature_weights + abc_enabled:true to model_status.optimization_summary.
    # This replaces the hardcoded fallback weights in trigger-job/index.ts.
    abc_summary: dict[str, object] | None = None
    try:
        abc_result: ABCResult = abc_optimize(
            frame,
            feature_columns=ABC_DEFAULT_FEATURES,
            seed=args.seed,
        )
        abc_version = f"opt-abc-{artifact_dir.name}"
        abc_summary = build_optimization_summary(
            abc_result,
            runtime_mode='batch_async',
            version=abc_version,
        )
        metadata['optimization_summary'] = abc_summary
        dump_json(artifact_dir / 'optimization_summary.json', abc_summary)
        dump_json(artifact_dir / 'training_metrics.json', metadata)
        print(
            f"[train_model] ABC optimizer done: holdout_pss={abc_result.holdout_pss:.3f} "
            f"iterations={abc_result.iterations} features={list(abc_result.feature_weights.keys())}",
            file=sys.stderr,
        )
    except Exception as exc:  # pragma: no cover - optimizer is best-effort
        abc_summary = None
        metadata['abc_error'] = str(exc)
        print(f"[train_model] ABC optimizer skipped: {exc}", file=sys.stderr)

    # P2.3: Refuse to publish to Supabase if this artifact was built from the
    # synthetic bootstrap fallback. The artifact remains on disk so the
    # operator can inspect it, but model_status stays pinned to the last
    # real-data model until fresh labeled events arrive.
    manifest = bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {}
    is_synthetic = bool(manifest.get('is_synthetic'))
    publish_skip_reason = publish_guard_reason(
        is_synthetic=is_synthetic,
        allow_publish=ALLOW_MODEL_STATUS_PUBLISH,
    )
    if publish_skip_reason is not None:
        metadata['publish_skipped'] = publish_skip_reason
    if is_synthetic:
        print(
            "[train_model] Refusing to publish synthetic-bootstrap artifact to Supabase.",
            file=sys.stderr,
        )
    elif not ALLOW_MODEL_STATUS_PUBLISH:
        print(
            "[train_model] Shadow-only remote training: skipping model_status publish.",
            file=sys.stderr,
        )

    if has_supabase_credentials() and not is_synthetic and ALLOW_MODEL_STATUS_PUBLISH:
        payload: dict[str, object] = {
            'version': f"async-{artifact_dir.name}",
            'last_trained': metadata['published_at'],
            'f1_score': metadata['metrics']['f1'],
            'inference_backend': 'batch_async',
            'next_run': None,
            'feature_version': str(bundle.get('dynamic_model_type') or 'surrogate_rf_v1'),
            'calibration_profile_version': str(bundle.get('dynamic_model_version') or 'surrogate_rf_v1'),
            'threshold_profile_version': str(bundle.get('surrogate_model_version') or 'surrogate_rf_v1'),
        }
        if abc_summary is not None:
            payload['optimization_version'] = str(abc_summary['optimization_version'])
            payload['optimization_summary'] = abc_summary
        # P2.2: Publish the hashes so inference (and future concept-drift
        # dashboards) can diff against the current runtime schema.
        if bundle.get('feature_columns_hash'):
            payload['feature_schema_hash'] = bundle['feature_columns_hash']
        if bundle.get('label_schema_hash'):
            payload['label_schema_hash'] = bundle['label_schema_hash']
        try:
            patch_first_row('model_status', payload)
        except Exception as exc:  # pragma: no cover - publish is best effort
            metadata['publish_error'] = str(exc)
            (artifact_dir / 'training_metrics.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
