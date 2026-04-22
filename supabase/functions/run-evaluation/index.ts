import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface MetricsResult {
  precisionRisk3: number;
  recallRisk3: number;
  f1Risk3: number;
  precisionRisk4: number;
  recallRisk4: number;
  f1Risk4: number;
  falseAlarmRate: number;
  ece: number; // Expected Calibration Error
  totalPredictions: number;
  totalEvents: number;
  riskDistribution: Record<number, number>;
}

function calculateMetrics(outcomes: any[]): MetricsResult {
  // Risk >= 3 metrics
  const risk3Predicted = outcomes.filter(o => o.predicted_risk_score >= 3);
  const risk3Events = outcomes.filter(o => o.predicted_risk_score >= 3 && o.event_observed);
  const risk3FalsePositives = outcomes.filter(o => o.predicted_risk_score >= 3 && !o.event_observed);
  
  // Risk >= 4 metrics
  const risk4Predicted = outcomes.filter(o => o.predicted_risk_score >= 4);
  const risk4Events = outcomes.filter(o => o.predicted_risk_score >= 4 && o.event_observed);
  
  // Overall events
  const totalEvents = outcomes.filter(o => o.event_observed).length;
  
  // Precision and Recall at risk >= 3
  const precisionRisk3 = risk3Predicted.length > 0 ? risk3Events.length / risk3Predicted.length : 0;
  const recallRisk3 = totalEvents > 0 ? risk3Events.length / totalEvents : 0;
  const f1Risk3 = (precisionRisk3 + recallRisk3) > 0 
    ? 2 * (precisionRisk3 * recallRisk3) / (precisionRisk3 + recallRisk3) 
    : 0;
  
  // Precision and Recall at risk >= 4
  const precisionRisk4 = risk4Predicted.length > 0 ? risk4Events.length / risk4Predicted.length : 0;
  const recallRisk4 = totalEvents > 0 ? risk4Events.length / totalEvents : 0;
  const f1Risk4 = (precisionRisk4 + recallRisk4) > 0 
    ? 2 * (precisionRisk4 * recallRisk4) / (precisionRisk4 + recallRisk4) 
    : 0;
  
  // False alarm rate
  const falseAlarmRate = risk3Predicted.length > 0 ? risk3FalsePositives.length / risk3Predicted.length : 0;
  
  // Expected Calibration Error (simplified)
  const riskBins: Record<number, { predicted: number; observed: number }> = {
    1: { predicted: 0, observed: 0 },
    2: { predicted: 0, observed: 0 },
    3: { predicted: 0, observed: 0 },
    4: { predicted: 0, observed: 0 },
    5: { predicted: 0, observed: 0 },
  };
  
  for (const o of outcomes) {
    const risk = o.predicted_risk_score;
    if (risk >= 1 && risk <= 5) {
      riskBins[risk].predicted++;
      if (o.event_observed) {
        riskBins[risk].observed++;
      }
    }
  }
  
  let eceSum = 0;
  let totalWeight = 0;
  for (const [risk, bin] of Object.entries(riskBins)) {
    if (bin.predicted > 0) {
      const predictedProb = parseInt(risk) / 5; // rough conversion
      const observedProb = bin.observed / bin.predicted;
      const weight = bin.predicted / outcomes.length;
      eceSum += weight * Math.abs(predictedProb - observedProb);
      totalWeight += weight;
    }
  }
  const ece = totalWeight > 0 ? eceSum / totalWeight : 0;
  
  // Risk distribution
  const riskDistribution: Record<number, number> = {};
  for (let i = 1; i <= 5; i++) {
    riskDistribution[i] = outcomes.filter(o => o.predicted_risk_score === i).length;
  }
  
  return {
    precisionRisk3: Number(precisionRisk3.toFixed(3)),
    recallRisk3: Number(recallRisk3.toFixed(3)),
    f1Risk3: Number(f1Risk3.toFixed(3)),
    precisionRisk4: Number(precisionRisk4.toFixed(3)),
    recallRisk4: Number(recallRisk4.toFixed(3)),
    f1Risk4: Number(f1Risk4.toFixed(3)),
    falseAlarmRate: Number(falseAlarmRate.toFixed(3)),
    ece: Number(ece.toFixed(3)),
    totalPredictions: outcomes.length,
    totalEvents,
    riskDistribution,
  };
}

function getSeasonFromDate(dateStr: string): string {
  const month = new Date(dateStr).getMonth();
  if (month >= 11 || month <= 1) return 'winter';
  if (month >= 2 && month <= 4) return 'spring';
  if (month >= 5 && month <= 7) return 'summer';
  return 'fall';
}

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  // BUG-03 fix: Wrap request parsing in try/catch for structured error response
  let requestBody: Record<string, unknown>;
  try {
    requestBody = await req.json();
  } catch (parseErr) {
    return new Response(JSON.stringify({ 
      error: 'Invalid JSON in request body',
      details: (parseErr as Error).message,
      code: 'INVALID_REQUEST'
    }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  const { 
    days_back: daysBack = 30,
    model_version: modelVersion,
    threshold_profile_version: thresholdVersion,
    hazard_type: hazardType = 'avalanche',
    regions,
    forecast_source: forecastSource = 'async',
  } = requestBody;

  if (hazardType !== 'avalanche') {
    return new Response(JSON.stringify({ 
      error: 'Only avalanche hazard type is currently supported',
      code: 'UNSUPPORTED_HAZARD_TYPE'
    }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  // BUG-03 fix: Validate environment variables
  const supabaseUrl = Deno.env.get('SUPABASE_URL');
  const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  
  if (!supabaseUrl || !serviceRoleKey) {
    return new Response(JSON.stringify({ 
      error: 'Server configuration error: missing database credentials',
      code: 'CONFIG_ERROR'
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  try {
    const supabase = createClient(supabaseUrl, serviceRoleKey);

    // Get model version if not specified
    let targetModelVersion = modelVersion;
    if (!targetModelVersion) {
      const { data: modelStatus } = await supabase
        .from('model_status')
        .select('version')
        .eq('hazard_type', hazardType)
        .limit(1)
        .maybeSingle();
      targetModelVersion = modelStatus?.version || 'unknown';
    }

    // Get threshold profile if not specified
    let targetThresholdVersion = thresholdVersion;
    if (!targetThresholdVersion) {
      const { data: threshold } = await supabase
        .from('threshold_profiles')
        .select('profile_version')
        .eq('hazard_type', hazardType)
        .eq('status', 'active')
        .limit(1)
        .maybeSingle();
      targetThresholdVersion = threshold?.profile_version || 'unknown';
    }

    // Create evaluation run record
    const evalStartDate = new Date();
    evalStartDate.setDate(evalStartDate.getDate() - daysBack);
    const evalEndDate = new Date();

    const { data: evalRun, error: evalErr } = await supabase
      .from('evaluation_runs')
      .insert({
        hazard_type: hazardType,
        run_name: `eval-${targetModelVersion}-${new Date().toISOString().split('T')[0]}`,
        model_version: targetModelVersion,
        label_version: 'v1.0.0',
        eval_start_date: evalStartDate.toISOString(),
        eval_end_date: evalEndDate.toISOString(),
        regions_evaluated: regions || [],
        threshold_profile_version: targetThresholdVersion,
        status: 'running',
      })
      .select('id')
      .maybeSingle();
    if (evalErr) throw evalErr;
    if (!evalRun?.id) throw new Error('Failed to create evaluation run');

    // Fetch outcomes for evaluation period
    let outcomesQuery = supabase
      .from('forecast_outcomes')
      .select('*')
      .eq('hazard_type', hazardType)
      .gte('created_at', evalStartDate.toISOString())
      .lte('created_at', evalEndDate.toISOString());

    if (forecastSource === 'async') {
      outcomesQuery = outcomesQuery.not('forecast_grid_id', 'is', null);
    } else if (forecastSource === 'legacy') {
      outcomesQuery = outcomesQuery.not('forecast_id', 'is', null).is('forecast_grid_id', null);
    }

    if (regions && regions.length > 0) {
      // Note: This requires joining with forecasts to get region
      // For now, we evaluate all and slice later
    }

    const { data: allOutcomes, error: outcomesErr } = await outcomesQuery;
    if (outcomesErr) throw outcomesErr;

    const outcomes = allOutcomes || [];

    // Calculate overall metrics
    const overallMetrics = calculateMetrics(outcomes);

    // Update evaluation run with overall metrics
    await supabase
      .from('evaluation_runs')
      .update({
        overall_precision_risk3: overallMetrics.precisionRisk3,
        overall_precision_risk4: overallMetrics.precisionRisk4,
        overall_recall: overallMetrics.recallRisk3,
        overall_false_alarm_rate: overallMetrics.falseAlarmRate,
        overall_ece: overallMetrics.ece,
        status: 'completed',
        completed_at: new Date().toISOString(),
      })
      .eq('id', evalRun.id);

    // Calculate slice metrics
    const sliceMetrics = [];

    // By region (from forecast_analytics which has region_name)
    const { data: forecastsWithRegions } = await supabase
      .from('forecast_analytics')
      .select('id, region_name')
      .in('id', [...new Set(outcomes.map(o => o.forecast_id))]);

    const forecastRegions: Record<string, string> = {};
    for (const f of (forecastsWithRegions || [])) {
      forecastRegions[f.id] = f.region_name || 'Unknown';
    }

    const outcomesByRegion: Record<string, any[]> = {};
    for (const o of outcomes) {
      const region = forecastRegions[o.forecast_id] || 'Unknown';
      if (!outcomesByRegion[region]) outcomesByRegion[region] = [];
      outcomesByRegion[region].push(o);
    }

    for (const [region, regionOutcomes] of Object.entries(outcomesByRegion)) {
      const metrics = calculateMetrics(regionOutcomes);
      sliceMetrics.push({
        evaluation_run_id: evalRun.id,
        slice_type: 'region',
        slice_value: region,
        total_forecasts: [...new Set(regionOutcomes.map(o => o.forecast_id))].length,
        total_cells: regionOutcomes.length,
        observed_events: metrics.totalEvents,
        precision_risk3: metrics.precisionRisk3,
        recall_risk3: metrics.recallRisk3,
        f1_risk3: metrics.f1Risk3,
        precision_risk4: metrics.precisionRisk4,
        recall_risk4: metrics.recallRisk4,
        f1_risk4: metrics.f1Risk4,
        ece: metrics.ece,
        false_alarm_rate: metrics.falseAlarmRate,
        false_positives: Math.floor(metrics.falseAlarmRate * regionOutcomes.filter(o => o.predicted_risk_score >= 3).length),
        true_positives: regionOutcomes.filter(o => o.predicted_risk_score >= 3 && o.event_observed).length,
        risk_distribution: metrics.riskDistribution,
      });
    }

    // By season
    const outcomesBySeason: Record<string, any[]> = {};
    for (const o of outcomes) {
      // Get forecast date for season
      const season = getSeasonFromDate(o.outcome_window_start);
      if (!outcomesBySeason[season]) outcomesBySeason[season] = [];
      outcomesBySeason[season].push(o);
    }

    for (const [season, seasonOutcomes] of Object.entries(outcomesBySeason)) {
      const metrics = calculateMetrics(seasonOutcomes);
      sliceMetrics.push({
        evaluation_run_id: evalRun.id,
        slice_type: 'season',
        slice_value: season,
        total_forecasts: [...new Set(seasonOutcomes.map(o => o.forecast_id))].length,
        total_cells: seasonOutcomes.length,
        observed_events: metrics.totalEvents,
        precision_risk3: metrics.precisionRisk3,
        recall_risk3: metrics.recallRisk3,
        f1_risk3: metrics.f1Risk3,
        precision_risk4: metrics.precisionRisk4,
        recall_risk4: metrics.recallRisk4,
        f1_risk4: metrics.f1Risk4,
        ece: metrics.ece,
        false_alarm_rate: metrics.falseAlarmRate,
        false_positives: Math.floor(metrics.falseAlarmRate * seasonOutcomes.filter(o => o.predicted_risk_score >= 3).length),
        true_positives: seasonOutcomes.filter(o => o.predicted_risk_score >= 3 && o.event_observed).length,
        risk_distribution: metrics.riskDistribution,
      });
    }

    // By elevation band (estimated from cell row in outcomes)
    const elevationBands: Record<string, any[]> = {};
    for (const o of outcomes) {
      // Rough elevation from row position
      const elevMin = 1000 + (o.cell_row / 20) * 3500;
      const band = `${Math.floor(elevMin / 500) * 500}-${Math.floor(elevMin / 500) * 500 + 500}`;
      if (!elevationBands[band]) elevationBands[band] = [];
      elevationBands[band].push(o);
    }

    for (const [band, bandOutcomes] of Object.entries(elevationBands)) {
      const metrics = calculateMetrics(bandOutcomes);
      sliceMetrics.push({
        evaluation_run_id: evalRun.id,
        slice_type: 'elevation_band',
        slice_value: band,
        total_forecasts: [...new Set(bandOutcomes.map(o => o.forecast_id))].length,
        total_cells: bandOutcomes.length,
        observed_events: metrics.totalEvents,
        precision_risk3: metrics.precisionRisk3,
        recall_risk3: metrics.recallRisk3,
        f1_risk3: metrics.f1Risk3,
        precision_risk4: metrics.precisionRisk4,
        recall_risk4: metrics.recallRisk4,
        f1_risk4: metrics.f1Risk4,
        ece: metrics.ece,
        false_alarm_rate: metrics.falseAlarmRate,
        false_positives: Math.floor(metrics.falseAlarmRate * bandOutcomes.filter(o => o.predicted_risk_score >= 3).length),
        true_positives: bandOutcomes.filter(o => o.predicted_risk_score >= 3 && o.event_observed).length,
        risk_distribution: metrics.riskDistribution,
      });
    }

    // Insert slice metrics
    if (sliceMetrics.length > 0) {
      await supabase.from('evaluation_metrics').insert(sliceMetrics);
    }

    const result = {
      evaluation_run_id: evalRun.id,
      model_version: targetModelVersion,
      threshold_profile_version: targetThresholdVersion,
      days_evaluated: daysBack,
      total_outcomes: outcomes.length,
      overall_metrics: overallMetrics,
      slices_evaluated: sliceMetrics.length,
    };

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
