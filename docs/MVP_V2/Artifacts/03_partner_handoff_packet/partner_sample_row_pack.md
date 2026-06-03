# Himalayan Partner Evidence Sample Row Pack

Decision: `partner_sample_row_pack_written_example_only`

These rows are examples only. They are intentionally not submit-ready and must not be copied as evidence without replacing placeholders, source hashes, reviewer notes, and review status.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Sample rows are evidence | `false` |
| Example rows | 10 |

## Sample Row Policy

- Write CSV files: `false`
- Reason: Examples are JSON/Markdown guidance only so they cannot be accidentally validated as partner evidence.
- Must replace before submission:
  - all EXAMPLE_* identifiers
  - placeholder SHA-256 references
  - review_status=EXAMPLE_ONLY_REPLACE_WITH_REVIEWED
  - reviewer notes

## Examples

### `station_metadata.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `station_id` | `EXAMPLE_STATION_001` |
| `region_key` | `EXAMPLE_HIMALAYAN_REGION_A` |
| `latitude` | `31.2500` |
| `longitude` | `78.1200` |
| `elevation_m` | `3200` |
| `active_date_range` | `2026-01-01/2026-04-30` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-01T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `weather_station_observations.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `station_id` | `EXAMPLE_STATION_001` |
| `observed_at` | `2026-01-02T06:00:00+00:00` |
| `air_temp_c` | `-6.5` |
| `precipitation_mm` | `8.2` |
| `snowfall_cm` | `18.0` |
| `snow_depth_cm` | `142.0` |
| `wind_speed_ms` | `9.5` |
| `wind_dir_deg` | `270` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-02T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `snowpack_profile_features.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `station_id` | `EXAMPLE_STATION_001` |
| `observed_at` | `2026-01-03T06:00:00+00:00` |
| `layer_index` | `1` |
| `layer_depth_cm` | `42` |
| `grain_type` | `faceted_crystals` |
| `hardness_index` | `0.40` |
| `stability_index` | `0.62` |
| `quality_flag` | `reviewed_valid` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-03T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `danger_labels_and_bulletins.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `region_id` | `EXAMPLE_REGION_A` |
| `valid_from` | `2026-01-04T00:00:00+00:00` |
| `valid_to` | `2026-01-05T00:00:00+00:00` |
| `danger_scale_standard` | `eaws_5_level` |
| `danger_level_1_to_5` | `4` |
| `danger_level_1_to_4` | `4` |
| `avalanche_problem` | `wind_slab` |
| `elevation_band_policy` | `above_3000m` |
| `forecaster_or_reviewer_id` | `EXAMPLE_REVIEWER` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-04T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `warning_region_polygons.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `region_id` | `EXAMPLE_REGION_A` |
| `polygon_geometry` | `POLYGON((78.0 31.1,78.3 31.1,78.3 31.4,78.0 31.4,78.0 31.1))` |
| `crs` | `EPSG:4326` |
| `elevation_policy` | `bands_2500_3000_3500m` |
| `valid_date_range` | `2026-01-01/2026-04-30` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-05T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `historical_avalanche_events.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `event_id` | `EXAMPLE_EVENT_001` |
| `observed_at` | `2026-01-06T06:00:00+00:00` |
| `latitude` | `31.2500` |
| `longitude` | `78.1200` |
| `elevation_m` | `3200` |
| `aspect` | `N` |
| `avalanche_problem` | `wind_slab` |
| `observed_outcome` | `avalanche_observed` |
| `confidence` | `0.82` |
| `source` | `partner_field_report` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-06T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `remote_sensing_validation_scenes.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `scene_id` | `EXAMPLE_SCENE_001` |
| `sensor` | `Sentinel-1` |
| `acquired_at` | `2026-01-07T10:00:00+00:00` |
| `preprocessing_level` | `reviewed_analysis_ready` |
| `truth_mask_or_event_ref` | `EXAMPLE_EVENT_001` |
| `holdout_split` | `independent_holdout` |
| `license_scope` | `internal_research_validation` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-07T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `terrain_ates_runout_validation.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `region_id` | `EXAMPLE_REGION_A` |
| `dem_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `slope` | `36` |
| `aspect` | `N` |
| `terrain_class` | `challenging` |
| `runout_validation_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `quality_flag` | `reviewed_valid` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-08T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `scientist_reviews.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `review_id` | `EXAMPLE_REVIEW_001` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-09T12:00:00+00:00` |
| `case_id` | `EXAMPLE_CASE_001` |
| `verdict` | `label_valid` |
| `label_quality` | `valid` |
| `model_error_type` | `false_positive` |
| `confidence` | `0.82` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

### `independent_himalayan_holdout.csv`

- Sample only: `true`
- Not submit-ready: `true`
- Reason: Contains EXAMPLE values and placeholder SHA-256 references. Partners must replace every EXAMPLE value, set review_status=reviewed, and validate source_ref values through partner_source_manifest.json.

| Column | Example value |
|---|---|
| `holdout_id` | `EXAMPLE_HOLDOUT_001` |
| `source_refs` | `sha256:<64-hex-sha256-from-partner-source-manifest>;sha256:<second-64-hex-source-digest>` |
| `region_ids` | `EXAMPLE_REGION_A;EXAMPLE_REGION_B` |
| `date_range` | `2026-01-01/2026-02-20` |
| `leakage_check` | `independent_from_training_and_threshold_selection` |
| `acceptance_floors` | `macro_f1_min=0.70;high_danger_recall_min=0.80;ece_max=0.08` |
| `source_ref` | `sha256:<64-hex-sha256-from-partner-source-manifest>` |
| `license_scope` | `internal_research_validation` |
| `review_status` | `EXAMPLE_ONLY_REPLACE_WITH_REVIEWED` |
| `reviewer_id` | `EXAMPLE_REVIEWER_REPLACE_BEFORE_SUBMISSION` |
| `reviewed_at` | `2026-01-10T12:00:00+00:00` |
| `reviewer_notes` | `EXAMPLE ONLY - replace with real reviewer notes before submission.` |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: Sample rows are instructional examples only and are never accepted as reviewed Himalayan evidence.
