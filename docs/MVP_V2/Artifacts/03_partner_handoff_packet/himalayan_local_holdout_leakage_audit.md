# Himalayan Local Holdout Leakage Audit

Decision: `blocked_local_holdout_leakage_audit_no_holdout_rows`

This audit checks whether the independent Himalayan holdout package is structurally present, source-governed, and uncontaminated by non-holdout evidence.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Audit is prediction evidence | `false` |
| Holdout rows | 0 |
| Holdout source refs | 0 |
| Non-holdout source refs | 0 |
| Source-ref overlaps | 0 |
| Missing manifest hashes | 0 |
| Row issues | 0 |

## Checks

| Check | Passed | Detail |
|---|---:|---:|
| `holdout_file_present` | `true` | backend/artifacts/reproduction/himalayan_accuracy/partner_evidence_templates/independent_himalayan_holdout.csv |
| `holdout_rows_present` | `false` | 0 |
| `holdout_rows_valid` | `false` | 0 |
| `source_manifest_covers_holdout` | `false` | 0 |
| `source_ref_no_overlap_with_non_holdout_evidence` | `false` | 0 |

## Row Issue Examples

- None

## Overlapping Source Hashes

- None

## Next Actions

- Supply a reviewed independent_himalayan_holdout.csv with at least one independent holdout row.

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: The audit checks holdout leakage and source governance only. It is not model performance evidence or production authorization.
