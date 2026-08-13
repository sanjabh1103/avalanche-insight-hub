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
      active_learning_queue: {
        Row: {
          assigned_to: string | null
          created_at: string
          forecast_id: string
          forecast_outcome_id: string | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          predicted_risk: number | null
          priority_score: number
          reason: string
          resolution: string | null
          resolution_notes: string | null
          resolved_at: string | null
          review_status: string
          uncertainty_score: number | null
        }
        Insert: {
          assigned_to?: string | null
          created_at?: string
          forecast_id: string
          forecast_outcome_id?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          predicted_risk?: number | null
          priority_score?: number
          reason: string
          resolution?: string | null
          resolution_notes?: string | null
          resolved_at?: string | null
          review_status?: string
          uncertainty_score?: number | null
        }
        Update: {
          assigned_to?: string | null
          created_at?: string
          forecast_id?: string
          forecast_outcome_id?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          predicted_risk?: number | null
          priority_score?: number
          reason?: string
          resolution?: string | null
          resolution_notes?: string | null
          resolved_at?: string | null
          review_status?: string
          uncertainty_score?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "active_learning_queue_forecast_id_fkey"
            columns: ["forecast_id"]
            isOneToOne: false
            referencedRelation: "forecasts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "active_learning_queue_forecast_outcome_id_fkey"
            columns: ["forecast_outcome_id"]
            isOneToOne: false
            referencedRelation: "forecast_outcomes"
            referencedColumns: ["id"]
          },
        ]
      }
      avalanche_events: {
        Row: {
          aspect_bucket: string | null
          aspect_deg: number | null
          backscatter_delta_db: number | null
          coherence_drop: number | null
          confidence: number | null
          created_at: string
          description: string | null
          detection_confidence: number | null
          detection_mode: string
          elevation_m: number | null
          end_time: string | null
          event_features: Json
          event_geom: unknown
          event_subtype: string | null
          event_type: Database["public"]["Enums"]["event_type"] | null
          features: Json | null
          fusion_source: string | null
          geometry_type: string | null
          governance_version: string | null
          governed_at: string | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          label_confidence: number
          label_role: string
          location: unknown
          mask_asset_ref: string | null
          recent_activity_weight: number | null
          sar_metadata: Json
          satellite_scene_ids: string[]
          severity: number | null
          size_scale: string | null
          slope_angle_deg: number | null
          slope_band: string | null
          source: string
          source_model: string | null
          source_quality_score: number | null
          source_scene_ids: string[]
          start_time: string | null
          timestamp: string
          topo_profile: Json
          topo_resolution_m: number | null
          topo_source: string | null
          training_eligible: boolean
          training_eligible_reason: string | null
          training_weight: number
          trigger_type: string | null
          verification_status: string
        }
        Insert: {
          aspect_bucket?: string | null
          aspect_deg?: number | null
          backscatter_delta_db?: number | null
          coherence_drop?: number | null
          confidence?: number | null
          created_at?: string
          description?: string | null
          detection_confidence?: number | null
          detection_mode?: string
          elevation_m?: number | null
          end_time?: string | null
          event_features?: Json
          event_geom?: unknown
          event_subtype?: string | null
          event_type?: Database["public"]["Enums"]["event_type"] | null
          features?: Json | null
          fusion_source?: string | null
          geometry_type?: string | null
          governance_version?: string | null
          governed_at?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          label_confidence?: number
          label_role?: string
          location?: unknown
          mask_asset_ref?: string | null
          recent_activity_weight?: number | null
          sar_metadata?: Json
          satellite_scene_ids?: string[]
          severity?: number | null
          size_scale?: string | null
          slope_angle_deg?: number | null
          slope_band?: string | null
          source?: string
          source_model?: string | null
          source_quality_score?: number | null
          source_scene_ids?: string[]
          start_time?: string | null
          timestamp?: string
          topo_profile?: Json
          topo_resolution_m?: number | null
          topo_source?: string | null
          training_eligible?: boolean
          training_eligible_reason?: string | null
          training_weight?: number
          trigger_type?: string | null
          verification_status?: string
        }
        Update: {
          aspect_bucket?: string | null
          aspect_deg?: number | null
          backscatter_delta_db?: number | null
          coherence_drop?: number | null
          confidence?: number | null
          created_at?: string
          description?: string | null
          detection_confidence?: number | null
          detection_mode?: string
          elevation_m?: number | null
          end_time?: string | null
          event_features?: Json
          event_geom?: unknown
          event_subtype?: string | null
          event_type?: Database["public"]["Enums"]["event_type"] | null
          features?: Json | null
          fusion_source?: string | null
          geometry_type?: string | null
          governance_version?: string | null
          governed_at?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          label_confidence?: number
          label_role?: string
          location?: unknown
          mask_asset_ref?: string | null
          recent_activity_weight?: number | null
          sar_metadata?: Json
          satellite_scene_ids?: string[]
          severity?: number | null
          size_scale?: string | null
          slope_angle_deg?: number | null
          slope_band?: string | null
          source?: string
          source_model?: string | null
          source_quality_score?: number | null
          source_scene_ids?: string[]
          start_time?: string | null
          timestamp?: string
          topo_profile?: Json
          topo_resolution_m?: number | null
          topo_source?: string | null
          training_eligible?: boolean
          training_eligible_reason?: string | null
          training_weight?: number
          trigger_type?: string | null
          verification_status?: string
        }
        Relationships: []
      }
      calibration_profiles: {
        Row: {
          approved_at: string | null
          approved_by: string | null
          created_at: string
          description: string | null
          feature_scalars: Json
          hazard_type: Database["public"]["Enums"]["hazard_type"]
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
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
      calibration_reports: {
        Row: {
          artifact_ref: string | null
          calibration_method: string
          calibration_profile_version: string | null
          created_at: string
          dataset_snapshot_id: string
          forecast_horizon: number | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          hindcast_run_id: string
          id: string
          label_snapshot_id: string
          metric_summary: Json
          model_version: string
          region_key: string | null
          reliability_curve: Json
          season_window: string | null
          uncertainty_coverage: Json
          updated_at: string
        }
        Insert: {
          artifact_ref?: string | null
          calibration_method?: string
          calibration_profile_version?: string | null
          created_at?: string
          dataset_snapshot_id: string
          forecast_horizon?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          hindcast_run_id: string
          id?: string
          label_snapshot_id: string
          metric_summary?: Json
          model_version: string
          region_key?: string | null
          reliability_curve?: Json
          season_window?: string | null
          uncertainty_coverage?: Json
          updated_at?: string
        }
        Update: {
          artifact_ref?: string | null
          calibration_method?: string
          calibration_profile_version?: string | null
          created_at?: string
          dataset_snapshot_id?: string
          forecast_horizon?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          hindcast_run_id?: string
          id?: string
          label_snapshot_id?: string
          metric_summary?: Json
          model_version?: string
          region_key?: string | null
          reliability_curve?: Json
          season_window?: string | null
          uncertainty_coverage?: Json
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "calibration_reports_hindcast_run_id_fkey"
            columns: ["hindcast_run_id"]
            isOneToOne: false
            referencedRelation: "hindcast_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "calibration_reports_label_snapshot_id_fkey"
            columns: ["label_snapshot_id"]
            isOneToOne: false
            referencedRelation: "label_snapshots"
            referencedColumns: ["id"]
          },
        ]
      }
      compute_jobs: {
        Row: {
          bbox: number[] | null
          created_at: string
          error: string | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
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
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
      evaluation_metrics: {
        Row: {
          created_at: string
          ece: number | null
          evaluation_run_id: string
          f1_risk3: number | null
          f1_risk4: number | null
          false_alarm_rate: number | null
          false_positives: number | null
          id: string
          observed_events: number
          precision_risk3: number | null
          precision_risk4: number | null
          recall_risk3: number | null
          recall_risk4: number | null
          reliability_data: Json | null
          risk_distribution: Json | null
          slice_type: string
          slice_value: string
          total_cells: number
          total_forecasts: number
          true_positives: number | null
        }
        Insert: {
          created_at?: string
          ece?: number | null
          evaluation_run_id: string
          f1_risk3?: number | null
          f1_risk4?: number | null
          false_alarm_rate?: number | null
          false_positives?: number | null
          id?: string
          observed_events: number
          precision_risk3?: number | null
          precision_risk4?: number | null
          recall_risk3?: number | null
          recall_risk4?: number | null
          reliability_data?: Json | null
          risk_distribution?: Json | null
          slice_type: string
          slice_value: string
          total_cells: number
          total_forecasts: number
          true_positives?: number | null
        }
        Update: {
          created_at?: string
          ece?: number | null
          evaluation_run_id?: string
          f1_risk3?: number | null
          f1_risk4?: number | null
          false_alarm_rate?: number | null
          false_positives?: number | null
          id?: string
          observed_events?: number
          precision_risk3?: number | null
          precision_risk4?: number | null
          recall_risk3?: number | null
          recall_risk4?: number | null
          reliability_data?: Json | null
          risk_distribution?: Json | null
          slice_type?: string
          slice_value?: string
          total_cells?: number
          total_forecasts?: number
          true_positives?: number | null
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
      evaluation_runs: {
        Row: {
          completed_at: string | null
          created_at: string
          error_message: string | null
          eval_end_date: string
          eval_start_date: string
          hazard_type: Database["public"]["Enums"]["hazard_type"]
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
        }
        Insert: {
          completed_at?: string | null
          created_at?: string
          error_message?: string | null
          eval_end_date: string
          eval_start_date: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
        }
        Update: {
          completed_at?: string | null
          created_at?: string
          error_message?: string | null
          eval_end_date?: string
          eval_start_date?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
        }
        Relationships: []
      }
      feature_completeness_log: {
        Row: {
          forecast_grid_id: string | null
          forecast_id: string | null
          forecast_run_id: string | null
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
          forecast_grid_id?: string | null
          forecast_id?: string | null
          forecast_run_id?: string | null
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
          forecast_grid_id?: string | null
          forecast_id?: string | null
          forecast_run_id?: string | null
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
            foreignKeyName: "feature_completeness_log_forecast_grid_id_fkey"
            columns: ["forecast_grid_id"]
            isOneToOne: false
            referencedRelation: "forecast_grids"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "feature_completeness_log_forecast_id_fkey"
            columns: ["forecast_id"]
            isOneToOne: false
            referencedRelation: "forecasts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "feature_completeness_log_forecast_run_id_fkey"
            columns: ["forecast_run_id"]
            isOneToOne: false
            referencedRelation: "forecast_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "feature_completeness_log_recent_activity_feature_id_fkey"
            columns: ["recent_activity_feature_id"]
            isOneToOne: false
            referencedRelation: "recent_activity_features"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "feature_completeness_log_snow_cover_snapshot_id_fkey"
            columns: ["snow_cover_snapshot_id"]
            isOneToOne: false
            referencedRelation: "snow_cover_snapshots"
            referencedColumns: ["id"]
          },
        ]
      }
      field_reports: {
        Row: {
          aspect: string | null
          client_report_id: string | null
          confidence: number | null
          created_at: string
          dedupe_group_id: string | null
          description: string | null
          elevation_m: number | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          image_url: string | null
          location: unknown
          location_precision_m: number | null
          normalization_version: string | null
          normalized_event_type: string | null
          normalized_severity: string | null
          reporter_reliability_score: number | null
          review_status: Database["public"]["Enums"]["review_status"]
          reviewed_at: string | null
          reviewed_by: string | null
          snow_description: string | null
          status: Database["public"]["Enums"]["report_status"] | null
          submitted_offline: boolean
          sync_error: string | null
          sync_status: string
          synced_at: string | null
          terrain_context: string | null
          timestamp: string
          training_eligible: boolean
          trigger_type: string | null
          user_id: string | null
        }
        Insert: {
          aspect?: string | null
          client_report_id?: string | null
          confidence?: number | null
          created_at?: string
          dedupe_group_id?: string | null
          description?: string | null
          elevation_m?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          image_url?: string | null
          location?: unknown
          location_precision_m?: number | null
          normalization_version?: string | null
          normalized_event_type?: string | null
          normalized_severity?: string | null
          reporter_reliability_score?: number | null
          review_status?: Database["public"]["Enums"]["review_status"]
          reviewed_at?: string | null
          reviewed_by?: string | null
          snow_description?: string | null
          status?: Database["public"]["Enums"]["report_status"] | null
          submitted_offline?: boolean
          sync_error?: string | null
          sync_status?: string
          synced_at?: string | null
          terrain_context?: string | null
          timestamp?: string
          training_eligible?: boolean
          trigger_type?: string | null
          user_id?: string | null
        }
        Update: {
          aspect?: string | null
          client_report_id?: string | null
          confidence?: number | null
          created_at?: string
          dedupe_group_id?: string | null
          description?: string | null
          elevation_m?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          image_url?: string | null
          location?: unknown
          location_precision_m?: number | null
          normalization_version?: string | null
          normalized_event_type?: string | null
          normalized_severity?: string | null
          reporter_reliability_score?: number | null
          review_status?: Database["public"]["Enums"]["review_status"]
          reviewed_at?: string | null
          reviewed_by?: string | null
          snow_description?: string | null
          status?: Database["public"]["Enums"]["report_status"] | null
          submitted_offline?: boolean
          sync_error?: string | null
          sync_status?: string
          synced_at?: string | null
          terrain_context?: string | null
          timestamp?: string
          training_eligible?: boolean
          trigger_type?: string | null
          user_id?: string | null
        }
        Relationships: []
      }
      forecast_analytics: {
        Row: {
          avg_risk: number | null
          avg_uncertainty: number | null
          bbox: number[] | null
          calibration_profile_version: string | null
          capability_snapshot: Json
          cell_count: number | null
          created_at: string
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          model_version: string | null
          region_name: string | null
          runtime_mode: string
          weather_source: string | null
        }
        Insert: {
          avg_risk?: number | null
          avg_uncertainty?: number | null
          bbox?: number[] | null
          calibration_profile_version?: string | null
          capability_snapshot?: Json
          cell_count?: number | null
          created_at?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          model_version?: string | null
          region_name?: string | null
          runtime_mode?: string
          weather_source?: string | null
        }
        Update: {
          avg_risk?: number | null
          avg_uncertainty?: number | null
          bbox?: number[] | null
          calibration_profile_version?: string | null
          capability_snapshot?: Json
          cell_count?: number | null
          created_at?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          model_version?: string | null
          region_name?: string | null
          runtime_mode?: string
          weather_source?: string | null
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
          hourly_grids: Json
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
          hourly_grids?: Json
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
          hourly_grids?: Json
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
        Relationships: [
          {
            foreignKeyName: "forecast_grids_source_job_id_fkey"
            columns: ["source_job_id"]
            isOneToOne: false
            referencedRelation: "compute_jobs"
            referencedColumns: ["id"]
          },
        ]
      }
      forecast_outcomes: {
        Row: {
          cell_col: number
          cell_row: number
          created_at: string
          distance_to_nearest_event_m: number | null
          elevation_band_compatible: boolean | null
          event_observed: boolean
          excluded_from_training: boolean
          exclusion_reason: string | null
          forecast_grid_id: string | null
          forecast_hour: number
          forecast_id: string | null
          forecast_source: string | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
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
        }
        Insert: {
          cell_col: number
          cell_row: number
          created_at?: string
          distance_to_nearest_event_m?: number | null
          elevation_band_compatible?: boolean | null
          event_observed?: boolean
          excluded_from_training?: boolean
          exclusion_reason?: string | null
          forecast_grid_id?: string | null
          forecast_hour: number
          forecast_id?: string | null
          forecast_source?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
        }
        Update: {
          cell_col?: number
          cell_row?: number
          created_at?: string
          distance_to_nearest_event_m?: number | null
          elevation_band_compatible?: boolean | null
          event_observed?: boolean
          excluded_from_training?: boolean
          exclusion_reason?: string | null
          forecast_grid_id?: string | null
          forecast_hour?: number
          forecast_id?: string | null
          forecast_source?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
        }
        Relationships: [
          {
            foreignKeyName: "forecast_outcomes_forecast_grid_id_fkey"
            columns: ["forecast_grid_id"]
            isOneToOne: false
            referencedRelation: "forecast_grids"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "forecast_outcomes_forecast_id_fkey"
            columns: ["forecast_id"]
            isOneToOne: false
            referencedRelation: "forecasts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "forecast_outcomes_nearest_event_id_fkey"
            columns: ["nearest_event_id"]
            isOneToOne: false
            referencedRelation: "avalanche_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "forecast_outcomes_nearest_event_id_fkey"
            columns: ["nearest_event_id"]
            isOneToOne: false
            referencedRelation: "avalanche_events_decayed"
            referencedColumns: ["id"]
          },
        ]
      }
      forecast_publication_events: {
        Row: {
          created_at: string
          detail: Json
          forecast_run_id: string
          id: string
          stage: string
          status: string
        }
        Insert: {
          created_at?: string
          detail?: Json
          forecast_run_id: string
          id?: string
          stage: string
          status: string
        }
        Update: {
          created_at?: string
          detail?: Json
          forecast_run_id?: string
          id?: string
          stage?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "forecast_publication_events_forecast_run_id_fkey"
            columns: ["forecast_run_id"]
            isOneToOne: false
            referencedRelation: "forecast_active_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "forecast_publication_events_forecast_run_id_fkey"
            columns: ["forecast_run_id"]
            isOneToOne: false
            referencedRelation: "forecast_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      forecast_run_hours: {
        Row: {
          cell_count: number
          created_at: string
          forecast_hour: number
          forecast_run_id: string
          id: string
          payload_sha256: string | null
          ready_cell_count: number
          stale_cell_count: number
          storage_ref: string
          valid_time: string
        }
        Insert: {
          cell_count?: number
          created_at?: string
          forecast_hour: number
          forecast_run_id: string
          id?: string
          payload_sha256?: string | null
          ready_cell_count?: number
          stale_cell_count?: number
          storage_ref: string
          valid_time: string
        }
        Update: {
          cell_count?: number
          created_at?: string
          forecast_hour?: number
          forecast_run_id?: string
          id?: string
          payload_sha256?: string | null
          ready_cell_count?: number
          stale_cell_count?: number
          storage_ref?: string
          valid_time?: string
        }
        Relationships: [
          {
            foreignKeyName: "forecast_run_hours_forecast_run_id_fkey"
            columns: ["forecast_run_id"]
            isOneToOne: false
            referencedRelation: "forecast_active_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "forecast_run_hours_forecast_run_id_fkey"
            columns: ["forecast_run_id"]
            isOneToOne: false
            referencedRelation: "forecast_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      forecast_runs: {
        Row: {
          active: boolean
          bbox: number[]
          compatibility_forecast_grid_id: string | null
          created_at: string
          forecast_bulletins: Json
          forecast_date: string
          grid_size: number
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          horizon_hours: number
          id: string
          issue_time: string
          manifest_storage_ref: string | null
          model_metadata: Json
          publication_status: string
          published_at: string | null
          region_key: string
          region_name: string
          runout_storage_ref: string | null
          status: string
          updated_at: string
          weather_summary: Json
        }
        Insert: {
          active?: boolean
          bbox: number[]
          compatibility_forecast_grid_id?: string | null
          created_at?: string
          forecast_bulletins?: Json
          forecast_date: string
          grid_size: number
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          horizon_hours: number
          id?: string
          issue_time?: string
          manifest_storage_ref?: string | null
          model_metadata?: Json
          publication_status?: string
          published_at?: string | null
          region_key: string
          region_name: string
          runout_storage_ref?: string | null
          status?: string
          updated_at?: string
          weather_summary?: Json
        }
        Update: {
          active?: boolean
          bbox?: number[]
          compatibility_forecast_grid_id?: string | null
          created_at?: string
          forecast_bulletins?: Json
          forecast_date?: string
          grid_size?: number
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          horizon_hours?: number
          id?: string
          issue_time?: string
          manifest_storage_ref?: string | null
          model_metadata?: Json
          publication_status?: string
          published_at?: string | null
          region_key?: string
          region_name?: string
          runout_storage_ref?: string | null
          status?: string
          updated_at?: string
          weather_summary?: Json
        }
        Relationships: [
          {
            foreignKeyName: "forecast_runs_compatibility_forecast_grid_id_fkey"
            columns: ["compatibility_forecast_grid_id"]
            isOneToOne: false
            referencedRelation: "forecast_grids"
            referencedColumns: ["id"]
          },
        ]
      }
      forecast_shap_cache: {
        Row: {
          base_value: number | null
          cell_col: number
          cell_row: number
          created_at: string
          dominant_driver: string | null
          forecast_grid_id: string
          forecast_hour: number
          id: string
          model_version: string
          shap_values: Json
          top_features: Json
        }
        Insert: {
          base_value?: number | null
          cell_col: number
          cell_row: number
          created_at?: string
          dominant_driver?: string | null
          forecast_grid_id: string
          forecast_hour?: number
          id?: string
          model_version: string
          shap_values: Json
          top_features: Json
        }
        Update: {
          base_value?: number | null
          cell_col?: number
          cell_row?: number
          created_at?: string
          dominant_driver?: string | null
          forecast_grid_id?: string
          forecast_hour?: number
          id?: string
          model_version?: string
          shap_values?: Json
          top_features?: Json
        }
        Relationships: [
          {
            foreignKeyName: "forecast_shap_cache_forecast_grid_id_fkey"
            columns: ["forecast_grid_id"]
            isOneToOne: false
            referencedRelation: "forecast_grids"
            referencedColumns: ["id"]
          },
        ]
      }
      forecasts: {
        Row: {
          bbox: number[] | null
          calibration_profile_version: string | null
          capability_snapshot: Json
          created_at: string
          data_snapshot_id: string | null
          exposure: number | null
          feature_version: string | null
          grid_data: Json | null
          hazard: number | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          hourly_grids: Json | null
          id: string
          inference_backend: string
          input_completeness_score: number | null
          job_id: string | null
          label_support_score: number | null
          model_version: string | null
          optimization_summary: Json
          problem_type: string | null
          risk_score: number | null
          runtime_mode: string
          shap_values: Json | null
          snowpack_metrics: Json
          threshold_profile_version: string | null
          timestamp: string
          uncertainty_reasons: Json
          uncertainty_score: number | null
          vulnerability: number | null
        }
        Insert: {
          bbox?: number[] | null
          calibration_profile_version?: string | null
          capability_snapshot?: Json
          created_at?: string
          data_snapshot_id?: string | null
          exposure?: number | null
          feature_version?: string | null
          grid_data?: Json | null
          hazard?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          hourly_grids?: Json | null
          id?: string
          inference_backend?: string
          input_completeness_score?: number | null
          job_id?: string | null
          label_support_score?: number | null
          model_version?: string | null
          optimization_summary?: Json
          problem_type?: string | null
          risk_score?: number | null
          runtime_mode?: string
          shap_values?: Json | null
          snowpack_metrics?: Json
          threshold_profile_version?: string | null
          timestamp?: string
          uncertainty_reasons?: Json
          uncertainty_score?: number | null
          vulnerability?: number | null
        }
        Update: {
          bbox?: number[] | null
          calibration_profile_version?: string | null
          capability_snapshot?: Json
          created_at?: string
          data_snapshot_id?: string | null
          exposure?: number | null
          feature_version?: string | null
          grid_data?: Json | null
          hazard?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          hourly_grids?: Json | null
          id?: string
          inference_backend?: string
          input_completeness_score?: number | null
          job_id?: string | null
          label_support_score?: number | null
          model_version?: string | null
          optimization_summary?: Json
          problem_type?: string | null
          risk_score?: number | null
          runtime_mode?: string
          shap_values?: Json | null
          snowpack_metrics?: Json
          threshold_profile_version?: string | null
          timestamp?: string
          uncertainty_reasons?: Json
          uncertainty_score?: number | null
          vulnerability?: number | null
        }
        Relationships: []
      }
      hindcast_runs: {
        Row: {
          artifact_manifest_ref: string | null
          calibration_profile_version: string | null
          completed_at: string | null
          created_at: string
          dataset_snapshot_id: string
          eval_window_end: string
          eval_window_start: string
          forecast_horizons: number[]
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          label_snapshot_id: string
          model_version: string
          region_coverage: Json
          region_keys: string[]
          run_name: string
          source_composition: Json
          status: string
          summary_metrics: Json
          updated_at: string
        }
        Insert: {
          artifact_manifest_ref?: string | null
          calibration_profile_version?: string | null
          completed_at?: string | null
          created_at?: string
          dataset_snapshot_id: string
          eval_window_end: string
          eval_window_start: string
          forecast_horizons?: number[]
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          label_snapshot_id: string
          model_version: string
          region_coverage?: Json
          region_keys?: string[]
          run_name: string
          source_composition?: Json
          status?: string
          summary_metrics?: Json
          updated_at?: string
        }
        Update: {
          artifact_manifest_ref?: string | null
          calibration_profile_version?: string | null
          completed_at?: string | null
          created_at?: string
          dataset_snapshot_id?: string
          eval_window_end?: string
          eval_window_start?: string
          forecast_horizons?: number[]
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          label_snapshot_id?: string
          model_version?: string
          region_coverage?: Json
          region_keys?: string[]
          run_name?: string
          source_composition?: Json
          status?: string
          summary_metrics?: Json
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "hindcast_runs_label_snapshot_id_fkey"
            columns: ["label_snapshot_id"]
            isOneToOne: false
            referencedRelation: "label_snapshots"
            referencedColumns: ["id"]
          },
        ]
      }
      label_matching_policies: {
        Row: {
          created_at: string
          created_by: string | null
          description: string | null
          elevation_band_width_m: number
          elevation_flexibility_m: number
          exclude_manual_events: boolean
          exclude_unverified_reports: boolean
          hazard_type: Database["public"]["Enums"]["hazard_type"]
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
          elevation_band_width_m?: number
          elevation_flexibility_m?: number
          exclude_manual_events?: boolean
          exclude_unverified_reports?: boolean
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
          elevation_band_width_m?: number
          elevation_flexibility_m?: number
          exclude_manual_events?: boolean
          exclude_unverified_reports?: boolean
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
      label_snapshots: {
        Row: {
          confidence_decay_policy: Json
          coverage_summary: Json
          created_at: string
          dataset_snapshot_id: string
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          name: string | null
          provenance_notes: string | null
          region_coverage: Json
          season_coverage: Json
          snapshot_id: string
          source_composition: Json
          source_weights: Json
          status: string
          updated_at: string
        }
        Insert: {
          confidence_decay_policy?: Json
          coverage_summary?: Json
          created_at?: string
          dataset_snapshot_id: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          name?: string | null
          provenance_notes?: string | null
          region_coverage?: Json
          season_coverage?: Json
          snapshot_id: string
          source_composition?: Json
          source_weights?: Json
          status?: string
          updated_at?: string
        }
        Update: {
          confidence_decay_policy?: Json
          coverage_summary?: Json
          created_at?: string
          dataset_snapshot_id?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          name?: string | null
          provenance_notes?: string | null
          region_coverage?: Json
          season_coverage?: Json
          snapshot_id?: string
          source_composition?: Json
          source_weights?: Json
          status?: string
          updated_at?: string
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
          hazard_type: Database["public"]["Enums"]["hazard_type"]
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
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
      model_status: {
        Row: {
          active_model_type: string | null
          active_model_version: string | null
          autonomous_evidence_summary: Json
          calibration_profile_version: string | null
          capabilities: Json
          capability_summary: string
          data_freshness_hours: number | null
          drift_mode_state: string | null
          dynamic_model_candidate: Json
          f1_score: number | null
          feature_version: string | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          inference_backend: string
          last_inference: string | null
          last_trained: string | null
          latest_benchmark_summary: Json
          next_optimization_run: string | null
          next_run: string | null
          optimization_summary: Json
          optimization_version: string | null
          promotion_gate_passed: boolean | null
          pss_gate_passed: boolean | null
          pss_reported: number | null
          sar_pipeline_version: string | null
          satellite_detection_stats: Json
          shadow_mode_active: boolean | null
          snowpack_metrics: Json
          snowpack_model_version: string | null
          stability_summary: Json
          threshold_profile_version: string | null
          version: string | null
        }
        Insert: {
          active_model_type?: string | null
          active_model_version?: string | null
          autonomous_evidence_summary?: Json
          calibration_profile_version?: string | null
          capabilities?: Json
          capability_summary?: string
          data_freshness_hours?: number | null
          drift_mode_state?: string | null
          dynamic_model_candidate?: Json
          f1_score?: number | null
          feature_version?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          inference_backend?: string
          last_inference?: string | null
          last_trained?: string | null
          latest_benchmark_summary?: Json
          next_optimization_run?: string | null
          next_run?: string | null
          optimization_summary?: Json
          optimization_version?: string | null
          promotion_gate_passed?: boolean | null
          pss_gate_passed?: boolean | null
          pss_reported?: number | null
          sar_pipeline_version?: string | null
          satellite_detection_stats?: Json
          shadow_mode_active?: boolean | null
          snowpack_metrics?: Json
          snowpack_model_version?: string | null
          stability_summary?: Json
          threshold_profile_version?: string | null
          version?: string | null
        }
        Update: {
          active_model_type?: string | null
          active_model_version?: string | null
          autonomous_evidence_summary?: Json
          calibration_profile_version?: string | null
          capabilities?: Json
          capability_summary?: string
          data_freshness_hours?: number | null
          drift_mode_state?: string | null
          dynamic_model_candidate?: Json
          f1_score?: number | null
          feature_version?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          inference_backend?: string
          last_inference?: string | null
          last_trained?: string | null
          latest_benchmark_summary?: Json
          next_optimization_run?: string | null
          next_run?: string | null
          optimization_summary?: Json
          optimization_version?: string | null
          promotion_gate_passed?: boolean | null
          pss_gate_passed?: boolean | null
          pss_reported?: number | null
          sar_pipeline_version?: string | null
          satellite_detection_stats?: Json
          shadow_mode_active?: boolean | null
          snowpack_metrics?: Json
          snowpack_model_version?: string | null
          stability_summary?: Json
          threshold_profile_version?: string | null
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
      promotion_events: {
        Row: {
          automatic: boolean
          created_at: string
          decided_by: string | null
          decision: string
          decision_reason: string | null
          evaluation_run_id: string | null
          event_type: string
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          new_version: string
          previous_version: string | null
          region_name: string | null
          triggering_metrics: Json
        }
        Insert: {
          automatic?: boolean
          created_at?: string
          decided_by?: string | null
          decision: string
          decision_reason?: string | null
          evaluation_run_id?: string | null
          event_type: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          new_version: string
          previous_version?: string | null
          region_name?: string | null
          triggering_metrics: Json
        }
        Update: {
          automatic?: boolean
          created_at?: string
          decided_by?: string | null
          decision?: string
          decision_reason?: string | null
          evaluation_run_id?: string | null
          event_type?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
      recent_activity_features: {
        Row: {
          cell_col: number | null
          cell_row: number | null
          data_completeness_score: number
          elevation_range_m: Json | null
          event_density_per_km2: number | null
          id: string
          materialization_job_id: string | null
          materialized_at: string
          max_severity_in_window: number | null
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
        }
        Insert: {
          cell_col?: number | null
          cell_row?: number | null
          data_completeness_score?: number
          elevation_range_m?: Json | null
          event_density_per_km2?: number | null
          id?: string
          materialization_job_id?: string | null
          materialized_at?: string
          max_severity_in_window?: number | null
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
        }
        Update: {
          cell_col?: number | null
          cell_row?: number | null
          data_completeness_score?: number
          elevation_range_m?: Json | null
          event_density_per_km2?: number | null
          id?: string
          materialization_job_id?: string | null
          materialized_at?: string
          max_severity_in_window?: number | null
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
      rollback_state: {
        Row: {
          calibration_profile_version: string | null
          can_rollback_to: boolean
          created_at: string
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          model_version: string | null
          region_name: string
          rolled_back_at: string | null
          rolled_back_by: string | null
          snapshot_metrics: Json | null
          threshold_profile_version: string | null
        }
        Insert: {
          calibration_profile_version?: string | null
          can_rollback_to?: boolean
          created_at?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          model_version?: string | null
          region_name?: string
          rolled_back_at?: string | null
          rolled_back_by?: string | null
          snapshot_metrics?: Json | null
          threshold_profile_version?: string | null
        }
        Update: {
          calibration_profile_version?: string | null
          can_rollback_to?: boolean
          created_at?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
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
      sar_detection_artifacts: {
        Row: {
          avalanche_event_id: string | null
          centroid_summary: Json
          confidence_score: number
          created_at: string
          detection_geometry: Json
          geometry_type: string
          id: string
          mask_asset_ref: string | null
          model_version: string
          provenance: Json
          region_key: string
          scene_time: string | null
          source_scene_ids: string[]
        }
        Insert: {
          avalanche_event_id?: string | null
          centroid_summary?: Json
          confidence_score?: number
          created_at?: string
          detection_geometry?: Json
          geometry_type?: string
          id?: string
          mask_asset_ref?: string | null
          model_version: string
          provenance?: Json
          region_key: string
          scene_time?: string | null
          source_scene_ids?: string[]
        }
        Update: {
          avalanche_event_id?: string | null
          centroid_summary?: Json
          confidence_score?: number
          created_at?: string
          detection_geometry?: Json
          geometry_type?: string
          id?: string
          mask_asset_ref?: string | null
          model_version?: string
          provenance?: Json
          region_key?: string
          scene_time?: string | null
          source_scene_ids?: string[]
        }
        Relationships: [
          {
            foreignKeyName: "sar_detection_artifacts_avalanche_event_id_fkey"
            columns: ["avalanche_event_id"]
            isOneToOne: false
            referencedRelation: "avalanche_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "sar_detection_artifacts_avalanche_event_id_fkey"
            columns: ["avalanche_event_id"]
            isOneToOne: false
            referencedRelation: "avalanche_events_decayed"
            referencedColumns: ["id"]
          },
        ]
      }
      sar_release_reference_items: {
        Row: {
          baseline_mask_asset_ref: string | null
          bbox: Json
          created_at: string
          external_scene_id: string
          id: string
          metadata: Json
          reference_set_id: string
          region_key: string
          scene_time: string | null
          stack_asset_ref: string
          truth_mask_asset_ref: string
          updated_at: string
        }
        Insert: {
          baseline_mask_asset_ref?: string | null
          bbox?: Json
          created_at?: string
          external_scene_id: string
          id?: string
          metadata?: Json
          reference_set_id: string
          region_key: string
          scene_time?: string | null
          stack_asset_ref: string
          truth_mask_asset_ref: string
          updated_at?: string
        }
        Update: {
          baseline_mask_asset_ref?: string | null
          bbox?: Json
          created_at?: string
          external_scene_id?: string
          id?: string
          metadata?: Json
          reference_set_id?: string
          region_key?: string
          scene_time?: string | null
          stack_asset_ref?: string
          truth_mask_asset_ref?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "sar_release_reference_items_reference_set_id_fkey"
            columns: ["reference_set_id"]
            isOneToOne: false
            referencedRelation: "sar_release_reference_sets"
            referencedColumns: ["id"]
          },
        ]
      }
      sar_release_reference_sets: {
        Row: {
          authoritative: boolean
          created_at: string
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          notes: string | null
          purpose: string
          registry_asset_ref: string | null
          set_key: string
          source_name: string
          source_version: string
          split_name: string
          status: string
          updated_at: string
        }
        Insert: {
          authoritative?: boolean
          created_at?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          notes?: string | null
          purpose?: string
          registry_asset_ref?: string | null
          set_key: string
          source_name?: string
          source_version: string
          split_name: string
          status?: string
          updated_at?: string
        }
        Update: {
          authoritative?: boolean
          created_at?: string
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          notes?: string | null
          purpose?: string
          registry_asset_ref?: string | null
          set_key?: string
          source_name?: string
          source_version?: string
          split_name?: string
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      snow_cover_snapshots: {
        Row: {
          bbox: number[]
          captured_at: string
          coverage_ratio: number | null
          created_at: string
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
          coverage_ratio?: number | null
          created_at?: string
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
          coverage_ratio?: number | null
          created_at?: string
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
      threshold_profiles: {
        Row: {
          alert_threshold_risk: number
          approved_at: string | null
          approved_by: string | null
          calibration_method: string
          created_at: string
          derived_from_evaluation_run_id: string | null
          description: string | null
          expected_false_alarm_rate: number | null
          expected_precision_risk3: number | null
          expected_recall_risk3: number | null
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          id: string
          profile_version: string
          region_name: string
          risk_1_max: number
          risk_2_max: number
          risk_3_max: number
          risk_4_max: number
          season_window: string | null
          severe_alert_threshold_risk: number
          status: string
          updated_at: string
        }
        Insert: {
          alert_threshold_risk?: number
          approved_at?: string | null
          approved_by?: string | null
          calibration_method?: string
          created_at?: string
          derived_from_evaluation_run_id?: string | null
          description?: string | null
          expected_false_alarm_rate?: number | null
          expected_precision_risk3?: number | null
          expected_recall_risk3?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          profile_version: string
          region_name?: string
          risk_1_max?: number
          risk_2_max?: number
          risk_3_max?: number
          risk_4_max?: number
          season_window?: string | null
          severe_alert_threshold_risk?: number
          status?: string
          updated_at?: string
        }
        Update: {
          alert_threshold_risk?: number
          approved_at?: string | null
          approved_by?: string | null
          calibration_method?: string
          created_at?: string
          derived_from_evaluation_run_id?: string | null
          description?: string | null
          expected_false_alarm_rate?: number | null
          expected_precision_risk3?: number | null
          expected_recall_risk3?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"]
          id?: string
          profile_version?: string
          region_name?: string
          risk_1_max?: number
          risk_2_max?: number
          risk_3_max?: number
          risk_4_max?: number
          season_window?: string | null
          severe_alert_threshold_risk?: number
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
      snowpack_runs: {
        Row: {
          id: string
          run_id: string
          status: "queued" | "building" | "running" | "completed" | "failed" | "verified"
          region_key: string
          elevation_band: string
          horizon_hours: number
          ensemble_members: number
          poc_mode: boolean
          decision_record_sha256: string | null
          toolchain_manifest_id: string | null
          image_id: string | null
          image_archive_sha256: string | null
          bundle_storage_ref: string | null
          manifest_storage_ref: string | null
          producer_gate_passed: boolean
          consumer_gate_passed: boolean
          error: string | null
          github_run_id: number | null
          github_run_url: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          run_id: string
          status?: "queued" | "building" | "running" | "completed" | "failed" | "verified"
          region_key: string
          elevation_band: string
          horizon_hours: number
          ensemble_members?: number
          poc_mode?: boolean
          decision_record_sha256?: string | null
          toolchain_manifest_id?: string | null
          image_id?: string | null
          image_archive_sha256?: string | null
          bundle_storage_ref?: string | null
          manifest_storage_ref?: string | null
          producer_gate_passed?: boolean
          consumer_gate_passed?: boolean
          error?: string | null
          github_run_id?: number | null
          github_run_url?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          run_id?: string
          status?: "queued" | "building" | "running" | "completed" | "failed" | "verified"
          region_key?: string
          elevation_band?: string
          horizon_hours?: number
          ensemble_members?: number
          poc_mode?: boolean
          decision_record_sha256?: string | null
          toolchain_manifest_id?: string | null
          image_id?: string | null
          image_archive_sha256?: string | null
          bundle_storage_ref?: string | null
          manifest_storage_ref?: string | null
          producer_gate_passed?: boolean
          consumer_gate_passed?: boolean
          error?: string | null
          github_run_id?: number | null
          github_run_url?: string | null
          created_at?: string
          updated_at?: string
        }
        Relationships: []
      }
    }
    Views: {
      avalanche_events_decayed: {
        Row: {
          age_days: number | null
          aspect_bucket: string | null
          aspect_deg: number | null
          backscatter_delta_db: number | null
          coherence_drop: number | null
          confidence: number | null
          confidence_decayed: number | null
          created_at: string | null
          description: string | null
          detection_confidence: number | null
          detection_mode: string | null
          elevation_m: number | null
          end_time: string | null
          event_features: Json | null
          event_geom: unknown
          event_subtype: string | null
          event_type: Database["public"]["Enums"]["event_type"] | null
          features: Json | null
          fusion_source: string | null
          geometry_type: string | null
          governance_version: string | null
          governed_at: string | null
          hazard_type: Database["public"]["Enums"]["hazard_type"] | null
          id: string | null
          label_confidence: number | null
          label_role: string | null
          location: unknown
          mask_asset_ref: string | null
          recent_activity_weight: number | null
          sar_metadata: Json | null
          satellite_scene_ids: string[] | null
          severity: number | null
          size_scale: string | null
          slope_angle_deg: number | null
          slope_band: string | null
          source: string | null
          source_model: string | null
          source_quality_score: number | null
          source_scene_ids: string[] | null
          start_time: string | null
          timestamp: string | null
          topo_profile: Json | null
          topo_resolution_m: number | null
          topo_source: string | null
          training_eligible: boolean | null
          training_eligible_reason: string | null
          training_weight: number | null
          trigger_type: string | null
          verification_status: string | null
        }
        Insert: {
          age_days?: never
          aspect_bucket?: string | null
          aspect_deg?: number | null
          backscatter_delta_db?: number | null
          coherence_drop?: number | null
          confidence?: number | null
          confidence_decayed?: never
          created_at?: string | null
          description?: string | null
          detection_confidence?: number | null
          detection_mode?: string | null
          elevation_m?: number | null
          end_time?: string | null
          event_features?: Json | null
          event_geom?: unknown
          event_subtype?: string | null
          event_type?: Database["public"]["Enums"]["event_type"] | null
          features?: Json | null
          fusion_source?: string | null
          geometry_type?: string | null
          governance_version?: string | null
          governed_at?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"] | null
          id?: string | null
          label_confidence?: number | null
          label_role?: string | null
          location?: unknown
          mask_asset_ref?: string | null
          recent_activity_weight?: number | null
          sar_metadata?: Json | null
          satellite_scene_ids?: string[] | null
          severity?: number | null
          size_scale?: string | null
          slope_angle_deg?: number | null
          slope_band?: string | null
          source?: string | null
          source_model?: string | null
          source_quality_score?: number | null
          source_scene_ids?: string[] | null
          start_time?: string | null
          timestamp?: string | null
          topo_profile?: Json | null
          topo_resolution_m?: number | null
          topo_source?: string | null
          training_eligible?: boolean | null
          training_eligible_reason?: string | null
          training_weight?: number | null
          trigger_type?: string | null
          verification_status?: string | null
        }
        Update: {
          age_days?: never
          aspect_bucket?: string | null
          aspect_deg?: number | null
          backscatter_delta_db?: number | null
          coherence_drop?: number | null
          confidence?: number | null
          confidence_decayed?: never
          created_at?: string | null
          description?: string | null
          detection_confidence?: number | null
          detection_mode?: string | null
          elevation_m?: number | null
          end_time?: string | null
          event_features?: Json | null
          event_geom?: unknown
          event_subtype?: string | null
          event_type?: Database["public"]["Enums"]["event_type"] | null
          features?: Json | null
          fusion_source?: string | null
          geometry_type?: string | null
          governance_version?: string | null
          governed_at?: string | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"] | null
          id?: string | null
          label_confidence?: number | null
          label_role?: string | null
          location?: unknown
          mask_asset_ref?: string | null
          recent_activity_weight?: number | null
          sar_metadata?: Json | null
          satellite_scene_ids?: string[] | null
          severity?: number | null
          size_scale?: string | null
          slope_angle_deg?: number | null
          slope_band?: string | null
          source?: string | null
          source_model?: string | null
          source_quality_score?: number | null
          source_scene_ids?: string[] | null
          start_time?: string | null
          timestamp?: string | null
          topo_profile?: Json | null
          topo_resolution_m?: number | null
          topo_source?: string | null
          training_eligible?: boolean | null
          training_eligible_reason?: string | null
          training_weight?: number | null
          trigger_type?: string | null
          verification_status?: string | null
        }
        Relationships: []
      }
      forecast_active_runs: {
        Row: {
          active: boolean | null
          bbox: number[] | null
          compatibility_forecast_grid_id: string | null
          created_at: string | null
          forecast_bulletins: Json | null
          forecast_date: string | null
          grid_size: number | null
          hazard_type: Database["public"]["Enums"]["hazard_type"] | null
          horizon_hours: number | null
          id: string | null
          issue_time: string | null
          manifest_storage_ref: string | null
          model_metadata: Json | null
          publication_status: string | null
          published_at: string | null
          region_key: string | null
          region_name: string | null
          runout_storage_ref: string | null
          status: string | null
          updated_at: string | null
          weather_summary: Json | null
        }
        Insert: {
          active?: boolean | null
          bbox?: number[] | null
          compatibility_forecast_grid_id?: string | null
          created_at?: string | null
          forecast_bulletins?: Json | null
          forecast_date?: string | null
          grid_size?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"] | null
          horizon_hours?: number | null
          id?: string | null
          issue_time?: string | null
          manifest_storage_ref?: string | null
          model_metadata?: Json | null
          publication_status?: string | null
          published_at?: string | null
          region_key?: string | null
          region_name?: string | null
          runout_storage_ref?: string | null
          status?: string | null
          updated_at?: string | null
          weather_summary?: Json | null
        }
        Update: {
          active?: boolean | null
          bbox?: number[] | null
          compatibility_forecast_grid_id?: string | null
          created_at?: string | null
          forecast_bulletins?: Json | null
          forecast_date?: string | null
          grid_size?: number | null
          hazard_type?: Database["public"]["Enums"]["hazard_type"] | null
          horizon_hours?: number | null
          id?: string | null
          issue_time?: string | null
          manifest_storage_ref?: string | null
          model_metadata?: Json | null
          publication_status?: string | null
          published_at?: string | null
          region_key?: string | null
          region_name?: string | null
          runout_storage_ref?: string | null
          status?: string | null
          updated_at?: string | null
          weather_summary?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "forecast_runs_compatibility_forecast_grid_id_fkey"
            columns: ["compatibility_forecast_grid_id"]
            isOneToOne: false
            referencedRelation: "forecast_grids"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Functions: {
      fetch_labeler_events: {
        Args: {
          p_bbox_max_lat: number
          p_bbox_max_lng: number
          p_bbox_min_lat: number
          p_bbox_min_lng: number
          p_hazard_type: string
          p_limit?: number
          p_min_verification_rank?: number
          p_window_end: string
          p_window_start: string
        }
        Returns: {
          elevation_m: number
          id: string
          label_role: string
          lat: number
          lng: number
          severity: number
          timestamp: string
          verification_status: string
        }[]
      }
      get_shap_for_cell: {
        Args: {
          p_cell_col: number
          p_cell_row: number
          p_forecast_grid_id: string
          p_forecast_hour?: number
        }
        Returns: {
          base_value: number
          cell_col: number
          cell_row: number
          created_at: string
          dominant_driver: string
          forecast_grid_id: string
          forecast_hour: number
          model_version: string
          shap_values: Json
          top_features: Json
        }[]
      }
      get_snowpack_run_status: {
        Args: { p_run_id: string }
        Returns: {
          consumer_gate_passed: boolean
          created_at: string
          elevation_band: string
          ensemble_members: number
          horizon_hours: number
          poc_mode: boolean
          producer_gate_passed: boolean
          region_key: string
          run_id: string
          status: string
          updated_at: string
        }[]
      }
      is_admin: { Args: never; Returns: boolean }
      list_snowpack_run_status: {
        Args: {
          p_limit?: number
          p_region_key?: string | null
          p_verified_only?: boolean
        }
        Returns: {
          consumer_gate_passed: boolean
          created_at: string
          elevation_band: string
          ensemble_members: number
          horizon_hours: number
          poc_mode: boolean
          producer_gate_passed: boolean
          region_key: string
          run_id: string
          status: string
          updated_at: string
        }[]
      }
      match_corroborating_event: {
        Args: {
          p_event_id: string
          p_lat: number
          p_lng: number
          p_radius_m?: number
          p_timestamp: string
          p_window_hours?: number
        }
        Returns: {
          distance_m: number
          hours_delta: number
          matched_event_id: string
          source: string
        }[]
      }
      promote_event_verification: {
        Args: {
          p_event_id: string
          p_new_status: string
          p_promoter: string
          p_reason?: string
        }
        Returns: {
          id: string
          new_status: string
          previous_status: string
          promoted_at: string
        }[]
      }
      promote_forecast_run: {
        Args: { p_forecast_run_id: string }
        Returns: {
          active: boolean
          bbox: number[]
          compatibility_forecast_grid_id: string | null
          created_at: string
          forecast_bulletins: Json
          forecast_date: string
          grid_size: number
          hazard_type: Database["public"]["Enums"]["hazard_type"]
          horizon_hours: number
          id: string
          issue_time: string
          manifest_storage_ref: string | null
          model_metadata: Json
          publication_status: string
          published_at: string | null
          region_key: string
          region_name: string
          runout_storage_ref: string | null
          status: string
          updated_at: string
          weather_summary: Json
        }
        SetofOptions: {
          from: "*"
          to: "forecast_runs"
          isOneToOne: true
          isSetofReturn: false
        }
      }
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
        | "model_optimization"
        | "ml_train"
        | "forecast_grid_precompute"
        | "ingest_event"
      label_role: "training_label" | "display_only" | "excluded"
      report_status: "pending" | "verified" | "rejected"
      review_status:
        | "pending"
        | "under_review"
        | "approved"
        | "rejected"
        | "needs_info"
      verification_status:
        | "unverified"
        | "weak"
        | "verified"
        | "expert_verified"
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
      hazard_type: ["avalanche"],
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
        "model_optimization",
        "ml_train",
        "forecast_grid_precompute",
        "ingest_event",
      ],
      label_role: ["training_label", "display_only", "excluded"],
      report_status: ["pending", "verified", "rejected"],
      review_status: [
        "pending",
        "under_review",
        "approved",
        "rejected",
        "needs_info",
      ],
      verification_status: [
        "unverified",
        "weak",
        "verified",
        "expert_verified",
      ],
    },
  },
} as const
