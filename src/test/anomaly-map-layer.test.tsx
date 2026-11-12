import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AnomalyMapLayer from '@/components/AnomalyMapLayer';
import type { GridCell } from '@/lib/gridUtils';

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

describe('AnomalyMapLayer', () => {
  it('renders null when no cells and not visible', () => {
    const cells: GridCell[] = [];
    const { container } = render(
      <AnomalyMapLayer cells={cells} visible={false} onToggle={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('counts cells without verification packet as unverified', () => {
    const cells = [makeCell()];
    render(<AnomalyMapLayer cells={cells} visible={true} onToggle={vi.fn()} />);
    expect(screen.getByText(/1 Unverified/i)).toBeTruthy();
  });

  it('renders anomaly count badges when anomalies exist', () => {
    const cells = [
      makeCell({
        verificationPacket: {
          anomaly_state: 'anomaly',
          attribution_bucket: 'forcing_error',
        },
      }),
      makeCell({
        verificationPacket: {
          anomaly_state: 'watch',
          attribution_bucket: 'sensing_gap',
        },
      }),
      makeCell({
        verificationPacket: {
          anomaly_state: 'normal',
        },
      }),
    ];
    render(<AnomalyMapLayer cells={cells} visible={true} onToggle={vi.fn()} />);
    expect(screen.getByText(/1 Anomaly/i)).toBeTruthy();
    expect(screen.getByText(/1 Watch/i)).toBeTruthy();
    expect(screen.getByText(/1 Normal/i)).toBeTruthy();
  });

  it('shows attribution breakdown', () => {
    const cells = [
      makeCell({
        verificationPacket: {
          anomaly_state: 'anomaly',
          attribution_bucket: 'forcing_error',
        },
      }),
      makeCell({
        verificationPacket: {
          anomaly_state: 'anomaly',
          attribution_bucket: 'sensing_gap',
        },
      }),
    ];
    render(<AnomalyMapLayer cells={cells} visible={true} onToggle={vi.fn()} />);
    expect(screen.getByText('Forcing Error')).toBeTruthy();
    expect(screen.getByText('Sensing Gap')).toBeTruthy();
  });

  it('calls onToggle when hide button is clicked', () => {
    const onToggle = vi.fn();
    const cells = [
      makeCell({
        verificationPacket: { anomaly_state: 'anomaly' },
      }),
    ];
    render(<AnomalyMapLayer cells={cells} visible={true} onToggle={onToggle} />);
    const hideButton = screen.getByText('Hide');
    fireEvent.click(hideButton);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('shows decision-support disclaimer', () => {
    const cells = [
      makeCell({
        verificationPacket: { anomaly_state: 'anomaly' },
      }),
    ];
    render(<AnomalyMapLayer cells={cells} visible={true} onToggle={vi.fn()} />);
    expect(screen.getByText(/decision-support only/i)).toBeTruthy();
  });
});
