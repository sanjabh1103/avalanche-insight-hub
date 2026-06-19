# MVP V2 W0-W13 Partner Workorder

Status: 2026-05-24

This workorder is intentionally explicit because the partner/scientist process is not fully UI-driven today. The current workflow is CSV/manifest/CLI-based, with partial UI support for existing scientist/demo review surfaces.

## Role Key

| Role | Meaning |
|---|---|
| PL | Product lead / Sanjay-side owner. |
| PR | Partner liaison. |
| SL | Scientist lead. |
| ML | ML/data engineer. |
| GS | Geospatial/SAR reviewer. |
| HA | Holdout auditor. |
| OP | Operator running triage and packaging commands. |

## Weekly Execution Table

| Week | Primary Goal | Sanjay / Team Action | Scientist / Partner Action | Files To Use Or Fill | UI Availability | Done Criteria |
|---|---|---|---|---|---|---|
| W0 | Prepare read-ahead packet | Send deck PDFs, one-pager, action list, pilot plan, and this workorder. Confirm `production_scoring_allowed=false` and `himalayan_accuracy_claim_allowed=false`. | Confirm attendees, decision authority, and data owners. | `01_deck_pack/*.pdf`, `02_scientist_operating_pack/Scientist_Handout_OnePager.md`, `MVP_V2_Action_List.md`, `MVP_V2_13_Week_Pilot_Plan.md` | Presentation only | Meeting booked; claim locks acknowledged. |
| W1 | Handoff session | Walk through README, field dictionary, checksum guide, source manifest, and CSV list. | Confirm the packet is understandable and nominate data contacts. | `partner_handoff_readme.md`, `partner_field_dictionary.md`, `partner_source_package_checksum_guide.md`, `partner_source_manifest_template.*` | No | Minutes filed; partner has blank templates. |
| W2 | Source governance | Explain SHA-256, `source_ref`, license scope, reviewed date, and source-owner requirements. | Fill at least one source manifest entry. | `partner_source_manifest_template.json`, `partner_source_manifest_template.md` | No | At least one source entry is ready for validation. |
| W3 | Station metadata and GPxyz readiness | Validate station coverage and coordinate sanity. | Fill station rows for priority regions. | `station_metadata.csv` | No | Station count, region count, coordinate coverage, and elevation span known. |
| W4 | D_tidy labels and snowpack profiles | Validate label provenance and weak-layer fields. | Fill reviewed labels and profile rows; define weak-layer slice target. | `danger_labels_and_bulletins.csv`, `snowpack_profile_features.csv` | No | Reviewed labels pass basic schema; weak-layer slice target recorded. |
| W5 | First real partner-package triage | Run intake preflight, source manifest validation, evidence validation, quality score, and leakage checks. | Respond to first blocker list and resubmit if needed. | Validation outputs generated from `03_partner_handoff_packet/` plus real partner package | No | First blocker and readiness score are known. |
| W6 | RF4 feasibility and SAR read-only review | Draft feasibility note if row counts permit; review SAR only as shadow evidence. | Confirm whether data volume supports a spike; review SAR concerns without promotion. | `Swiss_Reproduction_Lane.md`, `remote_sensing_validation_scenes.csv`, feasibility note | Partial review UI only | No SAR or Himalayan accuracy claim produced. |
| W7 | Aggregation and discretization audit | Check refined threshold leakage and warning-region requirements. | Confirm elevation-band policy and region aggregation choices. | `warning_region_polygons.csv`, holdout protocol drafts | No | Band policy and leakage stance recorded. |
| W8 | Weak-layer review round 1 | Compile cases and prepare scientist review rows. | Fill verdicts and label-quality decisions. | `scientist_reviews.csv`, `snowpack_profile_features.csv`, `historical_avalanche_events.csv` | Partial | At least first review round has verdicts and notes. |
| W9 | Independent holdout pre-registration | Draft local holdout protocol and leakage rules. | Co-sign holdout split rules and acceptance floors. | `independent_himalayan_holdout.csv`, `himalayan_local_holdout_protocol.md` | No | Holdout protocol signed before metrics. |
| W10 | Review round 2 and resubmission | Re-run triage if new rows arrive; update weak-layer evidence pack. | Add revised/new rows and case verdicts. | `scientist_reviews.csv`, `snowpack_profile_features.csv`, `partner_submission_manifest_diff.*` | Partial | Round-2 review pack and diff are ready. |
| W11 | Failure-mode review | Prepare failure-mode review and pre-decision memo. | Classify model-side, data-side, terrain-side, or label-side blockers. | `historical_avalanche_events.csv`, `remote_sensing_validation_scenes.csv`, `terrain_ates_runout_validation.csv`, failure memo | Partial | Signed failure-mode classification. |
| W12 | Attestation or explicit claim block | Fill release-gate attestation only if all gates pass; otherwise write `claim_review_blocked`. | Approve, block, or request additional evidence. | `release_gate_attestation_template_pack.*`, `himalayan_local_holdout_metric_report.*` | No | Claim status is explicit. |
| W13 | Decision session | Present handoff-only, 90-day pilot, deeper co-development, narrow pilot, or stop options. | Choose next path and sign minutes. | `MVP_V2_Action_List.md`, pre-decision memo, status dashboard | Presentation only | Decision minutes and next charter filed. |

## CSV Column Checklist

| CSV | Scientist / Partner Must Fill | Notes |
|---|---|---|
| `station_metadata.csv` | `station_id`, `region_key`, `latitude`, `longitude`, `elevation_m`, `active_date_range`, `source_ref`, `license_scope`, `review_status`, `reviewer_id`, `reviewed_at`, `reviewer_notes` | Required before GPxyz-style spatial readiness. |
| `weather_station_observations.csv` | `station_id`, `observed_at`, `air_temp_c`, `precipitation_mm`, `snowfall_cm`, `snow_depth_cm`, `wind_speed_ms`, `wind_dir_deg`, source/review fields | Required for local weather features. |
| `snowpack_profile_features.csv` | `station_id`, `observed_at`, `layer_index`, `layer_depth_cm`, `grain_type`, `hardness_index`, `stability_index`, `quality_flag`, source/review fields | Required for weak-layer and snowpack validation. |
| `danger_labels_and_bulletins.csv` | `region_id`, `valid_from`, `valid_to`, `danger_scale_standard`, `danger_level_1_to_5`, `danger_level_1_to_4`, `avalanche_problem`, `elevation_band_policy`, `forecaster_or_reviewer_id`, source/review fields | Raw public bulletins are not enough; rows need reviewed label provenance. |
| `warning_region_polygons.csv` | `region_id`, `polygon_geometry`, `crs`, `elevation_policy`, `valid_date_range`, source/review fields | Required before region aggregation claims. |
| `historical_avalanche_events.csv` | `event_id`, `observed_at`, `latitude`, `longitude`, `elevation_m`, `aspect`, `avalanche_problem`, `observed_outcome`, `confidence`, `source`, source/review fields | Required for event-outcome validation. |
| `remote_sensing_validation_scenes.csv` | `scene_id`, `sensor`, `acquired_at`, `preprocessing_level`, `truth_mask_or_event_ref`, `holdout_split`, source/review fields | Shadow-gated; not a production SAR path. |
| `terrain_ates_runout_validation.csv` | `region_id`, `dem_ref`, `slope`, `aspect`, `terrain_class`, `runout_validation_ref`, `quality_flag`, source/review fields | Required for terrain/runout context. |
| `scientist_reviews.csv` | `review_id`, `reviewer_id`, `reviewed_at`, `case_id`, `verdict`, `label_quality`, `model_error_type`, `confidence`, `source_ref`, `license_scope`, `review_status`, `reviewer_notes` | Current UI is partial; CSV remains authoritative for this handoff. |
| `independent_himalayan_holdout.csv` | `holdout_id`, `source_refs`, `region_ids`, `date_range`, `leakage_check`, `acceptance_floors`, source/review fields | Must be fresh and leakage-audited before local accuracy claims. |

## UI Status

| Workflow | UI Today? | Practical Instruction |
|---|---|---|
| Present MVP V2 story | Yes, via PDFs/HTML decks | Use `01_deck_pack/`. |
| Review scientist/demo cases | Partial | Existing scientist review surfaces can support discussion, but do not replace the CSV templates. |
| Partner source manifest entry | No | Use `partner_source_manifest_template.{json,md}`. |
| Partner evidence entry | No | Use ten blank CSV templates. |
| Holdout protocol and release attestation | No | Use generated Markdown/JSON templates. |
| Himalayan live region switch | Not yet | Requires evidence gates plus app region wiring. |

## Hard Stops

- Do not send synthetic fixture rows as partner evidence.
- Do not claim Himalayan accuracy from Colorado proof, Swiss reproduction, synthetic validation, or blank templates.
- Do not promote SAR or any model into production from this pack.
- Do not change public scoring, Supabase, Netlify, or model status as part of this handoff.
