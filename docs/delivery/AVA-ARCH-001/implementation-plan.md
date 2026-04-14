# Avalanche-First Architecture Plan

## Adversarial Review Summary

### What is strong in the proposed roadmap

- It correctly prioritizes labels, calibration, and evaluation instead of raw feature accumulation.
- It keeps Supabase Edge Functions in an orchestration role.
- It recognizes that regional behavior and reviewer credibility matter more than a single global metric.

### What needed correction

1. The original ordering assumed a more mature model than the repo currently contains.
2. Governance alone is insufficient unless lineage fields are wired into runtime immediately.
3. Regional calibration should follow a usable evaluation harness, not precede it.
4. Snow-cover ingestion should start as summary features, not raster-heavy assimilation.
5. Retraining and active learning should wait until label policy and slice metrics exist.

## Recommended Execution Slices

### Slice 1: Governance plus lineage foundation

- Add PRD addendum, evaluation spec, and label policy
- Add schema fields for `hazard_type`, uncertainty, and model lineage
- Thread new metadata through `run-forecast` and `trigger-job`

### Slice 2: Event and report quality schema

- Extend `avalanche_events` with verification, label-role, and richer geometry support
- Add normalized report and review-routing fields for `field_reports`
- Keep UI behavior avalanche-only

### Slice 3: Outcome labeling and evaluation harness

- Add `forecast_outcomes`, `evaluation_runs`, `evaluation_metrics`, and slice tables
- Add replayable matching policy with explicit versioning
- Build admin-only evaluation reporting

### Slice 4: Feature enrichment

- Add snow-cover summary ingestion
- Add recent-activity materialization
- Add source freshness and feature completeness accounting

### Slice 5: Calibration and promotion controls

- Add regional calibration profiles
- Add threshold profiles
- Add activation and rollback workflow

### Slice 6: Learning loop

- External retraining trigger
- candidate-vs-incumbent evaluation
- active-learning review queue

## Exit Criteria for Slice 1 ✅

- New documentation exists under `docs/delivery/AVA-ARCH-001/`
- Core tables can store hazard, lineage, and uncertainty fields
- `run-forecast` persists those fields
- `trigger-job` supports the next planned job families
- Existing UI behavior remains unchanged

## Exit Criteria for Slice 2 ✅

- `avalanche_events` has verification_status and label_role columns
- `field_reports` has review_status and training_eligible columns
- Geometry index exists for event_geom
- Review queue index for pending reports

## Exit Criteria for Slice 3 ✅

- `forecast_outcomes` table exists with labeling logic
- `evaluation_runs` and `evaluation_metrics` tables exist
- `model_registry` tracks candidate/incumbent models
- `active_learning_queue` for uncertain cases
- `label-forecast-outcomes` Edge Function deployed
- `run-evaluation` Edge Function deployed

## Exit Criteria for Slice 4 ✅

- `snow_cover_snapshots` table for lightweight snow summary
- `recent_activity_features` table for materialized summaries
- `feature_completeness_log` for audit trail
- `ingest-snow-cover` Edge Function deployed
- `recent-activity-refresh` Edge Function deployed

## Exit Criteria for Slice 5 ✅

- `calibration_profiles` for regional adjustments
- `threshold_profiles` for risk band mapping
- `promotion_events` audit log
- `rollback_state` for emergency recovery
- Default profiles seeded for 'global'

## Exit Criteria for Slice 6 🔄 (Partial)

- Model registry infrastructure exists
- Active learning queue schema ready
- Retraining job type supported
- External training pipeline: PENDING (requires external compute)
- Human review UI: PENDING

## Implementation Status

**Completed**: Slices 1-5 fully implemented, Slice 6 infrastructure ready  
**Files Created**: 4 migrations, 4 Edge Functions, updated AdminDashboard  
**See**: [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) for details
