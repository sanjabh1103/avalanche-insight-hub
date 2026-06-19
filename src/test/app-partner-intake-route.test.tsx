import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getSessionMock,
  getUserMock,
  signInWithPasswordMock,
  signOutMock,
  onAuthStateChangeMock,
  unsubscribeMock,
} = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
  getUserMock: vi.fn(),
  signInWithPasswordMock: vi.fn(),
  signOutMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(),
  unsubscribeMock: vi.fn(),
}));

vi.mock('sonner', () => ({
  Toaster: () => null,
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
    from: vi.fn(),
  },
}));

async function renderAppAt(path: string, partnerIntakeEnabled: boolean) {
  vi.resetModules();
  vi.stubEnv('VITE_FEATURE_PARTNER_INTAKE', partnerIntakeEnabled ? 'true' : '');
  window.history.pushState({}, '', path);
  const { default: App } = await import('@/App');
  render(<App />);
}

describe('partner-intake route feature flag', () => {
  beforeEach(() => {
    const scientist = {
      id: 'scientist-user',
      email: 'scientist@insight-hub.local',
      app_metadata: { roles: ['scientist'] },
    };
    getSessionMock.mockReset();
    getUserMock.mockReset();
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
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('does not mount the partner-intake route when the feature flag is off', async () => {
    await renderAppAt('/scientist/partner-intake', false);

    expect(await screen.findByText('404')).toBeTruthy();
    expect(screen.getByText(/Page not found/i)).toBeTruthy();
  });

  it('mounts the partner-intake route when the feature flag is on', async () => {
    await renderAppAt('/scientist/partner-intake', true);

    expect(await screen.findByText('Partner Evidence Intake')).toBeTruthy();
    expect(await screen.findByText('Local Package Preflight')).toBeTruthy();
  });
});
