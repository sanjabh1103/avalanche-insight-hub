function asFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

export function estimateElevation(
  row: number,
  totalRows: number,
  regionMinElev: number,
  regionMaxElev: number,
): number {
  const elevationRange = regionMaxElev - regionMinElev;
  return regionMinElev + (row / totalRows) * elevationRange;
}

export function normalizeAsyncHourlyGrids(
  hourlyGrids: unknown,
  gridGeojson: unknown,
): Record<string, unknown>[][] {
  if (Array.isArray(hourlyGrids) && hourlyGrids.length > 0) {
    return hourlyGrids
      .filter((grid) => Array.isArray(grid))
      .map((grid) =>
        (grid as unknown[]).filter(
          (cell): cell is Record<string, unknown> => Boolean(cell) && typeof cell === "object",
        )
      );
  }
  if (!Array.isArray(gridGeojson)) return [];
  const baseGrid = gridGeojson.filter(
    (cell): cell is Record<string, unknown> => Boolean(cell) && typeof cell === "object",
  );
  return baseGrid.length > 0 ? [baseGrid] : [];
}

export function getCellElevation(cell: Record<string, unknown>): number {
  const terrainInputs = (cell.terrainInputs ?? cell.terrain_inputs) as Record<string, unknown> | undefined;
  const terrainElevation = asFiniteNumber(terrainInputs?.elevation_m ?? terrainInputs?.elevationM);
  if (terrainElevation !== null) return terrainElevation;

  const fallbackElevation = asFiniteNumber(cell.elevation_m ?? cell.elevation);
  if (fallbackElevation !== null) return fallbackElevation;

  return estimateElevation(Number(cell.row ?? 0), 20, 1000, 4500);
}

export function getCellSarCoverageState(cell: Record<string, unknown>): string | null {
  const coverageFlags = (cell.coverageFlags ?? cell.coverage_flags) as Record<string, unknown> | undefined;
  const explicit = coverageFlags?.sar_coverage_state ?? cell.sar_coverage_state;
  return typeof explicit === "string" && explicit.trim() !== "" ? explicit : null;
}

export function getCellDryWetDomain(cell: Record<string, unknown>): string | null {
  const explicit = cell.dryWetDomain ?? cell.dry_wet_domain;
  return typeof explicit === "string" && explicit.trim() !== "" ? explicit : null;
}

export function getCellProblemSlug(cell: Record<string, unknown>): string | null {
  const explicit = cell.problemSlug ?? cell.problem_slug;
  return typeof explicit === "string" && explicit.trim() !== "" ? explicit : null;
}

export function buildElevationBand(
  elevationM: number | null | undefined,
  bandWidthM = 500,
): string {
  if (typeof elevationM !== "number" || !Number.isFinite(elevationM)) return "unknown";
  const lower = Math.floor(elevationM / bandWidthM) * bandWidthM;
  return `${lower}-${lower + bandWidthM}`;
}
