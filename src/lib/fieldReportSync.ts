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

export async function submitQueuedFieldReport(report: QueuedFieldReport): Promise<FieldReportSubmissionResult> {
  const { data: { user } } = await supabase.auth.getUser();
  const { data: created, error } = await supabase.from('field_reports').insert({
    user_id: user?.id ?? report.userId,
    hazard_type: 'avalanche',
    review_status: 'pending',
    training_eligible: false,
    description: report.description,
    location: `SRID=4326;POINT(${report.lng} ${report.lat})` as unknown,
    timestamp: report.observedAt,
    client_report_id: report.clientReportId,
    sync_status: 'synced',
    submitted_offline: Boolean(report.submittedOffline),
    synced_at: new Date().toISOString(),
  }).select('id').maybeSingle();
  if (error) throw error;
  if (!created?.id) {
    throw new Error('Failed to create field report');
  }

  const { data: enrichmentResult, error: enrichmentError } = await supabase.functions.invoke('field-report-enrichment', {
    body: {
      fieldReportId: created.id,
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
