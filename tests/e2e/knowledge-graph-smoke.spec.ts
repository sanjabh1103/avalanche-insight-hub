import { expect, test, type Page } from '@playwright/test';

/**
 * Knowledge Graph browser smoke test.
 *
 * Verifies that a fresh checkout can:
 * 1. Open /knowledge
 * 2. See the graph load (not the lock page)
 * 3. Switch perspectives
 * 4. Toggle table view
 * 5. Change audience/depth
 * 6. Select a node
 * 7. See provenance status
 * 8. Reload snapshot
 *
 * This test requires the Vite dev server (not preview) because the knowledge
 * graph API endpoints are served by the vite-plugin-code-api plugin which only
 * runs in dev mode.
 *
 * Run with:
 *   PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test tests/e2e/knowledge-graph-smoke.spec.ts --project=chromium
 *
 * Or with a running dev server on port 8080:
 *   TEST_BASE_URL=http://localhost:8080 PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test tests/e2e/knowledge-graph-smoke.spec.ts --project=chromium
 */

const baseURL = process.env.TEST_BASE_URL || 'http://localhost:8080';

test.describe.configure({ mode: 'serial' });

test.describe('Knowledge Graph smoke test', () => {
  test.beforeAll(async () => {
    // Verify the dev server is running
    const response = await fetch(`${baseURL}/api/knowledge-graph/status`);
    if (!response.ok) {
      throw new Error(
        `Dev server not running at ${baseURL}. Start it with: VITE_DEMO_MODE=true npm run dev\n` +
        `Then run: TEST_BASE_URL=${baseURL} PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test tests/e2e/knowledge-graph-smoke.spec.ts --project=chromium`
      );
    }
  });

  test('loads /knowledge page without lock screen', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`, { waitUntil: 'domcontentloaded' });
    // Should NOT show the "Local Knowledge Workspace" lock page
    await expect(page.locator('body')).not.toContainText('Local Knowledge Workspace');
    await expect(page.getByRole('heading', { name: 'Code Knowledge Graph' })).toBeVisible();
    await expect(page.getByRole('tablist', { name: 'Graph perspective selector' })).toBeVisible();
  });

  test('graph loads with nodes from the API', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`);
    // The current Phase 2 snapshot is materially larger than the legacy
    // fallback; waiting on the rendered metric proves the API-backed graph won.
    await expect(page.getByText(/4916 nodes · 8158 edges/)).toBeVisible({ timeout: 15000 });
  });

  test('can switch between perspectives', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`);
    const architecture = page.getByRole('tab', { name: /^Architecture:/ });
    const mlPipeline = page.getByRole('tab', { name: /^ML Pipeline:/ });
    await expect(architecture).toHaveAttribute('aria-selected', 'true');
    await mlPipeline.click();
    await expect(mlPipeline).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('tabpanel', { name: 'ML Pipeline graph view' })).toBeVisible();
    await architecture.click();
    await expect(architecture).toHaveAttribute('aria-selected', 'true');
  });

  test('can toggle table view', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`);
    await page.getByRole('button', { name: 'Table view (accessible alternative)' }).click();
    const table = page.getByRole('table', { name: /Architecture graph data table/ });
    await expect(table).toBeVisible();
    const firstRow = table.locator('tbody tr').first();
    const nodeButton = firstRow.getByRole('button').last();
    await nodeButton.click();
    const detailPanel = page.getByRole('complementary', { name: /Detail panel for/ });
    await expect(detailPanel).toBeVisible();
    await expect(detailPanel.locator('h2')).toBeVisible();
    await detailPanel.getByRole('button', { name: 'Close detail panel' }).click();
    await expect(detailPanel).toHaveCount(0);
  });

  test('can change audience and depth', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`);
    const audience = page.getByLabel('Audience', { exact: true });
    const depth = page.getByLabel('Depth', { exact: true });
    await expect(audience).toHaveValue('novice');
    await expect(depth).toHaveValue('briefing');
    await audience.selectOption('ml_expert');
    await depth.selectOption('deep');
    await expect(audience).toHaveValue('ml_expert');
    await expect(depth).toHaveValue('deep');
  });

  test('provenance card shows status', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`);
    const provenance = page.getByRole('status', { name: /Graph provenance:/ });
    await expect(provenance).toBeVisible();
    await expect(provenance).toContainText(/Graph commit|Checkout|Source/);
  });

  test('can reload snapshot', async ({ page }: { page: Page }) => {
    await page.goto(`${baseURL}/knowledge`);
    const reloadResponse = page.waitForResponse((response) =>
      response.url().endsWith('/api/knowledge-graph/snapshot') &&
      response.request().method() === 'GET' &&
      response.ok(),
    );
    const reloadBtn = page.getByRole('button', { name: 'Reload graph snapshot' });
    await reloadBtn.click();
    await reloadResponse;
    await expect(page.getByRole('heading', { name: 'Code Knowledge Graph' })).toBeVisible();
    await expect(reloadBtn).toBeEnabled();
  });

  test('graph API endpoints respond correctly', async () => {
    // Verify the API endpoints are working
    const statusResponse = await fetch(`${baseURL}/api/knowledge-graph/status`);
    expect(statusResponse.ok).toBe(true);
    const statusData = await statusResponse.json();
    expect(statusData.provenance).toBeDefined();
    expect(statusData.provenance.source).toBeDefined();

    const snapshotResponse = await fetch(`${baseURL}/api/knowledge-graph/snapshot`);
    expect(snapshotResponse.ok).toBe(true);
    const snapshotData = await snapshotResponse.json();
    expect(snapshotData.graph).toBeDefined();
    expect(snapshotData.graph.nodes).toBeDefined();
    expect(snapshotData.graph.edges).toBeDefined();
    expect(snapshotData.graph.nodes.length).toBeGreaterThanOrEqual(4900);
    expect(snapshotData.graph.edges.length).toBeGreaterThanOrEqual(8100);
    expect(snapshotData.manifest.nodeCount).toBe(snapshotData.graph.nodes.length);
    expect(snapshotData.manifest.edgeCount).toBe(snapshotData.graph.edges.length);
    expect(statusData.provenance.nodeCount).toBe(snapshotData.graph.nodes.length);
    expect(statusData.provenance.edgeCount).toBe(snapshotData.graph.edges.length);
  });
});
