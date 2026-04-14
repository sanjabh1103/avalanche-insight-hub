# Avalanche Label Policy

## Purpose

Define how avalanche events, field reports, and non-events become trustworthy training and evaluation labels.

## Label Classes

- Positive label: verified avalanche event matched to a forecast cell and time window
- Hard negative: no verified event inside tolerance with sufficient observation coverage
- Uncertain label: ambiguous evidence, sparse coverage, or conflicting sources
- Display-only evidence: useful for UI or review but excluded from training

## Evidence Tiers

1. `expert_verified`
2. `verified`
3. `weak`
4. `unverified`

Only `expert_verified` and `verified` evidence may enter the default supervised training set unless a reviewed exception is recorded.

## Source Quality

Every event or normalized report should carry:

- source identifier
- verification status
- source quality score
- geometry precision
- reviewer status if manually reviewed

## Training Eligibility Rules

Training inclusion requires:

- approved hazard type
- acceptable verification status
- acceptable source quality
- no unresolved dedupe conflict
- no unresolved geometry ambiguity
- no unresolved time ambiguity

## Non-Deletion Rule

Low-quality or rejected evidence should remain stored for audit purposes, but marked as:

- `label_role = 'excluded'`, or
- `label_role = 'display_only'`

This preserves lineage and allows policy evolution without losing provenance.

## Forecast Outcome Policy

Outcome labels must declare:

- forecast identifier
- cell identifier or grid coordinates
- forecast lead time
- outcome window
- event observed flag
- severity label
- distance to nearest verified event
- label confidence
- label version

## Human Review Policy

Manual review is required for:

- high-impact false positives
- suspected misses
- conflicting source merges
- low-confidence positives
- normalization outputs below confidence threshold

## Versioning Policy

Any change to matching tolerance, source inclusion, or confidence thresholds requires a new `label_version`.
