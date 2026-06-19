# Himalayan Partner Evidence Field Dictionary

Decision: `partner_field_dictionary_written_pending_partner_submission`

This dictionary defines field semantics for partner evidence CSVs. It is a submission guide, not evidence, and it does not authorize production scoring.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Field definitions | 64 |

## Standards Anchors

| Source | Use | URL |
|---|---|---|
| EAWS avalanche danger scale and avalanche problems | Preserve canonical danger and problem semantics before model-specific class mapping. | https://www.avalanches.org/standards/ |
| CAAML-style avalanche data interchange | Keep evidence fields explicit enough for later structured data exchange and archival mapping. | https://caaml.org/ |

## Danger Scale Notes

- danger_level_1_to_5 preserves the partner or operational five-level scale when available.
- danger_level_1_to_4 is the current RF4-compatible research label and must not be treated as canonical truth.
- If a reviewed level 5 occurs, keep danger_level_1_to_5=5 and document the four-class mapping in reviewer_notes before RF4 evaluation.

## Field Definitions

| Column | Description | Format | Unit | Controlled values | Used by |
|---|---|---|---|---|---|
| `acceptance_floors` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `independent_himalayan_holdout` |
| `acquired_at` | Remote-sensing acquisition timestamp. | ISO-8601 timestamp | timestamp | None | `remote_sensing_validation_scenes` |
| `active_date_range` | Date interval when a station, region, or source was active and valid for analysis. | YYYY-MM-DD/YYYY-MM-DD | date range | None | `station_metadata` |
| `air_temp_c` | Near-surface air temperature used for weather features. | number | deg C | None | `weather_station_observations` |
| `aspect` | Slope aspect as degrees clockwise from north or a compass sector. | number in [0, 360] or compass sector | degrees | None | `historical_avalanche_events`, `terrain_ates_runout_validation` |
| `avalanche_problem` | Reviewed avalanche problem type associated with a label, event, or terrain context. | controlled value | none | `cornice_fall`, `deep_persistent_weak_layer`, `gliding_snow`, `loose_dry`, `loose_wet`, `multiple`, `new_snow`, `no_distinct_problem`, `other_reviewed`, `persistent_weak_layer`, `persistent_weak_layers`, `unknown`, `wet_snow`, `wind_slab` | `danger_labels_and_bulletins`, `historical_avalanche_events` |
| `case_id` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `scientist_reviews` |
| `confidence` | Reviewer confidence in an event, label, or case decision. | number in [0, 1] | ratio | None | `historical_avalanche_events`, `scientist_reviews` |
| `crs` | Coordinate reference system for a geometry or gridded source. | EPSG code or CRS identifier | none | None | `warning_region_polygons` |
| `danger_level_1_to_4` | Current research model-compatible four-class label; must not replace the canonical partner danger level. | integer from 1 to 4 | model class | None | `danger_labels_and_bulletins` |
| `danger_level_1_to_5` | Canonical reviewed avalanche danger level, preserving five-level operational standards where available. | integer from 1 to 5 | danger level | None | `danger_labels_and_bulletins` |
| `danger_scale_standard` | Danger-scale standard used by the partner before any model-compatible mapping. | controlled value | none | `eaws_5_level`, `local_4_level`, `partner_custom_reviewed`, `unknown` | `danger_labels_and_bulletins` |
| `date_range` | Date interval covered by a holdout or reviewed source group. | YYYY-MM-DD/YYYY-MM-DD | date range | None | `independent_himalayan_holdout` |
| `dem_ref` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `terrain_ates_runout_validation` |
| `elevation_band_policy` | Partner rule for applying danger labels by elevation band. | string | policy text | None | `danger_labels_and_bulletins` |
| `elevation_m` | Elevation above mean sea level. | number in [0, 9000] | m | None | `historical_avalanche_events`, `station_metadata` |
| `elevation_policy` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `warning_region_polygons` |
| `event_id` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `historical_avalanche_events` |
| `forecaster_or_reviewer_id` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `danger_labels_and_bulletins` |
| `grain_type` | Reviewed snow grain or weak-layer classification supplied by the partner. | string | none | None | `snowpack_profile_features` |
| `hardness_index` | Partner-reviewed snow hardness index or encoded hardness class. | number or reviewed class code | partner scale | None | `snowpack_profile_features` |
| `holdout_id` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `independent_himalayan_holdout` |
| `holdout_split` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `remote_sensing_validation_scenes` |
| `label_quality` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `incomplete`, `invalid`, `needs_terrain_context`, `suspect`, `unknown`, `valid` | `scientist_reviews` |
| `latitude` | WGS84 latitude for station, event, or validation point. | decimal degrees in [-90, 90] | degrees | None | `historical_avalanche_events`, `station_metadata` |
| `layer_depth_cm` | Depth of a snowpack layer or weak-layer marker. | nonnegative number | cm | None | `snowpack_profile_features` |
| `layer_index` | Ordered snowpack layer index within a station/time profile. | integer | none | None | `snowpack_profile_features` |
| `leakage_check` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `independent_himalayan_holdout` |
| `license_scope` | Reviewed usage scope for the source row or package. | controlled value | none | `blocked_license_scope`, `cc_by_nc_research_only`, `commercial_deployment_approved`, `external_imagery_share_approved`, `internal_research_validation`, `internal_shadow_presentation`, `partner_restricted_research`, `pending_license_review`, `public_presentation_with_attribution`, `research_validation_only`, `unknown` | `danger_labels_and_bulletins`, `historical_avalanche_events`, `independent_himalayan_holdout`, `remote_sensing_validation_scenes`, `scientist_reviews`, `snowpack_profile_features`, `station_metadata`, `terrain_ates_runout_validation`, `warning_region_polygons`, `weather_station_observations` |
| `longitude` | WGS84 longitude for station, event, or validation point. | decimal degrees in [-180, 180] | degrees | None | `historical_avalanche_events`, `station_metadata` |
| `model_error_type` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `calibration_error`, `domain_shift`, `false_negative`, `false_positive`, `localization_error`, `not_applicable`, `true_negative`, `true_positive`, `unknown` | `scientist_reviews` |
| `observed_at` | Timestamp for an observation, event, or reviewed snowpack profile. | ISO-8601 timestamp | timestamp | None | `historical_avalanche_events`, `snowpack_profile_features`, `weather_station_observations` |
| `observed_outcome` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `avalanche_observed`, `incident`, `near_miss`, `no_avalanche_observed`, `partial_evidence`, `unknown` | `historical_avalanche_events` |
| `polygon_geometry` | Warning-region geometry in a reviewed geospatial encoding. | WKT, GeoJSON, or partner-reviewed geometry reference | geometry | None | `warning_region_polygons` |
| `precipitation_mm` | Liquid-equivalent precipitation over the reported observation window. | nonnegative number | mm | None | `weather_station_observations` |
| `preprocessing_level` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `analysis_ready`, `co_registered`, `orthorectified`, `radiometrically_calibrated`, `raw`, `reviewed_analysis_ready`, `terrain_corrected`, `unknown` | `remote_sensing_validation_scenes` |
| `quality_flag` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `corrected`, `estimated`, `measured`, `modeled`, `provisional`, `reviewed_suspect`, `reviewed_valid`, `unknown` | `snowpack_profile_features`, `terrain_ates_runout_validation` |
| `region_id` | Stable warning-region identifier used to join labels, polygons, terrain, and holdout evidence. | string | none | None | `danger_labels_and_bulletins`, `terrain_ates_runout_validation`, `warning_region_polygons` |
| `region_ids` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `independent_himalayan_holdout` |
| `region_key` | Partner warning region, forecast zone, or pilot-area key for station grouping. | string | none | None | `station_metadata` |
| `review_id` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `scientist_reviews` |
| `review_status` | Partner review state; evidence rows must be reviewed before they can support readiness. | reviewed | none | None | `danger_labels_and_bulletins`, `historical_avalanche_events`, `independent_himalayan_holdout`, `remote_sensing_validation_scenes`, `scientist_reviews`, `snowpack_profile_features`, `station_metadata`, `terrain_ates_runout_validation`, `warning_region_polygons`, `weather_station_observations` |
| `reviewed_at` | Timestamp when the evidence row or source package was reviewed. | ISO-8601 timestamp | timestamp | None | `danger_labels_and_bulletins`, `historical_avalanche_events`, `independent_himalayan_holdout`, `remote_sensing_validation_scenes`, `scientist_reviews`, `snowpack_profile_features`, `station_metadata`, `terrain_ates_runout_validation`, `warning_region_polygons`, `weather_station_observations` |
| `reviewer_id` | Named reviewer, review board, or partner review identifier. | string | none | None | `danger_labels_and_bulletins`, `historical_avalanche_events`, `independent_himalayan_holdout`, `remote_sensing_validation_scenes`, `scientist_reviews`, `snowpack_profile_features`, `station_metadata`, `terrain_ates_runout_validation`, `warning_region_polygons`, `weather_station_observations` |
| `reviewer_notes` | Short notes explaining assumptions, caveats, or local mapping decisions. | string | none | None | `danger_labels_and_bulletins`, `historical_avalanche_events`, `independent_himalayan_holdout`, `remote_sensing_validation_scenes`, `scientist_reviews`, `snowpack_profile_features`, `station_metadata`, `terrain_ates_runout_validation`, `warning_region_polygons`, `weather_station_observations` |
| `runout_validation_ref` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `terrain_ates_runout_validation` |
| `scene_id` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `remote_sensing_validation_scenes` |
| `sensor` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `remote_sensing_validation_scenes` |
| `slope` | Slope angle for terrain or runout evidence. | number in [0, 90] | degrees | None | `terrain_ates_runout_validation` |
| `snow_depth_cm` | Total snow depth at the observation point. | nonnegative number | cm | None | `weather_station_observations` |
| `snowfall_cm` | New snowfall over the reported observation window. | nonnegative number | cm | None | `weather_station_observations` |
| `source` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `historical_avalanche_events` |
| `source_ref` | SHA-256 qualified reference to a reviewed source package. | sha256:<64-hex> or file:<path>#sha256=<64-hex> | reference | None | `danger_labels_and_bulletins`, `historical_avalanche_events`, `independent_himalayan_holdout`, `remote_sensing_validation_scenes`, `scientist_reviews`, `snowpack_profile_features`, `station_metadata`, `terrain_ates_runout_validation`, `warning_region_polygons`, `weather_station_observations` |
| `source_refs` | One or more SHA-256 qualified source references used by a holdout definition. | semicolon, comma, or pipe separated source_ref values | reference list | None | `independent_himalayan_holdout` |
| `stability_index` | Normalized snowpack stability indicator. | number in [0, 1] | ratio | None | `snowpack_profile_features` |
| `station_id` | Stable partner-local station identifier used to join metadata, weather, and snowpack rows. | string | none | None | `snowpack_profile_features`, `station_metadata`, `weather_station_observations` |
| `terrain_class` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `challenging`, `complex`, `extreme`, `non_avalanche`, `simple`, `unknown` | `terrain_ates_runout_validation` |
| `truth_mask_or_event_ref` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | None | `remote_sensing_validation_scenes` |
| `valid_date_range` | Date interval when a geometry or regional policy is valid. | YYYY-MM-DD/YYYY-MM-DD | date range | None | `warning_region_polygons` |
| `valid_from` | Forecast, bulletin, or label validity start. | ISO-8601 timestamp | timestamp | None | `danger_labels_and_bulletins` |
| `valid_to` | Forecast, bulletin, or label validity end. | ISO-8601 timestamp | timestamp | None | `danger_labels_and_bulletins` |
| `verdict` | Partner-reviewed field required by one or more Himalayan evidence templates. | string or reviewed partner value | none | `label_remediation_required`, `label_valid`, `model_error`, `review_incomplete`, `terrain_context_required`, `uncertain` | `scientist_reviews` |
| `wind_dir_deg` | Wind direction clockwise from north. | number in [0, 360] | degrees | None | `weather_station_observations` |
| `wind_speed_ms` | Wind speed aligned to the weather feature window. | nonnegative number | m/s | None | `weather_station_observations` |

## Template Guides

| Template | Category | Minimum rows | Controlled fields | World-class reason |
|---|---|---:|---|---|
| `station_metadata.csv` | himalayan_station_network | 10 | `license_scope` | Reviewed Himalayan station coordinates and elevations for GPxyz and local validation. |
| `weather_station_observations.csv` | weather_features | 30 | `license_scope` | Partner-observed weather station series aligned to local danger labels. |
| `snowpack_profile_features.csv` | snowpack_weak_layer | 20 | `quality_flag`, `license_scope` | HIM-STRAT/SNOWPACK-like local profile features and weak-layer validation. |
| `danger_labels_and_bulletins.csv` | danger_ground_truth | 10 | `danger_scale_standard`, `avalanche_problem`, `license_scope` | Reviewed Himalayan danger labels and bulletin archive by region/elevation band. |
| `warning_region_polygons.csv` | spatial_forecast_units | 1 | `license_scope` | Official or partner-reviewed Himalayan warning-region geometries. |
| `historical_avalanche_events.csv` | event_outcomes | 10 | `avalanche_problem`, `observed_outcome`, `license_scope` | Partner-confirmed Himalayan events for false-positive/false-negative assessment. |
| `remote_sensing_validation_scenes.csv` | remote_sensing | 5 | `preprocessing_level`, `license_scope` | Himalayan SAR/optical/InSAR validation scenes with independent holdouts. |
| `terrain_ates_runout_validation.csv` | terrain_exposure | 3 | `terrain_class`, `quality_flag`, `license_scope` | Reviewed terrain classes and runout validation for pilot regions. |
| `scientist_reviews.csv` | human_validation | 20 | `verdict`, `label_quality`, `model_error_type`, `license_scope` | Enough completed scientist reviews to support model-vs-human and label-quality analysis. |
| `independent_himalayan_holdout.csv` | release_gate | 1 | `license_scope` | Independent Himalayan final holdout not used in model or threshold selection. |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The field dictionary defines data semantics only. It is not partner evidence and does not validate any prediction claim.
