import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

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

async function getActiveLabelPolicy(supabase: any): Promise<LabelPolicy> {
  const { data: policy } = await supabase
    .from('label_matching_policies')
    .select('*')
    .eq('hazard_type', 'avalanche')
    .order('created_at', { ascending: false })
    .limit(1)
    .single();
  
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

function estimateElevation(row: number, totalRows: number, regionMinElev: number, regionMaxElev: number): number {
  // Rough elevation estimate based on grid row position
  // In production, use actual DEM data
  const elevationRange = regionMaxElev - regionMinElev;
  return regionMinElev + (row / totalRows) * elevationRange;
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

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { 
      forecast_id: forecastId,
      days_back: daysBack = 7,
      hazard_type: hazardType = 'avalanche'
    } = await req.json();

    if (hazardType !== 'avalanche') {
      return new Response(JSON.stringify({ error: 'Only avalanche supported' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    // Create job
    const { data: job, error: jobErr } = await supabase
      .from('compute_jobs')
      .insert({ 
        type: 'label_forecast_outcomes', 
        status: 'running',
        hazard_type: hazardType,
        payload: { forecast_id: forecastId, days_back: daysBack }
      })
      .select('id')
      .single();
    if (jobErr) throw jobErr;

    // Get labeling policy
    const policy = await getActiveLabelPolicy(supabase);
    const minVerificationRank = getVerificationRank(policy.min_event_verification);

    // Fetch forecasts to label
    let forecastQuery = supabase
      .from('forecasts')
      .select('id, created_at, hourly_grids, bbox, hazard_type')
      .eq('hazard_type', hazardType)
      .order('created_at', { ascending: false });
    
    if (forecastId) {
      forecastQuery = forecastQuery.eq('id', forecastId);
    } else {
      // Label forecasts from last N days that don't have outcomes yet
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - daysBack);
      forecastQuery = forecastQuery.gte('created_at', cutoffDate.toISOString());
    }

    const { data: forecasts, error: forecastErr } = await forecastQuery;
    if (forecastErr) throw forecastErr;

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
      await supabase
        .from('compute_jobs')
        .update({ status: 'completed', result: earlyResult })
        .eq('id', job.id);
      return new Response(JSON.stringify(earlyResult), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Wrap the labeling work in a timeout race to prevent stuck-running jobs
    const labelingWork = async () => {
      for (const forecast of forecasts) {
        // Check if already labeled
        const { data: existing } = await supabase
          .from('forecast_outcomes')
          .select('id')
          .eq('forecast_id', forecast.id)
          .limit(1);
        
        if (existing && existing.length > 0) {
          totalSkipped++;
          continue;
        }

        const hourlyGrids = forecast.hourly_grids || [];
        const bbox = forecast.bbox || [0, 0, 0, 0];
        const forecastTime = new Date(forecast.created_at);
        
        // Define outcome window (when events would verify this forecast)
        const windowStart = new Date(forecastTime);
        const windowEnd = new Date(forecastTime);
        windowEnd.setHours(windowEnd.getHours() + policy.temporal_tolerance_hours);

        // Fetch candidate events in bbox + time window
        // Expand bbox by tolerance
        const latBuffer = policy.spatial_tolerance_m / 111000;
        const lngBuffer = policy.spatial_tolerance_m / (111000 * Math.cos(bbox[0] * Math.PI / 180));
        
        const { data: events } = await supabase
          .from('avalanche_events')
          .select('id, location, timestamp, severity, verification_status, elevation_m, label_role')
          .eq('hazard_type', hazardType)
          .gte('timestamp', windowStart.toISOString())
          .lte('timestamp', windowEnd.toISOString())
          .not('label_role', 'eq', 'excluded');

        // Filter events by verification threshold
        const eligibleEvents = (events || []).filter((e: any) => 
          getVerificationRank(e.verification_status) >= minVerificationRank
        );

        // Process each hour and cell for this forecast only
        const outcomes = [];

        if (eligibleEvents.length === 0) {
          totalSkipped++;
          continue;
        }

        for (let hour = 0; hour < hourlyGrids.length; hour++) {
          const grid = hourlyGrids[hour];
          if (!Array.isArray(grid)) continue;

          for (const cell of grid) {
            if (!cell || typeof cell.row !== 'number') continue;

            const cellElevation = estimateElevation(cell.row, 20, 1000, 4500);
            
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
              forecast_id: forecast.id,
              hazard_type: hazardType,
              cell_row: cell.row,
              cell_col: cell.col,
              forecast_hour: hour,
              predicted_risk_score: Math.round(cell.riskScore || 1),
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
              excluded_from_training: !eventObserved && labelConfidence < 0.3,
              exclusion_reason: !eventObserved && labelConfidence < 0.3 ? 'low_confidence_negative' : null,
            });
          }
        }

        // Batch insert outcomes for this forecast only
        if (outcomes.length > 0) {
          const { error: insertErr } = await supabase
            .from('forecast_outcomes')
            .insert(outcomes);
          
          if (!insertErr) {
            totalLabeled += outcomes.length;
          }
        }
      }
    };

    // Race labeling against a hard timeout so jobs don't remain stuck running
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Labeling timed out after 30s — partial results saved')), 30000)
    );

    try {
      await Promise.race([labelingWork(), timeoutPromise]);
    } catch (timeoutErr) {
      // Mark job completed with partial results rather than leaving it 'running'
      const partialResult = {
        forecasts_processed: (forecasts || []).length,
        total_outcomes_labeled: totalLabeled,
        forecasts_skipped: totalSkipped,
        labeling_policy: policy,
        warning: (timeoutErr as Error).message,
      };
      await supabase
        .from('compute_jobs')
        .update({ status: 'completed', result: partialResult })
        .eq('id', job.id);
      return new Response(JSON.stringify(partialResult), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const result = {
      forecasts_processed: (forecasts || []).length,
      total_outcomes_labeled: totalLabeled,
      forecasts_skipped: totalSkipped,
      labeling_policy: policy,
    };

    await supabase
      .from('compute_jobs')
      .update({ status: 'completed', result })
      .eq('id', job.id);

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    if (supabaseUrl && serviceRoleKey) {
      try {
        const supabase = createClient(supabaseUrl, serviceRoleKey);
        const { data: latestJob } = await supabase
          .from('compute_jobs')
          .select('id')
          .eq('type', 'label_forecast_outcomes')
          .eq('status', 'running')
          .order('created_at', { ascending: false })
          .limit(1)
          .maybeSingle();
        if (latestJob?.id) {
          await supabase
            .from('compute_jobs')
            .update({ status: 'failed', error: (err as Error).message })
            .eq('id', latestJob.id);
        }
      } catch {
        // Best effort only; original error still returns to caller.
      }
    }
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
