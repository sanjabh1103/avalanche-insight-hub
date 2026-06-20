import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ExportForecast from '@/components/ExportForecast';
import type { GridCell } from '@/lib/gridUtils';

describe('ExportForecast', () => {
  const mockGrid = {
    cells: [
      {
        row: 0,
        col: 0,
        lat: 38.55,
        lng: -107.45,
        latEnd: 38.65,
        lngEnd: -107.35,
        riskScore: 3,
        hazard: 0.5,
        exposure: 0.4,
        vulnerability: 0.3,
        problemType: 'Wind Slab',
        shapValues: {
          snowfall_24h: 0.25,
          wind_speed: 0.15,
        },
        probability: 0.6,
        confidenceLower: 0.45,
        confidenceUpper: 0.75,
        uncertaintySpan: 0.3,
        uncertaintyClass: 'high' as const,
      } as GridCell,
    ],
    timestamp: '2026-06-20T12:00:00Z',
    bbox: [38.5, -107.5, 40.5, -105.5] as [number, number, number, number],
  };

  const mockGridWithCommas = {
    cells: [
      {
        ...mockGrid.cells[0],
        problemType: 'Persistent, Deep Slab',
      } as GridCell,
    ],
    timestamp: '2026-06-20T12:00:00Z',
    bbox: [38.5, -107.5, 40.5, -105.5] as [number, number, number, number],
  };

  beforeEach(() => {
    vi.restoreAllMocks();

    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    window.URL.revokeObjectURL = vi.fn();

    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tagName) => {
      const element = originalCreateElement(tagName);
      if (tagName === 'a') {
        vi.spyOn(element as HTMLAnchorElement, 'click').mockImplementation(() => {});
      }
      return element;
    });
  });

  it('renders disabled state when canExport is false', () => {
    render(
      <ExportForecast
        grid={mockGrid}
        canExport={false}
        regionName="Colorado Rockies"
        hour={72}
      />
    );

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toBeDisabled();
    expect(buttons[1]).toBeDisabled();
    expect(screen.getByText(/Artifact required for export/i)).toBeTruthy();
  });

  it('triggers CSV download when clicked and enabled', async () => {
    render(
      <ExportForecast
        grid={mockGrid}
        canExport={true}
        regionName="Colorado Rockies"
        hour={72}
      />
    );

    const csvButton = screen.getByRole('button', { name: /CSV/i });
    expect(csvButton).not.toBeDisabled();

    fireEvent.click(csvButton);

    expect(window.URL.createObjectURL).toHaveBeenCalled();
    const mockBlob = vi.mocked(window.URL.createObjectURL).mock.calls[0][0] as Blob;
    expect(mockBlob.type).toBe('text/csv');

    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsText(mockBlob);
    });

    expect(text).toContain('row,col,lat,lng,riskScore,probability,confidenceLower,confidenceUpper,uncertaintySpan,uncertaintyClass,hazard,exposure,vulnerability,problemType,snowfall_24h,wind_speed');
    expect(text).toContain('0,0,38.550000,-107.450000,3,0.600,0.450,0.750,0.300,high,0.500,0.400,0.300,Wind Slab,0.250,0.150');
  });

  it('triggers JSON download when clicked and enabled', async () => {
    render(
      <ExportForecast
        grid={mockGrid}
        canExport={true}
        regionName="Colorado Rockies"
        hour={72}
      />
    );

    const jsonButton = screen.getByRole('button', { name: /JSON/i });
    expect(jsonButton).not.toBeDisabled();

    fireEvent.click(jsonButton);

    expect(window.URL.createObjectURL).toHaveBeenCalled();
    const mockBlob = vi.mocked(window.URL.createObjectURL).mock.calls[0][0] as Blob;
    expect(mockBlob.type).toBe('application/json');

    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsText(mockBlob);
    });

    const data = JSON.parse(text);
    expect(data.metadata.region).toBe('Colorado Rockies');
    expect(data.metadata.hour).toBe(72);
    expect(data.grid[0].row).toBe(0);
    expect(data.grid[0].probability).toBe(0.6);
    expect(data.grid[0].uncertaintySpan).toBe(0.3);
  });

  it('RFC 4180 CSV quoting for fields containing commas', async () => {
    render(
      <ExportForecast
        grid={mockGridWithCommas}
        canExport={true}
        regionName="Colorado Rockies"
        hour={72}
      />
    );

    const csvButton = screen.getByRole('button', { name: /CSV/i });
    fireEvent.click(csvButton);

    const mockBlob = vi.mocked(window.URL.createObjectURL).mock.calls[0][0] as Blob;
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsText(mockBlob);
    });

    expect(text).toContain('"Persistent, Deep Slab"');
  });
});
