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
  5: 'Extreme',
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
