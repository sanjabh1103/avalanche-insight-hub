import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ContinuousVerificationDashboard from '@/components/ContinuousVerificationDashboard';

describe('ContinuousVerificationDashboard', () => {
  it('renders empty state when no data', () => {
    render(<ContinuousVerificationDashboard />);
    expect(screen.getByText('Continuous Verification Dashboard')).toBeTruthy();
    expect(screen.getByText(/No verification data available/i)).toBeTruthy();
  });

  it('renders an explicit unavailable state without inventing coverage', () => {
    render(
      <ContinuousVerificationDashboard
        status="unavailable"
        unavailableReason="verification_observations is unavailable until its migration is applied"
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(/unavailable/i);
    expect(screen.getByText(/No synthetic coverage is shown/i)).toBeTruthy();
  });

  it('renders metric cards with data', () => {
    const data = {
      coverage: {
        total_cells: 100,
        cells_with_3plus_sources: 75,
        cells_with_baselines: 80,
        cells_with_anomaly_state: 90,
      },
      stale_cells: {
        count: 5,
        top_stale: [
          { cell_id: 'cell_001', max_freshness_hours: 96.5 },
          { cell_id: 'cell_002', max_freshness_hours: 48.0 },
        ],
      },
      disagreement: {
        anomaly_count: 3,
        attribution_breakdown: { sensing_gap: 2, sensor_disagreement: 1 },
      },
      source_health: [
        { sensor: 'sar', avg_latency_hours: 12.5, gap_count: 1 },
        { sensor: 'optical', avg_latency_hours: 36.0, gap_count: 5 },
      ],
      model_drift: {
        calibration_drift: 0.05,
      },
      review_backlog: {
        pending_count: 8,
        oldest_pending_hours: 24.0,
      },
    };
    render(<ContinuousVerificationDashboard data={data} />);

    expect(screen.getByText('75%')).toBeTruthy();
    expect(screen.getByText('80%')).toBeTruthy();
    expect(screen.getByText('5')).toBeTruthy();
    expect(screen.getByText('cell_001')).toBeTruthy();
    expect(screen.getByText('96.5h')).toBeTruthy();
    expect(screen.getByText('sensing gap: 2')).toBeTruthy();
    expect(screen.getByText('sar')).toBeTruthy();
    expect(screen.getAllByText(/Decision-support only/i).length).toBeGreaterThan(0);
  });

  it('renders stale cells with danger variant for >72h', () => {
    const data = {
      stale_cells: {
        count: 2,
        top_stale: [{ cell_id: 'stale_cell', max_freshness_hours: 120.0 }],
      },
    };
    render(<ContinuousVerificationDashboard data={data} />);
    expect(screen.getByText('stale_cell')).toBeTruthy();
    expect(screen.getByText('120.0h')).toBeTruthy();
  });

  it('renders source health with gap warnings', () => {
    const data = {
      source_health: [
        { sensor: 'weather', avg_latency_hours: 3.0, gap_count: 0 },
        { sensor: 'gibs', avg_latency_hours: 48.0, gap_count: 7 },
      ],
    };
    render(<ContinuousVerificationDashboard data={data} />);
    expect(screen.getByText('weather')).toBeTruthy();
    expect(screen.getByText('gibs')).toBeTruthy();
    expect(screen.getByText('gaps: 7')).toBeTruthy();
  });

  it('renders truncation warning when truncatedTables is provided', () => {
    render(
      <ContinuousVerificationDashboard
        data={{}}
        truncatedTables={['verification_observations', 'verification_baselines']}
      />,
    );
    expect(screen.getByText(/Data may be incomplete/i)).toBeTruthy();
    expect(screen.getByText(/verification_observations/)).toBeTruthy();
    expect(screen.getByText(/verification_baselines/)).toBeTruthy();
  });

  it('does not render truncation warning when truncatedTables is empty', () => {
    render(<ContinuousVerificationDashboard data={{}} truncatedTables={[]} />);
    expect(screen.queryByText(/Data may be incomplete/i)).toBeNull();
  });
});
