import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { fieldReportId, lat, lng, description } = await req.json();
    if (!fieldReportId || !Number.isFinite(lat) || !Number.isFinite(lng)) {
      return new Response(JSON.stringify({ error: 'Invalid field report payload' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    const { data: job, error: jobErr } = await supabase
      .from('compute_jobs')
      .insert({
        type: 'field_report_enrichment',
        status: 'running',
        payload: { fieldReportId, lat, lng },
      })
      .select('id')
      .single();
    if (jobErr) throw jobErr;

    const ingestResponse = await fetch(`${Deno.env.get('SUPABASE_URL')}/functions/v1/ingest-event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')}`,
      },
      body: JSON.stringify({
        fieldReportId,
        lat,
        lng,
        description: description || 'Field report submitted',
        source: 'field_report',
        fusion_source: 'field_report_enrichment',
        event_type: 'unknown',
        severity: 3,
        confidence: 0.6,
        hazard_type: 'avalanche',
      }),
    });
    if (!ingestResponse.ok) {
      const text = await ingestResponse.text();
      throw new Error(`ingest-event failed (${ingestResponse.status}): ${text}`);
    }
    const ingestResult = await ingestResponse.json();

    await supabase.from('compute_jobs').update({
      status: 'completed',
      result: { fieldReportId, createdEvent: true, ingestResult },
    }).eq('id', job.id);

    return new Response(JSON.stringify({ ok: true, jobId: job.id }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
