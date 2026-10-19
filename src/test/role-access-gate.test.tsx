import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Session, User } from '@supabase/supabase-js';

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

import RoleAccessGate from '@/components/RoleAccessGate';

function buildUser(role: string, email = `${role}@insight-hub.local`): User {
  return {
    id: `${role}-user`,
    app_metadata: { roles: [role] },
    user_metadata: {},
    aud: 'authenticated',
    created_at: '2026-05-21T00:00:00Z',
    email,
  } as User;
}

function buildSession(user: User): Session {
  return {
    access_token: 'token',
    refresh_token: 'refresh',
    expires_in: 3600,
    expires_at: 9999999999,
    token_type: 'bearer',
    user,
  } as Session;
}

describe('RoleAccessGate', () => {
  beforeEach(() => {
    getSessionMock.mockReset();
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

  it('allows scientist sessions into the scientist workspace', async () => {
    const scientist = buildUser('scientist');
    getSessionMock.mockResolvedValue({
      data: { session: buildSession(scientist) },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: scientist },
      error: null,
    });

    render(
      <RoleAccessGate allowedRoles={['scientist', 'admin']}>
        <div>scientist validation tools</div>
      </RoleAccessGate>,
    );

    expect(await screen.findByText('Scientist Session')).toBeTruthy();
    expect(screen.getByText('scientist validation tools')).toBeTruthy();
  });

  it('allows admin sessions into the scientist workspace without changing admin-only gates', async () => {
    const admin = buildUser('admin', 'admin@insight-hub.local');
    getSessionMock.mockResolvedValue({
      data: { session: buildSession(admin) },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: admin },
      error: null,
    });

    render(
      <RoleAccessGate allowedRoles={['scientist', 'admin']}>
        <div>scientist validation tools</div>
      </RoleAccessGate>,
    );

    expect(await screen.findByText('Scientist Session')).toBeTruthy();
    expect(screen.getByText(/admin@insight-hub.local/i)).toBeTruthy();
    expect(screen.getByText('scientist validation tools')).toBeTruthy();
  });

  it('blocks unrelated authenticated roles', async () => {
    const viewer = buildUser('viewer', 'viewer@example.com');
    getSessionMock.mockResolvedValue({
      data: { session: buildSession(viewer) },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: viewer },
      error: null,
    });

    render(
      <RoleAccessGate allowedRoles={['scientist', 'admin']}>
        <div>scientist validation tools</div>
      </RoleAccessGate>,
    );

    expect(await screen.findByText('Access Role Required')).toBeTruthy();
    expect(screen.getByText(/scientist, admin/i)).toBeTruthy();
    expect(screen.queryByText('scientist validation tools')).toBeNull();
  });
});
