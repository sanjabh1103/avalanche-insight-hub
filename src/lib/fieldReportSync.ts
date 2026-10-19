import { supabase } from '@/integrations/supabase/client';
import {
  getAvalancheEventGovernanceLabel,
  parseAvalancheEventRow,
  type AvalancheEvent,
} from '@/lib/avalancheEvents';
import type { QueuedFieldReport } from '@/lib/offlineFieldReports';

export interface FieldReportSubmissionResult {
  event: AvalancheEvent;
  governanceLabel: string;
  promoted: boolean;
}

interface FieldReportSubmissionResponse {
  fieldReportId?: string;
}

export async function submitQueuedFieldReport(report: QueuedFieldReport): Promise<FieldReportSubmissionResult> {
  const { data: submissionResult, error: submissionError } = await supabase.functions.invoke('submit-field-report', {
    body: {
      lat: report.lat,
      lng: report.lng,
      description: report.description,
      timestamp: report.observedAt,
      clientReportId: report.clientReportId,
      locationName: report.locationName ?? null,
      submittedOffline: Boolean(report.submittedOffline),
    },
  });
  if (submissionError) throw submissionError;

  const fieldReportId = (submissionResult as FieldReportSubmissionResponse | null)?.fieldReportId;
  if (!fieldReportId) {
    throw new Error('Failed to create field report');
  }

  const { data: enrichmentResult, error: enrichmentError } = await supabase.functions.invoke('field-report-enrichment', {
    body: {
      fieldReportId,
      lat: report.lat,
      lng: report.lng,
      description: report.description,
      timestamp: report.observedAt,
      clientReportId: report.clientReportId,
      location_name: report.locationName ?? null,
      hazard_type: 'avalanche',
    },
  });
  if (enrichmentError) {
    throw enrichmentError;
  }

  const event = parseAvalancheEventRow((enrichmentResult as Record<string, unknown> | null)?.event as Record<string, unknown>);
  if (!event) {
    throw new Error('Field report was accepted but did not return a durable avalanche event');
  }

  const promotion = (enrichmentResult as Record<string, unknown> | null)?.promotion as Record<string, unknown> | null | undefined;
  return {
    event,
    governanceLabel: getAvalancheEventGovernanceLabel(event),
    promoted: Boolean(promotion?.promoted),
  };
}
