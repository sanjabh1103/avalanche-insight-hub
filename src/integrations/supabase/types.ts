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
          severity: number | null
          source: string | null
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
          severity?: number | null
          source?: string | null
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
          severity?: number | null
          source?: string | null
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
      field_reports: {
        Row: {
          created_at: string
          description: string | null
          id: string
          image_url: string | null
          location: unknown
          status: Database["public"]["Enums"]["report_status"] | null
          timestamp: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          description?: string | null
          id?: string
          image_url?: string | null
          location?: unknown
          status?: Database["public"]["Enums"]["report_status"] | null
          timestamp?: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          description?: string | null
          id?: string
          image_url?: string | null
          location?: unknown
          status?: Database["public"]["Enums"]["report_status"] | null
          timestamp?: string
          user_id?: string | null
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
      model_status: {
        Row: {
          f1_score: number | null
          id: string
          last_trained: string | null
          next_run: string | null
          version: string | null
        }
        Insert: {
          f1_score?: number | null
          id?: string
          last_trained?: string | null
          next_run?: string | null
          version?: string | null
        }
        Update: {
          f1_score?: number | null
          id?: string
          last_trained?: string | null
          next_run?: string | null
          version?: string | null
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
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      event_type: "slab" | "loose" | "wet" | "glide" | "cornice" | "unknown"
      job_status: "pending" | "running" | "completed" | "failed"
      job_type:
        | "forecast"
        | "daily_enrichment"
        | "sentinel_refresh"
        | "fine_tune"
        | "static_precompute"
        | "field_report_enrichment"
      report_status: "pending" | "verified" | "rejected"
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
      ],
      report_status: ["pending", "verified", "rejected"],
    },
  },
} as const
