# MVP V2 Artifacts - Artifact Workorder Index

Status: 2026-05-24

This is the single table for team and scientist orientation. It says what each artifact group does, who acts, what the scientist/partner must provide, whether the current UI can handle it, and what claim boundary applies.

## Critical Review Links

| Review Need | Open This File |
|---|---|
| Start here | [00_READ_ME_FIRST.md](00_read_me_first/00_READ_ME_FIRST.md) |
| First 5-minute FAQ | [SCIENTIST_TEAM_QUICK_START_FAQ.md](00_read_me_first/SCIENTIST_TEAM_QUICK_START_FAQ.md) |
| Colorado live proof vs Himalayan readiness | [COLORADO_TO_HIMALAYA_READINESS.md](00_read_me_first/COLORADO_TO_HIMALAYA_READINESS.md) |
| Scientist one-pager | [Scientist_Handout_OnePager.md](02_scientist_operating_pack/Scientist_Handout_OnePager.md) |
| Week-by-week workorder | [MVP_V2_W0_W13_PARTNER_WORKORDER.md](04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md) |
| Deck QA summary | [QA_SUMMARY.md](01_deck_pack/QA_SUMMARY.md) |
| Partner field dictionary | [partner_field_dictionary.md](03_partner_handoff_packet/partner_field_dictionary.md) |
| Blank evidence templates | [03_partner_handoff_packet/](03_partner_handoff_packet/) |

## One-Table Source Of Truth

| Artifact / File Group | What It Does | Sanjay / Team Action | Scientist / Partner Action | Week | UI Available Today? | Key Input Columns / Fields | Claim Boundary |
|---|---|---|---|---|---|---|---|
| `00_read_me_first/00_READ_ME_FIRST.md` | Gives the shortest route through the pack. | Send this first with the deck PDF set. | Read before the first call. | W0 | No | None | Orientation only. |
| `00_read_me_first/COLORADO_TO_HIMALAYA_READINESS.md` | Explains why Colorado is live first and what Himalayas require. | Use this whenever asked why the live app is not Himalayan yet. | Confirm whether Himalayan evidence can satisfy the checklist. | W0-W3 | No | See checklist rows below. | Colorado is technical proof, not Himalayan accuracy. |
| Five deck PDFs in `01_deck_pack/` | Customer/scientist presentation set. | Present or send as read-ahead. | Review claim boundaries and decision asks. | W0-W1 | Presentation only | None | No Himalayan accuracy claim. |
| Five HTML decks in `01_deck_pack/` | Browser-readable deck copies. | Use for local presentation if PDFs are not convenient. | Review same content as PDFs. | W0-W1 | Presentation only | None | Same as PDFs. |
| Seven transcript Markdown files in `01_deck_pack/` | Text version of all deck content, including two legacy aliases. | Use for search, notes, and audit. | Use for quick text review. | W0-W1 | No | None | Text proof only. |
| `01_deck_pack/QA_SUMMARY.md` | Records slide/page counts and viewport QA. | Reference as deck QA proof. | No action. | W0 | No | None | Deck rendering proof only. |
| `02_scientist_operating_pack/Scientist_Handout_OnePager.md` | Print-ready summary of live, research-only, and blocked claims. | Send before the deck. | Read and confirm meeting decision options. | W0 | No | None | Handoff orientation only. |
| `02_scientist_operating_pack/MVP_V2_13_Week_Pilot_Plan.md` | Week-by-week pilot plan. | Track owners and acceptance gates. | Confirm cadence and scientist authority. | W0-W13 | No | Week, owner, gate, risk trigger. | Pilot plan only. |
| `02_scientist_operating_pack/MVP_V2_Action_List.md` | Flat action list. | Assign PL/PR/ML/GS/HA/OP owners and update status. | Confirm SL-owned actions. | W0-W13 | Partial | Action ID, owner, dependency, acceptance, status. | No production mutation. |
| `02_scientist_operating_pack/MVP_V2_Weekly_Progress_Template.md` | Friday status note template. | Fill weekly and hash final note. | Confirm scientist decisions/blockers. | W1-W13 | No | Gate status, evidence pointer, owner, decisions, risks. | Status only. |
| `02_scientist_operating_pack/Himalayan_PrePartner_Evidence_Finite_Checkpoint.md` | Pre-partner evidence and command checkpoint. | Use to explain what is ready before real data. | Confirm missing real-data pieces. | W0-W2 | No | Evidence status, blocker, done criteria. | No accuracy claim. |
| `02_scientist_operating_pack/Avalanche_Prediction_Accuracy_Top10_Gap_Plan.md` | Top-10 prediction accuracy roadmap. | Use to align technical priorities. | Confirm scientific priority ranking. | W0-W13 | No | Feature gaps, evidence status, next target. | Roadmap only. |
| `02_scientist_operating_pack/Swiss_Reproduction_Lane.md` | Swiss RAvaFcast research lane status. | Explain Swiss results as method research. | Confirm it is not Himalayan proof. | W0-W7 | No | Swiss reproduction metrics and blockers. | Research-only. |
| `02_scientist_operating_pack/Remote_Sensing_Operational_Wishlist_Delta.md` | Customer wishlist delta. | Keep SAR/remote sensing gated. | Confirm wishlist priority and validation needs. | W0-W11 | Partial | Remote-sensing validation scene fields. | Shadow-gated. |
| `03_partner_handoff_packet/partner_handoff_readme.md` | Partner first-read guide. | Walk through in W1 session. | Follow resubmission sequence. | W1 | No | None | Navigation only. |
| `03_partner_handoff_packet/partner_field_dictionary.md` | Defines field meanings, units, controlled values. | Use as the schema explainer. | Use while filling CSV rows. | W1-W5 | No | All CSV columns. | Semantics only. |
| `03_partner_handoff_packet/partner_source_package_checksum_guide.md` | SHA-256 and `source_ref` workflow. | Train partner on hashing workflow. | Hash raw source packages and fill refs. | W1-W2 | No | `source_ref`, SHA-256, file path refs. | Provenance only. |
| `03_partner_handoff_packet/partner_source_manifest_template.{json,md}` | Source governance declaration. | Validate owner/license/review metadata. | Fill owner, dataset, license, date range, reviewer, SHA-256 refs. | W1-W2 | No | owner, dataset, license_scope, reviewed_at, sha256. | Required before evidence use. |
| `03_partner_handoff_packet/station_metadata.csv` | Station X/Y/Z for GPxyz readiness. | Validate station coverage. | Fill station ID, region, latitude, longitude, elevation, active date range, source refs. | W3 | No | `station_id`, `region_key`, `latitude`, `longitude`, `elevation_m`, `active_date_range`, `source_ref`, review fields. | Spatial readiness only. |
| `03_partner_handoff_packet/weather_station_observations.csv` | Weather feature evidence. | Validate row counts and date coverage. | Fill station weather observations. | W3-W5 | No | `station_id`, `observed_at`, `air_temp_c`, `precipitation_mm`, `snowfall_cm`, `snow_depth_cm`, wind fields, source/review fields. | Feature evidence only. |
| `03_partner_handoff_packet/snowpack_profile_features.csv` | Snowpack and weak-layer evidence. | Validate profile completeness. | Fill layers, depth, grain, hardness, stability, quality flag. | W4-W8 | No | `station_id`, `observed_at`, `layer_index`, `layer_depth_cm`, `grain_type`, `hardness_index`, `stability_index`, review fields. | Research-only until validated. |
| `03_partner_handoff_packet/danger_labels_and_bulletins.csv` | D_tidy-equivalent danger label evidence. | Validate provenance and controlled values. | Fill reviewed labels and bulletin context. | W4 | No | `region_id`, `valid_from`, `valid_to`, `danger_scale_standard`, `danger_level_1_to_5`, `danger_level_1_to_4`, `avalanche_problem`, `review_status`, source/review fields. | Not accuracy proof alone. |
| `03_partner_handoff_packet/warning_region_polygons.csv` | Warning region geometries. | Validate CRS, region joins, elevation policy. | Fill polygons and validity dates. | W7-W9 | No | `region_id`, `polygon_geometry`, `crs`, `elevation_policy`, `valid_date_range`, source/review fields. | Aggregation prerequisite. |
| `03_partner_handoff_packet/historical_avalanche_events.csv` | Event truth / outcome evidence. | Validate source refs and event coverage. | Fill observed events and confidence. | W5-W11 | No | `event_id`, `observed_at`, `latitude`, `longitude`, `elevation_m`, `aspect`, `avalanche_problem`, `observed_outcome`, `confidence`, source/review fields. | Validation input only. |
| `03_partner_handoff_packet/remote_sensing_validation_scenes.csv` | SAR/optical scene validation references. | Keep SAR shadow-gated. | Provide reviewed scene refs only if available. | W6-W11 | No | `scene_id`, `sensor`, `acquired_at`, `preprocessing_level`, `truth_mask_or_event_ref`, `holdout_split`, source/review fields. | SAR not operational. |
| `03_partner_handoff_packet/terrain_ates_runout_validation.csv` | Terrain and runout validation evidence. | Validate DEM/runout source refs. | Fill slope, aspect, class, and validation refs. | W8-W11 | No | `region_id`, `dem_ref`, `slope`, `aspect`, `terrain_class`, `runout_validation_ref`, `quality_flag`, review fields. | Context evidence only. |
| `03_partner_handoff_packet/scientist_reviews.csv` | Scientist adjudication ledger. | Prepare cases and ingest decisions. | Fill verdict, label quality, model error type, confidence, notes. | W8-W12 | Partial | `review_id`, `reviewer_id`, `reviewed_at`, `case_id`, `verdict`, `label_quality`, `model_error_type`, `confidence`, source/review fields. | Human review only. |
| `03_partner_handoff_packet/independent_himalayan_holdout.csv` | Fresh local holdout definition. | Enforce leakage audit. | Define holdout source refs, regions, dates, and floors after protocol signoff. | W9-W12 | No | `holdout_id`, `source_refs`, `region_ids`, `date_range`, `leakage_check`, `acceptance_floors`, source/review fields. | Required before claims. |
| `03_partner_handoff_packet/himalayan_local_holdout_*` | Holdout protocol, leakage audit, prediction template, and metric report. | Run only after real partner evidence is ready. | Sign protocol and review outputs. | W9-W12 | No | Holdout rows, predictions, metrics, leakage status. | Release-gate input only. |
| `03_partner_handoff_packet/release_gate_attestation_template_pack.*` | Named release-gate attestation. | Keep blocked unless evidence passes. | Named scientist approver signs only after gates pass. | W12-W13 | No | approver, evidence digest, floors, measured results. | Controls claims. |
| `04_workorders_and_weekly_execution/MVP_V2_W0_W13_PARTNER_WORKORDER.md` | Step-by-step weekly workorder. | Use as execution guide. | Use as scientist/partner checklist. | W0-W13 | Mixed | Weekly file list and columns. | Workorder only. |
| `05_deck_sources_for_traceability/` | Deck source and build/QA scripts. | Use if regenerating deck outputs. | No action. | As needed | No | Source Markdown, JS build script. | Traceability only. |
| `99_synthetic_smoke_only_DO_NOT_SUBMIT/` | Synthetic validator smoke package. | Use only to smoke-test validation tooling. | Do not submit as evidence. | Optional | No | Synthetic fixture rows. | Never evidence. |

## Himalaya Inclusion Checklist

| Requirement To Include Himalayas Live | Required Input / File | Owner | Current Status | UI Today? | Done Criteria |
|---|---|---|---|---|---|
| Partner source governance | `03_partner_handoff_packet/partner_source_manifest_template.{json,md}` | Partner + Sanjay team | Template ready | No | Manifest has owner, license scope, review date, SHA-256 refs. |
| Station metadata | `03_partner_handoff_packet/station_metadata.csv` | Partner + geospatial reviewer | Template ready | No | `station_id`, `region_key`, `latitude`, `longitude`, `elevation_m`, source refs pass validation. |
| Weather observations | `03_partner_handoff_packet/weather_station_observations.csv` | Partner | Template ready | No | Reviewed rows cover pilot region/date windows. |
| Snowpack and weak-layer evidence | `03_partner_handoff_packet/snowpack_profile_features.csv` | Partner + scientist | Template ready | No | Reviewed profile rows with layer/stability fields. |
| D_tidy-grade labels | `03_partner_handoff_packet/danger_labels_and_bulletins.csv` | Scientist + partner | Template ready | No | Reviewed labels with source, review status, dates, danger scale, notes. |
| Warning-region polygons | `03_partner_handoff_packet/warning_region_polygons.csv` | Partner + geospatial reviewer | Template ready | No | Region geometry, CRS, elevation policy, validity range pass. |
| Avalanche event truth | `03_partner_handoff_packet/historical_avalanche_events.csv` | Scientist + partner | Template ready | No | Event rows include location, outcome, confidence, source refs. |
| Remote-sensing scenes | `03_partner_handoff_packet/remote_sensing_validation_scenes.csv` | SAR/geospatial reviewer | Template ready | No | Scene metadata and truth refs reviewed; still shadow-gated. |
| Terrain/runout validation | `03_partner_handoff_packet/terrain_ates_runout_validation.csv` | Geospatial reviewer + scientist | Template ready | No | DEM/runout refs and terrain class pass review. |
| Scientist adjudication | `03_partner_handoff_packet/scientist_reviews.csv` | Scientist lead | Template ready; partial UI concepts exist | Partial | Verdict, label quality, model error type, confidence, notes recorded. |
| Independent holdout | `03_partner_handoff_packet/independent_himalayan_holdout.csv` | Holdout auditor + scientist | Template ready | No | Fresh holdout passes leakage audit and source-ref checks. |
| Live app region wiring | App region config, map bounds, tile/projection settings | Product/dev team | Not implemented for Himalayan live claim | Yes after development | Public route can render selected Himalayan pilot region without overclaim. |
| Model/evaluation promotion | Holdout metric report + release attestation | ML + scientist approver | Blocked | No | Local metrics and named release-gate attestation pass. |
