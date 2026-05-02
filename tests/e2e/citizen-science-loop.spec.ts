import { expect, test, type Page } from '@playwright/test';

const REGION_NAME = 'Himalayas (Nepal)';
const REGION_KEY = 'himalayas_nepal';
const FORECAST_RUN_ID = 'citizen-science-run-1';
const BBOX = [27.8, 86.7, 28.1, 87.1] as const;
const MANIFEST_REF = 'forecast-artifacts/manifests/citizen-science-run-1.json';
const HOUR_REFS = {
  0: 'forecast-artifacts/hours/citizen-science-run-1-hour-0.json',
  6: 'forecast-artifacts/hours/citizen-science-run-1-hour-6.json',
  12: 'forecast-artifacts/hours/citizen-science-run-1-hour-12.json',
  18: 'forecast-artifacts/hours/citizen-science-run-1-hour-18.json',
} as const;

function buildCells(forecastHour: number) {
  return [
    {
      row: 0,
      col: 0,
      lat: 27.9,
      lng: 86.82,
      lat_end: 27.95,
      lng_end: 86.87,
      risk_score: forecastHour >= 12 ? 4 : 3,
      probability: 0.71,
      hazard: 0.71,
      exposure: 0.46,
      vulnerability: 0.38,
      apt_eligible: true,
      public_eligible: true,
      problem_type: forecastHour >= 12 ? 'Wet Snow' : 'Wind Slab',
      problem_slug: forecastHour >= 12 ? 'wet_snow' : 'wind_slab',
      shap_values: {},
    },
    {
      row: 0,
      col: 1,
      lat: 27.9,
      lng: 86.87,
      lat_end: 27.95,
      lng_end: 86.92,
      risk_score: 4,
      probability: 0.74,
      hazard: 0.74,
      exposure: 0.5,
      vulnerability: 0.4,
      apt_eligible: true,
      public_eligible: true,
      problem_type: 'Wind Slab',
      problem_slug: 'wind_slab',
      shap_values: {},
    },
    {
      row: 1,
      col: 0,
      lat: 27.95,
      lng: 86.82,
      lat_end: 28.0,
      lng_end: 86.87,
      risk_score: 2,
      probability: 0.41,
      hazard: 0.41,
      exposure: 0.28,
      vulnerability: 0.22,
      apt_eligible: true,
      public_eligible: true,
      problem_type: 'No Distinct Avalanche Problem',
      problem_slug: 'no_distinct_avalanche_problem',
      shap_values: {},
    },
    {
      row: 1,
      col: 1,
      lat: 27.95,
      lng: 86.87,
      lat_end: 28.0,
      lng_end: 86.92,
      risk_score: 0,
      terrain_fused_risk_score: 3,
      probability: 0.33,
      hazard: 0.33,
      exposure: 0.18,
      vulnerability: 0.12,
      apt_eligible: false,
      apt_mask_reason: 'slope_outside_30_to_50_deg',
      problem_type: 'No Distinct Avalanche Problem',
      problem_slug: 'no_distinct_avalanche_problem',
      shap_values: {},
    },
  ];
}

function buildManifest() {
  return {
    schemaVersion: 'forecast-manifest/v1',
    forecastRunId: FORECAST_RUN_ID,
    hazardType: 'avalanche',
    regionKey: REGION_KEY,
    regionName: REGION_NAME,
    forecastDate: '2026-05-02',
    issueTime: '2026-05-02T00:00:00.000Z',
    horizonHours: 24,
    gridSize: 20,
    bbox: [...BBOX],
    status: 'ready',
    weatherSummary: {
      snowfall_24h: '12 cm',
      wind_speed: '22 km/h',
      temperature: '-7 C',
      precipitation: '4 mm',
      snow_depth: '95 cm',
    },
    forecastBulletin: {
      schema_version: 'forecast-bulletin/v1',
      standard: 'EAWS-style experimental',
      danger_level: 4,
      danger_label: 'High',
      primary_problem: 'no_distinct_avalanche_problem',
      problems: [],
      critical_elevations: { min_m: 400, max_m: 6000, band_step_m: 200 },
      critical_aspects: ['E', 'SE', 'S', 'SW', 'W'],
      coverage: 'ready',
      issue_window_policy: 'daypart_v1',
      primary_window: 'day_1_night',
      primary_window_policy: 'first_available_current_or_future_daypart_v1',
      peak_window: {
        window: 'day_2_morning',
        danger_level: 5,
        danger_label: 'Very High',
        primary_problem: 'wet_snow',
        forecast_hours: [30],
        local_start: '2026-05-03T06:00:00+05:45',
        local_end: '2026-05-03T07:00:00+05:45',
        selected_forecast_hour: 30,
        selected_hour_local_start: '2026-05-03T06:00:00+05:45',
        selected_hour_local_end: '2026-05-03T07:00:00+05:45',
      },
      dayparts: [
        {
          window: 'day_1_night',
          day_index: 1,
          daypart: 'night',
          danger_level: 4,
          danger_label: 'High',
          primary_problem: 'no_distinct_avalanche_problem',
          forecast_hours: [0, 1, 2, 3, 4, 5],
          selected_forecast_hour: 0,
        },
        {
          window: 'day_1_morning',
          day_index: 1,
          daypart: 'morning',
          danger_level: 4,
          danger_label: 'High',
          primary_problem: 'wind_slab',
          forecast_hours: [6, 7, 8, 9, 10, 11],
          selected_forecast_hour: 6,
        },
        {
          window: 'day_1_afternoon',
          day_index: 1,
          daypart: 'afternoon',
          danger_level: 4,
          danger_label: 'High',
          primary_problem: 'wet_snow',
          forecast_hours: [12, 13, 14, 15, 16, 17],
          selected_forecast_hour: 12,
        },
        {
          window: 'day_1_evening',
          day_index: 1,
          daypart: 'evening',
          danger_level: 4,
          danger_label: 'High',
          primary_problem: 'wind_slab',
          forecast_hours: [18, 19, 20, 21, 22, 23],
          selected_forecast_hour: 18,
        },
      ],
      double_map: false,
      aggregation_notes: [],
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
        ready_cell_count: 4,
        eligible_cell_count: 3,
        max_danger_cell_count: 2,
        selected_level_cell_count: 2,
        selected_level_cell_share: 0.5,
        problem_counts: { wind_slab: 2 },
      },
    },
    modelMetadata: {},
    runoutStorageRef: null,
    hours: [
      { forecastHour: 0, validTime: '2026-05-02T00:00:00.000Z', storageRef: HOUR_REFS[0], cellCount: 4, readyCellCount: 3, staleCellCount: 0 },
      { forecastHour: 6, validTime: '2026-05-02T06:00:00.000Z', storageRef: HOUR_REFS[6], cellCount: 4, readyCellCount: 3, staleCellCount: 0 },
      { forecastHour: 12, validTime: '2026-05-02T12:00:00.000Z', storageRef: HOUR_REFS[12], cellCount: 4, readyCellCount: 3, staleCellCount: 0 },
      { forecastHour: 18, validTime: '2026-05-02T18:00:00.000Z', storageRef: HOUR_REFS[18], cellCount: 4, readyCellCount: 3, staleCellCount: 0 },
    ],
  };
}

async function installCitizenScienceMocks(page: Page) {
  let fieldReportCounter = 0;
  let eventCounter = 0;
  let avalancheEventReads = 0;
  let storedEvents: Array<Record<string, unknown>> = [];

  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation({ latitude: 27.9881, longitude: 86.925 });

  const manifest = buildManifest();

  await page.route('https://example.supabase.co/auth/v1/**', async (route) => {
    const url = route.request().url();
    const publicUser = {
      id: 'citizen-science-public-user',
      aud: 'authenticated',
      role: 'authenticated',
      email: 'public@insight-hub.local',
      app_metadata: {},
      user_metadata: {},
    };

    if (url.includes('/user')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(publicUser),
      });
      return;
    }

    if (url.includes('/token')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'citizen-science-access-token',
          refresh_token: 'citizen-science-refresh-token',
          token_type: 'bearer',
          expires_in: 3600,
          user: publicUser,
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });

  await page.route('https://example.supabase.co/functions/v1/run-forecast', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        stale: false,
        status: 'ready',
        source: 'forecast_runs',
        forecastRunId: FORECAST_RUN_ID,
        forecastId: null,
        manifestPath: MANIFEST_REF,
        forecastBulletin: null,
        regionName: REGION_NAME,
        regionKey: REGION_KEY,
        forecastDate: '2026-05-02',
        hours: 24,
        weatherSummary: null,
        modelMetadata: {},
      }),
    });
  });

  await page.route('https://example.supabase.co/storage/v1/object/**', async (route) => {
    const url = route.request().url();
    if (url.includes(MANIFEST_REF)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(manifest),
      });
      return;
    }

    const hourRef = Object.values(HOUR_REFS).find((candidate) => url.includes(candidate));
    if (hourRef) {
      const matchingHour = Number(
        Object.entries(HOUR_REFS).find(([, candidate]) => candidate === hourRef)?.[0] ?? 0,
      );
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema_version: 'forecast-hour/v1',
          forecast_run_id: FORECAST_RUN_ID,
          region_key: REGION_KEY,
          forecast_date: '2026-05-02',
          forecast_hour: matchingHour,
          valid_time: `2026-05-02T${String(matchingHour).padStart(2, '0')}:00:00.000Z`,
          cells: buildCells(matchingHour),
        }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'not-found' }),
    });
  });

  await page.route('https://example.supabase.co/rest/v1/avalanche_events**', async (route) => {
    avalancheEventReads += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(storedEvents),
    });
  });

  await page.route('https://example.supabase.co/rest/v1/field_reports**', async (route) => {
    fieldReportCounter += 1;
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ id: `field-report-${fieldReportCounter}` }),
    });
  });

  await page.route('https://example.supabase.co/functions/v1/field-report-enrichment', async (route) => {
    eventCounter += 1;
    const payload = JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>;
    const event = {
      id: `event-${eventCounter}`,
      location: {
        type: 'Point',
        coordinates: [Number(payload.lng ?? 86.925), Number(payload.lat ?? 27.9881)],
      },
      severity: 3,
      confidence: 0.68,
      label_confidence: 0.84,
      description: String(payload.description ?? ''),
      source: 'field_report',
      event_type: 'unknown',
      timestamp: String(payload.timestamp ?? '2026-05-02T04:30:00.000Z'),
      features: {
        field_report_id: `field-report-${fieldReportCounter}`,
        client_report_id: String(payload.clientReportId ?? ''),
        location_name: REGION_NAME,
      },
    };
    storedEvents = [event, ...storedEvents];

    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ event }),
    });
  });

  return {
    getAvalancheEventReadCount: () => avalancheEventReads,
  };
}

async function countEventMarkers(page: Page) {
  return await page.evaluate(() => {
    const selectors = [
      '[class*="events-pane"] path',
      '[class*="events-pane"] circle',
    ];
    return selectors.reduce((count, selector) => count + document.querySelectorAll(selector).length, 0);
  });
}

async function countGridPaths(page: Page) {
  return await page.evaluate(() => document.querySelectorAll('.leaflet-overlay-pane path').length);
}

test.describe('Citizen science loop', () => {
  test('renders the grid, submits a field report, reconciles the marker, and syncs daypart navigation', async ({ page }) => {
    const mockState = await installCitizenScienceMocks(page);

    await page.goto('/?region=Himalayas%20(Nepal)&hour=0', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Danger Level 4: High').first()).toBeVisible({ timeout: 15000 });
    await expect.poll(
      () => page.locator('[data-testid^="daypart-chip-"]').count(),
      { timeout: 15000 },
    ).toBe(4);
    await expect.poll(() => countGridPaths(page), { timeout: 15000 }).toBeGreaterThan(0);

    await page.getByRole('button', { name: 'SHOW EVENTS' }).click();
    await expect.poll(() => countEventMarkers(page), { timeout: 5000 }).toBe(0);

    await page.getByRole('button', { name: 'REPORT' }).click();
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: /use my location/i }).click();
    await page.getByLabel('Description').fill('Citizen science loop e2e smoke event');
    await page.getByLabel('Observation time').fill('2026-05-02T10:00');
    await page.getByRole('button', { name: /submit report/i }).click();

    await expect.poll(() => countEventMarkers(page), { timeout: 5000 }).toBe(1);
    await expect(page.getByRole('dialog')).toBeHidden({ timeout: 15000 });
    await expect.poll(() => countEventMarkers(page), { timeout: 5000 }).toBe(1);

    await page.getByTestId('daypart-chip-morning').evaluate((element) => {
      if (element instanceof HTMLButtonElement) {
        element.click();
      }
    });
    await expect(page.getByTestId('daypart-chip-morning')).toHaveAttribute('data-active-daypart', 'true');
    await expect(page.getByLabel('Timeline hour offset')).toHaveAttribute('aria-valuenow', '6');

    await page.getByTestId('daypart-chip-afternoon').evaluate((element) => {
      if (element instanceof HTMLButtonElement) {
        element.click();
      }
    });
    await expect(page.getByTestId('daypart-chip-afternoon')).toHaveAttribute('data-active-daypart', 'true');
    await expect(page.getByLabel('Timeline hour offset')).toHaveAttribute('aria-valuenow', '12');

    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Danger Level 4: High').first()).toBeVisible({ timeout: 15000 });
    await expect.poll(() => mockState.getAvalancheEventReadCount(), { timeout: 5000 }).toBeGreaterThan(1);
  }, 45_000);
});
