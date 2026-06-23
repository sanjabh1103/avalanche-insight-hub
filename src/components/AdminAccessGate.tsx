import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AuthChangeEvent, Session, User } from '@supabase/supabase-js';
import { Loader2, LockKeyhole, LogOut, ShieldAlert, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { supabase } from '@/integrations/supabase/client';

type AdminAccessState = 'loading' | 'signed_out' | 'forbidden' | 'ready';
const ACCESS_CHECK_TIMEOUT_MS = 4500;
const SIGN_IN_RETRY_DELAYS_MS = [150, 300, 600];

function extractAdminRoles(appMetadata: unknown): string[] {
  if (!appMetadata || typeof appMetadata !== 'object' || Array.isArray(appMetadata)) {
    return [];
  }
  const roles = (appMetadata as { roles?: unknown }).roles;
  if (!Array.isArray(roles)) {
    return [];
  }
  return roles
    .filter((value): value is string => typeof value === 'string')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
}

function isAdminUser(user: User | null): boolean {
  if (!user) {
    return false;
  }
  return extractAdminRoles(user.app_metadata).includes('admin');
}

function resolveAccessState(user: User | null): AdminAccessState {
  if (!user) {
    return 'signed_out';
  }
  return isAdminUser(user) ? 'ready' : 'forbidden';
}

async function waitForUserSession(): Promise<User | null> {
  for (const delayMs of SIGN_IN_RETRY_DELAYS_MS) {
    const { data, error } = await supabase.auth.getSession();
    if (!error && data.session?.user) {
      return data.session.user;
    }
    await new Promise((resolve) => window.setTimeout(resolve, delayMs));
  }
  return null;
}

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_PASSWORD = 'test123';

export default function AdminAccessGate({ children }: { children: ReactNode }) {
  const [accessState, setAccessState] = useState<AdminAccessState>('loading');
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [accessCheckTimedOut, setAccessCheckTimedOut] = useState(false);
  const [demoUnlocked, setDemoUnlocked] = useState(false);
  const [demoPasswordInput, setDemoPasswordInput] = useState('');
  const syncRequestRef = useRef(0);
  const timeoutRef = useRef<number | null>(null);

  const clearAccessTimeout = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const scheduleAccessTimeout = useCallback((requestId: number) => {
    clearAccessTimeout();
    timeoutRef.current = window.setTimeout(() => {
      if (syncRequestRef.current === requestId) {
        setAccessCheckTimedOut(true);
      }
    }, ACCESS_CHECK_TIMEOUT_MS);
  }, [clearAccessTimeout]);

  const applyUserState = useCallback((user: User | null) => {
    setUserEmail(user?.email ?? null);
    setAccessState(resolveAccessState(user));
    setAccessCheckTimedOut(false);
  }, []);

  const syncUser = useCallback(async (options?: { showLoading?: boolean }) => {
    const requestId = syncRequestRef.current + 1;
    syncRequestRef.current = requestId;
    if (options?.showLoading ?? false) {
      setAccessState('loading');
      scheduleAccessTimeout(requestId);
    }
    const { data, error } = await supabase.auth.getUser();
    if (syncRequestRef.current !== requestId) {
      return;
    }
    clearAccessTimeout();
    if (error) {
      applyUserState(null);
      return;
    }
    applyUserState(data.user ?? null);
  }, [applyUserState, clearAccessTimeout, scheduleAccessTimeout]);

  const hydrateFromSession = useCallback((session: Session | null) => {
    applyUserState(session?.user ?? null);
  }, [applyUserState]);

  const handleAuthTransition = useCallback((event: AuthChangeEvent, session: Session | null) => {
    syncRequestRef.current += 1;
    clearAccessTimeout();
    setAccessCheckTimedOut(false);
    if (event === 'SIGNED_OUT') {
      hydrateFromSession(null);
      return;
    }
    hydrateFromSession(session);
    if (session?.user && (event === 'INITIAL_SESSION' || event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED')) {
      void syncUser();
    }
  }, [clearAccessTimeout, hydrateFromSession, syncUser]);

  const retrySessionCheck = useCallback(() => {
    void syncUser({ showLoading: true });
  }, [syncUser]);

  useEffect(() => {
    const requestId = syncRequestRef.current + 1;
    syncRequestRef.current = requestId;
    setAccessState('loading');
    setAccessCheckTimedOut(false);
    scheduleAccessTimeout(requestId);
    void supabase.auth.getSession().then(({ data, error }) => {
      if (syncRequestRef.current !== requestId) {
        return;
      }
      clearAccessTimeout();
      if (error) {
        applyUserState(null);
        return;
      }
      const session = data.session ?? null;
      hydrateFromSession(session);
      if (session?.user) {
        void syncUser();
      }
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      handleAuthTransition(event, session);
    });
    return () => {
      clearAccessTimeout();
      subscription.unsubscribe();
    };
  }, [applyUserState, clearAccessTimeout, handleAuthTransition, hydrateFromSession, scheduleAccessTimeout, syncUser]);

  const handleSignIn = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) {
        setSubmitError(error.message);
        return;
      }
      setPassword('');
      const signedInUser = data.user ?? data.session?.user ?? await waitForUserSession();
      if (signedInUser) {
        applyUserState(signedInUser);
        void syncUser();
      } else {
        await syncUser({ showLoading: true });
      }
    } finally {
      setSubmitting(false);
    }
  }, [applyUserState, email, password, syncUser]);

  const handleSignOut = useCallback(async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { error } = await supabase.auth.signOut();
      if (error) {
        setSubmitError(error.message);
        return;
      }
      setPassword('');
      setUserEmail(null);
      setAccessState('signed_out');
    } finally {
      setSubmitting(false);
    }
  }, []);

  const adminSummary = useMemo(() => {
    if (!userEmail) {
      return 'Signed in operator session';
    }
    return `Signed in as ${userEmail}`;
  }, [userEmail]);

  if (DEMO_MODE) {
    if (demoUnlocked) {
      return <>{children}</>;
    }
    return (
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em] text-foreground">
            <LockKeyhole className="h-4 w-4 text-emerald-400" />
            Admin Demo Access
          </CardTitle>
          <CardDescription>
            Enter the demo password to access the admin workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (demoPasswordInput === DEMO_PASSWORD) {
                setDemoUnlocked(true);
              } else {
                setSubmitError('Incorrect demo password.');
              }
            }}
            className="space-y-3"
          >
            <div className="space-y-1">
              <Label htmlFor="demo-admin-password">Demo password</Label>
              <Input
                id="demo-admin-password"
                type="password"
                value={demoPasswordInput}
                onChange={(event) => {
                  setDemoPasswordInput(event.target.value);
                  setSubmitError(null);
                }}
                placeholder="Enter demo password"
                autoFocus
              />
            </div>
            {submitError ? (
              <p className="text-xs text-red-400">{submitError}</p>
            ) : null}
            <Button type="submit" className="w-full">Unlock Admin</Button>
          </form>
        </CardContent>
      </Card>
    );
  }

  if (accessState === 'loading') {
    return (
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="flex flex-col gap-3 p-4 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{accessCheckTimedOut ? 'Admin session check is taking longer than expected.' : 'Verifying admin session...'}</span>
          </div>
          {accessCheckTimedOut ? (
            <Button type="button" variant="outline" size="sm" className="self-start sm:self-auto" onClick={retrySessionCheck}>
              Retry session check
            </Button>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  if (accessState === 'signed_out') {
    return (
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em] text-foreground">
            <LockKeyhole className="h-4 w-4 text-emerald-400" />
            Admin Access
          </CardTitle>
          <CardDescription>
            This route requires an authenticated Supabase operator session.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          <form className="space-y-3" onSubmit={handleSignIn}>
            <div className="space-y-1.5">
              <Label htmlFor="admin-email">Email</Label>
              <Input
                id="admin-email"
                autoComplete="username"
                inputMode="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="admin@insight-hub.local"
                disabled={submitting}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="admin-password">Password</Label>
              <Input
                id="admin-password"
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter admin password"
                disabled={submitting}
              />
            </div>
            {submitError ? (
              <div className="text-xs text-red-400" role="alert">
                {submitError}
              </div>
            ) : null}
            <Button type="submit" className="w-full" disabled={submitting || !email.trim() || !password}>
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Sign in
            </Button>
          </form>
        </CardContent>
      </Card>
    );
  }

  if (accessState === 'forbidden') {
    return (
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em] text-foreground">
            <ShieldAlert className="h-4 w-4 text-amber-300" />
            Admin Access Required
          </CardTitle>
          <CardDescription>
            The current session is authenticated but does not carry the `admin` role in app metadata.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 p-4 pt-2">
          <div className="text-xs text-muted-foreground">{adminSummary}</div>
          {submitError ? (
            <div className="text-xs text-red-400" role="alert">
              {submitError}
            </div>
          ) : null}
          <Button type="button" variant="outline" onClick={handleSignOut} disabled={submitting}>
            {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogOut className="mr-2 h-4 w-4" />}
            Sign out
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="flex items-center justify-between gap-3 p-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              Admin Session
            </div>
            <div className="truncate text-sm text-foreground">{adminSummary}</div>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={handleSignOut} disabled={submitting}>
            {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogOut className="mr-2 h-4 w-4" />}
            Sign out
          </Button>
        </CardContent>
      </Card>
      {children}
    </div>
  );
}
