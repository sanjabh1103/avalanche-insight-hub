# Modal Worker Runbook

This project uses Modal as the only GPU execution backend for the Wave 4 SAR and MTS-LSTM worker flows. GitHub Actions and `trigger-job` are dispatch layers only.

## Required Secrets and Runtime

- `MODAL_WORKER_URL`: base URL for the deployed worker
- `MODAL_WORKER_TOKEN`: bearer token for the worker. The ASGI worker validates `Authorization: Bearer <token>` on every request.
- `SAR_UNET_MODEL_FAMILY`: defaults to `resnet34_unet`; `swinunet_tiny_diff` is reserved for the paper-family bi-temporal Swin path
- `SAR_UNET_MODEL_PATH`: checkpoint path available to the worker runtime
- `SAR_UNET_DEVICE`: defaults to `cpu`; set `cuda` for GPU shadow validation
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SAR_MASK_BUCKET`: defaults to `sar-masks`
- `SAR_UNET_MODEL_VERSION`: defaults to `sar_unet_resnet34_shadow_v1`
- `SAR_UNET_PROMOTED`: keep unset or `false` in shadow mode

The target Supabase project must already contain the private `sar-masks` bucket created by migration `20260425170000_create_sar_masks_bucket.sql`.
The target Supabase project must also contain the held-out registry tables created by migration `20260425200000_sar_release_reference_registry.sql`.

## In-Repo Operator Entry Points

- `.github/workflows/bootstrap_pinned_gate.yml`
  Temporary manual GitHub Actions workflow for cloud-to-cloud SnowSlide seeding when the archive is too large for local hardware. It downloads a truth/vector archive plus a separate Sentinel-1 VV/VH raster archive into the runner’s ephemeral storage, or reuses one bundled AvalCD-style archive when both input URLs match, assembles a canonical held-out directory, runs a strict `--validate-only` preflight against that assembled directory, then either performs an authoritative activation with real SAR inputs or a non-authoritative canary run that leaves the set in `draft`.
- `python -m backend.scripts.assemble_seed_archive`
  Runner-side staging CLI. It unwraps the truth archive, extracts the SAR raster archive, pairs vector truth with year-matched VV/VH GeoTIFF rasters, and emits a canonical local held-out directory for seeding. In bundled AvalCD mode it detects `_GT/_preVV/_preVH/_postVV/_postVH` scene families and materializes 4-channel temporal `stack.npz` payloads ordered as `[pre_vv, pre_vh, post_vv, post_vh]`.
- `python -m backend.scripts.bootstrap_release_gate`
  Operator bootstrap CLI for the GitHub-first rollout path. It validates `.env`, syncs secrets into GitHub/Modal/Supabase, seeds the authoritative SnowSlide held-out registry from a local zip, deploys the Modal worker, seeds the DEM volume, and then stops at `refs_ready_only` until a real `SAR_UNET_MODEL_PATH` is configured.
- `python -m backend.scripts.seed_snowslide_truth`
  One-off bootstrapping CLI. Seeds SnowSlide truth masks and canonical scene stacks into `sar-masks`, then registers the held-out set in Supabase as `draft`. The default path is authoritative; `--non-authoritative` is reserved for plumbing-only canary seeds.
- `python -m backend.scripts.materialize_release_baseline_masks`
  Materializes `baseline_mask.tif` for a registered SnowSlide reference set and marks the set `active` when complete unless `--no-activate` is used for a canary run.
- `python -m backend.scripts.evaluate_canary_release`
  Draft-only operator harness. It seeds zero-valued synthetic prediction masks under the standard `predictions/<model_version>/prediction_mask.tif` path for a non-authoritative reference set, builds a manual `scenes[]` manifest, and posts that manifest to the worker’s `evaluate-release` endpoint without requiring `SAR_UNET_MODEL_PATH`.
- `python -m backend.scripts.fetch_sota_sar_weights`
  Operator ingestion helper. It downloads a signed checkpoint into `backend/data/models/`, rejects obvious HTML or empty payloads, and atomically updates local `.env` with `SAR_UNET_MODEL_PATH`. It only updates `SAR_UNET_MODEL_FAMILY` or `SAR_UNET_MODEL_VERSION` when the operator passes those flags explicitly.
- `python -m backend.scripts.adapt_coldstart_swin_checkpoint`
  Cold-start recovery helper. It adapts a pretrained `timm` Swin-V2 Tiny encoder into the repo's shadow-only `swinunet_tiny_diff` checkpoint layout, writes `backend/data/models/swin_transformer_v2_tiny_coldstart_v1.pt`, verifies the worker can load it in shadow mode, and updates local `.env` to point at `/artifacts/models/swin_transformer_v2_tiny_coldstart_v1.pt`.
- `python -m backend.sar_release_manifest`
  Builds a held-out `evaluate-release` manifest either from an ad hoc JSON/CSV registry or from an authoritative SnowSlide `reference_set_key`.
- `python -m backend.sar_release_promote`
  Promotes a successful SAR evaluation by rerunning segmentation in promoted mode or, as recovery, flipping existing shadow rows.
- `modal deploy backend/modal_worker_app.py`
  Deploys the in-repo Modal ASGI worker surface that exposes the worker endpoints below on one base URL.
- `modal run backend/modal_worker_app.py --source-root backend/data/dem`
  Seeds Git LFS-backed DEM assets into the persistent Modal volume at `/artifacts/dem`.
- `modal run backend/modal_worker_app.py --source-model-path backend/data/models/swin_transformer_v2_tiny.pt --remote-model-path /models/swin_transformer_v2_tiny.pt`
  Uploads a fetched checkpoint into the existing Modal volume so the worker can read it at `/artifacts/models/swin_transformer_v2_tiny.pt` at runtime.
- `modal volume put avalanche-artifacts backend/data/models/swin_transformer_v2_tiny_coldstart_v1.pt /models/swin_transformer_v2_tiny_coldstart_v1.pt --force`
  Direct volume upload path for the cold-start checkpoint when `modal run` is undesirable or blocked by app-creation constraints. The worker still needs a fresh deployment or container refresh before the updated path is visible at runtime.

## Cloud Bootstrap Workflow

When the SnowSlide archive is too large to stage on a local machine, use the temporary manual GitHub workflow instead of the local zip bootstrap.

Trigger:
- GitHub Actions UI only via `workflow_dispatch`
- protected by the `production` environment

Inputs:
- `DATASET_URL` required
- `SAR_RASTER_URL` required
  Set this equal to `DATASET_URL` only when the archive itself already bundles truth plus the required Sentinel-1 SAR rasters, such as AvalCD.
- `REFERENCE_SET_KEY` optional, defaults to `snowslide-heldout-v1`
- `SOURCE_VERSION` optional; if blank, the workflow uses the current UTC date
- `BOOTSTRAP_MODE` optional, defaults to `authoritative`; allowed values are `authoritative` and `canary`

Security and source restrictions:
- `DATASET_URL` must be a direct downloadable truth/vector archive URL, not a record landing page; it may point either to the original academic record or to a trusted cloud mirror of the same authoritative truth archive
- `SAR_RASTER_URL` must be a direct downloadable Sentinel-1 VV/VH GeoTIFF archive URL; signed GCS or S3 URLs are preferred over public-read objects when you control the mirror
  When `SAR_RASTER_URL == DATASET_URL`, the workflow enters bundled-archive mode and validates the shared URL against the truth-host allowlist instead of the stricter SAR-host allowlist.
- `BOOTSTRAP_MODE=authoritative` is for real SAR activation only and is the only mode allowed to target `snowslide-heldout-v1`
- `BOOTSTRAP_MODE=canary` is for synthetic or provisional SAR plumbing validation only; it must use a non-production `REFERENCE_SET_KEY` and leaves the seeded set in `draft`
- the workflow assembles both sources into one canonical local dataset before preflight
- acceptable truth inputs are either raster truth masks (`.tif/.tiff`) or vector avalanche outlines (`.shp/.geojson/.json`) that can be rasterized against a georeferenced Sentinel-1 GeoTIFF stack or paired VV/VH GeoTIFF rasters
- GeoPackage truth inputs such as `.gpkg` remain unsupported in this slice and must fail closed until a dedicated extension lands
- IAS/webcam/optical datasets are invalid for the pinned gate and are rejected in preflight before any storage or Supabase mutation
- the assembler requires one co-registered VV/VH GeoTIFF pair for every truth year it discovers; for the Davos validation set that currently means both 2018 and 2019, for example:
  - `S1_2018_vv.tif`
  - `S1_2018_vh.tif`
  - `S1_2019_vv.tif`
  - `S1_2019_vh.tif`
- allowed truth hosts are fixed to:
  - `envidat.ch`
  - `www.envidat.ch`
  - `zenodo.org`
  - `www.zenodo.org`
  - `slf.ch`
  - `www.slf.ch`
  - `storage.googleapis.com`
  - `s3.amazonaws.com`
  - `*.s3.amazonaws.com`
- allowed SAR raster hosts are fixed to:
  - `storage.googleapis.com`
  - `s3.amazonaws.com`
  - `*.s3.amazonaws.com`
  - `dataspace.copernicus.eu`
- the workflow rejects non-`https` URLs, custom ports, embedded credentials, and non-ZIP payloads for both sources

Execution sequence:
1. download `truth_archive.zip` and `sar_rasters.zip` into the runner workspace with quoted shell input; when both URLs match, download once and reuse the same ZIP for both inputs
2. verify both ZIP payloads and fail if the SAR raster archive lacks `.tif/.tiff` members
3. run `python -m backend.scripts.assemble_seed_archive --truth-zip truth_archive.zip --sar-zip sar_rasters.zip --output-dir assembled_seed_dir`
4. run `python -m backend.scripts.seed_snowslide_truth --source-dir assembled_seed_dir --validate-only ...`
5. only if preflight returns `status=ok`, run `python -m backend.scripts.seed_snowslide_truth --source-dir assembled_seed_dir ...`; add `--non-authoritative` when `BOOTSTRAP_MODE=canary`
6. run `python -m backend.scripts.materialize_release_baseline_masks --reference-set-key ...`; add `--no-activate` when `BOOTSTRAP_MODE=canary`
7. fail unless the assembler, preflight, and both mutation JSON payloads return `status=ok`; authoritative mode additionally requires `authoritative=true` and `reference_set_status=active`, while canary mode requires `authoritative=false` and `reference_set_status=draft`
8. clean up both downloaded archives, the assembled directory, and JSON result files in an `always()` step

This workflow does **not** support a later "silent swap" of mirror ZIP contents into an already seeded authoritative set. Once a run uploads assets into `sar-masks` and records them in Supabase, replacing the source ZIPs in cloud storage does nothing to the active registry; a fresh reseed is required.

Synthetic overlapping SAR harnesses are acceptable only for `BOOTSTRAP_MODE=canary`. Real authoritative activation remains blocked until the operator supplies a valid 2018/2019 Sentinel-1 VV/VH archive.

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
- `SAR_UNET_MODEL_FAMILY`
- `SAR_UNET_MODEL_PATH`

If `SAR_UNET_MODEL_PATH` is absent, the bootstrap completes in `refs_ready_only` state and intentionally does **not** attempt held-out `sar-segment`, the official authoritative `evaluate_release` gate, promoted reruns, or `train_mtslstm` with `sar_release_gate_passed=true`. Draft canary evaluation remains possible through `python -m backend.scripts.evaluate_canary_release` because `evaluate-release` itself does not read `SAR_UNET_MODEL_PATH`.

The bootstrap secret sync now propagates `SAR_UNET_MODEL_FAMILY`, `SAR_UNET_MODEL_VERSION`, `SAR_UNET_PROMOTED`, and `SAR_UNET_MODEL_PATH` into the live Modal runtime. Local `.env` values alone are not the deployment source of truth.

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

Blocked next step until a supervised SAR candidate exists:
- use `train-sar-unet` with a heldout-clean training manifest to produce a shadow checkpoint, then rerun held-out `sar-segment`, build the authoritative manifest, and dispatch `evaluate_release`

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
- `stack_ref`, `stack_path`, or `stack_url` pointing to either a two-channel VV/VH array or a four-channel temporal stack ordered as `[pre_vv, pre_vh, post_vv, post_vh]`

The default `resnet34_unet` path consumes the two-channel VV/VH contract above. The `swinunet_tiny_diff` family is bi-temporal and expects either explicit pre/post inputs (`pre_channels` + `post_channels`, `pre_vv`/`pre_vh` + `post_vv`/`post_vh`, `pre_stack_ref` + `post_stack_ref`) or a 4-channel temporal stack ordered as `[pre_vv, pre_vh, post_vv, post_vh]`. Legacy held-out `stack.npz` assets remain 2-channel VV/VH, while bundled AvalCD seeds materialize 4-channel temporal stacks directly for the Swin path.

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

### `POST /train-sar-unet`

GPU-side supervised SAR fine-tuning entrypoint for the repo-native `swinunet_tiny_diff` family. This path consumes a dedicated SAR training manifest, excludes `snowslide-heldout-v1` from train/val, materializes `pre.tif` / `post.tif` / `mask.tif` patches, trains a shadow checkpoint, and writes validation metrics plus threshold-selection artifacts.

Recommended request body:

```json
{
  "hazard_type": "avalanche",
  "training_manifest_path": "sar-training/manifests/avalcd_shadow_v1.json",
  "model_family": "swinunet_tiny_diff",
  "patch_size": 128,
  "stride": 64,
  "epochs": 8,
  "batch_size": 8,
  "learning_rate": 0.0001,
  "loss": "focal_tversky",
  "candidate_model_version": "swinunet_tiny_diff_shadow_candidate_v1"
}
```

Required response fields:
- `status`
- `candidate_model_version`
- `model_family`
- `model_checkpoint_path`
- `best_threshold`
- `validation_auprc`
- `validation_metrics`
- `quality_gate_passed`
- `blocked_gate`
- `scene_gate_failures`
- `dataset_version`
- `train_events`
- `val_events`

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

`evaluate-release` does **not** read `SAR_UNET_MODEL_PATH`. That checkpoint gate only applies to `/sar-segment`. The key-only manifest resolver shown above is authoritative-only; it expects an `authoritative=true`, `status=active` reference set.

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

For a draft canary set, do not rely on `reference_set_key` alone. Seed synthetic prediction masks in the draft namespace and dispatch a manual `scenes[]` payload instead:

```bash
python3 -m backend.scripts.evaluate_canary_release \
  --env-file .env \
  --reference-set-key canary-test-v1 \
  --prediction-model-version sar_unet_resnet34_shadow_v1
```

That harness:
- requires `authoritative=false` and `status!=active`
- uploads zero-valued prediction masks under `predictions/<model_version>/prediction_mask.tif`
- posts a manual `scenes[]` manifest to `POST /evaluate-release`
- leaves the canary set in `draft` and does not mutate the authoritative registry

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

For the full operator-side sequence after the pinned bootstrap rerun completes,
including dry-run gate, execute-promotion, dynamic-model activation, and
Whitebox smoke proof, follow the `Post-Bootstrap Promotion And Activation
Sequence` section in [docs/OPERATOR_ROLLOUT_QA.md](docs/OPERATOR_ROLLOUT_QA.md).

## Modal Deployment

The in-repo deployment surface lives at `backend/modal_worker_app.py`. The bootstrap CLI above is now the preferred path. If you need to run the deployment steps manually, the minimal flow is:

```bash
pip install modal
modal deploy backend/modal_worker_app.py
modal run backend/modal_worker_app.py --source-root backend/data/dem
```

Set `MODAL_WORKER_URL` to the single deployed ASGI base URL that Modal prints for the worker app and keep `MODAL_WORKER_TOKEN` aligned with the worker secret injected into Modal.
