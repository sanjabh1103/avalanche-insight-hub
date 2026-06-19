# Himalayan Release-Gate Attestation Template Pack

Decision: `release_gate_attestation_template_pack_written_pending_validated_evidence`

This template pack tells reviewers how to document release-gate evidence after partner evidence passes. It is not evidence and does not authorize production scoring.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Template is evidence | `false` |
| Release gates | 4 |
| Attestation max age days | 180 |

## Gate Templates

| Gate | Required Fields | Acceptance Floor Requirements |
|---|---|---|
| `local_himalayan_holdout_passed` | `approved_by`, `summary`, `evidence_ref`, `reviewed_at`, `evidence_schema_version`, `validation_policy_version`, `acceptance_floors_ref`, `acceptance_floors`, `measured_results` | `ratio_fields`=macro_f1_min, high_danger_recall_min, mean_day_accuracy_min, region_accuracy_min, `max_ratio_fields`=brier_score_max, ece_max, `true_fields`=leakage_check_required, independent_holdout_required |
| `scientist_review_complete` | `approved_by`, `summary`, `evidence_ref`, `reviewed_at`, `evidence_schema_version`, `validation_policy_version`, `acceptance_floors_ref`, `acceptance_floors`, `measured_results` | `positive_integer_fields`=reviewed_case_count_min, reviewer_count_min, `ratio_fields`=adjudication_completion_rate_min, `nonnegative_integer_fields`=unresolved_critical_issue_max |
| `license_clearance_complete` | `approved_by`, `summary`, `evidence_ref`, `reviewed_at`, `evidence_schema_version`, `validation_policy_version`, `acceptance_floors_ref`, `acceptance_floors`, `measured_results` | `ratio_fields`=source_license_review_coverage_min, `nonnegative_integer_fields`=blocked_license_scope_count_max, unsupported_license_scope_count_max |
| `production_promotion_approved` | `approved_by`, `summary`, `evidence_ref`, `reviewed_at`, `evidence_schema_version`, `validation_policy_version`, `acceptance_floors_ref`, `acceptance_floors`, `measured_results` | `true_fields`=rollback_plan_required, monitoring_required, human_override_required, production_scoring_approval_required |

## Operator Rules

- Use this template only after partner evidence validation passes and scientist review is ready.
- Every gate needs a named approver, evidence digest, reviewed_at timestamp, acceptance floors, and measured results.
- Human approval text alone is insufficient without structured floors and measured results.
- Production scoring remains false even when claim-review gates pass; promotion requires a separate production path.

## Standards Anchors

| Anchor | Use | URL |
|---|---|---|
| NIST AI Risk Management Framework | Keep release decisions traceable, reviewed, and risk-governed before deployment claims. | https://www.nist.gov/itl/ai-risk-management-framework |
| WMO WIGOS data quality monitoring | Require quality-controlled observation and evidence handling before operational use. | https://community.wmo.int/en/activity-areas/wigos/wigos-data-quality-monitoring-system-wdqms |
| ISO 19157 geospatial data quality | Track geospatial completeness, lineage, consistency, and quality in release evidence. | https://www.iso.org/standard/78900.html |
| FAIR data principles | Keep final evidence reusable, source-referenced, and auditable. | https://www.go-fair.org/fair-principles/ |

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This pack is a blank attestation template. It is not validated evidence, accepted release-gate proof, or production authorization.
