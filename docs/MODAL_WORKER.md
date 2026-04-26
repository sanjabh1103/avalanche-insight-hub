# Modal Worker Runbook

This project uses Modal as the only GPU execution backend for the Wave 4 SAR and MTS-LSTM worker flows. GitHub Actions and `trigger-job` are dispatch layers only.

## Required Secrets and Runtime

- `MODAL_WORKER_URL`: base URL for the deployed worker
- `MODAL_WORKER_TOKEN`: bearer token for the worker. The ASGI worker validates `Authorization: Bearer <token>` on every request.
- `SAR_UNET_MODEL_PATH`: checkpoint path available to the worker runtime
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SAR_MASK_BUCKET`: defaults to `sar-masks`
- `SAR_UNET_MODEL_VERSION`: defaults to `sar_unet_resnet34_shadow_v1`
- `SAR_UNET_PROMOTED`: keep unset or `false` in shadow mode

The target Supabase project must already contain the private `sar-masks` bucket created by migration `20260425170000_create_sar_masks_bucket.sql`.
The target Supabase project must also contain the held-out registry tables created by migration `20260425200000_sar_release_reference_registry.sql`.

## In-Repo Operator Entry Points

- `.github/workflows/bootstrap_pinned_gate.yml`
  Temporary manual GitHub Actions workflow for cloud-to-cloud SnowSlide seeding when the archive is too large for local hardware. It downloads a direct Sentinel-1 SAR archive URL into the runner’s ephemeral storage, runs a strict `--validate-only` preflight, then runs `seed_snowslide_truth` and `materialize_release_baseline_masks` so the authoritative set ends `active`.
- `python -m backend.scripts.bootstrap_release_gate`
  Operator bootstrap CLI for the GitHub-first rollout path. It validates `.env`, syncs secrets into GitHub/Modal/Supabase, seeds the authoritative SnowSlide held-out registry from a local zip, deploys the Modal worker, seeds the DEM volume, and then stops at `refs_ready_only` until a real `SAR_UNET_MODEL_PATH` is configured.
- `python -m backend.scripts.seed_snowslide_truth`
  One-off bootstrapping CLI. Seeds authoritative SnowSlide truth masks and canonical scene stacks into `sar-masks`, then registers the held-out set in Supabase as `draft`.
- `python -m backend.scripts.materialize_release_baseline_masks`
  Materializes `baseline_mask.tif` for a registered SnowSlide reference set and marks the set `active` when complete.
- `python -m backend.sar_release_manifest`
  Builds a held-out `evaluate-release` manifest either from an ad hoc JSON/CSV registry or from an authoritative SnowSlide `reference_set_key`.
- `python -m backend.sar_release_promote`
  Promotes a successful SAR evaluation by rerunning segmentation in promoted mode or, as recovery, flipping existing shadow rows.
- `modal deploy backend/modal_worker_app.py`
  Deploys the in-repo Modal ASGI worker surface that exposes the worker endpoints below on one base URL.
- `modal run backend/modal_worker_app.py --source-root backend/data/dem`
  Seeds Git LFS-backed DEM assets into the persistent Modal volume at `/artifacts/dem`.

## Cloud Bootstrap Workflow

When the SnowSlide archive is too large to stage on a local machine, use the temporary manual GitHub workflow instead of the local zip bootstrap.

Trigger:
- GitHub Actions UI only via `workflow_dispatch`
- protected by the `production` environment

Inputs:
- `DATASET_URL` required
- `REFERENCE_SET_KEY` optional, defaults to `snowslide-heldout-v1`
- `SOURCE_VERSION` optional; if blank, the workflow uses the current UTC date

Security and source restrictions:
- `DATASET_URL` must be a direct downloadable archive URL, not a record landing page
- only SAR-compatible Sentinel-1 held-out archives are allowed
- IAS/webcam/optical datasets are invalid for the pinned gate and are rejected in preflight before any storage or Supabase mutation
- allowed hosts are fixed to:
  - `envidat.ch`
  - `www.envidat.ch`
  - `zenodo.org`
  - `www.zenodo.org`
  - `slf.ch`
  - `www.slf.ch`
- the workflow rejects non-`https` URLs, custom ports, embedded credentials, and non-ZIP payloads

Execution sequence:
1. download the archive into the runner workspace with quoted shell input
2. run `python -m backend.scripts.seed_snowslide_truth --source-zip snowslide_archive.zip --validate-only ...`
3. only if preflight returns `status=ok`, run `python -m backend.scripts.seed_snowslide_truth --source-zip snowslide_archive.zip ...`
4. run `python -m backend.scripts.materialize_release_baseline_masks --reference-set-key ...`
5. fail unless the preflight and both mutation JSON payloads return `status=ok` and baseline materialization returns `reference_set_status=active`
6. clean up the downloaded archive and JSON result files in an `always()` step

This workflow seeds authoritative truth and baseline refs only. It does **not** run held-out `sar-segment`, `evaluate_release`, promoted reruns, or `train_mtslstm`. It remains operationally paused until the operator supplies a valid SAR archive URL.

## Refs-Ready Bootstrap

The primary operator path is now the local bootstrap CLI. It reads `.env` explicitly and never prints secret values.

Required local `.env` inputs:
- `SUPABASE_URL` or `VITE_SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY` or `VITE_SUPABASE_PUBLISHABLE_KEY`
- `GEE_SERVICE_ACCOUNT_EMAIL`
- `GEE_KEY_FILE`
- `MODAL_WORKER_TOKEN`
- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`
- `ADMIN_USER_EMAILS` and/or `ADMIN_USER_IDS`

Optional for this slice:
- `SAR_UNET_MODEL_PATH`

If `SAR_UNET_MODEL_PATH` is absent, the bootstrap completes in `refs_ready_only` state and intentionally does **not** attempt held-out `sar-segment`, `evaluate_release`, promoted reruns, or `train_mtslstm` with `sar_release_gate_passed=true`.

Recommended sequence:

```bash
python -m backend.scripts.bootstrap_release_gate validate-env --env-file .env

python -m backend.scripts.bootstrap_release_gate refs-ready \
  --env-file .env \
  --source-zip /absolute/path/to/real-snowslide.zip \
  --set-key snowslide-heldout-v1 \
  --source-version 2026-04-25 \
  --repo sanjabh1103/avalanche-insight-hub \
  --project-ref fzheroisjhxnairglelv \
  --apply
```

What `refs-ready` does:
1. syncs GitHub secrets, the Modal secret, and Supabase project secrets
2. seeds authoritative SnowSlide truth and canonical held-out stacks from the local zip
3. materializes `baseline_mask.tif` for the authoritative set and activates it; seeding alone leaves the set in `draft`
4. deploys `backend/modal_worker_app.py`
5. seeds the DEM volume via `modal run backend/modal_worker_app.py --source-root backend/data/dem`
6. syncs the deployed `MODAL_WORKER_URL` back into GitHub and Supabase

Confirm these checkpoints before moving on:
- `sar_release_reference_sets.status = active`
- every held-out item has `truth_mask_asset_ref`, `stack_asset_ref`, and `baseline_mask_asset_ref`
- Modal worker is deployed on a single base URL
- `MODAL_WORKER_URL` is present in both GitHub secrets and Supabase secrets

Blocked next step until real SAR weights exist:
- once `SAR_UNET_MODEL_PATH` points to a real checkpoint, the next slice will run held-out `sar-segment`, build the authoritative manifest, and dispatch `evaluate_release`

## Worker Endpoints

### `POST /sar-segment`

Runs shadow-mode SAR segmentation and writes governed SAR events plus `sar_detection_artifacts` when weights and Supabase credentials are present.

Request body:

```json
{
  "hazard_type": "avalanche",
  "scenes": [
    {
      "scene_id": "S1A_TEST_001",
      "region_key": "colorado_rockies",
      "scene_time": "2026-04-25T00:00:00+00:00",
      "bbox": [-107.0, 39.0, -106.0, 40.0],
      "channels": [[[0.0]], [[0.0]]]
    }
  ]
}
```

Accepted scene payloads:
- `channels` as `(2, H, W)` or `(H, W, 2)`
- `vv` + `vh`
- `stack_ref`, `stack_path`, or `stack_url` pointing to a two-channel array

For authoritative held-out reruns, `sar-segment` may also receive:

```json
{
  "reference_set_key": "snowslide-heldout-v1",
  "prediction_model_version": "sar_unet_resnet34_shadow_v1",
  "shadow_mode": true
}
```

In that mode the worker loads held-out scenes from the authoritative registry and writes prediction masks under:

- `sar-masks/heldout/snowslide/<dataset_version>/<split>/<region_key>/<scene_id>/predictions/<model_version>/prediction_mask.tif`

Response fields:
- `status`
- `persisted_events`
- `artifact_rows_persisted`
- `mask_asset_refs`
- `detections`
- `checkpoint_key_mismatch` when warm-start loading had missing or unexpected keys

### `POST /train-mtslstm`

GPU-side MTS-LSTM training entrypoint. The worker should execute the repo training flow with Modal as the runtime provider and return the strict Wave 4 gate summary.

Recommended request body:

```json
{
  "hazard_type": "avalanche",
  "dataset_snapshot_id": "latest",
  "epochs": 50,
  "early_stopping": true,
  "minimum_epochs_before_early_stopping": 10,
  "patience_early_stopping": 7,
  "shadow_mode": true,
  "promotion_rule": "strict_pss_gt_rf_and_brier_lte_rf",
  "sar_release_gate_passed": false
}
```

Required response fields:
- `status`
- `model_artifact_ref`
- `dataset_snapshot_id`
- `lstm_pss`
- `rf_pss`
- `lstm_brier`
- `rf_brier`
- `shadow_quality_gate_passed`
- `sar_release_gate_passed`
- `production_eligibility_gate_passed`
- `epochs_requested`
- `epochs_completed`
- `early_stopped`

### `POST /infer-mtslstm`

GPU-side MTS-LSTM inference entrypoint. It should run batch inference against the latest artifact and return the inference manifest summary plus whether the artifact is still shadowed.

### `POST /evaluate-release`

Runs held-out SAR evaluation and returns the gate decision used before any SAR promotion.

Official gate usage should prefer `reference_set_key` over ad hoc refs. The worker can build the authoritative manifest from Supabase when given:

```json
{
  "reference_set_key": "snowslide-heldout-v1",
  "prediction_model_version": "sar_unet_resnet34_shadow_v1"
}
```

## Evaluation Manifest Contract

`evaluate-release` must receive a manifest with a non-empty `scenes[]` list. Each scene must include:

- `region_key`
- `prediction_mask`
- `truth_mask`

Mask refs may be supplied as:

- inline arrays
- local file paths
- `http(s)` URLs reachable by the worker
- Supabase Storage refs in `bucket/path` form, for example `sar-masks/2026-04-25/colorado_rockies/prediction_mask.tif`

Baseline gate input must be supplied in one of these forms:

1. `baseline_f1_floor`: positive float already derived from the GEE threshold baseline on the same held-out set
2. `baseline_metrics.f1`: positive float, with the worker applying `baseline_margin`
3. `baseline_mask` on every held-out scene, allowing the worker to derive baseline metrics against `truth_mask`

If none of those are present, the worker returns `status=invalid_manifest` and does not pass the gate.

Recommended evaluation payload:

```json
{
  "baseline_margin": 0.05,
  "scenes": [
    {
      "region_key": "colorado_rockies",
      "prediction_mask": "sar-masks/heldout/colorado_rockies/prediction_mask.tif",
      "truth_mask": "https://example-bucket.invalid/heldout/colorado_rockies/truth_mask.npy",
      "baseline_mask": "sar-masks/heldout/colorado_rockies/gee_threshold_mask.tif"
    }
  ]
}
```

To build this manifest from an ad hoc scene registry file:

```bash
python -m backend.sar_release_manifest \
  --registry /path/to/heldout-scenes.json \
  --split release-20260425 \
  --output /tmp/eval_manifest.json
```

To build the authoritative gate manifest from Supabase:

```bash
python -m backend.sar_release_manifest \
  --reference-set-key snowslide-heldout-v1 \
  --prediction-model-version sar_unet_resnet34_shadow_v1 \
  --output /tmp/eval_manifest.json
```

Registry rows must contain:

- `scene_id`
- `region_key`
- `truth_mask` or `truth_mask_format`

Optional fields:

- `prediction_mask`
- `baseline_mask`
- `baseline_metrics`
- `baseline_f1_floor`
- `scene_time`

If `prediction_mask` or `baseline_mask` is omitted, the builder derives them under:

- `sar-masks/heldout/<split>/<region_key>/<scene_id>/prediction_mask.tif`
- `sar-masks/heldout/<split>/<region_key>/<scene_id>/baseline_mask.tif`

If `truth_mask` is omitted, the builder derives it from `truth_mask_format` under:

- `sar-masks/heldout/<split>/<region_key>/<scene_id>/truth_mask.(tif|npy|npz)`

The release response should surface:
- `status`
- `f1`
- `iou`
- `false_positive_rate`
- `scene_count`
- `region_coverage`
- `baseline_f1_floor_used`
- `beats_baseline`

## Operational Notes

- Shadow mode is the default. Keep `SAR_UNET_PROMOTED=false` until held-out evaluation passes.
- Promoted mode is stricter than shadow mode: checkpoint key mismatches should fail the worker instead of only warning.
- `beats_baseline=true` requires strict improvement: F1 must exceed `baseline_f1_floor_used`, not merely equal it.
- `evaluate_release` now fails the GitHub job if the worker returns anything other than `status=ok`. A valid evaluation with `beats_baseline=false` still completes successfully.
- GitHub Actions does not run local GPU code for these flows. If `MODAL_WORKER_URL` is missing, dispatch jobs fail fast by design.
- Production-mutating GitHub jobs now run behind the `production` environment. Configure required reviewers, restrict deployment branches to `main`, and enable `prevent self-review` before using the rollout path.
- DEM GeoTIFFs are no longer shipped inside the Modal image. They are seeded once into the persistent `avalanche-artifacts` volume under `/artifacts/dem`.
- `modal_deploy.yml` now checks out Git LFS content before seeding the DEM volume.
- Wave 4 cutover is stricter than the shadow artifact gate. A trained LSTM artifact becomes production-eligible only when all three conditions are true:
  - `shadow_quality_gate_passed=true`
  - `sar_release_gate_passed=true`
  - promoted `sar_unet` volume meets the configured event, region, and scene-date thresholds
- `trigger-job` now treats malformed or missing `evaluation_manifest_json` as a request-validation failure and returns a clean 400 instead of a generic 500.
- Ad hoc `evaluation_manifest_json` and `evaluation_manifest` requests are now admin-only. `trigger-job` validates the caller JWT with Supabase Auth and then requires either `app_metadata.roles` to contain `admin` or the caller to be allowlisted through `ADMIN_USER_IDS` / `ADMIN_USER_EMAILS`.
- The official `evaluate_release` CI job (`ml_pipeline.yml`) now requires `reference_set_key` and builds the manifest from the authoritative SnowSlide registry before dispatching the worker. For manual worker execution you can still pass a manifest file directly:
  ```bash
  python3 -m backend.sar_unet_worker --mode evaluate-release --manifest /path/to/eval_manifest.json
  ```
  To dispatch the official gate through GitHub Actions:
  ```bash
  gh workflow run ml_pipeline.yml \
    -f mode=evaluate_release \
    -f reference_set_key=snowslide-heldout-v1 \
    -f prediction_model_version=sar_unet_resnet34_shadow_v1
  ```
  Once `beats_baseline=true` is confirmed, promote recent SAR results with one of these paths:

  Preferred rerun path:
  ```bash
  python -m backend.sar_release_promote \
    --evaluation-report /path/to/sar_evaluation_report.json \
    --scenes-manifest /path/to/sar_segment_manifest.json \
    --model-path /path/to/sar_unet_weights.ckpt
  ```

  Recovery path for already-written shadow rows:
  ```bash
  python -m backend.sar_release_promote \
    --evaluation-report /path/to/sar_evaluation_report.json \
    --days-back 30
  ```

  After promotion, set `SAR_RELEASE_GATE_PASSED=true` as a GitHub secret and re-dispatch `train_mtslstm` with `sar_release_gate_passed=true` in the payload.

## Modal Deployment

The in-repo deployment surface lives at `backend/modal_worker_app.py`. The bootstrap CLI above is now the preferred path. If you need to run the deployment steps manually, the minimal flow is:

```bash
pip install modal
modal deploy backend/modal_worker_app.py
modal run backend/modal_worker_app.py --source-root backend/data/dem
```

Set `MODAL_WORKER_URL` to the single deployed ASGI base URL that Modal prints for the worker app and keep `MODAL_WORKER_TOKEN` aligned with the worker secret injected into Modal.
