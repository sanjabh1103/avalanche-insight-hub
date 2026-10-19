import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient, type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import { extractBearerToken } from "../_shared/auth.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonResponse(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function trimString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function clientIp(req: Request): string {
  const forwarded = req.headers.get("cf-connecting-ip")
    ?? req.headers.get("x-real-ip")
    ?? req.headers.get("x-forwarded-for")
    ?? "";
  const first = forwarded.split(",")[0]?.trim();
  return first || "unknown";
}

async function sha256Hex(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function currentHourBucket(): string {
  const date = new Date();
  date.setUTCMinutes(0, 0, 0);
  return date.toISOString();
}

function parseRateLimit(): number {
  const raw = Number(Deno.env.get("FIELD_REPORT_RATE_LIMIT_PER_HOUR") ?? "5");
  if (!Number.isFinite(raw) || raw < 1) return 5;
  return Math.floor(raw);
}

async function authenticatedUserId(supabase: SupabaseClient, req: Request): Promise<string | null> {
  const token = extractBearerToken(req.headers.get("authorization"));
  if (!token) return null;

  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  if (token === serviceRoleKey || token === anonKey) {
    return null;
  }

  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data?.user?.id) {
    return null;
  }
  return data.user.id as string;
}

function validatePayload(payload: Record<string, unknown>) {
  const lat = Number(payload.lat);
  const lng = Number(payload.lng);
  const description = trimString(payload.description);
  const timestampRaw = trimString(payload.timestamp);
  const timestamp = timestampRaw || new Date().toISOString();
  const observedAt = new Date(timestamp);
  const clientReportId = trimString(payload.clientReportId);
  if (!clientReportId) {
    return { ok: false as const, error: "clientReportId is required" };
  }
  const locationName = trimString(payload.locationName) || null;

  if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
    return { ok: false as const, error: "Invalid latitude" };
  }
  if (!Number.isFinite(lng) || lng < -180 || lng > 180) {
    return { ok: false as const, error: "Invalid longitude" };
  }
  if (description.length < 1 || description.length > 2000) {
    return { ok: false as const, error: "Description must be between 1 and 2000 characters" };
  }
  if (Number.isNaN(observedAt.getTime())) {
    return { ok: false as const, error: "Invalid timestamp" };
  }
  if (clientReportId.length > 128) {
    return { ok: false as const, error: "clientReportId is too long" };
  }

  return {
    ok: true as const,
    value: {
      lat,
      lng,
      description,
      timestamp: observedAt.toISOString(),
      clientReportId,
      locationName,
      submittedOffline: Boolean(payload.submittedOffline),
    },
  };
}

export async function handleSubmitFieldReport(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    if (!serviceRoleKey || !supabaseUrl) {
      throw new Error("Missing Supabase service configuration");
    }

    const supabase = createClient(supabaseUrl, serviceRoleKey);
    let rawPayload: unknown;
    try {
      rawPayload = await req.json();
    } catch {
      return jsonResponse({ error: "Invalid JSON payload" }, 400);
    }
    const payload = asObject(rawPayload);
    const validation = validatePayload(payload);
    if (!validation.ok) {
      return jsonResponse({ error: validation.error }, 400);
    }

    const report = validation.value;
    const userId = await authenticatedUserId(supabase, req);

    // Check for duplicate BEFORE rate limiting so legitimate retries are not penalized
    const { data: existing, error: existingError } = await supabase
      .from("field_reports")
      .select("id")
      .eq("client_report_id", report.clientReportId)
      .maybeSingle();
    if (existingError) throw existingError;
    if (existing?.id) {
      return jsonResponse({
        ok: true,
        fieldReportId: existing.id,
        clientReportId: report.clientReportId,
        locationName: report.locationName,
        duplicate: true,
      });
    }

    const limit = parseRateLimit();
    const salt = Deno.env.get("FIELD_REPORT_RATE_LIMIT_SALT") || serviceRoleKey;
    const ipHash = await sha256Hex(`${salt}:${clientIp(req)}`);
    const hourBucket = currentHourBucket();
    const { data: rateRows, error: rateError } = await supabase.rpc(
      "increment_field_report_rate_limit",
      {
        p_ip_hash: ipHash,
        p_hour_bucket: hourBucket,
        p_limit: limit,
      },
    );
    if (rateError) throw rateError;

    const rateRow = Array.isArray(rateRows) ? rateRows[0] : rateRows;
    const requestCount = Number(rateRow?.request_count ?? 0);
    if (!rateRow?.allowed) {
      return jsonResponse({
        error: "Field report rate limit exceeded",
        rateLimit: {
          limit,
          remaining: 0,
          hourBucket,
        },
      }, 429);
    }

    const reportRow = {
      user_id: userId,
      review_status: "pending",
      training_eligible: false,
      description: report.description,
      location: `SRID=4326;POINT(${report.lng} ${report.lat})`,
      timestamp: report.timestamp,
      client_report_id: report.clientReportId,
      sync_status: "synced",
      submitted_offline: report.submittedOffline,
      synced_at: new Date().toISOString(),
    };
    const { data: created, error: insertError } = await supabase
      .from("field_reports")
      .insert(reportRow)
      .select("id")
      .maybeSingle();

    if (insertError && insertError.code !== "23505") throw insertError;

    let fieldReportId = created?.id as string | undefined;
    if (!fieldReportId && insertError?.code === "23505") {
      const { data: raceExisting, error: raceError } = await supabase
        .from("field_reports")
        .select("id")
        .eq("client_report_id", report.clientReportId)
        .maybeSingle();
      if (raceError) throw raceError;
      fieldReportId = raceExisting?.id as string | undefined;
    }
    if (!fieldReportId) {
      throw new Error("Failed to create field report");
    }

    return jsonResponse({
      ok: true,
      fieldReportId,
      clientReportId: report.clientReportId,
      locationName: report.locationName,
      rateLimit: {
        limit,
        remaining: Math.max(0, limit - requestCount),
        hourBucket,
      },
    });
  } catch (err) {
    console.error("submit-field-report error:", err);
    return jsonResponse({ error: "Internal server error" }, 500);
  }
}

if (import.meta.main) {
  serve(handleSubmitFieldReport);
}
