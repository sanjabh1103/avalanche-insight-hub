import { GRID_SIZE, RISK_COLORS, PROBLEM_TYPES } from './constants';

export interface GridCell {
  row: number;
  col: number;
  lat: number;
  lng: number;
  latEnd: number;
  lngEnd: number;
  riskScore: number;
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
  };
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
  grid_geojson: unknown;
  runout_polygons?: unknown;
  weather_summary?: unknown;
  model_metadata?: ForecastModelMetadata | unknown;
  status?: string;
  created_at?: string;
}

function normalizeUncertaintyClass(span: number | undefined): 'low' | 'medium' | 'high' | undefined {
  if (typeof span !== 'number' || !Number.isFinite(span)) return undefined;
  if (span > 0.3) return 'high';
  if (span > 0.18) return 'medium';
  return 'low';
}

function normalizeCell(cell: Partial<GridCell> & Record<string, unknown>): GridCell {
  const row = Number(cell.row ?? 0);
  const col = Number(cell.col ?? 0);
  const riskScore = Number(cell.riskScore ?? cell.risk_score ?? 1);
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
    lat: Number(cell.lat ?? 0),
    lng: Number(cell.lng ?? 0),
    latEnd: Number(cell.latEnd ?? cell.lat_end ?? 0),
    lngEnd: Number(cell.lngEnd ?? cell.lng_end ?? 0),
    riskScore: Number.isFinite(riskScore) ? riskScore : 1,
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
    featureValues: (cell.featureValues as Record<string, number>) || (cell.feature_values as Record<string, number>) || undefined,
    shapContext: normalizeShapContext(cell.shapContext ?? cell.shap_context),
    explanationSummary: typeof cell.explanationSummary === 'string'
      ? cell.explanationSummary
      : (typeof cell.explanation_summary === 'string' ? String(cell.explanation_summary) : null),
    coverageFlags: normalizeCoverageFlags(cell.coverageFlags ?? cell.coverage_flags),
    snowpackProxy: normalizeSnowpackProxy(cell.snowpackProxy ?? cell.snowpack_proxy),
  };
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
  return row.grid_geojson.map((cell) => normalizeCell(cell as Partial<GridCell> & Record<string, unknown>));
}

export function forecastGridRowToHourlyGrids(row: ForecastGridRowRecord): GridCell[][] {
  const cells = forecastGridRowToCells(row);
  const horizonHours = Math.max(1, Math.min(Number(row.horizon_hours || 24), 72));
  return Array.from({ length: horizonHours }, () => cells.map((cell) => ({ ...cell })));
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

      const problemIdx = Math.floor(rawRisk * (PROBLEM_TYPES.length - 1));

      cells.push({
        row: r,
        col: c,
        lat,
        lng,
        latEnd: lat + latStep,
        lngEnd: lng + lngStep,
        riskScore,
        hazard,
        exposure,
        vulnerability,
        problemType: PROBLEM_TYPES[problemIdx],
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
