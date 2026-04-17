export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      avalanche_events: {
        Row: {
          confidence: number | null
          created_at: string
          description: string | null
          event_type: Database["public"]["Enums"]["event_type"] | null
          features: Json | null
          fusion_source: string | null
          id: string
          location: unknown
          aspect_deg: number | null
          elevation_m: number | null
          severity: number | null
          source: string | null
          slope_angle_deg: number | null
          aspect_bucket: string | null
          slope_band: string | null
          topo_profile: Json | null
          topo_resolution_m: number | null
          topo_source: string | null
          timestamp: string
        }
        Insert: {
          confidence?: number | null
          created_at?: string
          description?: string | null
          event_type?: Database["public"]["Enums"]["event_type"] | null
          features?: Json | null
          fusion_source?: string | null
          id?: string
          location?: unknown
          aspect_deg?: number | null
          elevation_m?: number | null
          severity?: number | null
          source?: string | null
          slope_angle_deg?: number | null
          aspect_bucket?: string | null
          slope_band?: string | null
          topo_profile?: Json | null
          topo_resolution_m?: number | null
          topo_source?: string | null
          timestamp?: string
        }
        Update: {
          confidence?: number | null
          created_at?: string
          description?: string | null
          event_type?: Database["public"]["Enums"]["event_type"] | null
          features?: Json | null
          fusion_source?: string | null
          id?: string
          location?: unknown
          aspect_deg?: number | null
          elevation_m?: number | null
          severity?: number | null
          source?: string | null
          slope_angle_deg?: number | null
          aspect_bucket?: string | null
          slope_band?: string | null
          topo_profile?: Json | null
          topo_resolution_m?: number | null
          topo_source?: string | null
          timestamp?: string
        }
        Relationships: []
      }
      compute_jobs: {
        Row: {
          bbox: number[] | null
          created_at: string
          error: string | null
          id: string
          payload: Json | null
          result: Json | null
          status: Database["public"]["Enums"]["job_status"]
          time_offset: number | null
          type: Database["public"]["Enums"]["job_type"]
          updated_at: string
        }
        Insert: {
          bbox?: number[] | null
          created_at?: string
          error?: string | null
          id?: string
          payload?: Json | null
          result?: Json | null
          status?: Database["public"]["Enums"]["job_status"]
          time_offset?: number | null
          type: Database["public"]["Enums"]["job_type"]
          updated_at?: string
        }
        Update: {
          bbox?: number[] | null
          created_at?: string
          error?: string | null
          id?: string
          payload?: Json | null
          result?: Json | null
          status?: Database["public"]["Enums"]["job_status"]
          time_offset?: number | null
          type?: Database["public"]["Enums"]["job_type"]
          updated_at?: string
        }
        Relationships: []
      }
      forecast_analytics: {
        Row: {
          avg_risk: number | null
          bbox: number[] | null
          cell_count: number | null
          created_at: string
          id: string
          region_name: string | null
          weather_source: string | null
        }
        Insert: {
          avg_risk?: number | null
          bbox?: number[] | null
          cell_count?: number | null
          created_at?: string
          id?: string
          region_name?: string | null
          weather_source?: string | null
        }
        Update: {
          avg_risk?: number | null
          bbox?: number[] | null
          cell_count?: number | null
          created_at?: string
          id?: string
          region_name?: string | null
          weather_source?: string | null
        }
        Relationships: []
      }
      forecasts: {
        Row: {
          bbox: number[] | null
          created_at: string
          exposure: number | null
          grid_data: Json | null
          hazard: number | null
          hourly_grids: Json | null
          id: string
          job_id: string | null
          problem_type: string | null
          risk_score: number | null
          shap_values: Json | null
          timestamp: string
          vulnerability: number | null
        }
        Insert: {
          bbox?: number[] | null
          created_at?: string
          exposure?: number | null
          grid_data?: Json | null
          hazard?: number | null
          hourly_grids?: Json | null
          id?: string
          job_id?: string | null
          problem_type?: string | null
          risk_score?: number | null
          shap_values?: Json | null
          timestamp?: string
          vulnerability?: number | null
        }
        Update: {
          bbox?: number[] | null
          created_at?: string
          exposure?: number | null
          grid_data?: Json | null
          hazard?: number | null
          hourly_grids?: Json | null
          id?: string
          job_id?: string | null
          problem_type?: string | null
          risk_score?: number | null
          shap_values?: Json | null
          timestamp?: string
          vulnerability?: number | null
        }
        Relationships: []
      }
      forecast_grids: {
        Row: {
          bbox: number[]
          created_at: string
          forecast_date: string
          grid_geojson: Json
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          horizon_hours: number
          id: string
          model_metadata: Json
          region_key: string
          region_name: string
          runout_polygons: Json
          source_job_id: string | null
          status: string
          updated_at: string
          weather_summary: Json
        }
        Insert: {
          bbox: number[]
          created_at?: string
          forecast_date: string
          grid_geojson?: Json
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          horizon_hours?: number
          id?: string
          model_metadata?: Json
          region_key: string
          region_name: string
          runout_polygons?: Json
          source_job_id?: string | null
          status?: string
          updated_at?: string
          weather_summary?: Json
        }
        Update: {
          bbox?: number[]
          created_at?: string
          forecast_date?: string
          grid_geojson?: Json
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          horizon_hours?: number
          id?: string
          model_metadata?: Json
          region_key?: string
          region_name?: string
          runout_polygons?: Json
          source_job_id?: string | null
          status?: string
          updated_at?: string
          weather_summary?: Json
        }
        Relationships: []
      }
      model_status: {
        Row: {
          data_freshness_hours: number | null
          f1_score: number | null
          id: string
          last_inference: string | null
          last_trained: string | null
          next_run: string | null
          version: string | null
        }
        Insert: {
          data_freshness_hours?: number | null
          f1_score?: number | null
          id?: string
          last_inference?: string | null
          last_trained?: string | null
          next_run?: string | null
          version?: string | null
        }
        Update: {
          data_freshness_hours?: number | null
          f1_score?: number | null
          id?: string
          last_inference?: string | null
          last_trained?: string | null
          next_run?: string | null
          version?: string | null
        }
        Relationships: []
      }
      mountain_terrain: {
        Row: {
          aspect: number
          created_at: string
          curvature: number
          elevation: number
          id: string
          lat: number
          lng: number
          slope_angle: number
          tpi: number
          twi: number
        }
        Insert: {
          aspect?: number
          created_at?: string
          curvature?: number
          elevation?: number
          id?: string
          lat: number
          lng: number
          slope_angle?: number
          tpi?: number
          twi?: number
        }
        Update: {
          aspect?: number
          created_at?: string
          curvature?: number
          elevation?: number
          id?: string
          lat?: number
          lng?: number
          slope_angle?: number
          tpi?: number
          twi?: number
        }
        Relationships: []
      }
      system_config: {
        Row: {
          gemini_spend_cap: number | null
          gemini_usage: number | null
          id: string
          last_enrichment: string | null
        }
        Insert: {
          gemini_spend_cap?: number | null
          gemini_usage?: number | null
          id?: string
          last_enrichment?: string | null
        }
        Update: {
          gemini_spend_cap?: number | null
          gemini_usage?: number | null
          id?: string
          last_enrichment?: string | null
        }
        Relationships: []
      }
      user_alerts: {
        Row: {
          auth_key: string
          created_at: string
          endpoint: string
          id: string
          p256dh: string
          region_bbox: number[] | null
        }
        Insert: {
          auth_key: string
          created_at?: string
          endpoint: string
          id?: string
          p256dh: string
          region_bbox?: number[] | null
        }
        Update: {
          auth_key?: string
          created_at?: string
          endpoint?: string
          id?: string
          p256dh?: string
          region_bbox?: number[] | null
        }
        Relationships: []
      }
      field_reports: {
        Row: {
          aspect: string | null
          confidence: number | null
          created_at: string
          dedupe_group_id: string | null
          description: string | null
          elevation_m: number | null
          hazard_type: string
          id: string
          image_url: string | null
          location: unknown
          location_precision_m: number | null
          normalization_version: string | null
          normalized_event_type: string | null
          normalized_severity: string | null
          reporter_reliability_score: number | null
          reviewed_at: string | null
          reviewed_by: string | null
          review_status: string
          snow_description: string | null
          status: string | null
          terrain_context: string | null
          timestamp: string
          training_eligible: boolean
          trigger_type: string | null
          user_id: string | null
        }
        Insert: {
          aspect?: string | null
          confidence?: number | null
          created_at?: string
          dedupe_group_id?: string | null
          description?: string | null
          elevation_m?: number | null
          hazard_type?: string
          id?: string
          image_url?: string | null
          location?: unknown
          location_precision_m?: number | null
          normalization_version?: string | null
          normalized_event_type?: string | null
          normalized_severity?: string | null
          reporter_reliability_score?: number | null
          reviewed_at?: string | null
          reviewed_by?: string | null
          review_status?: string
          snow_description?: string | null
          status?: string | null
          terrain_context?: string | null
          timestamp?: string
          training_eligible?: boolean
          trigger_type?: string | null
          user_id?: string | null
        }
        Update: {
          aspect?: string | null
          confidence?: number | null
          created_at?: string
          dedupe_group_id?: string | null
          description?: string | null
          elevation_m?: number | null
          hazard_type?: string
          id?: string
          image_url?: string | null
          location?: unknown
          location_precision_m?: number | null
          normalization_version?: string | null
          normalized_event_type?: string | null
          normalized_severity?: string | null
          reporter_reliability_score?: number | null
          reviewed_at?: string | null
          reviewed_by?: string | null
          review_status?: string
          snow_description?: string | null
          status?: string | null
          terrain_context?: string | null
          timestamp?: string
          training_eligible?: boolean
          trigger_type?: string | null
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "field_reports_reviewed_by_fkey"
            columns: ["reviewed_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      forecast_outcomes: {
        Row: {
          created_at: string
          distance_to_nearest_event_m: number | null
          elevation_band_compatible: boolean | null
          event_observed: boolean
          excluded_from_training: boolean
          forecast_hour: number
          forecast_id: string
          hazard_type: string
          id: string
          label_confidence: number
          label_version: string
          nearest_event_id: string | null
          outcome_window_end: string
          outcome_window_start: string
          predicted_hazard: number
          predicted_risk_score: number
          severity_label: string | null
          spatial_tolerance_m: number
          temporal_tolerance_hours: number
          updated_at: string
          cell_col: number
          cell_row: number
          exclusion_reason: string | null
        }
        Insert: {
          created_at?: string
          distance_to_nearest_event_m?: number | null
          elevation_band_compatible?: boolean | null
          event_observed?: boolean
          excluded_from_training?: boolean
          forecast_hour: number
          forecast_id: string
          hazard_type?: string
          id?: string
          label_confidence?: number
          label_version?: string
          nearest_event_id?: string | null
          outcome_window_end: string
          outcome_window_start: string
          predicted_hazard: number
          predicted_risk_score: number
          severity_label?: string | null
          spatial_tolerance_m?: number
          temporal_tolerance_hours?: number
          updated_at?: string
          cell_col: number
          cell_row: number
          exclusion_reason?: string | null
        }
        Update: {
          created_at?: string
          distance_to_nearest_event_m?: number | null
          elevation_band_compatible?: boolean | null
          event_observed?: boolean
          excluded_from_training?: boolean
          forecast_hour?: number
          forecast_id?: string
          hazard_type?: string
          id?: string
          label_confidence?: number
          label_version?: string
          nearest_event_id?: string | null
          outcome_window_end?: string
          outcome_window_start?: string
          predicted_hazard?: number
          predicted_risk_score?: number
          severity_label?: string | null
          spatial_tolerance_m?: number
          temporal_tolerance_hours?: number
          updated_at?: string
          cell_col?: number
          cell_row?: number
          exclusion_reason?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "forecast_outcomes_forecast_id_fkey"
            columns: ["forecast_id"]
            isOneToOne: false
            referencedRelation: "forecasts"
            referencedColumns: ["id"]
          },
        ]
      }
      evaluation_runs: {
        Row: {
          completed_at: string | null
          created_at: string
          error_message: string | null
          hazard_type: string
          id: string
          label_version: string
          model_version: string
          overall_brier_score: number | null
          overall_ece: number | null
          overall_false_alarm_rate: number | null
          overall_precision_risk3: number | null
          overall_precision_risk4: number | null
          overall_recall: number | null
          regions_evaluated: string[]
          run_name: string
          status: string
          threshold_profile_version: string
          eval_end_date: string
          eval_start_date: string
        }
        Insert: {
          completed_at?: string | null
          created_at?: string
          error_message?: string | null
          hazard_type?: string
          id?: string
          label_version: string
          model_version: string
          overall_brier_score?: number | null
          overall_ece?: number | null
          overall_false_alarm_rate?: number | null
          overall_precision_risk3?: number | null
          overall_precision_risk4?: number | null
          overall_recall?: number | null
          regions_evaluated?: string[]
          run_name: string
          status?: string
          threshold_profile_version: string
          eval_end_date: string
          eval_start_date: string
        }
        Update: {
          completed_at?: string | null
          created_at?: string
          error_message?: string | null
          hazard_type?: string
          id?: string
          label_version?: string
          model_version?: string
          overall_brier_score?: number | null
          overall_ece?: number | null
          overall_false_alarm_rate?: number | null
          overall_precision_risk3?: number | null
          overall_precision_risk4?: number | null
          overall_recall?: number | null
          regions_evaluated?: string[]
          run_name?: string
          status?: string
          threshold_profile_version?: string
          eval_end_date?: string
          eval_start_date?: string
        }
        Relationships: []
      }
      evaluation_metrics: {
        Row: {
          created_at: string
          ece: number | null
          evaluation_run_id: string
          false_alarm_rate: number | null
          false_positives: number | null
          f1_risk3: number | null
          f1_risk4: number | null
          id: string
          observed_events: number
          precision_risk3: number | null
          precision_risk4: number | null
          recall_risk3: number | null
          recall_risk4: number | null
          risk_distribution: Json | null
          slice_type: string
          slice_value: string
          total_cells: number
          total_forecasts: number
          true_positives: number | null
          reliability_data: Json | null
        }
        Insert: {
          created_at?: string
          ece?: number | null
          evaluation_run_id: string
          false_alarm_rate?: number | null
          false_positives?: number | null
          f1_risk3?: number | null
          f1_risk4?: number | null
          id?: string
          observed_events: number
          precision_risk3?: number | null
          precision_risk4?: number | null
          recall_risk3?: number | null
          recall_risk4?: number | null
          risk_distribution?: Json | null
          slice_type: string
          slice_value: string
          total_cells: number
          total_forecasts: number
          true_positives?: number | null
          reliability_data?: Json | null
        }
        Update: {
          created_at?: string
          ece?: number | null
          evaluation_run_id?: string
          false_alarm_rate?: number | null
          false_positives?: number | null
          f1_risk3?: number | null
          f1_risk4?: number | null
          id?: string
          observed_events?: number
          precision_risk3?: number | null
          precision_risk4?: number | null
          recall_risk3?: number | null
          recall_risk4?: number | null
          risk_distribution?: Json | null
          slice_type?: string
          slice_value?: string
          total_cells?: number
          total_forecasts?: number
          true_positives?: number | null
          reliability_data?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "evaluation_metrics_evaluation_run_id_fkey"
            columns: ["evaluation_run_id"]
            isOneToOne: false
            referencedRelation: "evaluation_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      snow_cover_snapshots: {
        Row: {
          bbox: number[]
          captured_at: string
          created_at: string
          coverage_ratio: number | null
          elevation_band_stats: Json
          id: string
          ingestion_job_id: string | null
          processing_version: string
          quality_score: number | null
          source: string
          source_layer: string | null
          source_url: string | null
          valid_for_region: string
        }
        Insert: {
          bbox: number[]
          captured_at: string
          created_at?: string
          coverage_ratio?: number | null
          elevation_band_stats?: Json
          id?: string
          ingestion_job_id?: string | null
          processing_version?: string
          quality_score?: number | null
          source?: string
          source_layer?: string | null
          source_url?: string | null
          valid_for_region: string
        }
        Update: {
          bbox?: number[]
          captured_at?: string
          created_at?: string
          coverage_ratio?: number | null
          elevation_band_stats?: Json
          id?: string
          ingestion_job_id?: string | null
          processing_version?: string
          quality_score?: number | null
          source?: string
          source_layer?: string | null
          source_url?: string | null
          valid_for_region?: string
        }
        Relationships: [
          {
            foreignKeyName: "snow_cover_snapshots_ingestion_job_id_fkey"
            columns: ["ingestion_job_id"]
            isOneToOne: false
            referencedRelation: "compute_jobs"
            referencedColumns: ["id"]
          },
        ]
      }
      recent_activity_features: {
        Row: {
          cell_col: number | null
          cell_row: number | null
          data_completeness_score: number
          elevation_range_m: Json | null
          id: string
          materialization_job_id: string | null
          materialized_at: string
          region_name: string
          sources: Json
          total_event_count: number
          training_eligible_count: number
          unique_aspect_buckets: string[] | null
          verified_event_count: number
          weighted_severity_sum: number
          window_days: number
          window_end: string
          window_start: string
          event_density_per_km2: number | null
          max_severity_in_window: number | null
        }
        Insert: {
          cell_col?: number | null
          cell_row?: number | null
          data_completeness_score?: number
          elevation_range_m?: Json | null
          id?: string
          materialization_job_id?: string | null
          materialized_at?: string
          region_name: string
          sources?: Json
          total_event_count?: number
          training_eligible_count?: number
          unique_aspect_buckets?: string[] | null
          verified_event_count?: number
          weighted_severity_sum?: number
          window_days?: number
          window_end: string
          window_start: string
          event_density_per_km2?: number | null
          max_severity_in_window?: number | null
        }
        Update: {
          cell_col?: number | null
          cell_row?: number | null
          data_completeness_score?: number
          elevation_range_m?: Json | null
          id?: string
          materialization_job_id?: string | null
          materialized_at?: string
          region_name?: string
          sources?: Json
          total_event_count?: number
          training_eligible_count?: number
          unique_aspect_buckets?: string[] | null
          verified_event_count?: number
          weighted_severity_sum?: number
          window_days?: number
          window_end?: string
          window_start?: string
          event_density_per_km2?: number | null
          max_severity_in_window?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "recent_activity_features_materialization_job_id_fkey"
            columns: ["materialization_job_id"]
            isOneToOne: false
            referencedRelation: "compute_jobs"
            referencedColumns: ["id"]
          },
        ]
      }
      feature_completeness_log: {
        Row: {
          forecast_id: string
          id: string
          logged_at: string
          missing_features: string[]
          overall_completeness: number
          recent_activity_available: boolean
          recent_activity_feature_id: string | null
          recent_activity_window_days: number | null
          snow_cover_age_hours: number | null
          snow_cover_available: boolean
          snow_cover_snapshot_id: string | null
          terrain_available: boolean
          weather_available: boolean
          weather_freshness_hours: number | null
          weather_source: string | null
        }
        Insert: {
          forecast_id: string
          id?: string
          logged_at?: string
          missing_features?: string[]
          overall_completeness: number
          recent_activity_available?: boolean
          recent_activity_feature_id?: string | null
          recent_activity_window_days?: number | null
          snow_cover_age_hours?: number | null
          snow_cover_available?: boolean
          snow_cover_snapshot_id?: string | null
          terrain_available?: boolean
          weather_available?: boolean
          weather_freshness_hours?: number | null
          weather_source?: string | null
        }
        Update: {
          forecast_id?: string
          id?: string
          logged_at?: string
          missing_features?: string[]
          overall_completeness?: number
          recent_activity_available?: boolean
          recent_activity_feature_id?: string | null
          recent_activity_window_days?: number | null
          snow_cover_age_hours?: number | null
          snow_cover_available?: boolean
          snow_cover_snapshot_id?: string | null
          terrain_available?: boolean
          weather_available?: boolean
          weather_freshness_hours?: number | null
          weather_source?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "feature_completeness_log_forecast_id_fkey"
            columns: ["forecast_id"]
            isOneToOne: false
            referencedRelation: "forecasts"
            referencedColumns: ["id"]
          },
        ]
      }
      calibration_profiles: {
        Row: {
          approved_at: string | null
          approved_by: string | null
          created_at: string
          description: string | null
          feature_scalars: Json
          hazard_type: string
          id: string
          post_processing_rules: Json
          profile_version: string
          region_name: string
          season_window: string | null
          status: string
          trained_on_evaluation_run_id: string | null
          uncertainty_base: number
          uncertainty_per_missing_feature: number
          updated_at: string
        }
        Insert: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          description?: string | null
          feature_scalars?: Json
          hazard_type?: string
          id?: string
          post_processing_rules?: Json
          profile_version: string
          region_name: string
          season_window?: string | null
          status?: string
          trained_on_evaluation_run_id?: string | null
          uncertainty_base?: number
          uncertainty_per_missing_feature?: number
          updated_at?: string
        }
        Update: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          description?: string | null
          feature_scalars?: Json
          hazard_type?: string
          id?: string
          post_processing_rules?: Json
          profile_version?: string
          region_name?: string
          season_window?: string | null
          status?: string
          trained_on_evaluation_run_id?: string | null
          uncertainty_base?: number
          uncertainty_per_missing_feature?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "calibration_profiles_trained_on_evaluation_run_id_fkey"
            columns: ["trained_on_evaluation_run_id"]
            isOneToOne: false
            referencedRelation: "evaluation_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      threshold_profiles: {
        Row: {
          alert_threshold_risk: number
          approved_at: string | null
          approved_by: string | null
          calibration_method: string
          created_at: string
          description: string | null
          derived_from_evaluation_run_id: string | null
          expected_false_alarm_rate: number | null
          expected_precision_risk3: number | null
          expected_recall_risk3: number | null
          hazard_type: string
          id: string
          profile_version: string
          region_name: string
          risk_1_max: number
          risk_2_max: number
          risk_3_max: number
          risk_4_max: number
          severe_alert_threshold_risk: number
          season_window: string | null
          status: string
          updated_at: string
        }
        Insert: {
          alert_threshold_risk?: number
          approved_at?: string | null
          approved_by?: string | null
          calibration_method?: string
          created_at?: string
          description?: string | null
          derived_from_evaluation_run_id?: string | null
          expected_false_alarm_rate?: number | null
          expected_precision_risk3?: number | null
          expected_recall_risk3?: number | null
          hazard_type?: string
          id?: string
          profile_version: string
          region_name?: string
          risk_1_max?: number
          risk_2_max?: number
          risk_3_max?: number
          risk_4_max?: number
          severe_alert_threshold_risk?: number
          season_window?: string | null
          status?: string
          updated_at?: string
        }
        Update: {
          alert_threshold_risk?: number
          approved_at?: string | null
          approved_by?: string | null
          calibration_method?: string
          created_at?: string
          description?: string | null
          derived_from_evaluation_run_id?: string | null
          expected_false_alarm_rate?: number | null
          expected_precision_risk3?: number | null
          expected_recall_risk3?: number | null
          hazard_type?: string
          id?: string
          profile_version?: string
          region_name?: string
          risk_1_max?: number
          risk_2_max?: number
          risk_3_max?: number
          risk_4_max?: number
          severe_alert_threshold_risk?: number
          season_window?: string | null
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "threshold_profiles_derived_from_evaluation_run_id_fkey"
            columns: ["derived_from_evaluation_run_id"]
            isOneToOne: false
            referencedRelation: "evaluation_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      promotion_events: {
        Row: {
          automatic: boolean
          created_at: string
          decision: string
          decision_reason: string | null
          decided_by: string | null
          event_type: string
          evaluation_run_id: string | null
          hazard_type: string
          id: string
          new_version: string
          previous_version: string | null
          region_name: string | null
          triggering_metrics: Json
        }
        Insert: {
          automatic?: boolean
          created_at?: string
          decision: string
          decision_reason?: string | null
          decided_by?: string | null
          event_type: string
          evaluation_run_id?: string | null
          hazard_type?: string
          id?: string
          new_version: string
          previous_version?: string | null
          region_name?: string | null
          triggering_metrics: Json
        }
        Update: {
          automatic?: boolean
          created_at?: string
          decision?: string
          decision_reason?: string | null
          decided_by?: string | null
          event_type?: string
          evaluation_run_id?: string | null
          hazard_type?: string
          id?: string
          new_version?: string
          previous_version?: string | null
          region_name?: string | null
          triggering_metrics?: Json
        }
        Relationships: [
          {
            foreignKeyName: "promotion_events_evaluation_run_id_fkey"
            columns: ["evaluation_run_id"]
            isOneToOne: false
            referencedRelation: "evaluation_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      rollback_state: {
        Row: {
          can_rollback_to: boolean
          calibration_profile_version: string | null
          created_at: string
          hazard_type: string
          id: string
          model_version: string | null
          region_name: string
          rolled_back_at: string | null
          rolled_back_by: string | null
          snapshot_metrics: Json | null
          threshold_profile_version: string | null
        }
        Insert: {
          can_rollback_to?: boolean
          calibration_profile_version?: string | null
          created_at?: string
          hazard_type?: string
          id?: string
          model_version?: string | null
          region_name?: string
          rolled_back_at?: string | null
          rolled_back_by?: string | null
          snapshot_metrics?: Json | null
          threshold_profile_version?: string | null
        }
        Update: {
          can_rollback_to?: boolean
          calibration_profile_version?: string | null
          created_at?: string
          hazard_type?: string
          id?: string
          model_version?: string | null
          region_name?: string
          rolled_back_at?: string | null
          rolled_back_by?: string | null
          snapshot_metrics?: Json | null
          threshold_profile_version?: string | null
        }
        Relationships: []
      }
      model_registry: {
        Row: {
          activated_at: string | null
          activated_by: string | null
          activation_evaluation_run_id: string | null
          created_at: string
          feature_importance: Json | null
          feature_version: string
          hazard_type: string
          id: string
          model_artifact_url: string | null
          model_type: string
          model_version: string
          retired_at: string | null
          retired_reason: string | null
          status: string
          superseded_by_version: string | null
          training_dataset_version: string | null
          training_f1: number | null
          training_precision: number | null
          training_recall: number | null
          training_run_id: string | null
          updated_at: string
        }
        Insert: {
          activated_at?: string | null
          activated_by?: string | null
          activation_evaluation_run_id?: string | null
          created_at?: string
          feature_importance?: Json | null
          feature_version: string
          hazard_type?: string
          id?: string
          model_artifact_url?: string | null
          model_type?: string
          model_version: string
          retired_at?: string | null
          retired_reason?: string | null
          status?: string
          superseded_by_version?: string | null
          training_dataset_version?: string | null
          training_f1?: number | null
          training_precision?: number | null
          training_recall?: number | null
          training_run_id?: string | null
          updated_at?: string
        }
        Update: {
          activated_at?: string | null
          activated_by?: string | null
          activation_evaluation_run_id?: string | null
          created_at?: string
          feature_importance?: Json | null
          feature_version?: string
          hazard_type?: string
          id?: string
          model_artifact_url?: string | null
          model_type?: string
          model_version?: string
          retired_at?: string | null
          retired_reason?: string | null
          status?: string
          superseded_by_version?: string | null
          training_dataset_version?: string | null
          training_f1?: number | null
          training_precision?: number | null
          training_recall?: number | null
          training_run_id?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "model_registry_activation_evaluation_run_id_fkey"
            columns: ["activation_evaluation_run_id"]
            isOneToOne: false
            referencedRelation: "evaluation_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      active_learning_queue: {
        Row: {
          assigned_to: string | null
          created_at: string
          forecast_id: string
          forecast_outcome_id: string | null
          hazard_type: string
          id: string
          priority_score: number
          reason: string
          resolution: string | null
          resolution_notes: string | null
          review_status: string
          uncertainty_score: number | null
          predicted_risk: number | null
          resolved_at: string | null
        }
        Insert: {
          assigned_to?: string | null
          created_at?: string
          forecast_id: string
          forecast_outcome_id?: string | null
          hazard_type?: string
          id?: string
          priority_score?: number
          reason: string
          resolution?: string | null
          resolution_notes?: string | null
          review_status?: string
          uncertainty_score?: number | null
          predicted_risk?: number | null
          resolved_at?: string | null
        }
        Update: {
          assigned_to?: string | null
          created_at?: string
          forecast_id?: string
          forecast_outcome_id?: string | null
          hazard_type?: string
          id?: string
          priority_score?: number
          reason?: string
          resolution?: string | null
          resolution_notes?: string | null
          review_status?: string
          uncertainty_score?: number | null
          predicted_risk?: number | null
          resolved_at?: string | null
        }
        Relationships: []
      }
      label_matching_policies: {
        Row: {
          created_at: string
          created_by: string | null
          description: string | null
          exclude_manual_events: boolean
          exclude_unverified_reports: boolean
          elevation_band_width_m: number
          elevation_flexibility_m: number
          hazard_type: string
          id: string
          lead_time_discount_factor: number
          min_event_verification: string
          min_forecast_confidence: number
          policy_version: string
          spatial_tolerance_m: number
          temporal_tolerance_hours: number
        }
        Insert: {
          created_at?: string
          created_by?: string | null
          description?: string | null
          exclude_manual_events?: boolean
          exclude_unverified_reports?: boolean
          elevation_band_width_m?: number
          elevation_flexibility_m?: number
          hazard_type?: string
          id?: string
          lead_time_discount_factor?: number
          min_event_verification?: string
          min_forecast_confidence?: number
          policy_version: string
          spatial_tolerance_m?: number
          temporal_tolerance_hours?: number
        }
        Update: {
          created_at?: string
          created_by?: string | null
          description?: string | null
          exclude_manual_events?: boolean
          exclude_unverified_reports?: boolean
          elevation_band_width_m?: number
          elevation_flexibility_m?: number
          hazard_type?: string
          id?: string
          lead_time_discount_factor?: number
          min_event_verification?: string
          min_forecast_confidence?: number
          policy_version?: string
          spatial_tolerance_m?: number
          temporal_tolerance_hours?: number
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      event_type: "slab" | "loose" | "wet" | "glide" | "cornice" | "unknown"
      hazard_type: "avalanche"
      job_status: "pending" | "running" | "completed" | "failed"
      job_type:
        | "forecast"
        | "daily_enrichment"
        | "sentinel_refresh"
        | "fine_tune"
        | "static_precompute"
        | "field_report_enrichment"
        | "snow_cover_refresh"
        | "recent_activity_refresh"
        | "label_forecast_outcomes"
        | "run_evaluation"
        | "retrain_avalanche_model"
      report_status: "pending" | "verified" | "rejected"
      verification_status: "unverified" | "weak" | "verified" | "expert_verified"
      label_role: "training_label" | "display_only" | "excluded"
      review_status: "pending" | "under_review" | "approved" | "rejected" | "needs_info"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      event_type: ["slab", "loose", "wet", "glide", "cornice", "unknown"],
      job_status: ["pending", "running", "completed", "failed"],
      job_type: [
        "forecast",
        "daily_enrichment",
        "sentinel_refresh",
        "fine_tune",
        "static_precompute",
        "field_report_enrichment",
        "snow_cover_refresh",
        "recent_activity_refresh",
        "label_forecast_outcomes",
        "run_evaluation",
        "retrain_avalanche_model",
      ],
      report_status: ["pending", "verified", "rejected"],
      hazard_type: ["avalanche"],
      verification_status: ["unverified", "weak", "verified", "expert_verified"],
      label_role: ["training_label", "display_only", "excluded"],
      review_status: ["pending", "under_review", "approved", "rejected", "needs_info"],
    },
  },
} as const
