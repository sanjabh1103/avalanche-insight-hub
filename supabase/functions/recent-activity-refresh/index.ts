import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface EventSummary {
  count: number;
  verifiedCount: number;
  weightedSeverity: number;
  maxSeverity: number;
  sourceBreakdown: Record<string, number>;
  aspectBuckets: Set<string>;
  elevationRange: { min: number; max: number } | null;
}

function calculateRecencyWeight(eventDate: string, windowEnd: Date): number {
  const event = new Date(eventDate);
  const daysAgo = (windowEnd.getTime() - event.getTime()) / (1000 * 60 * 60 * 24);
  // Exponential decay: 1.0 at 0 days, ~0.37 at 7 days
  return Math.exp(-daysAgo / 7);
}

function getAspectBucket(degrees: number | null): string | null {
  if (!degrees) return null;
  if (degrees >= 337.5 || degrees < 22.5) return 'N';
  if (degrees >= 22.5 && degrees < 67.5) return 'NE';
  if (degrees >= 67.5 && degrees < 112.5) return 'E';
  if (degrees >= 112.5 && degrees < 157.5) return 'SE';
  if (degrees >= 157.5 && degrees < 202.5) return 'S';
  if (degrees >= 202.5 && degrees < 247.5) return 'SW';
  if (degrees >= 247.5 && degrees < 292.5) return 'W';
  return 'NW';
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { 
      region_name: regionName,
      window_days: windowDays = 7,
      hazard_type: hazardType = 'avalanche',
      materialize_cells: materializeCells = false,
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
        type: 'recent_activity_refresh', 
        status: 'running',
        hazard_type: hazardType,
        payload: { region_name: regionName, window_days: windowDays, materialize_cells: materializeCells }
      })
      .select('id')
      .single();
    if (jobErr) throw jobErr;

    // Calculate time window
    const windowEnd = new Date();
    const windowStart = new Date();
    windowStart.setDate(windowStart.getDate() - windowDays);

    // Base query for events
    let eventsQuery = supabase
      .from('avalanche_events')
      .select('id, location, timestamp, severity, verification_status, source, label_role, elevation_m, aspect_bucket')
      .eq('hazard_type', hazardType)
      .gte('timestamp', windowStart.toISOString())
      .lte('timestamp', windowEnd.toISOString())
      .not('label_role', 'eq', 'excluded');

    if (regionName) {
      // Filter by region via location-based heuristics or stored region
      eventsQuery = eventsQuery.or(`features->>location_name.ilike.%${regionName}%,location_name.ilike.%${regionName}%`);
    }

    const { data: events, error: eventsErr } = await eventsQuery;
    if (eventsErr) throw eventsErr;

    // Summarize by region level
    const regionSummary: EventSummary = {
      count: 0,
      verifiedCount: 0,
      weightedSeverity: 0,
      maxSeverity: 0,
      sourceBreakdown: {},
      aspectBuckets: new Set(),
      elevationRange: null,
    };

    let minElev: number | null = null;
    let maxElev: number | null = null;

    for (const event of (events || [])) {
      // Skip training-only events for display summary
      if (event.label_role === 'training_label' && !materializeCells) continue;

      regionSummary.count++;
      
      if (event.verification_status === 'verified' || event.verification_status === 'expert_verified') {
        regionSummary.verifiedCount++;
      }

      const recencyWeight = calculateRecencyWeight(event.timestamp, windowEnd);
      regionSummary.weightedSeverity += (event.severity || 3) * recencyWeight;
      regionSummary.maxSeverity = Math.max(regionSummary.maxSeverity, event.severity || 3);

      // Source breakdown
      const source = event.source || 'unknown';
      regionSummary.sourceBreakdown[source] = (regionSummary.sourceBreakdown[source] || 0) + 1;

      // Aspect
      if (event.aspect_bucket) {
        regionSummary.aspectBuckets.add(event.aspect_bucket);
      }

      // Elevation range
      if (event.elevation_m) {
        minElev = minElev === null ? event.elevation_m : Math.min(minElev, event.elevation_m);
        maxElev = maxElev === null ? event.elevation_m : Math.max(maxElev, event.elevation_m);
      }
    }

    if (minElev !== null && maxElev !== null) {
      regionSummary.elevationRange = { min: minElev, max: maxElev };
    }

    // Store region-level summary
    const { data: feature, error: featureErr } = await supabase
      .from('recent_activity_features')
      .upsert({
        region_name: regionName || 'global',
        cell_row: null,
        cell_col: null,
        window_start: windowStart.toISOString(),
        window_end: windowEnd.toISOString(),
        window_days: windowDays,
        total_event_count: regionSummary.count,
        verified_event_count: regionSummary.verifiedCount,
        training_eligible_count: (events || []).filter((e: any) => e.label_role === 'training_label').length,
        weighted_severity_sum: Number(regionSummary.weightedSeverity.toFixed(2)),
        max_severity_in_window: regionSummary.maxSeverity,
        unique_aspect_buckets: Array.from(regionSummary.aspectBuckets),
        elevation_range_m: regionSummary.elevationRange,
        sources: regionSummary.sourceBreakdown,
        data_completeness_score: events && events.length > 0 ? 1.0 : 0.5,
        materialized_at: new Date().toISOString(),
        materialization_job_id: job.id,
      }, {
        onConflict: 'region_name,cell_row,cell_col,window_start,window_end'
      })
      .select('id')
      .single();

    if (featureErr) throw featureErr;

    let cellSummaries = 0;

    // If requested, also materialize per-cell summaries (expensive, so optional)
    if (materializeCells && regionName) {
      // Get recent forecasts for this region to extract cell coordinates
      const { data: recentForecasts } = await supabase
        .from('forecasts')
        .select('id, hourly_grids')
        .eq('hazard_type', hazardType)
        .order('created_at', { ascending: false })
        .limit(1);

      if (recentForecasts && recentForecasts.length > 0 && recentForecasts[0].hourly_grids) {
        const grid = recentForecasts[0].hourly_grids[0];
        if (Array.isArray(grid)) {
          const cellFeatures = [];
          
          for (const cell of grid) {
            if (!cell || typeof cell.lat !== 'number') continue;

            // Find events near this cell
            const cellEvents = (events || []).filter((e: any) => {
              const locMatch = e.location?.match(/POINT\(([^ ]+) ([^ ]+)\)/);
              if (!locMatch) return false;
              
              const eLng = parseFloat(locMatch[1]);
              const eLat = parseFloat(locMatch[2]);
              
              // Rough 5km distance check
              const latDiff = Math.abs(eLat - cell.lat);
              const lngDiff = Math.abs(eLng - cell.lng);
              return latDiff < 0.045 && lngDiff < 0.045; // ~5km at mid latitudes
            });

            if (cellEvents.length === 0) continue;

            const cellSummary: EventSummary = {
              count: 0,
              verifiedCount: 0,
              weightedSeverity: 0,
              maxSeverity: 0,
              sourceBreakdown: {},
              aspectBuckets: new Set(),
              elevationRange: null,
            };

            for (const event of cellEvents) {
              cellSummary.count++;
              if (event.verification_status === 'verified' || event.verification_status === 'expert_verified') {
                cellSummary.verifiedCount++;
              }
              
              const recencyWeight = calculateRecencyWeight(event.timestamp, windowEnd);
              cellSummary.weightedSeverity += (event.severity || 3) * recencyWeight;
              cellSummary.maxSeverity = Math.max(cellSummary.maxSeverity, event.severity || 3);
              
              const source = event.source || 'unknown';
              cellSummary.sourceBreakdown[source] = (cellSummary.sourceBreakdown[source] || 0) + 1;
              
              if (event.aspect_bucket) {
                cellSummary.aspectBuckets.add(event.aspect_bucket);
              }
            }

            cellFeatures.push({
              region_name: regionName,
              cell_row: cell.row,
              cell_col: cell.col,
              window_start: windowStart.toISOString(),
              window_end: windowEnd.toISOString(),
              window_days: windowDays,
              total_event_count: cellSummary.count,
              verified_event_count: cellSummary.verifiedCount,
              weighted_severity_sum: Number(cellSummary.weightedSeverity.toFixed(2)),
              max_severity_in_window: cellSummary.maxSeverity,
              unique_aspect_buckets: Array.from(cellSummary.aspectBuckets),
              sources: cellSummary.sourceBreakdown,
              data_completeness_score: 1.0,
              materialized_at: new Date().toISOString(),
              materialization_job_id: job.id,
            });
          }

          if (cellFeatures.length > 0) {
            await supabase
              .from('recent_activity_features')
              .upsert(cellFeatures, {
                onConflict: 'region_name,cell_row,cell_col,window_start,window_end'
              });
            cellSummaries = cellFeatures.length;
          }
        }
      }
    }

    const result = {
      feature_id: feature?.id,
      region: regionName || 'global',
      window_days: windowDays,
      window_start: windowStart.toISOString(),
      window_end: windowEnd.toISOString(),
      total_events: regionSummary.count,
      verified_events: regionSummary.verifiedCount,
      weighted_severity: Number(regionSummary.weightedSeverity.toFixed(2)),
      max_severity: regionSummary.maxSeverity,
      sources: regionSummary.sourceBreakdown,
      cell_summaries_materialized: cellSummaries,
    };

    await supabase
      .from('compute_jobs')
      .update({ status: 'completed', result })
      .eq('id', job.id);

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
