import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MultiModalFusionCard from '@/components/MultiModalFusionCard';
import type { GridCell } from '@/lib/gridUtils';

vi.mock('@/lib/riskNarratives', () => ({
  selectRiskDrivers: vi.fn(() => ({ drivers: [] })),
}));

vi.mock('@/lib/constants', () => ({
  RISK_LABELS: { 1: 'Low', 2: 'Moderate', 3: 'Considerable', 4: 'High', 5: 'Extreme' },
  FUSION_SOURCES: {
    snowpack: { provenance: 'Live grid proxy · local POC evidence separate' },
  },
}));

vi.mock('@/lib/gridUtils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/gridUtils')>();
  return {
    ...actual,
    getRiskColor: vi.fn(() => 'rgb(255, 0, 0)'),
  };
});

function makeCell(overrides: Partial<GridCell> = {}): GridCell {
  return {
    row: 0,
    col: 0,
    lat: 39,
    lng: -106,
    latEnd: 39.1,
    lngEnd: -105.9,
    riskScore: 3,
    hazard: 0.5,
    exposure: 0.3,
    vulnerability: 0.2,
    problemType: 'Wind Slab',
    shapValues: {},
    ...overrides,
  };
}

describe('MultiModalFusionCard — Wave D verification fields', () => {
  it('renders placeholder when no cell selected', () => {
    render(<MultiModalFusionCard selectedCell={null} />);
    expect(screen.getByText(/select a cell/i)).toBeTruthy();
  });

  it('renders anomaly badge row when verificationPacket present', () => {
    const cell = makeCell({
      verificationPacket: {
        anomaly_state: 'anomaly',
        residual_zscore: 2.8,
        attribution_bucket: 'forcing_error',
      },
      discrepancyReasons: ['rapid_loading_anomaly'],
    });
    render(<MultiModalFusionCard selectedCell={cell} />);
    expect(screen.getByText('ANOMALY')).toBeTruthy();
    expect(screen.getByText(/z=2\.80/)).toBeTruthy();
    expect(screen.getByText(/forcing error/i)).toBeTruthy();
    expect(screen.getByText('rapid_loading_anomaly')).toBeTruthy();
  });

  it('renders consensus gauge when fusionEvidence present', () => {
    const cell = makeCell({
      fusionEvidence: {
        consensus_score: 0.82,
        contributing_sensors: ['s1', 'optical'],
      },
    });
    render(<MultiModalFusionCard selectedCell={cell} />);
    expect(screen.getByText(/82%/)).toBeTruthy();
    expect(screen.getByText('s1')).toBeTruthy();
    expect(screen.getByText('optical')).toBeTruthy();
  });

  it('renders baseline deviation row when observed and baseline_p50 present', () => {
    const cell = makeCell({
      verificationPacket: {
        observed: 1.2,
        baseline_p50: 0.8,
        residual_zscore: 2.5,
      },
    });
    render(<MultiModalFusionCard selectedCell={cell} />);
    expect(screen.getByText(/obs 1\.20/)).toBeTruthy();
    expect(screen.getByText(/p50 0\.80/)).toBeTruthy();
    expect(screen.getByText(/Δ 0\.40/)).toBeTruthy();
  });

  it('does not render anomaly row when verificationPacket absent', () => {
    const cell = makeCell();
    render(<MultiModalFusionCard selectedCell={cell} />);
    expect(screen.queryByText('ANOMALY')).toBeNull();
    expect(screen.queryByText('Consensus')).toBeNull();
  });

  it('renders permanent disclaimer', () => {
    const cell = makeCell();
    render(<MultiModalFusionCard selectedCell={cell} />);
    expect(screen.getByText(/decision-support only/i)).toBeTruthy();
  });

  it('renders watch state as warn-colored badge', () => {
    const cell = makeCell({
      verificationPacket: {
        anomaly_state: 'watch',
        residual_zscore: 1.6,
      },
    });
    render(<MultiModalFusionCard selectedCell={cell} />);
    expect(screen.getByText('WATCH')).toBeTruthy();
  });
});
