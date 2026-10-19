import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ForecastActionControls from '@/components/ForecastActionControls';
import type { GridCell } from '@/lib/gridUtils';
import type { Region } from '@/components/RegionSelector';

const region: Region = {
  name: 'Colorado Rockies',
  bbox: [39.4, -106.5, 39.6, -106.3],
  center: [39.5, -106.4],
  zoom: 10,
};

const cell: GridCell = {
  row: 5,
  col: 10,
  lat: 39.5,
  lng: -106.4,
  latEnd: 39.51,
  lngEnd: -106.39,
  riskScore: 3,
  hazard: 0.5,
  exposure: 0.4,
  vulnerability: 0.3,
  problemType: 'Wind Slab',
  shapValues: {},
  probability: 0.55,
};

const grid = { cells: [cell], timestamp: '2026-05-04T12:00:00Z', bbox: region.bbox as [number, number, number, number] };

const baseProps = {
  isMobile: false,
  runForecast: async () => {},
  forecasting: false,
  setReportOpen: () => {},
  forecastId: 'test-forecast-id',
  region,
  timeOffset: 0,
  selectedCell: cell,
  expertMode: false,
  show3D: false,
  grid,
  regionEvents: [],
  eventsLoading: false,
  showEvents: false,
  setShowEvents: () => {},
};

describe('ForecastActionControls metadata badge', () => {
  it('shows grid size and loaded/total hours in the badge', () => {
    render(
      <ForecastActionControls
        {...baseProps}
        hourlyGrids={[Array(400).fill(cell), null, null]}
        forecastAvailability="ready"
        forecastSource="precomputed"
        loadedHoursCount={1}
        totalHoursHorizon={3}
        gridSize={20}
      />,
    );
    const badge = screen.getByTestId('forecast-data-badge');
    expect(badge.textContent).toContain('20×20');
    expect(badge.textContent).toContain('1/3h');
  });

  it('distinguishes horizon total from loaded count', () => {
    render(
      <ForecastActionControls
        {...baseProps}
        hourlyGrids={[Array(400).fill(cell), null, null, null, null]}
        forecastAvailability="ready"
        forecastSource="precomputed"
        loadedHoursCount={1}
        totalHoursHorizon={5}
        gridSize={20}
      />,
    );
    const badge = screen.getByTestId('forecast-data-badge');
    expect(badge.textContent).toContain('1/5h');
    expect(badge.textContent).not.toContain('5/5h');
  });

  it('badge is visible even when forecast availability is stale', () => {
    render(
      <ForecastActionControls
        {...baseProps}
        hourlyGrids={[Array(400).fill(cell)]}
        forecastAvailability="stale"
        forecastSource="precomputed"
        loadedHoursCount={1}
        totalHoursHorizon={1}
        gridSize={20}
      />,
    );
    const badge = screen.getByTestId('forecast-data-badge');
    expect(badge.textContent).toContain('STALE');
    expect(badge.textContent).toContain('20×20');
  });

  it('uses default grid size 20 when gridSize is undefined', () => {
    render(
      <ForecastActionControls
        {...baseProps}
        hourlyGrids={[Array(400).fill(cell)]}
        forecastAvailability="ready"
        forecastSource="precomputed"
        loadedHoursCount={1}
        totalHoursHorizon={1}
        gridSize={undefined}
      />,
    );
    const badge = screen.getByTestId('forecast-data-badge');
    expect(badge.textContent).toContain('20×20');
  });
});
