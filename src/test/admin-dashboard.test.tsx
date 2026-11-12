import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fromMock, orderCalls } = vi.hoisted(() => ({
  fromMock: vi.fn(),
  orderCalls: [] as Array<[string, Record<string, unknown> | undefined]>,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    from: fromMock,
    functions: {
      invoke: vi.fn(),
    },
  },
}));

vi.mock('@/hooks/useRealtimeSubscription', () => ({
  useRealtimeSubscription: vi.fn(),
}));

import AdminDashboard from '@/components/AdminDashboard';

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
    eq: vi.fn().mockReturnThis(),
    maybeSingle: vi.fn(async () => ({ data, error: null })),
    then: (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
      Promise.resolve({ data, error: null }).then(resolve, reject),
  };
  return builder;
}

describe('AdminDashboard', () => {
  beforeEach(() => {
    orderCalls.length = 0;
    fromMock.mockReset();
    fromMock.mockImplementation((table: string) => {
      const responses: Record<string, unknown> = {
        compute_jobs: [],
        system_config: { gemini_usage: 0, gemini_spend_cap: 1000 },
        model_status: {
          version: 'forecast-20260505T091500Z',
          f1_score: 0.723,
          pss_reported: 0.713,
          pss_gate_passed: true,
          promotion_gate_passed: false,
          shadow_mode_active: true,
          active_model_type: 'surrogate_rf_v1',
          active_model_version: '2026-05-05T09:15:00Z',
          drift_mode_state: 'blocked_by_gate',
          capability_summary: 'batch-only forecast_grids',
          inference_backend: 'batch_async',
          feature_version: 'drift-accelerated-decay',
          calibration_profile_version: 'drift-accelerated-decay',
          threshold_profile_version: 'drift-accelerated-decay',
          snowpack_model_version: 'edge-him-strat-lite-v1',
          last_trained: '2026-05-05T08:30:00Z',
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
          latest_benchmark_summary: {
            benchmark_kind: 'inference_publication',
            status: 'ok',
            total_seconds: 211.921,
          },
          stability_summary: {
            classification: 'unstable',
            seed_count: 3,
            pss_std: 0.01659,
            threshold_drift: 0.157726,
            selected_feature_overlap_mean: 0.768791,
          },
          optimization_summary: {
            origin: 'artifact',
            optimization_version: 'opt-edge-20260505',
            selected_features: ['slope', 'elevation'],
            class_balance_report: { strategy: 'edge-lite-resampling' },
            abc_enabled: false,
          },
        },
        forecast_analytics: [],
        evaluation_runs: [],
        evaluation_metrics: [],
        forecast_outcomes: [],
        field_reports: [],
        avalanche_events: [],
        forecast_runs: [
          {
            id: 'run-1',
            region_key: 'swiss_alps',
            region_name: 'Swiss Alps',
            forecast_date: '2026-05-05',
            status: 'ready',
            publication_status: 'published',
            active: true,
            manifest_storage_ref: 'artifacts/run-1.json',
            compatibility_forecast_grid_id: 'grid-1',
            published_at: '2026-05-05T08:45:00Z',
            created_at: '2026-05-05T08:40:00Z',
            model_metadata: {
              source_health: {
                support_status: 'complete',
                overall_completeness: 1,
                weather_freshness_hours: 3,
                sar_coverage_mode: 'not_applicable',
                snowpack_proxy_available: true,
                missing_features: [],
              },
              decision_provenance: {
                threshold_profile: 'heuristic-risk-bands-v1',
                threshold_profile_origin: 'heuristic_seeded',
                dominant_mapping: 'heuristic_thresholds_and_frequency',
                frequency_threshold_profile: 'local_grid_share_heuristic_v2',
                aggregation_policy: 'daypart_primary_window_by_peak_hour',
                calibration_method: 'isotonic',
                selected_feature_count: 15,
              },
              governance_scope: {
                external_interoperability: 'not_implemented',
              },
            },
          },
        ],
        forecast_run_hours: [],
        forecast_publication_events: [],
      };
      return createQueryBuilder(table, responses[table]);
    });
  });

  it('loads the freshest model status row and surfaces scientist-safe admin interpretation', async () => {
    render(<AdminDashboard />);

    expect(await screen.findByText(/Current-state interpretation: governance evidence and benchmark traces for gated promotion review\./i)).toBeTruthy();
    expect(screen.getByText(/Current-state interpretation: operator evidence for gated candidate review; activation and authority standing require promotion proof\./i)).toBeTruthy();
    expect(screen.getByText(/Latest benchmark: inference_publication • ok • 211\.9s/i)).toBeTruthy();
    expect(screen.getByText(/Governance scope: internal lineage\/evaluation only; public claims remain gated until release artifacts pass\./i)).toBeTruthy();
    expect(screen.getByText('Run ID')).toBeTruthy();
    expect(screen.getAllByText('run-1').length).toBeGreaterThan(0);
    expect(orderCalls).toEqual([
      ['last_inference', { ascending: false, nullsFirst: false }],
      ['last_trained', { ascending: false, nullsFirst: false }],
    ]);
  }, 30_000);
});
