# Himalayan Avalanche Prediction Top-10 Feature Gap Matrix

Decision: `top10_feature_gap_matrix_written_pending_partner_evidence`

This matrix keeps the best-in-class avalanche prediction strategy tied to the current evidence contract. It is research-only and does not authorize production scoring or a Himalayan accuracy claim.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Feature count | 10 |
| Blocked feature count | 10 |
| Confidence position | `not_100_percent_confident_local_himalayan_evidence_required` |

## Top-10 Matrix

| # | Feature | Rating /5 | Readiness | Available Evidence | Blocked Evidence | Next Action |
|---:|---|---:|---|---|---|---|
| 1 | Himalayan station + snowpack data contract | 2 | `blocked_partner_evidence_required` | None | `station_metadata`, `weather_station_observations`, `snowpack_profile_features`, `danger_labels_and_bulletins` | Obtain a complete partner source manifest and filled station/weather/snowpack/danger CSVs. |
| 2 | Calibrated 4-class danger-level model | 3 | `blocked_partner_evidence_required` | None | `weather_station_observations`, `snowpack_profile_features`, `danger_labels_and_bulletins`, `independent_himalayan_holdout` | Run calibrated model evaluation only after local partner labels and holdout are available. |
| 3 | RAvaFcast-style spatial interpolation | 2 | `blocked_partner_evidence_required` | None | `station_metadata`, `weather_station_observations`, `danger_labels_and_bulletins` | Validate station coordinate coverage, then run GPxyz LOOCV and grid generation. |
| 4 | Elevation-band warning-region aggregation | 2 | `blocked_partner_evidence_required` | None | `warning_region_polygons`, `station_metadata`, `danger_labels_and_bulletins` | Acquire reviewed warning-region polygons and elevation-band policy. |
| 5 | Distributed snowpack / weak-layer evidence | 2 | `blocked_partner_evidence_required` | None | `snowpack_profile_features`, `weather_station_observations`, `danger_labels_and_bulletins` | Add reviewed snowpack profile exports and map fields to controlled partner schema. |
| 6 | Terrain, ATES, runout and exposure features | 3 | `blocked_partner_evidence_required` | None | `terrain_ates_runout_validation`, `warning_region_polygons`, `historical_avalanche_events` | Validate terrain/runout rows against partner-reviewed regions and events. |
| 7 | Remote-sensing avalanche evidence | 3 | `blocked_partner_evidence_required` | None | `remote_sensing_validation_scenes`, `historical_avalanche_events`, `independent_himalayan_holdout` | Collect Himalayan remote-sensing validation scenes and keep SAR/optical/InSAR shadow-gated. |
| 8 | Field reports and event-outcome feedback loop | 4 | `blocked_partner_evidence_required` | None | `historical_avalanche_events`, `scientist_reviews`, `danger_labels_and_bulletins` | Route real events through scientist review and close label/model error types. |
| 9 | Explainability, calibration and model-vs-human diagnostics | 3 | `blocked_partner_evidence_required` | None | `scientist_reviews`, `independent_himalayan_holdout`, `danger_labels_and_bulletins` | Add model-vs-scientist/outcome report once reviewed cases exist. |
| 10 | Release gates, uncertainty and claim governance | 4 | `blocked_partner_evidence_required` | None | `independent_himalayan_holdout`, `scientist_reviews`, `remote_sensing_validation_scenes` | Populate release-gate attestations only after local evidence and independent holdout pass. |

## External Anchors

| Anchor | Implication | URL |
|---|---|---|
| RAvaFcast v1.0.0 | Treat best-class danger forecasting as a pipeline from station classification through spatial interpolation to elevation/region aggregation. | https://gmd.copernicus.org/articles/17/7569/2024/ |
| European Avalanche Warning Services danger scale | Preserve five-level danger semantics and avoid silent label collapse. | https://www.avalanches.org/standards/avalanche-danger-scale/ |
| WMO WIGOS data quality monitoring | Treat observation readiness as a monitored data-quality pipeline. | https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms |
| NHESS model-vs-human avalanche warning skill literature | Compare models against expert forecasts and outcomes, not aggregate accuracy alone. | https://nhess.copernicus.org/articles/25/3333/2025/ |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This matrix is strategy and evidence-gap tracking only. It does not provide local Himalayan validation, release-gate attestations, or production authorization.
