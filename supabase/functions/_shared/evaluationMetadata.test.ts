import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

import {
  buildElevationBand,
  getCellDryWetDomain,
  getCellElevation,
  getCellProblemSlug,
  getCellSarCoverageState,
  normalizeAsyncHourlyGrids,
} from "./evaluationMetadata.ts";

Deno.test("normalizeAsyncHourlyGrids prefers persisted hourly grids and falls back to legacy grid", () => {
  const persisted = normalizeAsyncHourlyGrids(
    [[{ row: 0, col: 0, risk_score: 3 }]],
    [{ row: 0, col: 0, risk_score: 1 }],
  );
  assertEquals(persisted.length, 1);
  assertEquals(persisted[0][0].risk_score, 3);

  const fallback = normalizeAsyncHourlyGrids(null, [{ row: 0, col: 0, risk_score: 2 }]);
  assertEquals(fallback.length, 1);
  assertEquals(fallback[0][0].risk_score, 2);
});

Deno.test("cell helpers read terrain and coverage metadata from artifact-style cells", () => {
  const cell = {
    row: 4,
    terrain_inputs: { elevation_m: 3125 },
    coverage_flags: { sar_coverage_state: "low_coverage" },
    dry_wet_domain: "wet",
    problem_slug: "wet_snow",
  };

  assertEquals(getCellElevation(cell), 3125);
  assertEquals(getCellSarCoverageState(cell), "low_coverage");
  assertEquals(getCellDryWetDomain(cell), "wet");
  assertEquals(getCellProblemSlug(cell), "wet_snow");
});

Deno.test("buildElevationBand uses real elevation and preserves unknown fallback", () => {
  assertEquals(buildElevationBand(3125), "3000-3500");
  assertEquals(buildElevationBand(null), "unknown");
});
