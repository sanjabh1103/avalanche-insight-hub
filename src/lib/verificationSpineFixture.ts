import type { ForecastGridRowRecord, GridCell } from './gridUtils';
import { normalizeGridCells } from './gridUtils';
import type { ForecastBulletin } from './forecastBulletins';
import { normalizeForecastBulletin } from './forecastBulletins';
import type { Region } from '@/components/RegionSelector';
import { REGIONS } from '@/components/RegionSelector';

export const VERIFICATION_SPINE_FIXTURE_KEY = 'verification-spine';

export function buildVerificationSpineFixture(): {
  region: Region;
  row: ForecastGridRowRecord;
  grids: Array<GridCell[] | null>;
  bulletin: ForecastBulletin | null;
} {
  const region = REGIONS.find((c) => c.name === 'Colorado Rockies') ?? REGIONS[0];
  const bbox: [number, number, number, number] = [39.4, -106.5, 39.6, -106.3];
  const gridSize = 20;

  const rawCells = [
    {
      row: 0, col: 0, lat: 39.40, lng: -106.50, lat_end: 39.41, lng_end: -106.49,
      risk_score: 4, probability: 0.72, problem_type: 'Wind Slab', problem_slug: 'wind_slab',
      hazard: 0.72, exposure: 0.35, vulnerability: 0.28, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2850, slope_angle_deg: 38 },
      anomaly_score: 0.89,
      verification_packet: {
        anomaly_state: 'anomaly', residual_zscore: 2.85, attribution_bucket: 'forcing_error',
        baseline_p25: 0.3, baseline_p50: 0.5, baseline_p75: 0.7, observed: 1.35,
        confidence: 0.87, packet_version: 'v2', contributing_sensors: ['s1', 'optical', 'weather'],
        source_freshness_hours: { s1: 6, optical: 12, weather: 3 },
      },
      fusion_evidence: {
        snow_depth_m: 1.35, snow_cover_fraction: 0.92, wet_snow_fraction: 0.15,
        loading_rate_24h: 0.28, uncertainty: 0.18, consensus_score: 0.82,
        contributing_sensors: ['s1', 'optical', 'weather'],
      },
      discrepancy_reasons: ['rapid_loading_anomaly', 'sar_optical_mismatch'],
    },
    {
      row: 0, col: 1, lat: 39.40, lng: -106.49, lat_end: 39.41, lng_end: -106.48,
      risk_score: 3, probability: 0.58, problem_type: 'Wind Slab', problem_slug: 'wind_slab',
      hazard: 0.58, exposure: 0.31, vulnerability: 0.24, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2450, slope_angle_deg: 37.6 },
      anomaly_score: 0.62,
      verification_packet: {
        anomaly_state: 'watch', residual_zscore: 1.65, attribution_bucket: 'sensing_gap',
        baseline_p25: 0.25, baseline_p50: 0.45, baseline_p75: 0.65, observed: 0.78,
        confidence: 0.71, packet_version: 'v2', contributing_sensors: ['weather', 'optical'],
        source_freshness_hours: { optical: 18, weather: 3 },
      },
      fusion_evidence: {
        snow_depth_m: 0.78, snow_cover_fraction: 0.85, wet_snow_fraction: 0.08,
        loading_rate_24h: 0.12, uncertainty: 0.22, consensus_score: 0.58,
        contributing_sensors: ['weather', 'optical'],
      },
      discrepancy_reasons: ['optical_stale', 'partial_sar_coverage'],
    },
    {
      row: 0, col: 2, lat: 39.40, lng: -106.48, lat_end: 39.41, lng_end: -106.47,
      risk_score: 2, probability: 0.42, problem_type: 'Wet Snow', problem_slug: 'wet_snow',
      hazard: 0.42, exposure: 0.25, vulnerability: 0.20, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2200, slope_angle_deg: 33 },
      anomaly_score: 0.15,
      verification_packet: {
        anomaly_state: 'normal', residual_zscore: 0.42, attribution_bucket: 'unattributed',
        baseline_p25: 0.2, baseline_p50: 0.38, baseline_p75: 0.55, observed: 0.42,
        confidence: 0.93, packet_version: 'v2', contributing_sensors: ['s1', 'optical', 'weather', 'gibs'],
        source_freshness_hours: { s1: 6, optical: 12, weather: 3, gibs: 8 },
      },
      fusion_evidence: {
        snow_depth_m: 0.42, snow_cover_fraction: 0.78, wet_snow_fraction: 0.22,
        loading_rate_24h: 0.05, uncertainty: 0.08, consensus_score: 0.91,
        contributing_sensors: ['s1', 'optical', 'weather', 'gibs'],
      },
      discrepancy_reasons: [],
    },
    {
      row: 1, col: 0, lat: 39.41, lng: -106.50, lat_end: 39.42, lng_end: -106.49,
      risk_score: 4, probability: 0.68, problem_type: 'Persistent Slab', problem_slug: 'persistent_slab',
      hazard: 0.68, exposure: 0.38, vulnerability: 0.30, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 3100, slope_angle_deg: 40 },
      anomaly_score: 0.81,
      verification_packet: {
        anomaly_state: 'anomaly', residual_zscore: 2.42, attribution_bucket: 'physics_model_bias',
        baseline_p25: 0.35, baseline_p50: 0.55, baseline_p75: 0.75, observed: 1.12,
        confidence: 0.79, packet_version: 'v2', contributing_sensors: ['s1', 'weather', 'pinn'],
        source_freshness_hours: { s1: 12, weather: 3, pinn: 24 },
      },
      fusion_evidence: {
        snow_depth_m: 1.12, snow_cover_fraction: 0.95, wet_snow_fraction: 0.05,
        loading_rate_24h: 0.22, uncertainty: 0.15, consensus_score: 0.75,
        contributing_sensors: ['s1', 'weather', 'pinn'],
      },
      discrepancy_reasons: ['physics_underpredicts_loading', 'sar_depth_exceeds_model'],
    },
    {
      row: 1, col: 1, lat: 39.41, lng: -106.49, lat_end: 39.42, lng_end: -106.48,
      risk_score: 3, probability: 0.55, problem_type: 'Wind Slab', problem_slug: 'wind_slab',
      hazard: 0.55, exposure: 0.29, vulnerability: 0.23, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2600, slope_angle_deg: 36 },
      anomaly_score: 0.45,
      verification_packet: {
        anomaly_state: 'watch', residual_zscore: 1.22, attribution_bucket: 'threshold_miscalibration',
        baseline_p25: 0.22, baseline_p50: 0.40, baseline_p75: 0.58, observed: 0.55,
        confidence: 0.68, packet_version: 'v2', contributing_sensors: ['optical', 'weather'],
        source_freshness_hours: { optical: 12, weather: 3 },
      },
      fusion_evidence: {
        snow_depth_m: 0.55, snow_cover_fraction: 0.80, wet_snow_fraction: 0.10,
        loading_rate_24h: 0.08, uncertainty: 0.16, consensus_score: 0.65,
        contributing_sensors: ['optical', 'weather'],
      },
      discrepancy_reasons: ['threshold_borderline'],
    },
    {
      row: 1, col: 2, lat: 39.41, lng: -106.48, lat_end: 39.42, lng_end: -106.47,
      risk_score: 1, probability: 0.22, problem_type: 'No Distinct Avalanche Problem', problem_slug: 'no_distinct_avalanche_problem',
      hazard: 0.12, exposure: 0.10, vulnerability: 0.08, shap_values: {},
      apt_eligible: false, apt_mask_reason: 'slope_outside_30_to_50_deg', public_eligible: false,
      public_mask_reasons: ['warm_low_elevation_no_snow_support'],
      terrain_inputs: { elevation_m: 1820, slope_angle_deg: 18.5 },
      anomaly_score: 0.05,
      verification_packet: {
        anomaly_state: 'normal', residual_zscore: 0.18, attribution_bucket: 'unattributed',
        baseline_p25: 0.08, baseline_p50: 0.15, baseline_p75: 0.25, observed: 0.18,
        confidence: 0.95, packet_version: 'v2', contributing_sensors: ['weather', 'gibs'],
        source_freshness_hours: { weather: 3, gibs: 8 },
      },
      fusion_evidence: {
        snow_depth_m: 0.18, snow_cover_fraction: 0.35, wet_snow_fraction: 0.45,
        loading_rate_24h: 0.0, uncertainty: 0.06, consensus_score: 0.88,
        contributing_sensors: ['weather', 'gibs'],
      },
      discrepancy_reasons: [],
    },
    {
      row: 2, col: 0, lat: 39.42, lng: -106.50, lat_end: 39.43, lng_end: -106.49,
      risk_score: 2, probability: 0.38, problem_type: 'Wet Snow', problem_slug: 'wet_snow',
      hazard: 0.38, exposure: 0.22, vulnerability: 0.18, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2400, slope_angle_deg: 34 },
      anomaly_score: 0.28,
      verification_packet: {
        anomaly_state: 'watch', residual_zscore: 1.08, attribution_bucket: 'terrain_transfer_error',
        baseline_p25: 0.18, baseline_p50: 0.32, baseline_p75: 0.48, observed: 0.48,
        confidence: 0.64, packet_version: 'v2', contributing_sensors: ['weather', 'optical'],
        source_freshness_hours: { weather: 3, optical: 12 },
      },
      fusion_evidence: {
        snow_depth_m: 0.48, snow_cover_fraction: 0.72, wet_snow_fraction: 0.18,
        loading_rate_24h: 0.04, uncertainty: 0.14, consensus_score: 0.62,
        contributing_sensors: ['weather', 'optical'],
      },
      discrepancy_reasons: ['terrain_exposure_mismatch'],
    },
    {
      row: 2, col: 1, lat: 39.42, lng: -106.49, lat_end: 39.43, lng_end: -106.48,
      risk_score: 3, probability: 0.52, problem_type: 'Wind Slab', problem_slug: 'wind_slab',
      hazard: 0.52, exposure: 0.27, vulnerability: 0.22, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2750, slope_angle_deg: 39 },
      anomaly_score: 0.0,
      // No verification_packet — simulates unverified cell
      fusion_evidence: {
        snow_depth_m: 0.65, snow_cover_fraction: 0.82, wet_snow_fraction: 0.12,
        loading_rate_24h: 0.10, uncertainty: 0.20, consensus_score: 0.45,
        contributing_sensors: ['weather'],
      },
    },
    {
      row: 2, col: 2, lat: 39.42, lng: -106.48, lat_end: 39.43, lng_end: -106.47,
      risk_score: 1, probability: 0.18, problem_type: 'No Distinct Avalanche Problem', problem_slug: 'no_distinct_avalanche_problem',
      hazard: 0.08, exposure: 0.08, vulnerability: 0.06, shap_values: {},
      apt_eligible: false, apt_mask_reason: 'slope_outside_30_to_50_deg', public_eligible: false,
      public_mask_reasons: ['warm_low_elevation_no_snow_support'],
      terrain_inputs: { elevation_m: 1900, slope_angle_deg: 22 },
      // No verification_packet, no fusion_evidence — fully unverified cell
    },
    {
      row: 3, col: 0, lat: 39.43, lng: -106.50, lat_end: 39.44, lng_end: -106.49,
      risk_score: 3, probability: 0.60, problem_type: 'Persistent Slab', problem_slug: 'persistent_slab',
      hazard: 0.60, exposure: 0.32, vulnerability: 0.25, shap_values: {},
      apt_eligible: true, public_eligible: true,
      terrain_inputs: { elevation_m: 2950, slope_angle_deg: 41 },
      anomaly_score: 0.72,
      verification_packet: {
        anomaly_state: 'anomaly', residual_zscore: 3.12, attribution_bucket: 'forcing_error',
        baseline_p25: 0.28, baseline_p50: 0.48, baseline_p75: 0.68, observed: 1.48,
        confidence: 0.91, packet_version: 'v2', contributing_sensors: ['s1', 'optical', 'weather', 'pinn'],
        source_freshness_hours: { s1: 6, optical: 6, weather: 3, pinn: 24 },
      },
      fusion_evidence: {
        snow_depth_m: 1.48, snow_cover_fraction: 0.96, wet_snow_fraction: 0.03,
        loading_rate_24h: 0.35, uncertainty: 0.12, consensus_score: 0.86,
        contributing_sensors: ['s1', 'optical', 'weather', 'pinn'],
      },
      discrepancy_reasons: ['rapid_loading_anomaly', 'pinn_residual_high', 'sar_optical_mismatch'],
    },
  ];

  const hour0 = normalizeGridCells(rawCells, {
    bbox,
    gridSize,
    warnContext: 'fixture:verification-spine:hour-0',
  });

  const bulletin = normalizeForecastBulletin({
    schema_version: 'forecast-bulletin/v1',
    standard: 'EAWS-style experimental',
    danger_level: 3,
    danger_label: 'Considerable',
    primary_problem: 'wind_slab',
    problems: ['wind_slab', 'persistent_slab', 'wet_snow'],
    critical_elevations: { min_m: 2200, max_m: 3000, band_step_m: 200 },
    critical_aspects: ['NW', 'N', 'NE', 'E'],
    coverage: 'ready',
    issue_window_policy: 'daypart_v1',
    primary_window: 'day_1_morning',
    primary_window_policy: 'first_available_current_or_future_daypart_v1',
    peak_window: {
      window: 'day_1_afternoon',
      danger_level: 4,
      danger_label: 'High',
      primary_problem: 'wet_snow',
      forecast_hours: [12, 13, 14],
      local_start: '2026-07-04T12:00:00-06:00',
      local_end: '2026-07-04T18:00:00-06:00',
      selected_forecast_hour: 12,
      selected_hour_local_start: '2026-07-04T12:00:00-06:00',
      selected_hour_local_end: '2026-07-04T13:00:00-06:00',
    },
    dayparts: [
      { window: 'day_1_night', day_index: 1, daypart: 'night', danger_level: 2, danger_label: 'Moderate', primary_problem: 'no_distinct_avalanche_problem', selected_forecast_hour: 0 },
      { window: 'day_1_morning', day_index: 1, daypart: 'morning', danger_level: 3, danger_label: 'Considerable', primary_problem: 'wind_slab', selected_forecast_hour: 6 },
      { window: 'day_1_afternoon', day_index: 1, daypart: 'afternoon', danger_level: 4, danger_label: 'High', primary_problem: 'wet_snow', selected_forecast_hour: 12 },
      { window: 'day_1_evening', day_index: 1, daypart: 'evening', danger_level: 3, danger_label: 'Considerable', primary_problem: 'wind_slab', selected_forecast_hour: 18 },
    ],
    double_map: false,
    aggregation_notes: ['fixture_verification_spine'],
    public_mask_profile: { profile: 'apt_then_snow_elevation_public_eligible_v1', stage_a: 'apt_30_50_v1', stage_b: 'snow_elevation_proxy_v1' },
    frequency_threshold_profile: 'local_grid_share_heuristic_v2',
    derived_from: {
      aggregation: 'highest_regional_level_by_cumulative_frequency',
      source_field: 'risk_score',
      base_metric: 'probability_risk_score',
      terrain_filter_profile: 'apt_30_50_v1',
      frequency_basis: 'cumulative_ge_threshold',
      frequency_class: 'frequent',
      ready_cell_count: 10,
      eligible_cell_count: 7,
      max_danger_cell_count: 3,
      selected_level_cell_count: 3,
      selected_level_cell_share: 0.30,
      problem_counts: { wind_slab: 4, persistent_slab: 2, wet_snow: 2, no_distinct: 2 },
    },
  });

  const row: ForecastGridRowRecord = {
    id: 'dev-fixture-verification-spine',
    region_name: region.name,
    region_key: 'dev_verification_spine',
    forecast_date: '2026-07-04',
    horizon_hours: 24,
    bbox,
    grid_size: gridSize,
    grid_geojson: hour0,
    hourly_grids: [hour0],
    runout_polygons: [],
    weather_summary: {
      snowfall_24h: '12 cm',
      wind_speed: '28 km/h',
      temperature: '-3 C',
      precipitation: '14 mm',
      snow_depth: '65 cm',
    },
    model_metadata: {
      fixture: true,
      artifact_source: VERIFICATION_SPINE_FIXTURE_KEY,
      verification_spine_enabled: true,
      artifact_mode: 'technical_artifact',
      technical_artifact_path: '/artifacts/verification-spine/run_derived_artifact.json',
      technical_artifact_id: 'rda_vs_fixture_abc123def456',
      technical_artifact_sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
      release_decision: { artifact_mode: 'technical_artifact', allowed: true },
      calibration_lineage: { state: 'calibrated' },
    },
    status: 'ready',
    created_at: '2026-07-04T00:00:00Z',
  };

  return {
    region: { ...region, bbox, center: [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], zoom: 11 },
    row,
    grids: [hour0],
    bulletin,
  };
}
