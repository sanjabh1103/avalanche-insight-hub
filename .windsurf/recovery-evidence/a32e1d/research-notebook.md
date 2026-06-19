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
