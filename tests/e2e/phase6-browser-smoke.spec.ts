import { expect, test, type Page } from '@playwright/test';

type RouteCheck = {
  path: string;
  textMarkers: string[];
  buttonLabels?: string[];
  installMocks?: (page: Page) => Promise<void>;
  beforeAssertions?: (page: Page) => Promise<void>;
};

const ROUTE_CHECKS: RouteCheck[] = [
  { path: '/', textMarkers: ['Avalanche Hub'], buttonLabels: ['Submit field report'] },
  {
    path: '/admin',
    textMarkers: ['Field Reports', 'Model Status', 'Source Health', 'Decision Provenance', 'Model Stability'],
    installMocks: async (page: Page) => {
      const adminUser = {
        id: 'phase6-admin-user',
        aud: 'authenticated',
        role: 'authenticated',
        email: 'admin@insight-hub.local',
        app_metadata: { roles: ['admin'] },
        user_metadata: {},
      };

      await page.route('https://example.supabase.co/auth/v1/**', async (route) => {
        const url = route.request().url();

        if (url.includes('/token')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              access_token: 'phase6-access-token',
              refresh_token: 'phase6-refresh-token',
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
            body: JSON.stringify(adminUser),
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

      await page.route('https://example.supabase.co/rest/v1/**', async (route) => {
        const url = route.request().url();

        if (url.includes('/model_status')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              version: 'phase6-smoke',
              f1_score: 0.93,
              pss_reported: 0.91,
              promotion_gate_passed: true,
              pss_gate_passed: true,
              drift_mode_state: 'ready_for_manual_activation',
              data_freshness_hours: 2,
              inference_backend: 'phase6-browser-smoke',
              last_inference: '2026-05-01T04:00:00.000Z',
              last_trained: '2026-05-01T00:00:00.000Z',
              feature_version: 'phase6-smoke-feature-set',
              calibration_profile_version: 'phase6-smoke-calibration',
              threshold_profile_version: 'phase6-smoke-thresholds',
              latest_benchmark_summary: {
                benchmark_kind: 'inference_publication',
                total_seconds: 12.4,
                status: 'ok',
              },
              snowpack_model_version: 'phase6-smoke-snowpack',
              stability_summary: {
                classification: 'stable',
                seed_count: 3,
                selected_feature_overlap_mean: 0.82,
              },
              optimization_summary: {
                origin: 'phase6-browser-smoke',
              },
            }),
          });
          return;
        }

        if (url.includes('/forecast_runs')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([{
              id: 'forecast-run-1',
              region_key: 'kargil',
              region_name: 'Kargil',
              forecast_date: '2026-05-01',
              status: 'ready',
              publication_status: 'published',
              active: true,
              manifest_storage_ref: 'forecast-products/avalanche/kargil/forecast-run-1/manifest.json',
              compatibility_forecast_grid_id: 'fg-1',
              published_at: '2026-05-01T04:00:00.000Z',
              created_at: '2026-05-01T03:55:00.000Z',
              model_metadata: {
                source_health: {
                  support_status: 'partial',
                  overall_completeness: 0.75,
                  weather_freshness_hours: 2,
                  sar_coverage_mode: 'mixed',
                  snowpack_proxy_available: true,
                  missing_features: ['recent_activity_context'],
                },
                decision_provenance: {
                  threshold_profile: 'heuristic-risk-bands-v1',
                  threshold_profile_origin: 'heuristic_seeded',
                  dominant_mapping: 'heuristic_thresholds_and_frequency',
                  frequency_threshold_profile: 'local_grid_share_heuristic_v2',
                  aggregation_policy: 'highest_regional_level_by_cumulative_frequency',
                  calibration_method: 'isotonic_v1',
                  selected_feature_count: 12,
                },
                governance_scope: {
                  external_interoperability: 'not_implemented',
                },
                tree_shap_status: 'ready',
              },
            }]),
          });
          return;
        }

        if (url.includes('/forecast_run_hours')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([{
              forecast_run_id: 'forecast-run-1',
              forecast_hour: 0,
              ready_cell_count: 24,
              stale_cell_count: 3,
              created_at: '2026-05-01T04:00:00.000Z',
            }]),
          });
          return;
        }

        if (url.includes('/forecast_publication_events')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([{
              id: 'event-1',
              forecast_run_id: 'forecast-run-1',
              stage: 'promote_completed',
              status: 'ok',
              detail: {},
              created_at: '2026-05-01T04:01:00.000Z',
            }]),
          });
          return;
        }

        if (url.includes('/system_config')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              gemini_usage: 0,
              gemini_spend_cap: 100,
            }),
          });
          return;
        }

        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });
    },
    beforeAssertions: async (page: Page) => {
      const passwordInput = page.getByLabel('Password');
      if (await passwordInput.isVisible().catch(() => false)) {
        await passwordInput.fill('phase6-admin-password');
        await page.getByRole('button', { name: 'Sign in' }).click();
        await expect(page.getByText('Admin Session', { exact: true })).toBeVisible({ timeout: 15000 });
      }
    },
  },
];

async function expectStableRoute(page: Page, routeCheck: RouteCheck) {
  const pageErrors: string[] = [];
  const documentFailures: string[] = [];

  const onPageError = (error: Error) => {
    pageErrors.push(error.message);
  };
  const onRequestFailed = (request: { isNavigationRequest(): boolean; resourceType(): string; url(): string; failure(): { errorText?: string } | null }) => {
    if (request.isNavigationRequest() && request.resourceType() === 'document') {
      documentFailures.push(`${request.url()} :: ${request.failure()?.errorText || 'unknown document failure'}`);
    }
  };

  page.on('pageerror', onPageError);
  page.on('requestfailed', onRequestFailed);

  try {
    if (routeCheck.installMocks) {
      await routeCheck.installMocks(page);
    }

    const response = await page.goto(routeCheck.path, { waitUntil: 'domcontentloaded' });
    expect(response, `missing document response for ${routeCheck.path}`).not.toBeNull();
    expect(response?.ok(), `document response was not OK for ${routeCheck.path}`).toBeTruthy();

    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => undefined);

    if (routeCheck.beforeAssertions) {
      await routeCheck.beforeAssertions(page);
    }

    for (const marker of routeCheck.textMarkers) {
      await expect(page.getByText(marker, { exact: true }).first()).toBeVisible({ timeout: 15000 });
    }
    for (const label of routeCheck.buttonLabels || []) {
      await expect(page.getByRole('button', { name: label }).first()).toBeVisible({ timeout: 15000 });
    }

    expect(pageErrors, `uncaught page errors on ${routeCheck.path}`).toEqual([]);
    expect(documentFailures, `document request failures on ${routeCheck.path}`).toEqual([]);
  } finally {
    page.off('pageerror', onPageError);
    page.off('requestfailed', onRequestFailed);
  }
}

test.describe('Phase 6 browser smoke', () => {
  for (const routeCheck of ROUTE_CHECKS) {
    const summary = [...routeCheck.textMarkers, ...(routeCheck.buttonLabels || [])].join(' + ');
    test(`route ${routeCheck.path} shows ${summary}`, async ({ page }) => {
      await expectStableRoute(page, routeCheck);
    });
  }
});
