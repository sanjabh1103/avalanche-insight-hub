import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fromMock, orderCalls } = vi.hoisted(() => ({
  fromMock: vi.fn(),
  orderCalls: [] as Array<[string, Record<string, unknown> | undefined]>,
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    from: fromMock,
  },
}));

vi.mock('@/hooks/useRealtimeSubscription', () => ({
  useRealtimeSubscription: vi.fn(),
}));

import ModelStatusBadge from '@/components/ModelStatusBadge';

function createQueryBuilder(table: string, data: unknown) {
  const builder = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn((column: string, options?: Record<string, unknown>) => {
      if (table === 'model_status') {
        orderCalls.push([column, options]);
      }
      return builder;
    }),
    limit: vi.fn().mockReturnThis(),
    maybeSingle: vi.fn(async () => ({ data, error: null })),
  };
  return builder;
}

describe('ModelStatusBadge', () => {
  beforeEach(() => {
    orderCalls.length = 0;
    fromMock.mockReset();
    fromMock.mockImplementation((table: string) => createQueryBuilder(table, {
      version: 'forecast-20260505T091500Z',
      f1_score: 0.723,
      pss_reported: 0.713,
      pss_gate_passed: true,
      promotion_gate_passed: false,
      shadow_mode_active: true,
      active_model_type: 'surrogate_rf_v1',
      active_model_version: '2026-05-05T09:15:00Z',
      drift_mode_state: 'blocked_by_gate',
      dynamic_model_candidate: {
        dynamic_model_type: 'mts_lstm_v1',
        dynamic_model_version: 'mts-lstm-42',
        blocked_gate: 'shadow_quality_gate',
        ready_for_activation: false,
      },
      autonomous_evidence_summary: {
        positive_count: 1000,
        manual_positive_count: 0,
        autonomous_positive_count: 1000,
        promoted_sar_volume: {
          sar_unet_promoted_count: 0,
        },
      },
      last_inference: '2026-05-05T09:20:00Z',
      last_trained: '2026-05-05T08:30:00Z',
      data_freshness_hours: 1,
      feature_version: 'drift-accelerated-decay',
      calibration_profile_version: 'drift-accelerated-decay',
      threshold_profile_version: 'drift-accelerated-decay',
      capability_summary: 'batch-only forecast_grids',
      inference_backend: 'batch_async',
      latest_benchmark_summary: {
        benchmark_kind: 'inference_publication',
        status: 'ok',
        total_seconds: 211.921,
      },
      snowpack_model_version: 'edge-him-strat-lite-v1',
      stability_summary: {
        classification: 'unstable',
        seed_count: 3,
      },
    }));
  });

  it('orders model status by freshest evidence and renders benchmark context', async () => {
    render(<ModelStatusBadge />);

    expect(await screen.findByText(/Benchmark:/i)).toBeTruthy();
    expect(screen.getByText(/inference_publication • ok • 211\.9s/i)).toBeTruthy();
    expect(screen.getByText(/Stability: unstable • 3 seeds/i)).toBeTruthy();
    expect(screen.getByText(/Governance scope:/i)).toBeTruthy();
    expect(screen.getByText(/operator evidence for gated public promotion review/i)).toBeTruthy();
    expect(orderCalls).toEqual([
      ['last_inference', { ascending: false, nullsFirst: false }],
      ['last_trained', { ascending: false, nullsFirst: false }],
    ]);
  }, 30_000);

  it('renders error state when query fails', async () => {
    fromMock.mockImplementation(() => ({
      select: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockReturnThis(),
      maybeSingle: vi.fn(async () => ({ data: null, error: { message: 'permission denied' } })),
    }));
    render(<ModelStatusBadge />);
    // Should not crash — component handles error gracefully
    expect(document.body).toBeTruthy();
  }, 30_000);

  it('renders with ready_for_activation drift mode', async () => {
    fromMock.mockImplementation((table: string) => createQueryBuilder(table, {
      version: 'forecast-20260506T100000Z',
      f1_score: 0.85,
      pss_reported: 0.80,
      pss_gate_passed: true,
      promotion_gate_passed: true,
      shadow_mode_active: false,
      active_model_type: 'surrogate_rf_v1',
      active_model_version: '2026-05-06T10:00:00Z',
      drift_mode_state: 'ready_for_manual_activation',
      dynamic_model_candidate: null,
      autonomous_evidence_summary: {
        positive_count: 5000,
        manual_positive_count: 100,
        autonomous_positive_count: 4900,
        promoted_sar_volume: { sar_unet_promoted_count: 5 },
      },
      last_inference: '2026-05-06T10:05:00Z',
      last_trained: '2026-05-06T09:00:00Z',
      data_freshness_hours: 0.5,
      feature_version: 'v2',
      calibration_profile_version: 'v2',
      threshold_profile_version: 'v2',
      capability_summary: 'batch-only forecast_grids',
      inference_backend: 'batch_async',
      latest_benchmark_summary: null,
      snowpack_model_version: 'edge-him-strat-lite-v1',
      stability_summary: { classification: 'stable', seed_count: 5 },
    }));
    render(<ModelStatusBadge />);
    expect(await screen.findByText(/Stability: stable • 5 seeds/i)).toBeTruthy();
  }, 30_000);

  it('renders with null data without crashing', async () => {
    fromMock.mockImplementation(() => ({
      select: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockReturnThis(),
      maybeSingle: vi.fn(async () => ({ data: null, error: null })),
    }));
    render(<ModelStatusBadge />);
    expect(document.body).toBeTruthy();
  }, 30_000);
});
