// trigger-poc-snowpack/index.ts
//
// Phase 3: Edge Function that triggers a SNOWPACK POC run on GitHub Actions.
//
// Flow:
//   1. Receives POST with region_key, elevation_band, horizon_hours, poc_mode
//   2. Validates authorization (same pattern as trigger-job)
//   3. Inserts a row into snowpack_runs with status='queued'
//   4. Sends repository_dispatch to GitHub Actions API
//   5. Returns the run_id and snowpack_runs row id
//
// Required Supabase secrets:
//   SUPABASE_URL          — set by Supabase runtime
//   SUPABASE_SERVICE_ROLE_KEY — set by Supabase runtime
//   GITHUB_PAT            — GitHub Personal Access Token (repo scope)
//   GITHUB_REPO_OWNER     — e.g. "sanjayb"
//   GITHUB_REPO_NAME      — e.g. "avalanche-insight-hub"
//
// Edge Function limits (Free plan): 150s wall clock, 2s CPU, 256 MB memory.
// This function only creates a DB row + dispatches a GitHub API call —
// well within limits. SNOWPACK execution happens on GitHub Actions runners.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  generateRunId,
  type PocSnowpackRequest,
  validateRequest,
} from "./validation.ts";
import { authorizeJobRequest } from "../_shared/auth.ts";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL") ?? "",
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
);

const GITHUB_API_VERSION = "2022-11-28";
const EXPECTED_GITHUB_REPO_OWNER = "sanjabh11";
const EXPECTED_GITHUB_REPO_NAME = "avalanche-insight-hub";

function json(body: Record<string, unknown>, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function dispatchGitHubActions(
  runId: string,
  regionKey: string,
  elevationBand: string,
  horizonHours: number,
  ensembleMembers: number,
  pocMode: boolean,
  decisionRecordSha256: string,
  toolchainManifestId: string | undefined,
  rowId: string,
): Promise<{ success: boolean; runUrl: string | null; error: string | null }> {
  const githubPat = Deno.env.get("GITHUB_PAT");
  const repoOwner = Deno.env.get("GITHUB_REPO_OWNER");
  const repoName = Deno.env.get("GITHUB_REPO_NAME");

  if (!githubPat || !repoOwner || !repoName) {
    return {
      success: false,
      runUrl: null,
      error: "Missing GITHUB_PAT, GITHUB_REPO_OWNER, or GITHUB_REPO_NAME env vars",
    };
  }

  // This function is the private hosted POC dispatch path. Fail closed if
  // Supabase secrets are ever repointed at the scrubbed public repository.
  if (
    repoOwner !== EXPECTED_GITHUB_REPO_OWNER ||
    repoName !== EXPECTED_GITHUB_REPO_NAME
  ) {
    return {
      success: false,
      runUrl: null,
      error: "GitHub dispatch target must be the configured private repository",
    };
  }

  // client_payload has a limit of 10 top-level keys and ~64 KB.
  // We keep it minimal — the workflow reads full config from the DB row.
  const payload: Record<string, unknown> = {
    run_id: runId,
    region_key: regionKey,
    elevation_band: elevationBand,
    horizon_hours: horizonHours,
    ensemble_members: ensembleMembers,
    poc_mode: pocMode,
    decision_record_sha256: decisionRecordSha256,
    snowpack_run_row_id: rowId,
  };
  if (toolchainManifestId) {
    payload.toolchain_manifest_id = toolchainManifestId;
  }

  const apiUrl =
    `https://api.github.com/repos/${repoOwner}/${repoName}/dispatches`;

  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${githubPat}`,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        event_type: "poc-snowpack-request",
        client_payload: payload,
      }),
    });

    if (response.status === 204) {
      // GitHub returns 204 No Content on success — no run URL in response.
      // The workflow run URL must be constructed or fetched separately.
      return {
        success: true,
        runUrl: `https://github.com/${repoOwner}/${repoName}/actions`,
        error: null,
      };
    }

    const errorText = await response.text();
    return {
      success: false,
      runUrl: null,
      error: `GitHub API returned ${response.status}: ${errorText}`,
    };
  } catch (err) {
    return {
      success: false,
      runUrl: null,
      error: `GitHub API fetch failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  const authResult = await authorizeJobRequest("poc_snowpack", req, supabase);
  if (!authResult.authorized) {
    return json({ error: authResult.error ?? "Unauthorized" }, authResult.status ?? 401);
  }

  let body: PocSnowpackRequest;
  try {
    body = await req.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  const validationErrors = validateRequest(body);
  if (validationErrors.length > 0) {
    return json({ error: "Validation failed", details: validationErrors }, 400);
  }

  const runId = generateRunId(body.region_key, body.elevation_band);

  // Insert snowpack_runs row with status='queued'
  const { data: insertData, error: insertError } = await supabase
    .from("snowpack_runs")
    .insert({
      run_id: runId,
      status: "queued",
      region_key: body.region_key,
      elevation_band: body.elevation_band,
      horizon_hours: body.horizon_hours,
      ensemble_members: body.ensemble_members,
      poc_mode: body.poc_mode,
      decision_record_sha256: body.decision_record_sha256,
      toolchain_manifest_id: body.toolchain_manifest_id ?? null,
    })
    .select()
    .single();

  if (insertError || !insertData) {
    return json({
      error: "Failed to create snowpack_runs row",
      detail: insertError?.message ?? "No data returned",
    }, 500);
  }

  const rowId = insertData.id;

  // Dispatch to GitHub Actions
  const dispatchResult = await dispatchGitHubActions(
    runId,
    body.region_key,
    body.elevation_band,
    body.horizon_hours,
    body.ensemble_members,
    body.poc_mode,
    body.decision_record_sha256,
    body.toolchain_manifest_id,
    rowId,
  );

  if (!dispatchResult.success) {
    // Update the row to 'failed' since dispatch failed
    await supabase
      .from("snowpack_runs")
      .update({
        status: "failed",
        error: dispatchResult.error,
      })
      .eq("id", rowId);

    return json({
      error: "GitHub Actions dispatch failed",
      detail: dispatchResult.error,
      run_id: runId,
      snowpack_run_id: rowId,
    }, 502);
  }

  // Update row with GitHub run URL
  await supabase
    .from("snowpack_runs")
    .update({
      github_run_url: dispatchResult.runUrl,
      status: "building",
    })
    .eq("id", rowId);

  return json({
    run_id: runId,
    snowpack_run_id: rowId,
    status: "building",
    github_run_url: dispatchResult.runUrl,
    message: "SNOWPACK POC run dispatched to GitHub Actions",
  }, 200);
});
