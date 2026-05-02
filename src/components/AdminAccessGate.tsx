import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { Loader2, LockKeyhole, LogOut, ShieldAlert, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { supabase } from '@/integrations/supabase/client';

type AdminAccessState = 'loading' | 'signed_out' | 'forbidden' | 'ready';

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

export default function AdminAccessGate({ children }: { children: ReactNode }) {
  const [accessState, setAccessState] = useState<AdminAccessState>('loading');
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [email, setEmail] = useState('admin@insight-hub.local');
  const [password, setPassword] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const syncUser = useCallback(async () => {
    setSubmitError(null);
    setAccessState('loading');
    const { data, error } = await supabase.auth.getUser();
    if (error) {
      setUserEmail(null);
      setAccessState('signed_out');
      return;
    }

    const user = data.user;
    if (!user) {
      setUserEmail(null);
      setAccessState('signed_out');
      return;
    }

    setUserEmail(user.email ?? null);
    setAccessState(isAdminUser(user) ? 'ready' : 'forbidden');
  }, []);

  useEffect(() => {
    void syncUser();
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(() => {
      void syncUser();
    });
    return () => {
      subscription.unsubscribe();
    };
  }, [syncUser]);

  const handleSignIn = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) {
        setSubmitError(error.message);
        return;
      }
      setPassword('');
      await syncUser();
    } finally {
      setSubmitting(false);
    }
  }, [email, password, syncUser]);

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

  if (accessState === 'loading') {
    return (
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Verifying admin session...
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
