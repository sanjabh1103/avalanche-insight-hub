import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
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

    const { error: eventErr } = await supabase.from('avalanche_events').insert({
      source: 'field_report',
      description: description || 'Field report submitted',
      severity: 3,
      event_type: 'unknown',
      location: `SRID=4326;POINT(${lng} ${lat})`,
      confidence: 0.6,
      fusion_source: 'field_report_enrichment',
    });
    if (eventErr) throw eventErr;

    await supabase.from('compute_jobs').update({
      status: 'completed',
      result: { fieldReportId, createdEvent: true },
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
