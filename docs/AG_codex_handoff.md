# Supabase Migration Handoff

Status date: 2026-06-18

The runtime target is the new Supabase project `cyjqvqwpdgluivjoxcfl`:

- Dashboard: https://supabase.com/dashboard/project/cyjqvqwpdgluivjoxcfl
- Runtime URL: `https://cyjqvqwpdgluivjoxcfl.supabase.co`
- Old paused project: `fzheroisjhxnairglelv`

No operational secrets belong in this file. Use the Supabase dashboard,
Netlify dashboard, local ignored `.env` files, or a password manager for keys.

## Current Findings

- `supabase/config.toml` points at `cyjqvqwpdgluivjoxcfl`.
- The frontend Supabase client reads `VITE_SUPABASE_PUBLISHABLE_KEY`; it no
  longer prefers a stale `VITE_SUPABASE_ANON_KEY`.
- The Supabase CLI link has been corrected to `cyjqvqwpdgluivjoxcfl`; the stale
  local `.temp/project-ref` value for `fzheroisjhxnairglelv` was removed by
  relinking.
- A live read-only inventory on 2026-06-18 showed the core forecast/scientist
  tables and `forecast-products` bucket exist on the new project.
- Live cron inventory on 2026-06-18 showed all scheduled jobs use
  `private.get_supabase_url()` and none target the paused project.
- The new DB initially had zero `avalanche_events`, zero `forecast_runs`, zero
  `forecast_run_hours`, and zero `forecast_grids`, with placeholder
  `model_status` rows. That baseline is no longer current: the demo core now
  has 715 real HiAVAL historical display-only events and same-day forecast
  publication for Colorado Rockies and Himalayas Nepal.
- A retained GitHub Actions training artifact from run `24979677112`
  (`backend/artifacts/20260427T095428Z`) was restored locally. Its dataset
  metadata is `real_event_join_v1`, with 1000 positive `gee_sar` events and
  3000 sampled negatives; it is not a synthetic bootstrap artifact.
- A same-day Colorado Rockies publication was generated on 2026-06-18 against
  the new project:
  - `forecast_run_id`: `6fdf33c6-2d8e-4f60-b061-1c0a16007995`
  - `manifest_storage_ref`:
    `forecast-products/avalanche/colorado_rockies/6fdf33c6-2d8e-4f60-b061-1c0a16007995/manifest.json`
  - `forecast_date`: `2026-06-18`
  - `horizon_hours`: `72`
  - `grid_size`: `20`
  - `ready_cell_count`: `400`
  - `synthetic_inputs_present`: `false`
  - `snowpack_proxy_mode`: `regional`
- The publication command emitted a feature-schema drift warning because the
  retained April artifact hash differs from the current code hash. Treat this as
  a recovered RF/batch technical publication, not as a newly retrained current
  model.
- `STRICT_FORECAST_GATE=true bash scripts/supabase_migration_smoke.sh` passes
  against the new project for both `colorado_rockies` and `himalayas_nepal`.
- `scripts/demo_readiness_check.py` is the current non-mutating readiness gate.
  It verifies the target project ref, public `forecast-products` bucket, at
  least 700 HiAVAL display-only rows, zero synthetic display rows, active
  72-hour same-day forecast runs for Colorado and Himalayas, and strict
  `run-forecast` API responses for both regions.
- HiAVAL v1.3.0 was imported from Zenodo DOI `10.5281/zenodo.18257425` with
  `source='historical_import'`, `fusion_source='hiaval_v1_3_0'`,
  `training_eligible=false`, and `label_role='display_only'`. It is real
  historical inventory data for display/provenance, not recovered old-project
  rows and not training labels.
- Production Netlify was redeployed after the UI provenance fix. Fresh browser
  traffic now calls the new project and requests
  `avalanche_events?...source,fusion_source,event_type...`.
- Netlify production was redeployed after the scientist route bundle was
  missing from the prior production asset:
  - Production URL: https://avalanche-insight-hub.netlify.app
  - Deploy URL:
    https://6a33a5de5f75a3eeb8f89e9f--avalanche-insight-hub.netlify.app
  - Deploy logs:
    https://app.netlify.com/projects/avalanche-insight-hub/deploys/6a33a5de5f75a3eeb8f89e9f
- Browser smoke after clearing the old PWA service-worker cache loaded the
  current `assets/index-P9HUN58k.js` bundle and verified:
  - `/` renders `PRECOMPUTED BATCH - READY (72h)` for Colorado Rockies.
  - `/scientist` renders the scientist authentication gate.
  - `/scientist/daily-verification` renders the daily verification
    authentication gate.
  - `/admin` renders the operator authentication gate.
- Demo admin/scientist accounts were provisioned on the new project with
  `app_metadata.roles` and verified through production browser login:
  - Admin demo login reaches `/admin` content with active jobs/model evidence.
  - Scientist demo login reaches `/scientist` workbench/readiness content.
  - Scientist demo login reaches `/scientist/daily-verification` analytics and
    records content.
- `scripts/scientist_admin_rls_smoke.mjs` verifies new-project demo users and
  role boundaries without printing credentials: scientist/admin can read the
  labelled smoke case, scientist can seed case/review/action/daily verification
  rows, admin can resolve the smoke action, and anonymous/ordinary viewer access
  is denied.
- Cron auth material is installed in Supabase Vault for the new project:
  `job_dispatch_token` and `anon_key` resolve through the private helper
  functions without printing secret values.
- `trigger-job` auth smoke on 2026-06-18 rejected an unauthenticated
  `static_precompute` request with HTTP 401 and accepted a valid job-token
  request with HTTP 200, creating a simulated `compute_jobs` row.
- Phase 8 evidence artifacts were created under
  `.windsurf/recovery-evidence/a32e1d/`: `recovery-summary.md`,
  `supabase-inventory.md`, `forecast-proof.json`, `browser-smoke.md`,
  `cron-edge-gpu-checks.md`, `corpus-restoration-audit.md`, and
  `security-followups.md`.
- `scripts/avalanche_events_corpus_audit.mjs` originally verified the corpus
  gap without printing secrets: the partner handoff CSV had 0 rows, the only
  local event CSV with rows was explicitly synthetic, and retained train
  artifacts contained model/metrics/schema files but no source rows. The
  current no-cost replacement corpus is HiAVAL, imported through
  `scripts/import_hiaval_historical_events.py`.
- `backend.news_ingest` now defaults to `gemini-2.5-flash` and accepts either
  `SUPABASE_URL` or `VITE_SUPABASE_URL`. A live bounded run on 2026-06-18
  fetched NewsData candidates but inserted 0 rows because Gemini classified the
  checked articles as not concrete avalanche events.
- The GitHub scheduled `infer` workflow run `27752839019` failed on
  2026-06-18 because scheduled inference tried to download
  `avalanche-train-artifacts` from the same run, but no train job runs in that
  scheduled event. The workflow now trains a fresh real-data model only when no
  `model.joblib` was restored, then runs daily inference. This keeps scheduled
  publication independent of same-run artifact availability without adding a
  synthetic model fallback.
- GEE SAR extraction is bounded by `--region-key`, `--dry-run`,
  `GEE_REGION_KEYS`, and `GEE_DRY_RUN`. A local Himalayas dry-run attempt failed
  before extraction because Google project `511429282057` has
  `earthengine.googleapis.com` disabled. Do not claim SAR detections or
  `grounded_himalayan_evidence=true` until that Google API is enabled and a
  clean dry-run/apply sequence is verified.
- `supabase_migrations.schema_migrations` metadata was repaired through
  `scripts/repair_supabase_migration_history.sh` and the normal Supabase CLI
  repair path; the remote table now exists with 50 local migration versions
  recorded and latest version `20260618160000`.
- The new project database password now works with the normal CLI path:
  `supabase migration list --linked` connects and
  `supabase db push --dry-run --linked` reports the remote database is up to
  date.
- Security Advisor remediation on 2026-06-18 reduced findings from 19 warnings
  to 2 warnings. Cleared findings include all mutable function search paths,
  `public.is_scientist_or_admin()` security-definer exposure, and permissive
  always-true insert policies. Residual warnings are `pg_net` extension
  placement and leaked-password protection.
- `.github/workflows/secret-scan.yml` now runs the repo-local credential-pattern
  scan on pull requests and branch pushes with read-only permissions.
- `forecast-products` must be public-read for published forecast artifacts and
  should use the same bucket settings as
  `20260501123000_forecast_runs_publication_plane.sql`.
- Cron should use a dedicated `JOB_DISPATCH_TOKEN`, not a service-role or anon
  key fallback.
- The prior documented Colorado Rockies run
  `4822ecf8-defa-4479-ac86-cf9eb7cf2f08` is not recoverable from public storage
  right now: the old project hostname did not resolve and the new bucket returned
  object not found for that manifest path.
- A non-destructive old-project REST count probe for `avalanche_events` against
  `fzheroisjhxnairglelv` failed because the inactive old project hostname does
  not resolve, so there is no verified live pull path for the old corpus until
  the project is unpaused or an exported backup is provided.

## Safe Local Commands

Run the read-only smoke check with a publishable key loaded from a secure shell:

```bash
export SUPABASE_PUBLISHABLE_KEY="<new-project-publishable-key>"
bash scripts/supabase_migration_smoke.sh
```

Run the hard public forecast gate:

```bash
export SUPABASE_PUBLISHABLE_KEY="<new-project-publishable-key>"
STRICT_FORECAST_GATE=true bash scripts/supabase_migration_smoke.sh
```

Strict mode requires `source="forecast_runs"`, `hours=72`,
`sameDayPublished=true`, a manifest path, and model metadata that does not mark
the run as synthetic/demo fallback.

Run the SQL inventory against the new project only:

```bash
supabase link --project-ref cyjqvqwpdgluivjoxcfl --password "<new-project-db-password>"
supabase db query --linked --file scripts/supabase_migration_inventory.sql
```

Update Netlify env and trigger a cache-cleared deploy without hardcoding tokens:

```bash
export NETLIFY_TOKEN="<netlify-token>"
export SUPABASE_PUBLISHABLE_KEY="<new-project-publishable-key>"
bash scripts/netlify_env_redeploy.sh
```

Scan the repo for accidentally staged secrets:

```bash
bash scripts/secret_scan.sh
```

Run the current no-mutation demo readiness gate:

```bash
python3 scripts/demo_readiness_check.py
```

Run the bounded live news ingestion path. The script now accepts
`VITE_SUPABASE_URL` from `.env` and skips safely when credentials are missing:

```bash
set -a
source .env
set +a
NEWS_MAX_ARTICLES=10 python3 -m backend.news_ingest
```

After enabling Earth Engine API for Google project `511429282057`, test SAR
without writes first:

```bash
set -a
source .env
set +a
GEE_MAX_CENTROIDS_PER_REGION=3 \
GEE_LOOKBACK_DAYS=3 \
python3 -m backend.gee_extractor --region-key himalayas_nepal --dry-run
```

Only after that dry-run prints clean region counts should a live SAR insert be
considered:

```bash
set -a
source .env
set +a
GEE_MAX_CENTROIDS_PER_REGION=3 \
GEE_LOOKBACK_DAYS=3 \
python3 -m backend.gee_extractor --region-key himalayas_nepal
```

Provision and smoke the local demo admin/scientist RLS path:

```bash
node scripts/scientist_admin_rls_smoke.mjs
```

This script refuses non-`cyjqvqwpdgluivjoxcfl` URLs, only mutates local
`*@insight-hub.local` demo users, and prints redacted user identifiers.

Repair migration metadata if a fresh restored project is missing
`supabase_migrations.schema_migrations`:

```bash
bash scripts/repair_supabase_migration_history.sh
```

This script repairs metadata only. It creates/upserts the Supabase migration
history table from local migration filenames; it does not execute migration
bodies.

Audit whether a real `avalanche_events` corpus is available for restoration:

```bash
node scripts/avalanche_events_corpus_audit.mjs
```

After the old project is unpaused and its REST hostname resolves, preview the
real corpus without writing to the new project:

```bash
export OLD_SUPABASE_URL="https://fzheroisjhxnairglelv.supabase.co"
export OLD_SUPABASE_SERVICE_ROLE_KEY="<old-project-service-role-key>"
node scripts/restore_avalanche_events_from_project.mjs
```

Only after reviewing the reported source count, import/upsert by stable event
ID with `node scripts/restore_avalanche_events_from_project.mjs --apply`. The
script refuses any destination other than `cyjqvqwpdgluivjoxcfl` and defaults
to dry-run.

Run the public submission RLS smoke after policy changes:

```bash
node scripts/public_submission_rls_smoke.mjs
```

## Demo Gate

The public forecast API/storage part of the demo gate now passes for
`colorado_rockies` and `himalayas_nepal`: `run-forecast` returns HTTP 200 with
`source="forecast_runs"`, 72 hours, same-day publication, and manifest path.
`scripts/demo_readiness_check.py` is the authoritative repeatable gate for this
two-region proof.

The production browser smoke now passes for the public route, unauthenticated
auth gates, and authenticated demo lanes: the public page renders the recovered
72-hour batch; `/admin` logs in as the local demo admin and shows system/model
evidence; `/scientist` logs in as the local demo scientist and shows workbench
content; `/scientist/daily-verification` shows the seeded paired-comparison
record and analytics.

For scientific honesty in the demo:

- Forecasts are recovered RF/batch technical publications from real weather
  inputs, not newly validated all-region operational forecasts.
- HiAVAL events are historical display-only observations, not training labels.
- News ingestion is enabled but writes only when Gemini extracts a concrete,
  in-region avalanche event above the confidence threshold.
- SAR/GEE remains externally blocked until Earth Engine API is enabled for the
  configured Google project.

## Verification Evidence

Commands rerun on 2026-06-18:

```bash
STRICT_FORECAST_GATE=true bash scripts/supabase_migration_smoke.sh
bash scripts/secret_scan.sh
git diff --check
npm run lint
npm run test -- src/test/supabase-config.test.ts src/test/forecast-restore.test.ts src/test/grid-utils-hourly.test.ts src/test/admin-access-gate.test.tsx src/test/role-access-gate.test.tsx src/test/scientist-validation-workbench.test.tsx src/test/scientist-daily-verification.test.tsx
npm run build
supabase db query --linked --file scripts/supabase_migration_inventory.sql
node scripts/scientist_admin_rls_smoke.mjs
.venv/bin/python -m pytest backend/tests/test_surrogate_rf.py backend/tests/test_train_model_publish_guard.py
bash scripts/repair_supabase_migration_history.sh
node scripts/avalanche_events_corpus_audit.mjs
```

Observed results:

- Strict Supabase smoke passed with HTTP 200 REST probes and `run-forecast`
  returning `ok=true`, `source="forecast_runs"`, `hours=72`,
  `sameDayPublished=true`, a manifest path, and no synthetic/demo fallback
  metadata.
- Secret scan found no tracked or unignored candidate secrets.
- Diff whitespace check passed.
- Lint passed.
- Focused Vitest suite passed: 7 files, 23 tests.
- Vite production build passed and generated scientist/admin chunks.
- Remote inventory showed 2 active forecast runs, 144 forecast-run-hour rows, 2
  forecast grids, 2 model-status rows, 1 compute job from the auth smoke, core forecast/scientist objects present,
  `forecast-products` public, and all expected cron jobs active with
  `uses_dynamic_project_helper=true` and `targets_old_project=false`.
- Remote inventory also showed `private.get_supabase_url()` resolves to the new
  project and `private.get_job_dispatch_token()` plus
  `private.get_supabase_apikey()` return present redacted health status.
- Scientist/admin RLS smoke passed with one labelled smoke case, one review, one
  action, one daily verification record, ordinary viewer access hidden, anonymous
  access hidden, and viewer insert rejected with Postgres/RLS code `42501`.
- GitHub Actions and Supabase Edge secret listings show Modal-related secret
  names exist without exposing values; local Modal ASGI import smoke now checks
  `/health`, `/sar-segment`, `/train-sar-unet`, `/train-mtslstm`,
  `/infer-mtslstm`, and `/evaluate-release`. The worker declares T4 GPU
  functions for SAR segmentation, SAR U-Net training, SAR checkpoint
  evaluation, and MTS-LSTM training. GitHub deployment run `25589982702`
  succeeded on 2026-05-09, but live probes on 2026-06-18 and a `/health` probe
  on 2026-06-19 return HTTP 404 because the Modal workspace is disabled. The
  worker code path is restored; the live worker is not currently available and
  is not part of the public forecast proof.
- Production browser login smoke passed for `/admin`, `/scientist`, and
  `/scientist/daily-verification` using the local demo accounts.
- Edge `trigger-job` smoke rejected missing auth with HTTP 401 and accepted the
  Vault/Edge job token with HTTP 200 for `static_precompute`.
- Backend RF/publish-guard tests passed after installing `pytest` into the
  local `.venv`: 13 passed, 2 skipped.
- `.windsurf/recovery-evidence/a32e1d/forecast-proof.json` validates as JSON.
- Migration metadata repair passed: `supabase_migrations.schema_migrations`
  exists with 50 local migration versions and latest `20260618160000`.
- Avalanche events corpus audit passed as a no-go restoration proof: no
  admissible real corpus rows were found locally or in retained GitHub train
  artifacts; the only populated CSV candidate is synthetic and must not be used
  for scientific recovery.
- Security Advisor refresh passed as a partial remediation proof: 19 warnings
  were reduced to 2 warnings, clearing all function search-path,
  `is_scientist_or_admin()` security-definer, and always-true insert-policy
  findings.
- Public submission RLS smoke passed: safe anonymous field report and alert
  inserts returned HTTP 201, while privileged field-report state and invalid
  alert endpoint attempts were rejected with HTTP 401.
- GitHub scheduled inference failure was reproduced from Actions logs for run
  `27752839019`: no same-run `avalanche-train-artifacts` artifact was available,
  then `backend.daily_inference` failed because `backend/artifacts` had no
  `model.joblib`. `.github/workflows/ml_pipeline.yml` now adds a guarded
  real-data training step before inference when the artifact is absent.
- A manual all-region June 19 publication wrote 72-hour, same-day forecast runs
  for all 8 configured public regions. The strict full-grid process exit failed
  for `cascades_wa` and `japanese_alps` because terrain gaps left 14 and 13
  cells unavailable, respectively; all 8 still have published manifest paths.
  The workflow now keeps all-region scheduled accumulation on the same-day gate
  and makes the full-grid gate an explicit manual input for demo-primary proof
  subsets.

## Current Blockers

- The old project's original `avalanche_events` corpus is still not reachable:
  a non-destructive REST probe to `fzheroisjhxnairglelv` failed because the
  inactive old hostname does not resolve. The new project now has the no-cost
  HiAVAL display-only corpus, but that is intentionally not a recovered
  training-label corpus. Old-corpus restoration still needs unpaused old-project
  access, an exported backup, retained source event rows, or another governed
  ingestion run.
- The workflow fallback training step has been patched locally. It must be
  committed and pushed before the next scheduled GitHub `infer` run can prove
  the CI fix in Actions.
- All-region same-day accumulation is now live for June 19, but full-grid proof
  across all 8 regions is not true until Cascades and Japanese Alps terrain
  gaps are resolved. Colorado Rockies and Himalayas Nepal pass the strict
  same-day demo readiness gate.
- Modal/GPU code and CI route checks have been restored locally, including a
  non-mutating `/health` route and `scripts/modal_worker_health_check.py`, but
  the current configured Modal workspace still returns HTTP 404
  `workspace ... is disabled`. Live GPU proof requires enabling the Modal
  workspace or deploying the worker into an enabled Modal workspace/profile,
  then rerunning the health check and the relevant dispatch workflow.
- Residual Security Advisor warnings are `extension_in_public` for `pg_net` and
  disabled leaked-password protection. `pg_net` is `extrelocatable=false` and
  cron SQL calls `net.http_post`, so clearing it requires destructive
  drop/recreate testing. A scoped leaked-password-protection config request
  returned HTTP 402 because the feature requires Supabase Pro or higher.
- The first browser check after deploy still saw old `/scientist` 404s from the
  stale PWA service worker. Clearing service workers/caches resolved it; users
  with the old app cached may need a hard refresh or service-worker update.
- A synthetic bootstrap training attempt was intentionally interrupted because
  it reached external Open-Meteo fetches through the MTS-LSTM head. Synthetic
  bootstrap must remain a labelled technical fallback, not proof of scientific
  recovery.
- If a degraded UI-only artifact is needed before the real corpus/artifact is
  restored, it must be explicitly labelled as a technical demo fallback and must
  not be used to claim current scientific forecast proof.
