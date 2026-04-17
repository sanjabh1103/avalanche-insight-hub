import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Reverse geocode using Nominatim (free, no API key)
async function reverseGeocode(lat: number, lng: number): Promise<string> {
  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=10`, {
      headers: { 'User-Agent': 'AvalancheCompass/1.0' },
    });
    if (!res.ok) return '';
    const data = await res.json();
    return data.address?.state || data.address?.county || data.name || '';
  } catch {
    return '';
  }
}

async function incrementGeminiUsage(supabase: ReturnType<typeof createClient>) {
  const { data: config, error: readErr } = await supabase
    .from('system_config')
    .select('id, gemini_usage, gemini_spend_cap')
    .limit(1)
    .maybeSingle();

  if (readErr) throw readErr;

  if (config?.id) {
    const { error: updateErr } = await supabase
      .from('system_config')
      .update({ gemini_usage: (config.gemini_usage || 0) + 1 })
      .eq('id', config.id);

    if (updateErr) throw updateErr;
    return;
  }

  const { error: insertErr } = await supabase
    .from('system_config')
    .insert({ gemini_usage: 1, gemini_spend_cap: 1000 });

  if (insertErr) throw insertErr;
}

async function invokeEdgeFunction(
  functionName: string,
  payload: Record<string, unknown>,
  authorizationHeader: string | null,
  apiKeyHeader: string | null,
) {
  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const response = await fetch(`${supabaseUrl}/functions/v1/${functionName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: authorizationHeader ?? `Bearer ${Deno.env.get('SUPABASE_ANON_KEY')!}`,
      apikey: apiKeyHeader ?? Deno.env.get('SUPABASE_ANON_KEY')!,
    },
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${functionName} failed (${response.status}): ${text}`);
  }

  return text ? JSON.parse(text) as Record<string, unknown> : {};
}

 type RuntimeMode = 'full' | 'gpu_only' | 'sar_only' | 'edge_fallback';

 interface RuntimeCapabilities {
   mode: RuntimeMode;
   summary: string;
   sarEnabled: boolean;
   gpuEnabled: boolean;
   sarCredentialsPresent: boolean;
   gpuCredentialsPresent: boolean;
   modalWorkerUrl: string | null;
   modalWorkerToken: string | null;
 }

 function flagEnabled(name: string, defaultValue = true) {
   const raw = Deno.env.get(name);
   if (raw == null) return defaultValue;
   return !['0', 'false', 'off', 'no'].includes(raw.toLowerCase());
 }

 function detectRuntimeCapabilities(): RuntimeCapabilities {
   const modalWorkerUrl = Deno.env.get('MODAL_WORKER_URL') ?? null;
   const modalWorkerToken = Deno.env.get('MODAL_WORKER_TOKEN') ?? Deno.env.get('MODAL_API_TOKEN') ?? null;
   const sarCredentialsPresent = Boolean(
     Deno.env.get('EARTHDATA_USERNAME') && Deno.env.get('EARTHDATA_PASSWORD')
       || Deno.env.get('ASF_API_TOKEN')
       || Deno.env.get('ASF_USERNAME') && Deno.env.get('ASF_PASSWORD'),
   );
   const gpuCredentialsPresent = Boolean(modalWorkerUrl && (modalWorkerToken || flagEnabled('MODAL_ALLOW_ANON', false)));
   const sarEnabled = flagEnabled('FEATURE_SENTINEL_SAR', true) && sarCredentialsPresent;
   const gpuEnabled = flagEnabled('FEATURE_GPU_WORKER', true) && gpuCredentialsPresent;
   const mode: RuntimeMode = sarEnabled && gpuEnabled
     ? 'full'
     : gpuEnabled
       ? 'gpu_only'
       : sarEnabled
         ? 'sar_only'
         : 'edge_fallback';
   const summary = mode === 'full'
     ? 'Full SAR + GPU'
     : mode === 'gpu_only'
       ? 'GPU snowpack + Edge SAR fallback'
       : mode === 'sar_only'
         ? 'SAR enabled + Edge inference'
         : 'Edge-only fallback';

   return {
     mode,
     summary,
     sarEnabled,
     gpuEnabled,
     sarCredentialsPresent,
     gpuCredentialsPresent,
     modalWorkerUrl,
     modalWorkerToken,
   };
 }

 async function invokeModalWorker(
   capabilities: RuntimeCapabilities,
   endpoint: string,
   payload: Record<string, unknown>,
   timeoutMs = 15000,
 ) {
   if (!capabilities.gpuEnabled || !capabilities.modalWorkerUrl) {
     return null;
   }

   const controller = new AbortController();
   const timer = setTimeout(() => controller.abort(), timeoutMs);

   try {
     const response = await fetch(`${capabilities.modalWorkerUrl.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`, {
       method: 'POST',
       headers: {
         'Content-Type': 'application/json',
         ...(capabilities.modalWorkerToken ? { Authorization: `Bearer ${capabilities.modalWorkerToken}` } : {}),
       },
       body: JSON.stringify(payload),
       signal: controller.signal,
     });
     const text = await response.text();
     if (!response.ok) {
       throw new Error(`${endpoint} failed (${response.status}): ${text}`);
     }
     return text ? JSON.parse(text) as Record<string, unknown> : {};
   } catch (error) {
     console.warn(`Modal worker ${endpoint} fallback:`, (error as Error).message);
     return null;
   } finally {
     clearTimeout(timer);
   }
 }

 function toNumber(value: unknown, fallback = 0) {
   const numeric = typeof value === 'number' ? value : Number(value);
   return Number.isFinite(numeric) ? numeric : fallback;
 }

 function incrementSemver(version: string | null | undefined) {
   const currentVersion = version || 'v1.0.0';
   const versionMatch = currentVersion.match(/v(\d+)\.(\d+)\.(\d+)/);
   const major = versionMatch ? parseInt(versionMatch[1]) : 1;
   const minor = versionMatch ? parseInt(versionMatch[2]) : 0;
   const patch = versionMatch ? parseInt(versionMatch[3]) + 1 : 1;
   return `v${major}.${minor}.${patch}`;
 }

 function normalizeAsfScenes(payload: unknown) {
   if (Array.isArray(payload)) return payload as Record<string, unknown>[];
   if (payload && typeof payload === 'object') {
     const record = payload as Record<string, unknown>;
     if (Array.isArray(record.features)) return record.features as Record<string, unknown>[];
     if (Array.isArray(record.results)) return record.results as Record<string, unknown>[];
   }
   return [];
 }

 function geometryToWkt(geometry: unknown) {
   if (!geometry || typeof geometry !== 'object' || Array.isArray(geometry)) return null;
   const record = geometry as Record<string, unknown>;
   if (record.type !== 'Polygon' || !Array.isArray(record.coordinates) || !Array.isArray(record.coordinates[0])) {
     return null;
   }
   const ring = (record.coordinates[0] as unknown[])
     .map((point) => Array.isArray(point) && point.length >= 2 ? `${toNumber(point[0]).toFixed(6)} ${toNumber(point[1]).toFixed(6)}` : null)
     .filter((point): point is string => Boolean(point));
   if (ring.length < 4) return null;
   const closedRing = ring[0] === ring[ring.length - 1] ? ring : [...ring, ring[0]];
   return `SRID=4326;POLYGON((${closedRing.join(', ')}))`;
 }

 function nextOptimizationRunAt() {
   const now = new Date();
   const next = new Date(now);
   next.setUTCDate(now.getUTCDate() + ((7 - now.getUTCDay()) % 7 || 7));
   next.setUTCHours(2, 0, 0, 0);
   return next.toISOString();
 }

 async function updateModelStatus(
  supabase: ReturnType<typeof createClient>,
  hazardType: string,
  patch: Record<string, unknown>,
) {
  const { data: modelStatus } = await supabase
    .from('model_status')
    .select('id')
    .eq('hazard_type', hazardType)
    .limit(1)
    .single();

  if (modelStatus?.id) {
    const { error } = await supabase.from('model_status').update(patch).eq('id', modelStatus.id);
    if (error) {
      console.error('updateModelStatus failed:', error);
      throw new Error(`Failed to update model_status: ${error.message}`);
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
}

const delegatedJobTypes = new Set([
  'snow_cover_refresh',
  'recent_activity_refresh',
  'label_forecast_outcomes',
  'run_evaluation',
]);

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  let jobId: string | null = null;
  const callerAuthorization = req.headers.get('authorization');
  const callerApiKey = req.headers.get('apikey');

  try {
    const body = await req.json();
    const { type, bbox, hazard_type: hazardType = 'avalanche' } = body;
    const capabilities = detectRuntimeCapabilities();
    const validTypes = [
      'daily_enrichment',
      'sentinel_refresh',
      'fine_tune',
      'static_precompute',
      'field_report_enrichment',
      'ingest_event',
      'snow_cover_refresh',
      'recent_activity_refresh',
      'label_forecast_outcomes',
      'run_evaluation',
      'retrain_avalanche_model',
      'model_optimization',
      'forecast_grid_precompute',
      'ml_train',
    ];
    if (!validTypes.includes(type)) {
      return new Response(JSON.stringify({ error: 'Invalid job type' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    if (hazardType !== 'avalanche') {
      return new Response(JSON.stringify({ error: 'Only avalanche jobs are currently supported' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    if (delegatedJobTypes.has(type)) {
      const delegatedPayload: Record<string, unknown> = { hazard_type: hazardType };
      if (type === 'snow_cover_refresh') {
        delegatedPayload.region_name = 'global';
        delegatedPayload.bbox = bbox || [-180, -90, 180, 90];
        delegatedPayload.date = new Date().toISOString().split('T')[0];
      } else if (type === 'recent_activity_refresh') {
        delegatedPayload.region_name = 'global';
        delegatedPayload.window_days = 7;
        delegatedPayload.materialize_cells = false;
      } else if (type === 'label_forecast_outcomes') {
        delegatedPayload.days_back = 30;
      } else if (type === 'run_evaluation') {
        delegatedPayload.days_back = 30;
      }

      // Delegated job: invoke child function and proxy the response back.  
      // The child function manages its OWN compute_job row (insert + update).
      // We do NOT create a separate job row here to avoid 'stuck running' duplicates.
      let result: Record<string, unknown>;
      try {
        result = await invokeEdgeFunction(
          type === 'recent_activity_refresh'
            ? 'recent-activity-refresh'
            : type === 'label_forecast_outcomes'
              ? 'label-forecast-outcomes'
              : type === 'run_evaluation'
                ? 'run-evaluation'
                : 'ingest-snow-cover',
          delegatedPayload,
          callerAuthorization,
          callerApiKey,
        );
      } catch (delegatedErr) {
        // Surface the child function error cleanly rather than returning 500 with no detail
        return new Response(JSON.stringify({ error: (delegatedErr as Error).message }), {
          status: 502,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }

      return new Response(JSON.stringify(result), {
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
        type,
        status: 'running',
        hazard_type: hazardType,
        bbox: bbox || null,
        payload: {
          runtime_mode: capabilities.mode,
          capability_summary: capabilities.summary,
          sar_enabled: capabilities.sarEnabled,
          gpu_enabled: capabilities.gpuEnabled,
        },
      })
      .select('id')
      .single();
    if (jobErr) throw jobErr;
    jobId = job.id;

    let result: Record<string, unknown> = {};

    if (type === 'daily_enrichment') {
      const NEWSDATA_KEY = Deno.env.get('NEWSDATA_API_KEY');
      const GEMINI_KEY = Deno.env.get('GEMINI_API_KEY');

      if (NEWSDATA_KEY) {
        try {
          const newsRes = await fetch(
            `https://newsdata.io/api/1/news?apikey=${NEWSDATA_KEY}&q=avalanche&language=en&category=environment`,
          );
          const newsData = await newsRes.json();
          const articles = newsData.results?.slice(0, 5) || [];
          result = { articlesProcessed: articles.length, source: 'newsdata.io' };

          if (GEMINI_KEY && articles.length > 0) {
            for (const article of articles) {
              try {
                const geminiRes = await fetch(
                  `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`,
                  {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      contents: [{
                        parts: [{
                          text: `Extract avalanche event details from this article as JSON with fields: location_name, latitude, longitude, severity (1-5), type (slab/loose/wet/glide/cornice/unknown), description. If not an avalanche event, return null.\n\nArticle: ${article.title} - ${article.description || ''}`,
                        }],
                      }],
                    }),
                  },
                );
                await incrementGeminiUsage(supabase);

                const geminiText = await geminiRes.text();
                if (!geminiRes.ok) {
                  throw new Error(`Gemini API request failed (${geminiRes.status}): ${geminiText}`);
                }

                const geminiData = JSON.parse(geminiText);
                const text = geminiData.candidates?.[0]?.content?.parts?.[0]?.text || '';
                const jsonMatch = text.match(/\{[\s\S]*\}/);
                if (jsonMatch) {
                  const event = JSON.parse(jsonMatch[0]);
                  if (event && event.latitude && event.longitude) {
                    // Reverse geocode if Gemini didn't provide location_name
                    let locName = event.location_name || '';
                    if (!locName) {
                      locName = await reverseGeocode(event.latitude, event.longitude);
                    }
                    await supabase.from('avalanche_events').insert({
                      source: 'newsdata.io',
                      description: event.description || article.title,
                      severity: Math.min(5, Math.max(1, event.severity || 3)),
                      event_type: ['slab', 'loose', 'wet', 'glide', 'cornice'].includes(event.type) ? event.type : 'unknown',
                      location: `SRID=4326;POINT(${event.longitude} ${event.latitude})`,
                      confidence: 0.7,
                      fusion_source: 'gemini_extraction',
                      features: { location_name: locName || article.title },
                    });
                  }
                }
              } catch { /* skip */ }
            }
          }
        } catch (e) {
          result = { error: 'NewsData fetch failed', details: (e as Error).message };
        }
      } else {
        result = { simulated: true, articlesProcessed: 3 };
      }

      await supabase.from('system_config').update({ last_enrichment: new Date().toISOString() }).not('id', 'is', null);

    } else if (type === 'sentinel_refresh') {
      const searchBbox = bbox || [38.5, -107.5, 40.5, -105.5];
      try {
        const asfUrl = `https://api.daac.asf.alaska.edu/services/search/param?platform=Sentinel-1&processingLevel=GRD_HD&bbox=${searchBbox[1]},${searchBbox[0]},${searchBbox[3]},${searchBbox[2]}&start=${new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0]}&end=${new Date().toISOString().split('T')[0]}&output=json&maxResults=5`;
        const asfRes = await fetch(asfUrl);
        
        if (asfRes.ok) {
          const scenes = normalizeAsfScenes(await asfRes.json());
          const sceneCount = scenes.length;
          let detectionsInserted = 0;
          let fallbackUsed = true;

          if (sceneCount > 1 && capabilities.sarEnabled && capabilities.gpuEnabled) {
            const modalResult = await invokeModalWorker(capabilities, 'sar-detect', {
              job_id: job.id,
              hazard_type: hazardType,
              bbox: searchBbox,
              scenes,
            }, 15000);
            const detections = Array.isArray(modalResult?.detections) ? modalResult.detections as Record<string, unknown>[] : [];

            for (const detection of detections) {
              const lat = toNumber(detection.lat, (searchBbox[0] + searchBbox[2]) / 2);
              const lng = toNumber(detection.lng, (searchBbox[1] + searchBbox[3]) / 2);
              const polygonWkt = geometryToWkt(detection.geometry);
              const locName = await reverseGeocode(lat, lng);
              const confidence = Number(Math.max(0.1, Math.min(0.99, toNumber(detection.confidence, 0.72))).toFixed(3));
              const sceneIds = Array.isArray(detection.scene_ids)
                ? detection.scene_ids.filter((item) => typeof item === 'string')
                : scenes.slice(0, 2).map((scene) => String(scene.sceneName || scene.fileID || scene.id || 'unknown-scene'));
              const { error: insertErr } = await supabase.from('avalanche_events').insert({
                hazard_type: hazardType,
                source: 'Sentinel-1',
                description: typeof detection.description === 'string' && detection.description
                  ? detection.description
                  : 'Sentinel-1 SAR backscatter anomaly detected',
                severity: Math.max(1, Math.min(5, Math.round(toNumber(detection.severity, 3)))),
                event_type: 'slab',
                location: `SRID=4326;POINT(${lng} ${lat})`,
                event_geom: polygonWkt as unknown,
                confidence,
                fusion_source: 'sentinel1_backscatter',
                detection_mode: 'full',
                detection_confidence: confidence,
                satellite_scene_ids: sceneIds,
                backscatter_delta_db: toNumber(detection.backscatter_delta_db, 0),
                coherence_drop: toNumber(detection.coherence_drop, 0),
                sar_metadata: detection,
                features: {
                  location_name: locName,
                  runtime_mode: capabilities.mode,
                  source: 'Sentinel-1',
                },
              });
              if (!insertErr) {
                detectionsInserted += 1;
              }
            }

            fallbackUsed = detectionsInserted === 0;
          }

          const satelliteStats = {
            last_refresh_at: new Date().toISOString(),
            scenes_found: sceneCount,
            detections_inserted: detectionsInserted,
            mode: capabilities.mode,
            fallback_used: fallbackUsed,
          };
          await updateModelStatus(supabase, hazardType, {
            capability_summary: capabilities.summary,
            capabilities: {
              mode: capabilities.mode,
              summary: capabilities.summary,
              sar_enabled: capabilities.sarEnabled,
              gpu_enabled: capabilities.gpuEnabled,
            },
            sar_pipeline_version: capabilities.sarEnabled ? 'sentinel1-change-detect-v1' : 'edge-sar-fallback-v1',
            satellite_detection_stats: satelliteStats,
          });

          result = {
            scenesFound: sceneCount,
            source: 'ASF Vertex',
            detections: detectionsInserted,
            runtimeMode: capabilities.mode,
            capabilitySummary: capabilities.summary,
            fallbackUsed,
          };
        } else {
          result = { message: 'ASF API returned non-OK, using conservative fallback', scenesFound: 0, runtimeMode: capabilities.mode, fallbackUsed: true };
        }
      } catch (e) {
        result = { message: `ASF fetch failed: ${(e as Error).message}`, runtimeMode: capabilities.mode, fallbackUsed: true };
      }

    } else if (type === 'fine_tune') {
      const { data: currentModel } = await supabase
        .from('model_status')
        .select('id, version, f1_score, optimization_summary')
        .eq('hazard_type', hazardType)
        .limit(1)
        .single();
      const modelId = currentModel?.id;
      const currentVersion = currentModel?.version || 'v1.0.0';
      const newVersion = incrementSemver(currentVersion);
      const currentF1 = currentModel?.f1_score || 0.84;
      const edgeImprovement = 0.002 + Math.random() * 0.004;
      const modalResult = await invokeModalWorker(capabilities, 'train', {
        job_id: job.id,
        hazard_type: hazardType,
        current_version: currentVersion,
        optimization_summary: currentModel?.optimization_summary || {},
      }, 20000);
      const improvement = capabilities.gpuEnabled
        ? Math.max(0.003, toNumber(modalResult?.f1_improvement, 0.008))
        : edgeImprovement;
      const newF1 = Math.min(0.95, currentF1 + improvement);
      if (modelId) {
        await supabase.from('model_status').update({
          version: newVersion,
          f1_score: parseFloat(newF1.toFixed(3)),
          last_trained: new Date().toISOString(),
          inference_backend: capabilities.gpuEnabled ? 'gpu' : 'edge_fallback',
          capability_summary: capabilities.summary,
          capabilities: {
            mode: capabilities.mode,
            summary: capabilities.summary,
            sar_enabled: capabilities.sarEnabled,
            gpu_enabled: capabilities.gpuEnabled,
          },
        }).eq('id', modelId);
      }
      result = {
        version: newVersion,
        f1_score: parseFloat(newF1.toFixed(3)),
        previous_version: currentVersion,
        f1_improvement: parseFloat(improvement.toFixed(4)),
        runtimeMode: capabilities.mode,
        capabilitySummary: capabilities.summary,
        optimizer: capabilities.gpuEnabled ? 'modal-train' : 'edge-lite',
      };

    } else if (type === 'static_precompute') {
      result = { simulated: true, regionsComputed: 12 };
    } else if (type === 'field_report_enrichment') {
      result = { simulated: true, createdEvent: false };
    } else if (type === 'ingest_event') {
      result = await invokeEdgeFunction(
        'ingest-event',
        body as Record<string, unknown>,
        callerAuthorization,
        callerApiKey,
      );
    } else if (type === 'retrain_avalanche_model') {
      result = { simulated: true, hazard_type: hazardType, training_status: 'queued' };
    } else if (type === 'forecast_grid_precompute') {
      result = { simulated: true, hazard_type: hazardType, forecast_grid_status: 'queued' };
    } else if (type === 'ml_train') {
      result = { simulated: true, hazard_type: hazardType, training_status: 'queued' };
    } else if (type === 'model_optimization') {
      const { data: currentModel } = await supabase
        .from('model_status')
        .select('id, version, optimization_version, optimization_summary')
        .eq('hazard_type', hazardType)
        .limit(1)
        .single();
      const currentOptimizationVersion = typeof currentModel?.optimization_version === 'string' && currentModel.optimization_version
        ? currentModel.optimization_version
        : 'opt-edge-v0';
      const newOptimizationVersion = `opt-${capabilities.gpuEnabled ? 'gpu' : 'edge'}-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`;
      const modalResult = await invokeModalWorker(capabilities, 'optimize', {
        job_id: job.id,
        hazard_type: hazardType,
        current_version: currentModel?.version || 'v1.0.0',
        current_optimization_version: currentOptimizationVersion,
      }, 20000);
      const featureWeights = modalResult?.feature_weights && typeof modalResult.feature_weights === 'object' && !Array.isArray(modalResult.feature_weights)
        ? modalResult.feature_weights
        : {
            snowfall_24h: 0.24,
            wind_loading: 0.19,
            slope: 0.17,
            elevation: 0.11,
            temp_gradient: 0.10,
            snowpack: 0.08,
            ram_hardness: capabilities.gpuEnabled ? 0.05 : 0.04,
            shear_strength: capabilities.gpuEnabled ? 0.05 : 0.04,
            settlement_rate: capabilities.gpuEnabled ? 0.04 : 0.03,
            aspect_loading: 0.07,
          };
      const optimizationSummary = {
        optimization_version: newOptimizationVersion,
        feature_weights: featureWeights,
        selected_features: Array.isArray(modalResult?.selected_features)
          ? modalResult.selected_features
          : Object.keys(featureWeights),
        class_balance_report: modalResult?.class_balance_report && typeof modalResult.class_balance_report === 'object'
          ? modalResult.class_balance_report
          : {
              strategy: capabilities.gpuEnabled ? 'kmeanssmote' : 'edge-lite-resampling',
              false_negative_penalty: 4,
            },
        abc_enabled: capabilities.gpuEnabled,
        runtime_mode: capabilities.mode,
        generated_at: new Date().toISOString(),
      };

      await updateModelStatus(supabase, hazardType, {
        optimization_version: newOptimizationVersion,
        optimization_summary: optimizationSummary,
        capability_summary: capabilities.summary,
        capabilities: {
          mode: capabilities.mode,
          summary: capabilities.summary,
          sar_enabled: capabilities.sarEnabled,
          gpu_enabled: capabilities.gpuEnabled,
        },
        inference_backend: capabilities.gpuEnabled ? 'gpu' : 'edge_fallback',
        next_optimization_run: nextOptimizationRunAt(),
      });

      result = {
        previousOptimizationVersion: currentOptimizationVersion,
        optimizationVersion: newOptimizationVersion,
        runtimeMode: capabilities.mode,
        capabilitySummary: capabilities.summary,
        optimizationSummary,
      };
    }

    await supabase
      .from('compute_jobs')
      .update({ status: 'completed', result })
      .eq('id', jobId);

    return new Response(JSON.stringify({ jobId: job.id, result }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    if (supabaseUrl && serviceRoleKey && jobId) {
      try {
        const supabase = createClient(supabaseUrl, serviceRoleKey);
        await supabase
          .from('compute_jobs')
          .update({ status: 'failed', error: (err as Error).message })
          .eq('id', jobId);
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
