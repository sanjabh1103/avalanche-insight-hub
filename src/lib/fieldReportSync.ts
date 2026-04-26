import { supabase } from '@/integrations/supabase/client';
import type { QueuedFieldReport } from '@/lib/offlineFieldReports';

export async function submitQueuedFieldReport(report: QueuedFieldReport): Promise<void> {
  const { data: { user } } = await supabase.auth.getUser();
  const { data: created, error } = await supabase.from('field_reports').upsert({
    user_id: user?.id ?? report.userId,
    hazard_type: 'avalanche',
    review_status: 'pending',
    training_eligible: false,
    description: report.description,
    location: `SRID=4326;POINT(${report.lng} ${report.lat})` as unknown,
    client_report_id: report.clientReportId,
  }, {
    onConflict: 'client_report_id',
  }).select('id').maybeSingle();
  if (error) throw error;
  if (!created?.id) {
    throw new Error('Failed to create field report');
  }

  const { error: enrichmentError } = await supabase.functions.invoke('field-report-enrichment', {
    body: {
      fieldReportId: created.id,
      lat: report.lat,
      lng: report.lng,
      description: report.description,
      hazard_type: 'avalanche',
    },
  });
  if (enrichmentError) {
    throw enrichmentError;
  }
}
