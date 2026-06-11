import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  fromMock,
  getSessionMock,
  getUserMock,
  signInWithPasswordMock,
  signOutMock,
  onAuthStateChangeMock,
  unsubscribeMock,
} = vi.hoisted(() => ({
  fromMock: vi.fn(),
  getSessionMock: vi.fn(),
  getUserMock: vi.fn(),
  signInWithPasswordMock: vi.fn(),
  signOutMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(),
  unsubscribeMock: vi.fn(),
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
      getSession: getSessionMock,
      getUser: getUserMock,
      signInWithPassword: signInWithPasswordMock,
      signOut: signOutMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
    from: fromMock,
  },
}));

import ScientistDailyVerificationPage from '@/pages/ScientistDailyVerificationPage';

function createQueryBuilder(data: unknown) {
  const builder = {
    select: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    single: vi.fn(async () => ({ data: Array.isArray(data) ? data[0] : data, error: null })),
    then: (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
      Promise.resolve({ data, error: null }).then(resolve, reject),
  };
  return builder;
}

describe('ScientistDailyVerificationPage', () => {
  beforeEach(() => {
    const scientist = {
      id: 'scientist-user',
      email: 'scientist@insight-hub.local',
      app_metadata: { roles: ['scientist'] },
    };
    getSessionMock.mockReset();
    getUserMock.mockReset();
    fromMock.mockReset();
    onAuthStateChangeMock.mockReset();
    unsubscribeMock.mockReset();
    signInWithPasswordMock.mockReset();
    signOutMock.mockReset();
    getSessionMock.mockResolvedValue({
      data: { session: { user: scientist } },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: scientist },
      error: null,
    });
    onAuthStateChangeMock.mockReturnValue({
      data: {
        subscription: {
          unsubscribe: unsubscribeMock,
        },
      },
    });
    fromMock.mockImplementation((table: string) => {
      if (table === 'scientist_daily_verifications') {
        return createQueryBuilder([
          {
            id: 'pair-1',
            reviewer_id: 'scientist-user',
            region_key: 'himalayas_nepal',
            region_name: 'Himalayas Nepal',
            verification_date: '2026-05-21',
            scientist_danger_level: '3',
            model_danger_level: '2',
            official_avalanche_problem: 'wind_slab',
            model_avalanche_problem: 'persistent_weak_layers',
            observed_outcome: 'unknown',
            created_at: '2026-05-21T00:00:00Z',
          },
          {
            id: 'pair-2',
            reviewer_id: 'scientist-user',
            region_key: 'himalayas_nepal',
            region_name: 'Himalayas Nepal',
            verification_date: '2026-05-20',
            scientist_danger_level: '2',
            model_danger_level: '2',
            official_avalanche_problem: 'wind_slab',
            model_avalanche_problem: 'wind_slab',
            observed_outcome: 'no_event_observed',
            created_at: '2026-05-20T00:00:00Z',
          },
        ]);
      }
      return createQueryBuilder([]);
    });
  });

  it('renders paired scientist-vs-model verification controls for scientist role', async () => {
    render(
      <MemoryRouter>
        <ScientistDailyVerificationPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Daily Verification')).toBeTruthy();
    expect(screen.getByText('Paired Input')).toBeTruthy();
    expect(screen.getByText('Scientist danger level')).toBeTruthy();
    expect(screen.getByText('Model danger level')).toBeTruthy();
    expect(screen.getByText('Analytics')).toBeTruthy();
    expect(screen.getByText('Recent Pairs')).toBeTruthy();
    await waitFor(() => expect(fromMock).toHaveBeenCalledWith('scientist_daily_verifications'));
    expect(await screen.findByText(/2026-05-21 · Himalayas Nepal/i)).toBeTruthy();
    expect(screen.getByText(/Scientist 3/i)).toBeTruthy();
    expect(screen.getByText('Danger agreement')).toBeTruthy();
    expect(screen.getByText('50%')).toBeTruthy();
    expect(screen.getByText('Danger confusion matrix')).toBeTruthy();
    expect(screen.getByText('EAWS problem confusion matrix')).toBeTruthy();
  });
});
