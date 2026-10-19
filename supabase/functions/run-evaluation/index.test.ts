import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

import { buildOutcomeSliceGroups, pushSliceMetrics } from "./index.ts";

Deno.test("buildOutcomeSliceGroups uses persisted evaluation metadata for elevation and domain slices", () => {
  const outcomes = [
    {
      forecast_id: "fg-1",
      forecast_grid_id: "fg-1",
      cell_row: 0,
      cell_col: 0,
      predicted_risk_score: 4,
      event_observed: true,
      cell_elevation_m: 3125,
      sar_coverage_state: "low_coverage",
      dry_wet_domain: "wet",
      problem_slug: "wet_snow",
    },
    {
      forecast_id: "fg-1",
      forecast_grid_id: "fg-1",
      cell_row: 99,
      cell_col: 4,
      predicted_risk_score: 2,
      event_observed: false,
      cell_elevation_m: 1840,
      sar_coverage_state: "full_coverage",
      dry_wet_domain: "dry",
      problem_slug: "wind_slab",
    },
    {
      forecast_id: "fg-2",
      forecast_grid_id: "fg-2",
      cell_row: 8,
      cell_col: 3,
      predicted_risk_score: 1,
      event_observed: false,
      cell_elevation_m: null,
      sar_coverage_state: null,
      dry_wet_domain: null,
      problem_slug: null,
    },
  ];

  const groups = buildOutcomeSliceGroups(outcomes);

  assertEquals(Object.keys(groups.elevationBands).sort(), ["1500-2000", "3000-3500", "unknown"]);
  assertEquals(groups.elevationBands["3000-3500"][0].cell_row, 0);
  assertEquals(groups.sarCoverageSlices.low_coverage.length, 1);
  assertEquals(groups.sarCoverageSlices.full_coverage.length, 1);
  assertEquals(groups.sarCoverageSlices.unknown.length, 1);
  assertEquals(groups.dryWetDomainSlices.wet.length, 1);
  assertEquals(groups.dryWetDomainSlices.dry.length, 1);
  assertEquals(groups.dryWetDomainSlices.unknown.length, 1);
  assertEquals(groups.problemSlices.wet_snow.length, 1);
  assertEquals(groups.problemSlices.wind_slab.length, 1);
  assertEquals(groups.problemSlices.unknown.length, 1);
});

Deno.test("pushSliceMetrics materializes slice rows with per-slice counts", () => {
  const sliceMetrics: Record<string, unknown>[] = [];
  pushSliceMetrics(sliceMetrics, {
    evalRunId: "eval-1",
    sliceType: "dry_wet_domain",
    groupedOutcomes: {
      wet: [
        {
          forecast_id: "fg-1",
          forecast_grid_id: "fg-1",
          predicted_risk_score: 4,
          event_observed: true,
        },
        {
          forecast_id: "fg-1",
          forecast_grid_id: "fg-1",
          predicted_risk_score: 2,
          event_observed: false,
        },
      ],
    },
  });

  assertEquals(sliceMetrics.length, 1);
  assertEquals(sliceMetrics[0], {
    evaluation_run_id: "eval-1",
    slice_type: "dry_wet_domain",
    slice_value: "wet",
    total_forecasts: 1,
    total_cells: 2,
    observed_events: 1,
    precision_risk3: 1,
    recall_risk3: 1,
    f1_risk3: 1,
    precision_risk4: 1,
    recall_risk4: 1,
    f1_risk4: 1,
    ece: 0.3,
    false_alarm_rate: 0,
    false_positives: 0,
    true_positives: 1,
    risk_distribution: {
      1: 0,
      2: 1,
      3: 0,
      4: 1,
      5: 0,
    },
  });
});
