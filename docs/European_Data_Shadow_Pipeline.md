# European Data Shadow Pipeline

This implementation adds a shadow-only European avalanche data layer. It is intentionally not wired into public production scoring. The current public scorer remains the existing RF baseline until European shadow metrics beat that baseline and promotion gates pass.

## What Is Implemented

| Layer | File | Purpose |
|---|---|---|
| Source registry | `backend/common/european_shadow_sources.py` | Catalogues Swiss SPOT6, French EPA/CLPA, Norwegian SAR, AvalCD, SLF, and EAWS sources with region, data lane, record-count, license, attribution, and risk metadata. |
| License gates | `backend/common/european_shadow_sources.py` | Blocks benchmark/shadow-training use until a `license_review_id` is attached for sources requiring review. |
| Production guard | `backend/common/european_shadow_sources.py` | Blocks `production_scoring` for every European source, even after license review. |
| Staged records | `normalize_staged_european_record` | Normalizes downloaded or externally staged records into a manifest-safe internal shape without database writes. |
| SAR reuse | `build_sar_training_manifest_from_staged_records` | Converts reviewed AvalCD/Norway SAR staged records into the existing `sar_training_manifest_v1` contract. |
| Updated recommendation ratings | `dataset_family_assessments` | Stores the 1-5 enhancement values, best-use guidance, cautions, implementation status, and remaining work for the seven European dataset families. |
| Manifest CLI | `backend/scripts/build_european_shadow_manifest.py` | Emits a reviewable JSON manifest and usage-gate report for all or selected European sources. |

## Updated Recommendation Status

| Dataset family | Enhancement value /5 | Current implementation status | Still pending |
|---|---:|---|---|
| Norway 472k SAR detections | 5.0 | Registered as `norway_sar_activity_monitoring` with benchmark-only gates and production block. | Verify source package/license, stage detections with false-positive and temporal-uncertainty fields, build activity-rate benchmark. |
| Swiss SPOT6 24,778 outlines | 4.5 | Registered as 2018 and 2019 SPOT6 sources with shadow occurrence staging and license gates. | Download/checksum EnviDat exports after review, normalize polygons, keep extreme-event split separate from normal-season validation. |
| French EPA/CLPA | 4.5 | Registered as EPA event history and CLPA path-prior sources with benchmark/path-prior gates. | Verify avalanches.fr export terms, separate dated EPA labels from undated CLPA priors, add observability-bias audit slices. |
| Swiss weather/snowpack/danger ratings | 4.0 | Registered as SLF weather/snowpack feature join and CAAML danger-rating benchmark source. | Build API connector, join covariates without relabeling forecasts as observations, add calibration slices. |
| AvalCD | 4.0 | Registered as SAR benchmark source and convertible into existing `sar_training_manifest_v1`. | Verify Zenodo license, retrieve assets, stage scenes, run SAR detector benchmark in shadow mode. |
| SLF accident datasets | 3.0 | Registered as `slf_accident_datasets` with benchmark-only gates. | Download all-accident and fatal-only exports after terms review, normalize location uncertainty and casualty fields, avoid using accidents as occurrence-frequency truth. |
| EAWS/SLF bulletins | 2.5 | Registered as bulletin context and danger-rating benchmark sources. | Build context ingestion and semantic mapping while keeping bulletins out of observed-event labels. |

Overall enhancement average across the seven families is `3.93 / 5`, with five families at `4.0 / 5` or higher. The strongest value is validation and shadow-model qualification, not immediate public production scoring.

## Usage

Generate a full registry manifest:

```bash
python3 -m backend.scripts.build_european_shadow_manifest
```

Generate a reviewed subset manifest:

```bash
python3 -m backend.scripts.build_european_shadow_manifest \
  --source swiss_spot6_2018 \
  --source avalcd_zenodo_v1 \
  --license-review swiss_spot6_2018=license-review-spot6-2026-05-16 \
  --license-review avalcd_zenodo_v1=license-review-avalcd-2026-05-16 \
  --snapshot-id european-shadow-reviewed-v1 \
  --output backend/artifacts/european-shadow-reviewed-v1.json
```

## Promotion Rule

European data can support shadow validation, benchmark reconstruction, SAR candidate training, and calibration diagnostics. It must not change public production scoring until all of these are true:

| Gate | Required Evidence |
|---|---|
| License and attribution | Every included source has a recorded license review and required attribution. |
| RF comparator | Any recalibrated RF model has strictly better time-split Peirce Skill Score and no worse Brier score than the current RF baseline. |
| Local non-regression | Non-European/local validation slices do not materially degrade. |
| SAR qualification | SAR candidates pass held-out SAR gates and current release-gate policies. |
| Product truth | Public UI and artifacts continue to show candidate/fallback state until promotion is explicit. |
