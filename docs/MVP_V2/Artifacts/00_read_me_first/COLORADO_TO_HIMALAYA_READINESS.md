# Colorado Rockies Live Proof And Himalayan Readiness

Status: 2026-05-24

## Why Colorado Rockies Is Live First

| Question | Answer For Scientist / Client |
|---|---|
| Why Colorado Rockies first? | Colorado Rockies is the currently verified live proof region because the hosted app already has public and `/admin` evidence for a same-day `20x20` / `72h` full-grid technical publication dated 2026-05-08. It is a safe operational proof surface for routes, publication mechanics, grid rendering, admin observability, and claim-boundary demonstration. It is **not** being used as proof of Himalayan accuracy. |
| Is Colorado the target geography? | No. It is the current live technical proof geography. The target expansion is Himalayan readiness, but that needs local reviewed data, partner source governance, scientist validation, and release gates before live claims. |
| Why not switch the live claim to Himalayas now? | Because the repo has Himalayan partner templates, synthetic smoke checks, and candidate/public-source context, but not yet reviewed Himalayan `D_tidy` labels, station X/Y/Z coverage, warning-region polygons, local holdout metrics, and scientist release attestation. |
| What changes when Himalayas are ready? | The app can move from "Colorado live technical proof + Himalayan evidence intake" to "Himalayan pilot region live technical publication" only after ingestion, validation, local holdout, UI region wiring, and release-gate approval pass. |

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

## Practical Transition Path

1. Keep Colorado Rockies as the live technical proof surface for the meeting.
2. Use the Himalayan packet to collect real partner evidence.
3. Run preflight, source-manifest validation, evidence validation, quality scoring, leakage audit, and holdout metrics only after real partner rows arrive.
4. Add Himalayan UI/region wiring only after at least one pilot region has enough validated evidence to render without implying accuracy.
5. Change public claim language only after release-gate attestation passes with a named scientist approver.
