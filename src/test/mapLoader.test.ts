import { describe, it, expect } from 'vitest';
import type { ForecastMap, MapCell } from '../lib/mapLoader';

describe('mapLoader types', () => {
  it('MapCell has expected fields', () => {
    const cell: MapCell = {
      id: 'cell-00-00',
      row: 0,
      col: 0,
      bounds: [[26.5, 80.0]],
      riskBand: 'moderate',
      uncertaintyBand: 'medium',
      availability: 'available',
      explanationCode: 'wind_slab_moderate',
    };
    expect(cell.id).toBe('cell-00-00');
    expect(cell.riskBand).toBe('moderate');
  });

  it('ForecastMap blocked state has required fields', () => {
    const map: ForecastMap = {
      schemaVersion: 'public_forecast_map_v1',
      status: 'blocked',
      blockedReason: 'No approved snapshot',
      region: null,
      validFrom: null,
      validTo: null,
      source: null,
      cells: [],
      disclaimer: 'Map snapshot not available.',
      license: null,
      attribution: null,
    };
    expect(map.status).toBe('blocked');
    expect(map.cells.length).toBe(0);
    expect(map.disclaimer).toContain('not available');
  });
});
