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

  it('uses proxy-safe empty-state wording when data is missing', () => {
    render(
      <TooltipProvider>
        <SnowpackProxyCard selectedCell={null} />
      </TooltipProvider>,
    );

    expect(screen.getByText(/Snowpack proxy unavailable/i)).toBeTruthy();
  });
});
