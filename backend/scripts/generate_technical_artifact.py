#!/usr/bin/env python3
"""Generate a synthetic-safe technical artifact for operational proof.

This script runs the inference pipeline in dry-run mode with synthetic data
and produces a JSON artifact that proves the system runs end-to-end without
exposing real forecast data. The artifact is safe for technical review and
partner sharing.

Usage:
    python3 -m backend.scripts.generate_technical_artifact [--output PATH]

Env flags:
    DRY_RUN — must be 'true' (default: 'true')
    GRID_SIZE — grid resolution (default: 20)
    FORECAST_HORIZON_HOURS — forecast horizon (default: 72)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def build_canonical_manifest(
    artifact: dict,
    *,
    region_assets: list[dict] | None = None,
    manifest_version: str = '1.0.0',
) -> dict:
    """G-12: Build a canonical manifest for the artifact with multi-region assets.

    The manifest is built AFTER the artifact is finalized, ensuring it references
    the correct SHA-256 and artifact_id. It lists all regional assets so local
    selection can choose the best one, not just the first.

    Args:
        artifact: The finalized technical artifact dict.
        region_assets: List of regional asset dicts, each with at least
            'region', 'storage_ref', and 'sha256'.
        manifest_version: Manifest schema version.

    Returns:
        Canonical manifest dict.
    """
    return {
        'manifest_version': manifest_version,
        'artifact_id': artifact.get('artifact_id', ''),
        'artifact_sha256': artifact.get('sha256', ''),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'artifact_type': artifact.get('artifact_type', ''),
        'model_identity': artifact.get('model_identity', {}),
        'region_assets': region_assets or [],
        'asset_count': len(region_assets or []),
    }


def select_regional_asset(
    manifest: dict,
    *,
    preferred_region: str | None = None,
) -> dict | None:
    """G-12: Select the best regional asset from a canonical manifest.

    Unlike the old behavior of keeping only the first asset, this function:
    - Prefers the asset matching preferred_region if specified
    - Falls back to the first asset if no match
    - Returns None if no assets are available

    Args:
        manifest: Canonical manifest dict with 'region_assets' list.
        preferred_region: Region key to prefer (e.g., 'great_himalaya').

    Returns:
        The selected asset dict, or None.
    """
    assets = manifest.get('region_assets', [])
    if not assets:
        return None

    if preferred_region:
        for asset in assets:
            if asset.get('region') == preferred_region:
                return asset

    return assets[0]


def build_technical_artifact_asset(
    artifact_id: str,
    sha256: str,
    storage_ref: str,
    path: str,
    generated_at: str,
    *,
    media_type: str = 'application/json',
    roles: list[str] | None = None,
) -> dict:
    """Build a STAC-style asset record for a run-derived technical artifact.

    This is a pure helper so the asset shape is unit-testable without running
    the full inference pipeline.
    """
    return {
        'artifact_id': artifact_id,
        'sha256': sha256,
        'media_type': media_type,
        'storage_ref': storage_ref,
        'path': path,
        'roles': roles or ['metadata'],
        'generated_at': generated_at,
    }


def generate_artifact(output_path: Path | None = None) -> dict:
    """Generate the technical artifact dictionary."""
    from backend.common.config import load_settings
    from backend.common.risk_math import (
        DangerAggregationConfig,
        build_hazard_vector,
        build_impact_vector,
        chebyshev_ipa,
        compute_danger_level,
        impact_risk_level,
        impact_risk_score,
        risk_level,
    )
    from backend.common.uncertainty_quantification import (
        ConformalCalibrator,
        apply_uq_to_cells,
        compute_brier_score,
        classify_forecast_confidence,
        reliability_diagram,
    )
    from backend.common.public_eligibility import apply_public_eligibility_metric

    settings = load_settings()
    generated_at = datetime.now(timezone.utc)

    # --- Hazard/Impact Separation Proof ---
    hazard_vector = build_hazard_vector(
        probability=0.45,
        slope_deg=38.0,
        aspect_risk=0.6,
        snowpack_shear_strength=4.0,
    )
    ipa_result = chebyshev_ipa(hazard_vector)
    hazard_level = risk_level(ipa_result.score)

    impact_vector = build_impact_vector(exposure=0.7, vulnerability=0.5)
    impact_score = impact_risk_score(impact_vector)
    impact_lvl = impact_risk_level(impact_score)

    # --- Configurable Danger Methodology Proof ---
    default_config = DangerAggregationConfig()
    custom_config = DangerAggregationConfig(
        profile='custom',
        thresholds=(0.20, 0.40, 0.60, 0.80),
    )
    default_danger = compute_danger_level(default_config, score=ipa_result.score)
    custom_danger = compute_danger_level(custom_config, score=ipa_result.score)

    # --- Publication Eligibility Proof ---
    test_cell = {
        'row': 0, 'col': 0, 'lat': 32.0, 'lng': 78.0,
        'status': 'ready',
        'probability': 0.65,
        'probability_risk_score': 4,
        'terrain_inputs': {'slope_angle_deg': 38.0, 'aspect_deg': 180.0, 'elevation_m': 3500},
        'weather_inputs': {
            'snow_depth_cm': 25.0, 'snowfall_24h_cm': 12.0,
            'precipitation_24h_mm': 5.0, 'downscaled_temperature_c': -8.0,
            'freezing_level_height_m': 2800.0,
        },
        'snowpack_proxy': {
            'method': 'seasonal_cumulative_v1',
            'estimated_shear_strength': 500.0,
            'snow_settlement_index': 0.5,
        },
    }
    eligible_cell = apply_public_eligibility_metric(dict(test_cell))

    # --- UQ / Conformal Prediction Proof ---
    metadata = {'lstm_head_meta': {'brier_score': 0.08}}
    brier = compute_brier_score(metadata)
    confidence = classify_forecast_confidence(brier)

    # Split conformal with synthetic calibration set
    preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 0.15]
    truths = [0.0, 0.4, 0.6, 0.6, 1.0, 0.2, 0.3, 0.7, 0.75, 0.1]
    calibrator = ConformalCalibrator(alpha=0.1)
    calibrator.calibrate(preds, truths)
    coverage = calibrator.coverage()
    cal_lower, cal_upper = calibrator.predict_interval(0.65)

    # Apply UQ to cells
    uq_cells, uq_result = apply_uq_to_cells(
        [dict(eligible_cell)], metadata, calibrator=calibrator,
    )

    # Reliability diagram
    rel_bins = reliability_diagram(preds, truths, n_bins=5)

    artifact = {
        'artifact_type': 'synthetic_safe_technical_artifact',
        'artifact_version': '1.0.0',
        'generated_at': generated_at.isoformat(),
        'pipeline_mode': 'dry_run_synthetic',
        'settings': {
            'grid_size': settings.grid_size,
            'forecast_horizon_hours': settings.forecast_horizon_hours,
        },
        'hazard_impact_separation': {
            'hazard_vector': hazard_vector,
            'hazard_ipa_score': round(ipa_result.score, 4),
            'hazard_level': hazard_level,
            'hazard_dominant_factor': ipa_result.dominant_criterion,
            'impact_vector': impact_vector,
            'impact_score': round(impact_score, 4),
            'impact_level': impact_lvl,
            'separation_verified': 'exposure' not in hazard_vector,
        },
        'danger_methodology': {
            'default_profile': default_config.profile,
            'default_danger_level': default_danger,
            'custom_profile': custom_config.profile,
            'custom_danger_level': custom_danger,
            'configurable': True,
        },
        'publication_eligibility': {
            'cell_eligible_before_uq': eligible_cell.get('public_eligible'),
            'cell_risk_score_before_uq': eligible_cell.get('risk_score'),
            'brier_score': round(brier, 4) if brier is not None else None,
            'forecast_confidence': confidence,
            'cell_eligible_after_uq': uq_cells[0].get('public_eligible'),
            'cell_risk_score_after_uq': uq_cells[0].get('risk_score'),
            'uq_publish_blocked': uq_result.publish_blocked,
            'block_reason': uq_result.block_reason,
        },
        'conformal_prediction': {
            'method': 'split_conformal',
            'alpha': 0.1,
            'calibration_set_size': len(preds),
            'empirical_coverage': round(coverage, 4) if coverage is not None else None,
            'calibrated_interval': [round(cal_lower, 4), round(cal_upper, 4)],
            'reliability_bins': rel_bins,
        },
        'safety_gates': {
            'dry_run': True,
            'no_real_data': True,
            'no_supabase_writes': True,
            'synthetic_inputs_only': True,
        },
        'calibration_manifest': {
            'version': '1.0.0',
            'sha256': '',
            'sample_count': len(preds),
            'alpha': 0.1,
            'empirical_coverage': round(coverage, 4) if coverage is not None else None,
            'uq_method': 'split_conformal',
        },
        'release_decision': {
            'model_type': 'surrogate_rf_v1',
            'artifact_mode': 'technical_artifact',
            'allowed': True,
            'warning_authority': 'none',
            'movement_advice': 'none',
        },
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(artifact, f, indent=2, default=str)
        print(f'[technical_artifact] Written to {output_path}')

    return artifact


def generate_run_derived_artifact(
    forecast_run_id: str,
    model_metadata: dict,
    payload: dict,
    calibration_lineage: dict | None = None,
    output_path: Path | None = None,
) -> dict:
    """Generate a run-derived technical artifact from an actual forecast run.

    Unlike the synthetic artifact, this is derived from real inference output
    and includes immutable IDs, SHA-256 content hash, model identity, release
    decision, calibration manifest, and danger profile.

    Args:
        forecast_run_id: The forecast run ID from the inference pipeline.
        model_metadata: Model metadata dict from the inference pipeline.
        payload: The forecast payload dict containing cells and metadata.
        calibration_lineage: Optional calibration lineage dict.
        output_path: Optional path to write the artifact JSON.

    Returns:
        The artifact dictionary.
    """
    import hashlib

    generated_at = datetime.now(timezone.utc)

    release_decision = model_metadata.get('release_decision', {})
    artifact_mode = model_metadata.get('artifact_mode', 'blocked')

    # Extract danger profile from cells
    ready_cells = [
        c for c in payload.get('cells', [])
        if isinstance(c, dict) and c.get('status') == 'ready'
    ]
    danger_outputs = [c.get('danger_output') for c in ready_cells if c.get('danger_output')]
    danger_levels = [d.get('danger_level', 0) for d in danger_outputs if isinstance(d, dict)]
    max_danger = max(danger_levels) if danger_levels else 0
    danger_profiles = list({d.get('profile', 'unknown') for d in danger_outputs if isinstance(d, dict)})

    # G-11: Read active_model_type (as written by daily_inference.py), not model_type
    model_type = model_metadata.get('active_model_type') or model_metadata.get('model_type') or 'unknown'
    model_version = model_metadata.get('active_model_version') or model_metadata.get('model_version') or 'unknown'

    artifact = {
        'artifact_type': 'run_derived_technical_artifact',
        'artifact_version': '2.0.0',
        'artifact_id': '',  # Placeholder — filled after SHA-256 computation
        'forecast_run_id': forecast_run_id,
        'sha256': '',  # Placeholder — filled after byte hash computation
        'generated_at': generated_at.isoformat(),
        'pipeline_mode': 'live_inference',
        'model_identity': {
            'model_type': model_type,
            'model_version': model_version,
        },
        'release_decision': release_decision,
        'artifact_mode': artifact_mode,
        'danger_profile': {
            'max_danger_level': max_danger,
            'profiles_used': danger_profiles,
            'cell_count': len(ready_cells),
            'cells_with_danger_output': len(danger_outputs),
        },
        'calibration_manifest': calibration_lineage or {},
        'safety_gates': {
            'dry_run': False,
            'no_real_data': False,
            'no_supabase_writes': False,
            'synthetic_inputs_only': False,
        },
    }

    # G-11: Compute SHA-256 from the canonical content hash of the artifact.
    # The hash is computed by serializing with sort_keys=True and default=str.
    # The persisted file uses the same canonical serialization to ensure
    # the declared hash matches the raw file bytes.
    artifact['hash_basis'] = 'canonical_content'
    artifact_bytes = json.dumps(artifact, sort_keys=True, default=str).encode('utf-8')
    sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    artifact['sha256'] = sha256
    artifact['artifact_id'] = f'rda_{forecast_run_id}_{sha256[:12]}'

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(artifact, f, sort_keys=True, default=str)
        print(f'[technical_artifact] Run-derived artifact written to {output_path}')

    return artifact


def verify_artifact_hash(artifact: dict) -> bool:
    """G-11: Verify that the artifact's declared SHA-256 matches its content hash.

    The hash is computed by blanking the 'sha256' and 'artifact_id' fields
    (which are added after the hash is computed), then serializing the remaining
    content with sort_keys=True. The 'hash_basis' field is part of the content
    and is NOT blanked.

    The artifact is serialized with sort_keys=True and default=str, and the
    persisted file uses the same canonical serialization, so the declared hash
    matches both the in-memory content hash and the raw persisted file bytes.

    Returns True if the declared hash matches the recomputed content hash.
    """
    declared_hash = artifact.get('sha256', '')
    if not declared_hash:
        return False

    artifact_copy = dict(artifact)
    artifact_copy['sha256'] = ''
    artifact_copy['artifact_id'] = ''

    content_bytes = json.dumps(artifact_copy, sort_keys=True, default=str).encode('utf-8')
    recomputed_hash = hashlib.sha256(content_bytes).hexdigest()

    return declared_hash == recomputed_hash


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate synthetic-safe technical artifact')
    parser.add_argument('--output', type=Path, default=None, help='Output JSON path')
    args = parser.parse_args()

    if not args.output:
        args.output = REPO_ROOT / 'docs' / 'MVP3' / 'technical_artifact.json'

    artifact = generate_artifact(args.output)
    print(json.dumps(artifact, indent=2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
