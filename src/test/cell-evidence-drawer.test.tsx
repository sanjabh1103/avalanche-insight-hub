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
    expect(screen.getByText(/ML Explanation/i)).toBeTruthy();
    expect(screen.getAllByText(/Physics Narrative/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Linked reality evidence/i)).toBeTruthy();
    expect(await screen.findByText(/Forecast outcomes 1 · field reports 1/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /queue for scientist review/i })).toBeTruthy();
  });

  it('renders source freshness, evidence refs, baseline IDs and lineage when present', async () => {
    fromMock.mockImplementation((table: string) => {
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
      verificationPacket: {
        anomaly_state: 'anomaly',
        residual_zscore: 2.8,
        attribution_bucket: 'sensing_gap',
        confidence: 0.85,
        packet_version: 'v1',
        contributing_sensors: ['sar', 'optical', 'weather'],
        source_freshness_hours: { sar: 12.5, optical: 96.0, weather: 3.0 },
        evidence_refs: ['openmeteo:great_himalaya:cell_1', 's2:tile_42:2026-01-15'],
        baseline_ids: ['bl_001', 'bl_002'],
        lineage: {
          source_lineage: {
            weather: { reference: 'openmeteo:cell_1', verified: true },
            sar: { reference: 's1:scene_42', verified: false },
          },
        },
      },
    };

    render(<CellEvidenceDrawer selectedCell={cell} regionName="Colorado Rockies" />);

    expect(screen.getByText('Source freshness')).toBeTruthy();
    expect(screen.getAllByText('sar').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('12.5h')).toBeTruthy();
    expect(screen.getByText('96.0h')).toBeTruthy();
    expect(screen.getByText('Evidence refs')).toBeTruthy();
    expect(screen.getByText('openmeteo:great_himalaya:cell_1')).toBeTruthy();
    expect(screen.getByText('Baselines:')).toBeTruthy();
    expect(screen.getByText('bl_001')).toBeTruthy();
    expect(screen.getByText('Lineage')).toBeTruthy();
    expect(screen.getByText('✓ verified')).toBeTruthy();
    expect(screen.getByText('✗ unverified')).toBeTruthy();
  });
});
