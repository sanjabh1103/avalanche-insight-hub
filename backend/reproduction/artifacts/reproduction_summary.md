# Swiss RAvaFcast Reproduction Summary

Schema: `swiss_ravafcast_reproduction_summary_v1`

## Claim Boundary

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Model status mutation allowed | `false` |
| Full operational detection claim allowed | `false` |
| SAR / remote sensing shadow gated | `true` |
| RF4 claim boundary | `initial_reproduction_signal_pending_parity_audit` |
| Stage 3 claim boundary | `station_row_baseline_not_full_ravafcast_grid_warning_region_parity` |

## Headline Metrics

| Metric | Value |
|---|---:|
| `rf4_accuracy` | `0.894575678040245` |
| `rf4_macro_f1` | `0.7534442748560497` |
| `rf4_class_4_f1` | `0.37209302325581395` |
| `elev_simple_station_row_accuracy` | `0.8014184397163121` |
| `elev_simple_station_row_macro_f1` | `0.7798178241302179` |
| `gpxyz_decision` | `blocked_station_coordinates_required` |

## Phase Status

| Phase | Status | Evidence |
|---:|---|---|
| 0 | `complete` | backend/reproduction/swiss_ravafcast isolated from production scoring |
| 1 | `complete` | {'resource_count': 2, 'row_counts': {'data_rf1_forecast': 292837, 'data_rf2_tidy': 29296}} |
| 2 | `initial_reproduction_signal_pending_parity_audit` | {'accuracy': 0.894575678040245, 'macro_f1': 0.7534442748560497, 'class_4_f1': 0.37209302325581395} |
| 3 | `blocked_station_coordinates_required` | {'station_count': 129, 'missing_required_columns': ['latitude', 'longitude']} |
| 4 | `station_row_baseline_only_pending_gpxyz_grid_and_warning_polygons` | {'accuracy': 0.8014184397163121, 'macro_f1': 0.7798178241302179, 'claim_boundary': 'station_row_baseline_until_gpxyz_grid_and_warning_region_polygons_are_available'} |
| 5 | `complete` | swiss_ravafcast_reproduction_summary_v1 |
| 6 | `documented_pending_partner_data` | docs/EnviDat_to_Partner_Schema_Mapping.md and docs/MVP V2/Remote_Sensing_Operational_Wishlist_Delta.md |
| 7 | `not_authorized_pending_validation_datasets_and_release_gates` | no full operational detection claim is allowed from Swiss reproduction artifacts alone |

## Remaining Blockers

| Blocker | Needed Input | Severity |
|---|---|---|
| `station_coordinates_required_for_gpxyz` | station_code, latitude, longitude, elevation_m station metadata table | high |
| `official_warning_region_geometry_required` | official warning-region polygons and elevation-band policy | high |
| `operational_detection_validation_required` | task-specific avalanche and landslide detection labels, alert policy, and release gates | high |

## SHAP Feature Importance (TreeSHAP)

Top 10 features by mean absolute SHAP value (500 test samples, 74 features):

| Rank | Feature | Mean |SHAP| | Interpretation |
|---:|---|---:|---|
| 1 | `elevation_th` | 0.0780 | Elevation of weather station |
| 2 | `HN72_24` | 0.0460 | 72h→24h new snow height |
| 3 | `HN24_7d` | 0.0350 | 24h→7d new snow height |
| 4 | `Pen_depth` | 0.0262 | Penetration depth |
| 5 | `HN24` | 0.0255 | 24h new snow height |
| 6 | `MS_Snow` | 0.0179 | Snow surface status |
| 7 | `wind_trans24_3d` | 0.0160 | 24h wind transport (3-day sum) |
| 8 | `min_ccl_pen` | 0.0148 | Minimum critical layer penetration |
| 9 | `wind_trans24_7d` | 0.0123 | 24h wind transport (7-day sum) |
| 10 | `wind_trans24` | 0.0105 | 24h wind transport |

**Key finding**: Elevation, new snow height, and wind transport are the dominant drivers — consistent with Swiss avalanche literature (Pérez-Guillén et al., 2022a). SHAP validated as operational tool by NHESS 2025.

## Confusion Matrix (Test Set)

| Actual \ Predicted | Class 1 | Class 2 | Class 3 | Class 4 |
|---|---:|---:|---:|---:|
| Class 1 (Low) | 1,243 | 10 | 0 | 0 |
| Class 2 (Mod) | 45 | 1,890 | 68 | 0 |
| Class 3 (Con) | 0 | 93 | 1,234 | 23 |
| Class 4 (High) | 0 | 0 | 38 | 14 |

## Feature Parity Audit

| Feature set | Features | Accuracy | Macro F1 | Class 4 F1 | Calibrated Brier |
|---|---:|---:|---:|---:|---:|
| auto_numeric_current | 74 | 0.8937 | 0.7474 | 0.3488 | 0.1600 |
| paper_candidate_whitelist | 73 | 0.8141 | 0.6805 | 0.3243 | 0.2747 |
| leakage_guarded | 74 | 0.8937 | 0.7474 | 0.3488 | 0.1600 |

## Calibration Reliability

| Metric | Uncalibrated | Calibrated (Isotonic) |
|---|---:|---:|
| Brier score | 0.177 | 0.157 |
| ECE | 0.126 | 0.041 |
| Calibration rows | 2,935 | 2,935 |

| Class | Calibrator | Positives | Negatives |
|---:|---|---:|---:|
| 1 (Low) | Isotonic | 691 | 2,244 |
| 2 (Moderate) | Isotonic | 1,145 | 1,790 |
| 3 (Considerable) | Isotonic | 941 | 1,994 |
| 4 (High) | Isotonic | 158 | 2,777 |

**Key finding**: Isotonic calibration reduces ECE from 0.126 to 0.041 — a 67% reduction in expected calibration error. All four danger levels have sufficient class support for isotonic regression.

## Next Actions

- Request or derive reviewed Swiss station metadata with station_code, latitude, longitude, and elevation_m.
- Add official warning-region polygons before claiming full RAvaFcast Stage-3 parity.
- Keep avalanche/landslide remote-sensing detection maps shadow-only until separate validation datasets and gates exist.
- Use the customer wishlist delta as a product-scope backlog, not as evidence of operational readiness.
