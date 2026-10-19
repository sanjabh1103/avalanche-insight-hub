# Swiss RF4 Feature Parity Audit

Decision: `initial_reproduction_signal_pending_parity_audit`

| Feature set | Features | Accuracy | Macro F1 | Class 4 F1 | Calibrated Brier | Accuracy delta vs RF2 upper |
|---|---:|---:|---:|---:|---:|---:|
| auto_numeric_current | 74 | 0.8937 | 0.7474 | 0.3488 | 0.1600 | 0.1137 |
| paper_candidate_whitelist | 73 | 0.8141 | 0.6805 | 0.3243 | 0.2747 | 0.0341 |
| leakage_guarded | 74 | 0.8937 | 0.7474 | 0.3488 | 0.1600 | 0.1137 |

## Claim Boundary

This audit compares feature-set behavior only. It does not establish RAvaFcast paper parity, production readiness, or Himalayan transfer validity.
