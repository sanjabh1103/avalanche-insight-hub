import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// P1.3: Admin-invoked promotion endpoint. Calls the promote_event_verification
// RPC which refuses downgrades and writes an audit trail into
// avalanche_events.features->verification_promotion.

const ALLOWED_TARGETS = new Set(['weak', 'verified', 'expert_verified']);

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const body = await req.json();
    const eventId: string | undefined = body?.event_id ?? body?.eventId;
    const target: string = String(body?.target_status ?? body?.targetStatus ?? 'verified');
    const promoter: string = String(body?.promoter ?? 'admin:manual');
    const reason: string | undefined = body?.reason;

    if (!eventId || typeof eventId !== 'string') {
      return new Response(JSON.stringify({ error: 'event_id is required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    if (!ALLOWED_TARGETS.has(target)) {
      return new Response(JSON.stringify({ error: `target_status must be one of ${Array.from(ALLOWED_TARGETS).join(', ')}` }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    if (!supabaseUrl || !serviceRoleKey) {
      return new Response(JSON.stringify({ error: 'Server misconfigured: missing Supabase credentials' }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    const supabase = createClient(supabaseUrl, serviceRoleKey);

    const { data, error } = await (supabase as any).rpc('promote_event_verification', {
      p_event_id: eventId,
      p_new_status: target,
      p_promoter: promoter,
      p_reason: reason ?? null,
    });
    if (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      ok: true,
      event_id: eventId,
      promotion: Array.isArray(data) && data.length > 0 ? data[0] : null,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
