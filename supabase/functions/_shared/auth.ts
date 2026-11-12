export function extractBearerToken(authorizationHeader: string | null): string | null {
  if (!authorizationHeader) return null;
  const [scheme, token] = authorizationHeader.split(/\s+/, 2);
  if (!scheme || scheme.toLowerCase() !== "bearer" || !token) {
    return null;
  }
  return token.trim() || null;
}

export function parseCsvEnv(raw: string | undefined, { lowercase = false } = {}): Set<string> {
  return new Set(
    (raw ?? "")
      .split(",")
      .map((value) => lowercase ? value.trim().toLowerCase() : value.trim())
      .filter(Boolean),
  );
}

export function extractAdminRoles(appMetadata: unknown): string[] {
  if (!appMetadata || typeof appMetadata !== "object") {
    return [];
  }
  const roles = (appMetadata as Record<string, unknown>).roles;
  if (Array.isArray(roles)) {
    return roles
      .map((value) =>
        typeof value === "string" ? value.trim().toLowerCase() : ""
      )
      .filter(Boolean);
  }
  if (typeof roles === "string" && roles.trim()) {
    return [roles.trim().toLowerCase()];
  }
  return [];
}

export interface AuthContext {
  authorized: boolean;
  error?: string;
  status?: number;
  audit?: Record<string, unknown> | null;
}

export async function authorizeJobRequest(
  _type: string,
  req: Request,
  supabase: any,
): Promise<AuthContext> {
  // Check if REQUIRE_JOB_AUTH is disabled — but NEVER allow disabling in production
  const requireJobAuth = Deno.env.get("REQUIRE_JOB_AUTH");
  const isProduction = !!Deno.env.get("DENO_DEPLOYMENT_ID");
  if (
    !isProduction &&
    (requireJobAuth === "false" || requireJobAuth === "0" || requireJobAuth === "off" || requireJobAuth === "no")
  ) {
    return { authorized: true, audit: { source: "disabled" } };
  }

  const callerAuthorization = req.headers.get("authorization");
  const jobTokenHeader = req.headers.get("x-job-token")?.trim() || null;
  // Cron sends a valid Supabase JWT in Authorization so the gateway can
  // satisfy verify_jwt=true, and the dedicated job token in x-job-token.
  // Prefer the explicit job-token channel so a caller cannot accidentally
  // route a valid but non-system bearer token through the cron path.
  const token = jobTokenHeader || extractBearerToken(callerAuthorization);

  // 1. Check System / Cron Token
  const systemToken = Deno.env.get("JOB_DISPATCH_TOKEN");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  if (token && (
    (systemToken && token === systemToken) ||
    (serviceRoleKey && token === serviceRoleKey)
  )) {
    return { authorized: true, audit: { source: "system_token" } };
  }

  if (!token) {
    return {
      authorized: false,
      status: 401,
      error: "Missing authorization token",
    };
  }

  // 2. Check User JWT via Supabase Auth
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data?.user) {
    return {
      authorized: false,
      status: 401,
      error: "Invalid or expired authorization token",
    };
  }

  const user = data.user;
  const adminRoles = extractAdminRoles(user.app_metadata);
  const adminUserIds = parseCsvEnv(Deno.env.get("ADMIN_USER_IDS"));
  const adminEmails = parseCsvEnv(Deno.env.get("ADMIN_USER_EMAILS"), {
    lowercase: true,
  });
  const normalizedEmail = typeof user.email === "string"
    ? user.email.trim().toLowerCase()
    : "";

  let authSource: string | null = null;
  if (adminRoles.includes("admin")) {
    authSource = "app_metadata.roles";
  } else if (adminUserIds.has(user.id)) {
    authSource = "ADMIN_USER_IDS";
  } else if (normalizedEmail && adminEmails.has(normalizedEmail)) {
    authSource = "ADMIN_USER_EMAILS";
  }

  if (!authSource) {
    return {
      authorized: false,
      status: 403,
      error: "Administrative privileges are required for this action",
    };
  }

  return {
    authorized: true,
    audit: {
      user_id: user.id,
      user_email: user.email ?? null,
      app_metadata_roles: adminRoles,
      auth_source: authSource,
    },
  };
}

export async function incrementGeminiUsage(supabase: any) {
  const { data: config, error: readErr } = await supabase
    .from("system_config")
    .select("id, gemini_usage, gemini_spend_cap")
    .limit(1)
    .maybeSingle();

  if (readErr) throw readErr;

  if (config?.id) {
    const { error: updateErr } = await supabase
      .from("system_config")
      .update({ gemini_usage: (config.gemini_usage || 0) + 1 })
      .eq("id", config.id);

    if (updateErr) throw updateErr;
    return;
  }

  const { error: insertErr } = await supabase
    .from("system_config")
    .insert({ gemini_usage: 1, gemini_spend_cap: 1000 });

  if (insertErr) throw insertErr;
}

/**
 * Atomically reserve a Gemini API call slot against the spend cap.
 *
 * This replaces the read-check-call-increment pattern with a single atomic
 * Postgres RPC that increments gemini_usage only if the cap has not been
 * reached. Returns true if the caller may proceed with the API call, false
 * if the cap has been exceeded (fail-closed on RPC error).
 */
export async function reserveGeminiUsage(supabase: any): Promise<boolean> {
  try {
    const { data, error } = await supabase.rpc("reserve_gemini_usage");
    if (error) {
      console.error("reserve_gemini_usage RPC failed:", error);
      return false;
    }
    return data?.reserved === true;
  } catch (err) {
    console.error("reserve_gemini_usage RPC threw:", err);
    return false;
  }
}

export async function isGeminiSpendCapExceeded(supabase: any): Promise<boolean> {
  const { data: config, error } = await supabase
    .from("system_config")
    .select("gemini_usage, gemini_spend_cap")
    .limit(1)
    .maybeSingle();
  if (error) {
    console.error("Failed to read system config for Gemini spend cap:", error);
    return false;
  }
  if (!config) return false;
  const usage = config.gemini_usage || 0;
  const cap = config.gemini_spend_cap || 1000;
  return usage >= cap;
}
