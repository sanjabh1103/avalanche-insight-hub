from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 'himalayan_accuracy_readiness_contract_v3'
HIMALAYAN_TOP10_FEATURE_GAP_MATRIX_SCHEMA_VERSION = (
    'himalayan_accuracy_top10_feature_gap_matrix_v1'
)
HIMALAYAN_LOCAL_HOLDOUT_PROTOCOL_SCHEMA_VERSION = (
    'himalayan_accuracy_local_holdout_protocol_v1'
)
HIMALAYAN_LOCAL_HOLDOUT_LEAKAGE_AUDIT_SCHEMA_VERSION = (
    'himalayan_accuracy_local_holdout_leakage_audit_v1'
)
HIMALAYAN_LOCAL_HOLDOUT_METRIC_REPORT_SCHEMA_VERSION = (
    'himalayan_accuracy_local_holdout_metric_report_v1'
)
HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_TEMPLATE_SCHEMA_VERSION = (
    'himalayan_accuracy_local_holdout_prediction_template_v1'
)
HIMALAYAN_BOUNDARY_READINESS_REPORT_SCHEMA_VERSION = (
    'himalayan_accuracy_boundary_readiness_report_v1'
)
PARTNER_TEMPLATE_SCHEMA_VERSION = 'himalayan_accuracy_partner_evidence_templates_v3'
PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION = 'himalayan_accuracy_partner_source_manifest_v1'
PARTNER_INTAKE_CHECKLIST_SCHEMA_VERSION = 'himalayan_accuracy_partner_intake_checklist_v1'
PARTNER_INTAKE_PREFLIGHT_SCHEMA_VERSION = 'himalayan_accuracy_partner_intake_preflight_v1'
PARTNER_INTAKE_DRY_RUN_RUNBOOK_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_intake_dry_run_runbook_v1'
)
PARTNER_SUBMISSION_STATUS_SCHEMA_VERSION = 'himalayan_accuracy_partner_submission_status_v1'
PARTNER_PACKAGE_INDEX_SCHEMA_VERSION = 'himalayan_accuracy_partner_package_index_v1'
PARTNER_INCOMING_TRIAGE_RUNBOOK_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_incoming_triage_runbook_v1'
)
PARTNER_SOURCE_PACKAGE_CHECKSUM_GUIDE_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_source_package_checksum_guide_v1'
)
PARTNER_SYNTHETIC_VALIDATION_PACKAGE_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_synthetic_validation_package_v1'
)
PARTNER_FIELD_DICTIONARY_SCHEMA_VERSION = 'himalayan_accuracy_partner_field_dictionary_v1'
PARTNER_SAMPLE_ROW_PACK_SCHEMA_VERSION = 'himalayan_accuracy_partner_sample_row_pack_v1'
PARTNER_SUBMISSION_QUALITY_SCORE_SCHEMA_VERSION = 'himalayan_accuracy_partner_submission_quality_score_v1'
PARTNER_SUBMISSION_ACCEPTANCE_CHECKLIST_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_submission_acceptance_checklist_v1'
)
PARTNER_HANDOFF_README_SCHEMA_VERSION = 'himalayan_accuracy_partner_handoff_readme_v1'
PARTNER_SUBMISSION_MANIFEST_DIFF_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_submission_manifest_diff_v1'
)
PARTNER_SUBMISSION_REVIEW_LEDGER_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_submission_review_ledger_v1'
)
PARTNER_SUBMISSION_STATUS_DASHBOARD_SCHEMA_VERSION = (
    'himalayan_accuracy_partner_submission_status_dashboard_v1'
)
PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION = 'himalayan_accuracy_partner_evidence_validation_v3'
VALIDATION_POLICY_VERSION = (
    'himalayan_partner_evidence_policy_v3_tidy_label_gpxyz_density_refined_discretization'
)
DEPRECATED_SCHEMA_VERSIONS = (
    'himalayan_accuracy_readiness_contract_v1',
    'himalayan_accuracy_readiness_contract_v2',
    'himalayan_accuracy_partner_evidence_templates_v1',
    'himalayan_accuracy_partner_evidence_templates_v2',
    'himalayan_accuracy_partner_evidence_validation_v1',
    'himalayan_accuracy_partner_evidence_validation_v2',
)
USAGE_BOUNDARY = 'research_validation_only'

STATUS_AVAILABLE = 'available'
STATUS_PARTNER_REQUIRED = 'partner_required'
STATUS_NOT_APPLICABLE = 'not_applicable'
ALLOWED_STATUSES = {STATUS_AVAILABLE, STATUS_PARTNER_REQUIRED, STATUS_NOT_APPLICABLE}
LICENSE_SCOPES_SUPPORTING_RESEARCH_VALIDATION = {
    'internal_research_validation',
    'research_validation_only',
    'partner_restricted_research',
    'cc_by_nc_research_only',
    'commercial_deployment_approved',
}
PARTNER_EVIDENCE_REVIEW_MAX_AGE_DAYS = 365.0
PARTNER_SOURCE_MANIFEST_MAX_AGE_DAYS = 365.0
RELEASE_GATE_ATTESTATION_MAX_AGE_DAYS = 180.0
NOT_APPLICABLE_WAIVER_MAX_AGE_DAYS = 365.0
MAX_REVIEW_FUTURE_SKEW_DAYS = 1.0
SHA256_REFERENCE_PATTERN = re.compile(r'^[a-fA-F0-9]{64}$')

REQUIRED_RELEASE_GATES = (
    'local_himalayan_holdout_passed',
    'scientist_review_complete',
    'license_clearance_complete',
    'production_promotion_approved',
)
HIMALAYAN_CLAIM_STATE_TAXONOMY = (
    'methodology_evidence_only',
    'partner_package_triaged',
    'scientist_review_ready',
    'local_holdout_ready',
    'claim_review_ready',
)
RELEASE_GATE_ATTESTATION_TEMPLATE_PACK_SCHEMA_VERSION = (
    'himalayan_accuracy_release_gate_attestation_template_pack_v1'
)

COMMON_TEMPLATE_COLUMNS = (
    'source_ref',
    'license_scope',
    'review_status',
    'reviewer_id',
    'reviewed_at',
    'reviewer_notes',
)
REQUIRED_NOT_APPLICABLE_WAIVER_FIELDS = ('approved_by', 'reason', 'evidence_ref', 'reviewed_at')
REQUIRED_RELEASE_GATE_ATTESTATION_FIELDS = (
    'approved_by',
    'summary',
    'evidence_ref',
    'reviewed_at',
    'evidence_schema_version',
    'validation_policy_version',
    'acceptance_floors_ref',
    'acceptance_floors',
    'measured_results',
)
REQUIRED_PARTNER_SOURCE_MANIFEST_FIELDS = (
    'source_id',
    'sha256',
    'source_owner',
    'dataset_name',
    'license_scope',
    'date_range',
    'review_status',
    'reviewer_id',
    'reviewed_at',
    'evidence_package_ref',
)

RELEASE_GATE_ACCEPTANCE_FLOOR_REQUIREMENTS: dict[str, dict[str, Any]] = {
    'local_himalayan_holdout_passed': {
        'ratio_fields': (
            'macro_f1_min',
            'high_danger_recall_min',
            'mean_day_accuracy_min',
            'region_accuracy_min',
        ),
        'max_ratio_fields': (
            'brier_score_max',
            'ece_max',
        ),
        'true_fields': (
            'leakage_check_required',
            'independent_holdout_required',
        ),
    },
    'scientist_review_complete': {
        'positive_integer_fields': (
            'reviewed_case_count_min',
            'reviewer_count_min',
        ),
        'ratio_fields': (
            'adjudication_completion_rate_min',
        ),
        'nonnegative_integer_fields': (
            'unresolved_critical_issue_max',
        ),
    },
    'license_clearance_complete': {
        'ratio_fields': (
            'source_license_review_coverage_min',
        ),
        'nonnegative_integer_fields': (
            'blocked_license_scope_count_max',
            'unsupported_license_scope_count_max',
        ),
    },
    'production_promotion_approved': {
        'true_fields': (
            'rollback_plan_required',
            'monitoring_required',
            'human_override_required',
            'production_scoring_approval_required',
        ),
    },
}

HIMALAYAN_LOCAL_HOLDOUT_ACCEPTANCE_FLOORS: dict[str, Any] = {
    'macro_f1_min': 0.70,
    'high_danger_recall_min': 0.80,
    'brier_score_max': 0.18,
    'ece_max': 0.08,
    'mean_day_accuracy_min': 0.75,
    'region_accuracy_min': 0.70,
    'leakage_check_required': True,
    'independent_holdout_required': True,
}
HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_COLUMNS = (
    'holdout_id',
    'valid_at',
    'region_id',
    'elevation_band',
    'true_danger_level_1_to_4',
    'predicted_danger_level_1_to_4',
    'probability_level_1',
    'probability_level_2',
    'probability_level_3',
    'probability_level_4',
)

ALLOWED_HOLDOUT_SPLITS = {'validation', 'test', 'holdout', 'fresh_final', 'independent_holdout'}
ALLOWED_ASPECT_VALUES = {
    'n',
    'ne',
    'e',
    'se',
    's',
    'sw',
    'w',
    'nw',
    'north',
    'northeast',
    'east',
    'southeast',
    'south',
    'southwest',
    'west',
    'northwest',
    'all',
    'unknown',
}

CONTROLLED_VALUE_SETS: dict[str, set[str]] = {
    'license_scope': {
        'internal_research_validation',
        'research_validation_only',
        'partner_restricted_research',
        'cc_by_nc_research_only',
        'internal_shadow_presentation',
        'public_presentation_with_attribution',
        'external_imagery_share_approved',
        'commercial_deployment_approved',
        'pending_license_review',
        'blocked_license_scope',
        'unknown',
    },
    'avalanche_problem': {
        'new_snow',
        'wind_slab',
        'persistent_weak_layer',
        'persistent_weak_layers',
        'wet_snow',
        'gliding_snow',
        'deep_persistent_weak_layer',
        'loose_dry',
        'loose_wet',
        'cornice_fall',
        'multiple',
        'no_distinct_problem',
        'other_reviewed',
        'unknown',
    },
    'observed_outcome': {
        'avalanche_observed',
        'no_avalanche_observed',
        'partial_evidence',
        'near_miss',
        'incident',
        'unknown',
    },
    'preprocessing_level': {
        'raw',
        'orthorectified',
        'terrain_corrected',
        'radiometrically_calibrated',
        'co_registered',
        'analysis_ready',
        'reviewed_analysis_ready',
        'unknown',
    },
    'quality_flag': {
        'reviewed_valid',
        'reviewed_suspect',
        'estimated',
        'modeled',
        'measured',
        'corrected',
        'provisional',
        'unknown',
    },
    'terrain_class': {
        'non_avalanche',
        'simple',
        'challenging',
        'complex',
        'extreme',
        'unknown',
    },
    'verdict': {
        'label_valid',
        'label_remediation_required',
        'model_error',
        'terrain_context_required',
        'review_incomplete',
        'uncertain',
    },
    'label_quality': {
        'valid',
        'suspect',
        'invalid',
        'incomplete',
        'needs_terrain_context',
        'unknown',
    },
    'model_error_type': {
        'true_positive',
        'false_positive',
        'false_negative',
        'true_negative',
        'calibration_error',
        'localization_error',
        'domain_shift',
        'not_applicable',
        'unknown',
    },
    'danger_scale_standard': {
        'eaws_5_level',
        'local_4_level',
        'partner_custom_reviewed',
        'unknown',
    },
    'label_source': {
        'official_forecast',
        'tidy_reanalysis',
        'local_nowcast',
        'scientist_reviewed',
        'field_observer',
        'avalanche_occurrence_record',
        'unknown',
    },
    'avalanche_regime': {
        'dry_snow',
        'wet_snow',
        'mixed',
        'unknown',
    },
    'forecast_cycle': {
        'morning_update',
        'evening_bulletin',
        'nowcast',
        'hindcast',
        'unknown',
    },
}


@dataclass(frozen=True)
class ReferenceRequirement:
    source_requirement: str
    source_field: str
    target_requirement: str
    target_field: str
    multi_value: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRequirement:
    key: str
    category: str
    required_fields: tuple[str, ...]
    unlocks_top10_feature: str
    minimum_rows_for_availability: int = 1
    minimum_distinct_counts: dict[str, int] = field(default_factory=dict)
    minimum_temporal_span_days: dict[str, float] = field(default_factory=dict)
    minimum_numeric_spans: dict[str, float] = field(default_factory=dict)
    current_status: str = STATUS_PARTNER_REQUIRED
    current_repo_evidence: str = 'not_available_as_local_himalayan_truth'
    needed_for_world_class: str = ''
    loophole_if_missing: str = ''

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['required_fields'] = list(self.required_fields)
        payload['minimum_distinct_counts'] = dict(self.minimum_distinct_counts)
        payload['minimum_temporal_span_days'] = dict(self.minimum_temporal_span_days)
        payload['minimum_numeric_spans'] = dict(self.minimum_numeric_spans)
        return payload


REQUIREMENTS: tuple[EvidenceRequirement, ...] = (
    EvidenceRequirement(
        key='station_metadata',
        category='himalayan_station_network',
        required_fields=('station_id', 'region_key', 'latitude', 'longitude', 'elevation_m', 'active_date_range'),
        unlocks_top10_feature='Himalayan station + snowpack data contract',
        minimum_rows_for_availability=10,
        minimum_distinct_counts={'station_id': 10, 'region_key': 3},
        minimum_numeric_spans={'elevation_m': 500.0},
        current_repo_evidence='partner adapter docs only',
        needed_for_world_class='Reviewed Himalayan station coordinates and elevations for GPxyz and local validation.',
        loophole_if_missing='Spatial interpolation cannot be validated and Swiss station evidence may be mistaken for Himalayan proof.',
    ),
    EvidenceRequirement(
        key='weather_station_observations',
        category='weather_features',
        required_fields=(
            'station_id',
            'observed_at',
            'air_temp_c',
            'precipitation_mm',
            'snowfall_cm',
            'snow_depth_cm',
            'wind_speed_ms',
            'wind_dir_deg',
        ),
        unlocks_top10_feature='Calibrated 4-class danger-level model',
        minimum_rows_for_availability=30,
        minimum_distinct_counts={'station_id': 3, 'observed_at': 10},
        minimum_temporal_span_days={'observed_at': 7.0},
        current_repo_evidence='Open-Meteo proxy and feature pipeline',
        needed_for_world_class='Partner-observed weather station series aligned to local danger labels.',
        loophole_if_missing='Open-Meteo proxy performance may not represent Himalayan station-scale conditions.',
    ),
    EvidenceRequirement(
        key='snowpack_profile_features',
        category='snowpack_weak_layer',
        required_fields=(
            'station_id',
            'observed_at',
            'layer_index',
            'layer_depth_cm',
            'grain_type',
            'hardness_index',
            'stability_index',
            'quality_flag',
            'profile_model',
            'snowpack_model_version',
            'profile_extracted_at_local_time',
            'stability_metric_name',
        ),
        unlocks_top10_feature='Distributed snowpack / weak-layer evidence',
        minimum_rows_for_availability=20,
        minimum_distinct_counts={'station_id': 3, 'observed_at': 5},
        minimum_temporal_span_days={'observed_at': 4.0},
        current_repo_evidence='snowpack proxy plus Swiss RF2 weak-layer columns',
        needed_for_world_class='HIM-STRAT/SNOWPACK-like local profile features and weak-layer validation.',
        loophole_if_missing='Seasonal proxy scalars can be overread as weak-layer truth.',
    ),
    EvidenceRequirement(
        key='danger_labels_and_bulletins',
        category='danger_ground_truth',
        required_fields=(
            'region_id',
            'valid_from',
            'valid_to',
            'danger_scale_standard',
            'danger_level_1_to_5',
            'danger_level_1_to_4',
            'label_source',
            'tidy_label_review_basis',
            'nowcast_evidence_ref',
            'observer_evidence_ref',
            'forecast_cycle',
            'forecast_issue_time',
            'valid_at',
            'window_center_local_time',
            'aggregation_window_hours',
            'avalanche_problem',
            'avalanche_regime',
            'elevation_band_policy',
            'critical_elevation_m',
            'aspect_policy',
            'forecaster_or_reviewer_id',
        ),
        unlocks_top10_feature='Calibrated 4-class danger-level model',
        minimum_rows_for_availability=10,
        minimum_distinct_counts={'region_id': 3, 'danger_level_1_to_4': 2},
        minimum_temporal_span_days={'valid_from': 7.0},
        current_repo_evidence='scientist daily verification schema and Swiss RF2 labels',
        needed_for_world_class='Reviewed Himalayan danger labels and bulletin archive by region/elevation band.',
        loophole_if_missing='Model agreement cannot be judged against local expert truth.',
    ),
    EvidenceRequirement(
        key='warning_region_polygons',
        category='spatial_forecast_units',
        required_fields=('region_id', 'polygon_geometry', 'crs', 'elevation_policy', 'valid_date_range'),
        unlocks_top10_feature='Elevation-band warning-region aggregation',
        minimum_rows_for_availability=1,
        minimum_distinct_counts={'region_id': 1},
        current_repo_evidence='app regions and station-row Swiss aggregation baseline',
        needed_for_world_class='Official or partner-reviewed Himalayan warning-region geometries.',
        loophole_if_missing='Station or grid predictions cannot be converted into forecast-region evidence.',
    ),
    EvidenceRequirement(
        key='historical_avalanche_events',
        category='event_outcomes',
        required_fields=(
            'event_id',
            'observed_at',
            'latitude',
            'longitude',
            'elevation_m',
            'aspect',
            'avalanche_problem',
            'avalanche_regime',
            'observed_outcome',
            'confidence',
            'source',
            'field_report_ref',
            'avalanche_atlas_ref',
        ),
        unlocks_top10_feature='Field reports and event-outcome feedback loop',
        minimum_rows_for_availability=10,
        minimum_distinct_counts={'event_id': 10},
        minimum_temporal_span_days={'observed_at': 7.0},
        minimum_numeric_spans={'elevation_m': 500.0},
        current_repo_evidence='event ingestion and field-report workflow',
        needed_for_world_class='Partner-confirmed Himalayan events for false-positive/false-negative assessment.',
        loophole_if_missing='Forecast accuracy can be confused with bulletin agreement only.',
    ),
    EvidenceRequirement(
        key='remote_sensing_validation_scenes',
        category='remote_sensing',
        required_fields=(
            'scene_id',
            'sensor',
            'acquired_at',
            'preprocessing_level',
            'truth_mask_or_event_ref',
            'holdout_split',
            'license_scope',
        ),
        unlocks_top10_feature='Remote-sensing avalanche evidence',
        minimum_rows_for_availability=5,
        minimum_distinct_counts={'scene_id': 5},
        minimum_temporal_span_days={'acquired_at': 4.0},
        current_repo_evidence='European SAR shadow lane; SnowSlide still blocked',
        needed_for_world_class='Himalayan SAR/optical/InSAR validation scenes with independent holdouts.',
        loophole_if_missing='European scene performance may be incorrectly generalized to Himalayan terrain.',
    ),
    EvidenceRequirement(
        key='terrain_ates_runout_validation',
        category='terrain_exposure',
        required_fields=('region_id', 'dem_ref', 'slope', 'aspect', 'terrain_class', 'runout_validation_ref', 'quality_flag'),
        unlocks_top10_feature='Terrain, ATES, runout and exposure features',
        minimum_rows_for_availability=3,
        minimum_distinct_counts={'region_id': 3},
        minimum_numeric_spans={'slope': 10.0},
        current_repo_evidence='DEM, runout, map, impact overlays, and 3D inspection',
        needed_for_world_class='Reviewed terrain classes and runout validation for pilot regions.',
        loophole_if_missing='Terrain visualization may be mistaken for validated exposure modelling.',
    ),
    EvidenceRequirement(
        key='scientist_reviews',
        category='human_validation',
        required_fields=(
            'review_id',
            'reviewer_id',
            'reviewed_at',
            'case_id',
            'verdict',
            'label_quality',
            'model_error_type',
            'confidence',
        ),
        unlocks_top10_feature='Explainability, calibration and model-vs-human diagnostics',
        minimum_rows_for_availability=20,
        minimum_distinct_counts={'review_id': 20, 'case_id': 20},
        minimum_temporal_span_days={'reviewed_at': 7.0},
        current_repo_evidence='scientist validation route, daily verification, and action ledger',
        needed_for_world_class='Enough completed scientist reviews to support model-vs-human and label-quality analysis.',
        loophole_if_missing='Structured workflow exists but has insufficient local expert evidence.',
    ),
    EvidenceRequirement(
        key='independent_himalayan_holdout',
        category='release_gate',
        required_fields=(
            'holdout_id',
            'source_refs',
            'region_ids',
            'date_range',
            'label_source',
            'tidy_label_review_basis',
            'nowcast_evidence_ref',
            'observer_evidence_ref',
            'forecast_cycle',
            'forecast_issue_time',
            'valid_at',
            'window_center_local_time',
            'aggregation_window_hours',
            'avalanche_regime',
            'critical_elevation_m',
            'aspect_policy',
            'field_report_ref',
            'avalanche_atlas_ref',
            'leakage_check',
            'acceptance_floors',
        ),
        unlocks_top10_feature='Release gates, uncertainty and claim governance',
        minimum_rows_for_availability=1,
        minimum_distinct_counts={'holdout_id': 1},
        current_repo_evidence='fresh-final-holdout design discipline from SAR lane',
        needed_for_world_class='Independent Himalayan final holdout not used in model or threshold selection.',
        loophole_if_missing='A tuned candidate may be promoted from contaminated validation evidence.',
    ),
)


REFERENCE_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    ReferenceRequirement(
        source_requirement='weather_station_observations',
        source_field='station_id',
        target_requirement='station_metadata',
        target_field='station_id',
    ),
    ReferenceRequirement(
        source_requirement='snowpack_profile_features',
        source_field='station_id',
        target_requirement='station_metadata',
        target_field='station_id',
    ),
    ReferenceRequirement(
        source_requirement='danger_labels_and_bulletins',
        source_field='region_id',
        target_requirement='warning_region_polygons',
        target_field='region_id',
    ),
    ReferenceRequirement(
        source_requirement='terrain_ates_runout_validation',
        source_field='region_id',
        target_requirement='warning_region_polygons',
        target_field='region_id',
    ),
    ReferenceRequirement(
        source_requirement='independent_himalayan_holdout',
        source_field='region_ids',
        target_requirement='warning_region_polygons',
        target_field='region_id',
        multi_value=True,
    ),
)

TOP10_FEATURE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        'rank': 1,
        'feature': 'D_tidy-equivalent Himalayan label provenance',
        'required_evidence': (
            'danger_labels_and_bulletins',
            'historical_avalanche_events',
            'scientist_reviews',
            'independent_himalayan_holdout',
        ),
        'current_repo_evidence': 'Generated v3 templates require label source, review basis, nowcast/observer refs, regime, and timing fields.',
        'world_class_need': 'Partner-reviewed local danger truth backed by nowcast, observer, event, or reanalysis evidence, not raw public bulletins alone.',
        'gap_or_loophole': 'Without quality-controlled label provenance, the model can learn forecaster noise and no Himalayan accuracy claim is defensible.',
        'rating': 2,
        'next_target': 'Obtain filled danger, event, scientist-review, and holdout rows with D_tidy-equivalent provenance.',
    },
    {
        'rank': 2,
        'feature': 'Calibrated 4-class danger-level model',
        'required_evidence': (
            'weather_station_observations',
            'snowpack_profile_features',
            'danger_labels_and_bulletins',
            'independent_himalayan_holdout',
        ),
        'current_repo_evidence': 'Research-only Swiss RF4 reproduction, feature audit, and calibration artifacts.',
        'world_class_need': 'Local or reviewed-transfer calibrated danger model with per-class F1, high-danger recall, Brier score, and ECE.',
        'gap_or_loophole': 'Swiss RF4 signal is not Himalayan proof and can be inflated by split, feature, or label mismatch.',
        'rating': 3,
        'next_target': 'Run calibrated model evaluation only after local partner labels and holdout are available.',
    },
    {
        'rank': 3,
        'feature': 'RAvaFcast-style spatial interpolation',
        'required_evidence': (
            'station_metadata',
            'weather_station_observations',
            'danger_labels_and_bulletins',
        ),
        'current_repo_evidence': 'GPxyz readiness and exact-GP guardrails exist; real run blocks on station coordinates.',
        'world_class_need': 'Station-coordinate join, LOOCV ME/MAE/RMSE, 1 km grid predictions, and posterior uncertainty.',
        'gap_or_loophole': 'Missing station metadata blocks spatial forecast parity and regional interpretation.',
        'rating': 2,
        'next_target': 'Validate station coordinate coverage, then run GPxyz LOOCV and grid generation.',
    },
    {
        'rank': 4,
        'feature': 'Elevation-band warning-region aggregation',
        'required_evidence': (
            'warning_region_polygons',
            'station_metadata',
            'danger_labels_and_bulletins',
        ),
        'current_repo_evidence': 'Station-row elev-simple baseline exists for Swiss reproduction.',
        'world_class_need': 'Official Himalayan warning-region polygons, elevation policy, leakage-safe refined discretization, and day/region accuracy.',
        'gap_or_loophole': 'Station-row aggregation is not full regional forecast parity.',
        'rating': 2,
        'next_target': 'Acquire reviewed warning-region polygons and elevation-band policy.',
    },
    {
        'rank': 5,
        'feature': 'Distributed snowpack / weak-layer evidence',
        'required_evidence': (
            'snowpack_profile_features',
            'weather_station_observations',
            'danger_labels_and_bulletins',
        ),
        'current_repo_evidence': 'Snowpack proxy exists; Swiss source contains weak-layer-style variables.',
        'world_class_need': 'HIM-STRAT/SNOWPACK-like local profile fields, weak-layer indicators, and stability/failure-depth validation.',
        'gap_or_loophole': 'Proxy scalars are not weak-layer truth.',
        'rating': 2,
        'next_target': 'Add reviewed snowpack profile exports and map fields to controlled partner schema.',
    },
    {
        'rank': 6,
        'feature': 'Terrain, ATES, runout and exposure features',
        'required_evidence': (
            'terrain_ates_runout_validation',
            'warning_region_polygons',
            'historical_avalanche_events',
        ),
        'current_repo_evidence': 'DEM, runout, map overlays, impact layers, and 3D inspection exist.',
        'world_class_need': 'Reviewed slope/aspect/elevation/terrain traps, ATES-style classes, runout validation, and exposure-sensitive surfaces.',
        'gap_or_loophole': 'Terrain visualization can be mistaken for validated exposure modelling.',
        'rating': 3,
        'next_target': 'Validate terrain/runout rows against partner-reviewed regions and events.',
    },
    {
        'rank': 7,
        'feature': 'Remote-sensing avalanche evidence',
        'required_evidence': (
            'remote_sensing_validation_scenes',
            'historical_avalanche_events',
            'independent_himalayan_holdout',
        ),
        'current_repo_evidence': 'European SAR shadow lane exists; SnowSlide remains research-grade blocked.',
        'world_class_need': 'Himalayan SAR/optical/InSAR validation scenes, preprocessing contracts, independent holdouts, and precision/recall/FPR gates.',
        'gap_or_loophole': 'European scene performance cannot be generalized to Himalayan terrain.',
        'rating': 3,
        'next_target': 'Collect Himalayan remote-sensing validation scenes and keep SAR/optical/InSAR shadow-gated.',
    },
    {
        'rank': 8,
        'feature': 'Field reports and event-outcome feedback loop',
        'required_evidence': (
            'historical_avalanche_events',
            'scientist_reviews',
            'danger_labels_and_bulletins',
        ),
        'current_repo_evidence': 'Field reports, event ingestion, scientist validation cases, daily verification, and action ledger exist.',
        'world_class_need': 'Enough paired events, label-quality workflow, false-positive/false-negative closure, and training eligibility rules.',
        'gap_or_loophole': 'Workflow exists but local Himalayan evidence volume is still insufficient.',
        'rating': 4,
        'next_target': 'Route real events through scientist review and close label/model error types.',
    },
    {
        'rank': 9,
        'feature': 'Explainability, calibration and model-vs-human diagnostics',
        'required_evidence': (
            'scientist_reviews',
            'independent_himalayan_holdout',
            'danger_labels_and_bulletins',
        ),
        'current_repo_evidence': 'SHAP path, RF methodology docs, scientist daily verification, and RF4 calibration work exist.',
        'world_class_need': 'Artifact-level SHAP proof, calibrated probability quality, model-vs-scientist discrimination, and decision-curve evidence.',
        'gap_or_loophole': 'Explanations must be tied to active artifacts and local outcomes before claims.',
        'rating': 3,
        'next_target': 'Add model-vs-scientist/outcome report once reviewed cases exist.',
    },
    {
        'rank': 10,
        'feature': 'Release gates, uncertainty and claim governance',
        'required_evidence': (
            'independent_himalayan_holdout',
            'scientist_reviews',
            'remote_sensing_validation_scenes',
        ),
        'current_repo_evidence': 'Readiness contract, release attestations, production blocks, and SAR-style holdout discipline exist.',
        'world_class_need': 'One promotion framework across danger model, spatial aggregation, SAR/remote sensing, uncertainty display, and fresh holdouts.',
        'gap_or_loophole': 'Governance is strong, but local validation is still missing.',
        'rating': 4,
        'next_target': 'Populate release-gate attestations only after local evidence and independent holdout pass.',
    },
)


FIELD_GUIDANCE: dict[str, dict[str, str]] = {
    'station_id': {
        'description': 'Stable partner-local station identifier used to join metadata, weather, and snowpack rows.',
        'expected_format': 'string',
        'unit': 'none',
    },
    'region_key': {
        'description': 'Partner warning region, forecast zone, or pilot-area key for station grouping.',
        'expected_format': 'string',
        'unit': 'none',
    },
    'region_id': {
        'description': 'Stable warning-region identifier used to join labels, polygons, terrain, and holdout evidence.',
        'expected_format': 'string',
        'unit': 'none',
    },
    'latitude': {
        'description': 'WGS84 latitude for station, event, or validation point.',
        'expected_format': 'decimal degrees in [-90, 90]',
        'unit': 'degrees',
    },
    'longitude': {
        'description': 'WGS84 longitude for station, event, or validation point.',
        'expected_format': 'decimal degrees in [-180, 180]',
        'unit': 'degrees',
    },
    'elevation_m': {
        'description': 'Elevation above mean sea level.',
        'expected_format': 'number in [0, 9000]',
        'unit': 'm',
    },
    'active_date_range': {
        'description': 'Date interval when a station, region, or source was active and valid for analysis.',
        'expected_format': 'YYYY-MM-DD/YYYY-MM-DD',
        'unit': 'date range',
    },
    'valid_date_range': {
        'description': 'Date interval when a geometry or regional policy is valid.',
        'expected_format': 'YYYY-MM-DD/YYYY-MM-DD',
        'unit': 'date range',
    },
    'date_range': {
        'description': 'Date interval covered by a holdout or reviewed source group.',
        'expected_format': 'YYYY-MM-DD/YYYY-MM-DD',
        'unit': 'date range',
    },
    'observed_at': {
        'description': 'Timestamp for an observation, event, or reviewed snowpack profile.',
        'expected_format': 'ISO-8601 timestamp',
        'unit': 'timestamp',
    },
    'valid_from': {
        'description': 'Forecast, bulletin, or label validity start.',
        'expected_format': 'ISO-8601 timestamp',
        'unit': 'timestamp',
    },
    'valid_to': {
        'description': 'Forecast, bulletin, or label validity end.',
        'expected_format': 'ISO-8601 timestamp',
        'unit': 'timestamp',
    },
    'acquired_at': {
        'description': 'Remote-sensing acquisition timestamp.',
        'expected_format': 'ISO-8601 timestamp',
        'unit': 'timestamp',
    },
    'reviewed_at': {
        'description': 'Timestamp when the evidence row or source package was reviewed.',
        'expected_format': 'ISO-8601 timestamp',
        'unit': 'timestamp',
    },
    'air_temp_c': {
        'description': 'Near-surface air temperature used for weather features.',
        'expected_format': 'number',
        'unit': 'deg C',
    },
    'precipitation_mm': {
        'description': 'Liquid-equivalent precipitation over the reported observation window.',
        'expected_format': 'nonnegative number',
        'unit': 'mm',
    },
    'snowfall_cm': {
        'description': 'New snowfall over the reported observation window.',
        'expected_format': 'nonnegative number',
        'unit': 'cm',
    },
    'snow_depth_cm': {
        'description': 'Total snow depth at the observation point.',
        'expected_format': 'nonnegative number',
        'unit': 'cm',
    },
    'wind_speed_ms': {
        'description': 'Wind speed aligned to the weather feature window.',
        'expected_format': 'nonnegative number',
        'unit': 'm/s',
    },
    'wind_dir_deg': {
        'description': 'Wind direction clockwise from north.',
        'expected_format': 'number in [0, 360]',
        'unit': 'degrees',
    },
    'layer_index': {
        'description': 'Ordered snowpack layer index within a station/time profile.',
        'expected_format': 'integer',
        'unit': 'none',
    },
    'layer_depth_cm': {
        'description': 'Depth of a snowpack layer or weak-layer marker.',
        'expected_format': 'nonnegative number',
        'unit': 'cm',
    },
    'grain_type': {
        'description': 'Reviewed snow grain or weak-layer classification supplied by the partner.',
        'expected_format': 'string',
        'unit': 'none',
    },
    'hardness_index': {
        'description': 'Partner-reviewed snow hardness index or encoded hardness class.',
        'expected_format': 'number or reviewed class code',
        'unit': 'partner scale',
    },
    'stability_index': {
        'description': 'Normalized snowpack stability indicator.',
        'expected_format': 'number in [0, 1]',
        'unit': 'ratio',
    },
    'danger_scale_standard': {
        'description': 'Danger-scale standard used by the partner before any model-compatible mapping.',
        'expected_format': 'controlled value',
        'unit': 'none',
    },
    'danger_level_1_to_5': {
        'description': 'Canonical reviewed avalanche danger level, preserving five-level operational standards where available.',
        'expected_format': 'integer from 1 to 5',
        'unit': 'danger level',
    },
    'danger_level_1_to_4': {
        'description': 'Current research model-compatible four-class label; must not replace the canonical partner danger level.',
        'expected_format': 'integer from 1 to 4',
        'unit': 'model class',
    },
    'avalanche_problem': {
        'description': 'Reviewed avalanche problem type associated with a label, event, or terrain context.',
        'expected_format': 'controlled value',
        'unit': 'none',
    },
    'elevation_band_policy': {
        'description': 'Partner rule for applying danger labels by elevation band.',
        'expected_format': 'string',
        'unit': 'policy text',
    },
    'polygon_geometry': {
        'description': 'Warning-region geometry in a reviewed geospatial encoding.',
        'expected_format': 'WKT, GeoJSON, or partner-reviewed geometry reference',
        'unit': 'geometry',
    },
    'crs': {
        'description': 'Coordinate reference system for a geometry or gridded source.',
        'expected_format': 'EPSG code or CRS identifier',
        'unit': 'none',
    },
    'aspect': {
        'description': 'Slope aspect as degrees clockwise from north or a compass sector.',
        'expected_format': 'number in [0, 360] or compass sector',
        'unit': 'degrees',
    },
    'slope': {
        'description': 'Slope angle for terrain or runout evidence.',
        'expected_format': 'number in [0, 90]',
        'unit': 'degrees',
    },
    'confidence': {
        'description': 'Reviewer confidence in an event, label, or case decision.',
        'expected_format': 'number in [0, 1]',
        'unit': 'ratio',
    },
    'source_ref': {
        'description': 'SHA-256 qualified reference to a reviewed source package.',
        'expected_format': 'sha256:<64-hex> or file:<path>#sha256=<64-hex>',
        'unit': 'reference',
    },
    'source_refs': {
        'description': 'One or more SHA-256 qualified source references used by a holdout definition.',
        'expected_format': 'semicolon, comma, or pipe separated source_ref values',
        'unit': 'reference list',
    },
    'license_scope': {
        'description': 'Reviewed usage scope for the source row or package.',
        'expected_format': 'controlled value',
        'unit': 'none',
    },
    'review_status': {
        'description': 'Partner review state; evidence rows must be reviewed before they can support readiness.',
        'expected_format': 'reviewed',
        'unit': 'none',
    },
    'reviewer_id': {
        'description': 'Named reviewer, review board, or partner review identifier.',
        'expected_format': 'string',
        'unit': 'none',
    },
    'reviewer_notes': {
        'description': 'Short notes explaining assumptions, caveats, or local mapping decisions.',
        'expected_format': 'string',
        'unit': 'none',
    },
}


def _requirement_by_key() -> dict[str, EvidenceRequirement]:
    return {item.key: item for item in REQUIREMENTS}


def _reference_requirements_by_source() -> dict[str, list[ReferenceRequirement]]:
    grouped: dict[str, list[ReferenceRequirement]] = {}
    for item in REFERENCE_REQUIREMENTS:
        grouped.setdefault(item.source_requirement, []).append(item)
    return grouped


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ''


def _parse_datetime(value: object) -> datetime | None:
    raw = str(value).strip()
    if raw.endswith('Z'):
        raw = f'{raw[:-1]}+00:00'
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {'true', '1', 'yes'}:
        return True
    if raw in {'false', '0', 'no'}:
        return False
    return None


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _review_age_days(*, generated_at: datetime, reviewed_at: datetime) -> float:
    return round(
        (_ensure_timezone(generated_at) - _ensure_timezone(reviewed_at)).total_seconds() / 86400.0,
        6,
    )


def _sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_declared_sha256(reference: object) -> str | None:
    if _is_blank(reference):
        return None
    raw = str(reference).strip()
    if raw.lower().startswith('sha256:'):
        digest = raw.split(':', 1)[1].strip()
    elif '#sha256=' in raw:
        digest = raw.rsplit('#sha256=', 1)[1].strip()
    else:
        return None
    digest = digest.split('&', 1)[0].strip()
    return digest.lower() if SHA256_REFERENCE_PATTERN.fullmatch(digest) else None


def _reference_digest_error(column: str, value: object) -> str | None:
    if _is_blank(value):
        return None
    if _extract_declared_sha256(value) is None:
        return f'{column} must include a sha256 digest as sha256:<64-hex> or ...#sha256=<64-hex>'
    return None


def _reference_kind(value: object) -> str:
    raw = str(value or '').strip().lower()
    if raw.startswith('file:'):
        return 'local_file'
    if raw.startswith('https://'):
        return 'https_hash_declared'
    if raw.startswith('sha256:'):
        return 'hash_only'
    return 'other_hash_declared'


def _source_ref_integrity_issue(
    value: object,
    *,
    evidence_root: Path,
) -> dict[str, Any] | None:
    if _is_blank(value):
        return None
    raw = str(value).strip()
    declared_digest = _extract_declared_sha256(raw)
    if declared_digest is None:
        return {
            'source_ref': raw,
            'error': 'source_ref must include a valid sha256 digest',
        }
    if not raw.lower().startswith('file:'):
        return None

    reference_path = raw[5:].split('#', 1)[0].strip()
    if not reference_path:
        return {
            'source_ref': raw,
            'error': 'file source_ref must include a relative path',
        }
    path = Path(reference_path)
    if path.is_absolute() or '..' in path.parts:
        return {
            'source_ref': raw,
            'error': 'file source_ref must stay inside the partner evidence root',
        }
    evidence_root_resolved = evidence_root.resolve()
    resolved = (evidence_root / path).resolve()
    try:
        resolved.relative_to(evidence_root_resolved)
    except ValueError:
        return {
            'source_ref': raw,
            'error': 'file source_ref resolves outside the partner evidence root',
        }
    if not resolved.is_file():
        return {
            'source_ref': raw,
            'error': 'file source_ref does not resolve to a local file',
        }
    actual_digest = _sha256_digest(resolved)
    if actual_digest != declared_digest:
        return {
            'source_ref': raw,
            'error': 'file source_ref sha256 digest does not match local file',
            'declared_sha256': declared_digest,
            'actual_sha256': actual_digest,
        }
    return None


def validate_partner_source_manifest(
    partner_source_manifest: dict[str, Any] | None,
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    if partner_source_manifest is None:
        return {
            'schema_version': PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
            'validation_policy_version': VALIDATION_POLICY_VERSION,
            'usage_boundary': USAGE_BOUNDARY,
            'generated_at': generated_at.isoformat(),
            'production_scoring_allowed': False,
            'himalayan_accuracy_claim_allowed': False,
            'decision': 'partner_source_manifest_not_supplied',
            'source_count': 0,
            'valid_source_count': 0,
            'valid_source_hashes': [],
            'duplicate_source_hashes': [],
            'invalid_source_count': 0,
            'invalid_source_examples': [],
        }
    schema_version = str(partner_source_manifest.get('schema_version') or '').strip()
    validation_policy_version = str(partner_source_manifest.get('validation_policy_version') or '').strip()
    raw_sources = partner_source_manifest.get('sources')
    if schema_version != PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            'partner source manifest schema mismatch: '
            f'expected {PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION}, got {schema_version or "missing"}'
        )
    if validation_policy_version != VALIDATION_POLICY_VERSION:
        raise ValueError(
            'partner source manifest policy mismatch: '
            f'expected {VALIDATION_POLICY_VERSION}, got {validation_policy_version or "missing"}'
        )
    if not isinstance(raw_sources, list):
        raise ValueError('partner source manifest sources must be a list')

    seen_hashes: set[str] = set()
    duplicate_hashes: set[str] = set()
    valid_sources: list[dict[str, Any]] = []
    invalid_examples: list[dict[str, Any]] = []
    invalid_count = 0
    for index, raw_source in enumerate(raw_sources):
        entry_number = index + 1
        if not isinstance(raw_source, dict):
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append({'entry_number': entry_number, 'error': 'source entry must be a JSON object'})
            continue
        missing_fields = [
            field for field in REQUIRED_PARTNER_SOURCE_MANIFEST_FIELDS if _is_blank(raw_source.get(field))
        ]
        if missing_fields:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'error': f'missing required source field(s): {missing_fields}',
                    }
                )
            continue
        sha256 = str(raw_source.get('sha256') or '').strip().lower()
        if not SHA256_REFERENCE_PATTERN.fullmatch(sha256):
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'error': 'sha256 must be 64 hex characters',
                    }
                )
            continue
        if sha256 in seen_hashes:
            duplicate_hashes.add(sha256)
        seen_hashes.add(sha256)
        license_scope = _normalize_controlled_value(raw_source.get('license_scope'))
        if license_scope not in LICENSE_SCOPES_SUPPORTING_RESEARCH_VALIDATION:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'sha256': sha256,
                        'error': f'license_scope does not support research validation: {license_scope}',
                    }
                )
            continue
        if str(raw_source.get('review_status') or '').strip().lower() != 'reviewed':
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'sha256': sha256,
                        'error': 'review_status must be reviewed',
                    }
                )
            continue
        reviewed_at = _parse_datetime(raw_source.get('reviewed_at'))
        if reviewed_at is None:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'sha256': sha256,
                        'error': 'reviewed_at must be ISO-8601 parseable',
                    }
                )
            continue
        review_age_days = _review_age_days(generated_at=generated_at, reviewed_at=reviewed_at)
        if review_age_days > PARTNER_SOURCE_MANIFEST_MAX_AGE_DAYS:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'sha256': sha256,
                        'error': (
                            'reviewed_at is stale; max age is '
                            f'{PARTNER_SOURCE_MANIFEST_MAX_AGE_DAYS:g} days'
                        ),
                    }
                )
            continue
        if review_age_days < -MAX_REVIEW_FUTURE_SKEW_DAYS:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'sha256': sha256,
                        'error': (
                            'reviewed_at is in the future beyond allowed skew of '
                            f'{MAX_REVIEW_FUTURE_SKEW_DAYS:g} days'
                        ),
                    }
                )
            continue
        evidence_package_ref_error = _reference_digest_error(
            'evidence_package_ref',
            raw_source.get('evidence_package_ref'),
        )
        if evidence_package_ref_error is not None:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(
                    {
                        'entry_number': entry_number,
                        'source_id': raw_source.get('source_id'),
                        'sha256': sha256,
                        'error': evidence_package_ref_error,
                    }
                )
            continue
        valid_sources.append(
            {
                'source_id': str(raw_source['source_id']).strip(),
                'sha256': sha256,
                'source_owner': str(raw_source['source_owner']).strip(),
                'dataset_name': str(raw_source['dataset_name']).strip(),
                'license_scope': license_scope,
                'date_range': str(raw_source['date_range']).strip(),
                'review_status': 'reviewed',
                'reviewer_id': str(raw_source['reviewer_id']).strip(),
                'reviewed_at': str(raw_source['reviewed_at']).strip(),
                'review_age_days': review_age_days,
                'max_review_age_days': PARTNER_SOURCE_MANIFEST_MAX_AGE_DAYS,
                'evidence_package_ref': str(raw_source['evidence_package_ref']).strip(),
            }
        )

    if duplicate_hashes:
        invalid_count += len(duplicate_hashes)
        for digest in sorted(duplicate_hashes):
            if len(invalid_examples) < 5:
                invalid_examples.append({'sha256': digest, 'error': 'duplicate source hash'})
    decision = (
        'partner_source_manifest_available'
        if raw_sources and not invalid_count
        else 'blocked_invalid_partner_source_manifest'
        if raw_sources
        else 'blocked_empty_partner_source_manifest'
    )
    return {
        'schema_version': PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'source_count': len(raw_sources),
        'valid_source_count': len(valid_sources),
        'valid_source_hashes': sorted({source['sha256'] for source in valid_sources}),
        'duplicate_source_hashes': sorted(duplicate_hashes),
        'invalid_source_count': invalid_count,
        'invalid_source_examples': invalid_examples,
        'sources': valid_sources,
    }


def markdown_partner_source_manifest_validation(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Source Manifest Validation',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Source count | {payload['source_count']} |",
        f"| Valid source count | {payload['valid_source_count']} |",
        f"| Invalid source count | {payload['invalid_source_count']} |",
        f"| Duplicate source hashes | {len(payload.get('duplicate_source_hashes', []))} |",
        '',
        '## Source Hash Coverage',
        '',
    ]
    valid_hashes = payload.get('valid_source_hashes') or []
    if valid_hashes:
        for digest in valid_hashes:
            lines.append(f'- `{digest}`')
    else:
        lines.append('- None')
    lines.extend(['', '## Invalid Source Examples', ''])
    invalid_examples = payload.get('invalid_source_examples') or []
    if invalid_examples:
        lines.extend(['| Source | Error |', '|---|---|'])
        for example in invalid_examples:
            source_id = example.get('source_id') or example.get('sha256') or example.get('entry_number') or 'unknown'
            lines.append(f"| `{source_id}` | {example.get('error', 'unknown error')} |")
    else:
        lines.append('- None')
    lines.append('')
    return '\n'.join(lines)


def _validate_not_applicable_waivers(
    *,
    status_overrides: dict[str, str],
    known_requirements: dict[str, EvidenceRequirement],
    not_applicable_waivers: dict[str, Any] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    waivers = not_applicable_waivers or {}
    unknown_waivers = sorted(set(waivers) - set(known_requirements))
    if unknown_waivers:
        raise ValueError(f'unknown not_applicable waiver requirement(s): {unknown_waivers}')
    not_applicable_keys = sorted(
        key for key, status in status_overrides.items() if status == STATUS_NOT_APPLICABLE
    )
    missing = [key for key in not_applicable_keys if key not in waivers]
    if missing:
        raise ValueError(f'not_applicable override requires waiver(s): {missing}')
    invalid: list[dict[str, Any]] = []
    validated: dict[str, Any] = {}
    for key in not_applicable_keys:
        waiver = waivers.get(key)
        if not isinstance(waiver, dict):
            invalid.append({'key': key, 'error': 'waiver must be a JSON object'})
            continue
        blank_fields = [
            field for field in REQUIRED_NOT_APPLICABLE_WAIVER_FIELDS if _is_blank(waiver.get(field))
        ]
        if blank_fields:
            invalid.append({'key': key, 'error': f'missing required waiver field(s): {blank_fields}'})
            continue
        reviewed_at = _parse_datetime(waiver.get('reviewed_at'))
        if reviewed_at is None:
            invalid.append({'key': key, 'error': 'reviewed_at must be ISO-8601 parseable'})
            continue
        review_age_days = _review_age_days(generated_at=generated_at, reviewed_at=reviewed_at)
        if review_age_days > NOT_APPLICABLE_WAIVER_MAX_AGE_DAYS:
            invalid.append(
                {
                    'key': key,
                    'error': (
                        'reviewed_at is stale; max age is '
                        f'{NOT_APPLICABLE_WAIVER_MAX_AGE_DAYS:g} days'
                    ),
                }
            )
            continue
        if review_age_days < -MAX_REVIEW_FUTURE_SKEW_DAYS:
            invalid.append(
                {
                    'key': key,
                    'error': (
                        'reviewed_at is in the future beyond allowed skew of '
                        f'{MAX_REVIEW_FUTURE_SKEW_DAYS:g} days'
                    ),
                }
            )
            continue
        evidence_ref_error = _reference_digest_error('evidence_ref', waiver.get('evidence_ref'))
        if evidence_ref_error is not None:
            invalid.append({'key': key, 'error': evidence_ref_error})
            continue
        reason = str(waiver.get('reason') or '').strip()
        if len(reason) < 20:
            invalid.append({'key': key, 'error': 'reason must be at least 20 characters'})
            continue
        validated[key] = {
            'approved_by': str(waiver['approved_by']).strip(),
            'reason': reason,
            'evidence_ref': str(waiver['evidence_ref']).strip(),
            'reviewed_at': str(waiver['reviewed_at']).strip(),
            'review_age_days': review_age_days,
            'max_review_age_days': NOT_APPLICABLE_WAIVER_MAX_AGE_DAYS,
        }
    if invalid:
        raise ValueError(f'invalid not_applicable waiver(s): {invalid}')
    return validated


def _validate_release_gate_acceptance_floors(gate: str, floors: object) -> dict[str, Any]:
    if not isinstance(floors, dict):
        raise ValueError('acceptance_floors must be a JSON object')
    requirements = RELEASE_GATE_ACCEPTANCE_FLOOR_REQUIREMENTS[gate]
    required_fields: list[str] = []
    for field_group in (
        'ratio_fields',
        'max_ratio_fields',
        'positive_integer_fields',
        'nonnegative_integer_fields',
        'true_fields',
    ):
        required_fields.extend(requirements.get(field_group, ()))
    missing = [field for field in required_fields if _is_blank(floors.get(field))]
    if missing:
        raise ValueError(f'missing acceptance_floors field(s): {missing}')
    validated: dict[str, Any] = {}
    for field in (*requirements.get('ratio_fields', ()), *requirements.get('max_ratio_fields', ())):
        parsed = _parse_float(floors.get(field))
        if parsed is None or parsed < 0.0 or parsed > 1.0:
            raise ValueError(f'{field} must be numeric in [0, 1]')
        validated[field] = parsed
    for field in requirements.get('positive_integer_fields', ()):
        parsed = _parse_float(floors.get(field))
        if parsed is None or parsed % 1 != 0 or int(parsed) < 1:
            raise ValueError(f'{field} must be a positive integer')
        validated[field] = int(parsed)
    for field in requirements.get('nonnegative_integer_fields', ()):
        parsed = _parse_float(floors.get(field))
        if parsed is None or parsed % 1 != 0 or int(parsed) < 0:
            raise ValueError(f'{field} must be a nonnegative integer')
        validated[field] = int(parsed)
    for field in requirements.get('true_fields', ()):
        parsed = _parse_bool(floors.get(field))
        if parsed is not True:
            raise ValueError(f'{field} must be true')
        validated[field] = True
    return validated


def _validate_release_gate_measured_results(
    gate: str,
    *,
    floors: dict[str, Any],
    measured_results: object,
) -> dict[str, Any]:
    if not isinstance(measured_results, dict):
        raise ValueError('measured_results must be a JSON object')
    requirements = RELEASE_GATE_ACCEPTANCE_FLOOR_REQUIREMENTS[gate]
    required_fields: list[str] = []
    for field_group in (
        'ratio_fields',
        'max_ratio_fields',
        'positive_integer_fields',
        'nonnegative_integer_fields',
        'true_fields',
    ):
        required_fields.extend(requirements.get(field_group, ()))
    missing = [field for field in required_fields if _is_blank(measured_results.get(field))]
    if missing:
        raise ValueError(f'missing measured_results field(s): {missing}')
    validated: dict[str, Any] = {}
    for field in requirements.get('ratio_fields', ()):
        parsed = _parse_float(measured_results.get(field))
        if parsed is None or parsed < 0.0 or parsed > 1.0:
            raise ValueError(f'{field} measured result must be numeric in [0, 1]')
        if parsed < float(floors[field]):
            raise ValueError(f'{field} measured result must be >= acceptance floor')
        validated[field] = parsed
    for field in requirements.get('max_ratio_fields', ()):
        parsed = _parse_float(measured_results.get(field))
        if parsed is None or parsed < 0.0 or parsed > 1.0:
            raise ValueError(f'{field} measured result must be numeric in [0, 1]')
        if parsed > float(floors[field]):
            raise ValueError(f'{field} measured result must be <= acceptance floor')
        validated[field] = parsed
    for field in requirements.get('positive_integer_fields', ()):
        parsed = _parse_float(measured_results.get(field))
        if parsed is None or parsed % 1 != 0 or int(parsed) < 1:
            raise ValueError(f'{field} measured result must be a positive integer')
        if int(parsed) < int(floors[field]):
            raise ValueError(f'{field} measured result must be >= acceptance floor')
        validated[field] = int(parsed)
    for field in requirements.get('nonnegative_integer_fields', ()):
        parsed = _parse_float(measured_results.get(field))
        if parsed is None or parsed % 1 != 0 or int(parsed) < 0:
            raise ValueError(f'{field} measured result must be a nonnegative integer')
        if int(parsed) > int(floors[field]):
            raise ValueError(f'{field} measured result must be <= acceptance floor')
        validated[field] = int(parsed)
    for field in requirements.get('true_fields', ()):
        parsed = _parse_bool(measured_results.get(field))
        if parsed is not True:
            raise ValueError(f'{field} measured result must be true')
        validated[field] = True
    return validated


def _validate_release_gate_attestations(
    *,
    release_gates: dict[str, bool],
    release_gate_attestations: dict[str, Any] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    attestations = release_gate_attestations or {}
    known_gates = set(REQUIRED_RELEASE_GATES)
    unknown_attestations = sorted(set(attestations) - known_gates)
    if unknown_attestations:
        raise ValueError(f'unknown release gate attestation(s): {unknown_attestations}')
    true_gates = sorted(gate for gate, passed in release_gates.items() if passed)
    missing = [gate for gate in true_gates if gate not in attestations]
    if missing:
        raise ValueError(f'true release gate requires attestation(s): {missing}')
    invalid: list[dict[str, Any]] = []
    validated: dict[str, Any] = {}
    for gate in true_gates:
        attestation = attestations.get(gate)
        if not isinstance(attestation, dict):
            invalid.append({'gate': gate, 'error': 'attestation must be a JSON object'})
            continue
        blank_fields = [
            field for field in REQUIRED_RELEASE_GATE_ATTESTATION_FIELDS if _is_blank(attestation.get(field))
        ]
        if blank_fields:
            invalid.append({'gate': gate, 'error': f'missing required attestation field(s): {blank_fields}'})
            continue
        reviewed_at = _parse_datetime(attestation.get('reviewed_at'))
        if reviewed_at is None:
            invalid.append({'gate': gate, 'error': 'reviewed_at must be ISO-8601 parseable'})
            continue
        evidence_ref_error = _reference_digest_error('evidence_ref', attestation.get('evidence_ref'))
        if evidence_ref_error is not None:
            invalid.append({'gate': gate, 'error': evidence_ref_error})
            continue
        review_age_days = _review_age_days(generated_at=generated_at, reviewed_at=reviewed_at)
        if review_age_days > RELEASE_GATE_ATTESTATION_MAX_AGE_DAYS:
            invalid.append(
                {
                    'gate': gate,
                    'error': (
                        'reviewed_at is stale; max age is '
                        f'{RELEASE_GATE_ATTESTATION_MAX_AGE_DAYS:g} days'
                    ),
                }
            )
            continue
        if review_age_days < -MAX_REVIEW_FUTURE_SKEW_DAYS:
            invalid.append(
                {
                    'gate': gate,
                    'error': (
                        'reviewed_at is in the future beyond allowed skew of '
                        f'{MAX_REVIEW_FUTURE_SKEW_DAYS:g} days'
                    ),
                }
            )
            continue
        evidence_schema_version = str(attestation.get('evidence_schema_version') or '').strip()
        if evidence_schema_version != PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION:
            invalid.append(
                {
                    'gate': gate,
                    'error': (
                        'evidence_schema_version must match '
                        f'{PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION}'
                    ),
                }
            )
            continue
        validation_policy_version = str(attestation.get('validation_policy_version') or '').strip()
        if validation_policy_version != VALIDATION_POLICY_VERSION:
            invalid.append(
                {
                    'gate': gate,
                    'error': f'validation_policy_version must match {VALIDATION_POLICY_VERSION}',
                }
            )
            continue
        floors_ref_error = _reference_digest_error('acceptance_floors_ref', attestation.get('acceptance_floors_ref'))
        if floors_ref_error is not None:
            invalid.append({'gate': gate, 'error': floors_ref_error})
            continue
        try:
            acceptance_floors = _validate_release_gate_acceptance_floors(
                gate,
                attestation.get('acceptance_floors'),
            )
        except ValueError as exc:
            invalid.append({'gate': gate, 'error': str(exc)})
            continue
        try:
            measured_results = _validate_release_gate_measured_results(
                gate,
                floors=acceptance_floors,
                measured_results=attestation.get('measured_results'),
            )
        except ValueError as exc:
            invalid.append({'gate': gate, 'error': str(exc)})
            continue
        summary = str(attestation.get('summary') or '').strip()
        if len(summary) < 20:
            invalid.append({'gate': gate, 'error': 'summary must be at least 20 characters'})
            continue
        validated[gate] = {
            'approved_by': str(attestation['approved_by']).strip(),
            'summary': summary,
            'evidence_ref': str(attestation['evidence_ref']).strip(),
            'reviewed_at': str(attestation['reviewed_at']).strip(),
            'review_age_days': review_age_days,
            'max_review_age_days': RELEASE_GATE_ATTESTATION_MAX_AGE_DAYS,
            'evidence_schema_version': evidence_schema_version,
            'validation_policy_version': validation_policy_version,
            'acceptance_floors_ref': str(attestation['acceptance_floors_ref']).strip(),
            'acceptance_floors': acceptance_floors,
            'measured_results': measured_results,
        }
    if invalid:
        raise ValueError(f'invalid release gate attestation(s): {invalid}')
    return validated


def _validate_partner_evidence_validation_policy(payload: dict[str, Any] | None) -> None:
    if payload is None:
        return
    schema_version = str(payload.get('schema_version') or '')
    policy_version = str(payload.get('validation_policy_version') or '')
    if schema_version != PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION:
        raise ValueError(
            'partner evidence validation schema mismatch: '
            f'expected {PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION}, got {schema_version or "missing"}'
        )
    if policy_version != VALIDATION_POLICY_VERSION:
        raise ValueError(
            'partner evidence validation policy mismatch: '
            f'expected {VALIDATION_POLICY_VERSION}, got {policy_version or "missing"}'
        )


def build_contract(
    *,
    status_overrides: dict[str, str] | None = None,
    generated_at: datetime | None = None,
    release_gates: dict[str, bool] | None = None,
    partner_evidence_validation: dict[str, Any] | None = None,
    not_applicable_waivers: dict[str, Any] | None = None,
    release_gate_attestations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    _validate_partner_evidence_validation_policy(partner_evidence_validation)
    overrides = status_overrides or {}
    known = _requirement_by_key()
    unknown = sorted(set(overrides) - set(known))
    if unknown:
        raise ValueError(f'unknown Himalayan accuracy requirement override(s): {unknown}')
    validated_waivers = _validate_not_applicable_waivers(
        status_overrides=overrides,
        known_requirements=known,
        not_applicable_waivers=not_applicable_waivers,
        generated_at=generated_at,
    )
    requirements = []
    invalid = []
    for item in REQUIREMENTS:
        status = overrides.get(item.key, item.current_status)
        if status not in ALLOWED_STATUSES:
            invalid.append({'key': item.key, 'status': status})
            status = item.current_status
        payload = item.as_dict()
        payload['current_status'] = status
        requirements.append(payload)
    if invalid:
        raise ValueError(f'invalid Himalayan accuracy status override(s): {invalid}')

    supplied_release_gates = release_gates or {}
    if release_gates is None and release_gate_attestations:
        supplied_release_gates = {gate: gate in release_gate_attestations for gate in REQUIRED_RELEASE_GATES}
    unknown_gates = sorted(set(supplied_release_gates) - set(REQUIRED_RELEASE_GATES))
    if unknown_gates:
        raise ValueError(f'unknown release gate(s): {unknown_gates}')
    gate_status = {gate: bool(supplied_release_gates.get(gate, False)) for gate in REQUIRED_RELEASE_GATES}
    validated_release_gate_attestations = _validate_release_gate_attestations(
        release_gates=gate_status,
        release_gate_attestations=release_gate_attestations,
        generated_at=generated_at,
    )
    missing_requirements = [
        item['key'] for item in requirements if item['current_status'] == STATUS_PARTNER_REQUIRED
    ]
    blocked_gates = [gate for gate, passed in gate_status.items() if not passed]
    claim_allowed = not missing_requirements and not blocked_gates
    decision = 'ready_for_himalayan_accuracy_claim_review' if claim_allowed else 'blocked_pending_himalayan_evidence'
    payload = {
        'schema_version': SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'deprecated_schema_versions': list(DEPRECATED_SCHEMA_VERSIONS),
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': claim_allowed,
        'decision': decision,
        'allowed_statuses': sorted(ALLOWED_STATUSES),
        'release_gates': gate_status,
        'missing_requirements': missing_requirements,
        'blocked_release_gates': blocked_gates,
        'requirements': requirements,
    }
    if partner_evidence_validation is not None:
        payload['partner_evidence_validation'] = partner_evidence_validation
    if validated_waivers:
        payload['not_applicable_waivers'] = validated_waivers
    if validated_release_gate_attestations:
        payload['release_gate_attestations'] = validated_release_gate_attestations
    return payload


def load_status_overrides(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Himalayan accuracy status overrides must be a JSON object')
    return {str(key): str(value) for key, value in payload.items()}


def load_not_applicable_waivers(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Himalayan not_applicable waivers must be a JSON object')
    return {str(key): value for key, value in payload.items()}


def load_release_gate_attestations(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Himalayan release gate attestations must be a JSON object')
    return {str(key): value for key, value in payload.items()}


def load_partner_source_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Himalayan partner source manifest must be a JSON object')
    return payload


def write_contract(
    *,
    output_path: Path,
    status_overrides: dict[str, str] | None = None,
    release_gates: dict[str, bool] | None = None,
    partner_evidence_validation: dict[str, Any] | None = None,
    not_applicable_waivers: dict[str, Any] | None = None,
    release_gate_attestations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_contract(
        status_overrides=status_overrides,
        release_gates=release_gates,
        partner_evidence_validation=partner_evidence_validation,
        not_applicable_waivers=not_applicable_waivers,
        release_gate_attestations=release_gate_attestations,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    return payload


def partner_template_columns(requirement: EvidenceRequirement) -> tuple[str, ...]:
    columns: list[str] = []
    for column in (*requirement.required_fields, *COMMON_TEMPLATE_COLUMNS):
        if column not in columns:
            columns.append(column)
    return tuple(columns)


def build_partner_evidence_template_manifest(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    templates = []
    for requirement in REQUIREMENTS:
        templates.append(
            {
                'requirement_key': requirement.key,
                'category': requirement.category,
                'filename': f'{requirement.key}.csv',
                'columns': list(partner_template_columns(requirement)),
                'max_review_age_days': PARTNER_EVIDENCE_REVIEW_MAX_AGE_DAYS,
                'controlled_values': {
                    column: sorted(CONTROLLED_VALUE_SETS[column])
                    for column in partner_template_columns(requirement)
                    if column in CONTROLLED_VALUE_SETS
                },
                'minimum_rows_for_availability': requirement.minimum_rows_for_availability,
                'minimum_distinct_counts': dict(requirement.minimum_distinct_counts),
                'minimum_temporal_span_days': dict(requirement.minimum_temporal_span_days),
                'minimum_numeric_spans': dict(requirement.minimum_numeric_spans),
                'unlocks_top10_feature': requirement.unlocks_top10_feature,
                'needed_for_world_class': requirement.needed_for_world_class,
            }
        )
    return {
        'schema_version': PARTNER_TEMPLATE_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'deprecated_schema_versions': list(DEPRECATED_SCHEMA_VERSIONS),
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'templates_written_pending_partner_evidence',
        'templates': templates,
    }


def markdown_partner_evidence_templates(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Evidence Templates',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'These CSV templates convert the top-10 Himalayan accuracy blockers into reviewed partner inputs. '
        'They do not authorize production scoring or a Himalayan accuracy claim.',
        '',
        '| Requirement | Template | Minimum reviewed rows | Minimum distinct coverage | Minimum span coverage | Controlled fields | Columns |',
        '|---|---|---:|---|---|---|---|',
    ]
    for template in payload['templates']:
        temporal_spans = [
            f"`{column}` >= {days:g} days"
            for column, days in template.get('minimum_temporal_span_days', {}).items()
        ]
        numeric_spans = [
            f"`{column}` >= {span:g}"
            for column, span in template.get('minimum_numeric_spans', {}).items()
        ]
        span_rules = temporal_spans + numeric_spans
        lines.append(
            '| {key} | `{filename}` | {minimum_rows} | {minimum_distinct} | {minimum_spans} | {controlled_fields} | {columns} |'.format(
                key=template['requirement_key'],
                filename=template['filename'],
                minimum_rows=template['minimum_rows_for_availability'],
                minimum_distinct=', '.join(
                    f"`{column}` >= {count}"
                    for column, count in template.get('minimum_distinct_counts', {}).items()
                ) or 'None',
                minimum_spans=', '.join(span_rules) or 'None',
                controlled_fields=', '.join(
                    f"`{column}`"
                    for column in template.get('controlled_values', {})
                ) or 'None',
                columns=', '.join(f"`{column}`" for column in template['columns']),
            )
        )
    lines.append('')
    return '\n'.join(lines)


def build_partner_source_manifest_template(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        'schema_version': PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'source_manifest_template_written_pending_partner_sources',
        'required_source_fields': list(REQUIRED_PARTNER_SOURCE_MANIFEST_FIELDS),
        'max_review_age_days': PARTNER_SOURCE_MANIFEST_MAX_AGE_DAYS,
        'allowed_license_scopes_for_research_validation': sorted(
            LICENSE_SCOPES_SUPPORTING_RESEARCH_VALIDATION
        ),
        'sources': [],
        'example_source': {
            'source_id': 'partner_source_package_001',
            'sha256': '<64-hex-sha256-of-source-package>',
            'source_owner': '<partner institution or data owner>',
            'dataset_name': '<dataset or source package name>',
            'license_scope': 'internal_research_validation',
            'date_range': 'YYYY-MM-DD/YYYY-MM-DD',
            'review_status': 'reviewed',
            'reviewer_id': '<named reviewer or review board id>',
            'reviewed_at': 'YYYY-MM-DDTHH:MM:SS+00:00',
            'evidence_package_ref': 'sha256:<64-hex-review-artifact-digest>',
        },
        'source_ref_usage': {
            'hash_only': 'sha256:<64-hex-sha256-of-source-package>',
            'local_file': 'file:raw_sources/source_package.csv#sha256=<64-hex-sha256-of-source-package>',
        },
    }


def markdown_partner_source_manifest_template(payload: dict[str, Any]) -> str:
    fields = payload['required_source_fields']
    lines = [
        '# Himalayan Partner Source Manifest Template',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'Use this JSON manifest beside the partner evidence CSVs. Every `source_ref` '
        'hash used in the CSV templates must appear here before the evidence can '
        'support a Himalayan accuracy-readiness claim.',
        '',
        f"Schema version: `{payload['schema_version']}`",
        f"Validation policy: `{payload['validation_policy_version']}`",
        f"Maximum source-review age: `{payload['max_review_age_days']:g}` days",
        '',
        '| Field | Requirement |',
        '|---|---|',
    ]
    field_descriptions = {
        'source_id': 'Stable partner-local identifier for the source package.',
        'sha256': '64-character SHA-256 digest referenced by partner evidence `source_ref` values.',
        'source_owner': 'Institution, agency, or data owner responsible for the source package.',
        'dataset_name': 'Human-readable source dataset or package name.',
        'license_scope': 'Controlled scope that must support research validation.',
        'date_range': 'Date coverage of the source package, preferably `YYYY-MM-DD/YYYY-MM-DD`.',
        'review_status': 'Must be `reviewed`.',
        'reviewer_id': 'Named reviewer, review board, or partner review identifier.',
        'reviewed_at': 'ISO-8601 review timestamp, no more than the maximum review age.',
        'evidence_package_ref': 'SHA-256-qualified reference to the review or evidence package.',
    }
    for field in fields:
        lines.append(f"| `{field}` | {field_descriptions[field]} |")
    lines.extend(
        [
            '',
            'Allowed license scopes for research validation:',
            '',
            ', '.join(f"`{scope}`" for scope in payload['allowed_license_scopes_for_research_validation']),
            '',
            'Example `source_ref` values:',
            '',
            f"- Hash only: `{payload['source_ref_usage']['hash_only']}`",
            f"- Local file: `{payload['source_ref_usage']['local_file']}`",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_source_manifest_starter(
    evidence_root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    source_refs: dict[str, dict[str, Any]] = {}
    invalid_examples: list[dict[str, Any]] = []
    invalid_count = 0
    missing_evidence_files: list[str] = []
    scanned_files: list[str] = []

    for requirement in REQUIREMENTS:
        filename = f'{requirement.key}.csv'
        path = evidence_root / filename
        if not path.is_file():
            missing_evidence_files.append(filename)
            continue
        scanned_files.append(filename)
        with path.open('r', encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            if 'source_ref' not in (reader.fieldnames or []):
                continue
            for row_number, row in enumerate(reader, start=2):
                raw_source_ref = row.get('source_ref')
                if _is_blank(raw_source_ref):
                    continue
                digest = _extract_declared_sha256(raw_source_ref)
                if digest is None:
                    invalid_count += 1
                    if len(invalid_examples) < 5:
                        invalid_examples.append(
                            {
                                'file': filename,
                                'row_number': row_number,
                                'source_ref': str(raw_source_ref).strip(),
                                'error': 'source_ref must include a valid sha256 digest',
                            }
                        )
                    continue
                record = source_refs.setdefault(
                    digest,
                    {
                        'sha256': digest,
                        'source_ref_count': 0,
                        'requirements': set(),
                        'reference_kinds': {},
                        'source_ref_examples': [],
                    },
                )
                record['source_ref_count'] += 1
                record['requirements'].add(requirement.key)
                reference_kind = _reference_kind(raw_source_ref)
                record['reference_kinds'][reference_kind] = record['reference_kinds'].get(reference_kind, 0) + 1
                if len(record['source_ref_examples']) < 3:
                    record['source_ref_examples'].append(str(raw_source_ref).strip())

    sources = []
    source_ref_summary = []
    for index, digest in enumerate(sorted(source_refs), start=1):
        record = source_refs[digest]
        source_id = f'pending_source_{index:03d}'
        sources.append(
            {
                'source_id': source_id,
                'sha256': digest,
                'source_owner': '',
                'dataset_name': '',
                'license_scope': 'pending_license_review',
                'date_range': '',
                'review_status': 'pending',
                'reviewer_id': '',
                'reviewed_at': '',
                'evidence_package_ref': '',
            }
        )
        source_ref_summary.append(
            {
                'source_id': source_id,
                'sha256': digest,
                'source_ref_count': record['source_ref_count'],
                'requirements': sorted(record['requirements']),
                'reference_kinds': dict(sorted(record['reference_kinds'].items())),
                'source_ref_examples': record['source_ref_examples'],
            }
        )

    return {
        'schema_version': PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': (
            'source_manifest_starter_written_pending_source_review'
            if sources
            else 'source_manifest_starter_no_source_refs_found'
        ),
        'evidence_root': str(evidence_root),
        'scanned_files': scanned_files,
        'missing_evidence_files': missing_evidence_files,
        'source_ref_digest_count': len(sources),
        'invalid_source_ref_count': invalid_count,
        'invalid_source_ref_examples': invalid_examples,
        'source_ref_summary': source_ref_summary,
        'starter_instructions': [
            'Fill source_owner, dataset_name, date_range, reviewer_id, reviewed_at, and evidence_package_ref for every source.',
            'Replace license_scope=pending_license_review with a research-validation-supported scope only after review.',
            'Replace review_status=pending with reviewed only after source-package review is complete.',
            'Run partner source-manifest validation before evidence validation.',
        ],
        'sources': sources,
    }


def markdown_partner_source_manifest_starter(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Source Manifest Starter',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This starter is generated from `source_ref` hashes found in submitted evidence CSVs. '
        'It is intentionally pending and does not validate until source owner, license, review, date, and evidence-package fields are completed.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Source ref digests | {payload['source_ref_digest_count']} |",
        f"| Invalid source refs | {payload['invalid_source_ref_count']} |",
        f"| Missing evidence files | {len(payload['missing_evidence_files'])} |",
        '',
        '## Source Ref Summary',
        '',
        '| Source id | SHA-256 | Ref count | Requirements | Reference kinds |',
        '|---|---|---:|---|---|',
    ]
    for item in payload['source_ref_summary']:
        lines.append(
            '| `{source_id}` | `{sha256}` | {count} | {requirements} | {kinds} |'.format(
                source_id=item['source_id'],
                sha256=item['sha256'],
                count=item['source_ref_count'],
                requirements=', '.join(f"`{key}`" for key in item['requirements']) or 'None',
                kinds=', '.join(f"`{key}`: {value}" for key, value in item['reference_kinds'].items()) or 'None',
            )
        )
    if not payload['source_ref_summary']:
        lines.append('| None | None | 0 | None | None |')
    lines.extend(['', '## Starter Instructions', ''])
    for instruction in payload['starter_instructions']:
        lines.append(f'- {instruction}')
    lines.extend(['', '## Invalid Source Ref Examples', ''])
    if payload['invalid_source_ref_examples']:
        lines.extend(['| File | Row | Source ref | Error |', '|---|---:|---|---|'])
        for example in payload['invalid_source_ref_examples']:
            lines.append(
                f"| `{example['file']}` | {example['row_number']} | `{example['source_ref']}` | {example['error']} |"
            )
    else:
        lines.append('- None')
    lines.append('')
    return '\n'.join(lines)


def build_partner_evidence_intake_checklist(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    template_manifest = build_partner_evidence_template_manifest(generated_at=generated_at)
    source_manifest_template = build_partner_source_manifest_template(generated_at=generated_at)
    evidence_files = [
        {
            'path': template['filename'],
            'type': 'evidence_csv',
            'requirement_key': template['requirement_key'],
            'minimum_reviewed_rows': template['minimum_rows_for_availability'],
            'minimum_distinct_counts': template['minimum_distinct_counts'],
            'minimum_temporal_span_days': template['minimum_temporal_span_days'],
            'minimum_numeric_spans': template['minimum_numeric_spans'],
            'required_columns': template['columns'],
        }
        for template in template_manifest['templates']
    ]
    return {
        'schema_version': PARTNER_INTAKE_CHECKLIST_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_intake_checklist_written_pending_partner_submission',
        'required_package_files': [
            {
                'path': 'partner_source_manifest.json',
                'type': 'source_manifest',
                'required': True,
                'purpose': 'Maps every partner evidence source_ref SHA-256 value to owner, dataset, license, date range, reviewer, and evidence package.',
                'required_fields': source_manifest_template['required_source_fields'],
            },
            *evidence_files,
        ],
        'validation_outputs': [
            'partner_source_manifest_validation.json',
            'partner_source_manifest_validation.md',
            'partner_evidence_validation.json',
            'partner_evidence_validation.md',
            'readiness_contract.json',
            'readiness_contract.md',
        ],
        'intake_steps': [
            {
                'step': 1,
                'name': 'Prepare source packages',
                'check': 'Compute SHA-256 for each source package and add it to partner_source_manifest.json.',
            },
            {
                'step': 2,
                'name': 'Complete source manifest',
                'check': 'Every source has owner, dataset, license_scope, date_range, review_status=reviewed, reviewer_id, reviewed_at, and evidence_package_ref.',
            },
            {
                'step': 3,
                'name': 'Fill evidence CSVs',
                'check': 'Use reviewed rows only; every source_ref must point to a manifest SHA-256 or a local file hash reference.',
            },
            {
                'step': 4,
                'name': 'Validate source manifest first',
                'check': 'Run the standalone source-manifest validation before full evidence validation.',
            },
            {
                'step': 5,
                'name': 'Validate all evidence',
                'check': 'Run the partner evidence validation and keep blocked outputs if any group is incomplete, stale, undersized, unlicensed, or unreviewed.',
            },
        ],
        'package_rules': {
            'source_manifest_required': True,
            'source_ref_formats': [
                'sha256:<64-hex-sha256-of-source-package>',
                'file:<relative-path>#sha256=<64-hex-sha256-of-source-package>',
            ],
            'evidence_max_review_age_days': PARTNER_EVIDENCE_REVIEW_MAX_AGE_DAYS,
            'source_manifest_max_review_age_days': PARTNER_SOURCE_MANIFEST_MAX_AGE_DAYS,
            'allowed_license_scopes_for_research_validation': sorted(
                LICENSE_SCOPES_SUPPORTING_RESEARCH_VALIDATION
            ),
            'review_status_required': 'reviewed',
            'future_review_skew_days_allowed': MAX_REVIEW_FUTURE_SKEW_DAYS,
        },
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The intake package is a data-submission checklist. Accuracy and production claims require validated local evidence plus release-gate attestations.',
        },
    }


def markdown_partner_evidence_intake_checklist(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Evidence Intake Checklist',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This checklist tells partners how to package local Himalayan evidence for validation. '
        'It does not authorize a Himalayan accuracy claim or production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Required package files | {len(payload['required_package_files'])} |",
        '',
        '## Intake Steps',
        '',
        '| Step | Name | Check |',
        '|---:|---|---|',
    ]
    for item in payload['intake_steps']:
        lines.append(f"| {item['step']} | {item['name']} | {item['check']} |")
    lines.extend(
        [
            '',
            '## Required Package Files',
            '',
            '| Path | Type | Requirement | Minimum reviewed rows |',
            '|---|---|---|---:|',
        ]
    )
    for item in payload['required_package_files']:
        lines.append(
            '| `{path}` | `{type}` | {requirement} | {minimum_rows} |'.format(
                path=item['path'],
                type=item['type'],
                requirement=item.get('requirement_key', 'source_manifest'),
                minimum_rows=item.get('minimum_reviewed_rows', 'n/a'),
            )
        )
    lines.extend(
        [
            '',
            '## Validation Outputs',
            '',
        ]
    )
    for output in payload['validation_outputs']:
        lines.append(f'- `{output}`')
    lines.extend(
        [
            '',
            '## Package Rules',
            '',
            f"- Source manifest required: `{str(payload['package_rules']['source_manifest_required']).lower()}`",
            f"- Review status required: `{payload['package_rules']['review_status_required']}`",
            f"- Evidence max review age: `{payload['package_rules']['evidence_max_review_age_days']:g}` days",
            f"- Source manifest max review age: `{payload['package_rules']['source_manifest_max_review_age_days']:g}` days",
            '- Allowed license scopes: '
            + ', '.join(
                f"`{scope}`"
                for scope in payload['package_rules']['allowed_license_scopes_for_research_validation']
            ),
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_intake_dry_run_runbook(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    checklist = build_partner_evidence_intake_checklist(generated_at=generated_at)
    required_files = [item['path'] for item in checklist['required_package_files']]
    return {
        'schema_version': PARTNER_INTAKE_DRY_RUN_RUNBOOK_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_intake_dry_run_runbook_written_pending_partner_package',
        'operator_inputs': [
            {
                'name': '<partner-package-root>',
                'description': 'Directory containing partner_source_manifest.json, raw_sources/, and ten filled evidence CSV files.',
                'required': True,
            },
            {
                'name': '<previous-manifest-diff-json>',
                'description': 'Optional previous partner_submission_manifest_diff.json for resubmission comparison.',
                'required': False,
            },
        ],
        'required_partner_files': required_files,
        'dry_run_steps': [
            {
                'step': 1,
                'name': 'Confirm package files',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json '
                    '--partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md'
                ),
                'expected_pass_decision': 'partner_intake_package_files_present',
                'expected_blocked_decision': 'blocked_missing_partner_intake_files',
                'stop_if_blocked': True,
            },
            {
                'step': 2,
                'name': 'Validate source manifest',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json '
                    '--partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md'
                ),
                'expected_pass_decision': 'partner_source_manifest_available',
                'expected_blocked_decision': 'partner_source_manifest_not_supplied or blocked_invalid_partner_source_manifest',
                'stop_if_blocked': True,
            },
            {
                'step': 3,
                'name': 'Validate evidence rows',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json '
                    '--partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md'
                ),
                'expected_pass_decision': 'all_partner_evidence_available',
                'expected_blocked_decision': 'blocked_pending_partner_evidence',
                'stop_if_blocked': True,
            },
            {
                'step': 4,
                'name': 'Score and summarize submission',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json '
                    '--partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md '
                    '--partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json '
                    '--partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md '
                    '--partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json '
                    '--partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md'
                ),
                'expected_pass_decision': 'partner_submission_evidence_available_release_gates_pending',
                'expected_blocked_decision': 'blocked_submission_checks_not_run or blocked_<first_blocker>',
                'stop_if_blocked': False,
            },
            {
                'step': 5,
                'name': 'Capture manifest diff',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json '
                    '--partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md'
                ),
                'optional_previous_snapshot_flag': '--partner-submission-manifest-diff-previous <previous-manifest-diff-json>',
                'expected_pass_decision': 'partner_submission_manifest_diff_baseline_written or partner_submission_manifest_diff_changed',
                'expected_blocked_decision': 'blocked_manifest_diff_current_package_incomplete',
                'stop_if_blocked': False,
            },
        ],
        'interpretation_rules': [
            'A dry-run pass means the package is structurally ready for scientist review, not production.',
            'Any blocked preflight, source-manifest, or evidence-validation decision should be returned to the partner before scientist review.',
            'A quality score is evidence-package readiness, not model accuracy.',
            'Release-gate readiness requires separate accepted holdout, scientist-review, license-clearance, and promotion attestations.',
            'Never copy synthetic fixture rows into a partner package.',
        ],
        'expected_current_template_status': {
            'decision': 'blocked_missing_partner_intake_files',
            'reason': 'The generated template folder intentionally lacks partner_source_manifest.json and real reviewed rows.',
        },
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This runbook is an operator procedure. It does not provide partner evidence, scientific acceptance, or production authorization.',
        },
    }


def markdown_partner_intake_dry_run_runbook(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Intake Dry-Run Runbook',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This runbook tells an operator how to dry-run a real Himalayan partner submission package. '
        'It is a procedure artifact only and does not authorize claims.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Required partner files | {len(payload['required_partner_files'])} |",
        '',
        '## Operator Inputs',
        '',
        '| Name | Required | Description |',
        '|---|---:|---|',
    ]
    for item in payload['operator_inputs']:
        lines.append(
            f"| `{item['name']}` | `{str(item['required']).lower()}` | {item['description']} |"
        )
    lines.extend(['', '## Dry-Run Steps', ''])
    for item in payload['dry_run_steps']:
        lines.extend(
            [
                f"### {item['step']}. {item['name']}",
                '',
                '```bash',
                item['command'],
                '```',
                '',
                f"- Expected pass decision: `{item['expected_pass_decision']}`",
                f"- Expected blocked decision: `{item['expected_blocked_decision']}`",
                f"- Stop if blocked: `{str(item['stop_if_blocked']).lower()}`",
                '',
            ]
        )
        if item.get('optional_previous_snapshot_flag'):
            lines.append(f"- Optional previous snapshot flag: `{item['optional_previous_snapshot_flag']}`")
            lines.append('')
    lines.extend(
        [
            '## Interpretation Rules',
            '',
        ]
    )
    for rule in payload['interpretation_rules']:
        lines.append(f'- {rule}')
    lines.extend(
        [
            '',
            '## Expected Current Template Status',
            '',
            f"- Decision: `{payload['expected_current_template_status']['decision']}`",
            f"- Reason: {payload['expected_current_template_status']['reason']}",
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_release_gate_attestation_template_pack(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    templates = []
    for gate in REQUIRED_RELEASE_GATES:
        templates.append(
            {
                'gate': gate,
                'required_fields': list(REQUIRED_RELEASE_GATE_ATTESTATION_FIELDS),
                'acceptance_floor_requirements': RELEASE_GATE_ACCEPTANCE_FLOOR_REQUIREMENTS[gate],
                'template': {
                    'approved_by': '<named-reviewer-or-authorizer>',
                    'summary': f'<summary of reviewed evidence for {gate}>',
                    'evidence_ref': 'sha256:<64-hex-digest-of-evidence-pack>',
                    'reviewed_at': '<ISO-8601 timestamp>',
                    'evidence_schema_version': PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
                    'validation_policy_version': VALIDATION_POLICY_VERSION,
                    'acceptance_floors_ref': 'sha256:<64-hex-digest-of-accepted-floor-document>',
                    'acceptance_floors': RELEASE_GATE_ACCEPTANCE_FLOOR_REQUIREMENTS[gate],
                    'measured_results': '<structured metrics/results meeting the acceptance_floors>',
                },
                'reviewer_instruction': (
                    'Replace every placeholder with reviewed evidence. Do not set the gate true '
                    'until measured_results satisfy acceptance_floors and evidence_ref/acceptance_floors_ref '
                    'are SHA-256-qualified.'
                ),
            }
        )
    return {
        'schema_version': RELEASE_GATE_ATTESTATION_TEMPLATE_PACK_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'release_gate_attestation_template_pack_written_pending_validated_evidence',
        'template_is_evidence': False,
        'release_gate_count': len(templates),
        'release_gate_order': list(REQUIRED_RELEASE_GATES),
        'attestation_max_age_days': RELEASE_GATE_ATTESTATION_MAX_AGE_DAYS,
        'required_attestation_fields': list(REQUIRED_RELEASE_GATE_ATTESTATION_FIELDS),
        'templates': templates,
        'operator_rules': [
            'Use this template only after partner evidence validation passes and scientist review is ready.',
            'Every gate needs a named approver, evidence digest, reviewed_at timestamp, acceptance floors, and measured results.',
            'Human approval text alone is insufficient without structured floors and measured results.',
            'Production scoring remains false even when claim-review gates pass; promotion requires a separate production path.',
        ],
        'standards_anchors': [
            {
                'name': 'NIST AI Risk Management Framework',
                'url': 'https://www.nist.gov/itl/ai-risk-management-framework',
                'use': 'Keep release decisions traceable, reviewed, and risk-governed before deployment claims.',
            },
            {
                'name': 'WMO WIGOS data quality monitoring',
                'url': 'https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms',
                'use': 'Require quality-controlled observation and evidence handling before operational use.',
            },
            {
                'name': 'ISO 19157 geospatial data quality',
                'url': 'https://www.iso.org/standard/78900.html',
                'use': 'Track geospatial completeness, lineage, consistency, and quality in release evidence.',
            },
            {
                'name': 'FAIR data principles',
                'url': 'https://www.go-fair.org/fair-principles/',
                'use': 'Keep final evidence reusable, source-referenced, and auditable.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This pack is a blank attestation template. It is not validated evidence, accepted release-gate proof, or production authorization.',
        },
    }


def markdown_release_gate_attestation_template_pack(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Release-Gate Attestation Template Pack',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This template pack tells reviewers how to document release-gate evidence after partner evidence passes. '
        'It is not evidence and does not authorize production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Template is evidence | `{str(payload['template_is_evidence']).lower()}` |",
        f"| Release gates | {payload['release_gate_count']} |",
        f"| Attestation max age days | {payload['attestation_max_age_days']:g} |",
        '',
        '## Gate Templates',
        '',
        '| Gate | Required Fields | Acceptance Floor Requirements |',
        '|---|---|---|',
    ]
    for item in payload['templates']:
        floor_bits = []
        for key, value in item['acceptance_floor_requirements'].items():
            if isinstance(value, (list, tuple)):
                floor_bits.append(f"`{key}`={', '.join(value)}")
            else:
                floor_bits.append(f"`{key}`={value}")
        lines.append(
            '| {gate} | {fields} | {floors} |'.format(
                gate=f"`{item['gate']}`",
                fields=', '.join(f"`{field}`" for field in item['required_fields']),
                floors=', '.join(floor_bits),
            )
        )
    lines.extend(['', '## Operator Rules', ''])
    for rule in payload['operator_rules']:
        lines.append(f'- {rule}')
    lines.extend(
        [
            '',
            '## Standards Anchors',
            '',
            '| Anchor | Use | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['standards_anchors']:
        lines.append(f"| {item['name']} | {item['use']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_himalayan_local_holdout_protocol(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        'schema_version': HIMALAYAN_LOCAL_HOLDOUT_PROTOCOL_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'local_himalayan_holdout_protocol_written_pending_partner_evidence',
        'protocol_is_evidence': False,
        'objective': (
            'Pre-register the independent Himalayan holdout split, leakage controls, '
            'metrics, acceptance floors, and reporting outputs before any local model '
            'selection or public accuracy claim.'
        ),
        'required_partner_inputs': [
            'partner_source_manifest.json',
            'station_metadata.csv',
            'weather_station_observations.csv',
            'snowpack_profile_features.csv',
            'danger_labels_and_bulletins.csv',
            'warning_region_polygons.csv',
            'historical_avalanche_events.csv',
            'remote_sensing_validation_scenes.csv',
            'terrain_ates_runout_validation.csv',
            'scientist_reviews.csv',
            'independent_himalayan_holdout.csv',
        ],
        'split_policy': {
            'holdout_split_value': 'independent_holdout',
            'minimum_holdout_ids': 1,
            'must_be_excluded_from_training': True,
            'must_be_excluded_from_threshold_selection': True,
            'must_be_excluded_from_calibration': True,
            'temporal_overlap_allowed': False,
            'source_ref_overlap_allowed': False,
            'region_and_elevation_breakdown_required': True,
            'five_level_danger_preserved_until_reviewed_mapping': True,
        },
        'leakage_controls': [
            'No holdout row may be used for feature selection, calibration, threshold tuning, or release-gate floor selection.',
            'No source_ref SHA-256 digest may appear in both training/calibration evidence and independent_himalayan_holdout evidence.',
            'Holdout dates and warning-region identifiers must be reported explicitly before evaluation.',
            'Any four-class danger mapping must include reviewed mapping notes from the original five-level label.',
            'Remote-sensing scenes used for model or threshold selection cannot be reused as fresh final holdout evidence.',
        ],
        'metric_groups': [
            {
                'group': 'classification',
                'metrics': [
                    'macro_f1',
                    'per_class_f1',
                    'high_danger_recall',
                    'confusion_matrix',
                    'class_support',
                ],
            },
            {
                'group': 'calibration',
                'metrics': [
                    'brier_score',
                    'expected_calibration_error',
                    'classwise_calibration_bins',
                    'expected_danger_before_after_calibration',
                ],
            },
            {
                'group': 'spatial_temporal',
                'metrics': [
                    'mean_day_accuracy',
                    'median_day_accuracy',
                    'region_accuracy',
                    'elevation_band_accuracy',
                    'station_count',
                    'warning_region_count',
                ],
            },
            {
                'group': 'event_and_remote_sensing',
                'metrics': [
                    'historical_event_recall',
                    'remote_sensing_precision',
                    'remote_sensing_recall',
                    'remote_sensing_f1',
                    'remote_sensing_false_positive_rate',
                ],
            },
        ],
        'acceptance_floors': HIMALAYAN_LOCAL_HOLDOUT_ACCEPTANCE_FLOORS,
        'required_report_outputs': [
            'himalayan_local_holdout_evaluation_report.json',
            'himalayan_local_holdout_evaluation_report.md',
            'himalayan_local_holdout_leakage_audit.json',
            'himalayan_local_holdout_metric_report.json',
            'himalayan_local_holdout_metric_report.md',
            'himalayan_local_holdout_region_breakdown.csv',
            'himalayan_local_holdout_calibration_bins.csv',
            'himalayan_local_holdout_confusion_matrix.csv',
            'himalayan_local_holdout_scientist_review_packet.md',
        ],
        'stop_conditions': [
            'Stop if partner_source_manifest.json is missing or stale.',
            'Stop if independent_himalayan_holdout.csv is missing, blank, or has no independent_holdout rows.',
            'Stop if leakage audit finds source_ref, date, station, region, or scene contamination.',
            'Stop if any acceptance floor is missed; report blocker instead of weakening thresholds.',
            'Stop before production scoring even when the holdout passes; production requires separate release-gate attestations.',
        ],
        'standards_anchors': [
            {
                'name': 'RAvaFcast v1.0.0',
                'url': 'https://gmd.copernicus.org/articles/17/7569/2024/',
                'use': 'Keep station classification, spatial interpolation, and elevation/region aggregation as separate evaluation surfaces.',
            },
            {
                'name': 'European Avalanche Warning Services danger scale',
                'url': 'https://www.avalanches.org/standards/avalanche-danger-scale/',
                'use': 'Preserve five-level danger semantics unless a reviewed mapping justifies aggregation.',
            },
            {
                'name': 'NIST AI Risk Management Framework',
                'url': 'https://www.nist.gov/itl/ai-risk-management-framework',
                'use': 'Pre-register evaluation and release evidence before any risky operational claim.',
            },
            {
                'name': 'ISO 19157 geospatial data quality',
                'url': 'https://www.iso.org/standard/78900.html',
                'use': 'Report geospatial completeness, lineage, consistency, and quality in holdout evidence.',
            },
            {
                'name': 'FAIR data principles',
                'url': 'https://www.go-fair.org/fair-principles/',
                'use': 'Keep holdout evidence source-referenced, reusable, and auditable.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This is a pre-registered protocol. It contains no local holdout results, no accepted release-gate attestation, and no production authorization.',
        },
    }


def markdown_himalayan_local_holdout_protocol(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Local Holdout Evaluation Protocol',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        payload['objective'],
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Protocol is evidence | `{str(payload['protocol_is_evidence']).lower()}` |",
        f"| Required partner inputs | {len(payload['required_partner_inputs'])} |",
        f"| Required report outputs | {len(payload['required_report_outputs'])} |",
        '',
        '## Acceptance Floors',
        '',
        '| Metric | Floor |',
        '|---|---:|',
    ]
    for key, value in payload['acceptance_floors'].items():
        if isinstance(value, bool):
            rendered = str(value).lower()
        else:
            rendered = f'{value:g}'
        lines.append(f"| `{key}` | `{rendered}` |")
    lines.extend(['', '## Split Policy', '', '| Rule | Value |', '|---|---:|'])
    for key, value in payload['split_policy'].items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"| `{key}` | `{rendered}` |")
    lines.extend(['', '## Leakage Controls', ''])
    for item in payload['leakage_controls']:
        lines.append(f'- {item}')
    lines.extend(['', '## Metric Groups', '', '| Group | Metrics |', '|---|---|'])
    for group in payload['metric_groups']:
        lines.append(
            f"| `{group['group']}` | {', '.join(f'`{metric}`' for metric in group['metrics'])} |"
        )
    lines.extend(['', '## Required Report Outputs', ''])
    for item in payload['required_report_outputs']:
        lines.append(f'- `{item}`')
    lines.extend(['', '## Stop Conditions', ''])
    for item in payload['stop_conditions']:
        lines.append(f'- {item}')
    lines.extend(
        [
            '',
            '## Standards Anchors',
            '',
            '| Anchor | Use | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['standards_anchors']:
        lines.append(f"| {item['name']} | {item['use']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def _split_source_references(value: object) -> list[str]:
    if _is_blank(value):
        return []
    return [
        part.strip()
        for part in re.split(r'[;,|]', str(value))
        if part.strip()
    ]


def _source_hashes_from_csv(path: Path, *, evidence_root: Path) -> tuple[set[str], int, list[dict[str, Any]]]:
    hashes: set[str] = set()
    issue_count = 0
    examples: list[dict[str, Any]] = []
    if not path.is_file():
        return hashes, issue_count, examples
    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            values = []
            if 'source_ref' in (reader.fieldnames or []):
                values.extend(_split_source_references(row.get('source_ref')))
            if 'source_refs' in (reader.fieldnames or []):
                values.extend(_split_source_references(row.get('source_refs')))
            for raw in values:
                digest = _extract_declared_sha256(raw)
                issue = _source_ref_integrity_issue(raw, evidence_root=evidence_root)
                if digest:
                    hashes.add(digest)
                if issue is not None:
                    issue_count += 1
                    if len(examples) < 5:
                        examples.append({'file': path.name, 'row_number': row_number, **issue})
    return hashes, issue_count, examples


def _collect_non_holdout_source_hashes(evidence_root: Path) -> set[str]:
    hashes: set[str] = set()
    for requirement in REQUIREMENTS:
        if requirement.key == 'independent_himalayan_holdout':
            continue
        path = evidence_root / f'{requirement.key}.csv'
        file_hashes, _, _ = _source_hashes_from_csv(path, evidence_root=evidence_root)
        hashes.update(file_hashes)
    return hashes


def build_himalayan_local_holdout_leakage_audit(
    evidence_root: Path,
    *,
    generated_at: datetime | None = None,
    partner_source_manifest: dict[str, Any] | None = None,
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    protocol = protocol or build_himalayan_local_holdout_protocol(generated_at=generated_at)
    source_manifest_validation = validate_partner_source_manifest(
        partner_source_manifest,
        generated_at=generated_at,
    )
    holdout_path = evidence_root / 'independent_himalayan_holdout.csv'
    holdout_rows: list[dict[str, Any]] = []
    row_issues: list[dict[str, Any]] = []
    holdout_hashes: set[str] = set()
    if holdout_path.is_file():
        with holdout_path.open('r', encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            required = set(_requirement_by_key()['independent_himalayan_holdout'].required_fields)
            missing_columns = sorted(required - set(reader.fieldnames or []))
            if missing_columns:
                row_issues.append({'row_number': 1, 'error': f'missing required column(s): {missing_columns}'})
            for row_number, row in enumerate(reader, start=2):
                if not any(str(value or '').strip() for value in row.values()):
                    continue
                holdout_rows.append(row)
                missing_fields = sorted(field for field in required if _is_blank(row.get(field)))
                if missing_fields:
                    row_issues.append(
                        {
                            'row_number': row_number,
                            'holdout_id': row.get('holdout_id'),
                            'error': f'missing required field(s): {missing_fields}',
                        }
                    )
                leakage_text = str(row.get('leakage_check') or '').strip().lower()
                required_leakage_terms = {'independent', 'training', 'threshold'}
                missing_terms = sorted(term for term in required_leakage_terms if term not in leakage_text)
                if missing_terms:
                    row_issues.append(
                        {
                            'row_number': row_number,
                            'holdout_id': row.get('holdout_id'),
                            'error': f'leakage_check must mention {missing_terms}',
                        }
                    )
                floors_text = str(row.get('acceptance_floors') or '').strip()
                missing_floor_keys = [
                    key for key in HIMALAYAN_LOCAL_HOLDOUT_ACCEPTANCE_FLOORS if key not in floors_text
                ]
                if missing_floor_keys:
                    row_issues.append(
                        {
                            'row_number': row_number,
                            'holdout_id': row.get('holdout_id'),
                            'error': f'acceptance_floors missing key(s): {missing_floor_keys}',
                        }
                    )
                source_refs = _split_source_references(row.get('source_refs'))
                if not source_refs:
                    row_issues.append(
                        {
                            'row_number': row_number,
                            'holdout_id': row.get('holdout_id'),
                            'error': 'source_refs must include at least one sha256-qualified source reference',
                        }
                    )
                for raw_ref in source_refs:
                    digest = _extract_declared_sha256(raw_ref)
                    if digest is None:
                        row_issues.append(
                            {
                                'row_number': row_number,
                                'holdout_id': row.get('holdout_id'),
                                'source_ref': raw_ref,
                                'error': 'source_refs item must include a valid sha256 digest',
                            }
                        )
                        continue
                    holdout_hashes.add(digest)
                    source_issue = _source_ref_integrity_issue(raw_ref, evidence_root=evidence_root)
                    if source_issue is not None:
                        row_issues.append({'row_number': row_number, **source_issue})

    non_holdout_hashes = _collect_non_holdout_source_hashes(evidence_root) if evidence_root.is_dir() else set()
    overlapping_hashes = sorted(holdout_hashes & non_holdout_hashes)
    manifest_hashes = set(source_manifest_validation.get('valid_source_hashes', []))
    missing_manifest_hashes = (
        sorted(holdout_hashes - manifest_hashes)
        if holdout_hashes and source_manifest_validation.get('decision') == 'partner_source_manifest_available'
        else sorted(holdout_hashes)
        if holdout_hashes
        else []
    )
    checks = [
        {
            'key': 'holdout_file_present',
            'passed': holdout_path.is_file(),
            'detail': str(holdout_path),
        },
        {
            'key': 'holdout_rows_present',
            'passed': bool(holdout_rows),
            'detail': len(holdout_rows),
        },
        {
            'key': 'holdout_rows_valid',
            'passed': not row_issues and bool(holdout_rows),
            'detail': len(row_issues),
        },
        {
            'key': 'source_manifest_covers_holdout',
            'passed': bool(holdout_hashes) and not missing_manifest_hashes,
            'detail': len(missing_manifest_hashes),
        },
        {
            'key': 'source_ref_no_overlap_with_non_holdout_evidence',
            'passed': bool(holdout_hashes) and not overlapping_hashes,
            'detail': len(overlapping_hashes),
        },
    ]
    if not holdout_path.is_file():
        decision = 'blocked_local_holdout_leakage_audit_missing_holdout_file'
    elif not holdout_rows:
        decision = 'blocked_local_holdout_leakage_audit_no_holdout_rows'
    elif row_issues:
        decision = 'blocked_local_holdout_leakage_audit_invalid_holdout_rows'
    elif missing_manifest_hashes:
        decision = 'blocked_local_holdout_leakage_audit_missing_source_manifest_hashes'
    elif overlapping_hashes:
        decision = 'blocked_local_holdout_leakage_audit_source_ref_overlap'
    else:
        decision = 'local_holdout_leakage_audit_passed_release_gate_attestation_required'
    return {
        'schema_version': HIMALAYAN_LOCAL_HOLDOUT_LEAKAGE_AUDIT_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'audit_is_prediction_evidence': False,
        'evidence_root': str(evidence_root),
        'holdout_path': str(holdout_path),
        'holdout_row_count': len(holdout_rows),
        'holdout_ids': sorted(
            {
                str(row.get('holdout_id') or '').strip()
                for row in holdout_rows
                if str(row.get('holdout_id') or '').strip()
            }
        ),
        'holdout_source_ref_count': len(holdout_hashes),
        'non_holdout_source_ref_count': len(non_holdout_hashes),
        'source_ref_overlap_count': len(overlapping_hashes),
        'missing_manifest_hash_count': len(missing_manifest_hashes),
        'row_issue_count': len(row_issues),
        'checks': checks,
        'row_issue_examples': row_issues[:10],
        'overlapping_source_hashes': overlapping_hashes[:10],
        'missing_manifest_hashes': missing_manifest_hashes[:10],
        'source_manifest_decision': source_manifest_validation.get('decision'),
        'acceptance_floors': protocol['acceptance_floors'],
        'next_actions': [
            'Supply a reviewed independent_himalayan_holdout.csv with at least one independent holdout row.'
            if not holdout_rows
            else 'Fix holdout row schema, leakage_check text, source_refs, and acceptance_floors.'
            if row_issues
            else 'Add every holdout source_ref digest to partner_source_manifest.json.'
            if missing_manifest_hashes
            else 'Move contaminated source_ref digests out of training/calibration evidence or define a fresh holdout.'
            if overlapping_hashes
            else 'Proceed to local holdout metric evaluation and release-gate attestation; do not enable production scoring.',
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The audit checks holdout leakage and source governance only. It is not model performance evidence or production authorization.',
        },
    }


def markdown_himalayan_local_holdout_leakage_audit(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Local Holdout Leakage Audit',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This audit checks whether the independent Himalayan holdout package is structurally present, source-governed, and uncontaminated by non-holdout evidence.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Audit is prediction evidence | `{str(payload['audit_is_prediction_evidence']).lower()}` |",
        f"| Holdout rows | {payload['holdout_row_count']} |",
        f"| Holdout source refs | {payload['holdout_source_ref_count']} |",
        f"| Non-holdout source refs | {payload['non_holdout_source_ref_count']} |",
        f"| Source-ref overlaps | {payload['source_ref_overlap_count']} |",
        f"| Missing manifest hashes | {payload['missing_manifest_hash_count']} |",
        f"| Row issues | {payload['row_issue_count']} |",
        '',
        '## Checks',
        '',
        '| Check | Passed | Detail |',
        '|---|---:|---:|',
    ]
    for check in payload['checks']:
        lines.append(f"| `{check['key']}` | `{str(check['passed']).lower()}` | {check['detail']} |")
    lines.extend(['', '## Row Issue Examples', ''])
    if payload['row_issue_examples']:
        for item in payload['row_issue_examples']:
            lines.append(f"- row `{item.get('row_number')}`: {item.get('error')}")
    else:
        lines.append('- None')
    lines.extend(['', '## Overlapping Source Hashes', ''])
    if payload['overlapping_source_hashes']:
        for digest in payload['overlapping_source_hashes']:
            lines.append(f'- `{digest}`')
    else:
        lines.append('- None')
    lines.extend(['', '## Next Actions', ''])
    for action in payload['next_actions']:
        lines.append(f'- {action}')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def _parse_danger_level(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed < 1 or parsed > 4:
        return None
    return parsed


def _parse_probability(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed < 0.0 or parsed > 1.0:
        return None
    return parsed


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _round_metric(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _read_local_holdout_prediction_rows(path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if not path.is_file():
        return [], []
    issues: list[dict[str, Any]] = []
    rows: list[dict[str, str]] = []
    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        missing_columns = sorted(set(HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_COLUMNS) - set(reader.fieldnames or []))
        if missing_columns:
            issues.append({'row_number': 1, 'error': f'missing required column(s): {missing_columns}'})
        for row_number, row in enumerate(reader, start=2):
            if not any(str(value or '').strip() for value in row.values()):
                continue
            rows.append({key: str(value or '').strip() for key, value in row.items()})
            missing_fields = [
                field
                for field in HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_COLUMNS
                if not str(row.get(field) or '').strip()
            ]
            if missing_fields:
                issues.append(
                    {
                        'row_number': row_number,
                        'holdout_id': row.get('holdout_id'),
                        'error': f'missing required field(s): {missing_fields}',
                    }
                )
                continue
            true_level = _parse_danger_level(row.get('true_danger_level_1_to_4'))
            predicted_level = _parse_danger_level(row.get('predicted_danger_level_1_to_4'))
            if true_level is None:
                issues.append(
                    {
                        'row_number': row_number,
                        'holdout_id': row.get('holdout_id'),
                        'error': 'true_danger_level_1_to_4 must be an integer from 1 to 4',
                    }
                )
            if predicted_level is None:
                issues.append(
                    {
                        'row_number': row_number,
                        'holdout_id': row.get('holdout_id'),
                        'error': 'predicted_danger_level_1_to_4 must be an integer from 1 to 4',
                    }
                )
            probabilities = [
                _parse_probability(row.get(f'probability_level_{level}'))
                for level in range(1, 5)
            ]
            if any(value is None for value in probabilities):
                issues.append(
                    {
                        'row_number': row_number,
                        'holdout_id': row.get('holdout_id'),
                        'error': 'probability_level_1..4 must each be decimal probabilities in [0, 1]',
                    }
                )
                continue
            probability_sum = sum(value for value in probabilities if value is not None)
            if abs(probability_sum - 1.0) > 0.02:
                issues.append(
                    {
                        'row_number': row_number,
                        'holdout_id': row.get('holdout_id'),
                        'error': 'probability_level_1..4 must sum to approximately 1.0',
                    }
                )
    return rows, issues


def _compute_local_holdout_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    labels = (1, 2, 3, 4)
    confusion = {truth: {predicted: 0 for predicted in labels} for truth in labels}
    day_totals: dict[str, list[int]] = {}
    region_totals: dict[str, list[int]] = {}
    brier_values: list[float] = []
    calibration_bins = [
        {'bin': index, 'lower': index / 10.0, 'upper': (index + 1) / 10.0, 'count': 0, 'correct': 0, 'confidence_sum': 0.0}
        for index in range(10)
    ]
    for row in rows:
        truth = _parse_danger_level(row.get('true_danger_level_1_to_4'))
        predicted = _parse_danger_level(row.get('predicted_danger_level_1_to_4'))
        if truth is None or predicted is None:
            continue
        probabilities = [
            _parse_probability(row.get(f'probability_level_{level}')) or 0.0
            for level in labels
        ]
        confusion[truth][predicted] += 1
        correct = int(truth == predicted)
        day_key = str(row.get('valid_at') or '').split('T')[0]
        region_key = str(row.get('region_id') or '').strip() or 'unknown'
        day_totals.setdefault(day_key, []).append(correct)
        region_totals.setdefault(region_key, []).append(correct)
        brier_values.append(
            sum(
                (probability - (1.0 if truth == level else 0.0)) ** 2
                for probability, level in zip(probabilities, labels)
            )
            / len(labels)
        )
        confidence = max(probabilities)
        bin_index = min(9, int(confidence * 10))
        calibration_bins[bin_index]['count'] += 1
        calibration_bins[bin_index]['correct'] += correct
        calibration_bins[bin_index]['confidence_sum'] += confidence

    class_metrics = []
    f1_values: list[float] = []
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[truth][label] for truth in labels if truth != label)
        false_negative = sum(confusion[label][predicted] for predicted in labels if predicted != label)
        support = sum(confusion[label].values())
        precision = _safe_divide(true_positive, true_positive + false_positive)
        recall = _safe_divide(true_positive, true_positive + false_negative)
        f1 = _safe_divide(2 * precision * recall, precision + recall)
        if support:
            f1_values.append(f1)
        class_metrics.append(
            {
                'class_label': label,
                'support': support,
                'precision': _round_metric(precision),
                'recall': _round_metric(recall),
                'f1': _round_metric(f1),
            }
        )

    day_accuracy = [
        _safe_divide(sum(values), len(values))
        for values in day_totals.values()
        if values
    ]
    region_breakdown = []
    for region_id, values in sorted(region_totals.items()):
        region_breakdown.append(
            {
                'region_id': region_id,
                'row_count': len(values),
                'accuracy': _round_metric(_safe_divide(sum(values), len(values))),
            }
        )
    high_danger_truth = sum(
        sum(confusion[truth][predicted] for predicted in labels)
        for truth in (3, 4)
    )
    high_danger_hits = sum(
        confusion[truth][predicted]
        for truth in (3, 4)
        for predicted in (3, 4)
    )
    ece = 0.0
    total_rows = len(rows)
    rendered_bins = []
    for item in calibration_bins:
        count = item['count']
        accuracy = _safe_divide(item['correct'], count)
        confidence = _safe_divide(item['confidence_sum'], count)
        ece += (count / total_rows) * abs(accuracy - confidence) if total_rows else 0.0
        rendered_bins.append(
            {
                'bin': item['bin'],
                'lower': _round_metric(item['lower']),
                'upper': _round_metric(item['upper']),
                'count': count,
                'accuracy': _round_metric(accuracy) if count else None,
                'mean_confidence': _round_metric(confidence) if count else None,
            }
        )
    return {
        'row_count': total_rows,
        'macro_f1': _round_metric(sum(f1_values) / len(f1_values) if f1_values else 0.0),
        'high_danger_recall': _round_metric(_safe_divide(high_danger_hits, high_danger_truth)),
        'brier_score': _round_metric(sum(brier_values) / len(brier_values) if brier_values else 0.0),
        'expected_calibration_error': _round_metric(ece),
        'mean_day_accuracy': _round_metric(sum(day_accuracy) / len(day_accuracy) if day_accuracy else 0.0),
        'median_day_accuracy': _round_metric(_median(day_accuracy) or 0.0),
        'min_region_accuracy': _round_metric(
            min((item['accuracy'] for item in region_breakdown if item['accuracy'] is not None), default=0.0)
        ),
        'class_metrics': class_metrics,
        'confusion_matrix': [
            {'true_label': truth, **{f'predicted_{predicted}': confusion[truth][predicted] for predicted in labels}}
            for truth in labels
        ],
        'region_breakdown': region_breakdown,
        'calibration_bins': rendered_bins,
    }


def build_himalayan_local_holdout_metric_report(
    evidence_root: Path,
    *,
    generated_at: datetime | None = None,
    leakage_audit: dict[str, Any] | None = None,
    partner_source_manifest: dict[str, Any] | None = None,
    predictions_path: Path | None = None,
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    protocol = protocol or build_himalayan_local_holdout_protocol(generated_at=generated_at)
    leakage_audit = leakage_audit or build_himalayan_local_holdout_leakage_audit(
        evidence_root,
        generated_at=generated_at,
        partner_source_manifest=partner_source_manifest,
        protocol=protocol,
    )
    predictions_path = predictions_path or (evidence_root / 'himalayan_local_holdout_predictions.csv')
    rows: list[dict[str, str]] = []
    row_issues: list[dict[str, Any]] = []
    metrics: dict[str, Any] | None = None
    leakage_passed = (
        leakage_audit.get('decision')
        == 'local_holdout_leakage_audit_passed_release_gate_attestation_required'
    )
    if leakage_passed and predictions_path.is_file():
        rows, row_issues = _read_local_holdout_prediction_rows(predictions_path)
        if rows and not row_issues:
            metrics = _compute_local_holdout_metrics(rows)

    floors = protocol['acceptance_floors']
    floor_results = []
    if metrics is not None:
        floor_results = [
            {
                'metric': 'macro_f1',
                'observed': metrics['macro_f1'],
                'floor': floors['macro_f1_min'],
                'passed': metrics['macro_f1'] >= floors['macro_f1_min'],
            },
            {
                'metric': 'high_danger_recall',
                'observed': metrics['high_danger_recall'],
                'floor': floors['high_danger_recall_min'],
                'passed': metrics['high_danger_recall'] >= floors['high_danger_recall_min'],
            },
            {
                'metric': 'brier_score',
                'observed': metrics['brier_score'],
                'floor': floors['brier_score_max'],
                'passed': metrics['brier_score'] <= floors['brier_score_max'],
            },
            {
                'metric': 'expected_calibration_error',
                'observed': metrics['expected_calibration_error'],
                'floor': floors['ece_max'],
                'passed': metrics['expected_calibration_error'] <= floors['ece_max'],
            },
            {
                'metric': 'mean_day_accuracy',
                'observed': metrics['mean_day_accuracy'],
                'floor': floors['mean_day_accuracy_min'],
                'passed': metrics['mean_day_accuracy'] >= floors['mean_day_accuracy_min'],
            },
            {
                'metric': 'min_region_accuracy',
                'observed': metrics['min_region_accuracy'],
                'floor': floors['region_accuracy_min'],
                'passed': metrics['min_region_accuracy'] >= floors['region_accuracy_min'],
            },
        ]

    if not leakage_passed:
        decision = 'blocked_local_holdout_metric_report_leakage_audit_not_passed'
    elif not predictions_path.is_file():
        decision = 'blocked_local_holdout_metric_report_missing_predictions'
    elif not rows:
        decision = 'blocked_local_holdout_metric_report_no_prediction_rows'
    elif row_issues:
        decision = 'blocked_local_holdout_metric_report_invalid_prediction_rows'
    elif all(item['passed'] for item in floor_results):
        decision = 'local_holdout_metrics_passed_release_gate_attestation_required'
    else:
        decision = 'blocked_local_holdout_metrics_below_acceptance_floors'

    return {
        'schema_version': HIMALAYAN_LOCAL_HOLDOUT_METRIC_REPORT_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'metric_report_is_prediction_evidence': bool(metrics is not None),
        'evidence_root': str(evidence_root),
        'predictions_path': str(predictions_path),
        'prediction_required_columns': list(HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_COLUMNS),
        'leakage_audit_decision': leakage_audit.get('decision'),
        'prediction_row_count': len(rows),
        'prediction_row_issue_count': len(row_issues),
        'row_issue_examples': row_issues[:10],
        'acceptance_floors': floors,
        'floor_results': floor_results,
        'metrics': metrics,
        'next_actions': [
            'Pass the local holdout leakage audit before metric evaluation.'
            if not leakage_passed
            else 'Write himalayan_local_holdout_predictions.csv with reviewed truth labels, model predictions, and class probabilities.'
            if not predictions_path.is_file()
            else 'Add at least one non-blank prediction row.'
            if not rows
            else 'Fix prediction CSV schema, danger-level values, and probability columns.'
            if row_issues
            else 'Treat missed floors as a research blocker; do not weaken acceptance thresholds.'
            if floor_results and not all(item['passed'] for item in floor_results)
            else 'Prepare local_himalayan_holdout_passed release-gate attestation; do not enable production scoring.',
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This report is a local holdout metric gate. It can support a release-gate attestation only after leakage, prediction rows, and all acceptance floors pass.',
        },
    }


def markdown_himalayan_local_holdout_metric_report(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Local Holdout Metric Report',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This report is the executable metric gate for the independent Himalayan holdout. '
        'It refuses to evaluate metrics unless the leakage audit passes first.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Metric report is prediction evidence | `{str(payload['metric_report_is_prediction_evidence']).lower()}` |",
        f"| Leakage audit decision | `{payload['leakage_audit_decision']}` |",
        f"| Prediction rows | {payload['prediction_row_count']} |",
        f"| Prediction row issues | {payload['prediction_row_issue_count']} |",
        '',
        '## Acceptance Floors',
        '',
        '| Metric | Observed | Floor | Passed |',
        '|---|---:|---:|---:|',
    ]
    if payload['floor_results']:
        for item in payload['floor_results']:
            lines.append(
                f"| `{item['metric']}` | {item['observed']} | {item['floor']} | `{str(item['passed']).lower()}` |"
            )
    else:
        lines.append('| Not evaluated |  |  | `false` |')
    lines.extend(['', '## Row Issue Examples', ''])
    if payload['row_issue_examples']:
        for item in payload['row_issue_examples']:
            lines.append(f"- row `{item.get('row_number')}`: {item.get('error')}")
    else:
        lines.append('- None')
    metrics = payload.get('metrics')
    if metrics:
        lines.extend(
            [
                '',
                '## Metric Summary',
                '',
                f"- Macro F1: `{metrics['macro_f1']}`",
                f"- High-danger recall: `{metrics['high_danger_recall']}`",
                f"- Brier score: `{metrics['brier_score']}`",
                f"- Expected calibration error: `{metrics['expected_calibration_error']}`",
                f"- Mean day accuracy: `{metrics['mean_day_accuracy']}`",
                f"- Minimum region accuracy: `{metrics['min_region_accuracy']}`",
                '',
                '## Per-Class Metrics',
                '',
                '| Class | Support | Precision | Recall | F1 |',
                '|---:|---:|---:|---:|---:|',
            ]
        )
        for item in metrics['class_metrics']:
            lines.append(
                f"| {item['class_label']} | {item['support']} | {item['precision']} | {item['recall']} | {item['f1']} |"
            )
    lines.extend(['', '## Next Actions', ''])
    for action in payload['next_actions']:
        lines.append(f'- {action}')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_himalayan_local_holdout_prediction_template(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    column_definitions = [
        {
            'column': 'holdout_id',
            'required': True,
            'expected_format': 'string matching independent_himalayan_holdout.csv holdout_id',
            'validation_rule': 'must be non-blank and source-governed by a passing leakage audit',
        },
        {
            'column': 'valid_at',
            'required': True,
            'expected_format': 'ISO-8601 date or timestamp',
            'validation_rule': 'used for mean and median day accuracy grouping',
        },
        {
            'column': 'region_id',
            'required': True,
            'expected_format': 'string matching reviewed warning region identifier',
            'validation_rule': 'used for minimum region accuracy grouping',
        },
        {
            'column': 'elevation_band',
            'required': True,
            'expected_format': 'reviewed elevation band label or all',
            'validation_rule': 'kept for future elevation-band accuracy reporting',
        },
        {
            'column': 'true_danger_level_1_to_4',
            'required': True,
            'expected_format': 'integer from 1 to 4',
            'validation_rule': 'must come from reviewed local holdout truth labels',
        },
        {
            'column': 'predicted_danger_level_1_to_4',
            'required': True,
            'expected_format': 'integer from 1 to 4',
            'validation_rule': 'must be generated without using holdout rows for training, calibration, or threshold selection',
        },
    ]
    for level in range(1, 5):
        column_definitions.append(
            {
                'column': f'probability_level_{level}',
                'required': True,
                'expected_format': 'decimal probability in [0, 1]',
                'validation_rule': 'probability_level_1..4 must sum to approximately 1.0 per row',
            }
        )
    return {
        'schema_version': HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_TEMPLATE_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'local_holdout_prediction_template_written_pending_model_outputs',
        'template_is_prediction_evidence': False,
        'csv_filename': 'himalayan_local_holdout_predictions.csv',
        'required_columns': list(HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_COLUMNS),
        'column_definitions': column_definitions,
        'validation_rules': [
            'Run the local holdout leakage audit before writing or evaluating prediction rows.',
            'Use one row per holdout prediction unit: holdout id, valid time, region, and elevation band.',
            'Preserve reviewed five-level source labels elsewhere; this template is the RF4-compatible evaluation view only.',
            'Do not include any training, calibration, threshold-selection, or non-independent holdout rows.',
            'Class probabilities must be generated by the frozen candidate being evaluated and must sum to approximately 1.0.',
            'A filled CSV is not sufficient for a Himalayan accuracy claim until all metric floors and release-gate attestations pass.',
        ],
        'metric_report_dependency': {
            'consumer_artifact': 'himalayan_local_holdout_metric_report.json',
            'required_before_evaluation': [
                'himalayan_local_holdout_leakage_audit.json decision passes',
                'himalayan_local_holdout_predictions.csv exists',
                'all rows satisfy required columns, danger-level ranges, and probability checks',
            ],
        },
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This template defines the required prediction-output shape. It is not evidence, model output, metric proof, or production authorization.',
        },
    }


def markdown_himalayan_local_holdout_prediction_template(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Local Holdout Prediction Template',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This template defines the CSV that the local holdout metric report consumes after the leakage audit passes.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Template is prediction evidence | `{str(payload['template_is_prediction_evidence']).lower()}` |",
        f"| CSV filename | `{payload['csv_filename']}` |",
        f"| Required columns | {len(payload['required_columns'])} |",
        '',
        '## Required Columns',
        '',
        '| Column | Format | Validation rule |',
        '|---|---|---|',
    ]
    for item in payload['column_definitions']:
        lines.append(
            f"| `{item['column']}` | {item['expected_format']} | {item['validation_rule']} |"
        )
    lines.extend(['', '## Validation Rules', ''])
    for item in payload['validation_rules']:
        lines.append(f'- {item}')
    lines.extend(
        [
            '',
            '## Metric Report Dependency',
            '',
            f"- Consumer artifact: `{payload['metric_report_dependency']['consumer_artifact']}`",
        ]
    )
    for item in payload['metric_report_dependency']['required_before_evaluation']:
        lines.append(f'- {item}')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def write_himalayan_local_holdout_prediction_template_csv(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_COLUMNS))
        writer.writeheader()


def build_partner_incoming_triage_runbook(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        'schema_version': PARTNER_INCOMING_TRIAGE_RUNBOOK_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_incoming_triage_runbook_written_pending_partner_package',
        'runbook_is_prediction_evidence': False,
        'objective': (
            'Give the operator a deterministic first-response sequence for a real Himalayan '
            'partner evidence package without enabling production scoring or accuracy claims.'
        ),
        'pre_arrival_preparation': [
            {
                'priority': 1,
                'task': 'Confirm the partner package root path and keep the original package read-only.',
                'rating': 5,
                'reason': 'Preserves provenance and prevents accidental edits to received evidence.',
            },
            {
                'priority': 2,
                'task': 'Regenerate the template bundle and package index in the local artifact area.',
                'rating': 5,
                'reason': 'Ensures current schema, command order, and claim boundaries are visible before intake.',
            },
            {
                'priority': 3,
                'task': 'Prepare a previous manifest-diff snapshot if this is a resubmission.',
                'rating': 4,
                'reason': 'Makes package changes auditable across partner attempts.',
            },
        ],
        'triage_sequence': [
            {
                'step': 1,
                'name': 'Preflight file presence',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json '
                    '--partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md'
                ),
                'stop_if_decision_not': 'partner_intake_package_files_present',
                'rating': 5,
            },
            {
                'step': 2,
                'name': 'Build source manifest starter if hashes are missing',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest-starter-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.json '
                    '--partner-source-manifest-starter-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.md'
                ),
                'stop_if_decision_not': None,
                'rating': 4,
            },
            {
                'step': 3,
                'name': 'Validate source manifest governance',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json '
                    '--partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md'
                ),
                'stop_if_decision_not': 'partner_source_manifest_available',
                'rating': 5,
            },
            {
                'step': 4,
                'name': 'Validate evidence CSV rows and source refs',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json '
                    '--partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md'
                ),
                'stop_if_decision_not': 'all_partner_evidence_available',
                'rating': 5,
            },
            {
                'step': 5,
                'name': 'Run local holdout leakage audit',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json '
                    '--local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md'
                ),
                'stop_if_decision_not': 'local_holdout_leakage_audit_passed_release_gate_attestation_required',
                'rating': 5,
            },
            {
                'step': 6,
                'name': 'Provide prediction-output template if model outputs are not ready',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json '
                    '--local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md '
                    '--local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv'
                ),
                'stop_if_decision_not': None,
                'rating': 4,
            },
            {
                'step': 7,
                'name': 'Evaluate holdout metrics only after predictions exist',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--local-holdout-predictions <partner-package-root>/himalayan_local_holdout_predictions.csv '
                    '--local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json '
                    '--local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md'
                ),
                'stop_if_decision_not': 'local_holdout_metrics_passed_release_gate_attestation_required',
                'rating': 5,
            },
            {
                'step': 8,
                'name': 'Write summary, score, checklist, ledger, and dashboard',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json '
                    '--partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md '
                    '--partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json '
                    '--partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md '
                    '--partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json '
                    '--partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md '
                    '--partner-submission-review-ledger-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.json '
                    '--partner-submission-review-ledger-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.md '
                    '--partner-submission-status-dashboard-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.json '
                    '--partner-submission-status-dashboard-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.md'
                ),
                'stop_if_decision_not': None,
                'rating': 5,
            },
        ],
        'routing_decisions': [
            {
                'condition': 'missing required files, stale review, unsupported licenses, invalid source refs, or failed leakage audit',
                'route': 'return_to_partner_for_resubmission',
                'rating': 5,
            },
            {
                'condition': 'evidence and leakage pass, but holdout predictions are missing',
                'route': 'request_frozen_candidate_predictions_using_template',
                'rating': 5,
            },
            {
                'condition': 'holdout metrics pass all floors',
                'route': 'prepare local_himalayan_holdout_passed attestation; keep production blocked',
                'rating': 5,
            },
            {
                'condition': 'holdout metrics miss any floor',
                'route': 'scientist/model-error review; do not weaken floors',
                'rating': 5,
            },
        ],
        'stop_conditions': [
            'Stop on missing package files before row-level validation.',
            'Stop on invalid or stale partner_source_manifest.json before evidence validation.',
            'Stop on evidence validation failures before leakage audit or metrics.',
            'Stop on leakage audit failures before metric evaluation.',
            'Stop on metric floor failures before release-gate attestation.',
            'Stop before production scoring even if every research gate passes.',
        ],
        'standards_anchors': [
            {
                'name': 'NIST AI RMF Measure function',
                'url': 'https://airc.nist.gov/airmf-resources/playbook/measure/',
                'use': 'Document test sets, metrics, tools, and stop conditions before claims.',
            },
            {
                'name': 'FAIR provenance principle R1.2',
                'url': 'https://www.go-fair.org/fair-principles/r1-2-metadata-associated-detailed-provenance/',
                'use': 'Keep source ownership, processing history, and reuse context explicit.',
            },
            {
                'name': 'RAvaFcast v1.0.0',
                'url': 'https://ui.adsabs.harvard.edu/abs/2024GMD....17.7569M/abstract',
                'use': 'Preserve separate classification, interpolation, aggregation, and evaluation stages.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The triage runbook is operator procedure only. It does not supply partner evidence, model predictions, metric proof, release-gate approval, or production authorization.',
        },
    }


def markdown_partner_incoming_triage_runbook(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Incoming Partner Package Triage Runbook',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        payload['objective'],
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Runbook is prediction evidence | `{str(payload['runbook_is_prediction_evidence']).lower()}` |",
        f"| Triage steps | {len(payload['triage_sequence'])} |",
        '',
        '## Pre-Arrival Preparation',
        '',
        '| Priority | Task | Rating | Reason |',
        '|---:|---|---:|---|',
    ]
    for item in payload['pre_arrival_preparation']:
        lines.append(
            f"| {item['priority']} | {item['task']} | {item['rating']} | {item['reason']} |"
        )
    lines.extend(['', '## Triage Sequence', ''])
    for item in payload['triage_sequence']:
        lines.extend(
            [
                f"### {item['step']}. {item['name']}",
                '',
                f"- Priority rating: `{item['rating']}/5`",
                f"- Stop unless decision is: `{item['stop_if_decision_not'] or 'not_applicable'}`",
                '',
                '```bash',
                item['command'],
                '```',
                '',
            ]
        )
    lines.extend(
        [
            '## Routing Decisions',
            '',
            '| Condition | Route | Rating |',
            '|---|---|---:|',
        ]
    )
    for item in payload['routing_decisions']:
        lines.append(f"| {item['condition']} | {item['route']} | {item['rating']} |")
    lines.extend(['', '## Stop Conditions', ''])
    for item in payload['stop_conditions']:
        lines.append(f'- {item}')
    lines.extend(
        [
            '',
            '## Standards Anchors',
            '',
            '| Anchor | Use | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['standards_anchors']:
        lines.append(f"| {item['name']} | {item['use']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_package_index(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    checklist = build_partner_evidence_intake_checklist(generated_at=generated_at)
    return {
        'schema_version': PARTNER_PACKAGE_INDEX_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_package_index_written_pending_partner_submission',
        'artifact_sequence': [
            {
                'step': 1,
                'artifact': 'partner_handoff_readme.md',
                'purpose': 'Compact first-read handoff that points to the package index, scorecard, acceptance checklist, examples, and resubmission commands.',
                'command_flags': [
                    '--partner-handoff-readme-output',
                    '--partner-handoff-readme-markdown',
                ],
            },
            {
                'step': 2,
                'artifact': 'partner_field_dictionary.md',
                'purpose': 'Defines field meanings, units, formats, controlled values, and non-lossy danger-scale guidance.',
                'command_flags': [
                    '--partner-field-dictionary-output',
                    '--partner-field-dictionary-markdown',
                ],
            },
            {
                'step': 3,
                'artifact': 'partner_sample_row_pack.md',
                'purpose': 'Shows example-only rows for each evidence CSV without creating submit-ready evidence files.',
                'command_flags': [
                    '--partner-sample-row-pack-output',
                    '--partner-sample-row-pack-markdown',
                ],
            },
            {
                'step': 4,
                'artifact': 'partner_synthetic_validation_report.md',
                'purpose': 'Optional synthetic-only smoke package proving the validation chain can pass structurally without creating real Himalayan evidence.',
                'command_flags': [
                    '--partner-synthetic-validation-package-root',
                    '--partner-synthetic-validation-report-output',
                    '--partner-synthetic-validation-report-markdown',
                ],
            },
            {
                'step': 5,
                'artifact': 'partner_intake_checklist.md',
                'purpose': 'Defines the required source manifest, evidence CSVs, package rules, and validation outputs.',
                'command_flags': [
                    '--partner-intake-checklist-output',
                    '--partner-intake-checklist-markdown',
                ],
            },
            {
                'step': 6,
                'artifact': 'partner_intake_dry_run_runbook.md',
                'purpose': 'Operator runbook for dry-running a real submitted partner package while keeping claims blocked.',
                'command_flags': [
                    '--partner-intake-dry-run-runbook-output',
                    '--partner-intake-dry-run-runbook-markdown',
                ],
            },
            {
                'step': 7,
                'artifact': 'partner_incoming_triage_runbook.md',
                'purpose': 'First-response operator sequence for a real incoming partner package, including stop conditions and routing decisions.',
                'command_flags': [
                    '--partner-incoming-triage-runbook-output',
                    '--partner-incoming-triage-runbook-markdown',
                ],
            },
            {
                'step': 8,
                'artifact': 'partner_intake_preflight.md',
                'purpose': 'Checks whether the source manifest and ten evidence CSV files are present before row-level validation.',
                'command_flags': [
                    '--partner-intake-preflight-output',
                    '--partner-intake-preflight-markdown',
                ],
            },
            {
                'step': 9,
                'artifact': 'partner_source_manifest_starter.md',
                'purpose': 'Derives a fillable source manifest skeleton from source_ref hashes found in submitted evidence CSVs.',
                'command_flags': [
                    '--partner-source-manifest-starter-output',
                    '--partner-source-manifest-starter-markdown',
                ],
            },
            {
                'step': 10,
                'artifact': 'partner_source_manifest_validation.md',
                'purpose': 'Validates source ownership, dataset names, licenses, dates, reviewer identity, freshness, and SHA-256 references.',
                'command_flags': [
                    '--partner-source-manifest-validation-output',
                    '--partner-source-manifest-validation-markdown',
                ],
            },
            {
                'step': 11,
                'artifact': 'partner_evidence_validation.md',
                'purpose': 'Validates every partner evidence CSV for row count, coverage, values, freshness, licenses, and source references.',
                'command_flags': [
                    '--partner-evidence-validation-output',
                    '--partner-evidence-validation-markdown',
                ],
            },
            {
                'step': 12,
                'artifact': 'partner_submission_quality_score.md',
                'purpose': 'Scores package completeness, source governance, evidence coverage, review controls, and release-gate readiness.',
                'command_flags': [
                    '--partner-submission-quality-score-output',
                    '--partner-submission-quality-score-markdown',
                ],
            },
            {
                'step': 13,
                'artifact': 'partner_submission_acceptance_checklist.md',
                'purpose': 'Translates scorecard failures into partner-side fixes before scientist review or claim review.',
                'command_flags': [
                    '--partner-submission-acceptance-checklist-output',
                    '--partner-submission-acceptance-checklist-markdown',
                ],
            },
            {
                'step': 14,
                'artifact': 'partner_submission_manifest_diff.md',
                'purpose': 'Compares package file presence, hashes, sizes, row counts, and schema versions against a previous submission snapshot.',
                'command_flags': [
                    '--partner-submission-manifest-diff-output',
                    '--partner-submission-manifest-diff-markdown',
                ],
            },
            {
                'step': 15,
                'artifact': 'partner_submission_review_ledger.md',
                'purpose': 'Records each package attempt, fingerprint, score, blocker, review routing state, and resubmission action over time.',
                'command_flags': [
                    '--partner-submission-review-ledger-output',
                    '--partner-submission-review-ledger-markdown',
                ],
            },
            {
                'step': 16,
                'artifact': 'partner_submission_status_dashboard.md',
                'purpose': 'One-page operator/scientist status export summarizing blocker, score, top-10 readiness, routing state, and claim gates.',
                'command_flags': [
                    '--partner-submission-status-dashboard-output',
                    '--partner-submission-status-dashboard-markdown',
                ],
            },
            {
                'step': 17,
                'artifact': 'himalayan_local_holdout_protocol.md',
                'purpose': 'Pre-registers independent Himalayan holdout split rules, leakage checks, metrics, floors, and report outputs before evaluation.',
                'command_flags': [
                    '--local-holdout-protocol-output',
                    '--local-holdout-protocol-markdown',
                ],
            },
            {
                'step': 18,
                'artifact': 'himalayan_local_holdout_leakage_audit.md',
                'purpose': 'Checks independent holdout rows, source-ref manifest coverage, and source-ref overlap before metric evaluation.',
                'command_flags': [
                    '--local-holdout-leakage-audit-output',
                    '--local-holdout-leakage-audit-markdown',
                ],
            },
            {
                'step': 19,
                'artifact': 'himalayan_local_holdout_prediction_template.md',
                'purpose': 'Defines the header-only predictions CSV that the local holdout metric report consumes after leakage audit pass.',
                'command_flags': [
                    '--local-holdout-prediction-template-output',
                    '--local-holdout-prediction-template-markdown',
                    '--local-holdout-prediction-template-csv',
                ],
            },
            {
                'step': 20,
                'artifact': 'himalayan_local_holdout_metric_report.md',
                'purpose': 'Blocks metric evaluation until the leakage audit passes, then reports local holdout classification, calibration, and region floors.',
                'command_flags': [
                    '--local-holdout-metric-report-output',
                    '--local-holdout-metric-report-markdown',
                    '--local-holdout-predictions',
                ],
            },
            {
                'step': 21,
                'artifact': 'partner_submission_summary.md',
                'purpose': 'Combines preflight, source-manifest validation, evidence validation, and readiness status into one first-blocker report.',
                'command_flags': [
                    '--partner-submission-summary-output',
                    '--partner-submission-summary-markdown',
                ],
            },
            {
                'step': 22,
                'artifact': 'partner_source_package_checksum_guide.md',
                'purpose': 'Explains SHA-256 source-package checksums, source_ref syntax, and partner_source_manifest.json handoff rules.',
                'command_flags': [
                    '--partner-source-package-checksum-guide-output',
                    '--partner-source-package-checksum-guide-markdown',
                ],
            },
            {
                'step': 23,
                'artifact': 'release_gate_attestation_template_pack.md',
                'purpose': 'Fillable template pack for holdout, scientist-review, license, and promotion attestations after evidence passes.',
                'command_flags': [
                    '--release-gate-attestation-template-pack-output',
                    '--release-gate-attestation-template-pack-markdown',
                ],
            },
            {
                'step': 24,
                'artifact': 'readiness_contract.md',
                'purpose': 'Shows the release-gated Himalayan accuracy-readiness contract after validated evidence and attestations are applied.',
                'command_flags': [
                    '--output',
                    '--output-markdown',
                ],
            },
        ],
        'required_partner_files': [
            {
                'path': item['path'],
                'type': item['type'],
                'requirement_key': item.get('requirement_key', 'source_manifest'),
            }
            for item in checklist['required_package_files']
        ],
        'command_order': [
            {
                'step': 1,
                'name': 'Generate templates and package index',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--templates-output-root backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates '
                    '--partner-handoff-readme-output backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_readme.json '
                    '--partner-handoff-readme-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_handoff_readme.md '
                    '--partner-field-dictionary-output backend/artifacts/reproduction/himalayan_accuracy/partner_field_dictionary.json '
                    '--partner-field-dictionary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_field_dictionary.md '
                    '--partner-sample-row-pack-output backend/artifacts/reproduction/himalayan_accuracy/partner_sample_row_pack.json '
                    '--partner-sample-row-pack-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_sample_row_pack.md '
                    '--partner-source-package-checksum-guide-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_package_checksum_guide.json '
                    '--partner-source-package-checksum-guide-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_package_checksum_guide.md '
                    '--partner-synthetic-validation-package-root backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_package '
                    '--partner-synthetic-validation-report-output backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_report.json '
                    '--partner-synthetic-validation-report-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_synthetic_validation_report.md '
                    '--partner-intake-dry-run-runbook-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_dry_run_runbook.json '
                    '--partner-intake-dry-run-runbook-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_dry_run_runbook.md '
                    '--partner-incoming-triage-runbook-output backend/artifacts/reproduction/himalayan_accuracy/partner_incoming_triage_runbook.json '
                    '--partner-incoming-triage-runbook-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_incoming_triage_runbook.md '
                    '--release-gate-attestation-template-pack-output backend/artifacts/reproduction/himalayan_accuracy/release_gate_attestation_template_pack.json '
                    '--release-gate-attestation-template-pack-markdown backend/artifacts/reproduction/himalayan_accuracy/release_gate_attestation_template_pack.md '
                    '--partner-package-index-output backend/artifacts/reproduction/himalayan_accuracy/partner_package_index.json '
                    '--partner-package-index-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_package_index.md'
                ),
            },
            {
                'step': 2,
                'name': 'Preflight submitted package files',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json '
                    '--partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md'
                ),
            },
            {
                'step': 3,
                'name': 'Generate source manifest starter if needed',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest-starter-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.json '
                    '--partner-source-manifest-starter-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_starter.md'
                ),
            },
            {
                'step': 4,
                'name': 'Validate source manifest',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json '
                    '--partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md'
                ),
            },
            {
                'step': 5,
                'name': 'Validate partner evidence and summarize blockers',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json '
                    '--partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md '
                    '--partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json '
                    '--partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md '
                    '--partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json '
                    '--partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md '
                    '--partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json '
                    '--partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md '
                    '--partner-submission-review-ledger-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.json '
                    '--partner-submission-review-ledger-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_review_ledger.md '
                    '--partner-submission-status-dashboard-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.json '
                    '--partner-submission-status-dashboard-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_status_dashboard.md '
                    '--local-holdout-protocol-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_protocol.json '
                    '--local-holdout-protocol-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_protocol.md '
                    '--local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json '
                    '--local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md '
                    '--local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json '
                    '--local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md '
                    '--local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv '
                    '--local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json '
                    '--local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md '
                    '--partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json '
                    '--partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md '
                    '--local-holdout-leakage-audit-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.json '
                    '--local-holdout-leakage-audit-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_leakage_audit.md '
                    '--local-holdout-prediction-template-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.json '
                    '--local-holdout-prediction-template-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_prediction_template.md '
                    '--local-holdout-prediction-template-csv backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_predictions.csv '
                    '--local-holdout-metric-report-output backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.json '
                    '--local-holdout-metric-report-markdown backend/artifacts/reproduction/himalayan_accuracy/himalayan_local_holdout_metric_report.md'
                ),
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This index is a partner handoff map. Local Himalayan evidence, source governance, release attestations, and promotion approval are still required.',
        },
    }


def markdown_partner_package_index(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Evidence Package Index',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This index is the one-file handoff for the Himalayan partner evidence package. '
        'It links the checklist, preflight, source-manifest starter, validations, submission summary, and readiness contract.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Required partner files | {len(payload['required_partner_files'])} |",
        f"| Artifact sequence steps | {len(payload['artifact_sequence'])} |",
        '',
        '## Artifact Sequence',
        '',
        '| Step | Artifact | Purpose | Command flags |',
        '|---:|---|---|---|',
    ]
    for item in payload['artifact_sequence']:
        lines.append(
            '| {step} | `{artifact}` | {purpose} | {flags} |'.format(
                step=item['step'],
                artifact=item['artifact'],
                purpose=item['purpose'],
                flags=', '.join(f"`{flag}`" for flag in item['command_flags']),
            )
        )
    lines.extend(
        [
            '',
            '## Required Partner Files',
            '',
            '| Path | Type | Requirement |',
            '|---|---|---|',
        ]
    )
    for item in payload['required_partner_files']:
        lines.append(
            f"| `{item['path']}` | `{item['type']}` | {item['requirement_key']} |"
        )
    lines.extend(['', '## Command Order', ''])
    for item in payload['command_order']:
        lines.extend(
            [
                f"### {item['step']}. {item['name']}",
                '',
                '```bash',
                item['command'],
                '```',
                '',
            ]
        )
    lines.extend(
        [
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_source_package_checksum_guide(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        'schema_version': PARTNER_SOURCE_PACKAGE_CHECKSUM_GUIDE_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_source_package_checksum_guide_written_pending_partner_sources',
        'required_source_manifest_fields': list(REQUIRED_PARTNER_SOURCE_MANIFEST_FIELDS),
        'supported_reference_formats': [
            {
                'format': 'sha256:<64-hex-sha256-of-source-package>',
                'use': 'Use when the CSV source_ref points directly to a reviewed source package digest.',
            },
            {
                'format': 'file:raw_sources/<source-file>#sha256=<64-hex-sha256-of-source-package>',
                'use': 'Use when partners also provide a stable relative raw_sources path for review navigation.',
            },
        ],
        'checksum_commands': [
            {
                'platform': 'macos',
                'command': 'shasum -a 256 raw_sources/<source-file>',
                'expected_output': '<64-hex-sha256>  raw_sources/<source-file>',
            },
            {
                'platform': 'linux',
                'command': 'sha256sum raw_sources/<source-file>',
                'expected_output': '<64-hex-sha256>  raw_sources/<source-file>',
            },
            {
                'platform': 'python',
                'command': (
                    "/opt/homebrew/bin/python3 -c \"import hashlib, pathlib; "
                    "p=pathlib.Path('raw_sources/<source-file>'); "
                    "print(hashlib.sha256(p.read_bytes()).hexdigest(), p)\""
                ),
                'expected_output': '<64-hex-sha256> raw_sources/<source-file>',
            },
        ],
        'package_layout': [
            {
                'path': '<partner-package-root>/partner_source_manifest.json',
                'purpose': 'Reviewed source-governance manifest keyed by source_id and SHA-256 digest.',
            },
            {
                'path': '<partner-package-root>/raw_sources/<source-file>',
                'purpose': 'Immutable source package or source export used to compute source_ref digests.',
            },
            {
                'path': '<partner-package-root>/<evidence-template>.csv',
                'purpose': 'Filled evidence CSV whose source_ref values match partner_source_manifest.json.',
            },
        ],
        'workflow_steps': [
            'Freeze each raw source export or package before filling evidence CSV rows.',
            'Compute the SHA-256 digest from the frozen source file or source package.',
            'Add one partner_source_manifest.json source entry with sha256, owner, license, reviewer, reviewed_at, and evidence_package_ref.',
            'Use the same digest in each CSV source_ref that depends on that source.',
            'Run source-manifest validation, then full evidence validation, before scientist or claim review.',
        ],
        'common_mistakes': [
            'Hashing a file after editing it to fill CSV values.',
            'Using MD5, SHA-1, or a truncated digest instead of full SHA-256.',
            'Using an absolute private laptop path instead of a stable relative raw_sources path.',
            'Leaving evidence_package_ref blank in partner_source_manifest.json.',
            'Changing source files after checksums were recorded.',
            'Using a source with unreviewed, blocked, or unknown license scope.',
        ],
        'standards_anchors': [
            {
                'name': 'NIST FIPS 180-4 Secure Hash Standard',
                'url': 'https://csrc.nist.gov/pubs/fips/180-4/upd1/final',
                'use': 'Treat SHA-256 as the stable source integrity reference for partner evidence packages.',
            },
            {
                'name': 'Python hashlib documentation',
                'url': 'https://docs.python.org/3/library/hashlib.html',
                'use': 'Use hashlib.sha256 for deterministic local checksum reproduction.',
            },
            {
                'name': 'GNU coreutils sha256sum',
                'url': 'https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html',
                'use': 'Use sha256sum where GNU coreutils are available.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This guide documents provenance mechanics only. It is not source evidence, model validation, scientist review, or production authorization.',
        },
    }


def markdown_partner_source_package_checksum_guide(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Source Package Checksum Guide',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This guide explains how partners should compute SHA-256 checksums for frozen source packages, '
        'use those checksums in CSV `source_ref` fields, and mirror them in `partner_source_manifest.json`.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        '',
        '## Supported Reference Formats',
        '',
        '| Format | Use |',
        '|---|---|',
    ]
    for item in payload['supported_reference_formats']:
        lines.append(f"| `{item['format']}` | {item['use']} |")
    lines.extend(
        [
            '',
            '## Required Source Manifest Fields',
            '',
        ]
    )
    for field_name in payload['required_source_manifest_fields']:
        lines.append(f'- `{field_name}`')
    lines.extend(
        [
            '',
            '## Package Layout',
            '',
            '| Path | Purpose |',
            '|---|---|',
        ]
    )
    for item in payload['package_layout']:
        lines.append(f"| `{item['path']}` | {item['purpose']} |")
    lines.extend(['', '## Checksum Commands', ''])
    for item in payload['checksum_commands']:
        lines.extend(
            [
                f"### {item['platform']}",
                '',
                '```bash',
                item['command'],
                '```',
                '',
                f"Expected output: `{item['expected_output']}`",
                '',
            ]
        )
    lines.extend(['## Workflow', ''])
    for step in payload['workflow_steps']:
        lines.append(f'- {step}')
    lines.extend(['', '## Common Mistakes', ''])
    for mistake in payload['common_mistakes']:
        lines.append(f'- {mistake}')
    lines.extend(
        [
            '',
            '## Standards Anchors',
            '',
            '| Anchor | Use | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['standards_anchors']:
        lines.append(f"| {item['name']} | {item['use']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_himalayan_top10_feature_gap_matrix(
    *,
    generated_at: datetime | None = None,
    readiness_contract: dict[str, Any] | None = None,
    evidence_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    readiness_contract = readiness_contract or build_contract(generated_at=generated_at)
    statuses = {
        item['key']: item.get('current_status', STATUS_PARTNER_REQUIRED)
        for item in readiness_contract.get('requirements', [])
    }
    if evidence_validation:
        statuses.update(
            {
                key: value
                for key, value in evidence_validation.get('status_overrides', {}).items()
            }
        )
    features = []
    for definition in TOP10_FEATURE_DEFINITIONS:
        required = list(definition['required_evidence'])
        available = [key for key in required if statuses.get(key) == STATUS_AVAILABLE]
        blocked = [key for key in required if statuses.get(key) != STATUS_AVAILABLE]
        if not blocked:
            readiness_status = 'evidence_available_release_gates_pending'
            immediate_next_action = 'Run local model, spatial, scientist, and release-gate evaluation before any claim.'
        elif available:
            readiness_status = 'partially_available_partner_evidence_pending'
            immediate_next_action = f"Complete blocked evidence group(s): {', '.join(blocked)}."
        else:
            readiness_status = 'blocked_partner_evidence_required'
            immediate_next_action = str(definition['next_target'])
        features.append(
            {
                **definition,
                'required_evidence': required,
                'available_evidence': available,
                'blocked_evidence': blocked,
                'readiness_status': readiness_status,
                'immediate_next_action': immediate_next_action,
            }
        )
    blocked_feature_count = sum(
        1 for item in features if item['readiness_status'] != 'evidence_available_release_gates_pending'
    )
    return {
        'schema_version': HIMALAYAN_TOP10_FEATURE_GAP_MATRIX_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': (
            'top10_feature_gap_matrix_evidence_available_release_gates_pending'
            if blocked_feature_count == 0
            else 'top10_feature_gap_matrix_written_pending_partner_evidence'
        ),
        'confidence_position': 'not_100_percent_confident_local_himalayan_evidence_required',
        'rating_scale': '5 = implementation/evidence near needed standard; 1 = mostly missing',
        'feature_count': len(features),
        'blocked_feature_count': blocked_feature_count,
        'features': features,
        'external_anchors': [
            {
                'name': 'RAvaFcast v1.0.0',
                'url': 'https://gmd.copernicus.org/articles/17/7569/2024/',
                'implication': 'Treat best-class danger forecasting as a pipeline from station classification through spatial interpolation to elevation/region aggregation.',
            },
            {
                'name': 'NHESS 2022 RF danger labels',
                'url': 'https://nhess.copernicus.org/articles/22/2031/2022/',
                'implication': 'Separate raw forecasts from D_tidy-equivalent quality-controlled labels before training or claiming accuracy.',
            },
            {
                'name': 'European Avalanche Warning Services danger scale',
                'url': 'https://www.avalanches.org/standards/avalanche-danger-scale/',
                'implication': 'Preserve five-level danger semantics and avoid silent label collapse.',
            },
            {
                'name': 'WMO WIGOS data quality monitoring',
                'url': 'https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms',
                'implication': 'Treat observation readiness as a monitored data-quality pipeline.',
            },
            {
                'name': 'NHESS model-vs-human avalanche warning skill literature',
                'url': 'https://nhess.copernicus.org/articles/25/3333/2025/',
                'implication': 'Compare models against expert forecasts and outcomes, not aggregate accuracy alone.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This matrix is strategy and evidence-gap tracking only. It does not provide local Himalayan validation, release-gate attestations, or production authorization.',
        },
    }


def markdown_himalayan_top10_feature_gap_matrix(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Avalanche Prediction Top-10 Feature Gap Matrix',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This matrix keeps the best-in-class avalanche prediction strategy tied to the current evidence contract. '
        'It is research-only and does not authorize production scoring or a Himalayan accuracy claim.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Feature count | {payload['feature_count']} |",
        f"| Blocked feature count | {payload['blocked_feature_count']} |",
        f"| Confidence position | `{payload['confidence_position']}` |",
        '',
        '## Top-10 Matrix',
        '',
        '| # | Feature | Rating /5 | Readiness | Available Evidence | Blocked Evidence | Next Action |',
        '|---:|---|---:|---|---|---|---|',
    ]
    for item in payload['features']:
        lines.append(
            '| {rank} | {feature} | {rating} | `{readiness}` | {available} | {blocked} | {next_action} |'.format(
                rank=item['rank'],
                feature=item['feature'],
                rating=item['rating'],
                readiness=item['readiness_status'],
                available=', '.join(f"`{key}`" for key in item['available_evidence']) or 'None',
                blocked=', '.join(f"`{key}`" for key in item['blocked_evidence']) or 'None',
                next_action=item['immediate_next_action'],
            )
        )
    lines.extend(
        [
            '',
            '## External Anchors',
            '',
            '| Anchor | Implication | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['external_anchors']:
        lines.append(f"| {item['name']} | {item['implication']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_field_dictionary(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    used_by: dict[str, list[str]] = {}
    for requirement in REQUIREMENTS:
        for column in partner_template_columns(requirement):
            used_by.setdefault(column, []).append(requirement.key)
    field_definitions = []
    for column in sorted(used_by):
        guidance = FIELD_GUIDANCE.get(
            column,
            {
                'description': 'Partner-reviewed field required by one or more Himalayan evidence templates.',
                'expected_format': 'string or reviewed partner value',
                'unit': 'none',
            },
        )
        field_definitions.append(
            {
                'column': column,
                'description': guidance['description'],
                'expected_format': guidance['expected_format'],
                'unit': guidance['unit'],
                'controlled_values': sorted(CONTROLLED_VALUE_SETS.get(column, set())),
                'used_by_requirements': sorted(used_by[column]),
                'required_in_template_count': len(used_by[column]),
                'collection_note': (
                    'Preserve the original partner value in source systems; only map to this schema with reviewer notes.'
                ),
            }
        )
    template_guides = []
    for requirement in REQUIREMENTS:
        columns = list(partner_template_columns(requirement))
        template_guides.append(
            {
                'requirement_key': requirement.key,
                'filename': f'{requirement.key}.csv',
                'category': requirement.category,
                'required_columns': columns,
                'controlled_fields': [
                    column for column in columns if column in CONTROLLED_VALUE_SETS
                ],
                'minimum_rows_for_availability': requirement.minimum_rows_for_availability,
                'minimum_distinct_counts': dict(requirement.minimum_distinct_counts),
                'minimum_temporal_span_days': dict(requirement.minimum_temporal_span_days),
                'minimum_numeric_spans': dict(requirement.minimum_numeric_spans),
                'world_class_reason': requirement.needed_for_world_class,
            }
        )
    return {
        'schema_version': PARTNER_FIELD_DICTIONARY_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_field_dictionary_written_pending_partner_submission',
        'standards_anchors': [
            {
                'name': 'EAWS avalanche danger scale and avalanche problems',
                'url': 'https://www.avalanches.org/standards/',
                'usage': 'Preserve canonical danger and problem semantics before model-specific class mapping.',
            },
            {
                'name': 'CAAML-style avalanche data interchange',
                'url': 'https://caaml.org/',
                'usage': 'Keep evidence fields explicit enough for later structured data exchange and archival mapping.',
            },
        ],
        'scale_mapping_notes': [
            'danger_level_1_to_5 preserves the partner or operational five-level scale when available.',
            'danger_level_1_to_4 is the current RF4-compatible research label and must not be treated as canonical truth.',
            'If a reviewed level 5 occurs, keep danger_level_1_to_5=5 and document the four-class mapping in reviewer_notes before RF4 evaluation.',
        ],
        'field_count': len(field_definitions),
        'field_definitions': field_definitions,
        'template_guides': template_guides,
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The field dictionary defines data semantics only. It is not partner evidence and does not validate any prediction claim.',
        },
    }


def markdown_partner_field_dictionary(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Evidence Field Dictionary',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This dictionary defines field semantics for partner evidence CSVs. '
        'It is a submission guide, not evidence, and it does not authorize production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Field definitions | {payload['field_count']} |",
        '',
        '## Standards Anchors',
        '',
        '| Source | Use | URL |',
        '|---|---|---|',
    ]
    for item in payload['standards_anchors']:
        lines.append(f"| {item['name']} | {item['usage']} | {item['url']} |")
    lines.extend(['', '## Danger Scale Notes', ''])
    for note in payload['scale_mapping_notes']:
        lines.append(f'- {note}')
    lines.extend(
        [
            '',
            '## Field Definitions',
            '',
            '| Column | Description | Format | Unit | Controlled values | Used by |',
            '|---|---|---|---|---|---|',
        ]
    )
    for item in payload['field_definitions']:
        controlled_values = ', '.join(f"`{value}`" for value in item['controlled_values']) or 'None'
        used_by = ', '.join(f"`{value}`" for value in item['used_by_requirements'])
        lines.append(
            '| `{column}` | {description} | {expected_format} | {unit} | {controlled} | {used_by} |'.format(
                column=item['column'],
                description=item['description'],
                expected_format=item['expected_format'],
                unit=item['unit'],
                controlled=controlled_values,
                used_by=used_by,
            )
        )
    lines.extend(
        [
            '',
            '## Template Guides',
            '',
            '| Template | Category | Minimum rows | Controlled fields | World-class reason |',
            '|---|---|---:|---|---|',
        ]
    )
    for item in payload['template_guides']:
        controlled_fields = ', '.join(f"`{field}`" for field in item['controlled_fields']) or 'None'
        lines.append(
            '| `{filename}` | {category} | {rows} | {controlled_fields} | {reason} |'.format(
                filename=item['filename'],
                category=item['category'],
                rows=item['minimum_rows_for_availability'],
                controlled_fields=controlled_fields,
                reason=item['world_class_reason'],
            )
        )
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def _sample_value_for_column(column: str, row_index: int = 0) -> str:
    day = (row_index % 20) + 1
    sample_digest = '<64-hex-sha256-from-partner-source-manifest>'
    sample_source_ref = f'sha256:{sample_digest}'
    values = {
        'station_id': 'EXAMPLE_STATION_001',
        'region_key': 'EXAMPLE_HIMALAYAN_REGION_A',
        'region_id': 'EXAMPLE_REGION_A',
        'region_ids': 'EXAMPLE_REGION_A;EXAMPLE_REGION_B',
        'latitude': '31.2500',
        'longitude': '78.1200',
        'elevation_m': '3200',
        'active_date_range': '2026-01-01/2026-04-30',
        'valid_date_range': '2026-01-01/2026-04-30',
        'date_range': '2026-01-01/2026-02-20',
        'observed_at': f'2026-01-{day:02d}T06:00:00+00:00',
        'valid_from': f'2026-01-{day:02d}T00:00:00+00:00',
        'valid_to': f'2026-01-{day + 1:02d}T00:00:00+00:00',
        'acquired_at': f'2026-01-{day:02d}T10:00:00+00:00',
        'reviewed_at': f'2026-01-{day:02d}T12:00:00+00:00',
        'air_temp_c': '-6.5',
        'precipitation_mm': '8.2',
        'snowfall_cm': '18.0',
        'snow_depth_cm': '142.0',
        'wind_speed_ms': '9.5',
        'wind_dir_deg': '270',
        'layer_index': '1',
        'layer_depth_cm': '42',
        'grain_type': 'faceted_crystals',
        'hardness_index': '0.40',
        'stability_index': '0.62',
        'danger_scale_standard': 'eaws_5_level',
        'danger_level_1_to_5': '4',
        'danger_level_1_to_4': '4',
        'avalanche_problem': 'wind_slab',
        'elevation_band_policy': 'above_3000m',
        'forecaster_or_reviewer_id': 'EXAMPLE_REVIEWER',
        'polygon_geometry': 'POLYGON((78.0 31.1,78.3 31.1,78.3 31.4,78.0 31.4,78.0 31.1))',
        'crs': 'EPSG:4326',
        'elevation_policy': 'bands_2500_3000_3500m',
        'event_id': 'EXAMPLE_EVENT_001',
        'aspect': 'N',
        'observed_outcome': 'avalanche_observed',
        'confidence': '0.82',
        'source': 'partner_field_report',
        'scene_id': 'EXAMPLE_SCENE_001',
        'sensor': 'Sentinel-1',
        'preprocessing_level': 'reviewed_analysis_ready',
        'truth_mask_or_event_ref': 'EXAMPLE_EVENT_001',
        'holdout_split': 'independent_holdout',
        'dem_ref': sample_source_ref,
        'slope': '36',
        'terrain_class': 'challenging',
        'runout_validation_ref': sample_source_ref,
        'quality_flag': 'reviewed_valid',
        'review_id': 'EXAMPLE_REVIEW_001',
        'case_id': 'EXAMPLE_CASE_001',
        'verdict': 'label_valid',
        'label_quality': 'valid',
        'model_error_type': 'false_positive',
        'holdout_id': 'EXAMPLE_HOLDOUT_001',
        'leakage_check': 'independent_from_training_and_threshold_selection',
        'acceptance_floors': 'macro_f1_min=0.70;high_danger_recall_min=0.80;ece_max=0.08',
        'source_ref': sample_source_ref,
        'source_refs': f'{sample_source_ref};sha256:<second-64-hex-source-digest>',
        'license_scope': 'internal_research_validation',
        'review_status': 'EXAMPLE_ONLY_REPLACE_WITH_REVIEWED',
        'reviewer_id': 'EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION',
        'reviewer_notes': 'EXAMPLE ONLY - replace with real reviewer notes before submission.',
    }
    return values.get(column, f'EXAMPLE_{column.upper()}')


def build_partner_sample_row_pack(
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    examples = []
    for index, requirement in enumerate(REQUIREMENTS):
        columns = list(partner_template_columns(requirement))
        example_row = {
            column: _sample_value_for_column(column, row_index=index)
            for column in columns
        }
        examples.append(
            {
                'requirement_key': requirement.key,
                'filename': f'{requirement.key}.csv',
                'sample_only': True,
                'not_submit_ready': True,
                'reason_not_submit_ready': (
                    'Contains EXAMPLE values and placeholder SHA-256 references. '
                    'Partners must replace every EXAMPLE value, set review_status=reviewed, '
                    'and validate source_ref values through partner_source_manifest.json.'
                ),
                'columns': columns,
                'example_row': example_row,
            }
        )
    return {
        'schema_version': PARTNER_SAMPLE_ROW_PACK_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_sample_row_pack_written_example_only',
        'sample_rows_are_evidence': False,
        'examples_count': len(examples),
        'sample_row_policy': {
            'write_csv_files': False,
            'reason': 'Examples are JSON/Markdown guidance only so they cannot be accidentally validated as partner evidence.',
            'must_replace_before_submission': [
                'all EXAMPLE_* identifiers',
                'placeholder SHA-256 references',
                'review_status=EXAMPLE_ONLY_REPLACE_WITH_REVIEWED',
                'reviewer notes',
            ],
        },
        'examples': examples,
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'Sample rows are instructional examples only and are never accepted as reviewed Himalayan evidence.',
        },
    }


def markdown_partner_sample_row_pack(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Evidence Sample Row Pack',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'These rows are examples only. They are intentionally not submit-ready and must not be copied as evidence without replacing placeholders, source hashes, reviewer notes, and review status.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Sample rows are evidence | `{str(payload['sample_rows_are_evidence']).lower()}` |",
        f"| Example rows | {payload['examples_count']} |",
        '',
        '## Sample Row Policy',
        '',
        f"- Write CSV files: `{str(payload['sample_row_policy']['write_csv_files']).lower()}`",
        f"- Reason: {payload['sample_row_policy']['reason']}",
        '- Must replace before submission:',
    ]
    for item in payload['sample_row_policy']['must_replace_before_submission']:
        lines.append(f'  - {item}')
    lines.extend(['', '## Examples', ''])
    for item in payload['examples']:
        lines.extend(
            [
                f"### `{item['filename']}`",
                '',
                f"- Sample only: `{str(item['sample_only']).lower()}`",
                f"- Not submit-ready: `{str(item['not_submit_ready']).lower()}`",
                f"- Reason: {item['reason_not_submit_ready']}",
                '',
                '| Column | Example value |',
                '|---|---|',
            ]
        )
        for column in item['columns']:
            lines.append(f"| `{column}` | `{item['example_row'][column]}` |")
        lines.append('')
    lines.extend(
        [
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def _score_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _score_dimension(
    *,
    key: str,
    label: str,
    score: float,
    max_score: float,
    status: str,
    evidence: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    rounded_score = _rounded_float(score)
    rounded_max = _rounded_float(max_score)
    return {
        'key': key,
        'label': label,
        'score': rounded_score,
        'max_score': rounded_max,
        'score_ratio': _rounded_float(_score_ratio(rounded_score, rounded_max)),
        'status': status,
        'evidence': evidence,
        'next_action': next_action,
    }


def build_partner_submission_quality_score(
    *,
    generated_at: datetime | None = None,
    intake_preflight: dict[str, Any] | None = None,
    source_manifest_validation: dict[str, Any] | None = None,
    evidence_validation: dict[str, Any] | None = None,
    readiness_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)

    present_files = int(intake_preflight.get('present_file_count', 0)) if intake_preflight else 0
    required_files = int(intake_preflight.get('required_file_count', 0)) if intake_preflight else 0
    file_ratio = _score_ratio(present_files, required_files)
    file_status = (
        'passed'
        if intake_preflight and intake_preflight.get('decision') == 'partner_intake_package_files_present'
        else 'blocked'
        if intake_preflight
        else 'not_run'
    )
    package_dimension = _score_dimension(
        key='package_file_completeness',
        label='Required package files',
        score=15.0 * file_ratio,
        max_score=15.0,
        status=file_status,
        evidence={
            'decision': intake_preflight.get('decision') if intake_preflight else 'not_run',
            'present_file_count': present_files,
            'required_file_count': required_files,
            'missing_files': intake_preflight.get('missing_files', []) if intake_preflight else [],
        },
        next_action='Supply partner_source_manifest.json and all ten evidence CSV files.',
    )

    source_count = int(source_manifest_validation.get('source_count', 0)) if source_manifest_validation else 0
    valid_source_count = int(source_manifest_validation.get('valid_source_count', 0)) if source_manifest_validation else 0
    source_ratio = _score_ratio(valid_source_count, source_count)
    source_status = (
        'passed'
        if source_manifest_validation
        and source_manifest_validation.get('decision') == 'partner_source_manifest_available'
        else 'blocked'
        if source_manifest_validation
        else 'not_run'
    )
    source_dimension = _score_dimension(
        key='source_governance',
        label='Source manifest governance',
        score=20.0 * source_ratio,
        max_score=20.0,
        status=source_status,
        evidence={
            'decision': source_manifest_validation.get('decision') if source_manifest_validation else 'not_run',
            'source_count': source_count,
            'valid_source_count': valid_source_count,
            'invalid_source_count': (
                source_manifest_validation.get('invalid_source_count', 0)
                if source_manifest_validation
                else 0
            ),
        },
        next_action='Map every source_ref SHA-256 to owner, dataset, license, date range, reviewer, and evidence package.',
    )

    reports = list(evidence_validation.get('reports', [])) if evidence_validation else []
    report_count = len(reports)
    available_count = sum(1 for report in reports if report.get('status') == STATUS_AVAILABLE)
    row_ratio = _score_ratio(available_count, report_count)
    evidence_status = (
        'passed'
        if evidence_validation and evidence_validation.get('decision') == 'all_partner_evidence_available'
        else 'blocked'
        if evidence_validation
        else 'not_run'
    )
    evidence_dimension = _score_dimension(
        key='evidence_row_sufficiency',
        label='Evidence row sufficiency',
        score=20.0 * row_ratio,
        max_score=20.0,
        status=evidence_status,
        evidence={
            'decision': evidence_validation.get('decision') if evidence_validation else 'not_run',
            'available_requirements': evidence_validation.get('available_requirements', []) if evidence_validation else [],
            'blocked_requirements': evidence_validation.get('blocked_requirements', []) if evidence_validation else [],
            'available_requirement_count': available_count,
            'requirement_count': report_count,
        },
        next_action='Fill every evidence CSV with enough reviewed rows to meet the row floor.',
    )

    coverage_ratios = []
    for report in reports:
        if int(report.get('row_count', 0) or 0) <= 0:
            coverage_ratios.append(0.0)
            continue
        coverage_flags = [
            bool(report.get('sufficient_distinct_coverage')),
            bool(report.get('sufficient_temporal_coverage')),
            bool(report.get('sufficient_numeric_coverage')),
        ]
        coverage_ratios.append(sum(1 for flag in coverage_flags if flag) / len(coverage_flags))
    coverage_ratio = (
        sum(coverage_ratios) / len(coverage_ratios)
        if coverage_ratios
        else 0.0
    )
    coverage_dimension = _score_dimension(
        key='coverage_quality',
        label='Spatial, temporal, numeric coverage',
        score=20.0 * coverage_ratio,
        max_score=20.0,
        status='passed' if coverage_ratio >= 1.0 else 'blocked' if reports else 'not_run',
        evidence={
            'requirement_count': report_count,
            'coverage_ratio': _rounded_float(coverage_ratio),
            'shortfall_requirements': [
                report['requirement_key']
                for report in reports
                if int(report.get('row_count', 0) or 0) <= 0
                or not (
                    report.get('sufficient_distinct_coverage')
                    and report.get('sufficient_temporal_coverage')
                    and report.get('sufficient_numeric_coverage')
                )
            ],
        },
        next_action='Broaden station, region, scene, case, time, elevation, or slope coverage where required.',
    )

    review_ratios = []
    for report in reports:
        if int(report.get('row_count', 0) or 0) <= 0:
            review_ratios.append(0.0)
            continue
        review_flags = [
            report.get('review_freshness_status') == 'passed',
            report.get('license_scope_check_status') == 'passed',
            report.get('source_ref_integrity_status') == 'passed',
            report.get('source_ref_manifest_status') == 'passed',
        ]
        review_ratios.append(sum(1 for flag in review_flags if flag) / len(review_flags))
    review_ratio = sum(review_ratios) / len(review_ratios) if review_ratios else 0.0
    review_dimension = _score_dimension(
        key='review_license_source_controls',
        label='Review freshness, license, and source controls',
        score=15.0 * review_ratio,
        max_score=15.0,
        status='passed' if review_ratio >= 1.0 else 'blocked' if reports else 'not_run',
        evidence={
            'requirement_count': report_count,
            'review_license_source_ratio': _rounded_float(review_ratio),
            'shortfall_requirements': [
                report['requirement_key']
                for report in reports
                if int(report.get('row_count', 0) or 0) <= 0
                or not (
                    report.get('review_freshness_status') == 'passed'
                    and report.get('license_scope_check_status') == 'passed'
                    and report.get('source_ref_integrity_status') == 'passed'
                    and report.get('source_ref_manifest_status') == 'passed'
                )
            ],
        },
        next_action='Ensure every row is reviewed, fresh, license-supported, and linked to the source manifest.',
    )

    release_ready = bool(
        readiness_contract
        and readiness_contract.get('decision') == 'ready_for_himalayan_accuracy_claim_review'
        and readiness_contract.get('himalayan_accuracy_claim_allowed') is True
    )
    release_dimension = _score_dimension(
        key='release_gate_readiness',
        label='Release-gate attestations',
        score=10.0 if release_ready else 0.0,
        max_score=10.0,
        status='passed' if release_ready else 'blocked' if readiness_contract else 'not_run',
        evidence={
            'decision': readiness_contract.get('decision') if readiness_contract else 'not_run',
            'himalayan_accuracy_claim_allowed': (
                readiness_contract.get('himalayan_accuracy_claim_allowed')
                if readiness_contract
                else False
            ),
        },
        next_action='Supply accepted holdout, scientist-review, license-clearance, and promotion attestations after evidence passes.',
    )

    dimensions = [
        package_dimension,
        source_dimension,
        evidence_dimension,
        coverage_dimension,
        review_dimension,
        release_dimension,
    ]
    total_score = _rounded_float(sum(dimension['score'] for dimension in dimensions))
    max_score = _rounded_float(sum(dimension['max_score'] for dimension in dimensions))
    score_ratio = _score_ratio(total_score, max_score)
    if not any(
        item is not None
        for item in (
            intake_preflight,
            source_manifest_validation,
            evidence_validation,
            readiness_contract,
        )
    ):
        decision = 'blocked_quality_checks_not_run'
        readiness_band = 'not_run'
    elif release_ready and score_ratio >= 0.999:
        decision = 'partner_submission_quality_ready_for_claim_review'
        readiness_band = 'release_ready'
    elif total_score >= 75.0 and evidence_dimension['status'] == 'passed':
        decision = 'partner_submission_quality_evidence_ready_release_gates_pending'
        readiness_band = 'evidence_ready_release_gates_pending'
    elif total_score >= 50.0:
        decision = 'partner_submission_quality_partial'
        readiness_band = 'partial'
    else:
        decision = 'blocked_low_partner_submission_quality'
        readiness_band = 'low_quality_or_missing'
    failed_dimensions = [
        dimension for dimension in dimensions if dimension['status'] != 'passed'
    ]
    return {
        'schema_version': PARTNER_SUBMISSION_QUALITY_SCORE_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': bool(release_ready),
        'decision': decision,
        'readiness_band': readiness_band,
        'score': total_score,
        'max_score': max_score,
        'score_ratio': _rounded_float(score_ratio),
        'dimensions': dimensions,
        'failed_dimension_count': len(failed_dimensions),
        'failed_dimensions': [dimension['key'] for dimension in failed_dimensions],
        'next_actions': [dimension['next_action'] for dimension in failed_dimensions],
        'quality_policy': {
            'scoring_model': '100 point evidence-package quality rubric',
            'dimensions': {
                'package_file_completeness': 15,
                'source_governance': 20,
                'evidence_row_sufficiency': 20,
                'coverage_quality': 20,
                'review_license_source_controls': 15,
                'release_gate_readiness': 10,
            },
            'score_is_not_accuracy': True,
            'score_is_not_production_authorization': True,
        },
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': bool(release_ready),
            'production_scoring_allowed': False,
            'reason': 'The quality score grades partner evidence package readiness only; model claims still require validated evidence and release gates.',
        },
    }


def markdown_partner_submission_quality_score(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Submission Quality Score',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This scorecard grades partner evidence-package readiness. It is not a model accuracy result and does not authorize production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Score | {payload['score']} / {payload['max_score']} |",
        f"| Readiness band | `{payload['readiness_band']}` |",
        f"| Failed dimensions | {payload['failed_dimension_count']} |",
        '',
        '## Dimensions',
        '',
        '| Dimension | Score | Status | Evidence | Next action |',
        '|---|---:|---|---|---|',
    ]
    for dimension in payload['dimensions']:
        evidence_bits = ', '.join(
            f"`{key}`={value}"
            for key, value in dimension['evidence'].items()
            if key not in {'missing_files', 'available_requirements', 'blocked_requirements', 'shortfall_requirements'}
        )
        lines.append(
            '| {label} | {score} / {max_score} | `{status}` | {evidence} | {next_action} |'.format(
                label=dimension['label'],
                score=dimension['score'],
                max_score=dimension['max_score'],
                status=dimension['status'],
                evidence=evidence_bits or 'See JSON',
                next_action=dimension['next_action'],
            )
        )
    lines.extend(['', '## Failed Dimensions', ''])
    if payload['failed_dimensions']:
        for key in payload['failed_dimensions']:
            lines.append(f'- `{key}`')
    else:
        lines.append('- None')
    lines.extend(
        [
            '',
            '## Quality Policy',
            '',
            f"- Score is not accuracy: `{str(payload['quality_policy']['score_is_not_accuracy']).lower()}`",
            f"- Score is not production authorization: `{str(payload['quality_policy']['score_is_not_production_authorization']).lower()}`",
            '',
        ]
    )
    return '\n'.join(lines)


def _evidence_report_by_key(
    evidence_validation: dict[str, Any] | None,
    requirement_key: str,
) -> dict[str, Any] | None:
    if not evidence_validation:
        return None
    for report in evidence_validation.get('reports', []):
        if report.get('requirement_key') == requirement_key:
            return report
    return None


def _quality_dimension_by_key(
    quality_score: dict[str, Any] | None,
    dimension_key: str,
) -> dict[str, Any] | None:
    if not quality_score:
        return None
    for dimension in quality_score.get('dimensions', []):
        if dimension.get('key') == dimension_key:
            return dimension
    return None


def _boundary_gate(
    *,
    key: str,
    label: str,
    status: str,
    decision: str,
    evidence: dict[str, Any],
    blocks_claim_review: bool,
    next_action: str,
) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'status': status,
        'decision': decision,
        'evidence': evidence,
        'blocks_claim_review': blocks_claim_review,
        'next_action': next_action,
    }


def _boundary_gate_status(passed: bool, *, not_run: bool = False) -> str:
    if not_run:
        return 'not_run'
    return 'passed' if passed else 'blocked'


def build_himalayan_boundary_readiness_report(
    *,
    generated_at: datetime | None = None,
    intake_preflight: dict[str, Any] | None = None,
    source_manifest_validation: dict[str, Any] | None = None,
    evidence_validation: dict[str, Any] | None = None,
    readiness_contract: dict[str, Any] | None = None,
    leakage_audit: dict[str, Any] | None = None,
    metric_report: dict[str, Any] | None = None,
    submission_summary: dict[str, Any] | None = None,
    quality_score: dict[str, Any] | None = None,
    acceptance_checklist: dict[str, Any] | None = None,
    source_traceability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    readiness_contract = readiness_contract or build_contract(generated_at=generated_at)
    quality_score = quality_score or build_partner_submission_quality_score(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    acceptance_checklist = acceptance_checklist or build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=quality_score,
    )
    submission_summary = submission_summary or build_partner_submission_status_summary(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )

    package_files_passed = bool(
        intake_preflight
        and intake_preflight.get('decision') == 'partner_intake_package_files_present'
    )
    source_manifest_passed = bool(
        source_manifest_validation
        and source_manifest_validation.get('decision') == 'partner_source_manifest_available'
    )
    evidence_passed = bool(
        evidence_validation
        and evidence_validation.get('decision') == 'all_partner_evidence_available'
    )
    label_report = _evidence_report_by_key(evidence_validation, 'danger_labels_and_bulletins')
    station_report = _evidence_report_by_key(evidence_validation, 'station_metadata')
    holdout_report = _evidence_report_by_key(evidence_validation, 'independent_himalayan_holdout')
    label_gate = (label_report or {}).get('label_provenance_gate') or {}
    station_coverage = (station_report or {}).get('coverage_diagnostics') or {}
    label_passed = bool(
        label_report
        and label_report.get('status') == STATUS_AVAILABLE
        and label_gate.get('status') == 'passed'
    )
    station_passed = bool(
        station_report
        and station_report.get('status') == STATUS_AVAILABLE
        and not station_coverage.get('sparse_coverage_warnings')
    )
    leakage_passed = bool(
        leakage_audit
        and leakage_audit.get('decision') == 'local_holdout_leakage_audit_passed_release_gate_attestation_required'
    )
    metric_passed = bool(
        metric_report
        and metric_report.get('decision') == 'local_holdout_metrics_passed_release_gate_attestation_required'
    )
    release_passed = bool(
        readiness_contract.get('decision') == 'ready_for_himalayan_accuracy_claim_review'
        and readiness_contract.get('himalayan_accuracy_claim_allowed') is True
    )
    source_traceability_passed = bool(
        source_traceability
        and source_traceability.get('decision') in {
            'source_traceability_passed_perfect_match_claims_blocked',
            'source_traceability_passed_with_unused_manifest_sources',
        }
    )

    gates = [
        _boundary_gate(
            key='package_file_completeness',
            label='Partner package files',
            status=_boundary_gate_status(package_files_passed, not_run=intake_preflight is None),
            decision=intake_preflight.get('decision') if intake_preflight else 'not_run',
            evidence={
                'present_file_count': intake_preflight.get('present_file_count', 0) if intake_preflight else 0,
                'required_file_count': intake_preflight.get('required_file_count', 0) if intake_preflight else 0,
                'missing_files': intake_preflight.get('missing_files', []) if intake_preflight else [],
            },
            blocks_claim_review=True,
            next_action='Supply partner_source_manifest.json and all ten evidence CSVs.',
        ),
        _boundary_gate(
            key='source_traceability_license_freshness',
            label='Source traceability, license, and freshness',
            status=_boundary_gate_status(
                source_manifest_passed
                and bool(
                    source_traceability_passed
                    or (source_traceability is None and evidence_passed)
                ),
                not_run=source_manifest_validation is None,
            ),
            decision=(
                source_traceability.get('decision')
                if source_traceability
                else source_manifest_validation.get('decision')
                if source_manifest_validation
                else 'not_run'
            ),
            evidence={
                'source_count': source_manifest_validation.get('source_count', 0) if source_manifest_validation else 0,
                'valid_source_count': (
                    source_manifest_validation.get('valid_source_count', 0)
                    if source_manifest_validation
                    else 0
                ),
                'source_traceability_decision': source_traceability.get('decision') if source_traceability else 'not_run',
            },
            blocks_claim_review=True,
            next_action='Map every source_ref to a reviewed source manifest entry with supported license scope and fresh review.',
        ),
        _boundary_gate(
            key='evidence_quality',
            label='Evidence row, coverage, review, and source controls',
            status=_boundary_gate_status(evidence_passed, not_run=evidence_validation is None),
            decision=evidence_validation.get('decision') if evidence_validation else 'not_run',
            evidence={
                'available_requirements': evidence_validation.get('available_requirements', []) if evidence_validation else [],
                'blocked_requirements': evidence_validation.get('blocked_requirements', []) if evidence_validation else [],
                'quality_score': quality_score.get('score', 0.0),
                'readiness_band': quality_score.get('readiness_band', 'not_run'),
            },
            blocks_claim_review=True,
            next_action='Fix all row, coverage, controlled-value, review, license, and source-ref blockers.',
        ),
        _boundary_gate(
            key='d_tidy_label_provenance',
            label='D_tidy-grade local danger labels',
            status=_boundary_gate_status(label_passed, not_run=evidence_validation is None),
            decision=(label_report or {}).get('decision', 'not_run'),
            evidence={
                'row_count': (label_report or {}).get('row_count', 0),
                'minimum_row_count': (label_report or {}).get('minimum_row_count', 0),
                'label_provenance_gate': label_gate,
            },
            blocks_claim_review=True,
            next_action='Provide reviewed local labels with label_source, tidy review basis, nowcast/observer refs, regime, and timing fields.',
        ),
        _boundary_gate(
            key='station_gpxyz_readiness',
            label='Station X/Y/Z and GPxyz readiness',
            status=_boundary_gate_status(station_passed, not_run=evidence_validation is None),
            decision=(station_report or {}).get('decision', 'not_run'),
            evidence={
                'row_count': (station_report or {}).get('row_count', 0),
                'coverage_diagnostics': station_coverage,
            },
            blocks_claim_review=True,
            next_action='Provide reviewed station latitude, longitude, elevation, region coverage, and elevation span before GPxyz claims.',
        ),
        _boundary_gate(
            key='independent_holdout_definition',
            label='Independent Himalayan holdout definition',
            status=_boundary_gate_status(
                bool(holdout_report and holdout_report.get('status') == STATUS_AVAILABLE),
                not_run=evidence_validation is None,
            ),
            decision=(holdout_report or {}).get('decision', 'not_run'),
            evidence={
                'row_count': (holdout_report or {}).get('row_count', 0),
                'source_refs': (holdout_report or {}).get('source_ref_hashes', []),
            },
            blocks_claim_review=True,
            next_action='Pre-register holdout regions, dates, source refs, leakage checks, and acceptance floors before metrics.',
        ),
        _boundary_gate(
            key='holdout_leakage_audit',
            label='Independent holdout leakage audit',
            status=_boundary_gate_status(leakage_passed, not_run=leakage_audit is None),
            decision=leakage_audit.get('decision') if leakage_audit else 'not_run',
            evidence={
                'holdout_row_count': leakage_audit.get('holdout_row_count', 0) if leakage_audit else 0,
                'source_ref_overlap_count': leakage_audit.get('source_ref_overlap_count', 0) if leakage_audit else 0,
                'row_issue_count': leakage_audit.get('row_issue_count', 0) if leakage_audit else 0,
            },
            blocks_claim_review=True,
            next_action='Stop metric reporting until holdout source refs are independent and leakage audit passes.',
        ),
        _boundary_gate(
            key='holdout_metrics_uncertainty',
            label='Local holdout metrics and calibration uncertainty',
            status=_boundary_gate_status(metric_passed, not_run=metric_report is None),
            decision=metric_report.get('decision') if metric_report else 'not_run',
            evidence={
                'prediction_row_count': metric_report.get('prediction_row_count', 0) if metric_report else 0,
                'metrics': metric_report.get('metrics', {}) if metric_report else {},
                'floor_results': metric_report.get('floor_results', []) if metric_report else [],
            },
            blocks_claim_review=True,
            next_action='Evaluate frozen local holdout predictions only after leakage audit passes.',
        ),
        _boundary_gate(
            key='release_gate_attestations',
            label='Release-gate attestations',
            status=_boundary_gate_status(release_passed),
            decision=readiness_contract.get('decision', 'not_run'),
            evidence={
                'release_gates': readiness_contract.get('release_gates', {}),
                'blocked_release_gates': readiness_contract.get('blocked_release_gates', []),
                'release_gate_attestations': sorted(readiness_contract.get('release_gate_attestations', {})),
            },
            blocks_claim_review=True,
            next_action='Attach accepted holdout, scientist-review, license-clearance, and promotion attestations.',
        ),
        _boundary_gate(
            key='sar_shadow_boundary',
            label='SAR and remote-sensing shadow boundary',
            status='enforced',
            decision='sar_shadow_only_until_fresh_local_gates_pass',
            evidence={
                'sar_shadow_only': True,
                'known_transfer_risks': [
                    'wet_snow_false_positives',
                    'shadow_layover',
                    'small_event_misses',
                    'local_holdout_transferability',
                ],
            },
            blocks_claim_review=False,
            next_action='Keep SAR as research/shadow evidence until separate precision, recall, F1, FPR, and fresh-final gates pass.',
        ),
    ]

    if release_passed:
        claim_state = 'claim_review_ready'
    elif metric_passed:
        claim_state = 'local_holdout_ready'
    elif acceptance_checklist.get('scientist_review_ready') is True:
        claim_state = 'scientist_review_ready'
    elif evidence_passed:
        claim_state = 'partner_package_triaged'
    else:
        claim_state = 'methodology_evidence_only'

    if claim_state == 'claim_review_ready':
        decision = 'boundary_readiness_claim_review_ready_production_blocked'
    elif claim_state == 'local_holdout_ready':
        decision = 'boundary_readiness_local_holdout_ready_release_gates_pending'
    elif claim_state == 'scientist_review_ready':
        decision = 'boundary_readiness_scientist_review_ready_release_gates_pending'
    elif claim_state == 'partner_package_triaged':
        decision = 'boundary_readiness_partner_package_triaged_release_gates_pending'
    else:
        decision = 'boundary_readiness_blocked_methodology_evidence_only'

    blocking_gates = [
        gate for gate in gates if gate['blocks_claim_review'] and gate['status'] != 'passed'
    ]
    uncertainty_metrics = (metric_report.get('metrics') or {}) if metric_report else {}
    return {
        'schema_version': HIMALAYAN_BOUNDARY_READINESS_REPORT_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': bool(release_passed),
        'decision': decision,
        'claim_state': claim_state,
        'claim_state_taxonomy': list(HIMALAYAN_CLAIM_STATE_TAXONOMY),
        'production_state': 'production_blocked',
        'production_blocked_reason': (
            'This report can only route to claim review. Production scoring still requires separate promotion approval and runtime rollout controls.'
        ),
        'first_blocker': blocking_gates[0]['key'] if blocking_gates else None,
        'blocking_gate_count': len(blocking_gates),
        'passed_gate_count': sum(1 for gate in gates if gate['status'] in {'passed', 'enforced'}),
        'gates': gates,
        'score4_plus_decisions_implemented': [
            'artifact_derived_claim_state_taxonomy',
            'evidence_quality_readiness_report',
            'd_tidy_label_gate',
            'station_xyz_gpxyz_readiness',
            'source_traceability_license_freshness_gate',
            'independent_holdout_leakage_hard_stop',
            'release_gate_attestation_hardening',
            'uncertainty_and_sar_boundary_reporting',
        ],
        'explicitly_deferred_items': [
            'public_himalayan_route_switch',
            'production_scoring_change',
            'gpu_or_mts_lstm_training_before_local_truth',
            'sar_promotion',
            'public_facing_readiness_ui_before_real_partner_package',
            'public_data_scraping_as_d_tidy_substitute',
        ],
        'referenced_decisions': {
            'intake_preflight': intake_preflight.get('decision') if intake_preflight else 'not_run',
            'source_manifest_validation': source_manifest_validation.get('decision') if source_manifest_validation else 'not_run',
            'partner_evidence_validation': evidence_validation.get('decision') if evidence_validation else 'not_run',
            'readiness_contract': readiness_contract.get('decision', 'not_run'),
            'local_holdout_leakage_audit': leakage_audit.get('decision') if leakage_audit else 'not_run',
            'local_holdout_metric_report': metric_report.get('decision') if metric_report else 'not_run',
            'submission_summary': submission_summary.get('decision') if submission_summary else 'not_run',
            'quality_score': quality_score.get('decision', 'not_run'),
            'acceptance_checklist': acceptance_checklist.get('decision', 'not_run'),
            'source_traceability': source_traceability.get('decision') if source_traceability else 'not_run',
        },
        'quality_summary': {
            'score': quality_score.get('score', 0.0),
            'max_score': quality_score.get('max_score', 100.0),
            'readiness_band': quality_score.get('readiness_band', 'not_run'),
            'failed_dimensions': quality_score.get('failed_dimensions', []),
            'score_is_not_accuracy': True,
        },
        'uncertainty_boundary': {
            'calibration_status': (
                'available_from_local_holdout_metric_report'
                if metric_passed
                else 'blocked_until_local_holdout_metrics_pass'
            ),
            'reported_metrics': {
                key: uncertainty_metrics.get(key)
                for key in ('brier_score', 'expected_calibration_error', 'macro_f1', 'high_danger_recall')
                if key in uncertainty_metrics
            },
            'gpxyz_uncertainty_status': (
                'station_xyz_ready_for_gpxyz_design'
                if station_passed
                else 'blocked_station_xyz_density_or_elevation_span'
            ),
            'sar_uncertainty_status': 'shadow_only_transferability_not_proven',
            'refined_discretization_status': (
                'research_only_training_or_oob_thresholds_required_no_holdout_leakage'
            ),
        },
        'next_actions': [gate['next_action'] for gate in blocking_gates],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': bool(release_passed),
            'production_scoring_allowed': False,
            'reason': (
                'Boundary readiness composes partner evidence, label quality, station coverage, holdout, uncertainty, and release gates. '
                'It is not production authorization and cannot be satisfied by Swiss, Colorado, SAR, synthetic, or template-only evidence.'
            ),
        },
    }


def markdown_himalayan_boundary_readiness_report(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Prediction Boundary Readiness Report',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This report composes the partner evidence checks, label-quality gate, station/GPxyz readiness, source traceability, holdout controls, release gates, and uncertainty/SAR boundaries. It is readiness evidence, not model accuracy or production authorization.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Claim state | `{payload['claim_state']}` |",
        f"| Production state | `{payload['production_state']}` |",
        f"| First blocker | `{payload['first_blocker'] or 'none'}` |",
        f"| Blocking gates | {payload['blocking_gate_count']} |",
        f"| Quality score | {payload['quality_summary']['score']} / {payload['quality_summary']['max_score']} |",
        f"| Readiness band | `{payload['quality_summary']['readiness_band']}` |",
        '',
        '## Claim-State Taxonomy',
        '',
    ]
    for state in payload['claim_state_taxonomy']:
        prefix = 'current' if state == payload['claim_state'] else 'available'
        lines.append(f'- `{state}` - {prefix}')
    lines.extend(
        [
            '- `production_blocked` - always enforced for this research-validation artifact',
            '',
            '## Boundary Gates',
            '',
            '| Gate | Status | Decision | Blocks claim review | Next action |',
            '|---|---|---|---:|---|',
        ]
    )
    for gate in payload['gates']:
        lines.append(
            '| {label} | `{status}` | `{decision}` | `{blocks}` | {next_action} |'.format(
                label=gate['label'],
                status=gate['status'],
                decision=gate['decision'],
                blocks=str(gate['blocks_claim_review']).lower(),
                next_action=gate['next_action'],
            )
        )
    lines.extend(
        [
            '',
            '## Score 4+ Implemented Decisions',
            '',
        ]
    )
    for item in payload['score4_plus_decisions_implemented']:
        lines.append(f'- `{item}`')
    lines.extend(['', '## Explicitly Deferred', ''])
    for item in payload['explicitly_deferred_items']:
        lines.append(f'- `{item}`')
    lines.extend(
        [
            '',
            '## Uncertainty Boundary',
            '',
            '| Area | Status |',
            '|---|---|',
        ]
    )
    uncertainty = payload['uncertainty_boundary']
    for key in (
        'calibration_status',
        'gpxyz_uncertainty_status',
        'sar_uncertainty_status',
        'refined_discretization_status',
    ):
        lines.append(f"| `{key}` | `{uncertainty[key]}` |")
    lines.extend(['', '## Next Actions', ''])
    if payload['next_actions']:
        for action in payload['next_actions']:
            lines.append(f'- {action}')
    else:
        lines.append('- None')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_submission_acceptance_checklist(
    *,
    generated_at: datetime | None = None,
    quality_score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    if quality_score is None:
        quality_score = build_partner_submission_quality_score(generated_at=generated_at)
    acceptance_criteria = {
        'package_file_completeness': 'partner_source_manifest.json and all ten evidence CSV files are present.',
        'source_governance': 'Every source hash has reviewed owner, dataset, license scope, date range, reviewer, and evidence package metadata.',
        'evidence_row_sufficiency': 'Every evidence CSV meets its minimum reviewed-row floor.',
        'coverage_quality': 'Required distinct, temporal, elevation, and slope coverage floors pass for every evidence group.',
        'review_license_source_controls': 'Every row is fresh, reviewed, license-supported, SHA-256 referenced, and mapped to the source manifest.',
        'release_gate_readiness': 'Independent holdout, scientist review, license clearance, and promotion attestations pass after evidence acceptance.',
    }
    scientist_review_gate_keys = {
        'package_file_completeness',
        'source_governance',
        'evidence_row_sufficiency',
        'coverage_quality',
        'review_license_source_controls',
    }
    items = []
    for dimension in quality_score.get('dimensions', []):
        accepted = dimension.get('status') == 'passed'
        key = str(dimension['key'])
        items.append(
            {
                'key': key,
                'label': dimension['label'],
                'accepted': accepted,
                'status': 'accepted' if accepted else 'partner_action_required',
                'score': dimension['score'],
                'max_score': dimension['max_score'],
                'acceptance_criterion': acceptance_criteria.get(
                    key,
                    'Dimension-specific evidence must pass validation.',
                ),
                'partner_fix': 'None' if accepted else dimension['next_action'],
                'blocks_scientist_review': key in scientist_review_gate_keys and not accepted,
                'blocks_claim_review': not accepted,
            }
        )
    blocking_items = [item for item in items if not item['accepted']]
    scientist_review_blockers = [
        item for item in blocking_items if item['blocks_scientist_review']
    ]
    scientist_review_ready = not scientist_review_blockers and bool(items)
    claim_review_ready = (
        scientist_review_ready
        and not blocking_items
        and quality_score.get('himalayan_accuracy_claim_allowed') is True
    )
    if not items:
        decision = 'blocked_acceptance_checklist_quality_score_not_run'
    elif claim_review_ready:
        decision = 'partner_submission_acceptance_ready_for_claim_review'
    elif scientist_review_ready:
        decision = 'partner_submission_acceptance_scientist_review_ready_release_gates_pending'
    else:
        decision = 'blocked_acceptance_checklist_partner_fixes_required'
    return {
        'schema_version': PARTNER_SUBMISSION_ACCEPTANCE_CHECKLIST_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': bool(claim_review_ready),
        'decision': decision,
        'scientist_review_ready': scientist_review_ready,
        'claim_review_ready': claim_review_ready,
        'quality_score_summary': {
            'decision': quality_score.get('decision', 'not_run'),
            'readiness_band': quality_score.get('readiness_band', 'not_run'),
            'score': quality_score.get('score', 0.0),
            'max_score': quality_score.get('max_score', 100.0),
        },
        'accepted_item_count': len(items) - len(blocking_items),
        'blocking_item_count': len(blocking_items),
        'scientist_review_blocker_count': len(scientist_review_blockers),
        'items': items,
        'blocking_items': [item['key'] for item in blocking_items],
        'scientist_review_blockers': [item['key'] for item in scientist_review_blockers],
        'partner_next_actions': [item['partner_fix'] for item in blocking_items],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': bool(claim_review_ready),
            'production_scoring_allowed': False,
            'reason': 'The checklist gates partner evidence acceptance only. It does not authorize model claims or production scoring.',
        },
    }


def markdown_partner_submission_acceptance_checklist(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Submission Acceptance Checklist',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This checklist translates the package quality score into partner-side fixes before scientist review or claim review. It does not authorize production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Scientist review ready | `{str(payload['scientist_review_ready']).lower()}` |",
        f"| Claim review ready | `{str(payload['claim_review_ready']).lower()}` |",
        f"| Quality score | {payload['quality_score_summary']['score']} / {payload['quality_score_summary']['max_score']} |",
        f"| Blocking items | {payload['blocking_item_count']} |",
        '',
        '## Acceptance Items',
        '',
        '| Item | Status | Score | Acceptance criterion | Partner fix |',
        '|---|---|---:|---|---|',
    ]
    for item in payload['items']:
        lines.append(
            '| {label} | `{status}` | {score} / {max_score} | {criterion} | {fix} |'.format(
                label=item['label'],
                status=item['status'],
                score=item['score'],
                max_score=item['max_score'],
                criterion=item['acceptance_criterion'],
                fix=item['partner_fix'],
            )
        )
    lines.extend(['', '## Scientist Review Blockers', ''])
    if payload['scientist_review_blockers']:
        for key in payload['scientist_review_blockers']:
            lines.append(f'- `{key}`')
    else:
        lines.append('- None')
    lines.extend(['', '## Partner Next Actions', ''])
    if payload['partner_next_actions']:
        for action in payload['partner_next_actions']:
            lines.append(f'- {action}')
    else:
        lines.append('- None')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_handoff_readme(
    *,
    generated_at: datetime | None = None,
    package_index: dict[str, Any] | None = None,
    quality_score: dict[str, Any] | None = None,
    acceptance_checklist: dict[str, Any] | None = None,
    submission_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    package_index = package_index or build_partner_package_index(generated_at=generated_at)
    quality_score = quality_score or build_partner_submission_quality_score(generated_at=generated_at)
    acceptance_checklist = acceptance_checklist or build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=quality_score,
    )
    submission_summary = submission_summary or build_partner_submission_status_summary(
        generated_at=generated_at,
    )
    return {
        'schema_version': PARTNER_HANDOFF_README_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'partner_handoff_readme_written_pending_partner_submission',
        'current_status': {
            'package_index_decision': package_index.get('decision', 'not_run'),
            'quality_score_decision': quality_score.get('decision', 'not_run'),
            'quality_score': quality_score.get('score', 0.0),
            'quality_score_max': quality_score.get('max_score', 100.0),
            'readiness_band': quality_score.get('readiness_band', 'not_run'),
            'acceptance_decision': acceptance_checklist.get('decision', 'not_run'),
            'scientist_review_ready': acceptance_checklist.get('scientist_review_ready', False),
            'claim_review_ready': acceptance_checklist.get('claim_review_ready', False),
            'submission_summary_decision': submission_summary.get('decision', 'not_run'),
        },
        'open_first': [
            {
                'step': 1,
                'artifact': 'partner_handoff_readme.md',
                'reason': 'Start here for the short package navigation and resubmission sequence.',
            },
            {
                'step': 2,
                'artifact': 'partner_package_index.md',
                'reason': 'Use this as the full artifact map and command-order reference.',
            },
            {
                'step': 3,
                'artifact': 'partner_submission_status_dashboard.md',
                'reason': 'Use this for the one-page current blocker, score, top-10 readiness, and claim-gate status.',
            },
            {
                'step': 4,
                'artifact': 'partner_source_package_checksum_guide.md',
                'reason': 'Use this before filling source_ref values or partner_source_manifest.json.',
            },
            {
                'step': 5,
                'artifact': 'partner_synthetic_validation_report.md',
                'reason': 'Optional: smoke-test the validator with synthetic-only rows that must never be submitted as evidence.',
            },
            {
                'step': 6,
                'artifact': 'partner_intake_dry_run_runbook.md',
                'reason': 'Use this to dry-run a real submitted package and interpret expected blocked/pass decisions.',
            },
            {
                'step': 7,
                'artifact': 'partner_incoming_triage_runbook.md',
                'reason': 'Use this when a real partner package arrives to run the first-response sequence and route blockers.',
            },
            {
                'step': 8,
                'artifact': 'release_gate_attestation_template_pack.md',
                'reason': 'Use this after evidence validation passes to document holdout, scientist-review, license, and promotion gates.',
            },
            {
                'step': 9,
                'artifact': 'himalayan_local_holdout_protocol.md',
                'reason': 'Use this before any local model evaluation to lock split rules, leakage checks, metrics, and floors.',
            },
            {
                'step': 10,
                'artifact': 'himalayan_local_holdout_leakage_audit.md',
                'reason': 'Run this when partner evidence arrives to block contaminated or source-unreviewed holdout rows.',
            },
            {
                'step': 11,
                'artifact': 'himalayan_local_holdout_prediction_template.md',
                'reason': 'Use this to produce the exact predictions CSV consumed by the holdout metric report.',
            },
            {
                'step': 12,
                'artifact': 'himalayan_local_holdout_metric_report.md',
                'reason': 'Run this after the leakage audit passes to evaluate locked local holdout classification and calibration floors.',
            },
            {
                'step': 13,
                'artifact': 'partner_submission_acceptance_checklist.md',
                'reason': 'Fix every partner-side blocker before scientist review.',
            },
            {
                'step': 14,
                'artifact': 'partner_submission_quality_score.md',
                'reason': 'Track package quality dimensions and score changes after resubmission.',
            },
            {
                'step': 15,
                'artifact': 'partner_submission_manifest_diff.md',
                'reason': 'Confirm which files changed since the prior submitted package.',
            },
            {
                'step': 16,
                'artifact': 'partner_submission_review_ledger.md',
                'reason': 'Track each package attempt, score, blocker, routing state, and resubmission action over time.',
            },
            {
                'step': 17,
                'artifact': 'partner_field_dictionary.md',
                'reason': 'Confirm field meanings, units, formats, controlled values, and danger-scale mapping.',
            },
            {
                'step': 18,
                'artifact': 'partner_sample_row_pack.md',
                'reason': 'Use example-only rows as a guide, not as evidence.',
            },
        ],
        'resubmission_sequence': [
            {
                'step': 1,
                'name': 'Fill partner package',
                'action': 'Complete partner_source_manifest.json and all ten evidence CSVs using real reviewed Himalayan evidence.',
            },
            {
                'step': 2,
                'name': 'Run full validation and blocker reports',
                'command': (
                    'python3 -m backend.scripts.build_himalayan_accuracy_readiness_contract '
                    '--output backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.json '
                    '--output-markdown backend/artifacts/reproduction/himalayan_accuracy/readiness_contract.md '
                    '--partner-intake-root <partner-package-root> '
                    '--partner-evidence-root <partner-package-root> '
                    '--partner-source-manifest <partner-package-root>/partner_source_manifest.json '
                    '--partner-intake-preflight-output backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.json '
                    '--partner-intake-preflight-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_intake_preflight.md '
                    '--partner-source-manifest-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.json '
                    '--partner-source-manifest-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_source_manifest_validation.md '
                    '--partner-evidence-validation-output backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.json '
                    '--partner-evidence-validation-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_validation.md '
                    '--partner-submission-quality-score-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.json '
                    '--partner-submission-quality-score-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_quality_score.md '
                    '--partner-submission-acceptance-checklist-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.json '
                    '--partner-submission-acceptance-checklist-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_acceptance_checklist.md '
                    '--partner-submission-manifest-diff-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.json '
                    '--partner-submission-manifest-diff-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_manifest_diff.md '
                    '--partner-submission-summary-output backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.json '
                    '--partner-submission-summary-markdown backend/artifacts/reproduction/himalayan_accuracy/partner_submission_summary.md'
                ),
            },
            {
                'step': 3,
                'name': 'Route next review',
                'action': 'Proceed to scientist review only when scientist_review_ready=true; proceed to claim review only when claim_review_ready=true.',
            },
        ],
        'do_not_claim': [
            'Do not claim Himalayan accuracy readiness from blank templates, sample rows, or package navigation artifacts.',
            'Do not treat the submission quality score as prediction accuracy.',
            'Do not start production scoring, public claims, or promotion without validated evidence and release-gate attestations.',
            'Do not collapse five-level danger labels into four classes without reviewed mapping notes.',
        ],
        'best_practice_anchors': [
            {
                'name': 'FAIR data principles',
                'url': 'https://www.go-fair.org/fair-principles/',
                'use': 'Keep partner evidence findable, reusable, and source-governed before scientific claims.',
            },
            {
                'name': 'WMO WIGOS data quality monitoring',
                'url': 'https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms',
                'use': 'Treat observation readiness as a quality-controlled data pipeline, not a one-off upload.',
            },
            {
                'name': 'ISO 19157-style geospatial quality dimensions',
                'url': 'https://www.iso.org/standard/78900.html',
                'use': 'Track completeness, consistency, coverage, and lineage for geospatial evidence.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The handoff README is navigation only; it does not supply evidence, validate a model, or authorize production scoring.',
        },
    }


def markdown_partner_handoff_readme(payload: dict[str, Any]) -> str:
    status = payload['current_status']
    lines = [
        '# Himalayan Partner Evidence Handoff README',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This is the first file to read before submitting or resubmitting Himalayan partner evidence. '
        'It points to the artifact map, scorecard, acceptance checklist, field dictionary, and sample rows.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Quality score | {status['quality_score']} / {status['quality_score_max']} |",
        f"| Readiness band | `{status['readiness_band']}` |",
        f"| Scientist review ready | `{str(status['scientist_review_ready']).lower()}` |",
        f"| Claim review ready | `{str(status['claim_review_ready']).lower()}` |",
        '',
        '## Open First',
        '',
        '| Step | Artifact | Reason |',
        '|---:|---|---|',
    ]
    for item in payload['open_first']:
        lines.append(f"| {item['step']} | `{item['artifact']}` | {item['reason']} |")
    lines.extend(['', '## Resubmission Sequence', ''])
    for item in payload['resubmission_sequence']:
        lines.append(f"### {item['step']}. {item['name']}")
        lines.append('')
        if 'command' in item:
            lines.extend(['```bash', item['command'], '```', ''])
        else:
            lines.extend([item['action'], ''])
    lines.extend(['## Do Not Claim', ''])
    for item in payload['do_not_claim']:
        lines.append(f'- {item}')
    lines.extend(
        [
            '',
            '## Best-Practice Anchors',
            '',
            '| Anchor | Use | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['best_practice_anchors']:
        lines.append(f"| {item['name']} | {item['use']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def _csv_row_count_and_columns(path: Path) -> tuple[int, list[str]]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.reader(handle)
        try:
            columns = next(reader)
        except StopIteration:
            return 0, []
        row_count = sum(1 for row in reader if any(str(cell).strip() for cell in row))
    return row_count, columns


def _json_schema_version(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    schema_version = payload.get('schema_version')
    return str(schema_version) if schema_version is not None else None


def build_partner_submission_manifest_snapshot(
    package_root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    checklist = build_partner_evidence_intake_checklist(generated_at=generated_at)
    files = []
    for item in checklist['required_package_files']:
        relative_path = str(item['path'])
        absolute_path = package_root / relative_path
        present = absolute_path.is_file()
        file_record: dict[str, Any] = {
            'path': relative_path,
            'type': item['type'],
            'requirement_key': item.get('requirement_key', 'source_manifest'),
            'present': present,
            'size_bytes': 0,
            'sha256': None,
            'row_count': 0,
            'column_count': 0,
            'columns': [],
            'schema_version': None,
        }
        if present:
            file_record['size_bytes'] = absolute_path.stat().st_size
            file_record['sha256'] = _sha256_digest(absolute_path)
            if absolute_path.suffix.lower() == '.csv':
                row_count, columns = _csv_row_count_and_columns(absolute_path)
                file_record['row_count'] = row_count
                file_record['column_count'] = len(columns)
                file_record['columns'] = columns
            elif absolute_path.suffix.lower() == '.json':
                file_record['schema_version'] = _json_schema_version(absolute_path)
        files.append(file_record)

    fingerprint_material = [
        {
            'path': record['path'],
            'present': record['present'],
            'size_bytes': record['size_bytes'],
            'sha256': record['sha256'],
            'row_count': record['row_count'],
            'column_count': record['column_count'],
            'schema_version': record['schema_version'],
        }
        for record in files
    ]
    package_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_material, sort_keys=True).encode('utf-8')
    ).hexdigest()
    present_files = [record['path'] for record in files if record['present']]
    missing_files = [record['path'] for record in files if not record['present']]
    return {
        'package_root': str(package_root),
        'generated_at': generated_at.isoformat(),
        'package_fingerprint': package_fingerprint,
        'required_file_count': len(files),
        'present_file_count': len(present_files),
        'missing_file_count': len(missing_files),
        'present_files': present_files,
        'missing_files': missing_files,
        'files': files,
    }


def _extract_manifest_snapshot(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    if 'current_snapshot' in payload and isinstance(payload['current_snapshot'], dict):
        return payload['current_snapshot']
    if 'files' in payload and isinstance(payload['files'], list):
        return payload
    return None


def build_partner_submission_manifest_diff(
    package_root: Path,
    *,
    previous_snapshot: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    current_snapshot = build_partner_submission_manifest_snapshot(
        package_root,
        generated_at=generated_at,
    )
    previous = _extract_manifest_snapshot(previous_snapshot)
    previous_files = {
        record['path']: record
        for record in previous.get('files', [])
    } if previous else {}
    current_files = {
        record['path']: record
        for record in current_snapshot['files']
    }
    added_files = []
    removed_files = []
    changed_files = []
    unchanged_files = []
    row_count_changes = []
    schema_version_changes = []
    previous_available = previous is not None
    if previous_available:
        all_paths = sorted(set(previous_files) | set(current_files))
        for path in all_paths:
            before = previous_files.get(path)
            after = current_files.get(path)
            before_present = bool(before and before.get('present'))
            after_present = bool(after and after.get('present'))
            if after_present and not before_present:
                added_files.append(path)
            elif before_present and not after_present:
                removed_files.append(path)
            elif before_present and after_present:
                if before.get('sha256') == after.get('sha256'):
                    unchanged_files.append(path)
                else:
                    changed_files.append(path)
                if before.get('row_count') != after.get('row_count'):
                    row_count_changes.append(
                        {
                            'path': path,
                            'previous_row_count': before.get('row_count', 0),
                            'current_row_count': after.get('row_count', 0),
                        }
                    )
                if before.get('schema_version') != after.get('schema_version'):
                    schema_version_changes.append(
                        {
                            'path': path,
                            'previous_schema_version': before.get('schema_version'),
                            'current_schema_version': after.get('schema_version'),
                        }
                    )
    if current_snapshot['missing_file_count'] > 0:
        decision = 'blocked_manifest_diff_current_package_incomplete'
    elif not previous_available:
        decision = 'partner_submission_manifest_diff_baseline_written'
    elif removed_files:
        decision = 'blocked_manifest_diff_removed_required_files'
    elif changed_files or added_files:
        decision = 'partner_submission_manifest_diff_changed'
    else:
        decision = 'partner_submission_manifest_diff_no_changes'
    return {
        'schema_version': PARTNER_SUBMISSION_MANIFEST_DIFF_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'previous_snapshot_available': previous_available,
        'current_package_complete': current_snapshot['missing_file_count'] == 0,
        'current_snapshot': current_snapshot,
        'previous_package_fingerprint': previous.get('package_fingerprint') if previous else None,
        'current_package_fingerprint': current_snapshot['package_fingerprint'],
        'added_files': added_files,
        'removed_files': removed_files,
        'changed_files': changed_files,
        'unchanged_files': unchanged_files,
        'row_count_changes': row_count_changes,
        'schema_version_changes': schema_version_changes,
        'change_counts': {
            'added': len(added_files),
            'removed': len(removed_files),
            'changed': len(changed_files),
            'unchanged': len(unchanged_files),
            'row_count_changed': len(row_count_changes),
            'schema_version_changed': len(schema_version_changes),
        },
        'next_actions': [
            'Supply all missing required package files before scientist review.'
            if current_snapshot['missing_file_count'] > 0
            else 'Use this snapshot as the previous baseline for the next partner resubmission.'
            if not previous_available
            else 'Review changed files and rerun evidence validation before scientist review.'
            if changed_files or added_files or removed_files
            else 'No file-level changes detected; confirm whether a new submission was expected.',
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The manifest diff tracks package file changes only. It is not evidence validation, model accuracy, or production authorization.',
        },
    }


def markdown_partner_submission_manifest_diff(payload: dict[str, Any]) -> str:
    snapshot = payload['current_snapshot']
    lines = [
        '# Himalayan Partner Submission Manifest Diff',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This manifest compares package file presence, hashes, sizes, row counts, and schema versions across submissions. It does not validate evidence content or authorize claims.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Previous snapshot available | `{str(payload['previous_snapshot_available']).lower()}` |",
        f"| Current package complete | `{str(payload['current_package_complete']).lower()}` |",
        f"| Present files | {snapshot['present_file_count']} / {snapshot['required_file_count']} |",
        f"| Missing files | {snapshot['missing_file_count']} |",
        f"| Changed files | {payload['change_counts']['changed']} |",
        f"| Added files | {payload['change_counts']['added']} |",
        f"| Removed files | {payload['change_counts']['removed']} |",
        '',
        '## Current Files',
        '',
        '| Path | Present | Size bytes | Rows | SHA-256 |',
        '|---|---:|---:|---:|---|',
    ]
    for record in snapshot['files']:
        digest = record['sha256'] or 'missing'
        lines.append(
            '| `{path}` | `{present}` | {size} | {rows} | `{digest}` |'.format(
                path=record['path'],
                present=str(record['present']).lower(),
                size=record['size_bytes'],
                rows=record['row_count'],
                digest=digest,
            )
        )
    lines.extend(['', '## Changes', ''])
    for label, key in (
        ('Added files', 'added_files'),
        ('Removed files', 'removed_files'),
        ('Changed files', 'changed_files'),
        ('Unchanged files', 'unchanged_files'),
    ):
        lines.append(f'### {label}')
        if payload[key]:
            for path in payload[key]:
                lines.append(f'- `{path}`')
        else:
            lines.append('- None')
        lines.append('')
    lines.extend(['## Row Count Changes', ''])
    if payload['row_count_changes']:
        lines.extend(['| Path | Previous rows | Current rows |', '|---|---:|---:|'])
        for item in payload['row_count_changes']:
            lines.append(
                f"| `{item['path']}` | {item['previous_row_count']} | {item['current_row_count']} |"
            )
    else:
        lines.append('- None')
    lines.extend(['', '## Next Actions', ''])
    for action in payload['next_actions']:
        lines.append(f'- {action}')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def validate_partner_intake_package_preflight(
    intake_root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    checklist = build_partner_evidence_intake_checklist(generated_at=generated_at)
    root_exists = intake_root.is_dir()
    file_reports = []
    for item in checklist['required_package_files']:
        relative_path = str(item['path'])
        absolute_path = intake_root / relative_path
        present = root_exists and absolute_path.is_file()
        report = {
            'path': relative_path,
            'type': item['type'],
            'requirement_key': item.get('requirement_key', 'source_manifest'),
            'required': True,
            'present': present,
            'size_bytes': absolute_path.stat().st_size if present else 0,
        }
        file_reports.append(report)
    missing_files = [report['path'] for report in file_reports if not report['present']]
    present_files = [report['path'] for report in file_reports if report['present']]
    decision = (
        'partner_intake_package_files_present'
        if root_exists and not missing_files
        else 'blocked_missing_partner_intake_files'
    )
    return {
        'schema_version': PARTNER_INTAKE_PREFLIGHT_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'intake_root': str(intake_root),
        'intake_root_exists': root_exists,
        'required_file_count': len(file_reports),
        'present_file_count': len(present_files),
        'missing_file_count': len(missing_files),
        'present_files': present_files,
        'missing_files': missing_files,
        'file_reports': file_reports,
    }


def markdown_partner_intake_package_preflight(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Intake Package Preflight',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This preflight checks whether the partner package contains the required source manifest and evidence CSV files. '
        'It does not validate row contents and does not authorize a Himalayan accuracy claim or production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Intake root exists | `{str(payload['intake_root_exists']).lower()}` |",
        f"| Required files | {payload['required_file_count']} |",
        f"| Present files | {payload['present_file_count']} |",
        f"| Missing files | {payload['missing_file_count']} |",
        '',
        '## Required Files',
        '',
        '| Path | Type | Requirement | Present | Size bytes |',
        '|---|---|---|---:|---:|',
    ]
    for report in payload['file_reports']:
        lines.append(
            '| `{path}` | `{type}` | {requirement} | `{present}` | {size_bytes} |'.format(
                path=report['path'],
                type=report['type'],
                requirement=report['requirement_key'],
                present=str(report['present']).lower(),
                size_bytes=report['size_bytes'],
            )
        )
    lines.extend(['', '## Missing Files', ''])
    if payload['missing_files']:
        for path in payload['missing_files']:
            lines.append(f'- `{path}`')
    else:
        lines.append('- None')
    lines.append('')
    return '\n'.join(lines)


def build_partner_submission_status_summary(
    *,
    generated_at: datetime | None = None,
    intake_preflight: dict[str, Any] | None = None,
    source_manifest_validation: dict[str, Any] | None = None,
    evidence_validation: dict[str, Any] | None = None,
    readiness_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    checks = [
        {
            'key': 'intake_preflight',
            'label': 'Required package files',
            'decision': intake_preflight.get('decision') if intake_preflight else 'not_run',
            'passed': bool(
                intake_preflight
                and intake_preflight.get('decision') == 'partner_intake_package_files_present'
            ),
            'next_action': 'Supply partner_source_manifest.json and all ten evidence CSV files.',
        },
        {
            'key': 'source_manifest_validation',
            'label': 'Source manifest governance',
            'decision': source_manifest_validation.get('decision') if source_manifest_validation else 'not_run',
            'passed': bool(
                source_manifest_validation
                and source_manifest_validation.get('decision') == 'partner_source_manifest_available'
            ),
            'next_action': 'Validate source owner, license, reviewer, freshness, and evidence package refs.',
        },
        {
            'key': 'partner_evidence_validation',
            'label': 'Partner evidence CSV validation',
            'decision': evidence_validation.get('decision') if evidence_validation else 'not_run',
            'passed': bool(
                evidence_validation
                and evidence_validation.get('decision') == 'all_partner_evidence_available'
            ),
            'next_action': 'Fix missing, stale, undersized, unreviewed, unlicensed, or invalid evidence rows.',
        },
        {
            'key': 'readiness_contract',
            'label': 'Release-gated readiness contract',
            'decision': readiness_contract.get('decision') if readiness_contract else 'not_run',
            'passed': bool(
                readiness_contract
                and readiness_contract.get('decision') == 'ready_for_himalayan_accuracy_claim_review'
            ),
            'next_action': 'Supply release-gate attestations for holdout, scientist review, license clearance, and promotion approval.',
        },
    ]
    failed_checks = [check for check in checks if not check['passed']]
    first_blocker = failed_checks[0] if failed_checks else None
    if not intake_preflight or not source_manifest_validation or not evidence_validation:
        decision = 'blocked_submission_checks_not_run'
    elif first_blocker is None:
        decision = 'partner_submission_ready_for_himalayan_accuracy_claim_review'
    elif first_blocker['key'] == 'readiness_contract' and all(check['passed'] for check in checks[:3]):
        decision = 'partner_submission_evidence_available_release_gates_pending'
    else:
        decision = f"blocked_{first_blocker['key']}"
    return {
        'schema_version': PARTNER_SUBMISSION_STATUS_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': bool(
            readiness_contract
            and readiness_contract.get('himalayan_accuracy_claim_allowed') is True
        ),
        'decision': decision,
        'first_blocker': first_blocker['key'] if first_blocker else None,
        'checks_passed_count': len(checks) - len(failed_checks),
        'checks_failed_count': len(failed_checks),
        'checks': checks,
        'next_actions': [check['next_action'] for check in failed_checks],
        'referenced_decisions': {
            'intake_preflight': checks[0]['decision'],
            'source_manifest_validation': checks[1]['decision'],
            'partner_evidence_validation': checks[2]['decision'],
            'readiness_contract': checks[3]['decision'],
        },
    }


def markdown_partner_submission_status_summary(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Submission Status Summary',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This summary combines package preflight, source-manifest validation, partner evidence validation, '
        'and the release-gated readiness contract. It does not authorize production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Checks passed | {payload['checks_passed_count']} |",
        f"| Checks failed | {payload['checks_failed_count']} |",
        f"| First blocker | `{payload['first_blocker'] or 'none'}` |",
        '',
        '## Checks',
        '',
        '| Check | Decision | Passed | Next action |',
        '|---|---|---:|---|',
    ]
    for check in payload['checks']:
        lines.append(
            f"| {check['label']} | `{check['decision']}` | `{str(check['passed']).lower()}` | {check['next_action']} |"
        )
    lines.extend(['', '## Next Actions', ''])
    if payload['next_actions']:
        for action in payload['next_actions']:
            lines.append(f'- {action}')
    else:
        lines.append('- None')
    lines.append('')
    return '\n'.join(lines)


def _unique_nonblank(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def build_partner_submission_review_ledger(
    *,
    generated_at: datetime | None = None,
    package_root: Path | None = None,
    previous_ledger: dict[str, Any] | None = None,
    manifest_diff: dict[str, Any] | None = None,
    intake_preflight: dict[str, Any] | None = None,
    source_manifest_validation: dict[str, Any] | None = None,
    evidence_validation: dict[str, Any] | None = None,
    readiness_contract: dict[str, Any] | None = None,
    quality_score: dict[str, Any] | None = None,
    acceptance_checklist: dict[str, Any] | None = None,
    submission_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    quality_score = quality_score or build_partner_submission_quality_score(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    acceptance_checklist = acceptance_checklist or build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=quality_score,
    )
    submission_summary = submission_summary or build_partner_submission_status_summary(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    existing_entries = list(previous_ledger.get('entries', [])) if previous_ledger else []
    snapshot = _extract_manifest_snapshot(manifest_diff) if manifest_diff else None
    missing_files = list(snapshot.get('missing_files', [])) if snapshot else []
    package_fingerprint = (
        manifest_diff.get('current_package_fingerprint')
        if manifest_diff
        else snapshot.get('package_fingerprint')
        if snapshot
        else None
    )
    entry_seed = {
        'generated_at': generated_at.isoformat(),
        'package_root': str(package_root) if package_root else None,
        'package_fingerprint': package_fingerprint,
        'submission_summary_decision': submission_summary.get('decision', 'not_run'),
        'quality_score_decision': quality_score.get('decision', 'not_run'),
        'acceptance_decision': acceptance_checklist.get('decision', 'not_run'),
        'manifest_diff_decision': manifest_diff.get('decision', 'not_run') if manifest_diff else 'not_run',
    }
    submission_id = hashlib.sha256(
        json.dumps(entry_seed, sort_keys=True).encode('utf-8')
    ).hexdigest()[:16]
    next_actions = _unique_nonblank(
        list(submission_summary.get('next_actions', []))
        + list(acceptance_checklist.get('partner_next_actions', []))
        + list(manifest_diff.get('next_actions', []) if manifest_diff else [])
    )
    entry = {
        'submission_number': len(existing_entries) + 1,
        'submission_id': submission_id,
        'submitted_at': generated_at.isoformat(),
        'package_root': str(package_root) if package_root else None,
        'package_fingerprint': package_fingerprint,
        'package_complete': bool(
            manifest_diff.get('current_package_complete', False) if manifest_diff else False
        ),
        'manifest_diff_decision': manifest_diff.get('decision', 'not_run') if manifest_diff else 'not_run',
        'submission_summary_decision': submission_summary.get('decision', 'not_run'),
        'quality_score_decision': quality_score.get('decision', 'not_run'),
        'quality_score': quality_score.get('score', 0.0),
        'quality_score_max': quality_score.get('max_score', 100.0),
        'readiness_band': quality_score.get('readiness_band', 'not_run'),
        'acceptance_decision': acceptance_checklist.get('decision', 'not_run'),
        'scientist_review_ready': bool(acceptance_checklist.get('scientist_review_ready', False)),
        'claim_review_ready': bool(acceptance_checklist.get('claim_review_ready', False)),
        'first_blocker': submission_summary.get('first_blocker'),
        'missing_files': missing_files,
        'changed_files': list(manifest_diff.get('changed_files', []) if manifest_diff else []),
        'removed_files': list(manifest_diff.get('removed_files', []) if manifest_diff else []),
        'next_actions': next_actions,
    }
    entries = existing_entries + [entry]
    latest = entry
    if latest['claim_review_ready']:
        decision = 'partner_submission_review_ledger_updated_claim_review_ready'
    elif latest['scientist_review_ready']:
        decision = 'partner_submission_review_ledger_updated_scientist_review_ready'
    else:
        decision = 'partner_submission_review_ledger_updated_blocked'
    return {
        'schema_version': PARTNER_SUBMISSION_REVIEW_LEDGER_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'ledger_is_prediction_evidence': False,
        'submission_count': len(entries),
        'latest_submission_id': latest['submission_id'],
        'latest_first_blocker': latest['first_blocker'],
        'latest_quality_score': latest['quality_score'],
        'latest_readiness_band': latest['readiness_band'],
        'latest_scientist_review_ready': latest['scientist_review_ready'],
        'latest_claim_review_ready': latest['claim_review_ready'],
        'blocked_submission_count': sum(1 for item in entries if item.get('first_blocker')),
        'scientist_review_ready_count': sum(
            1 for item in entries if item.get('scientist_review_ready')
        ),
        'claim_review_ready_count': sum(1 for item in entries if item.get('claim_review_ready')),
        'entries': entries,
        'operator_rules': [
            'Append one ledger entry per partner submission or resubmission attempt.',
            'Use package_fingerprint and manifest diff outputs to distinguish changed packages.',
            'Do not route to scientist review until scientist_review_ready=true.',
            'Do not route to claim review until claim_review_ready=true.',
            'The ledger records governance state only; it is not prediction evidence.',
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The ledger tracks package review state and resubmission history. It does not validate model accuracy or authorize production scoring.',
        },
    }


def markdown_partner_submission_review_ledger(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Submission Review Ledger',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This ledger records partner submission and resubmission attempts over time. '
        'It is a governance trace, not prediction evidence or production authorization.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Ledger is prediction evidence | `{str(payload['ledger_is_prediction_evidence']).lower()}` |",
        f"| Submission count | {payload['submission_count']} |",
        f"| Latest first blocker | `{payload['latest_first_blocker'] or 'none'}` |",
        f"| Latest quality score | {payload['latest_quality_score']} |",
        f"| Latest readiness band | `{payload['latest_readiness_band']}` |",
        '',
        '## Submission Entries',
        '',
        '| # | Submission ID | Package complete | Score | Scientist review ready | Claim review ready | First blocker |',
        '|---:|---|---:|---:|---:|---:|---|',
    ]
    for entry in payload['entries']:
        lines.append(
            '| {number} | `{submission_id}` | `{package_complete}` | {score} / {max_score} | `{scientist}` | `{claim}` | `{blocker}` |'.format(
                number=entry['submission_number'],
                submission_id=entry['submission_id'],
                package_complete=str(entry['package_complete']).lower(),
                score=entry['quality_score'],
                max_score=entry['quality_score_max'],
                scientist=str(entry['scientist_review_ready']).lower(),
                claim=str(entry['claim_review_ready']).lower(),
                blocker=entry['first_blocker'] or 'none',
            )
        )
    latest = payload['entries'][-1] if payload['entries'] else None
    lines.extend(['', '## Latest Next Actions', ''])
    if latest and latest['next_actions']:
        for action in latest['next_actions']:
            lines.append(f'- {action}')
    else:
        lines.append('- None')
    lines.extend(['', '## Operator Rules', ''])
    for rule in payload['operator_rules']:
        lines.append(f'- {rule}')
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def build_partner_submission_status_dashboard(
    *,
    generated_at: datetime | None = None,
    package_index: dict[str, Any] | None = None,
    review_ledger: dict[str, Any] | None = None,
    submission_summary: dict[str, Any] | None = None,
    quality_score: dict[str, Any] | None = None,
    acceptance_checklist: dict[str, Any] | None = None,
    top10_feature_gap_matrix: dict[str, Any] | None = None,
    readiness_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    readiness_contract = readiness_contract or build_contract(generated_at=generated_at)
    package_index = package_index or build_partner_package_index(generated_at=generated_at)
    top10_feature_gap_matrix = top10_feature_gap_matrix or build_himalayan_top10_feature_gap_matrix(
        generated_at=generated_at,
        readiness_contract=readiness_contract,
    )
    quality_score = quality_score or build_partner_submission_quality_score(
        generated_at=generated_at,
        readiness_contract=readiness_contract,
    )
    acceptance_checklist = acceptance_checklist or build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=quality_score,
    )
    submission_summary = submission_summary or build_partner_submission_status_summary(
        generated_at=generated_at,
        readiness_contract=readiness_contract,
    )
    review_ledger = review_ledger or build_partner_submission_review_ledger(
        generated_at=generated_at,
        readiness_contract=readiness_contract,
        quality_score=quality_score,
        acceptance_checklist=acceptance_checklist,
        submission_summary=submission_summary,
    )
    latest_actions: list[Any] = []
    if review_ledger.get('entries'):
        latest_actions.extend(review_ledger['entries'][-1].get('next_actions', []))
    latest_actions.extend(submission_summary.get('next_actions', []))
    top10_actions = [
        item.get('immediate_next_action')
        for item in top10_feature_gap_matrix.get('features', [])
        if item.get('readiness_status') != 'evidence_available_release_gates_pending'
    ][:5]
    next_actions = _unique_nonblank(latest_actions + top10_actions)
    missing_files: list[str] = []
    if review_ledger.get('entries'):
        missing_files = list(review_ledger['entries'][-1].get('missing_files', []))
    release_gate_status = {
        gate: bool(readiness_contract.get('release_gates', {}).get(gate, False))
        for gate in REQUIRED_RELEASE_GATES
    }
    if review_ledger.get('latest_claim_review_ready'):
        decision = 'partner_submission_status_dashboard_claim_review_ready'
    elif review_ledger.get('latest_scientist_review_ready'):
        decision = 'partner_submission_status_dashboard_scientist_review_ready'
    else:
        decision = 'partner_submission_status_dashboard_blocked_partner_action_required'
    return {
        'schema_version': PARTNER_SUBMISSION_STATUS_DASHBOARD_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'dashboard_is_prediction_evidence': False,
        'current_status': {
            'latest_submission_id': review_ledger.get('latest_submission_id'),
            'latest_first_blocker': review_ledger.get('latest_first_blocker'),
            'latest_quality_score': review_ledger.get('latest_quality_score', 0.0),
            'quality_score_max': quality_score.get('max_score', 100.0),
            'latest_readiness_band': review_ledger.get('latest_readiness_band', 'not_run'),
            'submission_count': review_ledger.get('submission_count', 0),
            'scientist_review_ready': bool(review_ledger.get('latest_scientist_review_ready', False)),
            'claim_review_ready': bool(review_ledger.get('latest_claim_review_ready', False)),
            'top10_blocked_feature_count': top10_feature_gap_matrix.get('blocked_feature_count', 0),
            'top10_feature_count': top10_feature_gap_matrix.get('feature_count', 0),
            'package_artifact_sequence_count': len(package_index.get('artifact_sequence', [])),
            'missing_file_count': len(missing_files),
        },
        'source_artifacts': [
            {
                'artifact': 'partner_package_index.json',
                'schema_version': package_index.get('schema_version'),
                'decision': package_index.get('decision'),
            },
            {
                'artifact': 'partner_submission_review_ledger.json',
                'schema_version': review_ledger.get('schema_version'),
                'decision': review_ledger.get('decision'),
            },
            {
                'artifact': 'partner_submission_summary.json',
                'schema_version': submission_summary.get('schema_version'),
                'decision': submission_summary.get('decision'),
            },
            {
                'artifact': 'partner_submission_quality_score.json',
                'schema_version': quality_score.get('schema_version'),
                'decision': quality_score.get('decision'),
            },
            {
                'artifact': 'partner_submission_acceptance_checklist.json',
                'schema_version': acceptance_checklist.get('schema_version'),
                'decision': acceptance_checklist.get('decision'),
            },
            {
                'artifact': 'himalayan_top10_feature_gap_matrix.json',
                'schema_version': top10_feature_gap_matrix.get('schema_version'),
                'decision': top10_feature_gap_matrix.get('decision'),
            },
            {
                'artifact': 'readiness_contract.json',
                'schema_version': readiness_contract.get('schema_version'),
                'decision': readiness_contract.get('decision'),
            },
        ],
        'release_gate_status': release_gate_status,
        'missing_files': missing_files,
        'next_actions': next_actions,
        'operator_guardrails': [
            'Use this dashboard as a status export, not as prediction evidence.',
            'Do not open scientist review until scientist_review_ready=true.',
            'Do not open claim review until claim_review_ready=true.',
            'Do not claim Himalayan accuracy until all release gates pass with validated evidence.',
            'Do not enable production scoring from this research artifact.',
        ],
        'standards_anchors': [
            {
                'name': 'NIST AI Risk Management Framework',
                'url': 'https://www.nist.gov/itl/ai-risk-management-framework',
                'use': 'Keep AI risk decisions visible, governed, and traceable.',
            },
            {
                'name': 'WMO WIS/WIGOS monitoring practice',
                'url': 'https://wmo-im.github.io/wis2-manual/manual/wis2-manual-APPROVED.html',
                'use': 'Expose current status and historical performance/blockers through a monitor-style dashboard.',
            },
            {
                'name': 'ISO 19157 geospatial data quality',
                'url': 'https://www.iso.org/standard/78900.html',
                'use': 'Report completeness, lineage, and quality status for geospatial evidence.',
            },
            {
                'name': 'FAIR data principles',
                'url': 'https://www.go-fair.org/fair-principles/',
                'use': 'Keep evidence artifacts findable, reusable, source-referenced, and auditable.',
            },
        ],
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The dashboard summarizes package and review state. It is not local Himalayan validation, model performance evidence, release-gate approval, or production authorization.',
        },
    }


def markdown_partner_submission_status_dashboard(payload: dict[str, Any]) -> str:
    status = payload['current_status']
    lines = [
        '# Himalayan Partner Submission Status Dashboard',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This dashboard is a one-page status export for operators and scientists. '
        'It summarizes the latest package blocker, quality score, top-10 feature readiness, and claim gates.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Dashboard is prediction evidence | `{str(payload['dashboard_is_prediction_evidence']).lower()}` |",
        f"| Latest blocker | `{status['latest_first_blocker'] or 'none'}` |",
        f"| Latest quality score | {status['latest_quality_score']} / {status['quality_score_max']} |",
        f"| Readiness band | `{status['latest_readiness_band']}` |",
        f"| Submissions tracked | {status['submission_count']} |",
        f"| Top-10 blocked features | {status['top10_blocked_feature_count']} / {status['top10_feature_count']} |",
        f"| Package artifacts | {status['package_artifact_sequence_count']} |",
        '',
        '## Source Artifacts',
        '',
        '| Artifact | Schema | Decision |',
        '|---|---|---|',
    ]
    for item in payload['source_artifacts']:
        lines.append(
            f"| `{item['artifact']}` | `{item['schema_version']}` | `{item['decision']}` |"
        )
    lines.extend(['', '## Release Gates', '', '| Gate | Passed |', '|---|---:|'])
    for gate, passed in payload['release_gate_status'].items():
        lines.append(f"| `{gate}` | `{str(passed).lower()}` |")
    lines.extend(['', '## Missing Files', ''])
    if payload['missing_files']:
        for path in payload['missing_files']:
            lines.append(f'- `{path}`')
    else:
        lines.append('- None')
    lines.extend(['', '## Next Actions', ''])
    if payload['next_actions']:
        for action in payload['next_actions']:
            lines.append(f'- {action}')
    else:
        lines.append('- None')
    lines.extend(['', '## Operator Guardrails', ''])
    for item in payload['operator_guardrails']:
        lines.append(f'- {item}')
    lines.extend(
        [
            '',
            '## Standards Anchors',
            '',
            '| Anchor | Use | URL |',
            '|---|---|---|',
        ]
    )
    for item in payload['standards_anchors']:
        lines.append(f"| {item['name']} | {item['use']} | {item['url']} |")
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def write_partner_evidence_templates(output_root: Path) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    payload = build_partner_evidence_template_manifest(generated_at=generated_at)
    top10_matrix = build_himalayan_top10_feature_gap_matrix(generated_at=generated_at)
    source_manifest_template = build_partner_source_manifest_template(generated_at=generated_at)
    intake_checklist = build_partner_evidence_intake_checklist(generated_at=generated_at)
    intake_dry_run_runbook = build_partner_intake_dry_run_runbook(generated_at=generated_at)
    incoming_triage_runbook = build_partner_incoming_triage_runbook(generated_at=generated_at)
    local_holdout_protocol = build_himalayan_local_holdout_protocol(generated_at=generated_at)
    local_holdout_prediction_template = build_himalayan_local_holdout_prediction_template(
        generated_at=generated_at,
    )
    release_gate_attestation_template_pack = build_release_gate_attestation_template_pack(
        generated_at=generated_at,
    )
    field_dictionary = build_partner_field_dictionary(generated_at=generated_at)
    sample_row_pack = build_partner_sample_row_pack(generated_at=generated_at)
    checksum_guide = build_partner_source_package_checksum_guide(generated_at=generated_at)
    submission_quality_score = build_partner_submission_quality_score(generated_at=generated_at)
    acceptance_checklist = build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=submission_quality_score,
    )
    package_index = build_partner_package_index(generated_at=generated_at)
    handoff_readme = build_partner_handoff_readme(
        generated_at=generated_at,
        package_index=package_index,
        quality_score=submission_quality_score,
        acceptance_checklist=acceptance_checklist,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    for template in payload['templates']:
        path = output_root / str(template['filename'])
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(template['columns']))
            writer.writeheader()
    manifest_diff = build_partner_submission_manifest_diff(
        output_root,
        generated_at=generated_at,
    )
    holdout_leakage_audit = build_himalayan_local_holdout_leakage_audit(
        output_root,
        generated_at=generated_at,
    )
    holdout_metric_report = build_himalayan_local_holdout_metric_report(
        output_root,
        generated_at=generated_at,
        leakage_audit=holdout_leakage_audit,
    )
    submission_review_ledger = build_partner_submission_review_ledger(
        generated_at=generated_at,
        package_root=output_root,
        manifest_diff=manifest_diff,
        quality_score=submission_quality_score,
        acceptance_checklist=acceptance_checklist,
    )
    submission_status_dashboard = build_partner_submission_status_dashboard(
        generated_at=generated_at,
        package_index=package_index,
        review_ledger=submission_review_ledger,
        quality_score=submission_quality_score,
        acceptance_checklist=acceptance_checklist,
        top10_feature_gap_matrix=top10_matrix,
    )
    (output_root / 'partner_evidence_template_manifest.json').write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_evidence_template_manifest.md').write_text(
        markdown_partner_evidence_templates(payload),
        encoding='utf-8',
    )
    (output_root / 'himalayan_top10_feature_gap_matrix.json').write_text(
        json.dumps(top10_matrix, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'himalayan_top10_feature_gap_matrix.md').write_text(
        markdown_himalayan_top10_feature_gap_matrix(top10_matrix),
        encoding='utf-8',
    )
    (output_root / 'partner_source_manifest_template.json').write_text(
        json.dumps(source_manifest_template, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_source_manifest_template.md').write_text(
        markdown_partner_source_manifest_template(source_manifest_template),
        encoding='utf-8',
    )
    (output_root / 'partner_intake_checklist.json').write_text(
        json.dumps(intake_checklist, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_intake_checklist.md').write_text(
        markdown_partner_evidence_intake_checklist(intake_checklist),
        encoding='utf-8',
    )
    (output_root / 'partner_intake_dry_run_runbook.json').write_text(
        json.dumps(intake_dry_run_runbook, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_intake_dry_run_runbook.md').write_text(
        markdown_partner_intake_dry_run_runbook(intake_dry_run_runbook),
        encoding='utf-8',
    )
    (output_root / 'partner_incoming_triage_runbook.json').write_text(
        json.dumps(incoming_triage_runbook, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_incoming_triage_runbook.md').write_text(
        markdown_partner_incoming_triage_runbook(incoming_triage_runbook),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_protocol.json').write_text(
        json.dumps(local_holdout_protocol, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_protocol.md').write_text(
        markdown_himalayan_local_holdout_protocol(local_holdout_protocol),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_leakage_audit.json').write_text(
        json.dumps(holdout_leakage_audit, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_leakage_audit.md').write_text(
        markdown_himalayan_local_holdout_leakage_audit(holdout_leakage_audit),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_metric_report.json').write_text(
        json.dumps(holdout_metric_report, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_metric_report.md').write_text(
        markdown_himalayan_local_holdout_metric_report(holdout_metric_report),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_prediction_template.json').write_text(
        json.dumps(local_holdout_prediction_template, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'himalayan_local_holdout_prediction_template.md').write_text(
        markdown_himalayan_local_holdout_prediction_template(local_holdout_prediction_template),
        encoding='utf-8',
    )
    write_himalayan_local_holdout_prediction_template_csv(
        output_root / 'himalayan_local_holdout_predictions.csv'
    )
    (output_root / 'release_gate_attestation_template_pack.json').write_text(
        json.dumps(release_gate_attestation_template_pack, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'release_gate_attestation_template_pack.md').write_text(
        markdown_release_gate_attestation_template_pack(release_gate_attestation_template_pack),
        encoding='utf-8',
    )
    (output_root / 'partner_field_dictionary.json').write_text(
        json.dumps(field_dictionary, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_field_dictionary.md').write_text(
        markdown_partner_field_dictionary(field_dictionary),
        encoding='utf-8',
    )
    (output_root / 'partner_sample_row_pack.json').write_text(
        json.dumps(sample_row_pack, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_sample_row_pack.md').write_text(
        markdown_partner_sample_row_pack(sample_row_pack),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_quality_score.json').write_text(
        json.dumps(submission_quality_score, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_quality_score.md').write_text(
        markdown_partner_submission_quality_score(submission_quality_score),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_acceptance_checklist.json').write_text(
        json.dumps(acceptance_checklist, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_acceptance_checklist.md').write_text(
        markdown_partner_submission_acceptance_checklist(acceptance_checklist),
        encoding='utf-8',
    )
    (output_root / 'partner_handoff_readme.json').write_text(
        json.dumps(handoff_readme, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_handoff_readme.md').write_text(
        markdown_partner_handoff_readme(handoff_readme),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_manifest_diff.json').write_text(
        json.dumps(manifest_diff, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_manifest_diff.md').write_text(
        markdown_partner_submission_manifest_diff(manifest_diff),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_review_ledger.json').write_text(
        json.dumps(submission_review_ledger, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_review_ledger.md').write_text(
        markdown_partner_submission_review_ledger(submission_review_ledger),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_status_dashboard.json').write_text(
        json.dumps(submission_status_dashboard, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_submission_status_dashboard.md').write_text(
        markdown_partner_submission_status_dashboard(submission_status_dashboard),
        encoding='utf-8',
    )
    (output_root / 'partner_source_package_checksum_guide.json').write_text(
        json.dumps(checksum_guide, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_source_package_checksum_guide.md').write_text(
        markdown_partner_source_package_checksum_guide(checksum_guide),
        encoding='utf-8',
    )
    (output_root / 'partner_package_index.json').write_text(
        json.dumps(package_index, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'partner_package_index.md').write_text(
        markdown_partner_package_index(package_index),
        encoding='utf-8',
    )
    return payload


def _parse_float(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None

def _field_validation_error(column: str, value: object) -> str | None:
    if _is_blank(value):
        return None
    raw = str(value).strip()
    normalized = column.lower()
    if normalized in {'source_ref', 'evidence_ref'}:
        return _reference_digest_error(column, raw)
    if normalized in CONTROLLED_VALUE_SETS:
        canonical = _normalize_controlled_value(raw)
        if canonical not in CONTROLLED_VALUE_SETS[normalized]:
            allowed = ', '.join(sorted(CONTROLLED_VALUE_SETS[normalized]))
            return f'{column} must use one controlled value: {allowed}'
        return None
    if normalized == 'latitude':
        parsed = _parse_float(raw)
        if parsed is None or parsed < -90.0 or parsed > 90.0:
            return 'latitude must be a decimal degree in [-90, 90]'
    elif normalized == 'longitude':
        parsed = _parse_float(raw)
        if parsed is None or parsed < -180.0 or parsed > 180.0:
            return 'longitude must be a decimal degree in [-180, 180]'
    elif normalized in {'elevation_m', 'critical_elevation_m'}:
        parsed = _parse_float(raw)
        if parsed is None or parsed < 0.0 or parsed > 9000.0:
            return f'{column} must be numeric in [0, 9000]'
    elif normalized == 'danger_level_1_to_4':
        parsed = _parse_float(raw)
        if parsed is None or parsed % 1 != 0 or int(parsed) not in {1, 2, 3, 4}:
            return 'danger_level_1_to_4 must be an integer from 1 to 4'
    elif normalized == 'danger_level_1_to_5':
        parsed = _parse_float(raw)
        if parsed is None or parsed % 1 != 0 or int(parsed) not in {1, 2, 3, 4, 5}:
            return 'danger_level_1_to_5 must be an integer from 1 to 5'
    elif normalized in {'confidence', 'stability_index'}:
        parsed = _parse_float(raw)
        if parsed is None or parsed < 0.0 or parsed > 1.0:
            return f'{column} must be numeric in [0, 1]'
    elif normalized == 'slope':
        parsed = _parse_float(raw)
        if parsed is None or parsed < 0.0 or parsed > 90.0:
            return 'slope must be numeric in [0, 90]'
    elif normalized in {
        'observed_at',
        'valid_from',
        'valid_to',
        'acquired_at',
        'reviewed_at',
        'forecast_issue_time',
        'valid_at',
    }:
        if _parse_datetime(raw) is None:
            return f'{column} must be ISO-8601 parseable'
    elif normalized in {'window_center_local_time', 'profile_extracted_at_local_time'}:
        if re.match(r'^\d{2}:\d{2}$', raw) is None:
            return f'{column} must be local HH:MM time'
        hours, minutes = (int(part) for part in raw.split(':'))
        if hours > 23 or minutes > 59:
            return f'{column} must be local HH:MM time'
    elif normalized == 'aggregation_window_hours':
        parsed = _parse_float(raw)
        if parsed is None or parsed <= 0.0 or parsed > 72.0:
            return 'aggregation_window_hours must be numeric in (0, 72]'
    elif normalized == 'holdout_split':
        if raw.lower() not in ALLOWED_HOLDOUT_SPLITS:
            allowed = ', '.join(sorted(ALLOWED_HOLDOUT_SPLITS))
            return f'holdout_split must be one of: {allowed}'
    elif normalized == 'aspect':
        parsed = _parse_float(raw)
        if parsed is None:
            if raw.lower() not in ALLOWED_ASPECT_VALUES:
                return 'aspect must be a degree in [0, 360] or a recognized compass sector'
        elif parsed < 0.0 or parsed > 360.0:
            return 'aspect must be a degree in [0, 360] or a recognized compass sector'
    return None


def _datetime_timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _rounded_float(value: float) -> float:
    return round(value, 6)


def _station_coverage_diagnostics(
    requirement: EvidenceRequirement,
    *,
    distinct_counts: dict[str, int],
    distinct_count_shortfalls: dict[str, int],
    numeric_spans: dict[str, float],
    numeric_span_shortfalls: dict[str, float],
) -> dict[str, Any]:
    if requirement.key != 'station_metadata':
        return {}
    sparse_warnings: list[str] = []
    if distinct_count_shortfalls.get('station_id', 0) > 0:
        sparse_warnings.append('sparse_station_count')
    if distinct_count_shortfalls.get('region_key', 0) > 0:
        sparse_warnings.append('sparse_region_count')
    if numeric_span_shortfalls.get('elevation_m', 0.0) > 0:
        sparse_warnings.append('narrow_elevation_span')
    return {
        'diagnostic_type': 'gpxyz_station_coverage',
        'station_count': int(distinct_counts.get('station_id', 0)),
        'region_count': int(distinct_counts.get('region_key', 0)),
        'elevation_span_m': float(numeric_spans.get('elevation_m', 0.0)),
        'minimum_station_count': int(requirement.minimum_distinct_counts.get('station_id', 0)),
        'minimum_region_count': int(requirement.minimum_distinct_counts.get('region_key', 0)),
        'minimum_elevation_span_m': float(requirement.minimum_numeric_spans.get('elevation_m', 0.0)),
        'sparse_coverage_warnings': sparse_warnings,
        'gpxyz_claim_boundary': (
            'latitude_longitude_elevation_are_required_for_gpxyz; '
            'complex_terrain_covariates_are_optional_future_evidence_not_the_default_gp_input'
        ),
    }


def _normalize_controlled_value(value: object) -> str:
    normalized = str(value).strip().lower()
    for old, new in (('-', '_'), (' ', '_'), ('/', '_')):
        normalized = normalized.replace(old, new)
    while '__' in normalized:
        normalized = normalized.replace('__', '_')
    return normalized


def _split_reference_values(value: object, *, multi_value: bool) -> list[str]:
    if _is_blank(value):
        return []
    raw = str(value).strip()
    if not multi_value:
        return [raw]
    values = [raw]
    for delimiter in (';', '|', ','):
        split_values: list[str] = []
        for item in values:
            split_values.extend(item.split(delimiter))
        values = split_values
    return [item.strip() for item in values if item.strip()]


def _read_evidence_rows(evidence_root: Path, requirement_key: str) -> list[dict[str, str]]:
    path = evidence_root / f'{requirement_key}.csv'
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def validate_partner_evidence_file(
    evidence_root: Path,
    requirement: EvidenceRequirement,
    *,
    generated_at: datetime,
    source_manifest_available: bool,
    source_manifest_hashes: set[str],
) -> dict[str, Any]:
    expected_columns = partner_template_columns(requirement)
    path = evidence_root / f'{requirement.key}.csv'
    if not path.exists():
        return {
            'requirement_key': requirement.key,
            'filename': path.name,
            'status': STATUS_PARTNER_REQUIRED,
            'decision': 'missing_partner_evidence_file',
            'row_count': 0,
            'minimum_row_count': requirement.minimum_rows_for_availability,
            'sufficient_row_count': False,
            'row_count_shortfall': requirement.minimum_rows_for_availability,
            'minimum_distinct_counts': dict(requirement.minimum_distinct_counts),
            'distinct_counts': {},
            'distinct_count_shortfalls': dict(requirement.minimum_distinct_counts),
            'sufficient_distinct_coverage': False,
            'minimum_temporal_span_days': dict(requirement.minimum_temporal_span_days),
            'temporal_span_days': {},
            'temporal_span_shortfalls': dict(requirement.minimum_temporal_span_days),
            'sufficient_temporal_coverage': False,
            'minimum_numeric_spans': dict(requirement.minimum_numeric_spans),
            'numeric_spans': {},
            'numeric_span_shortfalls': dict(requirement.minimum_numeric_spans),
            'sufficient_numeric_coverage': False,
            'coverage_diagnostics': _station_coverage_diagnostics(
                requirement,
                distinct_counts={},
                distinct_count_shortfalls=dict(requirement.minimum_distinct_counts),
                numeric_spans={},
                numeric_span_shortfalls=dict(requirement.minimum_numeric_spans),
            ),
            'missing_columns': list(expected_columns),
            'incomplete_row_count': 0,
            'unreviewed_row_count': 0,
            'invalid_value_count': 0,
            'invalid_value_examples': [],
            'controlled_value_counts': {},
            'label_provenance_gate': {},
            'license_scope_counts': {},
            'unsupported_license_scope_count': 0,
            'unsupported_license_scope_examples': [],
            'license_scope_check_status': 'blocked_license_scope_missing',
            'max_review_age_days': PARTNER_EVIDENCE_REVIEW_MAX_AGE_DAYS,
            'review_age_days_max': None,
            'stale_review_row_count': 0,
            'future_review_row_count': 0,
            'review_freshness_status': 'missing_file',
            'source_ref_integrity_status': 'missing_file',
            'source_ref_integrity_counts': {},
            'source_ref_issue_count': 0,
            'source_ref_issue_examples': [],
            'source_ref_manifest_status': 'missing_file',
            'source_ref_manifest_issue_count': 0,
            'source_ref_manifest_issue_examples': [],
            'source_ref_hashes': [],
        }

    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        rows = list(reader)

    missing_columns = [column for column in expected_columns if column not in columns]
    required_value_columns = [
        column
        for column in (
            *requirement.required_fields,
            'source_ref',
            'license_scope',
            'review_status',
            'reviewer_id',
            'reviewed_at',
        )
        if column in columns
    ]
    incomplete_row_count = 0
    unreviewed_row_count = 0
    invalid_value_count = 0
    invalid_value_examples: list[dict[str, Any]] = []
    controlled_value_counts: dict[str, dict[str, int]] = {}
    license_scope_counts: dict[str, int] = {}
    unsupported_license_scope_examples: list[str] = []
    review_ages: list[float] = []
    stale_review_row_count = 0
    future_review_row_count = 0
    source_ref_integrity_counts: dict[str, int] = {}
    source_ref_hashes: set[str] = set()
    source_ref_issue_count = 0
    source_ref_issue_examples: list[dict[str, Any]] = []
    for row_idx, row in enumerate(rows, start=2):
        if any(_is_blank(row.get(column)) for column in required_value_columns):
            incomplete_row_count += 1
        review_status = str(row.get('review_status') or '').strip().lower()
        if review_status != 'reviewed':
            unreviewed_row_count += 1
        license_scope = row.get('license_scope')
        if not _is_blank(license_scope):
            canonical_license_scope = _normalize_controlled_value(license_scope)
            license_scope_counts[canonical_license_scope] = license_scope_counts.get(canonical_license_scope, 0) + 1
            if (
                canonical_license_scope not in LICENSE_SCOPES_SUPPORTING_RESEARCH_VALIDATION
                and len(unsupported_license_scope_examples) < 5
            ):
                unsupported_license_scope_examples.append(str(license_scope).strip())
        for column in required_value_columns:
            error = _field_validation_error(column, row.get(column))
            if error is not None:
                invalid_value_count += 1
                if len(invalid_value_examples) < 5:
                    invalid_value_examples.append(
                        {
                            'row_number': row_idx,
                            'column': column,
                            'value': row.get(column),
                            'error': error,
                        }
                    )
            if column in CONTROLLED_VALUE_SETS and not _is_blank(row.get(column)):
                canonical_value = _normalize_controlled_value(row.get(column))
                value_counts = controlled_value_counts.setdefault(column, {})
                value_counts[canonical_value] = value_counts.get(canonical_value, 0) + 1
        reviewed_at = _parse_datetime(row.get('reviewed_at'))
        if reviewed_at is not None:
            review_age_days = _review_age_days(generated_at=generated_at, reviewed_at=reviewed_at)
            review_ages.append(review_age_days)
            if review_age_days > PARTNER_EVIDENCE_REVIEW_MAX_AGE_DAYS:
                stale_review_row_count += 1
            if review_age_days < -MAX_REVIEW_FUTURE_SKEW_DAYS:
                future_review_row_count += 1
        source_ref = row.get('source_ref')
        if not _is_blank(source_ref):
            source_ref_integrity_counts[_reference_kind(source_ref)] = (
                source_ref_integrity_counts.get(_reference_kind(source_ref), 0) + 1
            )
            declared_digest = _extract_declared_sha256(source_ref)
            if declared_digest is not None:
                source_ref_hashes.add(declared_digest)
            source_ref_issue = _source_ref_integrity_issue(source_ref, evidence_root=evidence_root)
            if source_ref_issue is not None:
                source_ref_issue_count += 1
                if len(source_ref_issue_examples) < 5:
                    source_ref_issue_examples.append({'row_number': row_idx, **source_ref_issue})

    decision = 'available_reviewed_partner_evidence'
    status = STATUS_AVAILABLE
    review_age_days_max = max(review_ages) if review_ages else None
    if future_review_row_count:
        review_freshness_status = 'blocked_future_reviewed_at'
    elif stale_review_row_count:
        review_freshness_status = 'blocked_stale_reviewed_at'
    elif review_ages:
        review_freshness_status = 'passed'
    else:
        review_freshness_status = 'not_available'
    if source_ref_issue_count:
        source_ref_integrity_status = 'blocked_unverified_source_refs'
    elif source_ref_integrity_counts:
        source_ref_integrity_status = 'passed'
    else:
        source_ref_integrity_status = 'not_available'
    missing_manifest_hashes = sorted(source_ref_hashes - source_manifest_hashes)
    source_ref_manifest_issue_count = 0
    source_ref_manifest_issue_examples: list[dict[str, Any]] = []
    if source_ref_hashes and not source_manifest_available:
        source_ref_manifest_status = 'blocked_manifest_missing_or_invalid'
        source_ref_manifest_issue_count = len(source_ref_hashes)
        source_ref_manifest_issue_examples = [
            {
                'sha256': digest,
                'error': 'source hash requires a valid partner source manifest entry',
            }
            for digest in sorted(source_ref_hashes)[:5]
        ]
    elif missing_manifest_hashes:
        source_ref_manifest_status = 'blocked_missing_manifest_hashes'
        source_ref_manifest_issue_count = len(missing_manifest_hashes)
        source_ref_manifest_issue_examples = [
            {
                'sha256': digest,
                'error': 'source hash is absent from the partner source manifest',
            }
            for digest in missing_manifest_hashes[:5]
        ]
    elif source_ref_hashes:
        source_ref_manifest_status = 'passed'
    else:
        source_ref_manifest_status = 'not_available'
    row_count_shortfall = max(requirement.minimum_rows_for_availability - len(rows), 0)
    sufficient_row_count = row_count_shortfall == 0
    distinct_counts = {
        column: len({str(row.get(column)).strip() for row in rows if not _is_blank(row.get(column))})
        for column in requirement.minimum_distinct_counts
        if column in columns
    }
    distinct_count_shortfalls = {
        column: max(minimum - distinct_counts.get(column, 0), 0)
        for column, minimum in requirement.minimum_distinct_counts.items()
    }
    sufficient_distinct_coverage = not any(distinct_count_shortfalls.values())
    temporal_span_days: dict[str, float] = {}
    for column in requirement.minimum_temporal_span_days:
        if column not in columns:
            continue
        values = [
            _parse_datetime(row.get(column))
            for row in rows
            if not _is_blank(row.get(column))
        ]
        valid_values = [value for value in values if value is not None]
        if valid_values:
            min_ts = min(_datetime_timestamp(value) for value in valid_values)
            max_ts = max(_datetime_timestamp(value) for value in valid_values)
            temporal_span_days[column] = _rounded_float((max_ts - min_ts) / 86400.0)
    temporal_span_shortfalls = {
        column: _rounded_float(max(minimum - temporal_span_days.get(column, 0.0), 0.0))
        for column, minimum in requirement.minimum_temporal_span_days.items()
    }
    sufficient_temporal_coverage = not any(temporal_span_shortfalls.values())
    numeric_spans: dict[str, float] = {}
    for column in requirement.minimum_numeric_spans:
        if column not in columns:
            continue
        values = [
            _parse_float(row.get(column))
            for row in rows
            if not _is_blank(row.get(column))
        ]
        valid_values = [value for value in values if value is not None]
        if valid_values:
            numeric_spans[column] = _rounded_float(max(valid_values) - min(valid_values))
    numeric_span_shortfalls = {
        column: _rounded_float(max(minimum - numeric_spans.get(column, 0.0), 0.0))
        for column, minimum in requirement.minimum_numeric_spans.items()
    }
    sufficient_numeric_coverage = not any(numeric_span_shortfalls.values())
    coverage_diagnostics = _station_coverage_diagnostics(
        requirement,
        distinct_counts=distinct_counts,
        distinct_count_shortfalls=distinct_count_shortfalls,
        numeric_spans=numeric_spans,
        numeric_span_shortfalls=numeric_span_shortfalls,
    )
    unsupported_license_scope_count = sum(
        count
        for scope, count in license_scope_counts.items()
        if scope not in LICENSE_SCOPES_SUPPORTING_RESEARCH_VALIDATION
    )
    label_provenance_gate: dict[str, Any] = {}
    if requirement.key == 'danger_labels_and_bulletins':
        label_source_counts = controlled_value_counts.get('label_source', {})
        regime_counts = controlled_value_counts.get('avalanche_regime', {})
        raw_forecast_only = (
            set(label_source_counts) <= {'official_forecast'}
            and len(rows) > 0
        )
        corroboration_issue_count = 0
        corroboration_issue_examples: list[dict[str, Any]] = []
        for row_idx, row in enumerate(rows, start=2):
            label_source = _normalize_controlled_value(row.get('label_source'))
            tidy_basis = str(row.get('tidy_label_review_basis') or '').strip()
            nowcast_ref = str(row.get('nowcast_evidence_ref') or '').strip()
            observer_ref = str(row.get('observer_evidence_ref') or '').strip()
            corroborated = bool(tidy_basis and nowcast_ref and observer_ref)
            if not corroborated:
                corroboration_issue_count += 1
                if len(corroboration_issue_examples) < 5:
                    corroboration_issue_examples.append(
                        {
                            'row_number': row_idx,
                            'label_source': label_source,
                            'error': (
                                'danger labels require tidy review basis plus nowcast and observer evidence refs; '
                                'raw official forecasts alone are not D_tidy-grade training truth'
                            ),
                        }
                    )
        if corroboration_issue_count:
            decision = 'blocked_raw_forecast_label_provenance'
            status = STATUS_PARTNER_REQUIRED
        label_provenance_gate = {
            'gate': 'd_tidy_label_provenance',
            'status': 'passed' if not corroboration_issue_count and len(rows) > 0 else 'blocked',
            'raw_forecast_only': raw_forecast_only,
            'label_source_counts': label_source_counts,
            'avalanche_regime_counts': regime_counts,
            'corroboration_issue_count': corroboration_issue_count,
            'corroboration_issue_examples': corroboration_issue_examples,
            'required_fields': [
                'label_source',
                'tidy_label_review_basis',
                'nowcast_evidence_ref',
                'observer_evidence_ref',
                'avalanche_regime',
                'forecast_issue_time',
                'valid_at',
                'window_center_local_time',
            ],
            'claim_boundary': (
                'Public bulletins are context only. D_tidy-grade labels require reviewed provenance, '
                'timing alignment, regime scope, and nowcast/observer corroboration.'
            ),
        }
    license_scope_check_status = 'passed' if not unsupported_license_scope_count else 'blocked_unsupported_scope'
    if missing_columns:
        decision = 'blocked_partner_evidence_schema_mismatch'
        status = STATUS_PARTNER_REQUIRED
    elif not rows:
        decision = 'blocked_empty_partner_evidence_file'
        status = STATUS_PARTNER_REQUIRED
    elif incomplete_row_count:
        decision = 'blocked_incomplete_partner_evidence_rows'
        status = STATUS_PARTNER_REQUIRED
    elif unreviewed_row_count:
        decision = 'blocked_unreviewed_partner_evidence_rows'
        status = STATUS_PARTNER_REQUIRED
    elif invalid_value_count:
        decision = 'blocked_invalid_partner_evidence_values'
        status = STATUS_PARTNER_REQUIRED
    elif source_ref_issue_count:
        decision = 'blocked_unverified_partner_evidence_source_refs'
        status = STATUS_PARTNER_REQUIRED
    elif future_review_row_count:
        decision = 'blocked_future_partner_evidence_review'
        status = STATUS_PARTNER_REQUIRED
    elif stale_review_row_count:
        decision = 'blocked_stale_partner_evidence_review'
        status = STATUS_PARTNER_REQUIRED
    elif unsupported_license_scope_count:
        decision = 'blocked_unsupported_partner_evidence_license_scope'
        status = STATUS_PARTNER_REQUIRED
    elif not sufficient_row_count:
        decision = 'blocked_insufficient_partner_evidence_rows'
        status = STATUS_PARTNER_REQUIRED
    elif not sufficient_distinct_coverage:
        decision = 'blocked_insufficient_partner_evidence_diversity'
        status = STATUS_PARTNER_REQUIRED
    elif not sufficient_temporal_coverage:
        decision = 'blocked_insufficient_partner_evidence_temporal_coverage'
        status = STATUS_PARTNER_REQUIRED
    elif not sufficient_numeric_coverage:
        decision = 'blocked_insufficient_partner_evidence_numeric_coverage'
        status = STATUS_PARTNER_REQUIRED
    elif source_ref_manifest_issue_count:
        decision = 'blocked_partner_source_manifest'
        status = STATUS_PARTNER_REQUIRED

    return {
        'requirement_key': requirement.key,
        'filename': path.name,
        'status': status,
        'decision': decision,
        'row_count': len(rows),
        'minimum_row_count': requirement.minimum_rows_for_availability,
        'sufficient_row_count': sufficient_row_count,
        'row_count_shortfall': row_count_shortfall,
        'minimum_distinct_counts': dict(requirement.minimum_distinct_counts),
        'distinct_counts': distinct_counts,
        'distinct_count_shortfalls': distinct_count_shortfalls,
        'sufficient_distinct_coverage': sufficient_distinct_coverage,
        'minimum_temporal_span_days': dict(requirement.minimum_temporal_span_days),
        'temporal_span_days': temporal_span_days,
        'temporal_span_shortfalls': temporal_span_shortfalls,
        'sufficient_temporal_coverage': sufficient_temporal_coverage,
        'minimum_numeric_spans': dict(requirement.minimum_numeric_spans),
        'numeric_spans': numeric_spans,
        'numeric_span_shortfalls': numeric_span_shortfalls,
        'sufficient_numeric_coverage': sufficient_numeric_coverage,
        'coverage_diagnostics': coverage_diagnostics,
        'missing_columns': missing_columns,
        'incomplete_row_count': incomplete_row_count,
        'unreviewed_row_count': unreviewed_row_count,
        'invalid_value_count': invalid_value_count,
        'invalid_value_examples': invalid_value_examples,
        'controlled_value_counts': controlled_value_counts,
        'label_provenance_gate': label_provenance_gate,
        'license_scope_counts': license_scope_counts,
        'unsupported_license_scope_count': unsupported_license_scope_count,
        'unsupported_license_scope_examples': unsupported_license_scope_examples,
        'license_scope_check_status': license_scope_check_status,
        'max_review_age_days': PARTNER_EVIDENCE_REVIEW_MAX_AGE_DAYS,
        'review_age_days_max': review_age_days_max,
        'stale_review_row_count': stale_review_row_count,
        'future_review_row_count': future_review_row_count,
        'review_freshness_status': review_freshness_status,
        'source_ref_integrity_status': source_ref_integrity_status,
        'source_ref_integrity_counts': source_ref_integrity_counts,
        'source_ref_issue_count': source_ref_issue_count,
        'source_ref_issue_examples': source_ref_issue_examples,
        'source_ref_manifest_status': source_ref_manifest_status,
        'source_ref_manifest_issue_count': source_ref_manifest_issue_count,
        'source_ref_manifest_issue_examples': source_ref_manifest_issue_examples,
        'source_ref_hashes': sorted(source_ref_hashes),
    }


def _apply_reference_integrity_checks(
    *,
    evidence_root: Path,
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {str(report['requirement_key']): report for report in reports}
    rows_by_key: dict[str, list[dict[str, str]]] = {}
    reference_rules_by_source = _reference_requirements_by_source()

    for report in reports:
        requirement_key = str(report['requirement_key'])
        rules = reference_rules_by_source.get(requirement_key, [])
        report['reference_requirements'] = [rule.as_dict() for rule in rules]
        report['reference_violations'] = []
        report['reference_check_status'] = 'not_applicable' if not rules else 'pending'

    for rule in REFERENCE_REQUIREMENTS:
        source_report = by_key.get(rule.source_requirement)
        target_report = by_key.get(rule.target_requirement)
        if source_report is None:
            continue
        if source_report.get('status') != STATUS_AVAILABLE:
            source_report['reference_check_status'] = 'skipped_source_not_available'
            continue
        if target_report is None or target_report.get('status') != STATUS_AVAILABLE:
            source_report['status'] = STATUS_PARTNER_REQUIRED
            source_report['decision'] = 'blocked_partner_evidence_reference_unavailable'
            source_report.setdefault('reference_violations', []).append(
                {
                    'source_field': rule.source_field,
                    'target_requirement': rule.target_requirement,
                    'target_field': rule.target_field,
                    'missing_reference_count': None,
                    'missing_reference_examples': [],
                    'error': 'target requirement is not available',
                }
            )
            source_report['reference_check_status'] = 'blocked_reference_unavailable'
            continue

        source_rows = rows_by_key.setdefault(rule.source_requirement, _read_evidence_rows(evidence_root, rule.source_requirement))
        target_rows = rows_by_key.setdefault(rule.target_requirement, _read_evidence_rows(evidence_root, rule.target_requirement))
        allowed = {
            str(row.get(rule.target_field)).strip()
            for row in target_rows
            if not _is_blank(row.get(rule.target_field))
        }
        referenced_values: list[str] = []
        for row in source_rows:
            referenced_values.extend(
                _split_reference_values(row.get(rule.source_field), multi_value=rule.multi_value)
            )
        missing_values = sorted({value for value in referenced_values if value not in allowed})
        if missing_values:
            source_report['status'] = STATUS_PARTNER_REQUIRED
            source_report['decision'] = 'blocked_partner_evidence_orphan_references'
            source_report.setdefault('reference_violations', []).append(
                {
                    'source_field': rule.source_field,
                    'target_requirement': rule.target_requirement,
                    'target_field': rule.target_field,
                    'missing_reference_count': len(missing_values),
                    'missing_reference_examples': missing_values[:5],
                    'error': 'source values do not exist in target evidence file',
                }
            )
            source_report['reference_check_status'] = 'blocked_orphan_references'
        elif source_report.get('reference_check_status') in {'pending', 'passed'}:
            source_report['reference_check_status'] = 'passed'

    return reports


def validate_partner_evidence_root(
    evidence_root: Path,
    *,
    generated_at: datetime | None = None,
    partner_source_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    partner_source_manifest_report = validate_partner_source_manifest(
        partner_source_manifest,
        generated_at=generated_at,
    )
    source_manifest_available = (
        partner_source_manifest_report['decision'] == 'partner_source_manifest_available'
    )
    source_manifest_hashes = set(partner_source_manifest_report.get('valid_source_hashes', []))
    reports = [
        validate_partner_evidence_file(
            evidence_root,
            requirement,
            generated_at=generated_at,
            source_manifest_available=source_manifest_available,
            source_manifest_hashes=source_manifest_hashes,
        )
        for requirement in REQUIREMENTS
    ]
    reports = _apply_reference_integrity_checks(evidence_root=evidence_root, reports=reports)
    status_overrides = {
        str(report['requirement_key']): str(report['status'])
        for report in reports
    }
    blocked = [str(report['requirement_key']) for report in reports if report['status'] != STATUS_AVAILABLE]
    return {
        'schema_version': PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'deprecated_schema_versions': list(DEPRECATED_SCHEMA_VERSIONS),
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': 'all_partner_evidence_available' if not blocked else 'blocked_pending_partner_evidence',
        'evidence_root': str(evidence_root),
        'available_requirements': [key for key, status in status_overrides.items() if status == STATUS_AVAILABLE],
        'blocked_requirements': blocked,
        'status_overrides': status_overrides,
        'partner_source_manifest': partner_source_manifest_report,
        'reports': reports,
    }


def markdown_partner_evidence_validation(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Evidence Validation',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        '| Requirement | Status | Decision | Rows | Minimum rows | Row shortfall | Distinct shortfalls | Span shortfalls | Review freshness | Source refs | Source manifest | License check | Reference check | Missing columns | Incomplete rows | Unreviewed rows | Invalid values |',
        '|---|---|---|---:|---:|---:|---|---|---|---|---|---|---|---|---:|---:|---:|',
    ]
    for report in payload['reports']:
        span_shortfalls = [
            f"`{column}`: {shortfall:g} days"
            for column, shortfall in report.get('temporal_span_shortfalls', {}).items()
            if shortfall
        ]
        span_shortfalls.extend(
            f"`{column}`: {shortfall:g}"
            for column, shortfall in report.get('numeric_span_shortfalls', {}).items()
            if shortfall
        )
        lines.append(
            '| {key} | `{status}` | `{decision}` | {rows} | {minimum_rows} | {shortfall} | {distinct_shortfalls} | {span_shortfalls} | `{review_freshness}` | `{source_ref_status}` | `{source_manifest_status}` | `{license_status}` | `{reference_status}` | {missing} | {incomplete} | {unreviewed} | {invalid} |'.format(
                key=report['requirement_key'],
                status=report['status'],
                decision=report['decision'],
                rows=report['row_count'],
                minimum_rows=report.get('minimum_row_count', 1),
                shortfall=report.get('row_count_shortfall', 0),
                distinct_shortfalls=', '.join(
                    f"`{column}`: {shortfall}"
                    for column, shortfall in report.get('distinct_count_shortfalls', {}).items()
                    if shortfall
                ) or 'None',
                span_shortfalls=', '.join(span_shortfalls) or 'None',
                review_freshness=report.get('review_freshness_status', 'not_checked'),
                source_ref_status=report.get('source_ref_integrity_status', 'not_checked'),
                source_manifest_status=report.get('source_ref_manifest_status', 'not_checked'),
                license_status=report.get('license_scope_check_status', 'not_checked'),
                reference_status=report.get('reference_check_status', 'not_applicable'),
                missing=', '.join(report['missing_columns']) or 'None',
                incomplete=report['incomplete_row_count'],
                unreviewed=report['unreviewed_row_count'],
                invalid=report.get('invalid_value_count', 0),
            )
        )
    lines.append('')
    return '\n'.join(lines)


def _synthetic_row_count(requirement: EvidenceRequirement) -> int:
    row_count = requirement.minimum_rows_for_availability
    if requirement.minimum_distinct_counts:
        row_count = max(row_count, max(requirement.minimum_distinct_counts.values()))
    if requirement.key == 'warning_region_polygons':
        row_count = max(row_count, 3)
    return row_count


def _synthetic_timestamp(generated_at: datetime, row_index: int, *, offset_days: int = 60) -> str:
    value = _ensure_timezone(generated_at) - timedelta(days=offset_days - row_index)
    return value.isoformat()


def _synthetic_date_range(generated_at: datetime) -> str:
    start = (_ensure_timezone(generated_at) - timedelta(days=90)).date().isoformat()
    end = (_ensure_timezone(generated_at) - timedelta(days=1)).date().isoformat()
    return f'{start}/{end}'


def _synthetic_partner_value_for_column(
    column: str,
    *,
    row_index: int,
    generated_at: datetime,
    source_ref: str,
) -> str:
    day_timestamp = _synthetic_timestamp(generated_at, row_index)
    next_day_timestamp = _synthetic_timestamp(generated_at, row_index + 1)
    values = {
        'source_ref': source_ref,
        'license_scope': 'internal_research_validation',
        'review_status': 'reviewed',
        'reviewer_id': 'synthetic_validation_fixture_reviewer',
        'reviewed_at': day_timestamp,
        'reviewer_notes': 'SYNTHETIC_VALIDATION_ONLY_NOT_PARTNER_EVIDENCE',
        'station_id': f'station_id_value_{row_index % 10}',
        'region_key': f'region_key_value_{row_index % 3}',
        'region_id': f'region_id_value_{row_index % 3}',
        'region_ids': 'region_id_value_0;region_id_value_1;region_id_value_2',
        'latitude': f'{31.25 + (row_index * 0.01):.4f}',
        'longitude': f'{78.12 + (row_index * 0.01):.4f}',
        'elevation_m': str(3200 + (row_index * 100)),
        'active_date_range': _synthetic_date_range(generated_at),
        'observed_at': day_timestamp,
        'valid_from': day_timestamp,
        'valid_to': next_day_timestamp,
        'forecast_issue_time': day_timestamp,
        'valid_at': day_timestamp,
        'date_range': _synthetic_date_range(generated_at),
        'valid_date_range': _synthetic_date_range(generated_at),
        'air_temp_c': f'{-8.0 + (row_index % 12):.1f}',
        'precipitation_mm': f'{row_index % 7:.1f}',
        'snowfall_cm': f'{(row_index % 9) * 2:.1f}',
        'snow_depth_cm': f'{80 + row_index:.1f}',
        'wind_speed_ms': f'{4 + (row_index % 8):.1f}',
        'wind_dir_deg': str((row_index * 30) % 360),
        'layer_index': str((row_index % 6) + 1),
        'layer_depth_cm': str(20 + (row_index * 3)),
        'grain_type': f'grain_type_value_{row_index % 4}',
        'hardness_index': f'{0.2 + ((row_index % 5) * 0.1):.2f}',
        'stability_index': '0.64',
        'quality_flag': 'reviewed_valid',
        'profile_model': 'HIM_STRAT_REVIEWED_SYNTHETIC',
        'snowpack_model_version': 'synthetic_v1',
        'profile_extracted_at_local_time': '12:00',
        'stability_metric_name': 'stability_index',
        'danger_scale_standard': 'eaws_5_level',
        'danger_level_1_to_5': str((row_index % 5) + 1),
        'danger_level_1_to_4': str((row_index % 4) + 1),
        'label_source': 'tidy_reanalysis',
        'tidy_label_review_basis': 'local_nowcast_and_observer_confirmed_synthetic',
        'nowcast_evidence_ref': f'nowcast_evidence_ref_value_{row_index}',
        'observer_evidence_ref': f'observer_evidence_ref_value_{row_index}',
        'forecast_cycle': 'nowcast',
        'window_center_local_time': '12:00',
        'aggregation_window_hours': '24',
        'avalanche_regime': 'dry_snow',
        'critical_elevation_m': str(2800 + (row_index * 50)),
        'aspect_policy': 'all',
        'avalanche_problem': 'wind_slab',
        'elevation_band_policy': 'synthetic_elev_bands_1200_1600_2000_2400',
        'forecaster_or_reviewer_id': 'synthetic_forecaster',
        'polygon_geometry': f'SYNTHETIC_POLYGON_{row_index}',
        'crs': 'EPSG:4326',
        'elevation_policy': 'synthetic_elevation_policy',
        'event_id': f'event_id_value_{row_index}',
        'aspect': str((row_index * 30) % 360),
        'observed_outcome': 'avalanche_observed',
        'confidence': '0.82',
        'source': 'synthetic_validation_fixture',
        'field_report_ref': f'field_report_ref_value_{row_index}',
        'avalanche_atlas_ref': f'avalanche_atlas_ref_value_{row_index}',
        'scene_id': f'scene_id_value_{row_index}',
        'sensor': 'synthetic_sensor',
        'acquired_at': day_timestamp,
        'preprocessing_level': 'reviewed_analysis_ready',
        'truth_mask_or_event_ref': f'event_id_value_{row_index}',
        'holdout_split': 'independent_holdout',
        'dem_ref': source_ref,
        'slope': str(25 + (row_index * 5)),
        'terrain_class': 'challenging',
        'runout_validation_ref': f'runout_validation_ref_value_{row_index}',
        'review_id': f'review_id_value_{row_index}',
        'case_id': f'case_id_value_{row_index}',
        'verdict': 'label_valid',
        'label_quality': 'valid',
        'model_error_type': 'not_applicable',
        'holdout_id': f'holdout_id_value_{row_index}',
        'source_refs': source_ref,
        'leakage_check': 'synthetic_independent_from_training_calibration_and_threshold_selection_for_fixture_only',
        'acceptance_floors': (
            'macro_f1_min=0.70;high_danger_recall_min=0.80;'
            'brier_score_max=0.18;ece_max=0.08;mean_day_accuracy_min=0.75;'
            'region_accuracy_min=0.70;leakage_check_required=true;'
            'independent_holdout_required=true'
        ),
    }
    return values.get(column, f'{column}_value_{row_index}')


def write_partner_synthetic_validation_package(
    output_root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    output_root.mkdir(parents=True, exist_ok=True)
    raw_sources_root = output_root / 'raw_sources'
    raw_sources_root.mkdir(parents=True, exist_ok=True)
    sources = []
    evidence_files = []
    for requirement in REQUIREMENTS:
        raw_source_path = raw_sources_root / f'{requirement.key}_synthetic_source.txt'
        raw_source_path.write_text(
            '\n'.join(
                [
                    'SYNTHETIC_VALIDATION_ONLY_NOT_PARTNER_EVIDENCE',
                    f'requirement_key={requirement.key}',
                    f'generated_at={generated_at.isoformat()}',
                    'purpose=exercise_himalayan_partner_validation_chain',
                    '',
                ]
            ),
            encoding='utf-8',
        )
        digest = _sha256_digest(raw_source_path)
        source_ref = f'file:raw_sources/{raw_source_path.name}#sha256={digest}'
        columns = partner_template_columns(requirement)
        row_count = _synthetic_row_count(requirement)
        csv_path = output_root / f'{requirement.key}.csv'
        with csv_path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns))
            writer.writeheader()
            for row_index in range(row_count):
                writer.writerow(
                    {
                        column: _synthetic_partner_value_for_column(
                            column,
                            row_index=row_index,
                            generated_at=generated_at,
                            source_ref=source_ref,
                        )
                        for column in columns
                    }
                )
        evidence_files.append(
            {
                'requirement_key': requirement.key,
                'filename': csv_path.name,
                'row_count': row_count,
                'source_ref': source_ref,
            }
        )
        sources.append(
            {
                'source_id': f'synthetic_{requirement.key}',
                'sha256': digest,
                'source_owner': 'Synthetic validation fixture generator',
                'dataset_name': f'Synthetic validation source for {requirement.key}',
                'license_scope': 'internal_research_validation',
                'date_range': _synthetic_date_range(generated_at),
                'review_status': 'reviewed',
                'reviewer_id': 'synthetic_validation_fixture_reviewer',
                'reviewed_at': (
                    _ensure_timezone(generated_at) - timedelta(days=7)
                ).isoformat(),
                'evidence_package_ref': f'sha256:{digest}',
            }
        )

    source_manifest = {
        'schema_version': PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'sources': sources,
    }
    source_manifest_path = output_root / 'partner_source_manifest.json'
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / 'SYNTHETIC_DO_NOT_SUBMIT.md').write_text(
        '# Synthetic Himalayan Partner Validation Package\n\n'
        'This package is generated only to smoke-test the validator. '
        'It is not partner evidence, not local Himalayan truth, not a model benchmark, '
        'and not a basis for production scoring or a Himalayan accuracy claim.\n',
        encoding='utf-8',
    )

    intake_preflight = validate_partner_intake_package_preflight(
        output_root,
        generated_at=generated_at,
    )
    source_manifest_validation = validate_partner_source_manifest(
        source_manifest,
        generated_at=generated_at,
    )
    evidence_validation = validate_partner_evidence_root(
        output_root,
        generated_at=generated_at,
        partner_source_manifest=source_manifest,
    )
    readiness_contract = build_contract(
        status_overrides=evidence_validation['status_overrides'],
        partner_evidence_validation=evidence_validation,
    )
    quality_score = build_partner_submission_quality_score(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    acceptance_checklist = build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=quality_score,
    )
    submission_summary = build_partner_submission_status_summary(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    structurally_passed = (
        intake_preflight['decision'] == 'partner_intake_package_files_present'
        and source_manifest_validation['decision'] == 'partner_source_manifest_available'
        and evidence_validation['decision'] == 'all_partner_evidence_available'
        and not readiness_contract['himalayan_accuracy_claim_allowed']
        and not readiness_contract['production_scoring_allowed']
    )
    return {
        'schema_version': PARTNER_SYNTHETIC_VALIDATION_PACKAGE_SCHEMA_VERSION,
        'validation_policy_version': VALIDATION_POLICY_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'generated_at': generated_at.isoformat(),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': (
            'synthetic_partner_validation_package_structurally_passed_claims_blocked'
            if structurally_passed
            else 'blocked_synthetic_partner_validation_package_failed'
        ),
        'synthetic_package_root': str(output_root),
        'synthetic_data_policy': {
            'is_real_himalayan_evidence': False,
            'may_be_submitted_as_partner_evidence': False,
            'may_unlock_scientist_review': False,
            'may_unlock_himalayan_accuracy_claim': False,
            'reason': 'Rows are deterministic synthetic fixtures for validator smoke testing only.',
        },
        'written_files': {
            'source_manifest': str(source_manifest_path),
            'do_not_submit_readme': str(output_root / 'SYNTHETIC_DO_NOT_SUBMIT.md'),
            'raw_source_count': len(sources),
            'evidence_file_count': len(evidence_files),
        },
        'evidence_files': evidence_files,
        'validation_decisions': {
            'intake_preflight': intake_preflight['decision'],
            'source_manifest_validation': source_manifest_validation['decision'],
            'evidence_validation': evidence_validation['decision'],
            'readiness_contract': readiness_contract['decision'],
            'quality_score': quality_score['decision'],
            'acceptance_checklist': acceptance_checklist['decision'],
            'submission_summary': submission_summary['decision'],
        },
        'validation_counts': {
            'available_requirements': len(evidence_validation['available_requirements']),
            'blocked_requirements': len(evidence_validation['blocked_requirements']),
            'missing_requirements': len(readiness_contract['missing_requirements']),
            'blocked_release_gates': len(readiness_contract['blocked_release_gates']),
            'quality_score': quality_score['score'],
            'quality_score_max': quality_score['max_score'],
        },
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The synthetic package proves validator plumbing only. Real reviewed Himalayan evidence and release-gate attestations are still required.',
        },
    }


def markdown_partner_synthetic_validation_package(payload: dict[str, Any]) -> str:
    lines = [
        '# Synthetic Himalayan Partner Validation Package',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This artifact reports a synthetic-only validator smoke test. It is not partner evidence, '
        'not a benchmark, and not a basis for a Himalayan accuracy or production claim.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Synthetic package root | `{payload['synthetic_package_root']}` |",
        f"| Evidence files | {payload['written_files']['evidence_file_count']} |",
        f"| Raw sources | {payload['written_files']['raw_source_count']} |",
        f"| Available requirements | {payload['validation_counts']['available_requirements']} |",
        f"| Blocked release gates | {payload['validation_counts']['blocked_release_gates']} |",
        '',
        '## Synthetic Data Policy',
        '',
    ]
    for key, value in payload['synthetic_data_policy'].items():
        lines.append(f'- `{key}`: `{str(value).lower() if isinstance(value, bool) else value}`')
    lines.extend(
        [
            '',
            '## Validation Decisions',
            '',
            '| Check | Decision |',
            '|---|---|',
        ]
    )
    for key, value in payload['validation_decisions'].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            '',
            '## Evidence Files',
            '',
            '| Requirement | File | Rows | Source ref |',
            '|---|---|---:|---|',
        ]
    )
    for item in payload['evidence_files']:
        lines.append(
            f"| `{item['requirement_key']}` | `{item['filename']}` | {item['row_count']} | `{item['source_ref']}` |"
        )
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            f"- Production scoring allowed: `{str(payload['claim_boundary']['production_scoring_allowed']).lower()}`",
            f"- Himalayan accuracy claim allowed: `{str(payload['claim_boundary']['himalayan_accuracy_claim_allowed']).lower()}`",
            f"- Reason: {payload['claim_boundary']['reason']}",
            '',
        ]
    )
    return '\n'.join(lines)


def markdown_contract(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Accuracy Readiness Contract',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        '',
        '## Missing Requirements',
        '',
    ]
    missing = payload.get('missing_requirements') or []
    if missing:
        for key in missing:
            lines.append(f'- `{key}`')
    else:
        lines.append('- None')
    lines.extend(
        [
            '',
            '## Requirements',
            '',
            '| Key | Status | Minimum reviewed rows | Minimum distinct coverage | Minimum span coverage | Unlocks | Required fields |',
            '|---|---|---:|---|---|---|---|',
        ]
    )
    for item in payload['requirements']:
        span_rules = [
            f"`{column}` >= {days:g} days"
            for column, days in item.get('minimum_temporal_span_days', {}).items()
        ]
        span_rules.extend(
            f"`{column}` >= {span:g}"
            for column, span in item.get('minimum_numeric_spans', {}).items()
        )
        lines.append(
            '| {key} | `{status}` | {minimum_rows} | {minimum_distinct} | {minimum_spans} | {unlocks} | {fields} |'.format(
                key=item['key'],
                status=item['current_status'],
                minimum_rows=item.get('minimum_rows_for_availability', 1),
                minimum_distinct=', '.join(
                    f"`{column}` >= {count}"
                    for column, count in item.get('minimum_distinct_counts', {}).items()
                ) or 'None',
                minimum_spans=', '.join(span_rules) or 'None',
                unlocks=item['unlocks_top10_feature'],
                fields=', '.join(item['required_fields']),
            )
        )
    lines.append('')
    return '\n'.join(lines)
