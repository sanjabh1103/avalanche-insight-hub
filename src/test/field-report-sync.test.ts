import { beforeEach, describe, expect, it, vi } from 'vitest';

import { submitQueuedFieldReport } from '@/lib/fieldReportSync';
import type { QueuedFieldReport } from '@/lib/offlineFieldReports';

const { invoke } = vi.hoisted(() => ({
  invoke: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    functions: {
      invoke,
    },
  },
}));

describe('submitQueuedFieldReport', () => {
  beforeEach(() => {
    invoke.mockReset();
  });

  it('submits through the rate-limited Edge Function before enrichment', async () => {
    const report: QueuedFieldReport = {
      id: 'field-client-1',
      clientReportId: 'field-client-1',
      lat: 28.001,
      lng: 86.912,
      description: 'Observed slab crown line near route',
      observedAt: '2026-05-02T04:30:00.000Z',
      locationName: 'Himalayas (Nepal)',
      submittedOffline: false,
      createdAt: '2026-05-02T04:31:00.000Z',
      userId: null,
    };

    invoke.mockImplementation(async (functionName: string) => {
      if (functionName === 'submit-field-report') {
        return { data: { fieldReportId: 'field-report-1' }, error: null };
      }
      if (functionName === 'field-report-enrichment') {
        return {
          data: {
            event: {
              id: 'event-1',
              location: 'POINT(86.912 28.001)',
              severity: 3,
              confidence: 0.6,
              label_confidence: 0.6,
              description: report.description,
              source: 'field_report',
              fusion_source: 'field_report_enrichment',
              event_type: 'unknown',
              timestamp: report.observedAt,
              verification_status: 'unverified',
              features: {
                field_report_id: 'field-report-1',
                client_report_id: report.clientReportId,
                location_name: report.locationName,
              },
            },
            promotion: { promoted: false },
          },
          error: null,
        };
      }
      return { data: null, error: new Error(`Unexpected function ${functionName}`) };
    });

    const result = await submitQueuedFieldReport(report);

    expect(invoke).toHaveBeenNthCalledWith(1, 'submit-field-report', {
      body: {
        lat: report.lat,
        lng: report.lng,
        description: report.description,
        timestamp: report.observedAt,
        clientReportId: report.clientReportId,
        locationName: report.locationName,
        submittedOffline: false,
      },
    });
    expect(invoke).toHaveBeenNthCalledWith(2, 'field-report-enrichment', expect.objectContaining({
      body: expect.objectContaining({ fieldReportId: 'field-report-1' }),
    }));
    expect(result.event.id).toBe('event-1');
    expect(result.governanceLabel).toBe('Pending corroboration');
    expect(result.promoted).toBe(false);
  });
});
