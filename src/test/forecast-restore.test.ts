import { describe, expect, it, vi } from 'vitest';

import type { ForecastGridRowRecord } from '@/lib/gridUtils';
import {
  resolveSharedForecast,
  type SharedForecastRunRecord,
} from '@/lib/forecastRestore';

function buildRun(overrides: Partial<SharedForecastRunRecord> = {}): SharedForecastRunRecord {
  return {
    id: 'run-1',
    region_name: 'Himalayas (Nepal)',
    region_key: 'himalayas_nepal',
    forecast_date: '2026-05-02',
    horizon_hours: 24,
    manifest_storage_ref: 'forecast-artifacts/manifests/run-1.json',
    compatibility_forecast_grid_id: 'grid-compat-1',
    ...overrides,
  };
}

function buildGrid(overrides: Partial<ForecastGridRowRecord> = {}): ForecastGridRowRecord {
  return {
    id: 'grid-1',
    region_name: 'Himalayas (Nepal)',
    region_key: 'himalayas_nepal',
    forecast_date: '2026-05-02',
    horizon_hours: 24,
    bbox: [27.8, 86.7, 28.1, 87.1],
    grid_geojson: [],
    hourly_grids: [],
    runout_polygons: [],
    ...overrides,
  };
}

describe('resolveSharedForecast', () => {
  it('prefers a direct forecast_runs id hit over compatibility and legacy rows', async () => {
    const fetchRunById = vi.fn().mockResolvedValue(buildRun({ id: 'run-direct' }));
    const fetchRunByCompatibilityForecastGridId = vi.fn().mockResolvedValue(buildRun({ id: 'run-compat' }));
    const fetchGridById = vi.fn().mockResolvedValue(buildGrid({ id: 'grid-legacy' }));

    const resolution = await resolveSharedForecast('shared-key', {
      fetchRunById,
      fetchRunByCompatibilityForecastGridId,
      fetchGridById,
    });

    expect(resolution).toMatchObject({
      source: 'forecast_runs',
      resolvedBy: 'forecast_run_id',
      run: { id: 'run-direct' },
    });
    expect(fetchRunById).toHaveBeenCalledWith('shared-key');
    expect(fetchRunByCompatibilityForecastGridId).not.toHaveBeenCalled();
    expect(fetchGridById).not.toHaveBeenCalled();
  });

  it('falls back to compatibility_forecast_grid_id before checking legacy forecast_grids', async () => {
    const fetchRunById = vi.fn().mockResolvedValue(null);
    const fetchRunByCompatibilityForecastGridId = vi.fn().mockResolvedValue(buildRun({ id: 'run-compat' }));
    const fetchGridById = vi.fn().mockResolvedValue(buildGrid({ id: 'grid-legacy' }));

    const resolution = await resolveSharedForecast('shared-key', {
      fetchRunById,
      fetchRunByCompatibilityForecastGridId,
      fetchGridById,
    });

    expect(resolution).toMatchObject({
      source: 'forecast_runs',
      resolvedBy: 'compatibility_forecast_grid_id',
      run: { id: 'run-compat' },
    });
    expect(fetchGridById).not.toHaveBeenCalled();
  });

  it('uses the legacy forecast_grids row only when no published run is available', async () => {
    const fetchRunById = vi.fn().mockResolvedValue(buildRun({ manifest_storage_ref: null }));
    const fetchRunByCompatibilityForecastGridId = vi.fn().mockResolvedValue(null);
    const fetchGridById = vi.fn().mockResolvedValue(buildGrid({ id: 'grid-legacy' }));

    const resolution = await resolveSharedForecast('shared-key', {
      fetchRunById,
      fetchRunByCompatibilityForecastGridId,
      fetchGridById,
    });

    expect(resolution).toMatchObject({
      source: 'forecast_grids',
      resolvedBy: 'legacy_forecast_grid_id',
      grid: { id: 'grid-legacy' },
    });
  });
});
