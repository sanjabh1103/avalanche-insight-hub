# Avalanche-First Architecture Implementation Summary

**Status**: Slice 2-6 Implementation Complete  
**Date**: 2026-04-14  
**Path**: Path A - Avalanche-first accuracy improvements

## What Was Implemented

### Slice 1: Governance + Lineage Foundation ✅ (Previously Complete)
- [prd.md](./prd.md), [evaluation-spec.md](./evaluation-spec.md), [label-policy.md](./label-policy.md)
- Schema migration: `20260414130000_avalanche_governance_foundation.sql`
- Runtime lineage fields in `run-forecast` and `trigger-job`

### Slice 2: Event/Report Quality Schema ✅ (This Session)

**Migration**: `20260414140000_avalanche_event_quality_schema.sql`

**Database Changes**:
- Extended `avalanche_events` with:
  - `event_geom` (Geometry, 4326) - full polygon/line support
  - Verification status enum: `unverified`, `weak`, `verified`, `expert_verified`
  - Label role: `training_label`, `display_only`, `excluded`
  - Event subtype, trigger type, size scale
  - Elevation, aspect bucket, slope band
  - Start/end time for temporal events
  - Source quality score, recent activity weight
  - Event features JSONB for extensibility

- Extended `field_reports` with:
  - Review status workflow: `pending`, `under_review`, `approved`, `rejected`, `needs_info`
  - Normalized event type, severity, trigger type
  - Terrain context, aspect, elevation
  - Confidence score, location precision
  - Reporter reliability, dedupe group
  - Training eligibility flag
  - Review tracking (who, when)

- Added indexes:
  - Review queue index for pending reports
  - Dedupe index for linking duplicate reports
  - Training eligibility index
  - Event geometry GiST index

### Slice 3: Forecast Outcome Labeling + Evaluation Harness ✅ (This Session)

**Migration**: `20260414150000_forecast_outcome_labeling.sql`

**New Tables**:
- `forecast_outcomes` - Labels for each forecast cell/hour matched to events
  - Cell identification (row, col, hour)
  - Predicted vs observed outcomes
  - Spatial matching (distance to nearest event)
  - Temporal matching (outcome window)
  - Label confidence and version
  - Exclusion flags for noisy labels

- `evaluation_runs` - Systematic backtesting records
  - Model version, label version, threshold version
  - Overall metrics (precision, recall, FPR, ECE)
  - Status tracking (running, completed, failed)

- `evaluation_metrics` - Stratified performance by slice
  - Slice types: region, season, elevation_band
  - Precision/recall at risk >= 3 and >= 4
  - False alarm rate, ECE, reliability data
  - Risk distribution

- `model_registry` - Versioned model artifacts
  - Training context and metrics
  - Status workflow: candidate → challenger → incumbent → retired
  - Activation audit trail
  - Feature importance storage

- `active_learning_queue` - Uncertain cases needing review
  - Priority scored by uncertainty and learning value
  - Review workflow with assignment
  - Resolution tracking

- `label_matching_policies` - Versioned matching parameters
  - Spatial/temporal tolerances
  - Elevation band flexibility
  - Quality gates for event inclusion

**Edge Function**: `label-forecast-outcomes/index.ts`
- Matches forecast cells to verified events using configurable policy
- Computes label confidence based on distance, verification quality, elevation match
- Generates training-eligible vs excluded labels
- Supports batch processing of historical forecasts

**Edge Function**: `run-evaluation/index.ts`
- Calculates precision/recall/F1 at multiple risk thresholds
- Computes Expected Calibration Error (ECE)
- Stratifies metrics by region, season, elevation band
- False alarm rate analysis
- Stores results for model comparison

### Slice 4: Feature Enrichment Schema ✅ (This Session)

**Migration**: `20260414160000_feature_enrichment_schema.sql`

**New Tables**:
- `snow_cover_snapshots` - Lightweight snow summary (not raw raster)
  - Coverage ratio per region
  - Elevation band statistics
  - Source tracking (GIBS, MODIS, fallback)
  - Quality scores

- `recent_activity_features` - Materialized event summaries
  - Region-level and optional cell-level
  - Recency-weighted severity sums
  - Source breakdown
  - Aspect bucket coverage
  - Elevation range statistics

- `feature_completeness_log` - Audit trail per forecast
  - Which features were available
  - Data freshness tracking
  - Missing feature accounting

**Edge Function**: `ingest-snow-cover/index.ts`
- NASA GIBS integration for MODIS Terra daily snow cover
- Seasonal-adjusted fallback when API unavailable
- Elevation band summary generation
- Quality score assignment

**Edge Function**: `recent-activity-refresh/index.ts`
- Materializes event summaries by region and time window
- Recency-weighted severity calculation
- Optional cell-level materialization
- Source and aspect bucket tracking

### Slice 5: Calibration + Promotion Controls ✅ (This Session)

**Migration**: `20260414170000_calibration_profiles.sql`

**New Tables**:
- `calibration_profiles` - Per-region scoring adjustments
  - Feature weight scalars (snowfall, wind, elevation, etc.)
  - Uncertainty scaling parameters
  - Post-processing rules (min elevation for high risk, slope caps)
  - Status workflow: draft → approved → active → retired
  - Approval audit trail

- `threshold_profiles` - Risk band mapping
  - Explicit thresholds for risk 1-5 bands
  - Alert threshold configuration
  - Calibration method tracking
  - Expected performance metrics

- `promotion_events` - Audit log
  - What was promoted (model, profile, thresholds)
  - Evidence (evaluation run, metrics)
  - Decision and reasoning
  - Automatic vs manual flag

- `rollback_state` - Emergency recovery snapshots
  - Current working configuration versions
  - Performance at snapshot time
  - Rollback triggers

### Slice 6: Learning Loop (Partial - Infrastructure Only) ✅ (This Session)

**Infrastructure Created**:
- Model registry with candidate/incumbent tracking
- Active learning queue schema
- Retraining job type in trigger-job

**Not Yet Implemented** (requires external compute):
- Actual external training pipeline
- Active learning prioritization algorithm
- Human review UI workflow

## Admin Dashboard Updates ✅

**File**: `src/components/AdminDashboard.tsx`

**Changes**:
- Extended JobType enum with all new job types
- Added 10 job buttons with icons and descriptions:
  - Snow Cover (NASA GIBS)
  - Recent Activity (materialization)
  - Label Outcomes (forecast-to-event matching)
  - Run Evaluation (metrics by slice)
  - Normalize Reports (field report processing)
  - Retrain Model (external trigger)
  - Plus existing 4 jobs
- Updated trigger payload to include hazard_type and bbox
- Enhanced Model Status display with calibration/threshold versions

## Files Created

### Migrations
1. `20260414140000_avalanche_event_quality_schema.sql`
2. `20260414150000_forecast_outcome_labeling.sql`
3. `20260414160000_feature_enrichment_schema.sql`
4. `20260414170000_calibration_profiles.sql`

### Edge Functions
1. `supabase/functions/ingest-snow-cover/index.ts`
2. `supabase/functions/label-forecast-outcomes/index.ts`
3. `supabase/functions/run-evaluation/index.ts`
4. `supabase/functions/recent-activity-refresh/index.ts`

### Documentation
- `IMPLEMENTATION_SUMMARY.md` (this file)

## Next Steps for Full Activation

### 1. Apply Migrations
```bash
supabase db push
```

### 2. Regenerate Types
```bash
supabase gen types typescript --local > src/integrations/supabase/types.ts
```

### 3. Deploy Edge Functions
```bash
supabase functions deploy ingest-snow-cover
supabase functions deploy label-forecast-outcomes
supabase functions deploy run-evaluation
supabase functions deploy recent-activity-refresh
```

### 4. Seed Initial Data
```sql
-- Insert default calibration profile
INSERT INTO calibration_profiles (profile_version, region_name, description, status)
VALUES ('alps-v1.0', 'Alps', 'Initial Alps calibration', 'draft');

-- Insert default threshold profile
INSERT INTO threshold_profiles (profile_version, region_name, risk_1_max, risk_2_max, risk_3_max, risk_4_max, status)
VALUES ('alps-thresholds-v1', 'Alps', 0.15, 0.35, 0.55, 0.75, 'draft');
```

### 5. Configure Cron Jobs
Add to `supabase/config.toml` or use pg_cron:
```sql
-- Daily snow cover refresh
SELECT cron.schedule('snow-cover-daily', '0 6 * * *', 
  $$SELECT net.http_post(url:='https://project-ref.supabase.co/functions/v1/ingest-snow-cover', body:='{"region_name": "global"}'::jsonb)$$);

-- Weekly recent activity materialization
SELECT cron.schedule('activity-weekly', '0 7 * * 1',
  $$SELECT net.http_post(url:='https://project-ref.supabase.co/functions/v1/recent-activity-refresh', body:='{"window_days": 7}'::jsonb)$$);

-- Daily forecast labeling
SELECT cron.schedule('labeling-daily', '0 2 * * *',
  $$SELECT net.http_post(url:='https://project-ref.supabase.co/functions/v1/label-forecast-outcomes', body:='{"days_back": 1}'::jsonb)$$);

-- Weekly evaluation
SELECT cron.schedule('evaluation-weekly', '0 3 * * 1',
  $$SELECT net.http_post(url:='https://project-ref.supabase.co/functions/v1/run-evaluation', body:='{"days_back": 7}'::jsonb)$$);
```

### 6. External Training Pipeline (Slice 6 Completion)
Set up scheduled external compute (GitHub Actions / AWS Lambda) that:
1. Reads approved training set from `forecast_outcomes`
2. Trains new model candidate
3. Writes to `model_registry` as 'candidate'
4. Triggers evaluation run
5. On metric improvement, promotes to 'challenger' then 'incumbent'

## Verification Checklist

- [ ] Migrations apply without errors
- [ ] New tables appear in Supabase Studio
- [ ] Edge Functions deploy successfully
- [ ] `ingest-snow-cover` creates snapshot records
- [ ] `recent-activity-refresh` materializes features
- [ ] `label-forecast-outcomes` matches forecasts to events
- [ ] `run-evaluation` produces slice metrics
- [ ] Admin Dashboard shows new job buttons
- [ ] Model status displays calibration/threshold versions
- [ ] Cron jobs scheduled and running

## Accuracy Roadmap Progress

| Slice | Status | Target Accuracy Impact |
|-------|--------|------------------------|
| 1. Governance + Lineage | ✅ Complete | Foundation for reproducibility |
| 2. Event/Report Quality | ✅ Complete | Better training signal |
| 3. Outcome Labeling + Evaluation | ✅ Complete | Measurable improvement tracking |
| 4. Feature Enrichment | ✅ Complete | Snow cover + activity signals |
| 5. Calibration + Promotion | ✅ Complete | Regional accuracy tuning |
| 6. Learning Loop | 🔄 Partial | Infrastructure ready, external training pending |

**Estimated Accuracy Impact**: Foundation for achieving 4.5/5 when Slice 6 completes and sufficient labeled data accumulates.
