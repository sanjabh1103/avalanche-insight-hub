# Recovery Research Notebook

Status date: 2026-06-19

## Checkpoint 2026-06-19T06:07:02Z

Focus: Supabase migration recovery, all-region forecast accumulation, and Modal
GPU demo restoration.

Evidence gathered:

- New Supabase target remains `cyjqvqwpdgluivjoxcfl`.
- June 19 manual inference published same-day 72-hour forecast runs for all 8
  configured regions.
- Strict demo readiness passes for `colorado_rockies` and `himalayas_nepal`.
- All-region strict full-grid proof fails only for `cascades_wa` and
  `japanese_alps`, because terrain gaps leave 14 and 13 unavailable cells.
- GitHub Modal credentials can list Modal apps through workflow run
  `27808705914`.
- Modal app list reports `avalanche-modal-worker` is `deployed` with app id
  `ap-DX6BWrPUPLnn1GuuWIdZYw`.
- Historical deploy log reports canonical web endpoint
  `https://sanjabh11--avalanche-modal-worker-worker-api.modal.run`.
- Local live probe of that endpoint still returns HTTP 404 with Modal message
  `workspace ... is disabled`.

Interpretation:

- The Modal app exists in the credentialed Modal workspace, so the earlier
  blanket statement "Modal app absent" would be wrong.
- The public endpoint and Modal app list contradict each other. Likely causes:
  stale public endpoint routing, disabled web endpoint/workspace for public
  HTTP while app metadata remains visible, or a deployment/environment mismatch.
- Launching GPU jobs is not justified until a non-mutating health route is
  reachable.

Marginal value of more work:

- High. The next non-destructive checks can distinguish stale URL from disabled
  workspace and may reveal whether a redeploy through GitHub Actions can restore
  the web endpoint.

Next action:

- Inspect Modal logs/app debug output through GitHub Actions.
- Avoid destructive Modal actions and avoid launching GPU jobs until `/health`
  is reachable.

## Checkpoint 2026-06-19T06:09:00Z

Focus: Modal endpoint contradiction.

Evidence gathered:

- Modal Debug workflow `27808767124` queried app logs for
  `avalanche-modal-worker`; no recent worker logs were emitted.
- Modal Debug workflow `27808794653` listed containers for app id
  `ap-DX6BWrPUPLnn1GuuWIdZYw`; output was `[]`.
- The deployed Modal app exists, but no containers are active.
- The local `/health` route and health-check script are not on remote `main`
  yet, so a GitHub redeploy from `main` would not include the new health gate.

Interpretation:

- The next useful step is not GPU execution. It is a fresh worker redeploy with
  a cheap `/health` route, followed by a public health probe.
- Because GitHub Actions is the only verified Modal-authenticated surface in
  this session, the deployable code must be committed and pushed before the
  deploy workflow can prove the fix.

Marginal value of more work:

- High. A narrow commit/push enables a fresh Modal deploy and separates app
  routing issues from code drift.

Next action:

- Commit and push only the focused recovery/Modal/workflow files.
- Dispatch `modal_deploy.yml` from the pushed ref.
- Probe `/health`; do not launch SAR or MTS-LSTM GPU jobs until health passes.

## Checkpoint 2026-06-19T06:14:20Z

Focus: Modal redeploy and health restoration.

Evidence gathered:

- Focused commit pushed:
  `4763d71 fix: restore modal health and all-region recovery gates` on
  `feature/european-data-shadow-pipeline`.
- Modal deploy workflow `27808891166` ran from that pushed ref and succeeded.
- Deploy log printed canonical endpoint
  `https://sanjabh11--avalanche-modal-worker-worker-api.modal.run`.
- `scripts/modal_worker_health_check.py` against that endpoint returned
  HTTP 200 and `ok=true`.
- Health response reported no missing expected routes and no missing expected
  GPU functions.

Interpretation:

- The live Modal ASGI worker is online again.
- This is a GPU compute-plane readiness proof, not a SAR/MTS-LSTM scientific
  promotion proof. No GPU training/inference job was launched during this
  checkpoint.

Marginal value of more work:

- Medium. Next useful work is to wire/update runtime secrets if any consumer
  still points at stale values, then run Supabase/forecast/demo gates. Launching
  GPU jobs has lower marginal value until a specific SAR/MTS-LSTM demo action is
  required and authorized.

Next action:

- Rerun the Supabase demo readiness gate.
- Verify repository/workflow state after the pushed commit.

## Checkpoint 2026-06-19T06:36:30Z

Focus: Backend CI stabilization after Modal/Supabase recovery commits.

Evidence gathered:

- Focused CI fix committed and pushed:
  `0309d36 fix: pin ci coverage for numba shap` on
  `feature/european-data-shadow-pipeline`.
- Local workflow YAML parse passed for:
  `.github/workflows/backend-ci.yml`, `.github/workflows/ml_pipeline.yml`, and
  `.github/workflows/modal_deploy.yml`.
- Local focused Python gate passed:
  `NUMBA_DISABLE_COVERAGE=1 .venv/bin/python -m unittest backend.tests.test_surrogate_rf backend.tests.test_run_authoritative_release_gate`
  with 15 tests run and 2 skipped.
- GitHub Backend CI workflow run `27809709380` completed successfully against
  head SHA `0309d36b43a6aabb9ddbb065cc1e246af09ff2b0`.
- The successful run included dependency installation, workflow YAML syntax
  validation, Modal app import smoke, and backend unit/gate-lock tests.

Interpretation:

- The previous GitHub runner failure was a dependency compatibility issue in
  the SHAP/Numba/Coverage import path, not a recovery-code correctness failure.
- Pinning a compatible `coverage>=7.6.1` in Backend CI resolves the GitHub
  runner failure while preserving the existing `NUMBA_DISABLE_COVERAGE` guard.

Marginal value of more work:

- Medium. The branch-level automation gate is now clean, but scheduled
  production workflows on `main` will not receive these recovery changes until
  the branch is merged or cherry-picked.

Next action:

- Prepare a PR/merge decision for the focused recovery commits.
- Do not claim scheduled daily recovery on `main` until those workflow changes
  are present on `main`.

## Checkpoint 2026-06-19T11:41:30Z

Focus: GEE/SAR commit integration, live preview smoke, and hosted Supabase
operational inventory.

Evidence gathered:

- User-provided GEE/SAR recovery commit `2ac53fe fix: resolve GEE Earth
  Engine API block and commit reaudit improvements` was verified locally and
  pushed to `feature/european-data-shadow-pipeline`.
- Pre-push checks passed:
  `bash scripts/secret_scan.sh`, Python `compileall` for `backend` and
  `scripts`, and `git diff --check origin/feature/european-data-shadow-pipeline..HEAD`.
- PR #1 remained mergeable at head
  `2ac53fe596cd80baa31023c744bbbfd272afd7ae`.
- PR checks passed on the pushed head:
  Backend CI run `27823364490`, Frontend Trust Checks runs `27823364489` and
  `27823362461`, and Netlify deploy preview.
- Live demo readiness passed against new project `cyjqvqwpdgluivjoxcfl`:
  public `forecast-products` bucket, 715 HiAVAL display-only rows, zero
  synthetic display rows, active same-day Colorado/Himalayas forecast runs, and
  strict `run-forecast` HTTP 200 with 72 hours for both regions.
- Modal worker health check returned HTTP 200 with `ok=true`,
  `runtime_provider=modal`, and no missing expected GPU functions/routes.
- Browser smoke on the Netlify preview loaded `/`, `/admin`, `/scientist`, and
  `/scientist/daily-verification` with HTTP 200 and no app console errors after
  filtering the known Netlify deploy-preview access-control 428 noise.
- Browser network calls used the new Supabase ref only; `run-forecast`,
  `avalanche_events`, `model_status`, manifest, hour-000, and runout storage
  requests returned HTTP 200.
- Hosted Postgres inventory proved 6 active cron jobs, zero old-project cron
  references, all cron commands using private URL/token helpers, helper URL
  resolving to `https://cyjqvqwpdgluivjoxcfl.supabase.co`, and helper tokens
  resolving without printing values.
- Core tables exist with live rows: `forecast_runs`, `forecast_run_hours`,
  `forecast_grids`, `model_status`, `avalanche_events`, and scientist
  validation tables. `forecast-products` bucket is public. RLS is enabled on
  forecast/event/scientist tables. `forecast_active_runs` is
  `security_invoker=true`.

Interpretation:

- New-project demo recovery is materially stronger than the earlier branch
  state: public forecast, events, Modal health, cron targeting, and preview
  routing are all backed by current evidence.
- The public forecast remains correctly framed as RF/batch publication.
  Modal/GPU is proven as an online compute plane, not as a promoted public
  SAR/MTS-LSTM forecast driver.

Marginal value of more work:

- Medium. The highest remaining value is merge/deploy coordination to get the
  green PR onto `main`, followed by production Netlify smoke and optional
  authenticated admin/scientist role smoke. Further code changes have lower
  value unless new production smoke failures appear.

Next action:

- Ask for or receive approval before merging PR #1 to `main`, because that is
  a production-affecting action.
- After merge, verify production Netlify, scheduled workflows on `main`, and
  authenticated admin/scientist access if demo credentials are available.

## Checkpoint 2026-06-19T12:36:00Z

Focus: approved merge, production Netlify smoke, and scheduled workflow
readiness on `main`.

Evidence gathered:

- PR #1 was merged to `main` with merge commit
  `47cfbb34dcf1c973f7243a174cbb92e02ae3e59a`.
- Main received two follow-up workflow hotfixes:
  `7fd8440 fix: keep ml pipeline dispatch within input limit` and
  `9cfdff6 fix: restore recovery model for scheduled inference`.
- Netlify production deploy for commit
  `9cfdff66621c68734e1330cff5115089cc16b162` is ready at
  `https://avalanche-insight-hub.netlify.app`, published at
  `2026-06-19T12:20:00.827Z`.
- Production routes returned HTTP 200 for `/`, `/admin`, `/scientist`, and
  `/scientist/daily-verification`.
- Browser smoke on production loaded the app shell. Network calls used the new
  Supabase project `cyjqvqwpdgluivjoxcfl`: `run-forecast`,
  `avalanche_events`, `model_status`, forecast manifest, hour-000, and runout
  storage requests all returned HTTP 200. No old project ref
  `fzheroisjhxnairglelv` appeared in the production index HTML or browser
  network logs.
- The only browser console item was the known Netlify access-control 428 side
  request, not an app or Supabase failure.
- GitHub Actions manual infer proof run `27825296080` completed successfully on
  `main` at `9cfdff6` in 6m38s.
- The infer run restored `model.joblib`, `training_metrics.json`, and
  `feature_schema.json` from the private Supabase `model-artifacts` bucket,
  then skipped synthetic fallback and published same-day forecasts.
- Publication proof passed for Colorado Rockies and Himalayas Nepal:
  72 hours, 400/400 ready cells per region, same-day published, zero stale
  cells, zero synthetic cells, and manifest paths under `forecast-products`.
- Live `scripts/demo_readiness_check.py` passed against new project
  `cyjqvqwpdgluivjoxcfl`: public `forecast-products`, 715 HiAVAL display-only
  rows, zero synthetic display rows, active same-day forecast runs, and strict
  `run-forecast` HTTP 200 for both proof regions.
- Modal health initially timed out once, then passed on retry with HTTP 200,
  `runtime_provider=modal`, and no missing expected routes or GPU functions.

Interpretation:

- The main production surface is now aligned with the migrated Supabase project
  and the PR recovery gates.
- Scheduled inference readiness is materially improved: the workflow no longer
  depends on a same-run training artifact and no longer silently proceeds when
  the new-project corpus has zero `training_eligible` severe events.
- Scientific guardrails remain intact. The workflow restores a named vetted
  recovery model artifact and otherwise requires real-data training; it does
  not reintroduce a synthetic fallback model.

Residual risks:

- Full all-region scheduled inference was not rerun in this checkpoint; the
  proof run used Colorado Rockies and Himalayas Nepal as the fast demo-primary
  subset.
- The `model-artifacts` restore bucket is a new private operational dependency
  and should remain private with service-role-only workflow access.
- Authenticated admin/scientist role checks were not repeated because no demo
  credentials were supplied in this checkpoint.

Next action:

- Let the normal `0 6 * * *` UTC scheduled run exercise the all-region default,
  or manually dispatch an all-region run during a wider verification window.
