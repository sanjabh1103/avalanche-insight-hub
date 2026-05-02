import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getUserMock,
  signInWithPasswordMock,
  signOutMock,
  onAuthStateChangeMock,
  unsubscribeMock,
} = vi.hoisted(() => ({
  getUserMock: vi.fn(),
  signInWithPasswordMock: vi.fn(),
  signOutMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(),
  unsubscribeMock: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getUser: getUserMock,
      signInWithPassword: signInWithPasswordMock,
      signOut: signOutMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
  },
}));

import AdminAccessGate from '@/components/AdminAccessGate';

describe('AdminAccessGate', () => {
  beforeEach(() => {
    getUserMock.mockReset();
    signInWithPasswordMock.mockReset();
    signOutMock.mockReset();
    unsubscribeMock.mockReset();
    onAuthStateChangeMock.mockReset();
    onAuthStateChangeMock.mockReturnValue({
      data: {
        subscription: {
          unsubscribe: unsubscribeMock,
        },
      },
    });
  });

  it('shows a login form when there is no authenticated session', async () => {
    getUserMock.mockResolvedValue({
      data: { user: null },
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
  });

  it('shows a forbidden state for authenticated non-admin users', async () => {
    getUserMock.mockResolvedValue({
      data: {
        user: {
          email: 'viewer@example.com',
          app_metadata: { roles: ['viewer'] },
        },
      },
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

  it('allows password sign-in and renders children for admin users', async () => {
    const testPassword = ['fixture', 'pwd'].join('-');
    getUserMock
      .mockResolvedValueOnce({
        data: { user: null },
        error: null,
      })
      .mockResolvedValueOnce({
        data: {
          user: {
            email: 'admin@insight-hub.local',
            app_metadata: { roles: ['admin'] },
          },
        },
        error: null,
      });
    signInWithPasswordMock.mockResolvedValue({
      data: { session: { access_token: 'token' } },
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
});
