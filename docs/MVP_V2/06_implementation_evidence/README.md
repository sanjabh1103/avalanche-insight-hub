# Implementation Evidence

Status date: 2026-05-22

This folder contains reference copies of the implementation artifacts that support the scientist co-working system. These copies are included so a technical reviewer can inspect the relevant source, scripts, migrations, and tests from one place.

## Important Source-Of-Truth Rule

The executable source of truth remains in the original project folders:

| Evidence Folder | Executable Source Location |
|---|---|
| `code/` | `src/` |
| `scripts/` | `backend/scripts/` |
| `migrations/` | `supabase/migrations/` |
| `tests/` | `src/test/` and `backend/tests/` |

If a code file changes in the original location, refresh this evidence copy before the next client scientist meeting.

## What This Evidence Proves

| Area | Evidence Type | Boundary |
|---|---|---|
| Scientist-safe access | `RoleAccessGate`, scientist pages, route tests | Admin access remains separate |
| Structured review | Workbench component and validation library | Review output is governed, not automatic retraining |
| Daily verification | Daily verification page and tests | Paired comparison evidence only |
| Evidence drawer | Cell evidence drawer component and tests | Evidence display support, not official warning authority |
| RLS and schema | Supabase migrations | Must be applied in order before live use |
| Demo/scientist scripts | Backend scripts and tests | Synthetic/demo data must stay non-training and non-production |
