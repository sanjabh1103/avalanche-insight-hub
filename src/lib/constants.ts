// Default bounding box: Colorado Rockies region
export const DEFAULT_BBOX: [number, number, number, number] = [38.5, -107.5, 40.5, -105.5];
export const DEFAULT_CENTER: [number, number] = [39.5, -106.5];
export const DEFAULT_ZOOM = 9;
export const GRID_SIZE = 20;

// Risk level colors (HSL strings for Leaflet)
export const RISK_COLORS: Record<number, string> = {
  1: '#22c55e', // green
  2: '#84cc16', // lime
  3: '#eab308', // yellow
  4: '#f97316', // orange
  5: '#ef4444', // red
};

export const RISK_LABELS: Record<number, string> = {
  1: 'Low',
  2: 'Moderate',
  3: 'Considerable',
  4: 'High',
  5: 'Very High',
};

export const PROBLEM_TYPES = [
  'Storm Slab',
  'Wind Slab',
  'Persistent Slab',
  'Deep Persistent Slab',
  'Wet Loose',
  'Wet Slab',
  'Cornice Fall',
  'Glide Avalanche',
] as const;

export interface HimalayanZone {
  zone_type: string;
  label: string;
  climate_class: 'maritime' | 'transition' | 'continental' | 'polar_dry';
  elevation_min: number;
  elevation_max: number;
  season_start: string;
  lapse_rate_c_per_m: number;
}

export const HIMALAYAN_ZONES: HimalayanZone[] = [
  {
    zone_type: 'pir_panjal',
    label: 'Pir Panjal (NW Himalaya)',
    climate_class: 'maritime',
    elevation_min: 2500,
    elevation_max: 4500,
    season_start: '11-01',
    lapse_rate_c_per_m: -0.0065,
  },
  {
    zone_type: 'shamshabari',
    label: 'Shamshabari (NW Himalaya)',
    climate_class: 'transition',
    elevation_min: 3000,
    elevation_max: 5000,
    season_start: '11-01',
    lapse_rate_c_per_m: -0.0060,
  },
  {
    zone_type: 'great_himalaya',
    label: 'Great Himalaya (NW Himalaya)',
    climate_class: 'continental',
    elevation_min: 3500,
    elevation_max: 5500,
    season_start: '11-01',
    lapse_rate_c_per_m: -0.0055,
  },
  {
    zone_type: 'karakoram_ladakh',
    label: 'Karakoram & Ladakh',
    climate_class: 'polar_dry',
    elevation_min: 4000,
    elevation_max: 6000,
    season_start: '10-15',
    lapse_rate_c_per_m: -0.0050,
  },
];

export const ZONE_CLIMATE_LABELS: Record<string, string> = {
  maritime: 'Maritime',
  transition: 'Transition',
  continental: 'Continental',
  polar_dry: 'Polar-Dry',
};

export type ForecastMode = 'full' | 'cold_start' | 'transfer';

export const FORECAST_MODE_LABELS: Record<ForecastMode, string> = {
  full: 'Full Data',
  cold_start: 'Cold-Start (3 winters)',
  transfer: 'Transfer Learning',
};

export const FORECAST_MODE_DESCRIPTIONS: Record<ForecastMode, string> = {
  full: 'Standard training with full historical archive.',
  cold_start: 'Data-efficient RF with aggressive feature selection. Relaxed quality gates.',
  transfer: 'Transfer learning from European model weights. Coming soon.',
};

export const SEISMIC_WINDOW_1 = { start: 1.97, end: 14.57, label: 'Acute (2–15h)' };
export const SEISMIC_WINDOW_2 = { start: 38.32, end: 76.32, label: 'Delayed (38–76h)' };

export const SEISMIC_WINDOW_LABELS: Record<number, string> = {
  1: 'Window 1 — Acute post-tremor',
  2: 'Window 2 — Delayed post-tremor',
};

export const FUSION_SOURCES = {
  dl_forecast: { label: 'DL Forecast', provenance: 'MTS-LSTM + RF' },
  shap: { label: 'SHAP Drivers', provenance: 'TreeSHAP' },
  sar: { label: 'SAR Coverage', provenance: 'Sentinel-1' },
  snowpack: { label: 'Snowpack', provenance: 'Live grid proxy · local POC evidence separate' },
  seismic: { label: 'Seismic', provenance: 'USGS' },
} as const;
