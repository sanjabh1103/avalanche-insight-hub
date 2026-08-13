import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import type { GridCell } from '@/lib/gridUtils';
import { _actWarnings } from '@/test/setup';

vi.mock('@/integrations/supabase/client', () => {
  const mockChain = {
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    maybeSingle: vi.fn().mockResolvedValue({ data: null, error: null }),
  };
  return {
    supabase: {
      functions: { invoke: vi.fn().mockResolvedValue({ data: null, error: null }) },
      from: vi.fn(() => mockChain),
      channel: vi.fn(() => ({
        on: vi.fn().mockReturnThis(),
        subscribe: vi.fn().mockReturnThis(),
      })),
      removeChannel: vi.fn(),
    },
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { useForecastState } from '@/hooks/useForecastState';
import { REGIONS } from '@/components/RegionSelector';

function createWrapper(initialEntries: string[] = ['/']) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter
      initialEntries={initialEntries}
    >
      {children}
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  _actWarnings.length = 0;
});

afterEach(async () => {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  expect(_actWarnings, `React act() warnings detected: ${_actWarnings.length} unresolved`).toHaveLength(0);
});

describe('useForecastState — initial state', () => {
  it('returns all expected top-level properties', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const r = result.current;
    expect(r).toHaveProperty('region');
    expect(r).toHaveProperty('timeOffset');
    expect(r).toHaveProperty('selectedCell');
    expect(r).toHaveProperty('forecasting');
    expect(r).toHaveProperty('forecastId');
    expect(r).toHaveProperty('hourlyGrids');
    expect(r).toHaveProperty('forecastSource');
    expect(r).toHaveProperty('forecastAvailability');
    expect(r).toHaveProperty('forecastNotice');
    expect(r).toHaveProperty('forecastBulletin');
    expect(r).toHaveProperty('showEvents');
    expect(r).toHaveProperty('events');
    expect(r).toHaveProperty('weatherSummary');
    expect(r).toHaveProperty('expertMode');
    expect(r).toHaveProperty('grid');
    expect(r).toHaveProperty('handleCellClick');
    expect(r).toHaveProperty('handleRegionChange');
    expect(r).toHaveProperty('runForecast');
    expect(r).toHaveProperty('ingestSensorData');
    expect(r).toHaveProperty('toggleSensorOverlay');
  });

  it('initializes with first region from REGIONS', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.region).toEqual(REGIONS[0]);
  });

  it('starts with timeOffset 0', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.timeOffset).toBe(0);
  });

  it('starts with forecasting false', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.forecasting).toBe(false);
  });

  it('starts with forecastAvailability unavailable', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.forecastAvailability).toBe('unavailable');
  });
});

describe('useForecastState — handleCellClick', () => {
  it('sets selectedCell when cell is available', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const cell = {
      row: 0, col: 0, lat: 39, lng: -106, lat_end: 39.1, lng_end: -105.9,
      risk_score: 3, hazard: 0.5, exposure: 0.3, vulnerability: 0.2,
      problem_type: 'Wind Slab', shap_values: {},
    };
    act(() => {
      result.current.handleCellClick(cell as unknown as GridCell);
    });
    expect(result.current.selectedCell).toEqual(cell);
  });

  it('does not set selectedCell when cell is unavailable', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    act(() => {
      result.current.handleCellClick({
        row: 0, col: 0, lat: 39, lng: -106, lat_end: 39.1, lng_end: -105.9,
        risk_score: -1, hazard: 0, exposure: 0, vulnerability: 0,
        problem_type: 'Unavailable', shap_values: {},
        disabled: true,
      } as unknown as GridCell);
    });
    expect(result.current.selectedCell).toBeNull();
  });
});

describe('useForecastState — handleRegionChange', () => {
  it('resets forecast state when region changes', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const newRegion = REGIONS[1] ?? REGIONS[0];
    act(() => {
      result.current.handleRegionChange(newRegion);
    });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.region).toEqual(newRegion);
    expect(result.current.selectedCell).toBeNull();
    expect(result.current.hourlyGrids).toBeNull();
    expect(result.current.forecastId).toBeUndefined();
    expect(result.current.forecastAvailability).toBe('unavailable');
    expect(result.current.timeOffset).toBe(0);
  });
});

describe('useForecastState — toggleSensorOverlay', () => {
  it('toggles showSensorOverlay from false to true', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.showSensorOverlay).toBe(false);
    act(() => {
      result.current.toggleSensorOverlay();
    });
    expect(result.current.showSensorOverlay).toBe(true);
    act(() => {
      result.current.toggleSensorOverlay();
    });
    expect(result.current.showSensorOverlay).toBe(false);
  });
});

describe('useForecastState — ingestSensorData', () => {
  it('parses valid JSON array of sensor events', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const rawData = JSON.stringify([
      { event_id: 'evt1', lat: 39.5, lng: -106.2, timestamp: '2026-01-01T00:00:00Z', sensor_type: 'seismic' },
    ]);
    act(() => {
      result.current.ingestSensorData(rawData);
    });
    expect(result.current.sensorEvents).toHaveLength(1);
    expect(result.current.sensorEvents[0].event_id).toBe('evt1');
    expect(result.current.showSensorOverlay).toBe(true);
  });

  it('parses JSON with events wrapper', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const rawData = JSON.stringify({
      events: [
        { event_id: 'evt2', lat: 40.0, lng: -105.5, sensor_type: 'geophone' },
      ],
    });
    act(() => {
      result.current.ingestSensorData(rawData);
    });
    expect(result.current.sensorEvents).toHaveLength(1);
    expect(result.current.sensorEvents[0].event_id).toBe('evt2');
  });

  it('parses CSV format sensor data', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const csvData = 'event_id,lat,lng,sensor_type\nevt3,39.5,-106.2,seismic\n';
    act(() => {
      result.current.ingestSensorData(csvData);
    });
    expect(result.current.sensorEvents).toHaveLength(1);
    expect(result.current.sensorEvents[0].event_id).toBe('evt3');
    expect(result.current.sensorEvents[0].lat).toBe(39.5);
  });

  it('rejects completely invalid input without crashing', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    act(() => {
      result.current.ingestSensorData('not valid json or csv');
    });
    expect(result.current.sensorEvents).toHaveLength(0);
  });

  it('filters out events missing required fields', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    const rawData = JSON.stringify([
      { event_id: 'good', lat: 39.5, lng: -106.2 },
      { event_id: 'no-lat', lng: -106.2 },
      { lat: 39.5, lng: -106.2 },
    ]);
    act(() => {
      result.current.ingestSensorData(rawData);
    });
    expect(result.current.sensorEvents).toHaveLength(1);
    expect(result.current.sensorEvents[0].event_id).toBe('good');
  });
});

describe('useForecastState — expert mode', () => {
  it('enabling expert mode opens expert panel', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.expertMode).toBe(false);
    expect(result.current.expertPanelOpen).toBe(false);
    act(() => {
      result.current.setExpertMode(true);
    });
    expect(result.current.expertMode).toBe(true);
    expect(result.current.expertPanelOpen).toBe(true);
  });

  it('disabling expert mode closes panel and resets overlays', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    act(() => {
      result.current.setExpertMode(true);
      result.current.setShowHeatmap(true);
      result.current.setShowRoads(true);
    });
    expect(result.current.expertPanelOpen).toBe(true);
    expect(result.current.showHeatmap).toBe(true);
    act(() => {
      result.current.setExpertMode(false);
    });
    expect(result.current.expertMode).toBe(false);
    expect(result.current.expertPanelOpen).toBe(false);
    expect(result.current.showHeatmap).toBe(false);
    expect(result.current.showRoads).toBe(false);
  });
});

describe('useForecastState — public-mask-smoke fixture', () => {
  it('loads fixture when fixture=public-mask-smoke URL param is present', async () => {
    const { result } = renderHook(() => useForecastState(), {
      wrapper: createWrapper(['/?fixture=public-mask-smoke']),
    });
    await waitFor(() => {
      expect(result.current.forecastAvailability).toBe('ready');
    });
    expect(result.current.region.name).toBe('Colorado Rockies');
    expect(result.current.hourlyGrids).not.toBeNull();
    expect(result.current.forecastSource).toBe('precomputed');
  });

  it('fixture provides grid cells with expected structure', async () => {
    const { result } = renderHook(() => useForecastState(), {
      wrapper: createWrapper(['/?fixture=public-mask-smoke']),
    });
    await waitFor(() => {
      expect(result.current.hourlyGrids).not.toBeNull();
    });
    const firstHour = result.current.hourlyGrids![0];
    expect(firstHour).not.toBeNull();
    expect(firstHour!.length).toBeGreaterThan(0);
    expect(firstHour![0]).toHaveProperty('lat');
    expect(firstHour![0]).toHaveProperty('lng');
    expect(firstHour![0]).toHaveProperty('riskScore');
  });
});

describe('useForecastState — runForecast with fixture', () => {
  it('shows info toast and does not fetch when fixture is active', async () => {
    const { toast } = await import('sonner');
    const { result } = renderHook(() => useForecastState(), {
      wrapper: createWrapper(['/?fixture=public-mask-smoke']),
    });
    await act(async () => {
      await result.current.runForecast();
    });
    expect(toast.info).toHaveBeenCalled();
  });
});

describe('useForecastState — grid memo', () => {
  it('returns empty cells array when no forecast is loaded', async () => {
    const { result } = renderHook(() => useForecastState(), { wrapper: createWrapper() });
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(result.current.grid.cells).toEqual([]);
    expect(result.current.grid).toHaveProperty('timestamp');
    expect(result.current.grid).toHaveProperty('bbox');
  });

  it('returns cells from hourlyGrids at current timeOffset after fixture load', async () => {
    const { result } = renderHook(() => useForecastState(), {
      wrapper: createWrapper(['/?fixture=public-mask-smoke']),
    });
    await waitFor(() => {
      expect(result.current.grid.cells.length).toBeGreaterThan(0);
    });
    expect(result.current.grid.bbox).toBeDefined();
  });
});
