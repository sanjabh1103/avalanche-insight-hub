import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import BaselineTimeseriesChart from '@/components/BaselineTimeseriesChart';

describe('BaselineTimeseriesChart', () => {
  it('renders collapsed with point count when not expanded', () => {
    const points = [
      { date: '2026-01-10', p50: 1.1, observed: 1.2, anomaly_state: 'normal' },
      { date: '2026-01-11', p50: 1.15, observed: 1.5, anomaly_state: 'watch' },
    ];
    render(<BaselineTimeseriesChart points={points} sensor="weather" />);
    expect(screen.getByText(/Baseline History/i)).toBeTruthy();
    expect(screen.getByText(/2 data points available/i)).toBeTruthy();
  });

  it('renders SVG chart when expanded with data', () => {
    const points = [
      { date: '2026-01-10', p25: 0.9, p50: 1.1, p75: 1.3, observed: 1.2, anomaly_state: 'normal' },
      { date: '2026-01-11', p25: 0.95, p50: 1.15, p75: 1.35, observed: 1.5, anomaly_state: 'watch' },
      { date: '2026-01-12', p25: 1.0, p50: 1.2, p75: 1.4, observed: 0.8, anomaly_state: 'anomaly' },
    ];
    render(<BaselineTimeseriesChart points={points} sensor="weather" defaultExpanded={true} />);
    expect(screen.getByRole('img', { name: /baseline time-series chart/i })).toBeTruthy();
    expect(screen.getByText('2026-01-10')).toBeTruthy();
    expect(screen.getByText('2026-01-12')).toBeTruthy();
    expect(screen.getByText(/Decision-support only/i)).toBeTruthy();
  });

  it('renders empty message when no data', () => {
    render(<BaselineTimeseriesChart points={[]} defaultExpanded={true} />);
    expect(screen.getByText(/No baseline time-series data/i)).toBeTruthy();
  });

  it('renders empty message when points have no numeric values', () => {
    const points = [
      { date: '2026-01-10', p50: null, observed: null },
    ];
    render(<BaselineTimeseriesChart points={points} defaultExpanded={true} />);
    expect(screen.getByText(/No baseline time-series data/i)).toBeTruthy();
  });
});
