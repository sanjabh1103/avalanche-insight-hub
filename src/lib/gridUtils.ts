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
  featureValues?: Record<string, number>;
  shapContext?: {
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
  model_metadata?: unknown;
  status?: string;
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
  const topFeatures = (value as Record<string, unknown>).topFeatures ?? (value as Record<string, unknown>).top_features;
  if (!Array.isArray(topFeatures)) return undefined;
  return {
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

function normalizeCoverageFlags(value: unknown): GridCell['coverageFlags'] {
  if (!value || typeof value !== 'object') return undefined;
  const row = value as Record<string, unknown>;
  return {
    sar_coverage_state: typeof row.sar_coverage_state === 'string' ? row.sar_coverage_state : undefined,
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
