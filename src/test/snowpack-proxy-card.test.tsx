import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import SnowpackProxyCard from '@/components/SnowpackProxyCard';
import { TooltipProvider } from '@/components/ui/tooltip';

describe('SnowpackProxyCard', () => {
  it('renders bounded proxy wording when proxy data is available', () => {
    render(
      <TooltipProvider>
        <SnowpackProxyCard
          selectedCell={{
            row: 0,
            col: 0,
            lat: 0,
            lng: 0,
            latEnd: 0,
            lngEnd: 0,
            riskScore: 2,
            hazard: 0.4,
            exposure: 0.3,
            vulnerability: 0.2,
            problemType: 'Persistent Slab',
            shapValues: {},
            probability: 0.5,
            snowpackProxy: {
              estimated_shear_strength: 4.2,
              snow_settlement_index: 0.61,
              season_start: '2025-11-01',
              method: 'seasonal_cumulative_v1',
            },
          }}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText('Weather-Driven Heuristic Proxy')).toBeTruthy();
    expect(screen.getByText(/not a direct field measurement/i)).toBeTruthy();
    expect(screen.getByText(/Season start:/i)).toBeTruthy();
  }, 15000);

  it('renders provenance even when season_start is absent', () => {
    render(
      <TooltipProvider>
        <SnowpackProxyCard
          selectedCell={{
            row: 0,
            col: 0,
            lat: 0,
            lng: 0,
            latEnd: 0,
            lngEnd: 0,
            riskScore: 2,
            hazard: 0.4,
            exposure: 0.3,
            vulnerability: 0.2,
            problemType: 'Persistent Slab',
            shapValues: {},
            snowpackProxy: {
              source_class: 'proxy',
              source: 'open_meteo_archive',
              uncertainty: 0.35,
              quality_flags: ['candidate'],
              run_id: 'run-001',
            },
          }}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText(/Source class:/i)).toBeTruthy();
    expect(screen.getByText(/open_meteo_archive/i)).toBeTruthy();
    expect(screen.getByText(/Uncertainty:/i)).toBeTruthy();
    expect(screen.getByText(/run-001/i)).toBeTruthy();
  });

  it('uses proxy-safe empty-state wording when data is missing', () => {
    render(
      <TooltipProvider>
        <SnowpackProxyCard selectedCell={null} />
      </TooltipProvider>,
    );

    expect(screen.getByText(/Snowpack proxy unavailable/i)).toBeTruthy();
  });

  it('renders execution, track, forecast, and partial-state provenance', () => {
    render(
      <TooltipProvider>
        <SnowpackProxyCard
          selectedCell={{
            row: 0, col: 0, lat: 0, lng: 0, latEnd: 1, lngEnd: 1,
            riskScore: 2, hazard: 0.4, exposure: 0.3, vulnerability: 0.2,
            problemType: 'Persistent Slab', shapValues: {},
            snowpackProxy: {
              execution_status: 'partial',
              track: 'track_2_nepal_engineering',
              approval_state: 'shadow_only',
              forecast_cycle: '2026-01-15T00:00:00Z',
              lead_time_h: 48,
              profile_available: false,
              stale_reason: 'missing .haz artifact',
              official_warning_eligible: false,
            },
          }}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText(/Execution status:/i)).toBeTruthy();
    expect(screen.getByText('partial')).toBeTruthy();
    expect(screen.getByText(/track_2_nepal_engineering/i)).toBeTruthy();
    expect(screen.getByText(/lead:/i)).toBeTruthy();
    expect(screen.getByText(/2026-01-15T00:00:00Z/i)).toBeTruthy();
    expect(screen.getByText(/missing \.haz artifact/i)).toBeTruthy();
    expect(screen.getByTestId('snowpack-official-warning-eligibility')).toHaveTextContent(/no/i);
  });
});
