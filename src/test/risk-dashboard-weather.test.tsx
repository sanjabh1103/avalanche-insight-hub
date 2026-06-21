import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RiskDashboard from '@/components/RiskDashboard';
import type { GridCell } from '@/lib/gridUtils';

function buildCell(overrides: Partial<GridCell> = {}): GridCell {
  return {
    row: 5,
    col: 10,
    lat: 39.0,
    lng: -106.0,
    latEnd: 39.1,
    lngEnd: -105.9,
    riskScore: 3,
    hazard: 0.5,
    exposure: 0.4,
    vulnerability: 0.3,
    problemType: 'Wind Slab',
    shapValues: { snowfall_24h: 0.2, wind_speed: 0.1 },
    probability: 0.55,
    ...overrides,
  };
}

const weatherSummary = {
  snowfall_24h: '12',
  wind_speed: '45',
  temperature: '-8',
  precipitation: '3',
  snow_depth: '120',
};

describe('RiskDashboard weather summary', () => {
  it('renders weather summary card when weather data is provided', () => {
    render(<RiskDashboard cell={buildCell()} weatherSummary={weatherSummary} />);
    expect(screen.getByText('Weather Summary')).toBeTruthy();
    expect(screen.getByText('12 cm')).toBeTruthy();
    expect(screen.getByText('45 km/h')).toBeTruthy();
    expect(screen.getByText('-8 °C')).toBeTruthy();
    expect(screen.getByText('3 mm')).toBeTruthy();
    expect(screen.getByText('120 cm')).toBeTruthy();
  });

  it('does not render weather summary card when weather data is null', () => {
    const { container } = render(
      <RiskDashboard cell={buildCell()} weatherSummary={null} />,
    );
    expect(screen.queryByText('Weather Summary')).toBeNull();
  });

  it('renders snow depth as — when value is N/A', () => {
    render(
      <RiskDashboard
        cell={buildCell()}
        weatherSummary={{ ...weatherSummary, snow_depth: 'N/A' }}
      />,
    );
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('prevents duplicate units when weather values already contain units', () => {
    render(
      <RiskDashboard
        cell={buildCell()}
        weatherSummary={{
          snowfall_24h: '12 cm',
          wind_speed: '45 km/h',
          temperature: '-8°C',
          precipitation: '3 mm',
          snow_depth: '120 cm',
        }}
      />,
    );
    expect(screen.getByText('12 cm')).toBeTruthy();
    expect(screen.getByText('45 km/h')).toBeTruthy();
    expect(screen.getByText('-8 °C')).toBeTruthy();
    expect(screen.getByText('3 mm')).toBeTruthy();
    expect(screen.getByText('120 cm')).toBeTruthy();
    expect(screen.queryByText('12 cm cm')).toBeNull();
    expect(screen.queryByText('45 km/h km/h')).toBeNull();
    expect(screen.queryByText('-8°C°C')).toBeNull();
    expect(screen.queryByText('3 mm mm')).toBeNull();
    expect(screen.queryByText('120 cm cm')).toBeNull();
  });

  it('prevents duplicate C suffix on temperature', () => {
    render(
      <RiskDashboard
        cell={buildCell()}
        weatherSummary={{
          ...weatherSummary,
          temperature: '-8 C',
        }}
      />,
    );
    expect(screen.getByText('-8 °C')).toBeTruthy();
    expect(screen.queryByText('-8 C°C')).toBeNull();
  });
});
