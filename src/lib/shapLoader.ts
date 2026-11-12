import { supabase } from '@/integrations/supabase/client';

export interface ShapTopFeature {
  feature: string;
  shap_value: number;
  feature_value: number;
  rank: number;
}

export interface ShapResult {
  origin: 'forecast_shap_cache' | 'inline_cell_context';
  topFeatures: ShapTopFeature[];
  modelVersion?: string;
  dominantDriver?: string | null;
  baseValue?: number | null;
}

const TTL_MS = 30_000;
const MAX_ENTRIES = 256;

interface CacheEntry {
  expiresAt: number;
  result: ShapResult | null;
}

const cache = new Map<string, CacheEntry>();

function cacheKey(forecastGridId: string, row: number, col: number, hour: number): string {
  return `${forecastGridId}|${row}|${col}|${hour}`;
}

function pruneCache() {
  if (cache.size <= MAX_ENTRIES) return;
  // Drop oldest entries until we fit.
  const keys = Array.from(cache.keys()).slice(0, cache.size - MAX_ENTRIES);
  keys.forEach((key) => cache.delete(key));
}

function normalizeTopFeatures(value: unknown): ShapTopFeature[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const row = item as Record<string, unknown>;
      return {
        feature: String(row.feature ?? ''),
        shap_value: Number(row.shap_value ?? 0),
        feature_value: Number(row.feature_value ?? 0),
        rank: Number(row.rank ?? 0),
      };
    })
    .filter((item) => item.feature.length > 0)
    .sort((a, b) => (a.rank || 99) - (b.rank || 99));
}

/**
 * P1.2: Load real TreeSHAP contributions for a specific forecast cell from
 * the forecast_shap_cache table via the get_shap_for_cell RPC. Returns null
 * when the table has no row for this cell/model version yet — callers are
 * expected to fall back to inline `cell.shapValues` and label the output as
 * "heuristic" rather than "TreeSHAP".
 */
export async function loadShapForCell(
  forecastGridId: string | null | undefined,
  row: number,
  col: number,
  hour = 0,
): Promise<ShapResult | null> {
  if (!forecastGridId) return null;

  const key = cacheKey(forecastGridId, row, col, hour);
  const cached = cache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.result;
  }

  try {
    const { data, error } = await supabase.rpc('get_shap_for_cell', {
      p_forecast_grid_id: forecastGridId,
      p_cell_row: row,
      p_cell_col: col,
      p_forecast_hour: hour,
    });
    if (error || !Array.isArray(data) || data.length === 0) {
      cache.set(key, { expiresAt: Date.now() + TTL_MS, result: null });
      pruneCache();
      return null;
    }
    const hit = data[0] as Record<string, unknown>;
    const topFeatures = normalizeTopFeatures(hit.top_features);
    if (topFeatures.length === 0) {
      cache.set(key, { expiresAt: Date.now() + TTL_MS, result: null });
      pruneCache();
      return null;
    }
    const result: ShapResult = {
      origin: 'forecast_shap_cache',
      topFeatures,
      modelVersion: typeof hit.model_version === 'string' ? hit.model_version : undefined,
      dominantDriver: typeof hit.dominant_driver === 'string' ? hit.dominant_driver : null,
      baseValue: typeof hit.base_value === 'number' ? hit.base_value : null,
    };
    cache.set(key, { expiresAt: Date.now() + TTL_MS, result });
    pruneCache();
    return result;
  } catch (error) {
    // Network or RPC error; surface null so caller renders heuristic path.
    // We deliberately don't retry — the UI has its own heuristic fallback.
    console.warn('loadShapForCell failed:', (error as Error).message);
    cache.set(key, { expiresAt: Date.now() + TTL_MS, result: null });
    pruneCache();
    return null;
  }
}

export function clearShapCache() {
  cache.clear();
}
