import { expect, test, type Page } from '@playwright/test';

/* ──────────────────────────────────────────────────────────────
 * Continuous Verification — signed-out access gate.
 *
 * Verifies that navigating to /scientist/continuous-verification
 * while signed out:
 *   1. Shows the access gate (login form)
 *   2. Does NOT make any requests to verification_* tables
 *
 * This is UAT test #2 from the verification spine audit.
 * ────────────────────────────────────────────────────────────── */

const VERIFICATION_TABLE_PATTERNS = [
  '/rest/v1/verification_observations',
  '/rest/v1/verification_baselines',
  '/rest/v1/verification_anomalies',
  '/rest/v1/verification_review_queue',
  '/rest/v1/scientist_validation_cases',
];

test.describe('Continuous Verification — signed-out access gate', () => {
  test('signed-out users see login gate and generate zero verification-table requests', async ({ page }: { page: Page }) => {
    const verificationRequests: string[] = [];

    // Mock auth endpoints to return no session (signed out)
    await page.route('**/auth/v1/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/token')) {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'invalid_credentials', message: 'Invalid login credentials' }),
        });
        return;
      }
      if (url.includes('/user')) {
        await route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'not_authenticated' }),
        });
        return;
      }
      // getSession returns empty
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { session: null }, error: null }),
      });
    });

    // Intercept all REST requests to detect verification-table access
    await page.route('**/rest/v1/**', async (route) => {
      const url = route.request().url();
      for (const pattern of VERIFICATION_TABLE_PATTERNS) {
        if (url.includes(pattern)) {
          verificationRequests.push(url);
        }
      }
      // Return empty data for any REST request
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // Navigate to the continuous verification page
    await page.goto('/scientist/continuous-verification', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => undefined);
    await page.waitForTimeout(2000);

    // Assert: the access gate is visible (login form)
    await expect(page.getByText('Continuous Verification Access')).toBeVisible({ timeout: 5000 });

    // Assert: no requests were made to verification tables
    expect(
      verificationRequests,
      `Signed-out user made ${verificationRequests.length} verification-table requests:\n${verificationRequests.join('\n')}`,
    ).toEqual([]);
  });
});
