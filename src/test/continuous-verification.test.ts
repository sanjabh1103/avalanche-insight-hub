import { describe, expect, it, vi } from 'vitest';

const { mockFrom } = vi.hoisted(() => ({ mockFrom: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { from: mockFrom },
}));

import {
  buildContinuousVerificationDashboardData,
  loadContinuousVerificationDashboard,
} from '@/lib/continuousVerification';

describe('continuous verification dashboard aggregation', () => {
  it('counts only independent sources and exposes stale evidence', () => {
    const data = buildContinuousVerificationDashboardData(
      [
        { cell_id: 'cell-1', sensor: 'weather', freshness_hours: 3, quality_state: 'verified', synthetic: false, acquisition_time: '2026-07-16T00:00:00Z' },
        { cell_id: 'cell-1', sensor: 'sar', freshness_hours: 4, quality_state: 'verified', synthetic: false, acquisition_time: '2026-07-15T23:00:00Z' },
        { cell_id: 'cell-1', sensor: 'optical', freshness_hours: 5, quality_state: 'verified', synthetic: false, acquisition_time: '2026-07-15T22:00:00Z' },
        { cell_id: 'cell-2', sensor: 'weather', freshness_hours: 96, quality_state: 'verified', synthetic: false, acquisition_time: '2026-07-12T00:00:00Z' },
        { cell_id: 'cell-2', sensor: 'synthetic', freshness_hours: 1, quality_state: 'verified', synthetic: true, acquisition_time: '2026-07-16T00:00:00Z' },
      ],
      [{ cell_id: 'cell-1' }],
      [{ cell_id: 'cell-2', attribution_bucket: 'sensing_gap' }],
      [{ cell_id: 'cell-2', review_state: 'pending', created_at: '2026-07-15T00:00:00Z' }],
      [{ id: 'case-1', status: 'pending', created_at: '2026-07-15T00:00:00Z', reviewed_at: null }],
      Date.parse('2026-07-16T00:00:00Z'),
    );

    expect(data.coverage?.total_cells).toBe(2);
    expect(data.coverage?.cells_with_3plus_sources).toBe(1);
    expect(data.stale_cells?.count).toBe(1);
    expect(data.stale_cells?.top_stale?.[0]).toEqual({ cell_id: 'cell-2', max_freshness_hours: 96 });
    expect(data.disagreement?.attribution_breakdown).toEqual({ sensing_gap: 1 });
    expect(data.review_backlog?.pending_count).toBe(1);
  });
});

describe('loadContinuousVerificationDashboard', () => {
  it('returns unavailable when tables do not exist', async () => {
    mockFrom.mockReturnValue({
      select: () => ({
        limit: () =>
          Promise.resolve({
            data: null,
            error: { code: '42P01', message: 'relation does not exist' },
          }),
      }),
    });
    const result = await loadContinuousVerificationDashboard();
    expect(result.status).toBe('unavailable');
    expect(result.unavailable_reason).toContain('unavailable');
    mockFrom.mockReset();
  });

  it('detects truncation when a table returns exactly MAX_ROWS', async () => {
    const fullRows = Array.from({ length: 1000 }, (_, i) => ({
      cell_id: `cell-${i}`,
      sensor: 'weather',
      freshness_hours: 3,
      quality_state: 'verified',
      synthetic: false,
      acquisition_time: '2026-07-16T00:00:00Z',
    }));
    mockFrom.mockReturnValue({
      select: () => ({
        limit: () => Promise.resolve({ data: fullRows, error: null }),
      }),
    });
    const result = await loadContinuousVerificationDashboard();
    expect(result.status).toBe('available');
    expect(result.truncated_tables).toBeDefined();
    expect(result.truncated_tables).toContain('verification_observations');
    mockFrom.mockReset();
  });

  it('does not flag truncation when rows are under the limit', async () => {
    const smallRows = Array.from({ length: 50 }, (_, i) => ({
      cell_id: `cell-${i}`,
      sensor: 'weather',
      freshness_hours: 3,
      quality_state: 'verified',
      synthetic: false,
      acquisition_time: '2026-07-16T00:00:00Z',
    }));
    mockFrom.mockReturnValue({
      select: () => ({
        limit: () => Promise.resolve({ data: smallRows, error: null }),
      }),
    });
    const result = await loadContinuousVerificationDashboard();
    expect(result.status).toBe('available');
    expect(result.truncated_tables).toBeUndefined();
    mockFrom.mockReset();
  });
});
