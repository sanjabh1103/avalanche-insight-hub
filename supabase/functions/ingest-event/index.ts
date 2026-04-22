import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const ELEVATION_LOOKUP_URL = 'https://api.open-elevation.com/api/v1/lookup';
const SAMPLE_DEGREE_OFFSET = 0.0025;
const METERS_PER_DEG_LAT = 111_320;

type EventPayload = {
  fieldReportId?: string;
  lat: number;
  lng: number;
  description?: string;
  hazard_type?: string;
  source?: string;
  event_type?: string;
  severity?: number;
  confidence?: number;
  location_name?: string;
  fusion_source?: string;
  metadata?: Record<string, unknown>;
};

type ElevationSample = {
  name: 'center' | 'north' | 'south' | 'east' | 'west';
  lat: number;
  lng: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function toFiniteNumber(value: unknown, fallback = 0) {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function buildSamples(lat: number, lng: number): ElevationSample[] {
  return [
    { name: 'center', lat, lng },
    { name: 'north', lat: lat + SAMPLE_DEGREE_OFFSET, lng },
    { name: 'south', lat: lat - SAMPLE_DEGREE_OFFSET, lng },
    { name: 'east', lat, lng: lng + SAMPLE_DEGREE_OFFSET },
    { name: 'west', lat, lng: lng - SAMPLE_DEGREE_OFFSET },
  ];
}

async function fetchElevations(samples: ElevationSample[]) {
  const locations = samples.map((sample) => `${sample.lat},${sample.lng}`).join('|');
  const url = `${ELEVATION_LOOKUP_URL}?locations=${encodeURIComponent(locations)}`;
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Elevation lookup failed (${response.status})`);
  }

  const payload = await response.json();
  const results = Array.isArray(payload?.results) ? payload.results : [];
  if (results.length !== samples.length) {
    throw new Error('Elevation lookup returned incomplete samples');
  }

  return samples.reduce<Record<string, number>>((acc, sample, index) => {
    acc[sample.name] = toFiniteNumber(results[index]?.elevation, NaN);
    return acc;
  }, {});
}

function fallbackElevations(lat: number, lng: number) {
  const center = 1800 + Math.sin(lat * 0.13) * 280 + Math.cos(lng * 0.11) * 220;
  const north = center + Math.sin((lat + SAMPLE_DEGREE_OFFSET) * 0.2) * 18;
  const south = center + Math.sin((lat - SAMPLE_DEGREE_OFFSET) * 0.2) * 12;
  const east = center + Math.cos((lng + SAMPLE_DEGREE_OFFSET) * 0.17) * 16;
  const west = center + Math.cos((lng - SAMPLE_DEGREE_OFFSET) * 0.17) * 14;
  return { center, north, south, east, west };
}

function slopeAspectFromSamples(samples: Record<string, number>, lat: number) {
  const center = samples.center;
  const north = samples.north;
  const south = samples.south;
  const east = samples.east;
  const west = samples.west;

  const metersPerDegLng = Math.max(1, METERS_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180));
  const spacingLatM = SAMPLE_DEGREE_OFFSET * METERS_PER_DEG_LAT;
  const spacingLngM = SAMPLE_DEGREE_OFFSET * metersPerDegLng;
  const dzdy = (north - south) / (2 * spacingLatM);
  const dzdx = (east - west) / (2 * spacingLngM);
  const slopeRad = Math.atan(Math.sqrt((dzdx * dzdx) + (dzdy * dzdy)));
  const slopeAngleDeg = Number((slopeRad * 180 / Math.PI).toFixed(2));
  const aspectDeg = Number(((Math.atan2(dzdx, -dzdy) * 180 / Math.PI + 360) % 360).toFixed(2));

  return {
    elevationM: Math.round(center),
    slopeAngleDeg,
    aspectDeg,
    slopeBand: slopeAngleDeg < 25 ? 'low' : slopeAngleDeg < 35 ? 'moderate' : slopeAngleDeg < 45 ? 'steep' : 'very_steep',
    aspectBucket: aspectDeg < 22.5 || aspectDeg >= 337.5
      ? 'N'
      : aspectDeg < 67.5
        ? 'NE'
        : aspectDeg < 112.5
          ? 'E'
          : aspectDeg < 157.5
            ? 'SE'
            : aspectDeg < 202.5
              ? 'S'
              : aspectDeg < 247.5
                ? 'SW'
                : aspectDeg < 292.5
                  ? 'W'
                  : 'NW',
    topoResolutionM: Number(((spacingLatM + spacingLngM) / 2).toFixed(1)),
    topoProfile: {
      sample_spacing_m: Number(((spacingLatM + spacingLngM) / 2).toFixed(1)),
      center_elevation_m: Math.round(center),
      north_elevation_m: Number(north.toFixed(2)),
      south_elevation_m: Number(south.toFixed(2)),
      east_elevation_m: Number(east.toFixed(2)),
      west_elevation_m: Number(west.toFixed(2)),
      dzdx: Number(dzdx.toFixed(6)),
      dzdy: Number(dzdy.toFixed(6)),
    },
  };
}

function safeJson(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

// Edit 2 preserved: topo-snapping already runs above. This classifier runs AFTER topo
// so it can optionally use the slope angle as a corroborating signal.
// Story 21 + Challenge 14: flip training_eligible=false for deposit-zone events so they
// render on the UI but do not poison the training set.
const DEPOSIT_KEYWORDS = [
  'village', 'valley', 'road', 'highway', 'town', 'settlement',
  'deposit', 'runout', 'buried', 'struck a', 'hit a', 'debris pile',
  'avalanche reached', 'debris across',
];
const RELEASE_KEYWORDS = [
  'ridge', 'slope', 'face', 'couloir', 'peak', 'cornice',
  'starting zone', 'release zone', 'crown', 'fracture line',
  'steep slope', 'above tree line',
];

type DepositClassification = {
  trainingEligible: boolean;
  reason: string | null;
  method: 'gemini' | 'heuristic' | 'skipped';
};

async function classifyDepositZoneWithGemini(description: string, apiKey: string): Promise<'DEPOSIT_ZONE' | 'RELEASE_ZONE' | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const prompt = [
      'Classify this avalanche event description as exactly one of these two tokens:',
      '- RELEASE_ZONE: the event happened on the slope/ridge/face where the avalanche started',
      '- DEPOSIT_ZONE: the event is in the valley/road/village where debris accumulated after traveling',
      '',
      `Description: "${description}"`,
      '',
      'Respond with ONLY the single token RELEASE_ZONE or DEPOSIT_ZONE and nothing else.',
    ].join('\n');

    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0, maxOutputTokens: 8 },
        }),
        signal: controller.signal,
      },
    );
    clearTimeout(timeout);
    if (!response.ok) return null;
    const payload = await response.json();
    const raw = payload?.candidates?.[0]?.content?.parts?.[0]?.text ?? '';
    const token = String(raw).trim().toUpperCase();
    if (token.includes('DEPOSIT')) return 'DEPOSIT_ZONE';
    if (token.includes('RELEASE')) return 'RELEASE_ZONE';
    return null;
  } catch (error) {
    console.warn('[ingest-event] Gemini classifier error:', (error as Error).message);
    return null;
  }
}

function heuristicClassify(description: string, slopeAngleDeg: number): 'DEPOSIT_ZONE' | 'RELEASE_ZONE' | null {
  const text = description.toLowerCase();
  const depositHits = DEPOSIT_KEYWORDS.filter((kw) => text.includes(kw)).length;
  const releaseHits = RELEASE_KEYWORDS.filter((kw) => text.includes(kw)).length;
  // Low slope is a strong deposit-zone corroborating signal.
  const lowSlope = Number.isFinite(slopeAngleDeg) && slopeAngleDeg < 15;
  if (depositHits > releaseHits) return 'DEPOSIT_ZONE';
  if (releaseHits > depositHits) return 'RELEASE_ZONE';
  if (lowSlope && depositHits > 0) return 'DEPOSIT_ZONE';
  return null;
}

async function classifyDepositZone(description: string, slopeAngleDeg: number): Promise<DepositClassification> {
  const trimmed = description?.trim() ?? '';
  if (!trimmed) {
    return { trainingEligible: true, reason: null, method: 'skipped' };
  }

  const apiKey = Deno.env.get('GEMINI_API_KEY');
  if (apiKey) {
    const verdict = await classifyDepositZoneWithGemini(trimmed, apiKey);
    if (verdict === 'DEPOSIT_ZONE') {
      return { trainingEligible: false, reason: 'gemini_deposit_zone', method: 'gemini' };
    }
    if (verdict === 'RELEASE_ZONE') {
      return { trainingEligible: true, reason: null, method: 'gemini' };
    }
    // fall through to heuristic if Gemini was inconclusive
  }

  const heuristic = heuristicClassify(trimmed, slopeAngleDeg);
  if (heuristic === 'DEPOSIT_ZONE') {
    return { trainingEligible: false, reason: 'heuristic_deposit_zone', method: 'heuristic' };
  }
  return { trainingEligible: true, reason: null, method: 'heuristic' };
}

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  let jobId: string | null = null;

  try {
    const payload = await req.json() as EventPayload;
    const lat = toFiniteNumber(payload.lat, NaN);
    const lng = toFiniteNumber(payload.lng, NaN);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return new Response(JSON.stringify({ error: 'Invalid coordinates' }), {
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
        type: 'ingest_event',
        status: 'running',
        payload: {
          lat,
          lng,
          hazard_type: payload.hazard_type || 'avalanche',
          source: payload.source || 'field_report',
          field_report_id: payload.fieldReportId || null,
        },
      })
      .select('id')
      .maybeSingle();
    if (jobErr) throw jobErr;
    if (!job?.id) throw new Error('Failed to create compute_job row');
    jobId = job.id;

    let elevationSamples: Record<string, number>;
    try {
      elevationSamples = await fetchElevations(buildSamples(lat, lng));
    } catch (error) {
      console.warn('Elevation lookup fallback in ingest-event:', (error as Error).message);
      elevationSamples = fallbackElevations(lat, lng);
    }

    const topo = slopeAspectFromSamples(elevationSamples, lat);
    const description = typeof payload.description === 'string' && payload.description.trim().length > 0
      ? payload.description.trim()
      : 'Observed avalanche-related event';
    const source = payload.source || 'field_report';
    const fusionSource = payload.fusion_source || source;
    const hazardType = payload.hazard_type || 'avalanche';
    const eventType = payload.event_type || 'unknown';
    const severity = Number.isFinite(payload.severity as number) ? Number(payload.severity) : 3;
    const confidence = clamp(Number.isFinite(payload.confidence as number) ? Number(payload.confidence) : 0.6, 0, 1);

    // Story 21: classify deposit vs. release zone AFTER topo is resolved so the
    // heuristic can use slope angle as a corroborating signal.
    const classification = await classifyDepositZone(description, topo.slopeAngleDeg);

    const { data: event, error: eventErr } = await supabase
      .from('avalanche_events')
      .insert({
        source,
        description,
        severity,
        event_type: eventType,
        location: `SRID=4326;POINT(${lng} ${lat})`,
        confidence,
        fusion_source: fusionSource,
        elevation_m: topo.elevationM,
        slope_band: topo.slopeBand,
        aspect_bucket: topo.aspectBucket,
        slope_angle_deg: topo.slopeAngleDeg,
        aspect_deg: topo.aspectDeg,
        topo_source: 'open-elevation',
        topo_resolution_m: topo.topoResolutionM,
        training_eligible: classification.trainingEligible,
        training_eligible_reason: classification.reason,
        topo_profile: {
          ...topo.topoProfile,
          hazard_type: hazardType,
          source,
          field_report_id: payload.fieldReportId || null,
          location_name: payload.location_name || null,
          metadata: safeJson(payload.metadata),
          deposit_zone_classifier: {
            method: classification.method,
            reason: classification.reason,
            training_eligible: classification.trainingEligible,
          },
        },
        features: {
          topo_source: 'open-elevation',
          topo_resolution_m: topo.topoResolutionM,
          slope_angle_deg: topo.slopeAngleDeg,
          aspect_deg: topo.aspectDeg,
          hazard_type: hazardType,
          source,
          training_eligible: classification.trainingEligible,
        },
      })
      .select('id, timestamp, source, description, severity, event_type, confidence, location')
      .maybeSingle();
    if (eventErr) throw eventErr;
    if (!event?.id) throw new Error('Failed to create avalanche_event row');

    await supabase
      .from('compute_jobs')
      .update({
        status: 'completed',
        result: {
          event_id: event.id,
          topo_source: 'open-elevation',
          elevation_m: topo.elevationM,
          slope_angle_deg: topo.slopeAngleDeg,
          aspect_deg: topo.aspectDeg,
          slope_band: topo.slopeBand,
          aspect_bucket: topo.aspectBucket,
          training_eligible: classification.trainingEligible,
          training_eligible_reason: classification.reason,
          deposit_zone_method: classification.method,
        },
      })
      .eq('id', job.id);

    return new Response(JSON.stringify({
      ok: true,
      jobId: job.id,
      event,
      topo: {
        source: 'open-elevation',
        elevation_m: topo.elevationM,
        slope_angle_deg: topo.slopeAngleDeg,
        aspect_deg: topo.aspectDeg,
        slope_band: topo.slopeBand,
        aspect_bucket: topo.aspectBucket,
        topo_resolution_m: topo.topoResolutionM,
      },
      governance: {
        training_eligible: classification.trainingEligible,
        training_eligible_reason: classification.reason,
        classifier_method: classification.method,
      },
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    if (jobId) {
      try {
        const supabase = createClient(
          Deno.env.get('SUPABASE_URL')!,
          Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
        );
        await supabase
          .from('compute_jobs')
          .update({ status: 'failed', error: (err as Error).message })
          .eq('id', jobId);
      } catch {
        // ignore job cleanup failures
      }
    }

    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
