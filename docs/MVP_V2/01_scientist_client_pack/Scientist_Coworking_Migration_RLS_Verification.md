# Scientist Co-Working Migration And RLS Verification

Status date: 2026-05-22

This note prevents partial deployment of the scientist co-working schema. The first migration creates the base tables, and the later hardening migrations add scientist/admin role gates, action closure, and daily verification. Do not expose `/scientist` against a database where only the first migration has been applied.

## Required Migration Order

| Order | Migration | Purpose | Must be present before pilot? |
|---:|---|---|---|
| 1 | `20260520120000_scientist_validation_workbench.sql` | Base validation cases and reviews | Yes |
| 2 | `20260521120000_scientist_validation_governance_hardening.sql` | Structured fields, actions, role helper, hardened RLS policies | Yes |
| 3 | `20260521143000_scientist_daily_verification_and_action_closure.sql` | Daily verification table and action closure notes | Yes |

## Final Policy Expectations

| Table | Expected access boundary |
|---|---|
| `scientist_validation_cases` | Scientist/admin users can read and update review workflow rows; anonymous and ordinary authenticated users must not get broad access. |
| `scientist_validation_reviews` | Scientist/admin users can insert/read review rows; ordinary authenticated users must not write reviews. |
| `scientist_validation_actions` | Scientist/admin users can read/update closure state; action creation remains governed by review workflow. |
| `scientist_daily_verifications` | Scientist/admin users can insert/read paired comparison rows; rows are comparison evidence only. |

## Live Verification SQL

Run this after applying migrations in Supabase SQL editor or via a read-only admin session:

```sql
select
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'public'
  and tablename in (
    'scientist_validation_cases',
    'scientist_validation_reviews',
    'scientist_validation_actions',
    'scientist_daily_verifications'
  )
order by tablename, policyname;
```

Expected result: final policies should reference the scientist/admin role helper or equivalent role-gated checks. If any final policy grants broad access to all `authenticated` users without the scientist/admin role boundary, stop the pilot and apply the hardening migrations before sharing credentials.

## Deployment Guardrail

- Apply all three migrations together for the scientist pilot.
- Verify `is_scientist_or_admin()` exists before live smoke.
- Verify `/scientist` with a scientist role and `/admin` with the same scientist account before the meeting.
- Keep `.env.scientist.local` ignored and never copy credentials into documents, screenshots, commits, or chat.

## Generated Type Guardrail

The current frontend carries local TypeScript interfaces for scientist validation payloads. After the live Supabase schema is finalized, regenerate `src/integrations/supabase/types.ts` from the deployed schema and remove any temporary broad table-client casts that are no longer needed. Until then, treat the local interfaces as the review-workflow contract and do not infer that generated Supabase types prove live-table availability.

## Secret Hygiene Guardrail

Future migrations and scheduled-job definitions should not hardcode service-role keys, project secrets, or reusable credentials. If a public anon key is unavoidable for legacy scheduled HTTP calls, label it explicitly as public anon scope and prefer Supabase vault/config references for any new secret-bearing workflow.
