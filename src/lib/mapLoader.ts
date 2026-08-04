export interface MapCell {
  id: string;
  row: number;
  col: number;
  bounds: [[number, number]];
  riskBand: string | null;
  uncertaintyBand: string | null;
  availability: string;
  explanationCode: string;
}

export interface ForecastMap {
  schemaVersion: string;
  status: 'approved' | 'preview_only' | 'blocked';
  blockedReason?: string;
  region: string | null;
  validFrom: string | null;
  validTo: string | null;
  source: {
    name: string;
    license: string;
    spdx: string | null;
    attribution: string;
    contentHash: string;
  } | null;
  cells: MapCell[];
  disclaimer: string;
  license: string | null;
  attribution: string | null;
}

export interface ForecastMapManifest {
  schemaVersion: string;
  status: 'approved' | 'preview_only' | 'blocked';
  mapSha256: string | null;
  blockedReason?: string;
}

export async function loadForecastMap(): Promise<ForecastMap> {
  const response = await fetch('/data/forecast-map.json');
  if (!response.ok) throw new Error(`Failed to load forecast map: ${response.status}`);
  return response.json();
}

export async function loadForecastMapManifest(): Promise<ForecastMapManifest> {
  const response = await fetch('/data/forecast-map-manifest.json');
  if (!response.ok) throw new Error(`Failed to load forecast map manifest: ${response.status}`);
  return response.json();
}
