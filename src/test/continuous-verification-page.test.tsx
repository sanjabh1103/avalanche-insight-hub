import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const { mockFrom, mockGetSession, mockGetUser, mockOnAuthStateChange } = vi.hoisted(() => ({
  mockFrom: vi.fn(),
  mockGetSession: vi.fn(),
  mockGetUser: vi.fn(),
  mockOnAuthStateChange: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    from: mockFrom,
    auth: {
      getSession: mockGetSession,
      getUser: mockGetUser,
      onAuthStateChange: mockOnAuthStateChange,
      signOut: vi.fn(),
      signInWithPassword: vi.fn(),
    },
  },
}));

vi.mock('@/lib/continuousVerification', () => ({
  loadContinuousVerificationDashboard: vi.fn(),
  buildContinuousVerificationDashboardData: vi.fn(),
}));

import { loadContinuousVerificationDashboard } from '@/lib/continuousVerification';
import ContinuousVerificationPage from '@/pages/ContinuousVerificationPage';

describe('ContinuousVerificationPage auth gating', () => {
  it('does not call loadContinuousVerificationDashboard when signed out', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });
    mockOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
    mockFrom.mockReturnValue({
      select: () => ({ limit: () => Promise.resolve({ data: [], error: null }) }),
    });

    render(<ContinuousVerificationPage />);

    // Wait for the gate to transition past loading
    await waitFor(() => {
      expect(screen.getByText('Continuous Verification Access')).toBeTruthy();
    });

    expect(loadContinuousVerificationDashboard).not.toHaveBeenCalled();
  });
});
