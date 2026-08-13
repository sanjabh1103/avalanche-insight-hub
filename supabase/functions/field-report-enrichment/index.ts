import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { extractBearerToken } from "../_shared/auth.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

export async function handleFieldReportEnrichment(req: Request) {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { fieldReportId, lat, lng, description, timestamp, clientReportId, location_name } = await req.json();
    if (!fieldReportId || !Number.isFinite(lat) || !Number.isFinite(lng)) {
      return new Response(JSON.stringify({ error: 'Invalid field report payload' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    if (!serviceRoleKey) {
      throw new Error('Missing SUPABASE_SERVICE_ROLE_KEY');
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      serviceRoleKey,
    );

    // Load the field report to verify ownership
    const { data: fieldReport, error: frErr } = await supabase
      .from('field_reports')
      .select('user_id')
      .eq('id', fieldReportId)
      .maybeSingle();

    if (frErr || !fieldReport) {
      return new Response(JSON.stringify({ error: 'Field report not found' }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Ownership validation check
    const requireJobAuth = Deno.env.get("REQUIRE_JOB_AUTH");
    const enforceAuth = requireJobAuth !== "false" && requireJobAuth !== "0" && requireJobAuth !== "off" && requireJobAuth !== "no";

    if (enforceAuth) {
      const authHeader = req.headers.get("authorization");
      const token = extractBearerToken(authHeader);

      if (token) {
        // Logged-in user
        const { data: authData, error: authErr } = await supabase.auth.getUser(token);
        if (authErr || !authData?.user) {
          return new Response(JSON.stringify({ error: 'Invalid user session' }), {
            status: 401,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        }
        if (fieldReport.user_id !== authData.user.id) {
          return new Response(JSON.stringify({ error: 'Access denied: report does not belong to user' }), {
            status: 403,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        }
      } else {
        // Anonymous submission
        if (fieldReport.user_id !== null) {
          return new Response(JSON.stringify({ error: 'Access denied: login required to enrich this report' }), {
            status: 403,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          });
        }
      }
    }

    const { data: job, error: jobErr } = await supabase
      .from('compute_jobs')
      .insert({
        type: 'field_report_enrichment',
        status: 'running',
        payload: { fieldReportId, lat, lng, timestamp, clientReportId },
      })
      .select('id')
      .maybeSingle();
    if (jobErr) throw jobErr;
    if (!job?.id) throw new Error('Failed to create compute_job row');

    const publicFunctionKey = Deno.env.get('SUPABASE_ANON_KEY') ?? serviceRoleKey;
    const systemToken = Deno.env.get('JOB_DISPATCH_TOKEN') || serviceRoleKey;

    const ingestResponse = await fetch(`${Deno.env.get('SUPABASE_URL')}/functions/v1/ingest-event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${systemToken}`,
        apikey: publicFunctionKey,
      },
      body: JSON.stringify({
        fieldReportId,
        lat,
        lng,
        description: description || 'Field report submitted',
        timestamp: timestamp || new Date().toISOString(),
        clientReportId: clientReportId || null,
        location_name: location_name || null,
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
    let createdEvent = (ingestResult as Record<string, unknown>)?.event as Record<string, unknown> | undefined;

    // P1.3: Auto-promote the newly-created event to verification_status='weak'
    // when a SAR or news event corroborates it within 48h and 5km. This is
    // how the training corpus gets populated with higher-quality rows than
    // the default 'unverified' citizen reports.
    let promotion: Record<string, unknown> | null = null;
    const newEventId: string | undefined = typeof createdEvent?.id === 'string'
      ? createdEvent.id
      : (ingestResult as Record<string, unknown>)?.event_id as string | undefined
        || (ingestResult as Record<string, unknown>)?.id as string | undefined
        || (ingestResult as Record<string, unknown>)?.avalanche_event_id as string | undefined;

    if (newEventId) {
      try {
        const { data: match } = await (supabase as any).rpc('match_corroborating_event', {
          p_event_id: newEventId,
          p_lat: lat,
          p_lng: lng,
          p_timestamp: timestamp || new Date().toISOString(),
          p_radius_m: 5000,
          p_window_hours: 48,
        });
        if (Array.isArray(match) && match.length > 0) {
          const hit = match[0] as Record<string, unknown>;
          const { data: promoted } = await (supabase as any).rpc('promote_event_verification', {
            p_event_id: newEventId,
            p_new_status: 'weak',
            p_promoter: 'auto:field_report_enrichment',
            p_reason: `corroborated by ${hit.source} at ${Math.round(Number(hit.distance_m ?? 0))}m / ${Number(hit.hours_delta ?? 0).toFixed(1)}h`,
          });
          promotion = {
            matched_event_id: hit.matched_event_id,
            matched_source: hit.source,
            distance_m: hit.distance_m,
            hours_delta: hit.hours_delta,
            promoted: Array.isArray(promoted) && promoted.length > 0 ? promoted[0] : null,
          };
        }
      } catch (promoteErr) {
        // Best-effort only; a promotion failure must not fail the whole ingest.
        console.warn('auto-promotion skipped:', (promoteErr as Error).message);
      }

      try {
        const { data: refreshedEvent } = await supabase
          .from('avalanche_events')
          .select('id, timestamp, source, description, severity, event_type, confidence, label_confidence, training_weight, verification_status, label_role, location, features')
          .eq('id', newEventId)
          .maybeSingle();
        if (refreshedEvent) {
          createdEvent = refreshedEvent as Record<string, unknown>;
        }
      } catch (refreshErr) {
        console.warn('event refresh skipped:', (refreshErr as Error).message);
      }
    }

    await supabase.from('compute_jobs').update({
      status: 'completed',
      result: { fieldReportId, createdEvent: true, ingestResult, promotion },
    }).eq('id', job!.id);

    return new Response(JSON.stringify({ ok: true, jobId: job!.id, event: createdEvent, promotion }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
}

if (import.meta.main) {
  serve(handleFieldReportEnrichment);
}
