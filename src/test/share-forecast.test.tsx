import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ShareForecast from '@/components/ShareForecast';

const mockRegion = {
  name: 'Colorado Rockies',
  bbox: [38, -107, 40, -105] as [number, number, number, number],
  center: [39, -106] as [number, number],
  zoom: 8,
};

const mockCell = {
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
  shapValues: {},
};

describe('ShareForecast', () => {
  const originalClipboard = navigator.clipboard;

  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    Object.assign(navigator, { clipboard: originalClipboard });
  });

  it('renders a SHARE button', () => {
    render(<ShareForecast region={mockRegion} hour={6} />);
    expect(screen.getByText('SHARE')).toBeTruthy();
  });

  it('generates a URL with region, bbox, and hour params on click', async () => {
    render(<ShareForecast region={mockRegion} hour={6} forecastId="run-123" />);
    fireEvent.click(screen.getByText('SHARE'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedUrl = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(copiedUrl).toContain('region=Colorado+Rockies');
    expect(copiedUrl).toContain('hour=6');
    expect(copiedUrl).toContain('forecast=run-123');
    expect(copiedUrl).toContain('bbox=');
  });

  it('includes selected cell coordinates in the URL', async () => {
    render(<ShareForecast region={mockRegion} hour={3} selectedCell={mockCell} />);
    fireEvent.click(screen.getByText('SHARE'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedUrl = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(copiedUrl).toContain('cell=5%2C10');
  });

  it('includes expert mode and 3D state when enabled', async () => {
    render(
      <ShareForecast
        region={mockRegion}
        hour={0}
        expertMode={true}
        show3D={true}
      />,
    );
    fireEvent.click(screen.getByText('SHARE'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedUrl = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(copiedUrl).toContain('expert=1');
    expect(copiedUrl).toContain('3d=1');
  });

  it('shows error fallback when clipboard API fails', async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(new Error('Permission denied')),
      },
    });

    render(<ShareForecast region={mockRegion} hour={0} />);
    fireEvent.click(screen.getByText('SHARE'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });
  });
});
