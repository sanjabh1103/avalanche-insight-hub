import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import FieldReportForm from '@/components/FieldReportForm';
import type { AvalancheEvent } from '@/lib/avalancheEvents';

const {
  submitQueuedFieldReport,
  enqueueFieldReport,
  flushQueuedFieldReports,
  getUser,
} = vi.hoisted(() => ({
  submitQueuedFieldReport: vi.fn(),
  enqueueFieldReport: vi.fn(),
  flushQueuedFieldReports: vi.fn(async () => 0),
  getUser: vi.fn(async () => ({ data: { user: null } })),
}));

let mapHandlers: { click?: (event: { latlng: { lat: number; lng: number } }) => void } = {};

vi.mock('@/lib/fieldReportSync', () => ({
  submitQueuedFieldReport,
}));

vi.mock('@/lib/offlineFieldReports', () => ({
  enqueueFieldReport,
  flushQueuedFieldReports,
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getUser,
    },
  },
}));

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="mock-map">{children}</div>,
  TileLayer: () => null,
  Rectangle: () => null,
  CircleMarker: () => null,
  useMapEvents: (handlers: typeof mapHandlers) => {
    mapHandlers = handlers;
    return {};
  },
}));

describe('FieldReportForm', () => {
  beforeEach(() => {
    submitQueuedFieldReport.mockReset();
    enqueueFieldReport.mockReset();
    flushQueuedFieldReports.mockClear();
    getUser.mockClear();
    mapHandlers = {};
    Object.defineProperty(window.navigator, 'onLine', {
      configurable: true,
      value: true,
    });
    Object.defineProperty(window.navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn((success: (position: { coords: { latitude: number; longitude: number } }) => void) => {
          success({ coords: { latitude: 27.9881, longitude: 86.925 } });
        }),
      },
    });
  });

  it('defaults the observed time, supports geolocation and map clicks, and submits optimistic plus durable events', async () => {
    const submitted: AvalancheEvent[] = [];
    submitQueuedFieldReport.mockResolvedValue({
      event: {
        id: 'event-1',
        lat: 27.99,
        lng: 86.92,
        severity: 3,
        confidence: 0.82,
        description: 'Observed crown line below Camp II',
        source: 'field_report',
        event_type: 'unknown',
        timestamp: '2026-05-02T04:30:00.000Z',
        location_name: 'Himalayas (Nepal)',
        clientReportId: 'field-durable',
        verificationStatus: 'unverified',
      },
      governanceLabel: 'Pending corroboration',
      promoted: false,
    });

    render(
      <FieldReportForm
        open
        onClose={() => undefined}
        onSubmitted={(event) => submitted.push(event)}
        regionCenter={[27.98, 86.92]}
        regionBbox={[27.8, 86.7, 28.1, 87.1]}
        regionName="Himalayas (Nepal)"
      />,
    );

    const observedTimeInput = screen.getByLabelText('Observation time') as HTMLInputElement;
    expect(observedTimeInput.value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);

    fireEvent.click(screen.getByRole('button', { name: /use my location/i }));
    expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('27.988100');
    expect((screen.getByLabelText('Longitude') as HTMLInputElement).value).toBe('86.925000');

    act(() => {
      mapHandlers.click?.({ latlng: { lat: 28.001234, lng: 86.912345 } });
    });
    expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('28.001234');
    expect((screen.getByLabelText('Longitude') as HTMLInputElement).value).toBe('86.912345');

    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'Observed crown line below Camp II' },
    });
    fireEvent.change(observedTimeInput, {
      target: { value: '2026-05-02T10:00' },
    });

    fireEvent.click(screen.getByRole('button', { name: /submit report/i }));

    await waitFor(() => {
      expect(submitQueuedFieldReport).toHaveBeenCalledTimes(1);
    });

    const queuedReport = submitQueuedFieldReport.mock.calls[0][0];
    expect(queuedReport.clientReportId).toMatch(/^field-/);
    expect(queuedReport.observedAt).toBe(new Date('2026-05-02T10:00').toISOString());
    expect(queuedReport.locationName).toBe('Himalayas (Nepal)');

    expect(submitted).toHaveLength(2);
    expect(submitted[0].optimistic).toBe(true);
    expect(submitted[0].clientReportId).toMatch(/^field-/);
    expect(submitted[1].id).toBe('event-1');
  }, 30_000);

  it('queues reports locally while offline for tablet field use', async () => {
    Object.defineProperty(window.navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    const submitted: AvalancheEvent[] = [];

    render(
      <FieldReportForm
        open
        onClose={() => undefined}
        onSubmitted={(event) => submitted.push(event)}
        regionCenter={[27.98, 86.92]}
        regionBbox={[27.8, 86.7, 28.1, 87.1]}
        regionName="Himalayas (Nepal)"
      />,
    );

    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'Offline tablet observation near test slope' },
    });
    fireEvent.click(screen.getByRole('button', { name: /submit report/i }));

    await waitFor(() => {
      expect(enqueueFieldReport).toHaveBeenCalledTimes(1);
    });
    expect(submitQueuedFieldReport).not.toHaveBeenCalled();
    expect(enqueueFieldReport.mock.calls[0][0]).toMatchObject({
      submittedOffline: true,
      locationName: 'Himalayas (Nepal)',
    });
    expect(submitted[0].optimistic).toBe(true);
  });
});
