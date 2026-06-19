# Himalayan Local Holdout Evaluation Protocol

Decision: `local_himalayan_holdout_protocol_written_pending_partner_evidence`

Pre-register the independent Himalayan holdout split, leakage controls, metrics, acceptance floors, and reporting outputs before any local model selection or public accuracy claim.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Protocol is evidence | `false` |
| Required partner inputs | 11 |
| Required report outputs | 9 |

## Acceptance Floors

| Metric | Floor |
|---|---:|
| `macro_f1_min` | `0.7` |
| `high_danger_recall_min` | `0.8` |
| `brier_score_max` | `0.18` |
| `ece_max` | `0.08` |
| `mean_day_accuracy_min` | `0.75` |
| `region_accuracy_min` | `0.7` |
| `leakage_check_required` | `true` |
| `independent_holdout_required` | `true` |

## Split Policy

| Rule | Value |
|---|---:|
| `holdout_split_value` | `independent_holdout` |
| `minimum_holdout_ids` | `1` |
| `must_be_excluded_from_training` | `true` |
| `must_be_excluded_from_threshold_selection` | `true` |
| `must_be_excluded_from_calibration` | `true` |
| `temporal_overlap_allowed` | `false` |
| `source_ref_overlap_allowed` | `false` |
| `region_and_elevation_breakdown_required` | `true` |
| `five_level_danger_preserved_until_reviewed_mapping` | `true` |

## Leakage Controls

- No holdout row may be used for feature selection, calibration, threshold tuning, or release-gate floor selection.
- No source_ref SHA-256 digest may appear in both training/calibration evidence and independent_himalayan_holdout evidence.
- Holdout dates and warning-region identifiers must be reported explicitly before evaluation.
- Any four-class danger mapping must include reviewed mapping notes from the original five-level label.
- Remote-sensing scenes used for model or threshold selection cannot be reused as fresh final holdout evidence.

## Metric Groups

| Group | Metrics |
|---|---|
| `classification` | `macro_f1`, `per_class_f1`, `high_danger_recall`, `confusion_matrix`, `class_support` |
| `calibration` | `brier_score`, `expected_calibration_error`, `classwise_calibration_bins`, `expected_danger_before_after_calibration` |
| `spatial_temporal` | `mean_day_accuracy`, `median_day_accuracy`, `region_accuracy`, `elevation_band_accuracy`, `station_count`, `warning_region_count` |
| `event_and_remote_sensing` | `historical_event_recall`, `remote_sensing_precision`, `remote_sensing_recall`, `remote_sensing_f1`, `remote_sensing_false_positive_rate` |

## Required Report Outputs

- `himalayan_local_holdout_evaluation_report.json`
- `himalayan_local_holdout_evaluation_report.md`
- `himalayan_local_holdout_leakage_audit.json`
- `himalayan_local_holdout_metric_report.json`
- `himalayan_local_holdout_metric_report.md`
- `himalayan_local_holdout_region_breakdown.csv`
- `himalayan_local_holdout_calibration_bins.csv`
- `himalayan_local_holdout_confusion_matrix.csv`
- `himalayan_local_holdout_scientist_review_packet.md`

## Stop Conditions

- Stop if partner_source_manifest.json is missing or stale.
- Stop if independent_himalayan_holdout.csv is missing, blank, or has no independent_holdout rows.
- Stop if leakage audit finds source_ref, date, station, region, or scene contamination.
- Stop if any acceptance floor is missed; report blocker instead of weakening thresholds.
- Stop before production scoring even when the holdout passes; production requires separate release-gate attestations.

## Standards Anchors

| Anchor | Use | URL |
|---|---|---|
| RAvaFcast v1.0.0 | Keep station classification, spatial interpolation, and elevation/region aggregation as separate evaluation surfaces. | https://gmd.copernicus.org/articles/17/7569/2024/ |
| European Avalanche Warning Services danger scale | Preserve five-level danger semantics unless a reviewed mapping justifies aggregation. | https://www.avalanches.org/standards/avalanche-danger-scale/ |
| NIST AI Risk Management Framework | Pre-register evaluation and release evidence before any risky operational claim. | https://www.nist.gov/itl/ai-risk-management-framework |
| ISO 19157 geospatial data quality | Report geospatial completeness, lineage, consistency, and quality in holdout evidence. | https://www.iso.org/standard/78900.html |
| FAIR data principles | Keep holdout evidence source-referenced, reusable, and auditable. | https://www.go-fair.org/fair-principles/ |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This is a pre-registered protocol. It contains no local holdout results, no accepted release-gate attestation, and no production authorization.
