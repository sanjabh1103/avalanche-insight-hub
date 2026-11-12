import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fromMock, getUserMock } = vi.hoisted(() => ({
  fromMock: vi.fn(),
  getUserMock: vi.fn(async () => ({ data: { user: { id: 'admin-user' } }, error: null })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getUser: getUserMock,
    },
    from: fromMock,
  },
}));

import ScientistValidationWorkbench from '@/components/ScientistValidationWorkbench';

function createQueryBuilder(data: unknown) {
  const builder = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    in: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    single: vi.fn(async () => ({ data: Array.isArray(data) ? data[0] : data, error: null })),
    then: (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
      Promise.resolve({ data, error: null }).then(resolve, reject),
  };
  return builder;
}

describe('ScientistValidationWorkbench', () => {
  beforeEach(() => {
    fromMock.mockReset();
    fromMock.mockImplementation((table: string) => {
      if (table === 'scientist_validation_cases') {
        return createQueryBuilder([
          {
            id: 'case-1',
            case_type: 'weak_layer',
            status: 'pending',
            priority: 5,
            region_key: 'colorado_rockies',
            region_name: 'Synthetic Himalayan Demo',
            forecast_run_id: 'run-1',
            forecast_grid_id: 'grid-1',
            forecast_hour: 6,
            cell_row: 1,
            cell_col: 2,
            title: 'Weak-layer proxy review: r1 c2',
            summary: 'Review weak-layer proxy',
            evidence: {
              synthetic_demo: true,
              training_eligible: false,
              production_eligible: false,
            },
            cell_snapshot: {},
            model_metadata: {},
            gate_key: 'weak_layer_validation',
            claim_boundary: 'synthetic_demo_not_scientific_evidence',
            requires_two_reviewers: true,
            disagreement_count: 0,
            signoff_scope: 'single_case_review',
            assigned_to: null,
            created_by: 'admin-user',
            created_at: '2026-05-20T00:00:00Z',
            updated_at: '2026-05-20T00:00:00Z',
            reviewed_at: null,
          },
        ]);
      }
      if (table === 'scientist_validation_reviews') {
        return createQueryBuilder([]);
      }
      if (table === 'scientist_validation_actions') {
        return createQueryBuilder([
          {
            id: 'action-1',
            case_id: 'case-1',
            review_id: null,
            action_type: 'evidence_request',
            status: 'open',
            priority: 5,
            summary: 'Collect field observation',
            owner_role: 'scientist',
            resolution_notes: null,
            evidence_refs: {},
            created_by: 'admin-user',
            created_at: '2026-05-20T00:00:00Z',
            resolved_at: null,
          },
        ]);
      }
      return createQueryBuilder([]);
    });
  });

  it('renders validation queue metrics and gate status without production promotion wording', async () => {
    render(
      <ScientistValidationWorkbench
        gateStatuses={[
          {
            key: 'mts_lstm',
            label: 'MTS-LSTM candidate',
            status: 'gated',
            detail: 'Candidate remains blocked by shadow_quality_gate.',
          },
        ]}
      />,
    );

    expect(await screen.findByText('Scientist Validation Workbench')).toBeTruthy();
    expect(screen.getByText('Weak-layer proxy review: r1 c2')).toBeTruthy();
    expect(screen.getByText('MTS-LSTM candidate')).toBeTruthy();
    expect(screen.getByText(/Candidate remains blocked/i)).toBeTruthy();
    expect(screen.getByText(/Governed actions/i)).toBeTruthy();
    expect(screen.getByText(/Reference Library/i)).toBeTruthy();
    expect(screen.getByText(/Action Closure Queue/i)).toBeTruthy();
    expect(screen.getByText(/synthetic demo/i)).toBeTruthy();
    expect(screen.getAllByText(/HIM-STRAT/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Collect field observation/i)).toBeTruthy();
    expect(screen.getByText('2 reviewers')).toBeTruthy();
    expect(screen.getByText('Sign-off MD')).toBeTruthy();
    expect(screen.getByText('Sign-off JSON')).toBeTruthy();
  });
});
