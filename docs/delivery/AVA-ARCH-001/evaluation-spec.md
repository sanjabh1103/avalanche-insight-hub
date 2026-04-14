# Avalanche Model Evaluation Specification

## Purpose

Define the release evaluation contract for all avalanche forecast model candidates, calibration profiles, and threshold profiles.

## Evaluation Units

Metrics must be computed at the following levels:

- Global
- Region
- Season
- Elevation band
- Lead time bucket
- Verification-confidence slice

Optional slices may include aspect bucket and source-density bucket once label quality supports them.

## Core Metrics

### Event discrimination

- PR-AUC for severe-event detection
- Recall for verified events within policy tolerance
- Precision at `risk >= 4`
- Precision at `risk >= 3`

### Calibration

- Expected Calibration Error (ECE)
- Brier score
- Reliability curves by region and globally

### False alarm control

- Severe false alarm rate
- Alert volume by region and season

### Operational usefulness

- Distance to nearest verified event for alerted cells
- Lead-time distribution for matched events
- Elevation-band hit rate

### Human review

- Mean reviewer score
- Reviewer disagreement rate
- Override rate against model output

## Matching Policy Inputs

Evaluation runs must declare:

- label version
- model version
- feature version
- threshold profile version
- calibration profile version
- space-time tolerance policy version

## Release Gates

A candidate can only be promoted when:

1. It beats or matches the incumbent on the global weighted release rubric.
2. It does not materially regress in any protected region slice.
3. Calibration metrics improve or remain within approved bounds.
4. Reviewer score remains at or above the release threshold.

## Regression Rules

Promotion must be blocked if any of the following occurs:

- Severe-event recall drops by more than `0.03` in a protected region.
- False alarm rate worsens by more than `0.05` without compensating recall improvement approved by reviewers.
- ECE worsens above the release limit.
- Reviewer mean falls below `4.5 / 5`.

## Run Outputs

Each evaluation run must persist:

- summary metrics
- slice metrics
- reliability outputs
- run metadata
- artifact links for plots or reports
- approval status and approver identity

## Decision Policy

- Evaluation is advisory for prototype mode.
- Evaluation is mandatory for production mode.
- No model, threshold, or calibration profile may be activated without a successful evaluation run tied to immutable inputs.
