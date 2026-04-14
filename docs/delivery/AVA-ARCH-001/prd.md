# Avalanche Accuracy Architecture Addendum

## Objective

Define the avalanche-first product contract required to move from a demo-grade heuristic forecaster to a production-grade avalanche forecast system without diluting trust through premature multi-hazard expansion.

## Current-State Reality

- The current `run-forecast` edge function is a heuristic scorer using Open-Meteo point weather plus synthetic terrain variation.
- The current model status surface exposes a single `f1_score`, which is not sufficient for probabilistic hazard release decisions.
- Field-report enrichment and fine-tuning flows are operational placeholders rather than auditable learning pipelines.
- Forecast persistence exists, but lineage, uncertainty, labels, and review metadata are not yet first-class.

## Product Decision

- Product scope remains avalanche-first in UI, release process, metrics, reviewer workflows, and public messaging.
- Multi-hazard expansion is deferred until avalanche-specific release gates are consistently met.
- Schema may include `hazard_type = 'avalanche'` now to avoid avoidable rewrites, but this is infrastructure-only and must not broaden public scope.

## North-Star Release Rubric

Promotion to "production-grade avalanche forecast" requires a weighted score of at least `4.5 / 5.0`.

| Dimension | Weight | Operational interpretation |
| --- | ---: | --- |
| Event discrimination | 30% | Severe-event recall and ranking quality improve on held-out seasons and regions |
| Calibration | 20% | Forecast probabilities or risk buckets align with observed outcomes |
| False alarm control | 20% | Severe alerts stay below an agreed false-alarm ceiling |
| Spatial and temporal usefulness | 15% | Forecasts are localized near real events at useful lead times |
| Expert review | 15% | Avalanche-informed reviewers judge forecast packages as credible and actionable |

## Product Constraints

- Edge Functions remain the control plane, not the heavy compute plane.
- Every persisted forecast must carry model lineage, data lineage, and uncertainty metadata.
- Labels and reviewer policies are release-critical, not optional support tooling.
- No hidden model, threshold, or calibration changes are allowed in production mode.

## Mandatory Release Metrics

- Severe-risk precision at `risk >= 4`
- Severe-risk precision at `risk >= 3`
- Severe-event recall within approved space-time tolerance
- False alarm rate for severe alerts
- Expected Calibration Error (ECE)
- Brier score
- Reliability curve outputs
- Expert review mean score

## Initial Ship Gates

These are target promotion gates, not assumptions about current performance.

- Severe-event recall `>= 0.75`
- Severe-risk precision `>= 0.60`
- False alarm rate `<= 0.35`
- ECE `<= 0.08`
- Expert review mean `>= 4.5 / 5`

## Architecture Principles

1. Avalanche-first trust before platform breadth.
2. Probabilistic outputs before richer visualization.
3. Reproducibility before retraining cadence.
4. Label quality before feature quantity.
5. Regional evaluation before global headline metrics.

## Milestone Ordering Decision

The roadmap will proceed in this order:

1. Governance contract and lineage schema
2. Forecast lineage and uncertainty plumbing
3. Event and report quality upgrades
4. Label-building and evaluation harness
5. Regional calibration and feature enrichment
6. External retraining and active-learning workflows

This ordering intentionally defers expensive ML automation until the system can measure whether it is helping.
