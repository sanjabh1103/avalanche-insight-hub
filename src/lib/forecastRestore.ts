import type { ForecastGridRowRecord } from '@/lib/gridUtils';

export interface SharedForecastRunRecord {
  id: string;
  region_name: string;
  region_key: string;
  forecast_date: string;
  horizon_hours: number;
  manifest_storage_ref: string | null;
  compatibility_forecast_grid_id: string | null;
  forecast_bulletins?: unknown;
  weather_summary?: unknown;
  model_metadata?: unknown;
  status?: string | null;
  published_at?: string | null;
  created_at?: string | null;
}

interface SharedForecastRestoreDeps {
  fetchRunById: (sharedForecast: string) => Promise<SharedForecastRunRecord | null>;
  fetchRunByCompatibilityForecastGridId: (sharedForecast: string) => Promise<SharedForecastRunRecord | null>;
  fetchGridById: (sharedForecast: string) => Promise<ForecastGridRowRecord | null>;
}

export type SharedForecastResolution =
  | {
    source: 'forecast_runs';
    resolvedBy: 'forecast_run_id' | 'compatibility_forecast_grid_id';
    run: SharedForecastRunRecord;
  }
  | {
    source: 'forecast_grids';
    resolvedBy: 'legacy_forecast_grid_id';
    grid: ForecastGridRowRecord;
  }
  | {
    source: 'missing';
    resolvedBy: 'none';
  };

export async function resolveSharedForecast(
  sharedForecast: string,
  deps: SharedForecastRestoreDeps,
): Promise<SharedForecastResolution> {
  const runById = await deps.fetchRunById(sharedForecast);
  if (runById?.manifest_storage_ref) {
    return {
      source: 'forecast_runs',
      resolvedBy: 'forecast_run_id',
      run: runById,
    };
  }

  const runByCompatibilityId = await deps.fetchRunByCompatibilityForecastGridId(sharedForecast);
  if (runByCompatibilityId?.manifest_storage_ref) {
    return {
      source: 'forecast_runs',
      resolvedBy: 'compatibility_forecast_grid_id',
      run: runByCompatibilityId,
    };
  }

  const gridById = await deps.fetchGridById(sharedForecast);
  if (gridById) {
    return {
      source: 'forecast_grids',
      resolvedBy: 'legacy_forecast_grid_id',
      grid: gridById,
    };
  }

  return {
    source: 'missing',
    resolvedBy: 'none',
  };
}
