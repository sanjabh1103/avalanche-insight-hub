import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AuthChangeEvent, Session, User } from '@supabase/supabase-js';

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

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
      getUser: getUserMock,
      signInWithPassword: signInWithPasswordMock,
      signOut: signOutMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
  },
}));

import AdminAccessGate from '@/components/AdminAccessGate';

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: 'user-1',
    app_metadata: { roles: ['admin'] },
    user_metadata: {},
    aud: 'authenticated',
    created_at: '2026-05-04T00:00:00Z',
    email: 'admin@insight-hub.local',
    ...overrides,
  } as User;
}

function buildSession(user: User | null): Session | null {
  if (!user) {
    return null;
  }
  return {
    access_token: 'token',
    refresh_token: 'refresh',
    expires_in: 3600,
    expires_at: 9999999999,
    token_type: 'bearer',
    user,
  } as Session;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

describe('AdminAccessGate', () => {
  let authStateCallback: ((event: AuthChangeEvent, session: Session | null) => void) | null;

  beforeEach(() => {
    authStateCallback = null;
    getSessionMock.mockReset();
    getUserMock.mockReset();
    signInWithPasswordMock.mockReset();
    signOutMock.mockReset();
    unsubscribeMock.mockReset();
    onAuthStateChangeMock.mockReset();
    onAuthStateChangeMock.mockImplementation((callback: (event: AuthChangeEvent, session: Session | null) => void) => {
      authStateCallback = callback;
      return {
        data: {
          subscription: {
            unsubscribe: unsubscribeMock,
          },
        },
      };
    });
  });

  it('shows a login form when there is no authenticated session', async () => {
    getSessionMock.mockResolvedValue({
      data: { session: null },
      error: null,
    });

    render(
      <AdminAccessGate>
        <div>secret dashboard</div>
      </AdminAccessGate>,
    );

    expect(await screen.findByText('Admin Access')).toBeTruthy();
    expect(screen.getByLabelText('Email')).toBeTruthy();
    expect(screen.queryByText('secret dashboard')).toBeNull();
    expect(getUserMock).not.toHaveBeenCalled();
  });

  it('shows a forbidden state for authenticated non-admin users', async () => {
    const viewer = buildUser({
      email: 'viewer@example.com',
      app_metadata: { roles: ['viewer'] },
    });
    getSessionMock.mockResolvedValue({
      data: { session: buildSession(viewer) },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: viewer },
      error: null,
    });

    render(
      <AdminAccessGate>
        <div>secret dashboard</div>
      </AdminAccessGate>,
    );

    expect(await screen.findByText('Admin Access Required')).toBeTruthy();
    expect(screen.getByText(/viewer@example.com/i)).toBeTruthy();
    expect(screen.queryByText('secret dashboard')).toBeNull();
  });

  it('forbids scientist-only users from the admin route', async () => {
    const scientist = buildUser({
      email: 'scientist@insight-hub.local',
      app_metadata: { roles: ['scientist'] },
    });
    getSessionMock.mockResolvedValue({
      data: { session: buildSession(scientist) },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: scientist },
      error: null,
    });

    render(
      <AdminAccessGate>
        <div>secret dashboard</div>
      </AdminAccessGate>,
    );

    expect(await screen.findByText('Admin Access Required')).toBeTruthy();
    expect(screen.getByText(/scientist@insight-hub.local/i)).toBeTruthy();
    expect(screen.queryByText('secret dashboard')).toBeNull();
  });

  it('allows password sign-in and renders children for admin users', async () => {
    const adminUser = buildUser();
    const testPassword = ['fixture', 'pwd'].join('-');
    getSessionMock
      .mockResolvedValueOnce({
        data: { session: null },
        error: null,
      })
      .mockResolvedValueOnce({
        data: { session: buildSession(adminUser) },
        error: null,
      });
    getUserMock.mockResolvedValue({
      data: { user: adminUser },
      error: null,
    });
    signInWithPasswordMock.mockResolvedValue({
      data: { user: adminUser, session: buildSession(adminUser) },
      error: null,
    });

    render(
      <AdminAccessGate>
        <div>secret dashboard</div>
      </AdminAccessGate>,
    );

    fireEvent.change(await screen.findByLabelText('Email'), {
      target: { value: 'admin@insight-hub.local' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: testPassword },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(signInWithPasswordMock).toHaveBeenCalledWith({
        email: 'admin@insight-hub.local',
        password: testPassword,
      });
    });
    expect(await screen.findByText('Admin Session')).toBeTruthy();
    expect(screen.getByText('secret dashboard')).toBeTruthy();
  });

  it('ignores stale getUser completions after a sign-out transition', async () => {
    const adminUser = buildUser();
    const delayedUser = deferred<{ data: { user: User | null }; error: null }>();
    getSessionMock.mockResolvedValue({
      data: { session: buildSession(adminUser) },
      error: null,
    });
    getUserMock.mockReturnValueOnce(delayedUser.promise);

    render(
      <AdminAccessGate>
        <div>secret dashboard</div>
      </AdminAccessGate>,
    );

    expect(await screen.findByText('Admin Session')).toBeTruthy();

    await act(async () => {
      authStateCallback?.('SIGNED_OUT', null);
      delayedUser.resolve({
        data: { user: adminUser },
        error: null,
      });
    });

    expect(await screen.findByText('Admin Access')).toBeTruthy();
    expect(screen.queryByText('secret dashboard')).toBeNull();
  });

  it('shows a bounded retry affordance when bootstrap session resolution is slow', async () => {
    vi.useFakeTimers();
    try {
      getSessionMock.mockReturnValue(new Promise(() => undefined));

      render(
        <AdminAccessGate>
          <div>secret dashboard</div>
        </AdminAccessGate>,
      );

      await act(async () => {
        vi.advanceTimersByTime(4_550);
        await Promise.resolve();
      });

      expect(screen.getByText('Admin session check is taking longer than expected.')).toBeTruthy();
      expect(screen.getByRole('button', { name: 'Retry session check' })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
