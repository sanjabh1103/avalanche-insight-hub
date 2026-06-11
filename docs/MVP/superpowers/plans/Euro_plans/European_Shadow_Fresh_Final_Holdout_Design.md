# European Shadow SAR Fresh Final Holdout Design

This is a design-only note. Do not construct, materialize, or evaluate a fresh final holdout until a SAR candidate first passes SnowSlide research-grade qualification.

## Purpose

SnowSlide has influenced threshold and candidate decisions. If a future candidate passes SnowSlide research-grade, a separate final holdout is required before Phase 7 promotion readiness.

## Required Properties

| Requirement | Rule |
|---|---|
| Independence | Must not reuse `snowslide-heldout-v1`. |
| Scene selection | Must include independent scenes not used for threshold selection, manual review, or candidate design. |
| Decision rule | Must use the exact accepted candidate threshold and post-processing rule unchanged. |
| Acceptance floors | Precision `>=0.70`, recall `>=0.50`, F1 `>=0.60`, false-positive rate `<=0.002`. |
| Persistence | Dry-run only until explicit promotion review. |
| License | Every source must have reviewed license and attribution terms before external sharing. |

## Leakage Controls

- Do not inspect labels while tuning thresholds or candidate design.
- Record scene IDs and source provenance before evaluation.
- Preserve a single immutable evaluation request.
- Treat any post-hoc threshold change as leakage that resets final-holdout validity.

## Current Status

Blocked. v8 did not pass SnowSlide research-grade, so fresh final holdout construction is premature.

The Sanjay B. shadow-only presentation authorization and Dr. AK___ manual-review assignment do not change this holdout status.
