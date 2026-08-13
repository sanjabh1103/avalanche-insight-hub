import { GRID_SIZE, RISK_COLORS, PROBLEM_TYPES } from './constants';

export type SnowpackExecutionStatus =
  | 'planned'
  | 'configuration_validated'
  | 'toolchain_unavailable'
  | 'inputs_unavailable'
  | 'native_running'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'fallback_proxy';

export interface GridCell {
  row: number;
  col: number;
  lat: number;
  lng: number;
  latEnd: number;
  lngEnd: number;
  geometryValid?: boolean;
  riskScore: number;
  status?: string;
  stale?: boolean;
  disabled?: boolean;
  availabilityReason?: string | null;
  hazard: number;
  exposure: number;
  vulnerability: number;
  problemType: string;
  shapValues: Record<string, number>;
  probability?: number;
  rfProbability?: number;
  fusionMethod?: string;
  limitingFactor?: string;
  chebyshevIpaScore?: number;
  hazardVector?: Record<string, number>;
  confidenceLower?: number;
  confidenceUpper?: number;
  uncertaintySpan?: number;
  uncertaintyClass?: 'low' | 'medium' | 'high';
  forecastConfidence?: 'high' | 'medium' | 'low' | 'unknown';
  brierScore?: number;
  conformalLower?: number;
  conformalUpper?: number;
  inferenceBackend?: string;
  runoutSeed?: boolean;
  selectedFeatures?: string[];
  weatherInputs?: Record<string, number>;
  terrainInputs?: Record<string, number>;
  modelVersion?: string;
  calibrationProfile?: string;
  dynamicModelType?: string;
  dynamicModelVersion?: string;
  surrogateModelVersion?: string;
  uncertaintyMethod?: string;
  terrainFusedRiskScore?: number;
  aptEligible?: boolean;
  aptProfile?: string;
  aptMaskReason?: string | null;
  publicEligible?: boolean;
  publicMaskReasons?: string[];
  publicMaskProfile?: {
    profile?: string;
    stage_a?: string;
    stage_b?: string;
  };
  snowElevationEligible?: boolean;
  snowElevationProfile?: string;
  snowElevationMaskReason?: string | null;
  snowRelevanceScore?: number;
  snowRelevanceBasis?: string[];
  rainOnSnowProxy?: boolean;
  wetSnowEligible?: boolean;
  problemSlug?: string;
  problemConfidence?: number;
  problemEvidence?: string[];
  ensembleAvailable?: boolean;
  ensembleSource?: string | null;
  ensembleTempP10?: number;
  ensembleTempP50?: number;
  ensembleTempP90?: number;
  ensembleSnowfallP10?: number;
  ensembleSnowfallP50?: number;
  ensembleSnowfallP90?: number;
  ensemblePrecipP10?: number;
  ensemblePrecipP50?: number;
  ensemblePrecipP90?: number;
  problemClassifierProfile?: string;
  dryWetDomain?: 'dry' | 'wet' | 'mixed' | 'unknown';
  featureValues?: Record<string, number>;
  shapContext?: {
    limitingFactor?: string;
    fusionMethod?: string;
    hazardVector?: Record<string, number>;
    topFeatures: Array<{
      feature: string;
      shap_value: number;
      feature_value: number;
      rank: number;
    }>;
  };
  dominantDriverFeature?: string | null;
  explanationSummary?: string | null;
  explainabilityMode?: 'tree_shap' | 'heuristic_fallback' | 'unavailable';
  explainabilityReason?: string | null;
  coverageFlags?: {
    sar_coverage_state?: string;
    residual_shadow?: boolean;
    data_gaps?: string[];
  };
  snowpackProxy?: {
    estimated_shear_strength?: number;
    snow_settlement_index?: number;
    season_start?: string;
    method?: string;
    // Phase 12 provenance/uncertainty fields (backward-compatible additions)
    source_class?: string;       // 'direct' | 'derived' | 'proxy' | 'synthetic' | 'nwp' | 'reanalysis' | 'ensemble' | 'remote_sensing'
    source?: string;             // Source identifier
    uncertainty?: number;        // 0-1 uncertainty estimate
    quality_flags?: string[];    // Quality flag list
    run_id?: string;             // Run/provenance identifier
    is_official_warning?: boolean; // Must always be false/undefined until Partner approves
    execution_status?: SnowpackExecutionStatus;
    track?: string;
    approval_state?: string;
    forecast_cycle?: string;
    valid_from?: string;
    valid_to?: string;
    lead_time_h?: number;
    profile_available?: boolean;
    episode_state?: string;
    stale_reason?: string;
    official_warning_eligible?: boolean;
  };
  seismicAmplification?: {
    factor: number;
    window_phase: number;
    hours_since_event: number;
    magnitude: number;
    epicenter_distance_km: number;
    epicenter_lat: number;
    epicenter_lng: number;
  } | null;
  physicsNarrative?: {
    summary: string;
    shear_strength_kpa?: number | null;
    stability_index?: number | null;
    grain_type?: string | null;
    temperature_gradient_per_m?: number | null;
    liquid_water_content_pct?: number | null;
    snow_height_m?: number | null;
    method: string;
    confidence: string;
    seismic_summary?: string | null;
  } | null;
  // F14: Multi-Hazard Framework
  dominantHazard?: string;
  compositeRisk?: number;
  compositeRiskLevel?: number;
  multiHazard?: {
    dominant_hazard: string;
    composite_risk: number;
    composite_risk_level: number;
    any_trigger_met: boolean;
    hazard_assessments: Record<string, {
      risk_score: number;
      risk_level: number;
      confidence: number;
      trigger_met: boolean;
      contributing_factors: Record<string, number>;
    }>;
  };
  // Wave D: verification spine fields (all optional, N/A-safe)
  verificationPacket?: {
    baseline_p25?: number;
    baseline_p50?: number;
    baseline_p75?: number;
    observed?: number;
    residual_zscore?: number;
    anomaly_state?: 'normal' | 'watch' | 'anomaly' | 'unverified';
    source_freshness_hours?: Record<string, number>;
    attribution_bucket?: string;
    confidence?: number;
    contributing_sensors?: string[];
    packet_version?: string;
    evidence_refs?: string[];
    baseline_ids?: string[];
    lineage?: Record<string, unknown>;
  } | null;
  fusionEvidence?: {
    snow_depth_m?: number | null;
    snow_cover_fraction?: number | null;
    wet_snow_fraction?: number | null;
    loading_rate_24h?: number | null;
    uncertainty?: number | null;
    consensus_score?: number;
    contributing_sensors?: string[];
  } | null;
  anomalyScore?: number | null;
  discrepancyReasons?: string[];
  verificationSummary?: {
    total_cells?: number;
    anomaly_count?: number;
    watch_count?: number;
    normal_count?: number;
    unverified_count?: number;
    attribution_breakdown?: Record<string, number>;
  } | null;
}

// Story 16: strict PRD rule — grey voxels when the raw confidence interval
// span exceeds 0.30, OVERRIDING the EAWS palette regardless of risk score.
export const HIGH_UNCERTAINTY_SPAN_THRESHOLD = 0.3;

export function isHighUncertaintyCell(cell: Pick<GridCell, 'confidenceLower' | 'confidenceUpper' | 'uncertaintySpan' | 'uncertaintyClass'> | null | undefined): boolean {
  if (!cell) return false;
  const { confidenceLower, confidenceUpper, uncertaintySpan, uncertaintyClass } = cell;
  if (typeof confidenceLower === 'number' && typeof confidenceUpper === 'number'
    && Number.isFinite(confidenceLower) && Number.isFinite(confidenceUpper)) {
    return (confidenceUpper - confidenceLower) > HIGH_UNCERTAINTY_SPAN_THRESHOLD;
  }
  if (typeof uncertaintySpan === 'number' && Number.isFinite(uncertaintySpan)) {
    return uncertaintySpan > HIGH_UNCERTAINTY_SPAN_THRESHOLD;
  }
  // Fallback for legacy cells that only shipped a class label.
  return uncertaintyClass === 'high';
}

export interface ForecastGrid {
  cells: GridCell[];
  timestamp: string;
  bbox: [number, number, number, number];
}

export interface ForecastModelMetadata {
  model_version?: string;
  dynamic_model_type?: string;
  dynamic_model_version?: string;
  surrogate_model_version?: string;
  forecast_mode?: string;
  seismic_events_active?: boolean;
  seismic_amplification_summary?: {
    events_checked?: number;
    active_windows?: number;
  };
  uncertainty_method?: string;
  label_snapshot_id?: string;
  sar_mask_asset_refs?: string[];
  sar_event_geometries?: Array<Record<string, unknown>>;
  stale?: boolean;
  [key: string]: unknown;
}

export interface ForecastGridRowRecord {
  id: string;
  region_name: string;
  region_key?: string;
  forecast_date: string;
  horizon_hours: number;
  bbox: number[];
  grid_size?: number | null;
  grid_geojson: unknown;
  hourly_grids?: unknown;
  runout_polygons?: unknown;
  weather_summary?: unknown;
  model_metadata?: ForecastModelMetadata | unknown;
  status?: string;
  created_at?: string;
  published_at?: string | null;
  freshness_hours?: number | null;
  same_day_published?: boolean;
}

function normalizeUncertaintyClass(span: number | undefined): 'low' | 'medium' | 'high' | undefined {
  if (typeof span !== 'number' || !Number.isFinite(span)) return undefined;
  if (span > 0.3) return 'high';
  if (span > 0.18) return 'medium';
  return 'low';
}

export interface GridNormalizationOptions {
  bbox?: [number, number, number, number] | number[];
  gridSize?: number | null;
  warnContext?: string;
}

const warnedInvalidGeometryContexts = new Set<string>();

function asFiniteNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return undefined;
}

function normalizeBBox(value: unknown): [number, number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 4) return undefined;
  const numbers = value.map((item) => asFiniteNumber(item));
  if (numbers.some((item) => item === undefined)) return undefined;
  const [latMin, lngMin, latMax, lngMax] = numbers as number[];
  if (latMax <= latMin || lngMax <= lngMin) return undefined;
  return [latMin, lngMin, latMax, lngMax];
}

function inferAxisStep(values: number[]): number | undefined {
  const unique = Array.from(new Set(values.filter(Number.isFinite))).sort((left, right) => left - right);
  let smallestPositiveDelta: number | undefined;
  for (let index = 1; index < unique.length; index += 1) {
    const delta = unique[index] - unique[index - 1];
    if (delta <= 0) continue;
    if (smallestPositiveDelta === undefined || delta < smallestPositiveDelta) {
      smallestPositiveDelta = delta;
    }
  }
  return smallestPositiveDelta;
}

function warnInvalidGeometry(context: string, invalidCount: number): void {
  if (!import.meta.env.DEV || invalidCount <= 0 || warnedInvalidGeometryContexts.has(context)) return;
  console.warn(`[gridUtils] skipped ${invalidCount} cells with invalid rectangle bounds (${context})`);
  warnedInvalidGeometryContexts.add(context);
}

function normalizeCell(
  cell: Partial<GridCell> & Record<string, unknown>,
  geometry?: {
    latStep?: number;
    lngStep?: number;
  },
): GridCell {
  const row = Number(cell.row ?? 0);
  const col = Number(cell.col ?? 0);
  const lat = asFiniteNumber(cell.lat);
  const lng = asFiniteNumber(cell.lng);
  const latEnd = asFiniteNumber(cell.latEnd) ?? asFiniteNumber(cell.lat_end)
    ?? (lat !== undefined && geometry?.latStep !== undefined ? lat + geometry.latStep : undefined);
  const lngEnd = asFiniteNumber(cell.lngEnd) ?? asFiniteNumber(cell.lng_end)
    ?? (lng !== undefined && geometry?.lngStep !== undefined ? lng + geometry.lngStep : undefined);
  const geometryValid = lat !== undefined
    && lng !== undefined
    && latEnd !== undefined
    && lngEnd !== undefined
    && latEnd > lat
    && lngEnd > lng;
  const status = typeof cell.status === 'string' ? String(cell.status) : undefined;
  const availabilityReason = typeof cell.availabilityReason === 'string'
    ? cell.availabilityReason
    : (typeof cell.availability_reason === 'string' ? String(cell.availability_reason) : null);
  const stale = typeof cell.stale === 'boolean'
    ? cell.stale
    : status !== undefined && status !== 'ready';
  const disabled = typeof cell.disabled === 'boolean'
    ? cell.disabled
    : status === 'unavailable_terrain' || availabilityReason !== null;
  const defaultRiskScore = disabled ? 0 : 1;
  const riskScore = Number(cell.riskScore ?? cell.risk_score ?? defaultRiskScore);
  const probability = cell.probability !== undefined ? Number(cell.probability) : (cell.probability as number | undefined) ?? (cell['probability'] as number | undefined);
  const confidenceLower = cell.confidenceLower !== undefined
    ? Number(cell.confidenceLower)
    : (cell.confidence_lower !== undefined ? Number(cell.confidence_lower) : undefined);
  const confidenceUpper = cell.confidenceUpper !== undefined
    ? Number(cell.confidenceUpper)
    : (cell.confidence_upper !== undefined ? Number(cell.confidence_upper) : undefined);
  const uncertaintySpan = cell.uncertaintySpan !== undefined
    ? Number(cell.uncertaintySpan)
    : (cell.uncertainty_span !== undefined ? Number(cell.uncertainty_span) : undefined);
  const uncertaintyClass = (cell.uncertaintyClass as GridCell['uncertaintyClass'])
    || (cell.uncertainty_class as GridCell['uncertaintyClass'])
    || normalizeUncertaintyClass(uncertaintySpan);
  return {
    row,
    col,
    lat: lat ?? Number.NaN,
    lng: lng ?? Number.NaN,
    latEnd: latEnd ?? Number.NaN,
    lngEnd: lngEnd ?? Number.NaN,
    geometryValid,
    riskScore: Number.isFinite(riskScore) ? riskScore : defaultRiskScore,
    status,
    stale,
    disabled,
    availabilityReason,
    hazard: Number(cell.hazard ?? 0),
    exposure: Number(cell.exposure ?? 0),
    vulnerability: Number(cell.vulnerability ?? 0),
    problemType: String(cell.problemType ?? cell.problem_type ?? 'Unknown'),
    shapValues: (cell.shapValues as Record<string, number>) || (cell.shap_values as Record<string, number>) || {},
    probability: typeof probability === 'number' && Number.isFinite(probability) ? probability : undefined,
    rfProbability: cell.rfProbability !== undefined
      ? Number(cell.rfProbability)
      : (cell.rf_probability !== undefined ? Number(cell.rf_probability) : undefined),
    fusionMethod: typeof cell.fusionMethod === 'string' ? cell.fusionMethod : (typeof cell.fusion_method === 'string' ? String(cell.fusion_method) : undefined),
    limitingFactor: typeof cell.limitingFactor === 'string' ? cell.limitingFactor : (typeof cell.limiting_factor === 'string' ? String(cell.limiting_factor) : undefined),
    chebyshevIpaScore: cell.chebyshevIpaScore !== undefined
      ? Number(cell.chebyshevIpaScore)
      : (cell.chebyshev_ipa_score !== undefined ? Number(cell.chebyshev_ipa_score) : undefined),
    hazardVector: normalizeNumberRecord(cell.hazardVector ?? cell.hazard_vector),
    confidenceLower,
    confidenceUpper,
    uncertaintySpan,
    uncertaintyClass,
    forecastConfidence: cell.forecastConfidence as GridCell['forecastConfidence']
      ?? (cell.forecast_confidence as GridCell['forecastConfidence']),
    brierScore: cell.brierScore !== undefined
      ? Number(cell.brierScore)
      : (cell.brier_score !== undefined ? Number(cell.brier_score) : undefined),
    conformalLower: cell.conformalLower !== undefined
      ? Number(cell.conformalLower)
      : (cell.conformal_lower !== undefined ? Number(cell.conformal_lower) : undefined),
    conformalUpper: cell.conformalUpper !== undefined
      ? Number(cell.conformalUpper)
      : (cell.conformal_upper !== undefined ? Number(cell.conformal_upper) : undefined),
    inferenceBackend: typeof cell.inferenceBackend === 'string' ? cell.inferenceBackend : (typeof cell.inference_backend === 'string' ? String(cell.inference_backend) : undefined),
    runoutSeed: Boolean(cell.runoutSeed ?? cell.runout_seed),
    selectedFeatures: Array.isArray(cell.selectedFeatures)
      ? cell.selectedFeatures.map(String)
      : Array.isArray(cell.selected_features)
        ? (cell.selected_features as unknown[]).map(String)
        : undefined,
    weatherInputs: (cell.weatherInputs as Record<string, number>) || (cell.weather_inputs as Record<string, number>) || undefined,
    terrainInputs: (cell.terrainInputs as Record<string, number>) || (cell.terrain_inputs as Record<string, number>) || undefined,
    modelVersion: typeof cell.modelVersion === 'string' ? cell.modelVersion : (typeof cell.model_version === 'string' ? String(cell.model_version) : undefined),
    calibrationProfile: typeof cell.calibrationProfile === 'string' ? cell.calibrationProfile : (typeof cell.calibration_profile === 'string' ? String(cell.calibration_profile) : undefined),
    dynamicModelType: typeof cell.dynamicModelType === 'string' ? cell.dynamicModelType : (typeof cell.dynamic_model_type === 'string' ? String(cell.dynamic_model_type) : undefined),
    dynamicModelVersion: typeof cell.dynamicModelVersion === 'string' ? cell.dynamicModelVersion : (typeof cell.dynamic_model_version === 'string' ? String(cell.dynamic_model_version) : undefined),
    surrogateModelVersion: typeof cell.surrogateModelVersion === 'string' ? cell.surrogateModelVersion : (typeof cell.surrogate_model_version === 'string' ? String(cell.surrogate_model_version) : undefined),
    uncertaintyMethod: typeof cell.uncertaintyMethod === 'string' ? cell.uncertaintyMethod : (typeof cell.uncertainty_method === 'string' ? String(cell.uncertainty_method) : undefined),
    terrainFusedRiskScore: cell.terrainFusedRiskScore !== undefined
      ? Number(cell.terrainFusedRiskScore)
      : (cell.terrain_fused_risk_score !== undefined ? Number(cell.terrain_fused_risk_score) : undefined),
    aptEligible: typeof cell.aptEligible === 'boolean'
      ? cell.aptEligible
      : (typeof cell.apt_eligible === 'boolean' ? cell.apt_eligible : undefined),
    aptProfile: typeof cell.aptProfile === 'string'
      ? cell.aptProfile
      : (typeof cell.apt_profile === 'string' ? String(cell.apt_profile) : undefined),
    aptMaskReason: typeof cell.aptMaskReason === 'string'
      ? cell.aptMaskReason
      : (typeof cell.apt_mask_reason === 'string' ? String(cell.apt_mask_reason) : null),
    publicEligible: typeof cell.publicEligible === 'boolean'
      ? cell.publicEligible
      : (typeof cell.public_eligible === 'boolean' ? cell.public_eligible : undefined),
    publicMaskReasons: Array.isArray(cell.publicMaskReasons)
      ? cell.publicMaskReasons.map(String)
      : Array.isArray(cell.public_mask_reasons)
        ? (cell.public_mask_reasons as unknown[]).map(String)
        : undefined,
    publicMaskProfile: normalizePublicMaskProfile(cell.publicMaskProfile ?? cell.public_mask_profile),
    snowElevationEligible: typeof cell.snowElevationEligible === 'boolean'
      ? cell.snowElevationEligible
      : (typeof cell.snow_elevation_eligible === 'boolean' ? cell.snow_elevation_eligible : undefined),
    snowElevationProfile: typeof cell.snowElevationProfile === 'string'
      ? cell.snowElevationProfile
      : (typeof cell.snow_elevation_profile === 'string' ? String(cell.snow_elevation_profile) : undefined),
    snowElevationMaskReason: typeof cell.snowElevationMaskReason === 'string'
      ? cell.snowElevationMaskReason
      : (typeof cell.snow_elevation_mask_reason === 'string' ? String(cell.snow_elevation_mask_reason) : null),
    snowRelevanceScore: cell.snowRelevanceScore !== undefined
      ? Number(cell.snowRelevanceScore)
      : (cell.snow_relevance_score !== undefined ? Number(cell.snow_relevance_score) : undefined),
    snowRelevanceBasis: Array.isArray(cell.snowRelevanceBasis)
      ? cell.snowRelevanceBasis.map(String)
      : Array.isArray(cell.snow_relevance_basis)
        ? (cell.snow_relevance_basis as unknown[]).map(String)
        : undefined,
    rainOnSnowProxy: typeof cell.rainOnSnowProxy === 'boolean'
      ? cell.rainOnSnowProxy
      : (typeof cell.rain_on_snow_proxy === 'boolean' ? cell.rain_on_snow_proxy : undefined),
    wetSnowEligible: typeof cell.wetSnowEligible === 'boolean'
      ? cell.wetSnowEligible
      : (typeof cell.wet_snow_eligible === 'boolean' ? cell.wet_snow_eligible : undefined),
    problemSlug: typeof cell.problemSlug === 'string'
      ? cell.problemSlug
      : (typeof cell.problem_slug === 'string' ? String(cell.problem_slug) : undefined),
    problemConfidence: cell.problemConfidence !== undefined
      ? Number(cell.problemConfidence)
      : (cell.problem_confidence !== undefined ? Number(cell.problem_confidence) : undefined),
    problemEvidence: Array.isArray(cell.problemEvidence)
      ? cell.problemEvidence.map(String)
      : Array.isArray(cell.problem_evidence)
        ? (cell.problem_evidence as unknown[]).map(String)
        : undefined,
    problemClassifierProfile: typeof cell.problemClassifierProfile === 'string'
      ? cell.problemClassifierProfile
      : (typeof cell.problem_classifier_profile === 'string' ? String(cell.problem_classifier_profile) : undefined),
    dryWetDomain: typeof cell.dryWetDomain === 'string'
      ? cell.dryWetDomain as GridCell['dryWetDomain']
      : (typeof cell.dry_wet_domain === 'string' ? String(cell.dry_wet_domain) as GridCell['dryWetDomain'] : undefined),
    featureValues: (cell.featureValues as Record<string, number>) || (cell.feature_values as Record<string, number>) || undefined,
    shapContext: normalizeShapContext(cell.shapContext ?? cell.shap_context),
    explanationSummary: typeof cell.explanationSummary === 'string'
      ? cell.explanationSummary
      : (typeof cell.explanation_summary === 'string' ? String(cell.explanation_summary) : null),
    explainabilityMode: typeof cell.explainabilityMode === 'string'
      ? cell.explainabilityMode as GridCell['explainabilityMode']
      : (typeof cell.explainability_mode === 'string'
        ? String(cell.explainability_mode) as GridCell['explainabilityMode']
        : undefined),
    explainabilityReason: typeof cell.explainabilityReason === 'string'
      ? cell.explainabilityReason
      : (typeof cell.explainability_reason === 'string' ? String(cell.explainability_reason) : null),
    coverageFlags: normalizeCoverageFlags(cell.coverageFlags ?? cell.coverage_flags),
    snowpackProxy: normalizeSnowpackProxy(cell.snowpackProxy ?? cell.snowpack_proxy),
    seismicAmplification: normalizeSeismicAmplification(cell.seismicAmplification ?? cell.seismic_amplification),
    physicsNarrative: normalizePhysicsNarrative(cell.physicsNarrative ?? cell.physics_narrative),
    dominantHazard: typeof cell.dominantHazard === 'string'
      ? cell.dominantHazard
      : (typeof cell.dominant_hazard === 'string' ? String(cell.dominant_hazard) : undefined),
    compositeRisk: typeof cell.compositeRisk === 'number'
      ? cell.compositeRisk
      : (typeof cell.composite_risk === 'number' ? Number(cell.composite_risk) : undefined),
    compositeRiskLevel: typeof cell.compositeRiskLevel === 'number'
      ? cell.compositeRiskLevel
      : (typeof cell.composite_risk_level === 'number' ? Number(cell.composite_risk_level) : undefined),
    multiHazard: normalizeMultiHazard(cell.multiHazard ?? cell.multi_hazard),
    verificationPacket: normalizeVerificationPacket(cell.verificationPacket ?? cell.verification_packet),
    fusionEvidence: normalizeFusionEvidence(cell.fusionEvidence ?? cell.fusion_evidence),
    anomalyScore: cell.anomalyScore !== undefined
      ? (cell.anomalyScore !== null ? Number(cell.anomalyScore) : null)
      : (cell.anomaly_score !== undefined
        ? (cell.anomaly_score !== null ? Number(cell.anomaly_score) : null)
        : undefined),
    discrepancyReasons: Array.isArray(cell.discrepancyReasons)
      ? cell.discrepancyReasons.map(String)
      : Array.isArray(cell.discrepancy_reasons)
        ? (cell.discrepancy_reasons as unknown[]).map(String)
        : undefined,
    verificationSummary: normalizeVerificationSummary(cell.verificationSummary ?? cell.verification_summary),
  };
}

function normalizePhysicsNarrative(value: unknown): GridCell['physicsNarrative'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (typeof row.summary !== 'string') return null;
  return {
    summary: row.summary,
    shear_strength_kpa: typeof row.shear_strength_kpa === 'number' ? row.shear_strength_kpa : null,
    stability_index: typeof row.stability_index === 'number' ? row.stability_index : null,
    grain_type: typeof row.grain_type === 'string' ? row.grain_type : null,
    temperature_gradient_per_m: typeof row.temperature_gradient_per_m === 'number' ? row.temperature_gradient_per_m : null,
    liquid_water_content_pct: typeof row.liquid_water_content_pct === 'number' ? row.liquid_water_content_pct : null,
    snow_height_m: typeof row.snow_height_m === 'number' ? row.snow_height_m : null,
    method: typeof row.method === 'string' ? row.method : 'unavailable',
    confidence: typeof row.confidence === 'string' ? row.confidence : 'low',
    seismic_summary: typeof row.seismic_summary === 'string' ? row.seismic_summary : null,
  };
}

function normalizeSeismicAmplification(value: unknown): GridCell['seismicAmplification'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const factor = Number(row.factor);
  const windowPhase = Number(row.window_phase);
  const hoursSinceEvent = Number(row.hours_since_event);
  const magnitude = Number(row.magnitude);
  const epicenterDistanceKm = Number(row.epicenter_distance_km);
  if (!Number.isFinite(factor) || !Number.isFinite(windowPhase)) return null;
  const epicenterLat = Number(row.epicenter_lat);
  const epicenterLng = Number(row.epicenter_lng);
  return {
    factor,
    window_phase: windowPhase,
    hours_since_event: Number.isFinite(hoursSinceEvent) ? hoursSinceEvent : 0,
    magnitude: Number.isFinite(magnitude) ? magnitude : 0,
    epicenter_distance_km: Number.isFinite(epicenterDistanceKm) ? epicenterDistanceKm : 0,
    epicenter_lat: Number.isFinite(epicenterLat) ? epicenterLat : 0,
    epicenter_lng: Number.isFinite(epicenterLng) ? epicenterLng : 0,
  };
}

function normalizeMultiHazard(value: unknown): GridCell['multiHazard'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  const dominant = typeof row.dominant_hazard === 'string' ? row.dominant_hazard : '';
  const compositeRisk = Number(row.composite_risk);
  const compositeRiskLevel = Number(row.composite_risk_level);
  const anyTriggerMet = Boolean(row.any_trigger_met);
  const rawAssessments = row.hazard_assessments;
  const hazard_assessments: NonNullable<GridCell['multiHazard']>['hazard_assessments'] = {};
  if (rawAssessments && typeof rawAssessments === 'object' && !Array.isArray(rawAssessments)) {
    for (const [hazardType, assessment] of Object.entries(rawAssessments as Record<string, unknown>)) {
      if (!assessment || typeof assessment !== 'object') continue;
      const a = assessment as Record<string, unknown>;
      hazard_assessments[hazardType] = {
        risk_score: Number(a.risk_score) || 0,
        risk_level: Number(a.risk_level) || 0,
        confidence: Number(a.confidence) || 0,
        trigger_met: Boolean(a.trigger_met),
        contributing_factors: (a.contributing_factors as Record<string, number>) || {},
      };
    }
  }
  if (!dominant) return undefined;
  return {
    dominant_hazard: dominant,
    composite_risk: Number.isFinite(compositeRisk) ? compositeRisk : 0,
    composite_risk_level: Number.isFinite(compositeRiskLevel) ? compositeRiskLevel : 0,
    any_trigger_met: anyTriggerMet,
    hazard_assessments,
  };
}

function normalizeVerificationPacket(value: unknown): GridCell['verificationPacket'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  const anomalyState = typeof row.anomaly_state === 'string' ? row.anomaly_state : undefined;
  const validStates = ['normal', 'watch', 'anomaly', 'unverified'];
  return {
    baseline_p25: typeof row.baseline_p25 === 'number' ? row.baseline_p25 : undefined,
    baseline_p50: typeof row.baseline_p50 === 'number' ? row.baseline_p50 : undefined,
    baseline_p75: typeof row.baseline_p75 === 'number' ? row.baseline_p75 : undefined,
    observed: typeof row.observed === 'number' ? row.observed : undefined,
    residual_zscore: typeof row.residual_zscore === 'number' ? row.residual_zscore : undefined,
    anomaly_state: anomalyState && validStates.includes(anomalyState)
      ? anomalyState as GridCell['verificationPacket'] extends { anomaly_state?: infer S } ? S : never
      : undefined,
    source_freshness_hours: normalizeNumberRecord(row.source_freshness_hours),
    attribution_bucket: typeof row.attribution_bucket === 'string' ? row.attribution_bucket : undefined,
    confidence: typeof row.confidence === 'number' ? row.confidence : undefined,
    contributing_sensors: Array.isArray(row.contributing_sensors)
      ? row.contributing_sensors.map(String)
      : undefined,
    packet_version: typeof row.packet_version === 'string' ? row.packet_version : undefined,
    evidence_refs: Array.isArray(row.evidence_refs) ? row.evidence_refs.map(String) : undefined,
    baseline_ids: Array.isArray(row.baseline_ids) ? row.baseline_ids.map(String) : undefined,
    lineage: (row.lineage && typeof row.lineage === 'object' && !Array.isArray(row.lineage))
      ? row.lineage as Record<string, unknown> : undefined,
  };
}

function normalizeFusionEvidence(value: unknown): GridCell['fusionEvidence'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  return {
    snow_depth_m: row.snow_depth_m !== undefined && row.snow_depth_m !== null
      ? Number(row.snow_depth_m) : null,
    snow_cover_fraction: row.snow_cover_fraction !== undefined && row.snow_cover_fraction !== null
      ? Number(row.snow_cover_fraction) : null,
    wet_snow_fraction: row.wet_snow_fraction !== undefined && row.wet_snow_fraction !== null
      ? Number(row.wet_snow_fraction) : null,
    loading_rate_24h: row.loading_rate_24h !== undefined && row.loading_rate_24h !== null
      ? Number(row.loading_rate_24h) : null,
    uncertainty: row.uncertainty !== undefined && row.uncertainty !== null
      ? Number(row.uncertainty) : null,
    consensus_score: typeof row.consensus_score === 'number' ? row.consensus_score : 0,
    contributing_sensors: Array.isArray(row.contributing_sensors)
      ? row.contributing_sensors.map(String)
      : undefined,
  };
}

function normalizeVerificationSummary(value: unknown): GridCell['verificationSummary'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  return {
    total_cells: typeof row.total_cells === 'number' ? row.total_cells : undefined,
    anomaly_count: typeof row.anomaly_count === 'number' ? row.anomaly_count : undefined,
    watch_count: typeof row.watch_count === 'number' ? row.watch_count : undefined,
    normal_count: typeof row.normal_count === 'number' ? row.normal_count : undefined,
    unverified_count: typeof row.unverified_count === 'number' ? row.unverified_count : undefined,
    attribution_breakdown: normalizeNumberRecord(row.attribution_breakdown),
  };
}

export function hasRenderableCellGeometry(
  cell: Pick<GridCell, 'lat' | 'lng' | 'latEnd' | 'lngEnd' | 'geometryValid'> | null | undefined,
): boolean {
  if (!cell) return false;
  if (cell.geometryValid === false) return false;
  return Number.isFinite(cell.lat)
    && Number.isFinite(cell.lng)
    && Number.isFinite(cell.latEnd)
    && Number.isFinite(cell.lngEnd)
    && cell.latEnd > cell.lat
    && cell.lngEnd > cell.lng;
}

export function normalizeGridCells(cells: unknown[], options: GridNormalizationOptions = {}): GridCell[] {
  const rawCells = cells
    .filter((cell): cell is Partial<GridCell> & Record<string, unknown> => Boolean(cell) && typeof cell === 'object');
  const bbox = normalizeBBox(options.bbox);
  const gridSize = asFiniteNumber(options.gridSize);
  const latStepFromBbox = bbox && gridSize && gridSize > 0 ? (bbox[2] - bbox[0]) / gridSize : undefined;
  const lngStepFromBbox = bbox && gridSize && gridSize > 0 ? (bbox[3] - bbox[1]) / gridSize : undefined;
  const latStep = latStepFromBbox ?? inferAxisStep(
    rawCells
      .map((cell) => asFiniteNumber(cell.lat))
      .filter((value): value is number => value !== undefined),
  );
  const lngStep = lngStepFromBbox ?? inferAxisStep(
    rawCells
      .map((cell) => asFiniteNumber(cell.lng))
      .filter((value): value is number => value !== undefined),
  );
  const normalizedCells = rawCells.map((cell) => normalizeCell(cell, { latStep, lngStep }));
  const invalidCount = normalizedCells.filter((cell) => !hasRenderableCellGeometry(cell)).length;
  warnInvalidGeometry(options.warnContext ?? 'grid-cells', invalidCount);
  return normalizedCells;
}

function normalizeShapContext(value: unknown): GridCell['shapContext'] {
  if (!value || typeof value !== 'object') return undefined;
  const rowValue = value as Record<string, unknown>;
  const topFeatures = (value as Record<string, unknown>).topFeatures ?? (value as Record<string, unknown>).top_features;
  if (!Array.isArray(topFeatures)) return undefined;
  return {
    limitingFactor: typeof rowValue.limitingFactor === 'string'
      ? rowValue.limitingFactor
      : (typeof rowValue.limiting_factor === 'string' ? String(rowValue.limiting_factor) : undefined),
    fusionMethod: typeof rowValue.fusionMethod === 'string'
      ? rowValue.fusionMethod
      : (typeof rowValue.fusion_method === 'string' ? String(rowValue.fusion_method) : undefined),
    hazardVector: normalizeNumberRecord(rowValue.hazardVector ?? rowValue.hazard_vector),
    topFeatures: topFeatures
      .filter((item) => item && typeof item === 'object')
      .map((item) => {
        const row = item as Record<string, unknown>;
        return {
          feature: String(row.feature ?? ''),
          shap_value: Number(row.shap_value ?? 0),
          feature_value: Number(row.feature_value ?? 0),
          rank: Number(row.rank ?? 0),
        };
      }),
  };
}

function normalizeNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const entries = Object.entries(value as Record<string, unknown>)
    .map(([key, raw]) => [key, Number(raw)] as const)
    .filter(([, numeric]) => Number.isFinite(numeric));
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function normalizeCoverageFlags(value: unknown): GridCell['coverageFlags'] {
  if (!value || typeof value !== 'object') return undefined;
  const row = value as Record<string, unknown>;
  const rawState = typeof row.sar_coverage_state === 'string' ? row.sar_coverage_state : undefined;
  const normalizedState =
    rawState === 'full_coverage' ? 'good'
      : rawState === 'low_coverage' ? 'low'
        : rawState;
  return {
    sar_coverage_state: normalizedState,
    residual_shadow: typeof row.residual_shadow === 'boolean' ? row.residual_shadow : undefined,
    data_gaps: Array.isArray(row.data_gaps) ? row.data_gaps.map(String) : undefined,
  };
}

function normalizePublicMaskProfile(value: unknown): GridCell['publicMaskProfile'] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const row = value as Record<string, unknown>;
  const profile = typeof row.profile === 'string' ? row.profile : undefined;
  const stageA = typeof row.stage_a === 'string'
    ? row.stage_a
    : (typeof row.stageA === 'string' ? row.stageA : undefined);
  const stageB = typeof row.stage_b === 'string'
    ? row.stage_b
    : (typeof row.stageB === 'string' ? row.stageB : undefined);
  if (!profile && !stageA && !stageB) return undefined;
  return {
    profile,
    stage_a: stageA,
    stage_b: stageB,
  };
}

function normalizeSnowpackProxy(value: unknown): GridCell['snowpackProxy'] {
  if (!value || typeof value !== 'object') return undefined;
  const v = value as Record<string, unknown>;
  const shear = v.estimated_shear_strength ?? v.estimatedShearStrength;
  const settle = v.snow_settlement_index ?? v.snowSettlementIndex;
  const seasonStart = v.season_start ?? v.seasonStart;
  const method = v.method;
  const payload: GridCell['snowpackProxy'] = {};
  if (typeof shear === 'number' && Number.isFinite(shear)) payload.estimated_shear_strength = shear;
  if (typeof settle === 'number' && Number.isFinite(settle)) payload.snow_settlement_index = settle;
  if (typeof seasonStart === 'string' && seasonStart) payload.season_start = seasonStart;
  if (typeof method === 'string' && method) payload.method = method;
  // Phase 12: provenance/uncertainty fields (backward-compatible)
  const sourceClass = v.source_class ?? v.sourceClass;
  if (typeof sourceClass === 'string' && sourceClass) payload.source_class = sourceClass;
  if (typeof v.source === 'string' && v.source) payload.source = v.source;
  if (typeof v.uncertainty === 'number' && Number.isFinite(v.uncertainty)) payload.uncertainty = v.uncertainty;
  const qualityFlags = v.quality_flags ?? v.qualityFlags;
  if (Array.isArray(qualityFlags)) payload.quality_flags = qualityFlags.filter((f): f is string => typeof f === 'string');
  const runId = v.run_id ?? v.runId;
  if (typeof runId === 'string' && runId) payload.run_id = runId;
  const executionStatus = v.execution_status ?? v.executionStatus;
  if (typeof executionStatus === 'string' && executionStatus) {
    const allowedStatuses: SnowpackExecutionStatus[] = [
      'planned', 'configuration_validated', 'toolchain_unavailable',
      'inputs_unavailable', 'native_running', 'running', 'completed',
      'partial', 'failed', 'fallback_proxy',
    ];
    if (allowedStatuses.includes(executionStatus as SnowpackExecutionStatus)) {
      payload.execution_status = executionStatus as SnowpackExecutionStatus;
    }
  }
  for (const [key, aliases] of [
    ['track', ['track']],
    ['approval_state', ['approval_state', 'approvalState']],
    ['forecast_cycle', ['forecast_cycle', 'forecastCycle']],
    ['valid_from', ['valid_from', 'validFrom']],
    ['valid_to', ['valid_to', 'validTo']],
    ['episode_state', ['episode_state', 'episodeState']],
    ['stale_reason', ['stale_reason', 'staleReason']],
  ] as const) {
    const raw = aliases.map((alias) => v[alias]).find((item) => typeof item === 'string' && item);
    if (typeof raw === 'string') payload[key] = raw;
  }
  const leadTime = v.lead_time_h ?? v.leadTimeH;
  if (typeof leadTime === 'number' && Number.isFinite(leadTime) && leadTime >= 0) {
    payload.lead_time_h = leadTime;
  }
  const profileAvailable = v.profile_available ?? v.profileAvailable;
  if (typeof profileAvailable === 'boolean') payload.profile_available = profileAvailable;
  const officialWarningEligible = v.official_warning_eligible ?? v.officialWarningEligible;
  if (officialWarningEligible === true) {
    payload.official_warning_eligible = false;
  } else if (officialWarningEligible === false) {
    payload.official_warning_eligible = false;
  }
  // is_official_warning must never be true until Partner approves
  const isOfficialWarning = v.is_official_warning ?? v.isOfficialWarning;
  if (isOfficialWarning === true) {
    payload.is_official_warning = false; // Force false — Partner approval required
  }

  if (Object.keys(payload).length === 0) {
    const metrics = v.snowpackMetrics ?? v.snowpack_metrics;
    if (metrics && typeof metrics === 'object' && !Array.isArray(metrics)) {
      const record = metrics as Record<string, unknown>;
      const metricShear = record.estimated_shear_strength ?? record.shear_strength ?? record.ram_hardness;
      const metricSettle = record.snow_settlement_index ?? record.settlement_rate;
      const metricMethod = record.method ?? record.source;
      if (typeof metricShear === 'number' && Number.isFinite(metricShear)) {
        payload.estimated_shear_strength = metricShear <= 1.5 ? metricShear * 10 : metricShear;
      }
      if (typeof metricSettle === 'number' && Number.isFinite(metricSettle)) {
        payload.snow_settlement_index = metricSettle;
      }
      if (typeof metricMethod === 'string' && metricMethod) {
        payload.method = metricMethod;
      }
    }
  }

  return Object.keys(payload).length > 0 ? payload : undefined;
}

export function forecastGridRowToCells(row: ForecastGridRowRecord): GridCell[] {
  if (!Array.isArray(row.grid_geojson)) return [];
  const metadata = row.model_metadata && typeof row.model_metadata === 'object' && !Array.isArray(row.model_metadata)
    ? row.model_metadata as Record<string, unknown>
    : {};
  return normalizeGridCells(row.grid_geojson.map((cell) => ({
    ...(cell as Partial<GridCell> & Record<string, unknown>),
    dynamic_model_type: (cell as Record<string, unknown>).dynamic_model_type ?? metadata.dynamic_model_type,
    dynamic_model_version: (cell as Record<string, unknown>).dynamic_model_version ?? metadata.dynamic_model_version,
    surrogate_model_version: (cell as Record<string, unknown>).surrogate_model_version ?? metadata.surrogate_model_version,
  })), {
    bbox: row.bbox,
    gridSize: row.grid_size,
    warnContext: `forecast-grid:${row.id}:grid_geojson`,
  });
}

export function forecastGridRowToHourlyGrids(row: ForecastGridRowRecord): GridCell[][] {
  const metadata = row.model_metadata && typeof row.model_metadata === 'object' && !Array.isArray(row.model_metadata)
    ? row.model_metadata as Record<string, unknown>
    : {};
  if (Array.isArray(row.hourly_grids) && row.hourly_grids.length > 0) {
    return row.hourly_grids
      .filter((grid): grid is unknown[] => Array.isArray(grid))
      .map((grid, index) => normalizeGridCells(grid.map((cell) => ({
        ...(cell as Partial<GridCell> & Record<string, unknown>),
        dynamic_model_type: (cell as Record<string, unknown>).dynamic_model_type ?? metadata.dynamic_model_type,
        dynamic_model_version: (cell as Record<string, unknown>).dynamic_model_version ?? metadata.dynamic_model_version,
        surrogate_model_version: (cell as Record<string, unknown>).surrogate_model_version ?? metadata.surrogate_model_version,
      })), {
        bbox: row.bbox,
        gridSize: row.grid_size,
        warnContext: `forecast-grid:${row.id}:hour-${index}`,
      }));
  }
  const cells = forecastGridRowToCells(row);
  return cells.length > 0 ? [cells] : [];
}

export function forecastGridRowUsesLegacyStaticPlayback(row: ForecastGridRowRecord): boolean {
  if (Array.isArray(row.hourly_grids) && row.hourly_grids.length > 0) {
    return false;
  }
  return Array.isArray(row.grid_geojson) && row.grid_geojson.length > 0;
}

export function forecastGridRowToRunoutPolygons(row: ForecastGridRowRecord): Array<Record<string, unknown>> {
  return Array.isArray(row.runout_polygons) ? row.runout_polygons as Array<Record<string, unknown>> : [];
}

export function forecastGridRowToSarGeometries(row: ForecastGridRowRecord): Array<Record<string, unknown>> {
  const metadata = row.model_metadata;
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return [];
  const geometries = (metadata as ForecastModelMetadata).sar_event_geometries;
  return Array.isArray(geometries) ? geometries : [];
}

// Simulated storm physics for grid generation
export function generateForecastGrid(
  bbox: [number, number, number, number],
  timeOffset: number = 0,
): ForecastGrid {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const latStep = (latMax - latMin) / GRID_SIZE;
  const lngStep = (lngMax - lngMin) / GRID_SIZE;
  const cells: GridCell[] = [];

  // Storm center drifts with time
  const stormCenterLat = latMin + (latMax - latMin) * (0.4 + 0.15 * Math.sin(timeOffset * 0.3));
  const stormCenterLng = lngMin + (lngMax - lngMin) * (0.5 + 0.2 * Math.cos(timeOffset * 0.2));
  const stormRadius = 0.8 + 0.3 * Math.sin(timeOffset * 0.15);

  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      const lat = latMin + r * latStep;
      const lng = lngMin + c * lngStep;
      const centerLat = lat + latStep / 2;
      const centerLng = lng + lngStep / 2;

      // Distance from storm center
      const dist = Math.sqrt(
        Math.pow(centerLat - stormCenterLat, 2) + Math.pow(centerLng - stormCenterLng, 2),
      );

      // Elevation proxy (higher = more north, higher columns)
      const elevFactor = 0.3 + 0.7 * (r / GRID_SIZE);
      // Aspect factor
      const aspectFactor = 0.5 + 0.5 * Math.sin((c / GRID_SIZE) * Math.PI * 2);

      // Base risk from storm proximity
      const stormInfluence = Math.max(0, 1 - dist / stormRadius);
      const baseRisk = stormInfluence * 0.6 + elevFactor * 0.25 + aspectFactor * 0.15;

      // Add temporal variation
      const timeVariation = 0.1 * Math.sin(timeOffset * 0.5 + r * 0.3 + c * 0.2);
      const rawRisk = Math.max(0, Math.min(1, baseRisk + timeVariation));

      const riskScore = Math.max(1, Math.min(5, Math.round(rawRisk * 5)));
      const hazard = 0.2 + rawRisk * 0.7;
      const exposure = 0.3 + elevFactor * 0.5;
      const vulnerability = 0.1 + aspectFactor * 0.6;
      const elevationMeters = 1200 + elevFactor * 2800;
      const slopeAngleDeg = 10 + rawRisk * 35;
      const aspectDeg = (c / GRID_SIZE) * 360;
      const aptEligible = slopeAngleDeg >= 30 && slopeAngleDeg <= 50;

      const problemIdx = Math.floor(rawRisk * (PROBLEM_TYPES.length - 1));

      cells.push({
        row: r,
        col: c,
        lat,
        lng,
        latEnd: lat + latStep,
        lngEnd: lng + lngStep,
        riskScore: aptEligible ? riskScore : 0,
        hazard,
        exposure,
        vulnerability,
        problemType: PROBLEM_TYPES[problemIdx],
        terrainFusedRiskScore: riskScore,
        aptEligible,
        aptProfile: 'apt_30_50_v1',
        aptMaskReason: aptEligible ? null : 'slope_outside_30_to_50_deg',
        shapValues: {
          snowfall_24h: 0.15 + stormInfluence * 0.3,
          wind_speed: 0.1 + aspectFactor * 0.25,
          temperature: 0.05 + timeVariation * 0.2,
          elevation: elevFactor * 0.2,
          slope_angle: 0.12 + rawRisk * 0.1,
          aspect: aspectFactor * 0.08,
        },
        terrainInputs: {
          elevation_m: elevationMeters,
          slope_angle_deg: slopeAngleDeg,
          aspect_deg: aspectDeg,
          terrain_roughness: 12 + elevFactor * 18,
        },
        coverageFlags: {
          sar_coverage_state: 'not_applicable',
          residual_shadow: false,
          data_gaps: ['client_generated_fallback'],
        },
      });
    }
  }

  return {
    cells,
    timestamp: new Date(Date.now() + timeOffset * 3600000).toISOString(),
    bbox,
  };
}

export function getRiskColor(score: number): string {
  return RISK_COLORS[Math.max(1, Math.min(5, Math.round(score)))] || RISK_COLORS[1];
}

export function isCellMasked(cell: Pick<GridCell, 'riskScore' | 'aptEligible' | 'publicEligible'> | null | undefined): boolean {
  if (!cell) return false;
  if (cell.publicEligible === false) return true;
  return cell.aptEligible === false || Number(cell.riskScore) <= 0;
}

export function isCellUnavailable(cell: Pick<GridCell, 'status' | 'stale' | 'disabled' | 'availabilityReason'> | null | undefined): boolean {
  if (!cell) return false;
  return Boolean(
    cell.disabled
    || cell.status === 'unavailable_terrain'
    || cell.availabilityReason
  );
}

function humanizeMaskReason(reason: string): string {
  if (reason === 'slope_outside_30_to_50_deg') return 'Outside avalanche-prone terrain profile.';
  if (reason === 'warm_low_elevation_no_snow_support') return 'No current snow/elevation relevance in this proxy forecast.';
  return reason.replace(/_/g, ' ');
}

export function getCellMaskReasons(cell: Pick<GridCell, 'aptEligible' | 'aptMaskReason' | 'publicEligible' | 'publicMaskReasons' | 'snowElevationEligible' | 'snowElevationMaskReason'> | null | undefined): string[] {
  if (!cell) return [];
  const explicitReasons = Array.isArray(cell.publicMaskReasons) ? cell.publicMaskReasons.filter(Boolean).map(String) : [];
  if (explicitReasons.length > 0) return [...new Set(explicitReasons)];

  const fallbackReasons: string[] = [];
  if (cell.aptEligible === false) {
    fallbackReasons.push(cell.aptMaskReason || 'slope_outside_30_to_50_deg');
  }
  if (cell.publicEligible === false && (cell.snowElevationEligible === false || Boolean(cell.snowElevationMaskReason))) {
    fallbackReasons.push(cell.snowElevationMaskReason || 'warm_low_elevation_no_snow_support');
  }
  return [...new Set(fallbackReasons)];
}

export function getCellMaskReasonDescriptions(cell: Pick<GridCell, 'aptEligible' | 'aptMaskReason' | 'publicEligible' | 'publicMaskReasons' | 'snowElevationEligible' | 'snowElevationMaskReason'> | null | undefined): string[] {
  return getCellMaskReasons(cell).map(humanizeMaskReason);
}

export function getCellMaskLabel(cell: Pick<GridCell, 'aptEligible' | 'aptMaskReason' | 'publicEligible' | 'publicMaskReasons' | 'snowElevationEligible' | 'snowElevationMaskReason' | 'riskScore'> | null | undefined): string {
  const reasons = getCellMaskReasons(cell);
  if (reasons.length > 1) return 'PUBLIC MASKED';
  if (reasons[0] === 'slope_outside_30_to_50_deg') return 'APT MASKED';
  if (reasons.length === 1) return 'SNOW/ELEV MASKED';
  return isCellMasked(cell) ? 'PUBLIC MASKED' : 'PUBLIC';
}

export function getCellMaskSummary(cell: Pick<GridCell, 'aptEligible' | 'aptMaskReason' | 'publicEligible' | 'publicMaskReasons' | 'snowElevationEligible' | 'snowElevationMaskReason' | 'riskScore'> | null | undefined): string {
  const reasons = getCellMaskReasons(cell);
  if (reasons.length > 1) return 'Masked from public avalanche warning.';
  if (reasons[0] === 'slope_outside_30_to_50_deg') return 'Outside avalanche-prone terrain profile.';
  if (reasons.length === 1) return 'No current snow/elevation relevance in this proxy forecast.';
  return 'Masked from public avalanche warning.';
}
