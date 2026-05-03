import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  fetchPublishedRunByCompatibilityForecastGridId,
  loadHourlyGridsFromForecastRun,
} from "../_shared/forecastArtifacts.ts";
import {
  getCellDryWetDomain,
  getCellElevation,
  getCellProblemSlug,
  getCellSarCoverageState,
  normalizeAsyncHourlyGrids,
} from "../_shared/evaluationMetadata.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface LabelPolicy {
  spatial_tolerance_m: number;
  temporal_tolerance_hours: number;
  elevation_band_width_m: number;
  elevation_flexibility_m: number;
  min_event_verification: string;
}

interface ForecastSourceRecord {
  source_type: 'forecast' | 'forecast_grid';
  id: string;
  created_at: string;
  bbox: number[];
  hourly_grids: any[][];
}

interface EligibleEvent {
  id: string;
  timestamp: string | null;
  severity: number;
  verification_status: string;
  elevation_m: number | null;
  label_role: string | null;
  training_eligible_reason: string | null;
  location: string;
}

interface FetchEligibleEventsRpcResult {
  events: EligibleEvent[];
  error: unknown;
}

interface ForecastEventLookupParams {
  hazardType: string;
  windowStartIso: string;
  windowEndIso: string;
  bbox: [number, number, number, number];
  minVerificationRank: number;
  limit: number;
}

interface LabelForecastRequestBody {
  forecast_id?: unknown;
  days_back?: unknown;
  hazard_type?: unknown;
}

type ForecastOutcomeInsert = Record<string, unknown>;

interface LabelForecastOutcomesDeps {
  createJob: (params: { hazardType: string; forecastId?: string; daysBack: number }) => Promise<{ id: string }>;
  completeJob: (jobId: string, result: Record<string, unknown>) => Promise<void>;
  failRunningJob: (errorMessage: string) => Promise<void>;
  fetchLabelPolicy: (hazardType: string) => Promise<LabelPolicy>;
  fetchForecastSources: (params: { hazardType: string; forecastId?: string; daysBack: number }) => Promise<ForecastSourceRecord[]>;
  fetchExistingOutcome: (forecast: ForecastSourceRecord) => Promise<boolean>;
  fetchEligibleEventsRpc: (params: ForecastEventLookupParams) => Promise<FetchEligibleEventsRpcResult>;
  fetchEligibleEventsFallback: (params: Omit<ForecastEventLookupParams, 'bbox'>) => Promise<EligibleEvent[]>;
  insertForecastOutcomeBatch: (outcomes: ForecastOutcomeInsert[]) => Promise<void>;
  runWithTimeout: <T>(work: () => Promise<T>, timeoutMs: number, timeoutMessage: string) => Promise<T>;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

function normalizeRpcEvent(event: any): EligibleEvent {
  return {
    id: String(event.id),
    timestamp: typeof event.timestamp === 'string' ? event.timestamp : null,
    severity: Number(event.severity ?? 0),
    verification_status: typeof event.verification_status === 'string' ? event.verification_status : 'unverified',
    elevation_m: typeof event.elevation_m === 'number' ? event.elevation_m : null,
    label_role: typeof event.label_role === 'string' ? event.label_role : null,
    training_eligible_reason: typeof event.training_eligible_reason === 'string' ? event.training_eligible_reason : null,
    location: `POINT(${event.lng} ${event.lat})`,
  };
}

function normalizeRestEvent(event: any): EligibleEvent {
  return {
    id: String(event.id),
    timestamp: typeof event.timestamp === 'string' ? event.timestamp : null,
    severity: Number(event.severity ?? 0),
    verification_status: typeof event.verification_status === 'string' ? event.verification_status : 'unverified',
    elevation_m: typeof event.elevation_m === 'number' ? event.elevation_m : null,
    label_role: typeof event.label_role === 'string' ? event.label_role : null,
    training_eligible_reason: typeof event.training_eligible_reason === 'string' ? event.training_eligible_reason : null,
    location: typeof event.location === 'string' ? event.location : '',
  };
}

async function getActiveLabelPolicy(supabase: any): Promise<LabelPolicy> {
  const { data: policy, error: policyErr } = await supabase
    .from('label_matching_policies')
    .select('*')
    .eq('hazard_type', 'avalanche')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (policyErr) console.warn('label policy fetch error:', policyErr.message);
  
  if (!policy) {
    return {
      spatial_tolerance_m: 5000,
      temporal_tolerance_hours: 24,
      elevation_band_width_m: 500,
      elevation_flexibility_m: 300,
      min_event_verification: 'weak',
    };
  }
  
  return {
    spatial_tolerance_m: policy.spatial_tolerance_m,
    temporal_tolerance_hours: policy.temporal_tolerance_hours,
    elevation_band_width_m: policy.elevation_band_width_m,
    elevation_flexibility_m: policy.elevation_flexibility_m,
    min_event_verification: policy.min_event_verification,
  };
}

function getVerificationRank(status: string): number {
  const ranks: Record<string, number> = {
    'unverified': 0,
    'weak': 1,
    'verified': 2,
    'expert_verified': 3,
  };
  return ranks[status] || 0;
}

function checkElevationCompatible(
  cellElevation: number,
  eventElevation: number | null,
  flexibility: number
): boolean {
  if (!eventElevation) return true;
  return Math.abs(cellElevation - eventElevation) <= flexibility;
}

function haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000; // Earth radius in meters
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLng/2) * Math.sin(dLng/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

async function fetchForecastSources(supabase: any, hazardType: string, forecastId: string | undefined, daysBack: number): Promise<ForecastSourceRecord[]> {
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - daysBack);
  const cutoffIso = cutoffDate.toISOString();

  let legacyQuery = supabase
    .from('forecasts')
    .select('id, created_at, hourly_grids, bbox, hazard_type')
    .eq('hazard_type', hazardType)
    .order('created_at', { ascending: false });

  let asyncQuery = supabase
    .from('forecast_grids')
    .select('id, created_at, hourly_grids, grid_geojson, bbox, hazard_type, status')
    .eq('hazard_type', hazardType)
    .in('status', ['ready', 'partial', 'stale'])
    .order('created_at', { ascending: false });

  if (forecastId) {
    legacyQuery = legacyQuery.eq('id', forecastId);
    asyncQuery = asyncQuery.eq('id', forecastId);
  } else {
    legacyQuery = legacyQuery.gte('created_at', cutoffIso);
    asyncQuery = asyncQuery.gte('created_at', cutoffIso);
  }

  const [
    { data: legacyForecasts, error: legacyErr },
    { data: asyncForecasts, error: asyncErr },
  ] = await Promise.all([legacyQuery, asyncQuery]);

  if (legacyErr) throw legacyErr;
  if (asyncErr) throw asyncErr;

  const normalizedLegacy = (legacyForecasts || []).map((forecast: any) => ({
    source_type: 'forecast' as const,
    id: forecast.id,
    created_at: forecast.created_at,
    bbox: Array.isArray(forecast.bbox) ? forecast.bbox : [0, 0, 0, 0],
    hourly_grids: Array.isArray(forecast.hourly_grids) ? forecast.hourly_grids : [],
  }));

  const normalizedAsync = (asyncForecasts || []).map((forecast: any) => ({
    source_type: 'forecast_grid' as const,
    id: forecast.id,
    created_at: forecast.created_at,
    bbox: Array.isArray(forecast.bbox) ? forecast.bbox : [0, 0, 0, 0],
    hourly_grids: normalizeAsyncHourlyGrids(forecast.hourly_grids, forecast.grid_geojson),
  }));
  const hydratedAsync = await Promise.all(normalizedAsync.map(async (forecast: ForecastSourceRecord) => {
    if (forecast.hourly_grids.length > 0) return forecast;
    const publishedRun = await fetchPublishedRunByCompatibilityForecastGridId(supabase, forecast.id);
    if (!publishedRun?.manifest_storage_ref) return forecast;
    const artifactPayload = await loadHourlyGridsFromForecastRun(supabase, publishedRun.manifest_storage_ref);
    return {
      ...forecast,
      created_at: artifactPayload.created_at || forecast.created_at,
      bbox: Array.isArray(artifactPayload.bbox) ? artifactPayload.bbox : forecast.bbox,
      hourly_grids: artifactPayload.hourly_grids,
    };
  }));

  return [...hydratedAsync, ...normalizedLegacy].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

function defaultDeps(): LabelForecastOutcomesDeps {
  const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? '';
  const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';
  const supabase = createClient(supabaseUrl, serviceRoleKey);

  return {
    async createJob({ hazardType, forecastId, daysBack }) {
      const { data: job, error: jobErr } = await supabase
        .from('compute_jobs')
        .insert({
          type: 'label_forecast_outcomes',
          status: 'running',
          hazard_type: hazardType,
          payload: { forecast_id: forecastId, days_back: daysBack },
        })
        .select('id')
        .maybeSingle();
      if (jobErr) throw jobErr;
      if (!job?.id) throw new Error('Failed to create compute_job row');
      return { id: String(job.id) };
    },

    async completeJob(jobId, result) {
      await supabase
        .from('compute_jobs')
        .update({ status: 'completed', result })
        .eq('id', jobId);
    },

    async failRunningJob(errorMessage) {
      if (!supabaseUrl || !serviceRoleKey) return;
      const cleanupClient = createClient(supabaseUrl, serviceRoleKey);
      const { data: latestJob } = await cleanupClient
        .from('compute_jobs')
        .select('id')
        .eq('type', 'label_forecast_outcomes')
        .eq('status', 'running')
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      if (!latestJob?.id) return;
      await cleanupClient
        .from('compute_jobs')
        .update({ status: 'failed', error: errorMessage })
        .eq('id', latestJob.id);
    },

    async fetchLabelPolicy(_hazardType) {
      return await getActiveLabelPolicy(supabase);
    },

    async fetchForecastSources({ hazardType, forecastId, daysBack }) {
      return await fetchForecastSources(supabase, hazardType, forecastId, daysBack);
    },

    async fetchExistingOutcome(forecast) {
      let existingQuery = supabase
        .from('forecast_outcomes')
        .select('id')
        .limit(1);
      existingQuery = forecast.source_type === 'forecast_grid'
        ? existingQuery.eq('forecast_grid_id', forecast.id)
        : existingQuery.eq('forecast_id', forecast.id);
      const { data: existing } = await existingQuery;
      return Array.isArray(existing) && existing.length > 0;
    },

    async fetchEligibleEventsRpc({
      hazardType,
      windowStartIso,
      windowEndIso,
      bbox,
      minVerificationRank,
      limit,
    }) {
      const [latMin, lngMin, latMax, lngMax] = bbox;
      if (latMin === 0 && lngMin === 0 && latMax === 0 && lngMax === 0) {
        return { events: [], error: null };
      }
      const { data: rpcEvents, error } = await supabase.rpc('fetch_labeler_events', {
        p_hazard_type: hazardType,
        p_window_start: windowStartIso,
        p_window_end: windowEndIso,
        p_bbox_min_lng: lngMin,
        p_bbox_min_lat: latMin,
        p_bbox_max_lng: lngMax,
        p_bbox_max_lat: latMax,
        p_min_verification_rank: minVerificationRank,
        p_limit: limit,
      });
      return {
        events: !error && Array.isArray(rpcEvents) ? rpcEvents.map(normalizeRpcEvent) : [],
        error,
      };
    },

    async fetchEligibleEventsFallback({
      hazardType,
      windowStartIso,
      windowEndIso,
      minVerificationRank,
      limit,
    }) {
      const { data: events } = await supabase
        .from('avalanche_events')
        .select('id, location, timestamp, severity, verification_status, elevation_m, label_role, training_eligible_reason')
        .eq('hazard_type', hazardType)
        .gte('timestamp', windowStartIso)
        .lte('timestamp', windowEndIso)
        .not('label_role', 'eq', 'excluded')
        .order('timestamp', { ascending: false })
        .limit(limit);
      return (events || [])
        .filter((event: any) => getVerificationRank(event.verification_status) >= minVerificationRank)
        .map(normalizeRestEvent);
    },

    async insertForecastOutcomeBatch(outcomes) {
      const { error } = await supabase
        .from('forecast_outcomes')
        .insert(outcomes);
      if (error) throw error;
    },

    async runWithTimeout(work, timeoutMs, timeoutMessage) {
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error(timeoutMessage)), timeoutMs)
      );
      return await Promise.race([work(), timeoutPromise]);
    },
  };
}

export async function handleLabelForecastOutcomes(
  req: Request,
  deps: LabelForecastOutcomesDeps = defaultDeps(),
) {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const requestBody = await req.json() as LabelForecastRequestBody;
    const forecastId = typeof requestBody.forecast_id === 'string' && requestBody.forecast_id
      ? requestBody.forecast_id
      : undefined;
    const daysBack = typeof requestBody.days_back === 'number' && Number.isFinite(requestBody.days_back)
      ? requestBody.days_back
      : 7;
    const hazardType = typeof requestBody.hazard_type === 'string' && requestBody.hazard_type
      ? requestBody.hazard_type
      : 'avalanche';

    if (hazardType !== 'avalanche') {
      return jsonResponse({ error: 'Only avalanche supported' }, 400);
    }

    const job = await deps.createJob({ hazardType, forecastId, daysBack });

    // Get labeling policy
    const policy = await deps.fetchLabelPolicy(hazardType);
    const minVerificationRank = getVerificationRank(policy.min_event_verification);

    const forecasts = await deps.fetchForecastSources({ hazardType, forecastId, daysBack });

    let totalLabeled = 0;
    let totalSkipped = 0;

    // Early exit guard: no forecasts found → mark complete with 0 labels immediately
    if (!forecasts || forecasts.length === 0) {
      const earlyResult = {
        forecasts_processed: 0,
        total_outcomes_labeled: 0,
        forecasts_skipped: 0,
        labeling_policy: policy,
        note: 'No matching forecasts found in window. Completed with 0 labels.',
      };
      await deps.completeJob(job.id, earlyResult);
      return jsonResponse(earlyResult);
    }

    // Wrap the labeling work in a timeout race to prevent stuck-running jobs
    const labelingWork = async () => {
      for (const forecast of forecasts) {
        // Check if already labeled
        if (await deps.fetchExistingOutcome(forecast)) {
          totalSkipped++;
          continue;
        }

        const hourlyGrids = forecast.hourly_grids || [];
        const bbox = Array.isArray(forecast.bbox) && forecast.bbox.length === 4 ? forecast.bbox : [0, 0, 0, 0];
        const forecastTime = new Date(forecast.created_at);

        // Define outcome window (when events would verify this forecast)
        const windowStart = new Date(forecastTime);
        const windowEnd = new Date(forecastTime);
        windowEnd.setHours(windowEnd.getHours() + policy.temporal_tolerance_hours);

        // P0.1: Bbox-narrowed RPC pre-filters in Postgres using the GIST index
        // on location, dropping the payload to O(matching events) instead of
        // O(all events in window). Falls back to the legacy REST query only
        // when the RPC is unavailable (e.g. during migration rollout).
        const [latMin, lngMin, latMax, lngMax] = bbox;
        let eligibleEvents: EligibleEvent[] = [];
        const { events: rpcEvents, error: rpcError } = await deps.fetchEligibleEventsRpc({
          hazardType,
          windowStartIso: windowStart.toISOString(),
          windowEndIso: windowEnd.toISOString(),
          bbox: [latMin, lngMin, latMax, lngMax],
          minVerificationRank,
          limit: 200,
        });
        eligibleEvents = rpcEvents;
        if (rpcError || eligibleEvents.length === 0) {
          eligibleEvents = await deps.fetchEligibleEventsFallback({
            hazardType,
            windowStartIso: windowStart.toISOString(),
            windowEndIso: windowEnd.toISOString(),
            minVerificationRank,
            limit: 200,
          });
        }

        // Process each hour and cell for this forecast only
        const outcomes: ForecastOutcomeInsert[] = [];

        if (eligibleEvents.length === 0) {
          totalSkipped++;
          continue;
        }

        // P0.1: Inner per-forecast budget. A pathological region cannot stall
        // the whole batch; on overshoot we save whatever labels we've built.
        const forecastDeadline = Date.now() + 15000;

        for (let hour = 0; hour < hourlyGrids.length; hour++) {
          if (Date.now() > forecastDeadline) break;
          const grid = hourlyGrids[hour];
          if (!Array.isArray(grid)) continue;

          for (const cell of grid) {
            if (!cell || typeof cell.row !== 'number') continue;

            const cellRecord = cell as Record<string, unknown>;
            const cellElevation = getCellElevation(cellRecord);
            
            // Find nearest matching event
            let nearestEvent: any = null;
            let nearestDistance = Infinity;
            let isElevationCompatible = false;

            for (const event of eligibleEvents) {
              // Parse location
              const locMatch = event.location?.match(/POINT\(([^ ]+) ([^ ]+)\)/);
              if (!locMatch) continue;
              
              const eventLng = parseFloat(locMatch[1]);
              const eventLat = parseFloat(locMatch[2]);
              
              const distance = haversineDistance(cell.lat, cell.lng, eventLat, eventLng);
              const elevOk = checkElevationCompatible(
                cellElevation,
                event.elevation_m,
                policy.elevation_flexibility_m
              );

              if (distance <= policy.spatial_tolerance_m && elevOk) {
                if (distance < nearestDistance) {
                  nearestDistance = distance;
                  nearestEvent = event;
                  isElevationCompatible = true;
                }
              }
            }

            // Determine label
            const eventObserved = nearestEvent !== null;
            const severityLabel = nearestEvent ? 
              (nearestEvent.severity >= 4 ? 'severe' : 
               nearestEvent.severity >= 3 ? 'moderate' : 'minor') : 'none';
            
            // Label confidence based on match quality
            let labelConfidence = 0.5;
            if (eventObserved) {
              const distanceScore = Math.max(0, 1 - nearestDistance / policy.spatial_tolerance_m);
              const verificationScore = getVerificationRank(nearestEvent.verification_status) / 3;
              const elevationScore = isElevationCompatible ? 1.0 : 0.5;
              labelConfidence = (distanceScore * 0.4 + verificationScore * 0.4 + elevationScore * 0.2);
            }

            outcomes.push({
              forecast_grid_id: forecast.source_type === 'forecast_grid' ? forecast.id : null,
              forecast_id: forecast.source_type === 'forecast' ? forecast.id : null,
              hazard_type: hazardType,
              cell_row: cell.row,
              cell_col: cell.col,
              forecast_hour: hour,
              predicted_risk_score: Math.round(cell.riskScore || cell.risk_score || 1),
              predicted_hazard: cell.hazard || 0,
              outcome_window_start: windowStart.toISOString(),
              outcome_window_end: windowEnd.toISOString(),
              event_observed: eventObserved,
              severity_label: severityLabel,
              distance_to_nearest_event_m: eventObserved ? nearestDistance : null,
              nearest_event_id: nearestEvent?.id || null,
              label_confidence: Number(labelConfidence.toFixed(3)),
              label_version: 'v1.0.0',
              spatial_tolerance_m: policy.spatial_tolerance_m,
              temporal_tolerance_hours: policy.temporal_tolerance_hours,
              elevation_band_compatible: isElevationCompatible,
              cell_elevation_m: cellElevation,
              sar_coverage_state: getCellSarCoverageState(cellRecord),
              dry_wet_domain: getCellDryWetDomain(cellRecord),
              problem_slug: getCellProblemSlug(cellRecord),
              training_eligible_reason: nearestEvent?.training_eligible_reason ?? null,
              excluded_from_training: !eventObserved && labelConfidence < 0.3,
              exclusion_reason: !eventObserved && labelConfidence < 0.3 ? 'low_confidence_negative' : null,
            });
          }
        }

        // Chunked insert so a large forecast grid cannot exceed the
        // Postgres statement timeout on a single INSERT.
        if (outcomes.length > 0) {
          const CHUNK = 500;
          for (let i = 0; i < outcomes.length; i += CHUNK) {
            const slice = outcomes.slice(i, i + CHUNK);
            await deps.insertForecastOutcomeBatch(slice);
            totalLabeled += slice.length;
          }
        }
      }
    };

    try {
      await deps.runWithTimeout(
        labelingWork,
        60000,
        'Labeling timed out after 60s — partial results saved',
      );
    } catch (timeoutErr) {
      // Mark job completed with partial results rather than leaving it 'running'
      const partialResult = {
        forecasts_processed: (forecasts || []).length,
        total_outcomes_labeled: totalLabeled,
        forecasts_skipped: totalSkipped,
        labeling_policy: policy,
        warning: (timeoutErr as Error).message,
      };
      await deps.completeJob(job.id, partialResult);
      return jsonResponse(partialResult);
    }

    const result = {
      forecasts_processed: (forecasts || []).length,
      total_outcomes_labeled: totalLabeled,
      forecasts_skipped: totalSkipped,
      labeling_policy: policy,
    };

    await deps.completeJob(job.id, result);

    return jsonResponse(result);
  } catch (err) {
    try {
      await deps.failRunningJob((err as Error).message);
    } catch {
      // Best effort only; original error still returns to caller.
    }
    return jsonResponse({ error: (err as Error).message }, 500);
  }
}

if (import.meta.main) {
  serve((req) => handleLabelForecastOutcomes(req));
}
