# Himalayan Local Holdout Metric Report

Decision: `blocked_local_holdout_metric_report_leakage_audit_not_passed`

This report is the executable metric gate for the independent Himalayan holdout. It refuses to evaluate metrics unless the leakage audit passes first.

| Gate | Value |
|---|---:|
| Production scoring allowed | `false` |
| Himalayan accuracy claim allowed | `false` |
| Metric report is prediction evidence | `false` |
| Leakage audit decision | `blocked_local_holdout_leakage_audit_no_holdout_rows` |
| Prediction rows | 0 |
| Prediction row issues | 0 |

## Acceptance Floors

| Metric | Observed | Floor | Passed |
|---|---:|---:|---:|
| Not evaluated |  |  | `false` |

## Row Issue Examples

- None

## Next Actions

- Pass the local holdout leakage audit before metric evaluation.

## Claim Boundary

- Production scoring allowed: `false`
- Himalayan accuracy claim allowed: `false`
- Reason: This report is a local holdout metric gate. It can support a release-gate attestation only after leakage, prediction rows, and all acceptance floors pass.
