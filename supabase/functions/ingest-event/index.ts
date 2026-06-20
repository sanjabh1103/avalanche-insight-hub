import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { extractBearerToken } from "../_shared/auth.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const ELEVATION_LOOKUP_URL = 'https://api.open-elevation.com/api/v1/lookup';
const SAMPLE_DEGREE_OFFSET = 0.0025;
const METERS_PER_DEG_LAT = 111_320;

type EventPayload = {
  fieldReportId?: string;
  clientReportId?: string;
  lat: number;
  lng: number;
  description?: string;
  timestamp?: string;
  hazard_type?: string;
  source?: string;
  event_type?: string;
  severity?: number;
  confidence?: number;
  label_confidence?: number;
  source_model?: string;
  source_scene_ids?: string[];
  geometry_type?: string;
  mask_asset_ref?: string | null;
  location_name?: string;
  fusion_source?: string;
  training_eligible?: boolean;
  label_role?: string;
  training_eligible_reason?: string;
  metadata?: Record<string, unknown>;
};

type FieldReportRow = {
  id: string;
  description: string | null;
  timestamp: string | null;
  client_report_id: string | null;
};

const GOVERNANCE_VERSION = 'autonomous_label_governance_v2';
const EVENT_SELECT_COLUMNS = 'id, timestamp, source, description, severity, event_type, confidence, label_confidence, training_weight, verification_status, label_role, location, features';

type ElevationSample = {
  name: 'center' | 'north' | 'south' | 'east' | 'west';
  lat: number;
  lng: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

// --- Prompt-injection guard for news-sourced descriptions ---
// Detects patterns commonly used to hijack LLM extraction: role directives,
// base64 payloads, HTML/script tags, excessive URL density, and oversized text.
// Returns sanitized text plus a flag indicating whether sanitization fired.
const INJECTION_PATTERNS = [
  /\b(system|assistant|user)\s*:/gi,       // Role-injection directives
  /\bignore\s+(previous|above|all)\b/gi,    // "Ignore previous instructions"
  /\b(do\s+not|don'?t)\s+follow\b/gi,      // Counter-instruction patterns
  /<\/?script\b/gi,                          // HTML script tags
  /data:[a-z]+\/[a-z]+;base64,/gi,          // Base64 data URIs
  /\{[^}]{0,20}(role|content|function)[^}]{0,20}\}/gi, // JSON role injection
];
const MAX_DESCRIPTION_LENGTH = 2000;
const MAX_URL_DENSITY = 3;

type SanitizeResult = {
  text: string;
  wasSanitized: boolean;
  sanitizeReasons: string[];
};

function sanitizeNewsDescription(raw: string): SanitizeResult {
  const reasons: string[] = [];
  let text = raw;

  // Length gate
  if (text.length > MAX_DESCRIPTION_LENGTH) {
    text = text.slice(0, MAX_DESCRIPTION_LENGTH) + ' [truncated]';
    reasons.push('length_exceeded');
  }

  // Pattern scrubbing
  for (const pattern of INJECTION_PATTERNS) {
    const nextText = text.replace(pattern, '[redacted]');
    if (nextText !== text) {
      text = nextText;
      reasons.push(`pattern_${pattern.source.slice(0, 20)}`);
    }
  }

  // URL density check
  const urlMatches = text.match(/https?:\/\/\S+/gi) || [];
  if (urlMatches.length > MAX_URL_DENSITY) {
    // Keep first MAX_URL_DENSITY URLs, redact the rest
    let count = 0;
    text = text.replace(/https?:\/\/\S+/gi, (match) => {
      count++;
      return count <= MAX_URL_DENSITY ? match : '[url-redacted]';
    });
    reasons.push('url_density_exceeded');
  }

  return {
    text: text.trim(),
    wasSanitized: reasons.length > 0,
    sanitizeReasons: reasons,
  };
}
// --- End prompt-injection guard ---

function sourceWeightFor(source: string, fusionSource?: string): number {
  const weights: Record<string, number> = {
    field_report: 1.0,
    field_report_offline_sync: 1.0,
    gemini_news: 0.8,
    newsdata_gemini: 0.8,
    gee_sar: 0.9,
    sentinel1_gee: 0.9,
    sar_unet: 1.1,
  };
  const primary = weights[source] ?? null;
  if (primary !== null) return primary;
  return weights[fusionSource || ''] ?? 0.75;
}

function recencyDecay(timestampIso?: string): number {
  if (!timestampIso) return 1;
  const ts = new Date(timestampIso);
  if (Number.isNaN(ts.getTime())) return 1;
  const ageDays = Math.max(0, (Date.now() - ts.getTime()) / (1000 * 60 * 60 * 24));
  const halfLifeDays = 30;
  return clamp(Math.exp((-Math.log(2) * ageDays) / halfLifeDays), 0.2, 1);
}

function corroborationWeight(metadata: Record<string, unknown>, source: string, fusionSource?: string): number {
  const corroborationSources = new Set<string>();
  const metadataSources = metadata.corroboration_sources;
  if (Array.isArray(metadataSources)) {
    metadataSources.forEach((entry) => {
      if (typeof entry === 'string' && entry.trim()) corroborationSources.add(entry.trim().toLowerCase());
    });
  }
  if (source) corroborationSources.add(source.toLowerCase());
  if (fusionSource) corroborationSources.add(fusionSource.toLowerCase());
  const count = Math.max(corroborationSources.size, 1);
  return clamp(1 + (count - 1) * 0.15, 1, 1.45);
}

function computeTrainingWeight(args: {
  labelConfidence: number;
  source: string;
  fusionSource?: string;
  timestampIso?: string;
  metadata: Record<string, unknown>;
}): number {
  return clamp(
    args.labelConfidence
      * sourceWeightFor(args.source, args.fusionSource)
      * corroborationWeight(args.metadata, args.source, args.fusionSource)
      * recencyDecay(args.timestampIso),
    0.1,
    1.5,
  );
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

async function findExistingEvent(
  supabase: any,
  args: { fieldReportId?: string; clientReportId?: string },
) {
  if (args.fieldReportId) {
    const { data } = await supabase
      .from('avalanche_events')
      .select(EVENT_SELECT_COLUMNS)
      .contains('features', { field_report_id: args.fieldReportId })
      .order('timestamp', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (data?.id) return data;
  }

  if (args.clientReportId) {
    const { data } = await supabase
      .from('avalanche_events')
      .select(EVENT_SELECT_COLUMNS)
      .contains('features', { client_report_id: args.clientReportId })
      .order('timestamp', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (data?.id) return data;
  }

  return null;
}

async function loadFieldReport(
  supabase: any,
  fieldReportId: string,
): Promise<FieldReportRow | null> {
  const { data, error } = await supabase
    .from('field_reports')
    .select('id, description, timestamp, client_report_id')
    .eq('id', fieldReportId)
    .maybeSingle();

  if (error) throw error;
  return data as FieldReportRow | null;
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

export async function handleIngestEvent(req: Request) {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  const authHeader = req.headers.get("authorization");
  const token = extractBearerToken(authHeader);
  const systemToken = Deno.env.get("JOB_DISPATCH_TOKEN");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  const requireJobAuth = Deno.env.get("REQUIRE_JOB_AUTH");
  const enforceAuth = requireJobAuth !== "false" && requireJobAuth !== "0" && requireJobAuth !== "off" && requireJobAuth !== "no";

  if (enforceAuth) {
    if (!token || (
      (!systemToken || token !== systemToken) &&
      (!serviceRoleKey || token !== serviceRoleKey)
    )) {
      return new Response(JSON.stringify({ error: "Unauthorized system call" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
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

    const source = payload.source || 'field_report';
    const fusionSource = payload.fusion_source || source;
    let governedFieldReport: FieldReportRow | null = null;

    if (source === 'field_report' || fusionSource === 'field_report_enrichment') {
      if (!payload.fieldReportId) {
        return new Response(JSON.stringify({ error: 'fieldReportId is required for governed field report ingestion' }), {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
      governedFieldReport = await loadFieldReport(supabase, payload.fieldReportId);
      if (!governedFieldReport?.id) {
        return new Response(JSON.stringify({ error: 'Backing field report was not found' }), {
          status: 404,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
      if (
        payload.clientReportId
        && governedFieldReport.client_report_id
        && payload.clientReportId !== governedFieldReport.client_report_id
      ) {
        return new Response(JSON.stringify({ error: 'clientReportId does not match the backing field report' }), {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
    }

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

    const existingEvent = await findExistingEvent(supabase, {
      fieldReportId: payload.fieldReportId,
      clientReportId: payload.clientReportId,
    });
    if (existingEvent?.id) {
      await supabase
        .from('compute_jobs')
        .update({
          status: 'completed',
          result: {
            event_id: existingEvent.id,
            deduped: true,
            dedupe_reason: payload.clientReportId ? 'client_report_id' : 'field_report_id',
          },
        })
        .eq('id', job.id);

      return new Response(JSON.stringify({
        ok: true,
        jobId: job.id,
        duplicate: true,
        event: existingEvent,
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    let elevationSamples: Record<string, number>;
    try {
      elevationSamples = await fetchElevations(buildSamples(lat, lng));
    } catch (error) {
      console.warn('Elevation lookup fallback in ingest-event:', (error as Error).message);
      elevationSamples = fallbackElevations(lat, lng);
    }

    const topo = slopeAspectFromSamples(elevationSamples, lat);
    let rawDescription = typeof governedFieldReport?.description === 'string' && governedFieldReport.description.trim().length > 0
      ? governedFieldReport.description.trim()
      : typeof payload.description === 'string' && payload.description.trim().length > 0
        ? payload.description.trim()
        : 'Observed avalanche-related event';

    // Apply prompt-injection guard for news-sourced events
    let descriptionSanitized = false;
    let sanitizeReasons: string[] = [];
    if (source === 'gemini_news' || source === 'newsdata_gemini') {
      const sanitizeResult = sanitizeNewsDescription(rawDescription);
      rawDescription = sanitizeResult.text;
      descriptionSanitized = sanitizeResult.wasSanitized;
      sanitizeReasons = sanitizeResult.sanitizeReasons;
      if (descriptionSanitized) {
        console.warn(`Prompt-injection guard fired for ${source} event: ${sanitizeReasons.join(', ')}`);
      }
    }
    const description = rawDescription;
    const metadata = safeJson(payload.metadata);
    // Merge sanitize audit into metadata for traceability
    if (descriptionSanitized) {
      (metadata as Record<string, unknown>).injection_guard = {
        sanitized: true,
        reasons: sanitizeReasons,
        guarded_at: new Date().toISOString(),
      };
    }
    const hazardType = payload.hazard_type || 'avalanche';
    const eventType = payload.event_type || 'unknown';
    const severity = Number.isFinite(payload.severity as number) ? Number(payload.severity) : 3;
    const confidence = clamp(Number.isFinite(payload.confidence as number) ? Number(payload.confidence) : 0.6, 0, 1);
    const labelConfidence = clamp(Number.isFinite(payload.label_confidence as number) ? Number(payload.label_confidence) : confidence, 0, 1);
    const sourceModel = typeof payload.source_model === 'string' && payload.source_model.trim()
      ? payload.source_model.trim()
      : source;
    const sourceSceneIds = Array.isArray(payload.source_scene_ids) ? payload.source_scene_ids.map(String) : [];
    const geometryType = typeof payload.geometry_type === 'string' && payload.geometry_type.trim()
      ? payload.geometry_type.trim()
      : 'point';
    const timestampIso = typeof governedFieldReport?.timestamp === 'string' && governedFieldReport.timestamp.trim()
      ? governedFieldReport.timestamp.trim()
      : typeof payload.timestamp === 'string' && payload.timestamp.trim()
        ? payload.timestamp.trim()
        : typeof metadata.event_date_iso === 'string' && metadata.event_date_iso
          ? metadata.event_date_iso
          : new Date().toISOString();
    const trainingWeight = computeTrainingWeight({
      labelConfidence,
      source,
      fusionSource,
      timestampIso,
      metadata,
    });
    const governedAt = new Date().toISOString();

    // Story 21: classify deposit vs. release zone AFTER topo is resolved so the
    // heuristic can use slope angle as a corroborating signal.
    const classification = await classifyDepositZone(description, topo.slopeAngleDeg);

    let trainingEligible = classification.trainingEligible;
    let trainingEligibleReason = classification.reason;

    // Caller-provided hard quarantine overrides local classification (e.g. unreviewed
    // Gemini or GEE candidates). This is a safety guard: display-only until a human
    // promotion path is completed.
    if (payload.training_eligible === false) {
      trainingEligible = false;
      trainingEligibleReason = payload.training_eligible_reason
        ? `${payload.training_eligible_reason}`
        : trainingEligibleReason ?? 'caller_quarantined';
    }

    // Milestone 3.5: news-sourced events require at least 2 corroboration sources or manual promotion
    if (source === 'gemini_news' || source === 'newsdata_gemini') {
      const corroborationSources = metadata.corroboration_sources;
      const hasMultipleSources = Array.isArray(corroborationSources) && corroborationSources.length >= 2;
      if (!hasMultipleSources) {
        trainingEligible = false;
        trainingEligibleReason = trainingEligibleReason
          ? `${trainingEligibleReason}_uncorroborated_news`
          : 'uncorroborated_news';
      }
    }

    // Machine-extracted events default to display-only labels until reviewed.
    const labelRole = payload.label_role ??
      ((source === 'gemini_news' || source === 'newsdata_gemini') && !trainingEligible ? 'display_only' : null);

    const { data: event, error: eventErr } = await supabase
      .from('avalanche_events')
      .insert({
        source,
        description,
        severity,
        event_type: eventType,
        location: `SRID=4326;POINT(${lng} ${lat})`,
        timestamp: timestampIso,
        confidence,
        label_confidence: labelConfidence,
        training_weight: trainingWeight,
        governance_version: GOVERNANCE_VERSION,
        governed_at: governedAt,
        fusion_source: fusionSource,
        source_model: sourceModel,
        source_scene_ids: sourceSceneIds,
        geometry_type: geometryType,
        mask_asset_ref: payload.mask_asset_ref ?? null,
        elevation_m: topo.elevationM,
        slope_band: topo.slopeBand,
        aspect_bucket: topo.aspectBucket,
        slope_angle_deg: topo.slopeAngleDeg,
        aspect_deg: topo.aspectDeg,
        topo_source: 'open-elevation',
        topo_resolution_m: topo.topoResolutionM,
        training_eligible: trainingEligible,
        training_eligible_reason: trainingEligibleReason,
        label_role: labelRole,
        verification_status: descriptionSanitized ? 'needs_review' : null,
        topo_profile: {
          ...topo.topoProfile,
          hazard_type: hazardType,
          source,
          field_report_id: payload.fieldReportId || null,
          client_report_id: governedFieldReport?.client_report_id ?? payload.clientReportId ?? null,
          location_name: payload.location_name || null,
          metadata,
          deposit_zone_classifier: {
            method: classification.method,
            reason: classification.reason,
            training_eligible: trainingEligible,
          },
          label_governance: {
            label_confidence: labelConfidence,
            training_weight: trainingWeight,
            governance_version: GOVERNANCE_VERSION,
            governed_at: governedAt,
            source_model: sourceModel,
            source_scene_ids: sourceSceneIds,
            geometry_type: geometryType,
            mask_asset_ref: payload.mask_asset_ref ?? null,
          },
        },
        features: {
          topo_source: 'open-elevation',
          topo_resolution_m: topo.topoResolutionM,
          slope_angle_deg: topo.slopeAngleDeg,
          aspect_deg: topo.aspectDeg,
          hazard_type: hazardType,
          source,
          field_report_id: payload.fieldReportId || null,
          client_report_id: governedFieldReport?.client_report_id ?? payload.clientReportId ?? null,
          location_name: payload.location_name || null,
          training_eligible: trainingEligible,
          source_model: sourceModel,
          source_scene_ids: sourceSceneIds,
          geometry_type: geometryType,
          mask_asset_ref: payload.mask_asset_ref ?? null,
          label_confidence: labelConfidence,
          training_weight: trainingWeight,
          governance_version: GOVERNANCE_VERSION,
          governed_at: governedAt,
        },
      })
      .select(EVENT_SELECT_COLUMNS)
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
          training_eligible: trainingEligible,
          training_eligible_reason: trainingEligibleReason,
          deposit_zone_method: classification.method,
          label_confidence: labelConfidence,
          training_weight: trainingWeight,
          source_model: sourceModel,
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
        training_eligible: trainingEligible,
        training_eligible_reason: trainingEligibleReason,
        classifier_method: classification.method,
        label_confidence: labelConfidence,
        training_weight: trainingWeight,
        governance_version: GOVERNANCE_VERSION,
        governed_at: governedAt,
        source_model: sourceModel,
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
}

if (import.meta.main) {
  serve(handleIngestEvent);
}
