-- Materialization trigger for reviewed shadow training candidates.
-- Split from 20260714170000 to isolate the complex CASE expressions.
-- All CASE...END blocks are parenthesized to avoid PostgreSQL parser ambiguity.

CREATE OR REPLACE FUNCTION public.materialize_reviewed_shadow_training_candidate()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
DECLARE
  replay jsonb;
  required_reviewer_count integer;
  review_count integer;
  distinct_reviewer_count integer;
  distinct_verdict_count integer;
  review_verdicts_valid boolean;
  labels_reliable boolean;
  model_verdicts_valid boolean;
  no_claim_block boolean;
  review_ids uuid[];
  review_summary jsonb;
  combined_case_payload text;
BEGIN
  IF TG_OP <> 'UPDATE'
    OR OLD.status = 'reviewed'
    OR NEW.status <> 'reviewed'
    OR NEW.case_origin <> 'forecast_publication'
    OR NEW.forecast_run_id IS NULL
    OR NEW.region_key IS NULL
    OR btrim(NEW.region_key) = ''
    OR NEW.cell_row IS NULL
    OR NEW.cell_col IS NULL THEN
    RETURN NEW;
  END IF;

  replay := COALESCE(NEW.cell_snapshot -> 'evidence_replay', NEW.evidence -> 'evidence_replay');
  IF replay IS NULL
    OR jsonb_typeof(replay #> '{forecast}') IS DISTINCT FROM 'object'
    OR jsonb_typeof(replay #> '{forecast,forecast_run_id}') IS DISTINCT FROM 'string'
    OR btrim(COALESCE(replay #>> '{forecast,forecast_run_id}', '')) = ''
    OR jsonb_typeof(replay #> '{forecast,region_key}') IS DISTINCT FROM 'string'
    OR btrim(COALESCE(replay #>> '{forecast,region_key}', '')) = ''
    OR replay #>> '{forecast,forecast_run_id}' IS DISTINCT FROM NEW.forecast_run_id::text
    OR replay #>> '{forecast,region_key}' IS DISTINCT FROM NEW.region_key
    OR jsonb_typeof(replay #> '{forecast,cell_row}') IS DISTINCT FROM 'number'
    OR replay #>> '{forecast,cell_row}' !~ '^-?[0-9]+$'
    OR jsonb_typeof(replay #> '{forecast,cell_col}') IS DISTINCT FROM 'number'
    OR replay #>> '{forecast,cell_col}' !~ '^-?[0-9]+$'
    OR replay #>> '{forecast,cell_row}' IS DISTINCT FROM NEW.cell_row::text
    OR replay #>> '{forecast,cell_col}' IS DISTINCT FROM NEW.cell_col::text
    OR NOT ((replay #> '{forecast}') ? 'forecast_grid_id')
    OR replay #>> '{forecast,valid_time_utc}' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?Z$'
    OR jsonb_typeof(replay #> '{alignment,grid}') IS DISTINCT FROM 'object'
    OR NOT ((replay #> '{alignment,grid}') ? 'forecast_grid_id')
    OR (
      jsonb_typeof(replay #> '{forecast,forecast_grid_id}') IS DISTINCT FROM 'string'
      AND jsonb_typeof(replay #> '{forecast,forecast_grid_id}') IS DISTINCT FROM 'null'
    )
    OR (
      jsonb_typeof(replay #> '{alignment,grid,forecast_grid_id}') IS DISTINCT FROM 'string'
      AND jsonb_typeof(replay #> '{alignment,grid,forecast_grid_id}') IS DISTINCT FROM 'null'
    )
    OR replay #>> '{alignment,grid,forecast_grid_id}' IS DISTINCT FROM replay #>> '{forecast,forecast_grid_id}'
    OR jsonb_typeof(replay #> '{alignment,grid,cell_row}') IS DISTINCT FROM 'number'
    OR replay #>> '{alignment,grid,cell_row}' !~ '^-?[0-9]+$'
    OR jsonb_typeof(replay #> '{alignment,grid,cell_col}') IS DISTINCT FROM 'number'
    OR replay #>> '{alignment,grid,cell_col}' !~ '^-?[0-9]+$'
    OR replay #>> '{alignment,grid,cell_row}' IS DISTINCT FROM replay #>> '{forecast,cell_row}'
    OR replay #>> '{alignment,grid,cell_col}' IS DISTINCT FROM replay #>> '{forecast,cell_col}'
    OR replay #>> '{alignment,time,forecast_valid_time_utc}' IS DISTINCT FROM replay #>> '{forecast,valid_time_utc}'
    OR replay #>> '{observed,status}' IS DISTINCT FROM 'available'
    OR replay #>> '{observed,synthetic_evidence_status}' IS DISTINCT FROM 'false'
    OR replay #>> '{provenance,provenance_complete}' IS DISTINCT FROM 'true'
    OR replay #>> '{provenance,lineage_verified}' IS DISTINCT FROM 'true'
    OR replay #>> '{provenance,source_hashes_present}' IS DISTINCT FROM 'true'
    OR replay #>> '{provenance,evidence_refs_present}' IS DISTINCT FROM 'true'
    OR replay #>> '{provenance,baseline_ids_present}' IS DISTINCT FROM 'true'
    OR jsonb_typeof(replay #> '{raw_layers,feature_values}') IS DISTINCT FROM 'object'
    OR replay #> '{raw_layers,feature_values}' = '{}'::jsonb
    OR jsonb_typeof(replay #> '{lineage,source_hashes}') IS DISTINCT FROM 'object'
    OR replay #> '{lineage,source_hashes}' = '{}'::jsonb
    OR (CASE
      WHEN jsonb_typeof(replay #> '{lineage,source_hashes}') = 'object'
        THEN EXISTS (
          SELECT 1
          FROM jsonb_each_text(replay #> '{lineage,source_hashes}') AS source_hash(source_key, source_value)
          WHERE btrim(source_key) = '' OR source_value !~ '^[0-9a-f]{64}$'
        )
      ELSE TRUE
    END)
    OR (CASE
      WHEN jsonb_typeof(replay #> '{lineage,evidence_refs}') = 'array'
        THEN jsonb_array_length(replay #> '{lineage,evidence_refs}')
      ELSE 0
    END) = 0
    OR (CASE
      WHEN jsonb_typeof(replay #> '{lineage,baseline_ids}') = 'array'
        THEN jsonb_array_length(replay #> '{lineage,baseline_ids}')
      ELSE 0
    END) = 0
    OR (CASE
      WHEN jsonb_typeof(replay #> '{lineage,evidence_refs}') = 'array'
        THEN EXISTS (
          SELECT 1
          FROM jsonb_array_elements_text(replay #> '{lineage,evidence_refs}') AS evidence_ref(value)
          WHERE btrim(value) = ''
        )
      ELSE TRUE
    END)
    OR (CASE
      WHEN jsonb_typeof(replay #> '{lineage,baseline_ids}') = 'array'
        THEN EXISTS (
          SELECT 1
          FROM jsonb_array_elements_text(replay #> '{lineage,baseline_ids}') AS baseline_id(value)
          WHERE btrim(value) = ''
        )
      ELSE TRUE
    END)
    OR jsonb_typeof(replay #> '{alignment,time,observation_times_utc}') IS DISTINCT FROM 'array'
    OR (CASE
      WHEN jsonb_typeof(replay #> '{alignment,time,observation_times_utc}') = 'array'
        THEN jsonb_array_length(replay #> '{alignment,time,observation_times_utc}') = 0
      ELSE TRUE
    END)
    OR (CASE
      WHEN jsonb_typeof(replay #> '{alignment,time,observation_times_utc}') = 'array'
        THEN EXISTS (
          SELECT 1
          FROM jsonb_array_elements_text(replay #> '{alignment,time,observation_times_utc}') AS observation_time(value)
          WHERE btrim(value) = ''
            OR value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?Z$'
        )
      ELSE TRUE
    END)
    OR jsonb_typeof(replay #> '{alignment,time,source_freshness_hours}') IS DISTINCT FROM 'object'
    OR replay #> '{alignment,time,source_freshness_hours}' = '{}'::jsonb
    OR (CASE
      WHEN jsonb_typeof(replay #> '{alignment,time,source_freshness_hours}') = 'object'
        THEN EXISTS (
          SELECT 1
          FROM jsonb_each_text(replay #> '{alignment,time,source_freshness_hours}') AS freshness(source_key, source_value)
          WHERE btrim(source_key) = ''
            OR source_value !~ '^(0|[0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        )
      ELSE TRUE
    END)
    OR COALESCE(replay ->> 'feature_snapshot_sha256', '') !~ '^[0-9a-f]{64}$'
    OR COALESCE(replay ->> 'replay_snapshot_sha256', '') !~ '^[0-9a-f]{64}$' THEN
    RETURN NEW;
  END IF;

  combined_case_payload := concat_ws(
    ' ',
    COALESCE(NEW.evidence::text, ''),
    COALESCE(NEW.cell_snapshot::text, ''),
    COALESCE(NEW.model_metadata::text, '')
  );
  IF combined_case_payload ~* 'synthetic_scenario|machine_extracted_news_unreviewed'
    OR combined_case_payload ~* '"auto_label"[[:space:]]*:'
    OR combined_case_payload ~* '"auto_labeled"[[:space:]]*:'
    OR combined_case_payload ~* '"auto_labelled"[[:space:]]*:'
    OR combined_case_payload ~* '"auto_generated"[[:space:]]*:'
    OR combined_case_payload ~* '"synthetic_demo"[[:space:]]*:[[:space:]]*true'
    OR combined_case_payload ~* '"synthetic_inputs_present"[[:space:]]*:[[:space:]]*true'
    OR combined_case_payload ~* '"has_synthetic_evidence"[[:space:]]*:[[:space:]]*true'
    OR combined_case_payload ~* '"synthetic"[[:space:]]*:[[:space:]]*true' THEN
    RETURN NEW;
  END IF;

  required_reviewer_count := CASE
    WHEN NEW.requires_two_reviewers OR NEW.priority >= 5 THEN 2
    ELSE 1
  END;

  SELECT
    COUNT(*),
    COUNT(DISTINCT reviewer_id) FILTER (WHERE reviewer_id IS NOT NULL),
    COUNT(DISTINCT verdict),
    COALESCE(bool_and(verdict IN ('accepted', 'rejected')), false),
    COALESCE(bool_and(label_quality_verdict = 'label_reliable'), false),
    COALESCE(bool_and(model_error_verdict IN (
      'model_plausible',
      'model_false_positive',
      'model_false_negative',
      'model_miscalibrated'
    )), false),
    COALESCE(bool_and(claim_impact <> 'block'), false),
    COALESCE(array_agg(id ORDER BY created_at), ARRAY[]::uuid[]),
    COALESCE(jsonb_agg(jsonb_build_object(
      'reviewer_id', reviewer_id,
      'verdict', verdict,
      'label_quality_verdict', label_quality_verdict,
      'model_error_verdict', model_error_verdict
    ) ORDER BY created_at), '[]'::jsonb)
  INTO
    review_count,
    distinct_reviewer_count,
    distinct_verdict_count,
    review_verdicts_valid,
    labels_reliable,
    model_verdicts_valid,
    no_claim_block,
    review_ids,
    review_summary
  FROM public.scientist_validation_reviews
  WHERE case_id = NEW.id;

  IF review_count < required_reviewer_count
    OR distinct_reviewer_count < required_reviewer_count
    OR distinct_verdict_count <> 1
    OR NOT review_verdicts_valid
    OR NOT labels_reliable
    OR NOT model_verdicts_valid
    OR NOT no_claim_block THEN
    RETURN NEW;
  END IF;

  INSERT INTO public.reviewed_shadow_training_candidates (
    case_id,
    forecast_run_id,
    region_key,
    cell_row,
    cell_col,
    feature_snapshot_sha256,
    evidence_replay_sha256,
    feature_snapshot,
    evidence_lineage,
    review_ids,
    review_summary,
    training_status,
    production_eligible,
    claim_boundary
  ) VALUES (
    NEW.id,
    NEW.forecast_run_id,
    NEW.region_key,
    NEW.cell_row,
    NEW.cell_col,
    replay ->> 'feature_snapshot_sha256',
    replay ->> 'replay_snapshot_sha256',
    replay #> '{raw_layers,feature_values}',
    replay -> 'lineage',
    review_ids,
    review_summary,
    'shadow_only',
    false,
    'reviewed_shadow_candidate_not_training_or_public_promotion'
  ) ON CONFLICT (case_id) DO NOTHING;

  RETURN NEW;
END;
$func$;

DROP TRIGGER IF EXISTS trg_materialize_reviewed_shadow_training_candidate
  ON public.scientist_validation_cases;
CREATE TRIGGER trg_materialize_reviewed_shadow_training_candidate
  AFTER UPDATE OF status ON public.scientist_validation_cases
  FOR EACH ROW
  EXECUTE FUNCTION public.materialize_reviewed_shadow_training_candidate();
