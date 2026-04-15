# Windsurf Supabase Local-Dev Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Avalanche Insight Hub run cleanly in Windsurf with a documented local Supabase workflow and a safe fallback path when the cloud-backed project is used instead.

**Architecture:** Keep the browser client pointed at a single Supabase endpoint via Vite env vars, and keep all database/function parity in the existing `supabase/` directory. Local development should use the Supabase CLI with the repo’s migrations and Edge Functions, while cloud-linked development remains an explicit fallback for users who prefer not to spin up the local stack.

**Tech Stack:** Vite, React, TypeScript, `@supabase/supabase-js`, Supabase CLI, Docker, Supabase Edge Functions.

---

### Task 1: Make the Supabase browser client fail fast with actionable startup errors

**Files:**
- Modify: `src/integrations/supabase/client.ts`
- Test: `src/integrations/supabase/client.test.ts` or existing test harness if one already covers the integration layer

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';

describe('supabase client env validation', () => {
  it('throws a clear error when VITE_SUPABASE_URL is missing', () => {
    expect(() => loadSupabaseClient({
      VITE_SUPABASE_URL: '',
      VITE_SUPABASE_PUBLISHABLE_KEY: 'test-key',
    })).toThrow('VITE_SUPABASE_URL is missing');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `vitest run src/integrations/supabase/client.test.ts -v`
Expected: fail because the validation helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```ts
function requireEnv(name: string, value: string | undefined) {
  if (!value) throw new Error(`${name} is missing. Create .env.local from the project example and fill it in before running the app.`);
  return value;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `vitest run src/integrations/supabase/client.test.ts -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/integrations/supabase/client.ts src/integrations/supabase/client.test.ts
git commit -m "fix: validate supabase browser env vars"
```

### Task 2: Fix the field report insert path so it uses valid geometry values and validates coordinates

**Files:**
- Modify: `src/components/FieldReportForm.tsx`
- Test: `src/components/FieldReportForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';

describe('field report geometry payload', () => {
  it('formats coordinates as a WKT point string', () => {
    expect(buildFieldReportLocation('39.5', '-106.5')).toBe('SRID=4326;POINT(-106.5 39.5)');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `vitest run src/components/FieldReportForm.test.tsx -v`
Expected: fail because the helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```ts
function buildFieldReportLocation(lat: string, lng: string) {
  return `SRID=4326;POINT(${lng.trim()} ${lat.trim()})`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `vitest run src/components/FieldReportForm.test.tsx -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/components/FieldReportForm.tsx src/components/FieldReportForm.test.tsx
git commit -m "fix: normalize field report geometry payload"
```

### Task 3: Document the Windsurf startup path and the Supabase migration model

**Files:**
- Modify: `README.md`
- Create: `.env.local.example`
- Create: `docs/superpowers/specs/2026-04-11-windsurf-supabase-design.md` if the repo expects a spec artifact before execution

- [ ] **Step 1: Write the documentation content**

```md
# Local development

1. Copy `.env.local.example` to `.env.local`.
2. Fill in local or cloud Supabase values.
3. Run `supabase start` for the full local replica, or skip it and use the hosted project as a fallback.
4. Run `npm run dev`.
```

- [ ] **Step 2: Add the env example**

```env
VITE_SUPABASE_PROJECT_ID="fzheroisjhxnairglelv"
VITE_SUPABASE_PUBLISHABLE_KEY="your-anon-key-here"
VITE_SUPABASE_URL="http://127.0.0.1:54321"
```

- [ ] **Step 3: Verify the text matches the repo’s actual Supabase surface**

Confirm the docs mention:
- `supabase/config.toml`
- `supabase/migrations/`
- `supabase/functions/`
- local vs hosted dev modes

- [ ] **Step 4: Commit**

```bash
git add README.md .env.local.example docs/superpowers/specs/2026-04-11-windsurf-supabase-design.md
git commit -m "docs: add Windsurf supabase setup guide"
```

### Task 4: Verify the repo boots cleanly in the chosen dev mode

**Files:**
- None expected unless verification exposes a missing script or startup guard

- [ ] **Step 1: Install dependencies**

Run: `npm install`
Expected: dependencies resolve locally.

- [ ] **Step 2: Start local Supabase if using the full replica**

Run: `supabase start`
Expected: local API, DB, and Studio URLs are printed.

- [ ] **Step 3: Start the frontend**

Run: `npm run dev`
Expected: Vite starts and the app loads with the configured Supabase endpoint.

- [ ] **Step 4: Exercise the Supabase-backed interactions**

Confirm:
- forecast invocation reaches `run-forecast`
- admin job buttons reach `trigger-job`
- field reports can submit
- realtime subscriptions attach without crashing

- [ ] **Step 5: Record the final verification state**

Capture the exact command outputs and any residual environment assumptions in the final handoff.
