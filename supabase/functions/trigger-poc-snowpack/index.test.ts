// trigger-poc-snowpack/index.test.ts
//
// Unit tests for the trigger-poc-snowpack Edge Function.
// Tests validation logic and request handling without live Supabase or GitHub API.

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  generateRunId,
  POC_ELEVATION_BAND,
  POC_REGION_KEY,
  validateRequest,
} from "./validation.ts";

const VALID_REQUEST = {
  region_key: POC_REGION_KEY,
  elevation_band: POC_ELEVATION_BAND,
  horizon_hours: 48,
  ensemble_members: 1,
  poc_mode: true,
  decision_record_sha256: "a".repeat(64),
};

Deno.test("validateRequest accepts valid input", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
  });
  assertEquals(errors.length, 0);
});

Deno.test("validateRequest rejects invalid region_key", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    region_key: "invalid_region",
  });
  assertEquals(errors.length, 1);
  assertEquals(errors[0].includes("region_key"), true);
});

Deno.test("validateRequest rejects invalid elevation_band", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    elevation_band: "invalid_band",
  });
  assertEquals(errors.length, 1);
  assertEquals(errors[0].includes("elevation_band"), true);
});

Deno.test("validateRequest rejects zero horizon_hours", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    horizon_hours: 0,
  });
  assertEquals(errors.length, 1);
  assertEquals(errors[0].includes("horizon_hours"), true);
});

Deno.test("validateRequest rejects negative horizon_hours", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    horizon_hours: -1,
  });
  assertEquals(errors.length, 1);
});

Deno.test("validateRequest rejects horizon_hours exceeding max", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    horizon_hours: 72,
  });
  assertEquals(errors.length, 1);
});

Deno.test("validateRequest rejects missing region_key", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    region_key: "",
  });
  assertEquals(errors.length, 1);
});

Deno.test("generateRunId produces expected format", () => {
  const runId = generateRunId(POC_REGION_KEY, POC_ELEVATION_BAND);
  assertEquals(runId.startsWith("poc-"), true);
  assertEquals(runId.includes("pir_panjal_nw_himalaya"), true);
  assertEquals(runId.includes(POC_ELEVATION_BAND), true);
  // Should have format: poc-YYYYMMDDTHHMMSS-region-band-random
  const parts = runId.split("-");
  assertEquals(parts.length >= 5, true);
});

Deno.test("generateRunId produces unique values", () => {
  const ids = new Set<string>();
  for (let i = 0; i < 100; i++) {
    ids.add(generateRunId(POC_REGION_KEY, POC_ELEVATION_BAND));
  }
  // With random suffix, all 100 should be unique
  assertEquals(ids.size, 100);
});

Deno.test("validateRequest accepts only the frozen POC scope", () => {
  assertEquals(validateRequest(VALID_REQUEST).length, 0);
});

Deno.test("validateRequest rejects non-POC scope and missing trust fields", () => {
  const errors = validateRequest({
    ...VALID_REQUEST,
    region_key: "himalayas_nepal",
    elevation_band: "lower",
    horizon_hours: 72,
    ensemble_members: 10,
    poc_mode: false,
    decision_record_sha256: "bad",
  });
  assertEquals(errors.length, 6);
});
