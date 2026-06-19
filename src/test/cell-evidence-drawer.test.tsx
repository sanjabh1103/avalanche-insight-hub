import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const { fromMock, getUserMock } = vi.hoisted(() => ({
  fromMock: vi.fn(),
  getUserMock: vi.fn(async () => ({ data: { user: null }, error: null })),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getUser: getUserMock,
    },
    from: fromMock,
  },
}));

import CellEvidenceDrawer from '@/components/CellEvidenceDrawer';
import type { GridCell } from '@/lib/gridUtils';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function createQueryBuilder(data: unknown) {
  const builder = {
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    then: (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
      Promise.resolve({ data, error: null }).then(resolve, reject),
  };
  return builder;
}

describe('CellEvidenceDrawer', () => {
  it('renders selected-cell evidence and keeps validation wording bounded', async () => {
    fromMock.mockImplementation((table: string) => {
      if (table === 'forecast_outcomes') {
        return createQueryBuilder([{ id: 'outcome-1' }]);
      }
      if (table === 'field_reports') {
        return createQueryBuilder([{ id: 'field-report-1' }]);
      }
      return createQueryBuilder([]);
    });
    const cell: GridCell = {
      row: 4,
      col: 7,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 4,
      hazard: 0.7,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      probability: 0.72,
      uncertaintyClass: 'high',
      uncertaintySpan: 0.36,
      runoutSeed: true,
      explainabilityMode: 'heuristic_fallback',
      dominantDriverFeature: 'wind_speed',
      publicEligible: true,
      snowpackProxy: {
        estimated_shear_strength: 2.4,
        snow_settlement_index: 0.31,
      },
    };

    render(<CellEvidenceDrawer selectedCell={cell} regionName="Colorado Rockies" />);

    expect(screen.getByText('Cell Evidence')).toBeTruthy();
    expect(screen.getByText('r4 c7')).toBeTruthy();
    expect(screen.getByText(/This is a proxy signal for review, not completed weak-layer validation/i)).toBeTruthy();
    expect(screen.getByText(/Linked reality evidence/i)).toBeTruthy();
    expect(await screen.findByText(/Forecast outcomes 1 · field reports 1/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /queue for scientist review/i })).toBeTruthy();
  });
});
