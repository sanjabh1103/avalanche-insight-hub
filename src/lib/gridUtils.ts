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
}

export interface ForecastGrid {
  cells: GridCell[];
  timestamp: string;
  bbox: [number, number, number, number];
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
