import { expect, test, type Page } from '@playwright/test';

const REGION_NAME = 'Colorado Rockies';
const REGION_KEY = 'colorado_rockies';
const FORECAST_RUN_ID = 'shared-forecast-run-1';
const COMPATIBILITY_FORECAST_ID = 'compat-grid-1';
const MANIFEST_REF = 'forecast-products/avalanche/colorado/manifest.json';
const RUNOUT_REF = 'forecast-products/avalanche/colorado/runouts.json';
const HOUR_REFS = {
  0: 'forecast-products/avalanche/colorado/hour-0.json',
  6: 'forecast-products/avalanche/colorado/hour-6.json',
  12: 'forecast-products/avalanche/colorado/hour-12.json',
  18: 'forecast-products/avalanche/colorado/hour-18.json',
} as const;

test.describe.configure({ mode: 'serial' });

type ExplainabilityMode = 'tree' | 'fallback';

function buildCells(explainabilityMode: ExplainabilityMode, forecastHour: number) {
  const primaryProblem = forecastHour >= 12 ? 'wet_snow' : 'wind_slab';
  const treeShapCell = {
    row: 0,
    col: 0,
    lat: 39.62,
    lng: -106.41,
    lat_end: 39.66,
    lng_end: -106.37,
    risk_score: forecastHour >= 12 ? 4 : 3,
    probability: 0.73,
    hazard: 0.73,
    exposure: 0.48,
    vulnerability: 0.39,
    apt_eligible: true,
    public_eligible: true,
    problem_type: forecastHour >= 12 ? 'Wet Snow' : 'Wind Slab',
    problem_slug: primaryProblem,
    shap_values: explainabilityMode === 'fallback'
      ? { wind_loading: 0.34, new_snow_24h: 0.22, thaw_rate: 0.11 }
      : { wind_loading: 0.41, new_snow_24h: 0.27, terrain_trap: 0.15 },
    explainability_mode: explainabilityMode === 'fallback' ? 'heuristic_fallback' : 'tree_shap',
    explainability_reason: explainabilityMode === 'fallback' ? 'batch_tree_shap_unavailable' : null,
    surrogate_model_version: 'surrogate_rf_v1',
    shap_context: explainabilityMode === 'tree'
      ? {
          limiting_factor: 'wind_loading',
          fusion_method: 'surrogate_rf_v1',
          top_features: [
            { feature: 'wind_loading', label: 'Wind loading', shap_value: 0.41 },
            { feature: 'new_snow_24h', label: 'New snow 24h', shap_value: 0.27 },
            { feature: 'terrain_trap', label: 'Terrain trap', shap_value: 0.15 },
          ],
        }
      : null,
  };

  return [
    treeShapCell,
    {
      row: 0,
      col: 1,
      lat: 39.62,
      lng: -106.36,
      lat_end: 39.66,
      lng_end: -106.32,
      risk_score: 2,
      probability: 0.44,
      hazard: 0.44,
      exposure: 0.29,
      vulnerability: 0.23,
      apt_eligible: true,
      public_eligible: true,
      problem_type: 'No Distinct Avalanche Problem',
      problem_slug: 'no_distinct_avalanche_problem',
      shap_values: {},
    },
  ];
}

function buildManifest(explainabilityMode: ExplainabilityMode) {
  return {
    schemaVersion: 'forecast-manifest/v1',
    forecastRunId: FORECAST_RUN_ID,
    hazardType: 'avalanche',
    regionKey: REGION_KEY,
    regionName: REGION_NAME,
    forecastDate: '2026-05-04',
    issueTime: '2026-05-04T00:00:00.000Z',
    horizonHours: 24,
    gridSize: 20,
    bbox: [39.54, -106.5, 39.74, -106.28],
    status: 'ready',
    weatherSummary: {
      snowfall_24h: '14 cm',
      wind_speed: '26 km/h',
      temperature: '-5 C',
      precipitation: '5 mm',
      snow_depth: '92 cm',
    },
    forecastBulletin: {
      schema_version: 'forecast-bulletin/v1',
      standard: 'EAWS-style experimental',
      danger_level: 4,
      danger_label: 'High',
      primary_problem: 'wind_slab',
      problems: ['wind_slab', 'wet_snow'],
      critical_elevations: { min_m: 2400, max_m: 4000, band_step_m: 200 },
      critical_aspects: ['S', 'SW', 'W'],
      coverage: 'ready',
      confidence_state: 'reduced',
      confidence_reasons: ['high_uncertainty_share'],
      uncertainty_summary: {
        eligible_cell_count: 21,
        high_uncertainty_cell_count: 21,
        high_uncertainty_share: 1,
        low_sar_coverage_cell_count: 4,
        low_sar_coverage_share: 0.19,
      },
      issue_window_policy: 'daypart_v1',
      primary_window: 'day_1_evening',
      primary_window_policy: 'first_available_current_or_future_daypart_v1',
      peak_window: {
        window: 'day_2_morning',
        danger_level: 5,
        danger_label: 'Very High',
        primary_problem: 'wet_snow',
        forecast_hours: [30],
        local_start: '2026-05-05T06:00:00-06:00',
        local_end: '2026-05-05T07:00:00-06:00',
        selected_forecast_hour: 30,
        selected_hour_local_start: '2026-05-05T06:00:00-06:00',
        selected_hour_local_end: '2026-05-05T07:00:00-06:00',
      },
      dayparts: [
        { window: 'day_1_night', day_index: 1, daypart: 'night', danger_level: 3, danger_label: 'Considerable', primary_problem: 'wind_slab', forecast_hours: [0, 1, 2, 3, 4, 5], selected_forecast_hour: 0 },
        { window: 'day_1_morning', day_index: 1, daypart: 'morning', danger_level: 4, danger_label: 'High', primary_problem: 'wind_slab', forecast_hours: [6, 7, 8, 9, 10, 11], selected_forecast_hour: 6 },
        { window: 'day_1_afternoon', day_index: 1, daypart: 'afternoon', danger_level: 4, danger_label: 'High', primary_problem: 'wet_snow', forecast_hours: [12, 13, 14, 15, 16, 17], selected_forecast_hour: 12 },
        { window: 'day_1_evening', day_index: 1, daypart: 'evening', danger_level: 4, danger_label: 'High', primary_problem: 'wind_slab', forecast_hours: [18, 19, 20, 21, 22, 23], selected_forecast_hour: 18 },
      ],
      double_map: false,
      aggregation_notes: ['final-pre-mvp-smoke'],
      public_mask_profile: {
        profile: 'apt_then_snow_elevation_public_eligible_v1',
        stage_a: 'apt_30_50_v1',
        stage_b: 'snow_elevation_proxy_v1',
      },
      frequency_threshold_profile: 'local_grid_share_heuristic_v2',
      derived_from: {
        aggregation: 'highest_regional_level_by_cumulative_frequency',
        source_field: 'risk_score',
        base_metric: 'probability_risk_score',
        terrain_filter_profile: 'apt_30_50_v1',
        frequency_basis: 'cumulative_ge_threshold',
        frequency_class: 'some',
        ready_cell_count: 2,
        eligible_cell_count: 2,
        max_danger_cell_count: 1,
        selected_level_cell_count: 1,
        selected_level_cell_share: 0.5,
        problem_counts: { wind_slab: 1, wet_snow: 1 },
      },
    },
    modelMetadata: {
      tree_shap_status: explainabilityMode === 'tree' ? 'ready' : 'fallback_only',
    },
    runoutStorageRef: RUNOUT_REF,
    hours: [
      { forecastHour: 0, validTime: '2026-05-04T00:00:00.000Z', storageRef: HOUR_REFS[0], cellCount: 2, readyCellCount: 2, staleCellCount: 0 },
      { forecastHour: 6, validTime: '2026-05-04T06:00:00.000Z', storageRef: HOUR_REFS[6], cellCount: 2, readyCellCount: 2, staleCellCount: 0 },
      { forecastHour: 12, validTime: '2026-05-04T12:00:00.000Z', storageRef: HOUR_REFS[12], cellCount: 2, readyCellCount: 2, staleCellCount: 0 },
      { forecastHour: 18, validTime: '2026-05-04T18:00:00.000Z', storageRef: HOUR_REFS[18], cellCount: 2, readyCellCount: 2, staleCellCount: 0 },
    ],
  };
}

function buildRunResponse() {
  return {
    ok: true,
    stale: false,
    status: 'ready',
    source: 'forecast_runs',
    forecastRunId: FORECAST_RUN_ID,
    forecastId: COMPATIBILITY_FORECAST_ID,
    manifestPath: MANIFEST_REF,
    forecastBulletin: null,
    regionName: REGION_NAME,
    regionKey: REGION_KEY,
    forecastDate: '2026-05-04',
    hours: 24,
    weatherSummary: {},
    modelMetadata: {},
    message: null,
  };
}

async function installForecastAppMocks(
  page: Page,
  options: {
    explainabilityMode?: ExplainabilityMode;
    requestLog?: string[];
    adminMode?: boolean;
  } = {},
) {
  const explainabilityMode = options.explainabilityMode ?? 'tree';
  const manifest = buildManifest(explainabilityMode);
  const runResponse = buildRunResponse();
  const requestLog = options.requestLog ?? [];

  const adminUser = {
    id: 'final-pre-mvp-admin',
    aud: 'authenticated',
    role: 'authenticated',
    email: 'admin@insight-hub.local',
    app_metadata: { roles: ['admin'] },
    user_metadata: {},
  };

  page.on('request', (request) => {
    requestLog.push(request.url());
  });

  await page.route('**/auth/v1/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/token')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'final-pre-mvp-access-token',
          refresh_token: 'final-pre-mvp-refresh-token',
          token_type: 'bearer',
          expires_in: 3600,
          user: adminUser,
        }),
      });
      return;
    }

    if (url.includes('/user')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(options.adminMode ? adminUser : null),
      });
      return;
    }

    if (url.includes('/logout')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });

  await page.route('**/functions/v1/run-forecast', async (route) => {
    const body = route.request().postData() ?? '';
    if (body.includes('Himalayas')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: false, status: 'unavailable', source: 'forecast_runs', message: 'No published forecast artifact is available for Himalayas (Nepal) in the current hosted dataset.' }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(runResponse),
    });
  });

  await page.route('**/rest/v1/**', async (route) => {
    const url = route.request().url();
    const accept = route.request().headers().accept ?? '';
    const wantsObject = accept.includes('application/vnd.pgrst.object+json');

    if (url.includes('/forecast_runs')) {
      const runRecord = {
        id: FORECAST_RUN_ID,
        region_name: REGION_NAME,
        region_key: REGION_KEY,
        forecast_date: '2026-05-04',
        horizon_hours: 24,
        manifest_storage_ref: MANIFEST_REF,
        compatibility_forecast_grid_id: COMPATIBILITY_FORECAST_ID,
        forecast_bulletins: manifest.forecastBulletin,
        weather_summary: manifest.weatherSummary,
        model_metadata: manifest.modelMetadata,
        status: 'ready',
        created_at: '2026-05-04T00:00:00.000Z',
        publication_status: 'published',
        active: true,
        published_at: '2026-05-04T00:15:00.000Z',
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(wantsObject ? runRecord : [runRecord]),
      });
      return;
    }

    if (url.includes('/forecast_grids')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (url.includes('/avalanche_events')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (url.includes('/model_status')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          version: 'final-pre-mvp',
          f1_score: 0.72,
          pss_reported: 0.71,
          pss_gate_passed: true,
          promotion_gate_passed: true,
          drift_mode_state: 'guarded_monitoring_only',
          inference_backend: 'gpu',
          active_model_type: 'surrogate_rf_v1',
          active_model_version: '2026-04-30T16:56:43.493906+00:00',
          dynamic_model_candidate: {
            dynamic_model_type: 'mts_lstm_v1',
            dynamic_model_version: 'mts-lstm-42',
            blocked_gate: 'shadow_quality_gate',
          },
          capabilities: { mode: 'shadow_candidate' },
          satellite_detection_stats: { fallback_used: false },
        }),
      });
      return;
    }

    if (url.includes('/forecast_run_hours')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { forecast_run_id: FORECAST_RUN_ID, forecast_hour: 0, ready_cell_count: 2, stale_cell_count: 0 },
        ]),
      });
      return;
    }

    if (url.includes('/forecast_publication_events')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'publication-1', forecast_run_id: FORECAST_RUN_ID, stage: 'publish_complete', status: 'ok', detail: {}, created_at: '2026-05-04T00:15:00.000Z' },
        ]),
      });
      return;
    }

    if (url.includes('/compute_jobs') || url.includes('/field_reports') || url.includes('/evaluation_runs') || url.includes('/forecast_outcomes') || url.includes('/evaluation_metrics')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
      return;
    }

    if (url.includes('/system_config')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(wantsObject ? { gemini_usage: 0, gemini_spend_cap: 100 } : [{ gemini_usage: 0, gemini_spend_cap: 100 }]),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(wantsObject ? {} : []),
    });
  });

  await page.route('**/storage/v1/object/**', async (route) => {
    const url = route.request().url();
    let body: unknown = {};
    if (url.includes(MANIFEST_REF)) {
      body = manifest;
    } else if (url.includes(HOUR_REFS[0])) {
      body = { schema_version: 'forecast-hour/v1', forecast_run_id: FORECAST_RUN_ID, region_key: REGION_KEY, forecast_date: '2026-05-04', forecast_hour: 0, valid_time: '2026-05-04T00:00:00.000Z', cells: buildCells(explainabilityMode, 0) };
    } else if (url.includes(HOUR_REFS[6])) {
      body = { schema_version: 'forecast-hour/v1', forecast_run_id: FORECAST_RUN_ID, region_key: REGION_KEY, forecast_date: '2026-05-04', forecast_hour: 6, valid_time: '2026-05-04T06:00:00.000Z', cells: buildCells(explainabilityMode, 6) };
    } else if (url.includes(HOUR_REFS[12])) {
      body = { schema_version: 'forecast-hour/v1', forecast_run_id: FORECAST_RUN_ID, region_key: REGION_KEY, forecast_date: '2026-05-04', forecast_hour: 12, valid_time: '2026-05-04T12:00:00.000Z', cells: buildCells(explainabilityMode, 12) };
    } else if (url.includes(HOUR_REFS[18])) {
      body = { schema_version: 'forecast-hour/v1', forecast_run_id: FORECAST_RUN_ID, region_key: REGION_KEY, forecast_date: '2026-05-04', forecast_hour: 18, valid_time: '2026-05-04T18:00:00.000Z', cells: buildCells(explainabilityMode, 18) };
    } else if (url.includes(RUNOUT_REF)) {
      body = {
        schema_version: 'forecast-runouts/v1',
        forecast_run_id: FORECAST_RUN_ID,
        region_key: REGION_KEY,
        forecast_date: '2026-05-04',
        runout_polygons: [
          {
            polygon: [
              [-106.405, 39.625],
              [-106.375, 39.625],
              [-106.375, 39.655],
              [-106.405, 39.655],
              [-106.405, 39.625],
            ],
          },
        ],
      };
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  await page.route('https://overpass-api.de/api/interpreter', async (route) => {
    const body = route.request().postData() ?? '';
    const response = body.includes('highway')
      ? {
          elements: [
            {
              id: 101,
              type: 'way',
              tags: { highway: 'primary', name: 'Demo Pass Road' },
              geometry: [
                { lat: 39.63, lon: -106.404 },
                { lat: 39.646, lon: -106.378 },
              ],
            },
          ],
        }
      : {
          elements: [
            {
              id: 202,
              type: 'node',
              lat: 39.641,
              lon: -106.389,
              tags: { place: 'village', name: 'Demo Village' },
            },
          ],
        };

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });
}

function collectPageErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function gotoSharedForecast(
  page: Page,
  options: {
    url?: string;
    waitForDataBadge?: boolean;
  } = {},
) {
  const url = options.url ?? `/?forecast=${FORECAST_RUN_ID}&cell=0,0`;
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('top-control-zone')).toBeVisible({ timeout: 15000 });
  if (options.waitForDataBadge ?? true) {
    await expect(page.getByTestId('forecast-data-badge')).toContainText('PRECOMPUTED BATCH', { timeout: 15000 });
  }
}

for (let attempt = 1; attempt <= 5; attempt += 1) {
  test(`admin auth stays deterministic on repeated local sign-in attempt ${attempt}`, async ({ page }) => {
    const pageErrors = collectPageErrors(page);
    await installForecastAppMocks(page, { adminMode: true });

    await page.goto('/admin');
    await expect(page.getByText('Admin Access')).toBeVisible();
    await page.getByLabel('Password').fill(`phase6-admin-password-${attempt}`);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Admin Session', { exact: true })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: /sign out/i }).click();
    await expect(page.getByText('Admin Access')).toBeVisible({ timeout: 15000 });
    expect(pageErrors).toEqual([]);
  });
}

test('artifact-backed route loads manifest/hour/runout payloads from storage and avoids forecast_grids JSONB', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  const requestLog: string[] = [];
  await installForecastAppMocks(page, { requestLog });

  await gotoSharedForecast(page);

  expect(requestLog.some((url) => url.includes('/storage/v1/object/') && url.includes(MANIFEST_REF))).toBeTruthy();
  expect(requestLog.some((url) => url.includes('/storage/v1/object/') && url.includes(HOUR_REFS[0]))).toBeTruthy();
  expect(requestLog.some((url) => url.includes('/storage/v1/object/') && url.includes(RUNOUT_REF))).toBeTruthy();
  expect(requestLog.some((url) => url.includes('/rest/v1/forecast_grids'))).toBeFalsy();
  expect(pageErrors).toEqual([]);
});

test('explainability labels TreeSHAP explicitly when the surrogate artifact is present', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  await gotoSharedForecast(page, { waitForDataBadge: false });
  await expect(page.getByText('TreeSHAP Contributions')).toBeVisible({ timeout: 15000 });

  await expect(page.getByText('● TREESHAP')).toBeVisible();
  await expect(page.getByText(/origin: batch TreeSHAP artifact/i)).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('explainability falls back honestly when TreeSHAP is unavailable', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'fallback' });

  await gotoSharedForecast(page, { waitForDataBadge: false });
  await expect(page.getByText('Explainability Contributions')).toBeVisible({ timeout: 15000 });

  await expect(page.getByText('● FALLBACK')).toBeVisible();
  await expect(page.getByText(/origin: heuristic fallback context/i)).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('daypart chips and timeline stay synchronized under stress', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  await gotoSharedForecast(page, { url: `/?forecast=${FORECAST_RUN_ID}`, waitForDataBadge: false });
  await expect(page.getByTestId('daypart-chip-morning')).toBeVisible({ timeout: 15000 });

  await page.getByTestId('daypart-chip-morning').click();
  await expect(page.getByText('+6h')).toBeVisible();

  await page.getByTestId('daypart-chip-afternoon').click();
  await expect(page.getByText('+12h')).toBeVisible();

  await page.getByTestId('daypart-chip-evening').click();
  await expect(page.getByText('+18h')).toBeVisible();

  const slider = page.getByRole('slider').first();
  await slider.focus();
  await slider.press('Home');
  await expect(page.getByText(/\+\s*0\s*h/)).toBeVisible();

  await slider.press('End');
  await expect(page.getByText(/\+\s*2[23]\s*h/)).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('later-hour grid loads from storage on daypart click and renders non-empty cells', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  const requestLog: string[] = [];
  await installForecastAppMocks(page, { explainabilityMode: 'tree', requestLog });

  await gotoSharedForecast(page, { url: `/?forecast=${FORECAST_RUN_ID}`, waitForDataBadge: false });
  await expect(page.getByTestId('daypart-chip-morning')).toBeVisible({ timeout: 15000 });

  // Initially only hour-0 should be loaded
  expect(requestLog.some((url) => url.includes('/storage/v1/object/') && url.includes(HOUR_REFS[0]))).toBeTruthy();
  expect(requestLog.some((url) => url.includes('/storage/v1/object/') && url.includes(HOUR_REFS[6]))).toBeFalsy();

  // Click morning daypart (hour 6) - should trigger lazy load
  await page.getByTestId('daypart-chip-morning').click();
  await expect(page.getByText('+6h')).toBeVisible();

  // Wait for the hour-6 storage request to fire
  await expect.poll(
    () => requestLog.some((url) => url.includes('/storage/v1/object/') && url.includes(HOUR_REFS[6])),
    { timeout: 15000, message: 'hour-6 storage request should fire after daypart click' },
  ).toBeTruthy();

  // Verify the badge shows 2/24h loaded (hour 0 + hour 6)
  await expect(page.getByTestId('forecast-data-badge')).toContainText('2/24h', { timeout: 15000 });

  expect(pageErrors).toEqual([]);
});

test('expert-only lazy surfaces load on demand without breaking the forecast view', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  const requestLog: string[] = [];
  await installForecastAppMocks(page, { explainabilityMode: 'tree', requestLog });

  await gotoSharedForecast(page, { url: `/?forecast=${FORECAST_RUN_ID}`, waitForDataBadge: false });
  await page.getByLabel('Toggle Expert Mode').click();
  await expect(page.getByText('Impact Overlays')).toBeVisible({ timeout: 15000 });

  await page.getByLabel('Roads & Highways').click();
  await expect(page.getByText(/Runout warnings:/i)).toBeVisible({ timeout: 15000 });

  await page.getByRole('button', { name: 'Open 3D' }).click();
  await expect(page.getByRole('dialog', { name: '3D Neighborhood Risk Map' })).toBeVisible({ timeout: 15000 });

  expect(requestLog.some((url) => url.includes('overpass-api.de/api/interpreter'))).toBeTruthy();
  expect(pageErrors).toEqual([]);
});

test('responsive control layout stays within viewport on phone, tablet, compact desktop, and narrow desktop with sidebar open', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  const scenarios = [
    { name: 'phone', viewport: { width: 390, height: 844 }, expectsMobileTray: true },
    { name: 'tablet', viewport: { width: 768, height: 1024 }, expectsMobileTray: false },
    { name: 'compact-desktop', viewport: { width: 1024, height: 768 }, expectsMobileTray: false },
    { name: 'narrow-desktop', viewport: { width: 1366, height: 900 }, expectsMobileTray: false },
  ];

  for (const scenario of scenarios) {
    await page.setViewportSize(scenario.viewport);
    await gotoSharedForecast(page, `/?forecast=${FORECAST_RUN_ID}`);

    const overflowOk = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    expect(overflowOk, `${scenario.name} should not have horizontal overflow`).toBeTruthy();

    const topZone = page.getByTestId('top-control-zone');
    const bulletin = page.getByTestId('forecast-bulletin-root');
    const topBox = await topZone.boundingBox();
    const bulletinBox = await bulletin.boundingBox();

    expect(topBox?.x ?? 0).toBeGreaterThanOrEqual(0);
    expect((topBox?.x ?? 0) + (topBox?.width ?? 0)).toBeLessThanOrEqual(scenario.viewport.width + 1);
    expect(bulletinBox?.x ?? 0).toBeGreaterThanOrEqual(0);
    expect((bulletinBox?.x ?? 0) + (bulletinBox?.width ?? 0)).toBeLessThanOrEqual(scenario.viewport.width + 1);

    if (scenario.expectsMobileTray) {
      await expect(page.getByTestId('mobile-action-tray')).toBeVisible();
      await expect(page.getByTestId('desktop-action-tray')).toHaveCount(0);
    } else {
      const desktopTray = page.getByTestId('desktop-action-tray');
      await expect(desktopTray).toBeVisible();
      await expect(page.getByTestId('mobile-action-tray')).toHaveCount(0);
      const trayBox = await desktopTray.boundingBox();
      expect(trayBox?.x ?? 0).toBeGreaterThanOrEqual(0);
      expect((trayBox?.x ?? 0) + (trayBox?.width ?? 0)).toBeLessThanOrEqual(scenario.viewport.width + 1);
      expect((bulletinBox?.y ?? 0) + (bulletinBox?.height ?? 0)).toBeLessThanOrEqual((trayBox?.y ?? 0) + 1);
    }
  }

  expect(pageErrors).toEqual([]);
}, 60_000);

test('hour URL param sets initial slider position on load with forecast', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  await page.goto(`/?forecast=${FORECAST_RUN_ID}&hour=6`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('top-control-zone')).toBeVisible({ timeout: 15000 });

  // The slider should reflect hour 6, not 0
  await expect(page.getByText('+6h')).toBeVisible({ timeout: 15000 });
  expect(pageErrors).toEqual([]);
});

test('cell URL param pre-selects grid cell on load with forecast', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  await page.goto(`/?forecast=${FORECAST_RUN_ID}&cell=0,0`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('top-control-zone')).toBeVisible({ timeout: 15000 });

  // The risk dashboard should be visible with the selected cell's data
  await expect(page.getByText(/Danger Level/i)).toBeVisible({ timeout: 15000 });
  expect(pageErrors).toEqual([]);
});

test('hour and cell URL params work together on load', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  await page.goto(`/?forecast=${FORECAST_RUN_ID}&hour=6&cell=0,0`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('top-control-zone')).toBeVisible({ timeout: 15000 });

  await expect(page.getByText('+6h')).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Danger Level/i)).toBeVisible({ timeout: 15000 });
  expect(pageErrors).toEqual([]);
});

test('selecting Himalayas region shows honest unavailable state, not a fake grid', async ({ page }) => {
  const pageErrors = collectPageErrors(page);
  await installForecastAppMocks(page, { explainabilityMode: 'tree' });

  await gotoSharedForecast(page, { waitForDataBadge: false });
  await expect(page.getByTestId('top-control-zone')).toBeVisible({ timeout: 15000 });

  // Select Himalayas (Nepal) from the region dropdown
  await page.getByRole('combobox').click();
  await page.getByRole('option', { name: 'Himalayas (Nepal)' }).click();

  // The app should show an honest unavailable message, not a blank or fake grid
  await expect(page.getByText(/No published forecast artifact is available for Himalayas/i)).toBeVisible({ timeout: 15000 });

  // The forecast data badge should NOT show PRECOMPUTED BATCH for Himalayas
  const badge = page.getByTestId('forecast-data-badge');
  await expect(badge).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});
